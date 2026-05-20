# GAAMA Memory System Analysis

## Overview

GAAMA (Graph-Augmented Agent Memory Architecture) is a long-term memory (LTM) system for AI agents that stores knowledge as a typed knowledge graph. It converts raw conversation traces into a hierarchy of memory nodes (episodes, facts, concepts, reflections) connected by typed edges, then retrieves relevant memories using a hybrid of vector similarity search and Personalized PageRank (PPR) over the graph structure.

The system has no short-term memory (STM) component -- it operates exclusively as an LTM store with a trace buffer for ingestion.

Core pipeline: **Ingest -> Create (extract+embed) -> Retrieve (KNN + PPR) -> Integrate (prompt composition)**

## Storage Layer

**Primary store:** SQLite with WAL mode (`adapters/sqlite_memory.py`)

Three logical tables in a single SQLite database:
- `nodes` -- node_id (PK), node_class, payload (JSON blob), updated_at
- `edges` -- edge_id (PK), edge_type, source_id, target_id, weight, created_at, label
- `node_fts` -- FTS5 virtual table for BM25 full-text search (columns: node_id, agent_id, user_id, task_id, content)
- `edge_fts` -- FTS5 virtual table for edge content search

**Vector store:** SQLite + `sqlite-vec` extension (`adapters/sqlite_vector.py`)
- `embedding_rows` -- maps entity_id to scope metadata (agent_id, user_id, task_id)
- `vec_embeddings` -- vec0 virtual table storing float32 vectors with cosine distance metric
- Default dimension: 1536 (OpenAI text-embedding-3-large)
- One embedding row inserted per scope per node (supports multi-tenant visibility)

**Blob store:** Local filesystem (`adapters/local_blob.py`) for raw trace payloads.

**Serialization:** Nodes are stored as JSON blobs via `infra/serialization.py`. The `serialize_node` / `deserialize_node` functions handle datetime coercion, legacy field migration (e.g., `confidence` -> `belief`, single `scope` -> `scopes` list), and provenance reconstruction.

## Write / Extraction Logic

Writing is a three-step LLM pipeline orchestrated by `services/ltm_creator.py` (class `LTMCreator`):

### Step 1: Episode Creation (no LLM)
- Each non-empty `TraceEvent` becomes an episode `MemoryNode` (lines 97-121)
- Episodes are linked in a temporal chain via `NEXT` edges
- The last existing episode for the agent is fetched and linked to the first new episode

### Step 2: Fact + Concept Extraction (LLM)
- Context retrieval: vector-searches existing episodes (similarity >= 0.75 threshold) and their connected facts, plus existing concept nodes
- Single LLM call using `prompts/fact_generation.md` extracts atomic facts and topic concepts
- Creates `DERIVED_FROM` edges (fact -> source episode), `HAS_CONCEPT` edges (episode -> concept), and `ABOUT_CONCEPT` edges (fact -> concept)
- Existing concepts are reused by label match; new ones get deterministic IDs via `canonical_id_entity`

### Step 3: Reflection Generation (LLM)
- Context retrieval: vector-searches similar existing facts and their connected reflections
- LLM call using `prompts/reflection_generation.md` synthesizes higher-order insights from facts
- Creates `DERIVED_FROM_FACT` edges (reflection -> source facts)

### Chunking
The orchestrator (`services/orchestrator.py`) supports token-bounded chunking (`max_tokens_per_chunk`) or fixed-size chunking (`chunk_size` + `chunk_overlap`) to process long trace buffers incrementally.

### Extraction Policy (`core/policies.py`)
Minimal config: `min_confidence=0.4`, `min_novelty=0.3`, `include_sensitive=False`, `require_provenance=True`.

## Read / Retrieval Logic

Primary retrieval engine: `NodeKNNPageRankRetrievalEngine` in `services/ltm_retriever.py`.

### Default Mode (KNN + PPR)
1. **KNN search** -- query the vector store for top-K nodes (K = 2x total budget, typically 40+)
2. **Seed selection** -- top KNN nodes by similarity become PPR seed distribution
3. **Graph expansion** -- BFS from seeds to depth `expansion_depth` (default 1) collecting edges
4. **Personalized PageRank** -- run PPR on the expanded subgraph (alpha=0.6, max 100 iterations, tolerance 1e-6) (`services/pagerank.py`)
5. **Scoring** -- final score = `ppr_weight * normalized_ppr + sim_weight * normalized_sim`, multiplied by `_belief_weight` (GEL-sourced nodes get special weight)
6. **Budgeting** -- results bucketed by kind (fact, reflection, skill, episode) with per-kind caps from `RetrievalBudget`
7. **Episode ordering** -- episodes sorted chronologically by `sequence` field

### Alternative Modes
- **Semantic-only** (`semantic_only=True`): pure vector KNN, no graph expansion or PPR
- **Hybrid** (`hybrid=True`): runs semantic and PPR in parallel, uses same-type replacement (PPR items replace weakest semantic items of same kind if score is higher)
- **Budgetless** (`budgetless=True`): ignores per-type caps, fills by global score ranking until `max_memory_words` is hit

### Hybrid Search (BM25 + Semantic)
`services/hybrid_search.py` provides a `HybridSearcher` that runs FTS5 BM25 and vector search in parallel threads, then fuses scores with configurable weights (default: BM25=0.4, semantic=0.6).

### LLM-Derived Budget
The orchestrator can optionally call an LLM to allocate the retrieval budget across categories (facts, reflections, skills, episodes) based on the query.

### Graph Edit Learning (GEL) -- `services/graph_edit_learner.py`
A post-retrieval corrective layer. When retrieved memory is insufficient:
1. Judge retrieval quality (online mode: LLM judge; batch mode: reward threshold)
2. Generate analysis questions via LLM
3. Explore graph for each sub-question (no LLM)
4. LLM reasons over results and plans graph edits (CREATE_FACT, CREATE_CONCEPT)
5. Optional LLM verification gate filters inaccurate edits
6. Execute edits (with dedup via cosine similarity threshold of 0.90)

GEL-created facts get `belief=0.85` (capped) and are tagged `source=gel`.

## Lifecycle / Decay Mechanism

**There is no automatic temporal decay, TTL, or scheduled forgetting.** Key observations:

- `MemoryNode.belief` (0.0-1.0) acts as a static confidence score set at creation time. It is never automatically decremented.
- `MemoryNode.time_valid_from` / `time_valid_to` fields exist but are not consulted during retrieval.
- `LTMForgettingEngine` (line 556 of `ltm_retriever.py`) is a simple query-and-delete mechanism: it queries nodes matching a `QueryFilters` selector and returns their IDs for deletion. No decay curve or staleness logic.
- `ForgetReport` tracks `deleted_node_ids`, `tombstone_ids`, `rewired_edge_ids` -- suggesting a design intention for soft-delete / edge rewiring, but the implementation only does hard deletion.
- `MemoryPack.trim_by_words()` implements a budget-proportional trimming that removes lowest-ranked items when the result exceeds word limits, but this is output shaping, not lifecycle management.
- The `clear_ltm()` method on both stores provides a full wipe (no selective decay).

**Net effect:** Memories persist indefinitely unless explicitly deleted via the `forget()` API.

## Key Data Structures

### MemoryNode (`core/types.py:73`)
Single discriminated-union dataclass for all node kinds. Key fields:
- `node_id`, `kind` (entity/fact/episode/reflection/skill/concept)
- `belief` (float 0-1), `relevance_score`, `sequence` (global ordering)
- `scopes: List[Scope]` (multi-tenant ownership: agent_id, user_id, task_id)
- Kind-specific content: `fact_text`, `summary`, `reflection_text`, `concept_label`, `skill_description`
- `embedding: Optional[Sequence[float]]`

### Edge (`core/types.py:137`)
Frozen dataclass: `edge_id`, `edge_type` (NEXT, DERIVED_FROM, DERIVED_FROM_FACT, HAS_CONCEPT, ABOUT_CONCEPT), `source_id`, `target_id`, `weight`, `label`.

### MemoryPack (`core/types.py:182`)
Retrieval result container with categorized string lists: `facts`, `reflections`, `skills`, `episodes`, plus `scores` dict and `citations`.

### RetrievalBudget (`core/types.py:163`)
Controls retrieval limits: `max_facts=8`, `max_reflections=4`, `max_skills=4`, `max_episodes=4`, `max_items=20`, `max_tokens=1500`.

### Scope (`core/types.py:39`)
Multi-tenant visibility context: `agent_id`, `user_id`, `task_id`. Nodes can have multiple scopes.

### GELConfig (`core/types.py:394`)
Controls the Graph Edit Learning system: reward threshold, max analysis questions, max edits, dedup similarity threshold, verification flags.

## Notable Design Decisions

1. **Single MemoryNode type with kind discriminator** -- avoids class hierarchy; all node kinds share one table and one serialization path. Trade-off: many fields are unused per kind.

2. **Concept nodes as graph connectors** -- concepts serve as topical hubs linking thematically related episodes and facts, enabling PPR to surface relevant memories even when direct text similarity is low.

3. **PPR + cosine similarity additive scoring** -- the retrieval engine combines structural graph proximity (PPR) with semantic similarity (cosine). Both are max-normalized to [0,1] before addition, ensuring neither dominates.

4. **Hub dampening** in `edges_from_core_edges` (pagerank.py:110) -- nodes with out-degree > 50 have edge weights scaled down by `threshold/degree`, preventing mega-hubs from diffusing PPR mass uniformly.

5. **No STM** -- the system is LTM-only. Context from recent conversation is rendered directly from the trace buffer (`_render_context_from_buffer`), not from a separate memory store.

6. **GEL as self-healing** -- the graph edit learner is a novel corrective feedback loop: when retrieval fails (low reward), it dynamically identifies gaps and inserts new facts/concepts to improve future retrievals.

7. **Multi-scope per node** -- a single memory node can be visible to multiple (agent, user, task) combinations, supporting shared memory across contexts.

8. **Embedding-per-scope storage** -- the vector store inserts one row per scope per node, enabling scope-filtered KNN queries without post-filtering.

9. **No automatic decay** -- the system trusts belief scores set at write time and relies on explicit `forget()` calls. This avoids complexity but means stale information persists until actively managed.

10. **Deterministic node IDs** (`canonical_id_entity`) for facts and concepts -- enables natural deduplication on upsert; inserting the same fact twice hits the same node_id.

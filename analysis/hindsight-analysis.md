# Hindsight Memory System Analysis

## Overview

Hindsight (by Vectorize) is an agent long-term memory system built as a Python/FastAPI monorepo. It stores memories as atomic **facts** organized into **banks** (isolated memory stores per user/agent). The system implements three core operations:

- **Retain**: Ingest content, extract facts via LLM, embed them, and store with entity/temporal/semantic links.
- **Recall**: Retrieve relevant memories via 4-way parallel search (semantic, BM25, graph, temporal) with fusion and reranking.
- **Reflect**: Agentic reasoning over retrieved memories using tool-calling LLM with access to observations and mental models.

Facts are classified as:
- `world` — general knowledge
- `experience` — personal/agent experiences
- `observation` — auto-consolidated summaries (bottom-up from raw facts)

The system also supports user-defined **mental models** (pinned reflections refreshed on demand) and **directives** (stored instructions).

## Storage Layer

**Database**: PostgreSQL with `pgvector` extension (also supports Oracle 23ai, pgvectorscale, VectorChord, AlloyDB ScANN).

**Schema** (managed via Alembic migrations in `hindsight_api/alembic/`):

| Table | Purpose |
|-------|---------|
| `banks` | Isolated memory stores (bank_id PK, name, disposition/personality JSONB, background) |
| `memory_units` | Core fact storage (UUID PK, bank_id, text, embedding vector(384), context, event_date, occurred_start/end, mentioned_at, fact_type, metadata JSONB, tags, proof_count, source_memory_ids, consolidated_at) |
| `memory_links` | Graph edges (from_unit_id, to_unit_id, link_type, weight 0-1, entity_id) |
| `entities` | Named entities (UUID PK, canonical_name, bank_id, mention_count, first/last_seen) |
| `unit_entities` | Junction table: memory_unit <-> entity mapping |
| `entity_cooccurrences` | Entity co-occurrence counts for graph retrieval |
| `documents` | Source document tracking (id, bank_id, original_text, content_hash) |
| `chunks` | Text chunks within documents (chunk_id, document_id, bank_id, chunk_text, content_hash) |
| `async_operations` | Background task queue (operation_id UUID, status, task_payload JSONB) |

**Multi-tenancy**: Schema-per-tenant isolation enforced via context variables. All table references go through `fq_table()` which prefixes the schema name. A runtime SQL validator (`validate_sql_schema`) prevents unqualified table access.

**File**: `hindsight_api/alembic/versions/5a366d414dce_initial_schema.py` (lines 132-460)

**Connection pooling**: asyncpg with configurable min/max pool sizes, read replicas supported via separate read backend.

## Write / Extraction Logic

**Entry point**: `MemoryEngine.retain_batch_async()` in `engine/memory_engine.py`

**Pipeline** (orchestrated by `engine/retain/orchestrator.py`):

1. **Chunking** — Content split into ~3000-char chunks (`fact_extraction.chunk_text`).
2. **Fact Extraction** — Each chunk sent to LLM with structured output schema. Extracts: fact text (combined "what | when | where | who | why"), fact_type (world/experience), entities, temporal dates (occurred_start/end), causal relations, location. (`engine/retain/fact_extraction.py`)
3. **Embedding** — Each fact text augmented with date info, then embedded via sentence-transformers (384-dim, local default) or external TEI. (`engine/retain/embedding_processing.py`)
4. **Entity Resolution** — Trigram GIN scan + co-occurrence scoring to match extracted entity names to existing canonical entities. (`engine/entity_resolver.py`)
5. **Storage** (3-phase transaction design):
   - **Phase 1** (read-only, separate connection): Entity resolution + semantic ANN search for similar existing facts.
   - **Phase 2** (write transaction): Insert facts into `memory_units`, create `unit_entities` links, insert temporal/semantic/causal links into `memory_links`. Document ownership enforced via `SELECT ... FOR UPDATE`.
   - **Phase 3** (post-commit, best-effort): Entity links for UI visualization, entity stats flush.
6. **Final Semantic ANN Pass** — After all batches commit, a single pass creates semantic links for all new units against the full bank (chunked, parallelized).

**Delta Retain**: When re-ingesting a document, only changed/new chunks are re-processed. Unchanged chunks detected via content_hash comparison. (`_try_delta_retain` in orchestrator.py, line 1520)

**Streaming Producer-Consumer**: Large documents processed in streaming mini-batches. LLM extraction (producer) runs concurrently with DB writes (consumer) via `asyncio.Queue`. Each batch commits independently for crash recovery.

**Link types created during retain**:
- `temporal` — time proximity between facts (weight = time decay)
- `semantic` — embedding cosine similarity >= 0.7 (weight = similarity score)
- `entity` — shared entity connections (for UI visualization only; retrieval uses self-join)
- `causes`/`caused_by`/`enables`/`prevents` — explicit causal chains from LLM extraction

## Read / Retrieval Logic

**Entry point**: `MemoryEngine.recall_async()` in `engine/memory_engine.py` (line 2635)

**Pipeline** (`engine/search/retrieval.py`):

1. **Query Embedding** — Embed the query text.
2. **4-Way Parallel Retrieval** (per fact type):
   - **Semantic** — HNSW vector similarity search with 5x over-fetch, cosine distance. Uses partial per-fact-type indexes.
   - **BM25** — Full-text keyword search via PostgreSQL `tsvector`/GIN (or VectorChord BM25, or pg_textsearch).
   - **Graph** — Link expansion retrieval (`engine/search/link_expansion_retrieval.py`): finds semantic seeds, then expands through entity co-occurrence self-join, precomputed semantic links, and causal links.
   - **Temporal** — Date-range query with spreading activation through temporal/causal links. Entry points ranked by date, filtered by embedding similarity threshold.
3. **Reciprocal Rank Fusion (RRF)** — Merges all retrieval lists per fact type using `1/(k + rank)` scoring (`engine/search/fusion.py`).
4. **Cross-Encoder Reranking** — Neural reranker (default: `ms-marco-MiniLM-L-6-v2`) scores query-document pairs. (`engine/search/reranking.py`)
5. **Combined Scoring** — Multiplicative boosts applied to cross-encoder score:
   - Recency: linear decay over 365 days (alpha=0.2, max +/-10%)
   - Temporal proximity: for time-constrained queries (alpha=0.2)
   - Proof count: log-normalized evidence strength for observations (alpha=0.1, max +/-5%)
6. **Token Budget Filtering** — Results returned until `max_tokens` budget exhausted.

**Budget system**: Configurable thinking budget (low/mid/high) controls graph traversal depth. Supports "fixed" or "adaptive" (proportional to max_tokens).

**Backpressure**: Semaphore limits concurrent recalls (`recall_max_concurrent`, default 50).

## Lifecycle / Decay Mechanism

Hindsight does **not** implement traditional memory decay (TTL, exponential forgetting, or automatic deletion based on age). Instead, it uses several mechanisms that achieve similar effects:

1. **Recency Boost in Scoring** (`engine/search/reranking.py`, line 101-108):
   - Linear decay over 365 days: `recency = max(0.1, 1.0 - days_ago/365)`
   - Applied as multiplicative boost (max +/-10%) to cross-encoder scores.
   - Old memories are not deleted but gradually rank lower.

2. **Consolidation** (`engine/consolidation/consolidator.py`):
   - Background job runs after retain. Processes unconsolidated memories (`consolidated_at IS NULL`).
   - LLM decides to CREATE new observations, UPDATE existing ones with new evidence, or DELETE obsolete observations.
   - `proof_count` tracks supporting evidence; observations with more proof rank higher.
   - Failed consolidation marked with `consolidation_failed_at` to prevent retry loops.
   - Effectively compresses many raw facts into fewer high-quality observations over time.

3. **Document Cascade Delete**:
   - Re-ingesting a document cascade-deletes all old facts, chunks, and links (via FK `ON DELETE CASCADE`).
   - Delta retain preserves unchanged chunks but removes changed/deleted ones.

4. **No Explicit Forgetting**: There is no automatic pruning, TTL, or decay-based deletion of individual memories. All raw facts persist indefinitely unless their source document is re-ingested or explicitly deleted.

## Key Data Structures

### RetainContent (input)
```python
@dataclass
class RetainContent:
    content: str
    context: str = ""
    event_date: datetime | None = None
    metadata: dict[str, str]
    entities: list[dict[str, str]]  # User-provided entities
    tags: list[str]  # Visibility scope tags
    observation_scopes: ...  # How to scope consolidation
```
File: `engine/retain/types.py`, line 47

### ProcessedFact (intermediate)
```python
@dataclass
class ProcessedFact:
    fact_text: str
    fact_type: str  # "world", "experience", "observation"
    embedding: list[float]  # 384-dim vector
    occurred_start: datetime | None
    occurred_end: datetime | None
    mentioned_at: datetime | None
    context: str
    metadata: dict[str, str]
    entities: list[EntityRef]
    causal_relations: list[CausalRelation]
    chunk_id: str | None
    document_id: str | None
    tags: list[str]
```
File: `engine/retain/types.py`, line 132

### RetrievalResult (search output)
Contains: id, text, context, fact_type, similarity, occurred_start, temporal_score, temporal_proximity, proof_count, tags.
File: `engine/search/types.py`

### MergedCandidate (post-fusion)
Contains: retrieval (RetrievalResult), rrf_score, rrf_rank, source_ranks dict.
File: `engine/search/types.py`

### Memory Links (graph edges)
Link types: `temporal`, `semantic`, `entity`, `causes`, `caused_by`, `enables`, `prevents`
Weight: float 0.0-1.0 (semantic = cosine similarity; temporal = time decay; causal = fixed 1.0)

## Notable Design Decisions

1. **No decay/forgetting by design**: Raw facts persist forever. Ranking naturally deprioritizes old irrelevant memories through recency boost. Consolidation compresses rather than deletes.

2. **Three-phase retain transaction**: Expensive reads (entity resolution, ANN) run outside the write transaction to avoid lock contention. Only critical writes (fact inserts, links) are transactional.

3. **Streaming producer-consumer**: LLM extraction and DB writes run concurrently for large documents, with per-batch commits for crash recovery. Document ownership serialized via `FOR UPDATE` row locks.

4. **Graph retrieval via self-join, not stored entity links**: Entity-based graph expansion uses `unit_entities` self-join (COUNT DISTINCT shared entities) rather than pre-computed `memory_links` entity edges. Entity links in `memory_links` exist only for UI visualization.

5. **Reciprocal Rank Fusion over learned fusion**: RRF (k=60) merges results from 4 retrieval strategies without needing training data or learned weights.

6. **Multiplicative scoring**: Secondary signals (recency, temporal proximity, proof count) are multiplicative boosts on the cross-encoder relevance score, ensuring they modulate rather than overpower base relevance.

7. **Delta retain**: Content-hash-based chunk deduplication avoids re-extracting unchanged portions of updated documents, saving LLM costs.

8. **Multi-tenant schema isolation**: Each tenant gets its own PostgreSQL schema. Context variables + `fq_table()` ensure all queries are schema-qualified. Runtime SQL validation catches unqualified references.

9. **Observation consolidation as background job**: After retain, a consolidation job synthesizes observations from raw facts using LLM-driven create/update/delete actions. Observations track `proof_count` and `source_memory_ids` for provenance.

10. **Pluggable backends**: Supports PostgreSQL and Oracle 23ai via a `DataAccessOps` abstraction layer with dialect-specific implementations (`engine/db/ops_postgresql.py`, `engine/db/ops_oracle.py`). Vector index supports pgvector HNSW, pgvectorscale DiskANN, VectorChord, and AlloyDB ScANN.

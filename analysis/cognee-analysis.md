# Cognee Memory System Analysis

## Overview

Cognee is a knowledge-graph-based memory system for AI agents that operates on a dual-layer architecture: a **permanent graph** (long-term memory via knowledge graph + vector embeddings) and a **session cache** (short-term memory via Redis or filesystem). The primary API surface consists of three high-level functions: `remember()` (write), `recall()` (read), and `forget()` (delete), with an `improve()` function that bridges session data into the permanent graph and applies feedback-driven weight updates.

The system follows an ECL (Extract, Cognify, Load) pipeline pattern rather than traditional RAG, using LLM-powered entity/relationship extraction to build structured knowledge graphs from raw data.

## Storage Layer

Cognee uses a multi-backend pluggable storage architecture with three independent persistence tiers:

### 1. Relational Database (metadata + lifecycle)
- **Default**: SQLite; **Alternative**: PostgreSQL
- Stores: dataset records, data records, pipeline status, user permissions, session lifecycle (`SessionRecord`, `SessionModelUsage`)
- Interface: SQLAlchemy async sessions via `get_relational_engine()`
- Key models: `cognee/modules/session_lifecycle/models.py`

### 2. Graph Database (knowledge graph)
- **Default**: Ladybug; **Alternatives**: Neo4j, Neptune, PostgreSQL
- Stores: entity nodes, relationship edges, feedback weights, frequency weights
- Interface: `GraphDBInterface` (`cognee/infrastructure/databases/graph/graph_db_interface.py`)
- Supports: node CRUD, edge CRUD, neighborhood traversal, filtered subgraph queries, feedback/frequency weight get/set

### 3. Vector Database (embeddings)
- **Default**: LanceDB; **Alternatives**: ChromaDB, PGVector, Qdrant, Weaviate, Milvus
- Stores: embedded representations of DataPoints, triplet embeddings
- Interface: `VectorDBInterface` (`cognee/infrastructure/databases/vector/vector_db_interface.py`)
- Supports: semantic search, batch search, collection management, belongs_to_set filtering

### 4. Session Cache (short-term/ephemeral memory)
- **Default**: Filesystem (`FSCacheAdapter`); **Alternatives**: Redis (`RedisAdapter`), Tapes (`TapesCacheAdapter`)
- Stores: Q&A entries, agent trace steps, graph context snapshots, usage logs
- Interface: `CacheDBInterface` (`cognee/infrastructure/databases/cache/cache_db_interface.py`)
- Config: `cognee/infrastructure/databases/cache/config.py`
- Factory: `cognee/infrastructure/databases/cache/get_cache_engine.py`

## Write / Extraction Logic

### `remember()` -- Primary Write API
**File**: `cognee/api/v1/remember/remember.py` (lines 593-965)

Two modes based on `session_id`:

**Without session_id (permanent memory)**:
1. Calls `add()` -- ingests raw data into relational DB + file storage
2. Calls `cognify()` -- runs the extraction pipeline:
   - `classify_documents` -- identifies document types
   - `extract_chunks_from_documents` -- splits into `DocumentChunk` objects using `TextChunker`
   - `extract_graph_from_data` (`cognee/tasks/graph/extract_graph_from_data.py`) -- LLM-powered entity/relationship extraction via `extract_content_graph()`, produces `KnowledgeGraph` (nodes + edges)
   - `integrate_chunk_graphs` -- validates against ontology, deduplicates edges, stamps provenance
   - `add_data_points` -- persists to graph DB + vector DB
3. Optionally calls `improve()` for enrichment (triplet embeddings, indexing)

**With session_id (session memory)**:
1. Stores text as a Q&A entry in session cache via `SessionManager.add_qa()`
2. Optionally bridges to permanent graph via `improve()` in background

### Typed Memory Entries
`remember()` also accepts typed `MemoryEntry` payloads (`cognee/memory/entries.py`):
- `QAEntry` -- dispatches to `SessionManager.add_qa()`
- `TraceEntry` -- dispatches to `SessionManager.add_agent_trace_step()`
- `FeedbackEntry` -- dispatches to `SessionManager.add_feedback()`
- `SkillRunEntry` -- graph-backed skill execution records

### `@agent_memory` Decorator
**File**: `cognee/modules/agent_memory/decorator.py`

Wraps async agent functions to automatically:
1. Retrieve memory context before execution (graph search + session trace feedback)
2. Persist execution trace after completion (parameters, return value, status)
3. Optionally periodically persist traces into the permanent knowledge graph

## Read / Retrieval Logic

### `recall()` -- Primary Read API
**File**: `cognee/api/v1/recall/recall.py` (lines 314-596)

Multi-source retrieval with configurable scope (`auto`, `graph`, `session`, `trace`, `graph_context`, `all`):

**Session search** (`_search_session`, line 155): Keyword/token-overlap ranking over cached Q&A entries. Tokenizes query and entries, scores by intersection size, returns top-k.

**Trace search** (`_search_trace`, line 213): Same token-overlap approach over agent trace steps (origin_function, params, return values, feedback).

**Graph context** (`_fetch_graph_context`, line 284): Returns pre-computed graph knowledge summaries synced to the session cache by `improve()`.

**Graph search** (`_run_graph`, line 476): Full knowledge graph search via `authorized_search()` with multiple strategies defined in `SearchType` enum (`cognee/modules/search/types/SearchType.py`):
- `GRAPH_COMPLETION` -- graph traversal + LLM completion
- `GRAPH_SUMMARY_COMPLETION` -- summaries + graph context
- `TRIPLET_COMPLETION` -- triplet-based (subject-predicate-object) search
- `RAG_COMPLETION` -- traditional vector RAG
- `CHUNKS` / `CHUNKS_LEXICAL` -- raw chunk retrieval
- `TEMPORAL` -- time-aware search
- `AGENTIC_COMPLETION` -- agentic reasoning over graph

**Triplet search core** (`cognee/modules/retrieval/utils/brute_force_triplet_search.py`):
1. Vector search to find relevant node IDs
2. Project graph subgraph (optionally with k-hop neighborhood expansion)
3. Map vector distances to graph nodes/edges
4. Calculate top triplet importances, incorporating `feedback_weight` when `feedback_influence > 0`

**Auto-routing**: When no `query_type` is specified and `auto_route=True`, a rule-based query classifier (`cognee/api/v1/recall/query_router.py`) picks the best search strategy.

## Lifecycle / Decay Mechanism

### Session TTL (Time-Based Expiry)
- **Config**: `session_ttl_seconds` in `CacheConfig` (default: 604800 = 7 days)
- **Redis**: `_apply_session_ttl()` calls `EXPIRE` on session keys after each write (`RedisAdapter.py`, line 163-166)
- **Effect**: Session cache entries auto-expire after the TTL; permanent graph data is NOT affected

### Session Abandonment Detection
- **File**: `cognee/modules/session_lifecycle/metrics.py` (lines 271-292)
- **Config**: `SESSION_ABANDON_AFTER_SECONDS` env var (default: 1800 = 30 minutes)
- **Mechanism**: Computed at read time via SQL CASE expression -- if `status == "running"` AND `last_activity_at` < threshold, effective status is `"abandoned"`. No background sweeper needed.

### Feedback Weight Decay/Boost
- **File**: `cognee/memify_pipelines/apply_feedback_weights.py`
- **Mechanism**: `improve()` reads session Q&A entries with feedback scores, applies exponential moving average (`alpha` parameter, default 0.1) to `feedback_weight` on graph nodes/edges referenced in `used_graph_element_ids`
- **Effect**: High-rated answers boost their source graph elements; low-rated answers decrease them. This influences future retrieval via `feedback_influence` parameter in triplet search.
- **Default weight**: `feedback_weight = 0.5` on all DataPoints (neutral starting point)

### No Explicit Memory Decay
There is no automatic time-based decay of permanent graph memory. The `importance_weight` field exists on DataPoints (default 0.5) but is not automatically decremented over time. Memory permanence is the default; explicit deletion requires `forget()`.

## Key Data Structures

### `DataPoint` (`cognee/infrastructure/engine/models/DataPoint.py`)
Base class for all graph nodes. Key fields:
- `id: UUID` -- deterministic (UUID5 from identity fields) or random (UUID4)
- `created_at / updated_at: int` -- millisecond timestamps
- `version: int` -- incremented via `update_version()`
- `metadata: MetaData` -- declares `index_fields` (for embedding) and `identity_fields` (for deduplication)
- `belongs_to_set: list` -- dataset/node-set membership tags
- `feedback_weight: float` -- session feedback signal (default 0.5)
- `importance_weight: float` -- static importance (default 0.5)
- `source_pipeline / source_task / source_node_set / source_user / source_content_hash` -- provenance tracking

### `KnowledgeGraph` (`cognee/shared/data_models.py`)
LLM extraction target model:
- `nodes: list[Node]` -- each with id, name, type, description
- `edges: list[Edge]` -- each with source_node_id, target_node_id, relationship_name

### `SessionQAEntry` (`cognee/infrastructure/databases/cache/models.py`)
Session cache entry:
- `time: str` -- ISO timestamp
- `qa_id: str` -- unique identifier for update/delete
- `question / context / answer: str`
- `feedback_text / feedback_score` -- user feedback (1-5 scale)
- `used_graph_element_ids: dict` -- maps to graph nodes/edges used in retrieval
- `memify_metadata: dict` -- tracks which pipelines have processed this entry

### `SessionAgentTraceEntry` (`cognee/infrastructure/databases/cache/models.py`)
Agent execution trace:
- `trace_id / origin_function / status`
- `memory_query / memory_context` -- what the agent retrieved
- `method_params / method_return_value` -- function I/O
- `session_feedback: str` -- LLM-generated or deterministic summary of the step

### `SessionRecord` (`cognee/modules/session_lifecycle/models.py`)
Relational lifecycle tracking:
- `session_id + user_id` (composite PK)
- `status / started_at / last_activity_at / ended_at`
- `tokens_in / tokens_out / cost_usd / error_count`

### `MemoryEntry` Union Type (`cognee/memory/entries.py`)
Discriminated union: `QAEntry | TraceEntry | FeedbackEntry | SkillRunEntry`

## Notable Design Decisions

1. **Dual-layer architecture**: Short-term session cache (Redis/FS with TTL) vs permanent knowledge graph. This separates fast ephemeral access from durable structured memory.

2. **Feedback-driven retrieval weighting**: Graph nodes/edges carry `feedback_weight` that is updated by user feedback scores on session Q&A entries. This creates a reinforcement loop where good retrieval results get boosted.

3. **Lazy bridging via `improve()`**: Session data is not immediately written to the permanent graph. Instead, `improve()` asynchronously: (a) applies feedback weights, (b) persists Q&A text, (c) persists agent traces, (d) builds triplet embeddings, (e) syncs graph context back to sessions.

4. **No automatic memory decay**: Permanent graph memory does not decay over time. The system relies on feedback weights and explicit `forget()` rather than time-based pruning. Only session cache has TTL-based expiry.

5. **Identity-based deduplication**: DataPoints with `identity_fields` in metadata generate deterministic UUID5 IDs, enabling automatic deduplication on re-ingestion.

6. **Provenance tracking**: Every DataPoint records `source_pipeline`, `source_task`, `source_user`, and `source_content_hash`, enabling full lineage tracking from raw data to graph nodes.

7. **Multi-tenant isolation**: Each user+dataset combination can map to isolated graph/vector databases. Session cache is keyed by `(user_id, session_id)` with cross-user access via dataset read grants.

8. **Pipeline-based composability**: All processing flows through `Task` objects composed into pipelines (`cognee/modules/pipelines/`). Custom extraction or enrichment logic slots into the same framework.

9. **Auto-routing for retrieval**: The `recall()` function includes a rule-based query classifier that picks the optimal search strategy (graph traversal, RAG, lexical, temporal, etc.) when no explicit type is specified.

10. **Session-to-graph sync**: The `improve()` function incrementally copies enriched graph relationships back into session caches as human-readable summaries, creating a bidirectional flow between short-term and long-term memory.

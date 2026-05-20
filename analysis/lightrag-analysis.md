# LightRAG Memory System Analysis

## Overview

LightRAG (by HKUDS) is a graph-based Retrieval-Augmented Generation system that functions as an external memory layer for LLMs. It ingests documents, extracts a knowledge graph of entities and relationships via LLM calls, stores them across multiple backend types, and retrieves relevant context at query time using a combination of vector similarity and graph traversal. The system supports multiple query modes (local, global, hybrid, mix, naive) to balance specificity vs. breadth.

Core orchestrator: `lightrag/lightrag.py` (the `LightRAG` dataclass, line 210).
Core operations: `lightrag/operate.py` (extraction, merging, querying).

## Storage Layer

LightRAG uses **four pluggable storage abstractions** defined in `lightrag/base.py`:

| Abstraction | Base Class | Purpose | Default Impl |
|---|---|---|---|
| KV Storage | `BaseKVStorage` (line 356) | Key-value store for docs, chunks, entities, relations, LLM cache | `JsonKVStorage` (JSON files) |
| Vector Storage | `BaseVectorStorage` (line 218) | Embedding-based similarity search | `NanoVectorDBStorage` (nano-vectordb JSON) |
| Graph Storage | `BaseGraphStorage` (line 405) | Entity-relationship graph | `NetworkXStorage` (GraphML files) |
| Doc Status Storage | `DocStatusStorage` (line 810) | Document processing lifecycle tracking | `JsonDocStatusStorage` |

**Named storage instances** created in `LightRAG.__post_init__` (lines 663-737):

- `llm_response_cache` - KV: caches all LLM responses (extraction, summary, query)
- `text_chunks` - KV: stores chunked document text
- `full_docs` - KV: stores original full document content
- `full_entities` / `full_relations` - KV: per-document entity/relation indexes
- `entity_chunks` / `relation_chunks` - KV: chunk-ID tracking per entity/relation
- `entities_vdb` - Vector: entity embeddings (meta: entity_name, source_id, content, file_path)
- `relationships_vdb` - Vector: relationship embeddings (meta: src_id, tgt_id, source_id, content, file_path)
- `chunks_vdb` - Vector: text chunk embeddings
- `chunk_entity_relation_graph` - Graph: the knowledge graph itself
- `doc_status` - Doc status: tracks PENDING/PROCESSING/PROCESSED/FAILED states

**Workspace isolation**: Each instance uses a `workspace` parameter for data separation. File-based backends use subdirectories; DB backends use prefixes or columns.

**Persistence model**: In-memory backends (JSON KV, NanoVectorDB, NetworkX) batch-write to disk via `index_done_callback()`. The `_insert_done()` method (line 2339) calls this on all storages after each document completes processing.

**Available backends** (registered in `lightrag/kg/__init__.py`):
- KV: Json, Redis, PostgreSQL, MongoDB, OpenSearch
- Vector: NanoVectorDB, Milvus, PostgreSQL (pgvector), Faiss, Qdrant, MongoDB, OpenSearch
- Graph: NetworkX, Neo4j, PostgreSQL, MongoDB, Memgraph, OpenSearch
- Doc Status: Json, Redis, PostgreSQL, MongoDB, OpenSearch

## Write / Extraction Logic

The write pipeline is triggered by `ainsert()` (line 1237) and proceeds through:

### 1. Document Enqueue (`apipeline_enqueue_documents`, line 1344)
- Deduplicates content by MD5 hash (or uses user-supplied IDs)
- Stores full document in `full_docs` KV
- Creates a `DocStatus.PENDING` entry in `doc_status`
- Sanitizes text encoding

### 2. Document Processing (`apipeline_process_enqueue_documents`, line 1740)
For each pending document:

**Stage 1 - Chunking and storage** (parallel):
- Splits document into token-sized chunks (default 1200 tokens, 100 overlap) via `chunking_by_token_size` (operate.py line 101)
- Chunk IDs are MD5 hashes of content with "chunk-" prefix
- Upserts chunks into `chunks_vdb`, `text_chunks`, and updates `doc_status` to PROCESSING

**Stage 2 - Entity/Relation Extraction** (`extract_entities`, operate.py line 2883):
- Sends each chunk to LLM with a structured extraction prompt (defined in `prompt.py` line 10)
- LLM outputs entities as `entity<|#|>name<|#|>type<|#|>description` tuples
- LLM outputs relations as `relation<|#|>source<|#|>target<|#|>keywords<|#|>description` tuples
- Supports "gleaning" (re-prompting for missed entities, controlled by `entity_extract_max_gleaning`)
- Results cached in `llm_response_cache` for rebuild scenarios

**Stage 3 - Merge** (`merge_nodes_and_edges`, operate.py line 2501):
- Two-phase: entities first, then relationships
- For each entity: fetches existing graph node, merges source_ids, deduplicates descriptions by content, summarizes via LLM if description list grows large (map-reduce approach in `_handle_entity_relation_summary`, line 167)
- Entity type resolved by majority vote across extractions
- Upserts to both graph storage (node properties) and vector DB (embedding of description)
- Uses keyed locks per entity/relation for concurrency safety
- Tracks `source_id` (which chunks contributed) with configurable limits (`max_source_ids_per_entity`)

### 3. Finalization
- `_insert_done()` persists all in-memory stores to disk
- Document status updated to `PROCESSED`

## Read / Retrieval Logic

Query entry point: `aquery()` (line 2622) which delegates to `kg_query()` (operate.py line 3164) or `naive_query()` (line 4953).

### KG Query Flow (modes: local, global, hybrid, mix)

1. **Keyword Extraction** (`extract_keywords_only`, line 3406): LLM extracts high-level (thematic) and low-level (specific) keywords from the query.

2. **Context Building** (`_build_query_context`, line 4239) - 4-stage architecture:
   - **Stage 1 - Search** (`_perform_kg_search`): Vector similarity search on `entities_vdb` and/or `relationships_vdb` using extracted keywords. Retrieves top-k entities/relations.
   - **Stage 2 - Truncation** (`_apply_token_truncation`): Enforces token budgets (`max_entity_tokens`, `max_relation_tokens`, `max_total_tokens`) on retrieved context.
   - **Stage 3 - Chunk Merging** (`_merge_all_chunks`): Gathers source text chunks from entities/relations via `source_id` links. In "mix" mode, also retrieves chunks directly from `chunks_vdb`. Deduplicates and optionally reranks.
   - **Stage 4 - Context String** (`_build_context_str`): Formats entities, relations, and chunks into the LLM prompt context with reference IDs.

3. **LLM Generation**: Final context + user query sent to LLM. Response cached.

### Naive Query Flow
- Direct vector search on `chunks_vdb` (no graph traversal)
- Processes chunks with optional reranking
- Builds context and sends to LLM

### Local vs Global vs Hybrid vs Mix
- **Local**: Searches `entities_vdb` with low-level keywords, finds related edges from matched nodes
- **Global**: Searches `relationships_vdb` with high-level keywords
- **Hybrid**: Combines local + global results
- **Mix**: KG retrieval (hybrid) + direct vector chunk retrieval from `chunks_vdb`
- **Naive**: Pure vector chunk retrieval, no graph

### Caching
- Query results cached by `args_hash` (mode + query + params)
- Keyword extraction cached separately
- All caching goes through `llm_response_cache` KV store

## Lifecycle / Decay Mechanism

**LightRAG has no built-in memory decay, TTL, or eviction mechanism.** Once data is written, it persists indefinitely unless explicitly deleted.

Available lifecycle operations:

1. **Document deletion** (`adelete_by_doc_id`, line 3223): Removes a document and cascades through chunks, graph nodes/edges, and vector entries. If an entity/relation is shared across documents, it is *rebuilt* from remaining chunks using cached LLM extraction results (`rebuild_knowledge_from_chunks`, operate.py line 560) rather than deleted outright.

2. **Entity/Relation deletion** (`adelete_by_entity`, line 4134; `adelete_by_relation`, line 4164): Direct removal of specific graph elements.

3. **Full data drop**: Each storage implements `drop()` to wipe all data.

4. **Source ID limiting** (`max_source_ids_per_entity`, `max_source_ids_per_relation`): Controls how many chunk references an entity/relation retains. Strategy is configurable: `KEEP` (ignore new chunks once limit reached) or `FIFO` (drop oldest source_ids). This provides indirect staleness management but does not remove the entity itself.

There is no:
- Time-based decay or forgetting
- Access-frequency-based eviction
- Automatic consolidation/compaction of old memories
- Relevance scoring that degrades over time

## Key Data Structures

### TextChunkSchema (base.py line 74)
```python
class TextChunkSchema(TypedDict):
    tokens: int
    content: str
    full_doc_id: str
    chunk_order_index: int
```

### Entity (graph node properties)
```
entity_name: str        # Normalized identifier (title case)
entity_type: str        # Category (from configured entity_types)
description: str        # LLM-generated summary (possibly multi-part joined by GRAPH_FIELD_SEP)
source_id: str          # Pipe-separated chunk IDs that mention this entity
file_path: str          # Pipe-separated source file paths
created_at: str         # Timestamp
```

### Relationship (graph edge properties)
```
src_id: str             # Source entity name
tgt_id: str             # Target entity name
description: str        # LLM-generated relationship description
keywords: str           # Comma-separated relationship keywords
weight: float           # Relationship strength (from LLM extraction)
source_id: str          # Pipe-separated chunk IDs
file_path: str          # Pipe-separated source file paths
```

### DocProcessingStatus (base.py line 763)
```python
@dataclass
class DocProcessingStatus:
    content_summary: str       # First 100 chars preview
    content_length: int
    file_path: str
    status: DocStatus          # PENDING | PROCESSING | PREPROCESSED | PROCESSED | FAILED
    created_at: str
    updated_at: str
    track_id: str | None
    chunks_count: int | None
    chunks_list: list[str] | None
    error_msg: str | None
    metadata: dict[str, Any]
```

### QueryParam (base.py line 85)
Controls retrieval behavior: mode, top_k, token budgets, reranking, streaming, conversation history.

### NameSpace (namespace.py)
String constants defining storage namespace keys for each storage instance (e.g., `"full_docs"`, `"entities"`, `"chunk_entity_relation"`, `"doc_status"`).

### GRAPH_FIELD_SEP
The separator `<SEP>` used to join multiple values within a single graph property field (e.g., multiple source_ids or descriptions).

## Notable Design Decisions

1. **Graph + Vector dual indexing**: Every entity and relationship is stored in both a graph (for traversal/structure) and a vector DB (for semantic similarity search). This enables both structural and semantic retrieval paths.

2. **Description merging via LLM summarization**: When the same entity appears across multiple chunks, descriptions are merged using a map-reduce LLM summarization strategy (`_handle_entity_relation_summary`). This keeps entity descriptions concise as more documents reference them.

3. **Keyed locking for concurrent graph writes**: Entity/relation merging uses per-key locks (`get_storage_keyed_lock`) so multiple documents can be processed in parallel without corrupting shared entities.

4. **LLM response caching enables rebuilds**: All extraction results are cached. When a document is deleted, affected entities/relations are rebuilt from the remaining cached extractions rather than re-running the LLM -- saving cost while maintaining consistency.

5. **Source ID limiting as implicit staleness control**: The `max_source_ids_per_entity` + `FIFO`/`KEEP` strategy provides the closest thing to memory decay -- it caps how much provenance an entity retains, though the entity itself is never removed.

6. **No built-in forgetting**: The system is purely additive. Memory grows monotonically unless explicit deletion is performed. There is no temporal decay, access-based eviction, or automatic garbage collection.

7. **Chunking is the unit of attribution**: The `source_id` field on entities/relations traces back to specific text chunks (MD5-based IDs), enabling document-level deletion and provenance tracking.

8. **Pluggable everything**: Storage backends, LLM providers, embedding functions, chunking functions, and rerankers are all configurable via constructor parameters or environment variables. The default file-based backends require zero infrastructure.

9. **Pipeline-based document processing**: Insert operations use a queue-based pipeline with status tracking (PENDING -> PROCESSING -> PROCESSED/FAILED), supporting cancellation, retry of failed documents, and progress monitoring.

10. **Undirected graph semantics**: All relationships are treated as undirected (edge keys are sorted), simplifying traversal and deduplication at the cost of directionality information.

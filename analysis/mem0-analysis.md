## Overview

Mem0 is a memory layer for AI agents that extracts, stores, and retrieves factual memories from conversations. The core Python SDK lives in `mem0/mem0/`. The primary class is `Memory` (sync) / `AsyncMemory` (async) in `mem0/memory/main.py`.

The system works by:
1. Accepting conversation messages via `add()`
2. Using an LLM to extract atomic factual statements from those messages
3. Embedding and storing them in a vector store
4. Retrieving relevant memories via hybrid search (semantic + BM25 + entity boost)

Memories are scoped to a session identity (at least one of `user_id`, `agent_id`, or `run_id`).

## Storage Layer

Three storage components work together:

**1. Vector Store (primary memory store)**
- Abstract base: `mem0/vector_stores/base.py` -- defines `insert`, `search`, `update`, `delete`, `get`, `list`, `keyword_search`, `search_batch`
- Default provider: Qdrant (`mem0/vector_stores/qdrant.py`)
- 30+ provider implementations (Pinecone, Chroma, pgvector, Redis, Milvus, Faiss, MongoDB, Elasticsearch, etc.)
- Config: `mem0/vector_stores/configs.py` -- `VectorStoreConfig` Pydantic model, defaults to `"qdrant"`
- Each memory is stored as a vector (embedding) + payload (metadata dict containing `data`, `hash`, `created_at`, `updated_at`, `text_lemmatized`, session IDs, etc.)

**2. SQLite (history + message context)**
- Implementation: `mem0/memory/storage.py` -- `SQLiteManager` class
- Two tables:
  - `history`: Tracks all ADD/UPDATE/DELETE events per memory_id (audit trail)
  - `messages`: Stores last 10 messages per session scope for context in subsequent extractions
- Default path: `~/.mem0/history.db` (configurable via `MemoryConfig.history_db_path`)
- Thread-safe with explicit locking

**3. Entity Store (auxiliary vector store)**
- A second vector store collection (`{collection_name}_entities`)
- Lazily initialized on first use (`Memory.entity_store` property, line ~389)
- Stores extracted entities (proper nouns, quoted text, noun compounds) linked to memory IDs
- Used at search time to boost memories that share entities with the query

## Write / Extraction Logic

Entry point: `Memory.add()` (line 573 of `main.py`)

**Non-infer mode** (`infer=False`): Messages stored directly as raw memories without LLM processing.

**Infer mode** (default, `infer=True`) -- V3 Phased Batch Pipeline:

1. **Phase 0 -- Context gathering**: Retrieve last 10 messages for the session scope from SQLite
2. **Phase 1 -- Existing memory retrieval**: Embed the parsed messages, semantic-search top 10 existing memories to provide dedup context to the LLM
3. **Phase 2 -- LLM extraction**: Single LLM call using `ADDITIVE_EXTRACTION_PROMPT` (system) + `generate_additive_extraction_prompt()` (user). The prompt instructs the LLM to produce ADD-only operations with `linked_memory_ids` referencing existing memories. Returns JSON `{"memory": [{"id": "0", "text": "...", "linked_memory_ids": [...]}]}`
4. **Phase 3 -- Batch embed**: All extracted memory texts are embedded in one batch call
5. **Phase 4/5 -- Hash dedup**: MD5 hash of each memory text checked against existing hashes and within-batch hashes. Duplicates are skipped
6. **Phase 6 -- Batch persist**: Vectors + payloads inserted into vector store. History records batch-written to SQLite
7. **Phase 7 -- Batch entity linking**: Entities extracted via spaCy NLP (`mem0/utils/entity_extraction.py`), deduplicated globally, batch-embedded, searched against entity store (threshold 0.95), then inserted or updated
8. **Phase 8 -- Message save**: Input messages saved to SQLite for future context

**Procedural memory** (`memory_type="procedural_memory"`): Special path that uses the LLM to produce a structured execution history summary rather than atomic facts.

**Extraction prompts** (`mem0/configs/prompts.py`):
- `ADDITIVE_EXTRACTION_PROMPT`: ~900-line system prompt defining extraction rules, quality standards, dedup logic, temporal grounding, and output format
- `USER_MEMORY_EXTRACTION_PROMPT` / `AGENT_MEMORY_EXTRACTION_PROMPT`: Role-specific variants (user facts vs. agent facts)
- `DEFAULT_UPDATE_MEMORY_PROMPT`: Legacy v1 prompt for ADD/UPDATE/DELETE/NONE decisions (still present but not used in v3 pipeline)

## Read / Retrieval Logic

Entry point: `Memory.search()` (line 1126 of `main.py`)

Hybrid scoring pipeline in `_search_vector_store()` (line 1343):

1. **Query preprocessing**: Lemmatize query for BM25; extract entities via spaCy
2. **Embed query**: Generate embedding vector
3. **Semantic search**: Vector similarity search with over-fetching (`max(limit * 4, 60)`)
4. **Keyword search**: BM25/full-text search against `text_lemmatized` field (if store supports it)
5. **BM25 normalization**: Raw BM25 scores normalized to [0,1] via logistic sigmoid with query-length-adaptive parameters (`mem0/utils/scoring.py`)
6. **Entity boost computation** (`_compute_entity_boosts`, line 1440): For each entity in the query, search entity store (threshold >= 0.5), then boost linked memories. Spread-attenuation: entities linking to many memories get reduced boost
7. **Combined scoring** (`score_and_rank` in `mem0/utils/scoring.py`):
   - `combined = (semantic + bm25 + entity_boost) / max_possible`
   - `max_possible` adapts: 1.0 (semantic only), 2.0 (+BM25), 2.5 (+entity), 1.5 (semantic+entity)
   - Threshold gates semantic score before combining
8. **Optional reranking**: If `rerank=True` and a reranker is configured, results are reranked post-scoring
9. **Formatting**: Results returned as `MemoryItem` dicts with score, metadata, timestamps

Other read operations:
- `get(memory_id)`: Direct vector store lookup by ID
- `get_all(filters, top_k)`: Lists memories filtered by session IDs
- `history(memory_id)`: Returns SQLite audit trail for a memory

## Lifecycle / Decay Mechanism

**In the open-source SDK: No built-in decay/TTL/expiration mechanism exists.**

- Memories persist indefinitely once stored
- The only removal paths are explicit `delete()`, `delete_all()`, or `reset()`
- History is append-only (records ADD, UPDATE, DELETE events with `is_deleted` flag)
- Messages table auto-evicts beyond 10 per session scope (line 282 of `storage.py`)

**In the hosted platform (client-only):**
- A `decay` boolean toggle exists in project settings (`mem0/client/project.py`, line 401)
- When enabled, "search-time ranking boosts recently-used memories and gently dampens stale ones"
- This is a server-side feature -- no decay logic is implemented in the open-source codebase

## Key Data Structures

**`MemoryConfig`** (`mem0/configs/base.py`, line 29):
```python
class MemoryConfig(BaseModel):
    vector_store: VectorStoreConfig  # default: qdrant
    llm: LlmConfig                   # default: openai
    embedder: EmbedderConfig         # default: openai
    history_db_path: str             # default: ~/.mem0/history.db
    reranker: Optional[RerankerConfig]
    version: str                     # "v1.1"
    custom_instructions: Optional[str]
```

**`MemoryItem`** (`mem0/configs/base.py`, line 16):
```python
class MemoryItem(BaseModel):
    id: str
    memory: str
    hash: Optional[str]
    metadata: Optional[Dict[str, Any]]
    score: Optional[float]
    created_at: Optional[str]
    updated_at: Optional[str]
```

**Vector store payload** (per memory):
```python
{
    "data": str,              # The memory text
    "hash": str,              # MD5 of memory text (for dedup)
    "text_lemmatized": str,   # Lemmatized text for BM25
    "created_at": str,        # ISO timestamp
    "updated_at": str,        # ISO timestamp
    "user_id": str,           # Session scope
    "agent_id": str,          # Session scope
    "run_id": str,            # Session scope
    "actor_id": str,          # Who said it
    "role": str,              # user/assistant
    "attributed_to": str,     # user/assistant attribution
}
```

**Entity store payload**:
```python
{
    "data": str,                  # Entity text
    "entity_type": str,           # proper_noun, quoted, compound, noun
    "linked_memory_ids": List[str], # UUIDs of memories mentioning this entity
    "user_id": str,               # Scope filters
}
```

**SQLite history record**:
```
id, memory_id, old_memory, new_memory, event, created_at, updated_at, is_deleted, actor_id, role
```

**`MemoryType` enum** (`mem0/configs/enums.py`): `SEMANTIC`, `EPISODIC`, `PROCEDURAL`

## Notable Design Decisions

1. **ADD-only extraction (V3 pipeline)**: The current pipeline uses additive extraction -- the LLM only produces ADD operations. Deduplication is handled by hash comparison rather than asking the LLM to decide ADD/UPDATE/DELETE (the legacy `DEFAULT_UPDATE_MEMORY_PROMPT` still exists but is unused in the v3 path). This reduces LLM complexity and latency.

2. **Anti-hallucination ID mapping** (line 717-721): Existing memory UUIDs are mapped to sequential integers before being sent to the LLM, preventing the model from hallucinating IDs.

3. **Hybrid retrieval scoring**: Rather than relying on vector similarity alone, retrieval combines three signals (semantic similarity, BM25 keyword match, entity boost) with adaptive normalization. The entity boost uses spread-attenuation to prevent high-connectivity entities from dominating.

4. **Entity store as a side-index**: Entities are extracted via spaCy NLP (not LLM) and stored in a separate vector collection. This enables entity-aware retrieval without additional LLM calls at search time.

5. **Session-scoped message context**: Last 10 messages per session are stored in SQLite and fed back to the extraction LLM for context resolution (pronoun resolution, continuations). Auto-eviction keeps this bounded.

6. **No decay in OSS**: Memory decay/aging is only available on the hosted platform. The open-source version has no built-in temporal downweighting.

7. **Hash-based dedup over semantic dedup**: Deduplication uses MD5 hash of exact text rather than embedding similarity, making it fast but only catching exact duplicates (not paraphrases).

8. **Graceful degradation**: Entity linking, batch operations, and BM25 all have fallback paths -- if batching fails, operations proceed one-by-one; if spaCy or keyword search is unavailable, those signals are simply omitted from scoring.

9. **Provider abstraction**: All storage (vector, LLM, embedder, reranker) uses a factory pattern with abstract base classes, enabling swapping between 30+ vector stores and 24+ LLM providers via config.

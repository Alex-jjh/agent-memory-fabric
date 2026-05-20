# mcp-mem0 Memory System Analysis

## Overview

mcp-mem0 is a thin MCP (Model Context Protocol) server that wraps the [Mem0](https://github.com/mem0ai/mem0) library (`mem0ai>=0.1.88`) to provide persistent long-term memory to AI agents. The server itself is minimal — two Python files totaling ~230 lines — and delegates all memory logic (embedding, extraction, deduplication, conflict resolution) to the upstream Mem0 library.

The MCP server exposes three tools: `save_memory`, `get_all_memories`, and `search_memories`.

**Key files:**
- `src/main.py` — MCP server definition, tool handlers, lifecycle management
- `src/utils.py` — Mem0 client configuration and initialization

## Storage Layer

Storage is a **Supabase-hosted PostgreSQL** database used as a vector store via the `vecs` library (dependency: `vecs>=0.4.5`).

Configuration (`src/utils.py`, lines 90-97):
```python
config["vector_store"] = {
    "provider": "supabase",
    "config": {
        "connection_string": os.environ.get('DATABASE_URL', ''),
        "collection_name": "mem0_memories",
        "embedding_model_dims": 1536 if llm_provider == "openai" else 768
    }
}
```

- Collection name: `mem0_memories`
- Embedding dimensions: 1536 (OpenAI `text-embedding-3-small`) or 768 (Ollama `nomic-embed-text`)
- The actual table schema, indexing, and similarity search are managed entirely by Mem0 + `vecs` (pgvector under the hood)

There is no local/file-based storage; the system requires a running PostgreSQL instance with pgvector.

## Write / Extraction Logic

Writing is performed by the `save_memory` tool (`src/main.py`, lines 53-70):

1. The user-provided text is wrapped into a chat message format: `[{"role": "user", "content": text}]`
2. `mem0_client.add(messages, user_id=DEFAULT_USER_ID)` is called

All extraction intelligence lives inside Mem0's `add()` method which:
- Uses the configured LLM to extract discrete facts/memories from the input
- Generates embeddings for the extracted facts
- Stores embeddings in the vector store
- Handles deduplication and conflict resolution (Mem0 internal behavior)

A `CUSTOM_INSTRUCTIONS` prompt template exists in `src/utils.py` (lines 7-15) that describes desired extraction behavior (key info, context, connections, importance, source), but it is **commented out** (line 99: `# config["custom_fact_extraction_prompt"] = CUSTOM_INSTRUCTIONS`) and therefore not active.

The default user ID is hardcoded as `"user"` (`src/main.py`, line 16) — there is no multi-user or multi-tenant support.

## Read / Retrieval Logic

Two retrieval paths exist:

### 1. Semantic Search (`search_memories`, lines 96-115)
- Calls `mem0_client.search(query, user_id=DEFAULT_USER_ID, limit=limit)`
- Default limit: 3 results
- Results ranked by vector similarity (cosine distance in pgvector)
- Returns flattened memory text strings as JSON array

### 2. Full Recall (`get_all_memories`, lines 72-92)
- Calls `mem0_client.get_all(user_id=DEFAULT_USER_ID)`
- Returns all memories for the user (paginated at 50 items by Mem0 defaults)
- Results flattened to just the `"memory"` text field

Both tools handle the Mem0 response format which wraps results in `{"results": [...]}` dicts, extracting only the `"memory"` string from each entry.

## Lifecycle / Decay Mechanism

**There is no lifecycle, decay, or expiration mechanism.** Memories persist indefinitely once stored. There is no:
- TTL or expiration
- Access-count tracking or recency boosting
- Consolidation or summarization of old memories
- Deletion tool exposed via MCP

The lifespan context manager (`src/main.py`, lines 24-42) manages only the Mem0 client object's lifecycle (creation/teardown), not memory lifecycle.

## Key Data Structures

### Mem0Context (dataclass, `src/main.py` lines 20-22)
```python
@dataclass
class Mem0Context:
    mem0_client: Memory
```
Holds the initialized Mem0 `Memory` client, passed through the MCP lifespan context.

### Mem0 Config Dict (constructed in `src/utils.py`)
A nested dictionary with three top-level keys:
- `"llm"` — provider, model, temperature (0.2), max_tokens (2000)
- `"embedder"` — provider, model, embedding_dims
- `"vector_store"` — provider (supabase), connection_string, collection_name, embedding_model_dims

### Memory Records (Mem0 internal, surfaced as)
Returned from Mem0 as:
```json
{"results": [{"memory": "string content", ...metadata...}]}
```
The MCP server strips all metadata and returns only the `"memory"` text strings.

## Notable Design Decisions

1. **Single-user hardcoded**: `DEFAULT_USER_ID = "user"` means all connected agents share one memory namespace. No session isolation.

2. **No delete/update tools**: Only add and read operations are exposed. There is no way for an agent to forget or correct memories through the MCP interface.

3. **Metadata discarded**: The retrieval tools discard all Mem0 metadata (timestamps, scores, IDs) and return only raw memory text. This prevents agents from reasoning about memory age or relevance scores.

4. **Custom extraction disabled**: The thoughtful extraction prompt in `utils.py` is commented out, relying entirely on Mem0's default fact extraction behavior.

5. **LLM-in-the-loop writes**: Every `save_memory` call invokes the configured LLM (via Mem0) to extract and process facts before storage — writes are not raw text appends.

6. **Transport flexibility**: Supports both SSE (HTTP, default port 8050) and stdio transports, making it usable as a standalone service or as a subprocess spawned by an MCP client.

7. **No caching layer**: Every search/retrieval hits the database directly through Mem0 with no local cache.

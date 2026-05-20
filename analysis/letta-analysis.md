# Letta Memory System Analysis

## Overview

Letta (formerly MemGPT) implements a **three-tier memory architecture** inspired by operating system memory hierarchies:

1. **Core Memory** (in-context) -- structured text blocks injected directly into the LLM context window. The agent can read and edit these during a conversation turn.
2. **Archival Memory** -- a long-term vector store (passages with embeddings) that the agent searches via semantic similarity. Survives indefinitely.
3. **Recall Memory** (Conversation Search) -- the agent's past messages, searchable via hybrid text+semantic search.

An optional **git-backed memory layer** provides full version history for core memory blocks (used in "sleeptime" and git-enabled agents).

---

## Storage Layer

### Core Memory (Blocks)

| Component | Location |
|-----------|----------|
| Pydantic schema | `letta/schemas/block.py` (class `Block`, line 67) |
| ORM model | `letta/orm/block.py` (class `Block`, line 20) |
| Block history (undo/redo) | `letta/orm/block_history.py` (class `BlockHistory`, line 12) |
| Manager | `letta/services/block_manager.py` (class `BlockManager`, line 53) |
| Git-enabled manager | `letta/services/block_manager_git.py` (class `GitEnabledBlockManager`, line 30) |

**Persistence**: PostgreSQL (primary), with SQLite as alternative. Blocks are stored in the `block` table with a composite unique constraint on `(id, label)`. A `BlocksAgents` pivot table links blocks to agents.

**Version tracking**: Each block row carries an integer `version` column (optimistic locking) and a `current_history_entry_id` FK into `block_history`. Every state change appends a snapshot to `BlockHistory` with a monotonically increasing `sequence_number` per block.

### Git-Backed Memory (Optional)

| Component | Location |
|-----------|----------|
| Storage backend (abstract) | `letta/services/memory_repo/storage/base.py` |
| Local FS backend | `letta/services/memory_repo/storage/local.py` |
| Git operations | `letta/services/memory_repo/git_operations.py` |
| MemFS client | `letta/services/memory_repo/memfs_client_base.py` |
| Block <-> Markdown | `letta/services/memory_repo/block_markdown.py` |

Blocks are serialized as Markdown with YAML frontmatter (description, read_only, metadata). Files live under `~/.letta/memfs/` (local) or GCS/S3 (cloud). Commits are real git commits, enabling diff/revert/branch workflows. PostgreSQL acts as a read-through cache.

### Archival Memory (Passages)

| Component | Location |
|-----------|----------|
| Pydantic schema | `letta/schemas/passage.py` (class `Passage`, line 35) |
| ORM model | `letta/orm/passage.py` (classes `ArchivalPassage`, `SourcePassage`) |
| Manager | `letta/services/passage_manager.py` (class `PassageManager`, line 43) |

**Persistence**: Passages stored in `archival_passages` table (for agent-created memories) or `source_passages` table (for file-derived passages). Embeddings are stored as `pgvector` vectors of up to 4096 dimensions (constant `MAX_EMBEDDING_DIM`, `letta/constants.py:93`). Tags are stored both in a JSON column (fast retrieval) and a `passage_tag` junction table (efficient filtering).

Optional dual-write to external vector stores: **Turbopuffer** and **Pinecone**.

### Recall Memory (Messages)

| Component | Location |
|-----------|----------|
| Manager | `letta/services/message_manager.py` |
| Search | `MessageManager.search_messages_async` (line 1142) |

Messages are stored in the primary database and searchable via hybrid (FTS + vector) or timestamp-based modes.

---

## Write / Extraction Logic

### Core Memory Writes

The agent modifies core memory through tool calls processed by `LettaCoreToolExecutor` (`letta/services/tool_executor/core_tool_executor.py`). Available operations (line 41-55):

- **`core_memory_append`** -- appends text with a newline separator (line 319-326)
- **`core_memory_replace`** -- exact string match and replace (line 328-344)
- **`memory_replace`** -- v2 replacement with uniqueness validation (line 346-401)
- **`memory_insert`** -- inserts text at a specific line number (function at `letta/functions/function_sets/base.py:391`)
- **`memory_rethink`** -- wholesale block rewrite for reorganization (line 488-517 of base.py)
- **`memory_apply_patch`** -- unified-diff patch for multi-block edits (line 403+)
- **`memory`** -- omnibus tool with subcommands: create, str_replace, insert, delete, rename (base.py line 10-68)

All writes route through `agent_state.memory.update_block_value()` -> `AgentManager.update_memory_if_changed_async()` which persists to the DB and triggers system prompt rebuild.

For git-enabled agents, `GitEnabledBlockManager.update_block_async` (line 188) writes to git first (source of truth), then syncs to PostgreSQL (cache).

### Archival Memory Writes

`archival_memory_insert` (core_tool_executor.py line 307-317) -> `PassageManager.insert_passage` (passage_manager.py line 543):
1. Text is embedded via the configured embedding model
2. Passage is inserted into `archival_passages` table
3. Optionally dual-written to Turbopuffer/Pinecone
4. Tags are stored in both JSON column and junction table

### Sleeptime / Background Memory

In "sleeptime" multi-agent mode (`letta/groups/sleeptime_multi_agent.py`), a background agent asynchronously processes conversation transcripts to update core memory blocks, using the `memory_replace`, `memory_insert`, `memory_rethink`, and `memory_finish_edits` tools. This runs in a separate thread so the main agent can continue responding.

---

## Read / Retrieval Logic

### Core Memory (In-Context)

Core memory is rendered into the system prompt via `Memory.compile()` (`letta/schemas/memory.py:688`). Three rendering modes:

1. **Standard** (`_render_memory_blocks_standard`, line 143) -- XML blocks with metadata
2. **Line-numbered** (`_render_memory_blocks_line_numbered`, line 175) -- adds line number prefixes for Anthropic models
3. **Git-backed** (`_render_memory_blocks_git`, line 205) -- structured `<self>` + `<memory>` tree rendering

Only `system/*` blocks are rendered for git-enabled agents; blocks under `skills/` are rendered separately as `<available_skills>`.

### Archival Memory Retrieval

`archival_memory_search` tool -> `AgentManager.search_agent_archival_memory_async` (agent_manager.py line 2534):
- Semantic search via embedding similarity
- Optional tag filtering (any/all match modes)
- Optional temporal filtering (start/end datetime)
- Default `top_k = 10` results

### Conversation (Recall) Search

`conversation_search` tool -> `MessageManager.search_messages_async` (message_manager.py line 1142):
- Hybrid search (text + semantic similarity) by default
- Filterable by role, date range
- Default page size of 5 results (`RETRIEVAL_QUERY_DEFAULT_PAGE_SIZE`, constants.py line 458)
- Results include RRF (Reciprocal Rank Fusion) scoring metadata

---

## Lifecycle / Decay Mechanism

**Letta does not implement automatic memory decay or TTL-based expiration.** Memories persist indefinitely once written.

The lifecycle mechanisms that exist:

1. **Conversation summarization** (`letta/services/summarizer/summarizer.py`):
   - `STATIC_MESSAGE_BUFFER` mode: hard-trims messages beyond buffer limit
   - `PARTIAL_EVICT_MESSAGE_BUFFER` mode: evicts ~30% of oldest in-context messages and replaces them with a recursive LLM-generated summary (injected as a user message at index 1)
   - Triggered when context window exceeds `SUMMARIZATION_TRIGGER_MULTIPLIER` (0.9) of max

2. **Soft deletion**: Passages have an `is_deleted` flag (passage_manager.py) but no automated garbage collection

3. **Block overwrite**: `memory_rethink` allows the agent (or sleeptime agent) to condense/reorganize blocks, effectively consolidating stale information

4. **Version history**: `BlockHistory` preserves prior states, enabling undo but not automatic pruning

---

## Key Data Structures

### `Block` (letta/schemas/block.py:67)
```python
class Block(BaseBlock):
    id: str
    value: str              # The actual memory content (text)
    limit: int              # Character limit (default 100,000)
    label: str              # Section identifier ("persona", "human", etc.)
    description: str        # Context for the LLM about this block's purpose
    read_only: bool         # If true, agent cannot modify
    metadata: dict          # Arbitrary metadata
    tags: List[str]         # Organizational tags
```

### `Memory` (letta/schemas/memory.py:68)
```python
class Memory(BaseModel):
    blocks: List[Block]         # In-context memory blocks
    file_blocks: List[FileBlock]  # File-derived blocks (from attached sources)
    agent_type: AgentType       # Controls rendering strategy
    git_enabled: bool           # Whether git-backed memory is active
```

### `Passage` (letta/schemas/passage.py:35)
```python
class Passage(PassageBase):
    id: str
    text: str                       # Content of the archival memory
    embedding: List[float]          # Vector embedding (up to 4096 dims)
    embedding_config: EmbeddingConfig
    archive_id: str                 # Links to agent's archive
    tags: List[str]                 # Searchable tags
    is_deleted: bool                # Soft-delete flag
    created_at: datetime
```

### `MemoryCommit` (letta/schemas/memory_repo.py:19)
```python
class MemoryCommit(LettaBase):
    sha: str                    # Git commit SHA
    parent_sha: str
    message: str
    author_type: str            # "agent", "user", or "system"
    author_id: str
    timestamp: datetime
    files_changed: List[str]
    additions: int
    deletions: int
```

---

## Notable Design Decisions

1. **Core memory is plain text, not structured data.** Blocks store free-form strings that the LLM reads/writes via tool calls. This maximizes flexibility but relies on the LLM's ability to maintain organization.

2. **Dual-write for archival memory.** Passages go to both SQL (pgvector) and optionally external vector DBs (Turbopuffer/Pinecone), providing resilience and vendor flexibility.

3. **Git as source of truth (optional).** The `GitEnabledBlockManager` pattern treats PostgreSQL as a cache and git (local or GCS) as the authoritative store. This enables branching, diffing, and auditing memory changes with full commit history.

4. **Sleeptime architecture decouples memory extraction from conversation.** A background "sleeptime agent" processes conversation asynchronously, so the main agent never blocks on memory updates. This is key to Letta's ability to handle long conversations without degrading response latency.

5. **Character limit, not token limit, for blocks.** Core memory uses a 100,000-character limit (`CORE_MEMORY_BLOCK_CHAR_LIMIT`), which is a simpler constraint than token counting.

6. **No automatic memory decay.** Unlike biological memory, all stored information persists unless the agent (or a sleeptime agent) explicitly overwrites it. Summarization only affects the in-context message window, not archival or core memory.

7. **Blocks are shared across agents via pivot table.** The `BlocksAgents` table allows multiple agents to share and co-edit the same memory block, enabling multi-agent memory coordination.

8. **Markdown with YAML frontmatter for git-stored blocks.** This format (`block_markdown.py`) is human-readable and editable outside the system while preserving metadata (description, read_only flags).

9. **Optimistic locking on blocks.** The ORM block model uses a `version` column for concurrent write safety, avoiding lost updates in multi-agent scenarios.

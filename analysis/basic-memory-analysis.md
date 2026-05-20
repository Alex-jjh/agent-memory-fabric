# Memory System Analysis: basic-memory

## Overview

basic-memory is a local-first knowledge management system built on the Model Context Protocol (MCP). It stores knowledge as plain Markdown files on disk, treating them as the source of truth, with a database (SQLite or Postgres) serving as a derived index. The system implements a knowledge graph where entities (notes) contain typed observations (facts) and relations (directed links to other entities). AI agents interact via MCP tools (`write_note`, `read_note`, `search_notes`, `build_context`) that route through a REST API to service and repository layers.

The architecture is: **MCP Tool -> Typed Client -> HTTP API (FastAPI) -> Service Layer -> Repository Layer -> Database + Filesystem**.

## Storage Layer

**Dual storage model:**

1. **Filesystem (source of truth):** Markdown files with YAML frontmatter stored in project directories. Each file is an entity with observations and relations encoded in markdown syntax.

2. **Database (derived index):** SQLite (default, with FTS5 + sqlite-vec) or PostgreSQL (with tsvector/GIN + pgvector). Managed via SQLAlchemy 2.0 async ORM with Alembic migrations.

**Database configuration** (`src/basic_memory/db.py`):
- SQLite: WAL mode, 64MB cache, 10s busy timeout, `aiosqlite` async driver
- Postgres: NullPool (assumes external pooler like PgBouncer), `asyncpg` driver, 30s timeouts

**Key tables** (defined in `src/basic_memory/models/knowledge.py`):
- `entity` - Core note records (lines 28-149)
- `observation` - Atomic facts about entities (lines 220-262)
- `relation` - Directed links between entities (lines 265-311)
- `note_content` - Materialized markdown content with sync state (lines 152-217)
- `search_index` - FTS5 virtual table (SQLite) or tsvector-indexed table (Postgres) (defined in `src/basic_memory/models/search.py`)
- `search_vector_chunks` - Semantic embedding chunks for vector search
- `project` - Multi-project isolation

**File storage** handled by `FileService` (`src/basic_memory/services/file_service.py`), with checksums for change detection.

## Write / Extraction Logic

**Entry point:** `write_note` MCP tool (`src/basic_memory/mcp/tools/write_note.py`)

**Write flow:**
1. MCP tool validates input (path traversal checks, tag parsing, metadata merging)
2. Constructs an `Entity` schema and calls `KnowledgeClient.create_entity()` (optimistic create, falls back to update on 409 conflict)
3. Routes through the FastAPI knowledge router to `EntityService`

**EntityService** (`src/basic_memory/services/entity_service.py`):
1. `prepare_create_entity_content()` (line 434): Resolves frontmatter overrides, generates permalink, builds final markdown via `schema_to_markdown()`
2. `create_entity_with_content()` (line 676): Writes file to disk, then upserts DB entity
3. `upsert_entity_from_markdown()` (line 975): Creates/updates the entity row, replaces observations, resolves and recreates relations

**Markdown extraction** (`src/basic_memory/markdown/entity_parser.py`):
- Uses `markdown-it` with custom plugins (`observation_plugin`, `relation_plugin` in `src/basic_memory/markdown/plugins.py`)
- **Observations** parsed from: `- [category] content #tag (context)` (line 34 of plugins.py)
- **Explicit relations** parsed from: `- relation_type [[Target]] (context)` (line 110 of plugins.py)
- **Inline relations** extracted from any `[[wikilink]]` in prose as `links_to` type (line 152 of plugins.py)

**Search indexing** happens inline after write:
- `SearchService.index_entity_data()` (line 493 of `search_service.py`): Deletes old index rows, re-indexes entity + all observations + outgoing relations
- Generates text variants (lowercase, path segments, word boundaries) for better fuzzy matching
- Optionally triggers vector embedding sync for semantic search

## Read / Retrieval Logic

**Three primary read mechanisms:**

### 1. Direct Read (`read_note` tool, `src/basic_memory/mcp/tools/read_note.py`)
Multi-strategy resolution (line 280):
1. Resolve identifier to entity ID via `KnowledgeClient.resolve_entity()` (permalink/file_path lookup)
2. Fallback: title search (exact case-insensitive match)
3. Fallback: full-text search, returns related results as suggestions

### 2. Search (`search_notes` tool, `src/basic_memory/mcp/tools/search.py`)
Supports multiple retrieval modes (`SearchRetrievalMode` enum):
- **FTS** - SQLite FTS5 or Postgres tsvector full-text search with boolean operators (AND/OR/NOT)
- **Vector** - Semantic embedding similarity search
- **Hybrid** - Combined FTS + vector with score merging

Additional search modes: title-only, exact permalink, permalink glob pattern matching.

Filters: `note_types`, `entity_types`, `after_date`, `metadata_filters` (JSON field queries), `tags`, `status`.

Relaxed FTS fallback (line 300 of `search_service.py`): If strict implicit-AND returns zero results for 3+ token queries, retries with OR-joined terms after removing stopwords.

### 3. Context Building (`build_context` tool, `src/basic_memory/mcp/tools/build_context.py`)
`ContextService` (`src/basic_memory/services/context_service.py`):
1. Resolves `memory://` URI to permalink(s) via pattern matching or direct lookup
2. Finds primary entities from search index
3. Traverses relations to configurable depth (1-3 hops)
4. Loads observations for all discovered entities
5. Returns hierarchical `ContextResult` with primary items, their observations, and related entities

## Lifecycle / Decay Mechanism

**basic-memory has no built-in memory decay, TTL, or automatic pruning.** All memories persist indefinitely unless explicitly deleted by the user.

**What exists for lifecycle management:**

1. **File sync** (`src/basic_memory/sync/sync_service.py`): A bidirectional sync between filesystem and database. Detects new/modified/deleted files and updates the index accordingly. Uses checksum comparison and mtime/size for change detection.

2. **Watch service** (`src/basic_memory/sync/watch_service.py`): Real-time filesystem watcher (via `watchfiles`) that triggers sync on file changes.

3. **Circuit breaker for sync failures** (line 53 of `sync_service.py`): Files that fail to sync 3+ consecutive times are temporarily skipped (until the file content changes).

4. **Explicit deletion:** `delete_note` tool and `delete_entity()` service method cascade-delete observations, relations, and search index entries.

5. **Stale row purging** (`_purge_stale_search_rows()`, line 692 of `search_service.py`): Removes orphaned search index entries for entities that no longer exist.

6. **Vector reindexing** with optional `force_full` mode that clears and regenerates all embeddings.

## Key Data Structures

### ORM Models (`src/basic_memory/models/knowledge.py`)

```
Entity
  id: int (PK)
  external_id: str (UUID, stable API identifier)
  title: str
  note_type: str
  permalink: str (unique per project, nullable)
  file_path: str (unique per project)
  checksum: str (file content hash)
  entity_metadata: JSON (tags, custom frontmatter)
  project_id: int (FK)
  created_at / updated_at: datetime

Observation
  id: int (PK)
  entity_id: int (FK -> Entity)
  content: str
  category: str (default "note")
  context: str (optional)
  tags: JSON list

Relation
  id: int (PK)
  from_id: int (FK -> Entity)
  to_id: int (FK -> Entity, nullable for forward references)
  to_name: str
  relation_type: str
  context: str (optional)
```

### Markdown Parse Result (`src/basic_memory/markdown/schemas.py`)

```
EntityMarkdown
  frontmatter: EntityFrontmatter (metadata dict with title, type, permalink, tags)
  content: str (markdown body)
  observations: List[Observation] (category, content, tags, context)
  relations: List[Relation] (type, target, context)
  created / modified: datetime
```

### Search Index Row (`src/basic_memory/repository/search_index_row.py`)

A denormalized row representing an entity, observation, or relation in the search index. Contains `id`, `type`, `title`, `content_stems`, `content_snippet`, `permalink`, `file_path`, `metadata` (JSON), timestamps, and `project_id`.

### Search Query (`src/basic_memory/schemas/search.py`)

```
SearchQuery
  permalink / permalink_match / text / title  (primary mode, use one)
  note_types / entity_types / after_date / metadata_filters / tags / status  (filters)
  retrieval_mode: FTS | VECTOR | HYBRID
  min_similarity: float (optional)
```

## Notable Design Decisions

1. **Files as source of truth:** The database is always derivable from the filesystem. This means knowledge survives independently of any AI session or database state. The sync layer rebuilds the index from files.

2. **Forward references:** Relations can target entities that don't exist yet (`to_id = NULL`, `to_name` stores the target). They are resolved when the target entity is created or during background relation resolution.

3. **Permalink stability:** Entities get a permalink that persists even if the file moves (unless configured otherwise via `update_permalinks_on_move`). This provides stable `memory://` URLs for AI conversation continuity.

4. **No memory decay by design:** All memories are permanent. The philosophy is "files are files" - the user manages their own knowledge lifecycle, just as they would with any notes system.

5. **Dual-backend search:** SQLite uses FTS5 virtual tables with custom tokenization; Postgres uses generated `tsvector` columns with GIN indexes. The `SearchRepository` protocol abstracts this.

6. **Semantic search as optional layer:** Vector embeddings (via FastEmbed or OpenAI) are opt-in, stored in `search_vector_chunks`. Entities can individually opt out via `embed: false` in metadata.

7. **Observation/Relation extraction via markdown-it plugins:** Custom parser plugins detect structured patterns (`[category] content`, `relation_type [[Target]]`) anywhere in the document body, not just under specific headings.

8. **Multi-project isolation:** All data is scoped by `project_id`. Projects can independently route to local or cloud backends.

9. **Optimistic create with conflict handling:** `write_note` attempts creation first, falling back to update on 409 conflict, with a configurable `overwrite` flag to prevent accidental overwrites.

10. **Relaxed FTS fallback:** When strict AND search returns no results for natural-language queries (3+ tokens, no explicit boolean operators), the system retries with OR-joined terms after removing stopwords - balancing precision with recall.

## Overview

CortexGraph is a graph-based short-term memory (STM) system for AI agents, exposed as an MCP (Model Context Protocol) server. It models episodic memories as nodes with typed directed relations forming a knowledge graph. The system implements biologically-inspired decay, spaced repetition, and automatic promotion of high-value memories to long-term storage (Obsidian vault markdown files).

Core architecture:
- **MCP server** (`src/cortexgraph/server.py`) registers tools via FastMCP decorators
- **Storage layer** with two backends: JSONL (default, human-readable) and SQLite
- **Decay engine** with three configurable models (power-law, exponential, two-component)
- **Preprocessing pipeline** for automatic entity extraction and importance scoring on write
- **Lifecycle management** via garbage collection, promotion, and consolidation

## Storage Layer

Two interchangeable backends share the same logical interface:

### JSONL Storage (`src/cortexgraph/storage/jsonl_storage.py`)
- **Primary format**: append-only `memories.jsonl` and `relations.jsonl` files
- **In-memory index**: all records loaded into `dict[str, Memory]` on connect (line 112-152)
- **Deletions**: append `{"id": ..., "_deleted": true}` markers; actual removal via compaction
- **Tag index**: secondary `dict[str, set[str]]` for fast tag-based filtering (line 155-186)
- **Compaction**: rewrites JSONL files removing stale entries and deletion markers (line 774-837)
- **File security**: `secure_file()` called on creation to restrict permissions

### SQLite Storage (`src/cortexgraph/storage/sqlite_storage.py`)
- Database file: `cortexgraph.db` in storage directory
- Schema: `memories` table (16 columns) + `relations` table with FK constraints + 5 indexes (lines 87-136)
- Embeddings stored as JSON text in BLOB column
- `VACUUM` for compaction

### Long-Term Memory Index (`src/cortexgraph/storage/ltm_index.py`)
- Indexes an Obsidian vault's markdown files into a JSONL index (`.cortexgraph-index.jsonl`)
- Extracts frontmatter, wikilinks, and hashtags for search
- Incremental updates based on file mtime

### Storage path resolution
Default: `~/.config/cortexgraph/jsonl/` (XDG-compliant), configurable via `CORTEXGRAPH_STORAGE_PATH`.

## Write / Extraction Logic

### Memory Creation (`src/cortexgraph/tools/save.py`)

The `save_memory` MCP tool (line 69-197):
1. **Input validation** - content max 50K chars, tags max 50, entities max 100
2. **Auto-enrichment** (when `enable_preprocessing=True`):
   - `PhraseDetector` identifies importance markers in content
   - `EntityExtractor` (`src/cortexgraph/preprocessing/entity_extractor.py`) uses spaCy NER + regex patterns for tech terms; falls back to proper-noun/URL regex if spaCy unavailable
   - `ImportanceScorer` (`src/cortexgraph/preprocessing/importance_scorer.py`) calculates strength (1.0-2.0) from weighted signals: content length (0.2), entity density (0.3), importance markers (0.4), question presence (0.1)
3. **Secrets detection** - warns on API keys, tokens (does not block save)
4. **Embedding generation** - optional sentence-transformers (`all-MiniLM-L6-v2`) encoding
5. **Persist** - UUID generated, Memory object saved to storage backend

### Relation Creation (`src/cortexgraph/tools/create_relation.py`)
- Directed edges with type (`references`, `similar_to`, `follows_from`, etc.) and strength (0-1)
- FK validation ensures both memories exist before creating relation

## Read / Retrieval Logic

### Search (`src/cortexgraph/tools/search.py`)

The `search_memory` tool (line 62-265):
1. **Filter phase**: status, tags, time window (via storage backend)
2. **Scoring phase**: for each candidate memory:
   - Compute temporal decay score via `calculate_score()`
   - Apply `min_score` threshold
   - Compute relevance: cosine similarity (if embeddings) or Jaccard text similarity fallback
   - Final score = decay_score * relevance_multiplier
3. **Spaced repetition blending**: if `include_review_candidates=True`, memories in the "danger zone" (score 0.15-0.35) are blended into results at configurable ratio (default 30%)
4. **Pagination** support via page/page_size parameters
5. **Content truncation**: preview_length parameter (default 300 chars)

### Auto-Recall (`src/cortexgraph/core/auto_recall.py`)

Background conversational reinforcement:
- `ConversationAnalyzer` extracts topics via regex patterns (proper nouns, acronyms, hyphenated terms)
- `AutoRecallEngine.process_message()` triggers if message has 2+ topics and is not purely a question
- Rate-limited (default 300s cooldown between triggers)
- Phase 1 (current): silent reinforcement only - updates `last_used`/`use_count` without surfacing

### Graph Traversal (`src/cortexgraph/tools/read_graph.py`)
- Returns full `KnowledgeGraph` (memories + relations + statistics)
- Visualization model: `GraphNode` (opacity = decay score, size = use_count) + `GraphEdge`

## Lifecycle / Decay Mechanism

### Decay Models (`src/cortexgraph/core/decay.py`)

Three configurable models (selected via `CORTEXGRAPH_DECAY_MODEL`):

| Model | Formula | Default half-life |
|-------|---------|-------------------|
| **power_law** (default) | `(1 + dt/t0)^(-alpha)` | 3 days (alpha=1.1) |
| **exponential** | `exp(-lambda * dt)` | 3 days (lambda=2.673e-6) |
| **two_component** | `w*exp(-lf*dt) + (1-w)*exp(-ls*dt)` | fast: 12h, slow: 7d (w=0.7) |

Score formula (line 26-78):
```
score = (use_count + 1)^beta * decay_component * strength
```
- `beta` (default 0.6): sublinear use-count scaling
- `strength` (1.0-2.0): importance multiplier set at write time

### Garbage Collection (`src/cortexgraph/tools/gc.py`)
- Iterates active memories, calls `should_forget()` (score < `forget_threshold` = 0.05)
- Supports `dry_run`, `archive_instead` (changes status to ARCHIVED vs. delete), and `limit`

### Promotion (`src/cortexgraph/tools/promote.py`, `src/cortexgraph/core/scoring.py`)
- Criteria: score >= 0.65 **OR** use_count >= 5 within 14 days
- Target: Obsidian vault markdown files with frontmatter
- Updates STM record status to `PROMOTED` with vault path reference
- Incrementally updates LTM index

### Consolidation (`src/cortexgraph/core/consolidation.py`)
- Merges high-cohesion clusters (>= 0.9 cohesion -> auto-merge)
- Smart content merge: keeps longest if near-duplicate, joins with separator if distinct
- Creates `consolidated_from` relations; archives originals
- Merged strength = max(strengths) + bonus (cohesion * count * 0.1, capped at 0.5)

### Reinforcement (`src/cortexgraph/tools/touch.py`, `src/cortexgraph/core/review.py`)
- `touch_memory`: increments use_count, resets last_used, optionally boosts strength (+0.1)
- `reinforce_memory`: called by auto-recall; additionally tracks cross-domain usage (+0.05 strength per cross-domain hit)
- Cross-domain detection: Jaccard similarity < 0.3 between memory tags and current context tags

### Natural Spaced Repetition (`src/cortexgraph/core/review.py`)
- "Danger zone" concept: memories with score 0.15-0.35 are candidates for review
- Priority follows inverted parabola peaking at midpoint (score ~0.25)
- Review candidates blended into search results (default 30% of result slots)
- Pattern: 2 primary results, then 1 review candidate, interleaved

## Key Data Structures

### Memory (`src/cortexgraph/storage/models.py`, line 27-133)
```python
class Memory(BaseModel):
    id: str                          # UUID
    content: str                     # Free-text content
    meta: MemoryMetadata             # tags, source, context, extra
    created_at: int                  # Unix epoch seconds
    last_used: int                   # Unix epoch seconds (drives decay)
    use_count: int                   # Access frequency
    strength: float                  # 1.0-2.0, importance multiplier
    status: MemoryStatus             # active | promoted | archived
    promoted_at: int | None
    promoted_to: str | None          # Vault path
    embed: list[float] | None       # Sentence embedding vector
    entities: list[str]             # Extracted named entities
    review_priority: float           # 0.0-1.0 spaced repetition priority
    last_review_at: int | None
    review_count: int
    cross_domain_count: int
```

### Relation (`src/cortexgraph/storage/models.py`, line 211-262)
```python
class Relation(BaseModel):
    id: str
    from_memory_id: str              # Source node
    to_memory_id: str                # Target node
    relation_type: str               # e.g. "references", "similar_to", "consolidated_from"
    strength: float                  # 0.0-1.0
    created_at: int
    metadata: dict[str, Any]
```

### Cluster (`src/cortexgraph/storage/models.py`, line 178-189)
- Groups of similar memories with cohesion score and suggested action (auto-merge/llm-review/keep-separate)

### KnowledgeGraph (`src/cortexgraph/storage/models.py`, line 265-270)
- Container for all memories + relations + aggregate statistics

## Notable Design Decisions

1. **Append-only JSONL as default backend** - prioritizes human readability and git-friendliness over performance; in-memory index means all data must fit in RAM.

2. **Three-tier decay model selection** - power-law (default) provides heavier tails than exponential, meaning old-but-frequently-used memories persist longer. Two-component models fast initial forgetting with slow residual retention.

3. **Strength as write-time importance** (1.0-2.0) - multiplicative on decay score, so high-importance memories decay on the same curve but start higher. Auto-calculated via preprocessing signals.

4. **Natural spaced repetition over explicit quizzing** - memories are not surfaced via flashcards; instead, those in the "danger zone" are blended into search results when contextually relevant, creating organic reinforcement.

5. **Dual STM/LTM architecture** - STM is the active working memory (JSONL/SQLite). Promotion moves memories to Obsidian vault markdown (LTM) with a lightweight JSONL index for search. This separates volatile working memory from persistent knowledge.

6. **Silent auto-recall** - conversation messages are analyzed in background; related memories get `last_used` updated to prevent decay without interrupting the user. This is the "use it or lose it" mechanism operating automatically.

7. **Consolidation preserves provenance** - merged memories create `consolidated_from` relations back to originals (which are deleted), maintaining audit trail in the graph structure.

8. **Embedding-optional design** - all retrieval paths have text-similarity (Jaccard) fallbacks, so the system works without `sentence-transformers` installed, just with degraded semantic matching.

9. **MCP tool interface** - exposed as an MCP server, meaning any MCP-compatible AI agent can use memory tools directly (save, search, touch, promote, gc, etc.) without custom integration code.

10. **Score = usage^beta * decay * strength** - single scalar combining recency, frequency, and importance. All lifecycle decisions (forget, promote, review) reduce to threshold checks on this score.

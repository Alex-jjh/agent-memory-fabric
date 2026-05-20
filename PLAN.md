# Implementation Plan: AMF Phase 1 + Phase 2

## Context

Agent Memory Fabric has a functional skeleton (`src/agent_memory_fabric/`) with lifecycle/decay already working (14 tests pass). The storage layer, write path, and retrieval are all stubs raising `NotImplementedError`. This plan implements Phase 1 (storage foundation) and Phase 2 (write + basic retrieval) to make the system end-to-end functional.

Key constraints:
- Markdown files = source of truth (Obsidian-compatible)
- SQLite sidecar = derived index (FTS5 + metadata + graph edges)
- No cloud dependencies for core (local-first)
- MIT license — can copy from GAAMA, HippoRAG, Hindsight, LightRAG, GraphRAG, mcp-mem0; adapt from Mem0, MemoryOS, Cognee, Letta (Apache 2.0); clean-room from CortexGraph, basic-memory (AGPL)

---

## Phase 1: Storage Foundation

### 1.1 `storage/markdown.py` — Markdown Read/Write

**Priority**: 1 (everything depends on this)  
**Complexity**: M  
**Dependencies**: `core/node.py` (done)  

**Implementation**:
- `_serialize(node) -> str`: YAML frontmatter (all MemoryNode fields except content) + `---\n` + content body
- `_deserialize(text, file_path) -> MemoryNode`: Split on `---`, parse YAML, reconstruct MemoryNode
- `write(node) -> Path`: mkdir -p + atomic write (temp file + os.replace)
- `read(node_id) -> MemoryNode`: Scan vault for file with matching `id` in frontmatter (cache ID→path mapping)
- `delete(node_id) -> bool`: Find file by ID → remove
- `list_all(scope?) -> list[MemoryNode]`: Walk directory tree, parse all `.md` files with frontmatter

**Code reuse**: Write fresh. Frontmatter parsing is trivial with `pyyaml`. Pattern inspired by basic-memory (AGPL — design only, no code).

**New dependency**: `pyyaml>=6.0` (move from `[full]` to core deps)

**Tests** (`tests/unit/test_markdown_store.py`):
- Round-trip: write → read → assert equal
- list_all with multiple scopes (global, project)
- Atomic write safety (no partial writes)
- Wikilink extraction from content

---

### 1.2 `storage/sqlite_store.py` — SQLite Sidecar

**Priority**: 2  
**Complexity**: M  
**Dependencies**: `core/node.py`, `storage/markdown.py`  

**Implementation**:
- `initialize()`: CREATE TABLE nodes, edges; CREATE VIRTUAL TABLE fts_index USING fts5
- `upsert_node(node)`: INSERT OR REPLACE into nodes + sync FTS content
- `delete_node(node_id)`: DELETE from nodes + edges + FTS
- `search_fts(query, limit) -> list[str]`: FTS5 MATCH + bm25() ranking
- `add_edge(source, target, type, weight)`: INSERT OR REPLACE edges
- `get_neighbors(node_id, edge_type?) -> list[str]`: SELECT from edges
- `reconcile(filesystem_nodes)`: Diff DB vs file list, sync (filesystem wins)
- `get_all_nodes(state?, project?) -> list[dict]`: Filtered metadata query

**Schema**:
```sql
CREATE TABLE nodes (
    id TEXT PRIMARY KEY, name TEXT, state TEXT, type TEXT,
    project TEXT, created TEXT, modified TEXT, last_accessed TEXT,
    access_count INTEGER, decay_score REAL, strength REAL,
    ttl TEXT, tags TEXT, file_path TEXT UNIQUE
);
CREATE TABLE edges (
    source_id TEXT, target_id TEXT, edge_type TEXT, weight REAL, created TEXT,
    PRIMARY KEY (source_id, target_id, edge_type)
);
CREATE VIRTUAL TABLE fts_index USING fts5(
    node_id UNINDEXED, name, content, tags, tokenize='unicode61', prefix='2,3'
);
```

**Code reuse**: Clean-room from basic-memory FTS5 pattern (AGPL — design only). Standard SQLite3 stdlib.

**Tests** (`tests/unit/test_sqlite_store.py`):
- Upsert + query back
- FTS5 search ranking correctness
- Edge add/get_neighbors
- Reconcile: filesystem adds/removes reflected in DB

---

### 1.3 `storage/graph.py` — Graph Operations (NEW FILE)

**Priority**: 3  
**Complexity**: M  
**Dependencies**: `storage/sqlite_store.py`  

**Implementation**:
- `extract_wikilinks(content: str) -> list[str]`: Regex `\[\[([^\]]+)\]\]`
- `build_edges_from_content(node, all_names: dict[str,str]) -> list[tuple]`: Wikilinks → resolved edges
- `personalized_pagerank(edges, seed_weights, alpha, max_iter, tol) -> dict[str, float]`: Pure-Python iterative PPR
- `get_subgraph(sqlite_store, node_id, depth=2) -> tuple[list[str], list[Edge]]`: BFS via edge table

**Code reuse**:
- **Copy from GAAMA** (MIT, `services/pagerank.py`): Pure-Python PPR implementation (~70 lines)
- Attribution header: `# Adapted from GAAMA (MIT) — Personalized PageRank`

**Tests** (`tests/unit/test_graph.py`):
- Wikilink extraction from various Markdown content
- PPR on hand-crafted 5-node graph (verify scores sum ≈ 1.0, seed node highest)
- BFS subgraph correctness at depth 1, 2

---

### 1.4 `core/engine.py` — Wire Storage Together

**Priority**: 4  
**Complexity**: S  
**Dependencies**: 1.1, 1.2, 1.3  

**Implementation**:
- `__init__`: Create vault dirs, initialize SQLiteStore, run startup reconcile
- `write(content, ...)`: Create MemoryNode → markdown.write() → sqlite.upsert() → extract wikilinks → add edges
- `read(node_id)`: markdown.read()
- `list_nodes(scope?, state?)`: sqlite.get_all_nodes() with filters
- `transition(node_id, target, reason)`: Validate → update state → persist to both stores
- `run_transitions()`: Load active nodes → evaluate all predicates → execute transitions
- `startup_reconcile()`: markdown.list_all() → sqlite.reconcile()

**Code reuse**: Write fresh (orchestration)

**Tests** (`tests/integration/test_engine_phase1.py`):
- Full cycle: write → read → verify
- Transition: active → decided → verify in both MD + DB
- run_transitions: node with expired TTL → verify Expired
- Startup reconcile: add file manually → engine restart → verify in DB

---

## Phase 2: Write Path + Basic Retrieval

### 2.1 `write/router.py` — Write Classification

**Priority**: 5  
**Complexity**: M  
**Dependencies**: Phase 1 complete  

**Implementation**:
- `dedup_check(content, existing_hashes) -> bool`: MD5 hash comparison
- `classify(content, existing_node?, related_nodes?) -> WriteOperation`:
  - Fast path: hash match → Skip; has TTL → Expire; contradicts existing → Replace
  - Default: Append (LLM classification deferred to Phase 3)
- `execute(content, operation, target?) -> MemoryNode`: Dispatch per operation type

**Code reuse**:
- **Adapt from Mem0** (Apache 2.0): `hashlib.md5(content.encode()).hexdigest()` dedup pattern
- Attribution: `# Pattern from Mem0 (Apache 2.0) — hash dedup`

**Tests** (`tests/unit/test_write_router.py`):
- Dedup detects exact duplicates
- Classify with TTL content → Expire
- Execute Replace updates content correctly
- Execute Append creates new node

---

### 2.2 `write/extractor.py` — Basic Memory Extraction

**Priority**: 6  
**Complexity**: S  
**Dependencies**: `write/router.py`  

**Implementation**:
- `extract_basic(text) -> list[ExtractionResult]`: Rule-based sentence splitting + filtering
- `generate_name(content) -> str`: First 5 words, kebab-cased, truncated to 50 chars
- `suggest_tags(content) -> list[str]`: Simple keyword heuristic

LLM-based extraction is Phase 3. This gives us a testable pipeline.

**Code reuse**: Write fresh (trivial rule-based version)

**Tests** (`tests/unit/test_extractor.py`):
- Reasonable candidates from a paragraph
- Name generation produces valid filenames
- Short sentences filtered out

---

### 2.3 `read/scorer.py` — Multi-Signal Scorer (V1: 3 signals)

**Priority**: 7  
**Complexity**: M  
**Dependencies**: `storage/sqlite_store.py`, `lifecycle/decay.py`  

**Implementation**:
- `normalize_bm25(raw_score, midpoint=8.0, steepness=0.6) -> float`: Sigmoid
- `reciprocal_rank_fusion(result_lists, k=60) -> list[tuple[str, float]]`: Standard RRF
- `score(query, candidates, ...) -> list[ScoredMemory]`:
  - Signal 1: BM25 (via sqlite FTS5, sigmoid normalized)
  - Signal 2: Recency (via `compute_decay()`)
  - Signal 3: Frequency (log-normalized `access_count`)
  - Weighted sum per `ScorerWeights` config
  - Assign tiers: top 30% = hot, next 40% = warm, rest = cold

Vector similarity (Signal 4) and graph proximity (Signal 5) deferred to Phase 3.

**Code reuse**:
- **Copy from Hindsight** (MIT): `reciprocal_rank_fusion` function (~30 lines)
- **Adapt from Mem0** (Apache 2.0): sigmoid BM25 normalization
- Attribution headers on each adapted function

**Tests** (`tests/unit/test_scorer.py`):
- normalize_bm25 produces [0, 1]
- RRF merges two ranked lists correctly
- score() ranks recent + frequent nodes higher than old + unused

---

### 2.4 `lifecycle/confidence.py` — Beta Distribution Confidence (NEW FILE)

**Priority**: 8  
**Complexity**: S  
**Dependencies**: `core/node.py`  

**Implementation**:
- `BetaConfidence(BaseModel)`: `alpha=1.0, beta=1.0, recent_outcomes: list[Outcome]`
- `record_outcome(success, weight=1.0)`: Update alpha/beta + append to recent_outcomes (sliding window, max 15)
- `effective_confidence(base=0.5, recency_weight=0.3) -> float`: Blend base + EMA of recent outcomes
- `from_provenance(provenance) -> BetaConfidence`: user-explicit → (9,1); inferred → (1,1)

**Code reuse**:
- Clean-room from Quick Desktop pattern (confidential): Beta distribution + EMA recent outcomes
- Pattern from Cognee (Apache 2.0): `stream_update_weight` formula

**Phase 3 interface pre-build**: Include `should_accelerate_decay() -> bool` (confidence < 0.3) and `should_resist_transition() -> bool` (confidence > 0.8). These will be wired into `lifecycle/transitions.py` in Phase 3 to make confidence modulate state transitions.

**Tests** (`tests/unit/test_confidence.py`):
- Repeated successes increase confidence
- Repeated failures decrease confidence
- User-explicit starts at ~0.9
- Clamped to [0, 1]
- should_accelerate_decay() returns True when confidence < 0.3
- should_resist_transition() returns True when confidence > 0.8

---

## Code Reuse Execution Order

| Step | Copy From | Target | License Header |
|------|-----------|--------|----------------|
| 1 | GAAMA `services/pagerank.py` | `storage/graph.py` | `# Adapted from GAAMA (MIT)` |
| 2 | Hindsight `engine/search/fusion.py` | `read/scorer.py` | `# Adapted from Hindsight (MIT)` |
| 3 | Mem0 `mem0/utils/scoring.py` | `read/scorer.py` | `# Adapted from Mem0 (Apache 2.0)` |
| 4 | Mem0 hash dedup | `write/router.py` | `# Pattern from Mem0 (Apache 2.0)` |

---

## Definition of Done

### Phase 1 Complete:
- [ ] All tests pass (`uv run pytest tests/ -v`)
- [ ] Can write 10 memories to vault, read them back, verify round-trip fidelity
- [ ] FTS5 search returns correct results for keyword queries
- [ ] Wikilinks in content create edges in SQLite graph
- [ ] `engine.run_transitions()` correctly expires a node with past-due TTL
- [ ] `engine.transition()` manually archives a node, reflected in both MD + DB
- [ ] Startup reconcile syncs filesystem → DB correctly

### Phase 2 Complete:
- [ ] `engine.write(content)` persists to both MD + DB with hash dedup
- [ ] Duplicate content detected and skipped (no second file created)
- [ ] `engine.search(query)` returns ranked results (BM25 + recency + frequency)
- [ ] RRF correctly merges multiple signal lists
- [ ] BetaConfidence tracks outcomes and adjusts effective_confidence
- [ ] Integration test: write 20 memories → search → verify ranking is sensible

### Test Targets:
- Phase 1: +25 new tests (total ~39)
- Phase 2: +20 new tests (total ~59)
- All tests run in <5s (no external services, no LLM calls)

---

## Verification

```bash
# All tests pass
uv run --extra dev pytest tests/ -v

# Smoke test
python -c "
from agent_memory_fabric import MemoryEngine
engine = MemoryEngine(vault_path='/tmp/test-vault')
node = engine.write('User prefers dark mode', name='dark-mode-pref', tags=['preference'])
results = engine.search('dark mode')
assert results[0].name == 'dark-mode-pref'
print('Phase 1+2 working!')
"
```

---

## Phase 3 Forward-Looking Notes (Do NOT implement yet)

These are research-validated enhancements for Phase 3. Noted here so Phase 1-2 interfaces accommodate them.

### 3.1 Abstain Gate (TARG-inspired)
Research (TARG paper) shows 70-90% of retrieval can be skipped — only 10-30% of turns actually benefit from memory injection. Phase 3 will add an intent classifier before the scorer that decides "should we inject at all?" This dramatically reduces cost and noise.

**Phase 1-2 implication**: The proactive gateway stub should have a `should_inject(message) -> bool` hook point.

### 3.2 Confidence ↔ State Machine Interaction
Low confidence should accelerate state transitions (faster decay toward Archived). High confidence should resist transitions (persistence). This creates a feedback loop: memories that prove useful stay Active longer; memories that fail transition faster.

**Phase 2 implication**: `lifecycle/confidence.py` (Task 2.4) must expose an interface that `lifecycle/transitions.py` can query. Pre-build: `BetaConfidence.should_accelerate_decay() -> bool` and `BetaConfidence.should_resist_transition() -> bool`.

### 3.3 Staleness Intrusion Filter
Archived and Expired nodes should be hard-excluded from scorer output (not just downweighted). This is the discrete-state advantage over CortexGraph's continuous decay — we can make a clean architectural cut.

**Phase 2 implication**: `read/scorer.py` should accept a `state_filter: set[LifecycleState]` parameter, defaulting to `{ACTIVE, DECIDED}`.

### 3.4 Vector Similarity (Signal 4) + Graph Proximity via PPR (Signal 5)
Phase 3 adds:
- Signal 4: Cosine similarity from sqlite-vec embeddings (requires sentence-transformers)
- Signal 5: PPR scores from `storage/graph.py` seeded by query-mentioned entities

**Phase 1 implication**: `storage/graph.py` PPR is already implemented. `storage/sqlite_store.py` has `search_vector()` and `upsert_embedding()` stubs ready.

### 3.5 Additional Phase 3 Items
- LLM-based write classification (replace rule-based stub in `write/router.py`)
- LLM-based memory extraction (replace `extract_basic` with prompt-driven extraction)
- Proactive gateway with budget allocation (Quick Desktop multi-pipeline pattern)
- Cross-encoder reranking after RRF (Hindsight pattern, MIT)


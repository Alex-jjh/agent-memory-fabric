# Code Reuse Report: Reference Repos → AMF Modules

*Generated: 2026-05-20 | Based on source code analysis of 7 reference systems*

---

## License Summary (Critical)

| Repo | License | Can Copy Code? | Can Adapt Algorithms? |
|------|---------|---------------|----------------------|
| **GAAMA** | MIT | Yes | Yes |
| **HippoRAG** | MIT | Yes | Yes |
| **Hindsight** | MIT | Yes | Yes |
| **Mem0** | Apache 2.0 | Yes (with attribution) | Yes |
| **MemoryOS** | Apache 2.0 | Yes (with attribution) | Yes |
| **CortexGraph** | AGPL-3.0 | **NO** (copyleft) | Yes (algorithms not copyrightable) |
| **basic-memory** | AGPL-3.0 | **NO** (copyleft) | Yes (algorithms not copyrightable) |
| **mcp-mem0** | MIT | Yes | Yes |

**Rule**: For CortexGraph and basic-memory, we can study the algorithms and do clean-room reimplementation, but cannot copy any code verbatim.

---

## Module 1: `lifecycle/decay.py`

### Best Sources

| Source | File | What | Adoptability |
|--------|------|------|-------------|
| **CortexGraph** | `src/cortexgraph/core/decay.py:26-78` | Power-law: `(use_count+1)^β * (1 + dt/t0)^(-α) * strength` | AGPL — clean-room reimplement |
| **MemoryOS** | `memoryos-pypi/mid_term.py:20-36` + `utils.py:228-237` | Heat: `α*visits + β*interaction + γ*exp(-Δt/τ)` | Apache 2.0 — can adapt |

### Recommended Implementation

AMF already has `ebbinghaus_decay`, `power_law_decay`, `exponential_decay`. Enhance with:

```python
# From MemoryOS (Apache 2.0, adaptable):
def heat_score(visits: int, interaction_len: int, hours_since: float,
               alpha=1.0, beta=1.0, gamma=1.0, tau_hours=24.0) -> float:
    recency = math.exp(-hours_since / tau_hours)
    return alpha * visits + beta * interaction_len + gamma * recency

# From CortexGraph (AGPL, reimplement the math):
def power_law_with_halflife(hours_since: float, alpha=1.1, halflife_days=3.0) -> float:
    t_half = halflife_days * 24.0
    denom = math.pow(2.0, 1.0 / alpha) - 1.0
    t0 = t_half / denom if denom > 0 else t_half
    return math.pow(1.0 + (hours_since / t0), -alpha)

# CortexGraph's full score formula (reimplemented):
def composite_score(use_count: int, hours_since: float, strength: float,
                    beta=0.6, decay_model="power_law") -> float:
    use_component = math.pow(use_count + 1, beta)
    decay_component = power_law_with_halflife(hours_since)
    return use_component * decay_component * strength
```

---

## Module 2: `lifecycle/state_machine.py`

### Best Sources

| Source | File | What | Adoptability |
|--------|------|------|-------------|
| **CortexGraph** | `src/cortexgraph/core/scoring.py:10-77` | `should_forget()` (score < 0.05) + `should_promote()` (score >= 0.65 OR use_count >= 5 in 14 days) | AGPL — reimplement logic |
| **CortexGraph** | `src/cortexgraph/tools/gc.py:13-94` | GC tool: lists active memories, scores each, collects below threshold, archives or deletes | AGPL — reimplement |
| **CortexGraph** | `src/cortexgraph/agents/decay_analyzer.py:187-224` | Action recommendation: score<0.05→GC, <0.10→GC, <0.20→CONSOLIDATE, strength>=1.5→PROMOTE | AGPL — reimplement |

### Recommended Implementation

AMF's `transitions.py` already has `TemporalDecayPredicate`, `TTLExpirationPredicate`, `InactivityArchivePredicate`. Add:

```python
# Dual-path promotion (inspired by CortexGraph's logic, clean-room):
class PromotionPredicate:
    def __init__(self, score_threshold=0.65, use_count_threshold=5, time_window_days=14):
        self.score_threshold = score_threshold
        self.use_count_threshold = use_count_threshold
        self.time_window_days = time_window_days

    def evaluate(self, node: MemoryNode) -> LifecycleState | None:
        if node.state != LifecycleState.ACTIVE:
            return None
        score = compute_decay(node.last_accessed, strength=node.strength)
        # Path 1: High composite score
        if score >= self.score_threshold:
            return LifecycleState.DECIDED
        # Path 2: High use in recent window
        age_days = (now - node.created).total_seconds() / 86400
        if node.access_count >= self.use_count_threshold and age_days <= self.time_window_days:
            return LifecycleState.DECIDED
        return None
```

---

## Module 3: `storage/sqlite_store.py`

### Best Sources

| Source | File | What | Adoptability |
|--------|------|------|-------------|
| **basic-memory** | `src/basic_memory/models/search.py:62-94` | FTS5 schema with `tokenize='unicode61'`, prefix indexes, UNINDEXED columns | AGPL — reimplement pattern |
| **basic-memory** | `src/basic_memory/repository/sqlite_search_repository.py:950-973` | BM25 search query with `bm25(search_index)` ranking | AGPL — reimplement pattern |
| **basic-memory** | `src/basic_memory/sync/sync_service.py:729-938` | Watermark-based incremental sync (mtime/size → checksum → change type) | AGPL — reimplement pattern |
| **basic-memory** | `src/basic_memory/services/context_service.py:528-653` | Recursive CTE for graph traversal | AGPL — standard SQL pattern |
| **GAAMA** | `core/storage.py` + `services/` | SQLite + sqlite-vec + FTS5 in single-file DB | MIT — can copy |

### Recommended Schema (clean-room, inspired by patterns):

```sql
-- Nodes table
CREATE TABLE nodes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    content TEXT,
    state TEXT NOT NULL DEFAULT 'active',
    type TEXT NOT NULL DEFAULT 'project',
    project TEXT,
    created TEXT NOT NULL,
    modified TEXT NOT NULL,
    last_accessed TEXT NOT NULL,
    access_count INTEGER DEFAULT 0,
    decay_score REAL DEFAULT 1.0,
    strength REAL DEFAULT 1.0,
    ttl TEXT,
    tags TEXT,  -- JSON array
    file_path TEXT UNIQUE
);

-- Graph edges
CREATE TABLE edges (
    source_id TEXT NOT NULL REFERENCES nodes(id),
    target_id TEXT NOT NULL REFERENCES nodes(id),
    edge_type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    created TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id, edge_type)
);

-- FTS5 full-text search
CREATE VIRTUAL TABLE fts_index USING fts5(
    id UNINDEXED,
    name,
    content,
    tags,
    tokenize='unicode61',
    prefix='2,3'
);

-- Vector embeddings (via sqlite-vec)
CREATE VIRTUAL TABLE vec_index USING vec0(
    node_id TEXT PRIMARY KEY,
    embedding float[384]
);
```

### Sync Algorithm (from basic-memory pattern):
1. Track `last_sync_time` + `last_file_count`
2. Incremental: only scan files with mtime > last_sync
3. Change detection: compare mtime/size first, checksum only if changed
4. Move detection: new file with same checksum as deleted = move
5. Circuit breaker: skip files that fail 3+ consecutive times

---

## Module 4: `read/scorer.py`

### Best Sources

| Source | File | What | Adoptability |
|--------|------|------|-------------|
| **Hindsight** | `engine/search/fusion.py:10-77` | RRF: `score(d) = Σ 1/(k + rank(d))`, k=60 | MIT — **copy directly** |
| **Hindsight** | `engine/search/reranking.py:20-130` | Multiplicative boosts: `CE * (1+α*(recency-0.5)) * (1+α*(temporal-0.5)) * (1+α*(proof-0.5))` | MIT — **copy directly** |
| **Mem0** | `mem0/utils/scoring.py:1-122` | 3-signal hybrid: semantic + sigmoid(BM25) + entity_boost, adaptive normalization | Apache 2.0 — adapt |
| **GAAMA** | `services/ltm_retriever.py:211-235` | PPR+cosine fusion: `score = w1*max_norm(PPR) + w2*max_norm(sim)` | MIT — **copy directly** |
| **GAAMA** | `services/pagerank.py:31-103` | Pure-Python iterative PPR (~70 lines, no C deps) | MIT — **copy directly** |

### Recommended Implementation

```python
# From Hindsight (MIT, copy directly):
def reciprocal_rank_fusion(result_lists: list[list], k: int = 60) -> list[tuple[str, float]]:
    scores = {}
    for results in result_lists:
        for rank, item in enumerate(results, start=1):
            doc_id = item.id
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)

# From Hindsight (MIT, copy directly):
def multiplicative_boost(base_score: float, recency: float, temporal: float,
                         proof_count: int, recency_alpha=0.2, temporal_alpha=0.2,
                         proof_alpha=0.1) -> float:
    proof_norm = min(1.0, 0.5 + (math.log(max(proof_count, 1)) / 10.0))
    recency_boost = 1.0 + recency_alpha * (recency - 0.5)
    temporal_boost = 1.0 + temporal_alpha * (temporal - 0.5)
    proof_boost = 1.0 + proof_alpha * (proof_norm - 0.5)
    return base_score * recency_boost * temporal_boost * proof_boost

# From Mem0 (Apache 2.0, adapt):
def normalize_bm25(raw_score: float, midpoint=8.0, steepness=0.6) -> float:
    return 1.0 / (1.0 + math.exp(-steepness * (raw_score - midpoint)))

# From GAAMA (MIT, copy directly):
def ppr_cosine_fusion(ppr_scores: dict, sim_scores: dict,
                      ppr_weight=0.1, sim_weight=1.0) -> dict:
    max_ppr = max(ppr_scores.values()) if ppr_scores else 1.0
    max_sim = max(sim_scores.values()) if sim_scores else 1.0
    combined = {}
    for nid in set(ppr_scores) | set(sim_scores):
        ppr = ppr_scores.get(nid, 0.0) / max_ppr if max_ppr > 0 else 0.0
        sim = sim_scores.get(nid, 0.0) / max_sim if max_sim > 0 else 0.0
        combined[nid] = ppr_weight * ppr + sim_weight * sim
    return combined
```

### AMF Multi-Signal Scorer Architecture:
1. **Stage 1**: Parallel retrieval (semantic KNN + FTS5/BM25 + graph neighbors)
2. **Stage 2**: RRF to merge candidate lists
3. **Stage 3**: Multiplicative boosts (recency, decay_score, access_count)
4. **Stage 4**: Lifecycle filter (exclude Expired, downweight Archived)
5. **Stage 5**: Token budget allocation (hot/warm/cold tiers)

---

## Module 5: `write/router.py`

### Best Sources

| Source | File | What | Adoptability |
|--------|------|------|-------------|
| **Mem0** | `mem0/memory/main.py:699-860` | V3 ADD-only pipeline + MD5 hash dedup | Apache 2.0 — adapt |
| **Mem0** | `mem0/configs/prompts.py:468-944` | V3 extraction prompt (ADDITIVE_EXTRACTION_PROMPT) | Apache 2.0 — adapt |
| **Hindsight** | `engine/consolidation/prompts.py` | LLM classifies creates/updates/deletes with structured JSON output | MIT — adapt pattern |

### Key Insight

Hindsight's conflict resolution is **100% LLM-based** (no rule-based classifier exists). Mem0 V3 **removed** the LLM-CRUD classifier entirely in favor of ADD-only + hash dedup. Both validate AMF's approach:

**AMF Write Router Strategy:**
1. **Fast path** (no LLM): MD5 hash → if duplicate, skip. If has TTL and expired, classify as Expire.
2. **Slow path** (LLM): Classify remaining as Replace/Append/Synthesize/Branch/Promote using:
   - Existing node content + new content → LLM judgment
   - Structured output: `{"operation": "replace|append|synthesize", "target_node_id": "...", "reason": "..."}`

```python
# From Mem0 (Apache 2.0):
import hashlib

def dedup_check(content: str, existing_hashes: set[str]) -> bool:
    """Returns True if duplicate (should skip)."""
    mem_hash = hashlib.md5(content.encode()).hexdigest()
    return mem_hash in existing_hashes
```

---

## Module 6: `storage/graph.py` (NEW — to be created)

### Best Sources

| Source | File | What | Adoptability |
|--------|------|------|-------------|
| **GAAMA** | `services/pagerank.py:31-103` | Pure-Python PPR with edge-type weights + hub dampening | MIT — **copy directly** |
| **GAAMA** | `core/types.py:20-26` | Multi-node-type schema (Episode/Fact/Reflection/Concept) | MIT — **copy directly** |
| **GAAMA** | `services/graph_edit_learner.py:92-830` | GEL self-healing (detect failure → decompose → patch graph) | MIT — adapt |
| **HippoRAG** | `src/hipporag/HippoRAG.py:1572-1611` | igraph PPR (faster but heavy C dep) | MIT — reference |
| **HippoRAG** | `src/hipporag/information_extraction/openie_openai.py:39-210` | NER → triple extraction pipeline | MIT — adapt |

### Recommended: Copy GAAMA's PPR (MIT, pure Python, ~70 lines)

```python
# From GAAMA services/pagerank.py (MIT license):
def personalized_pagerank(
    edges: list[tuple[str, str, float]],  # (source, target, weight)
    seed_weights: dict[str, float],
    alpha: float = 0.85,  # teleport probability
    max_iterations: int = 200,
    tolerance: float = 1e-6,
) -> dict[str, float]:
    """Pure-Python iterative PPR. No igraph dependency."""
    # Build adjacency
    nodes = set()
    out_edges = {}  # node -> [(target, weight)]
    for src, tgt, w in edges:
        nodes.add(src); nodes.add(tgt)
        out_edges.setdefault(src, []).append((tgt, w))

    # Normalize seed weights
    total_seed = sum(seed_weights.values()) or 1.0
    reset = {n: seed_weights.get(n, 0.0) / total_seed for n in nodes}

    # Initialize scores
    scores = dict(reset)
    n = len(nodes)

    for _ in range(max_iterations):
        new_scores = {}
        for node in nodes:
            # Teleport component
            s = alpha * reset.get(node, 0.0)
            # Incoming links contribution
            # (would need reverse adjacency for efficiency)
            new_scores[node] = s
        # ... (full implementation from GAAMA)
        if converged: break

    return scores
```

### Graph Node Types for AMF:
- **Memory** (user/feedback/project/reference nodes)
- **Entity** (people, places, concepts extracted from content)
- **Cluster** (group of related memories, from consolidation)

### Edge Types:
- `LINKS_TO` (wikilink between memories)
- `MENTIONS` (memory → entity)
- `RELATED` (semantic similarity > threshold)
- `CONSOLIDATED_FROM` (provenance after merge)
- `DERIVED_FROM` (synthesis provenance)

---

## Module 7: `mcp_server/server.py`

### Best Sources

| Source | File | What | Adoptability |
|--------|------|------|-------------|
| **mcp-mem0** | `src/main.py:1-128` | FastMCP setup with lifespan context, `@mcp.tool()` decorators, SSE/stdio transport | MIT — **copy directly as template** |

### Recommended Template (from mcp-mem0, MIT):

```python
from mcp.server.fastmcp import FastMCP, Context
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

@dataclass
class AMFContext:
    engine: MemoryEngine

@asynccontextmanager
async def amf_lifespan(server: FastMCP) -> AsyncIterator[AMFContext]:
    engine = MemoryEngine(vault_path="~/memory-vault")
    yield AMFContext(engine=engine)

mcp = FastMCP("agent-memory-fabric", lifespan=amf_lifespan)

@mcp.tool()
async def amf_retrieve(ctx: Context, query: str, scope: str = None, top_k: int = 5) -> str:
    engine = ctx.request_context.lifespan_context.engine
    results = engine.search(query, top_k=top_k, scope=scope)
    return json.dumps([r.model_dump() for r in results])

@mcp.tool()
async def amf_write(ctx: Context, content: str, operation: str = None, project: str = None) -> str:
    engine = ctx.request_context.lifespan_context.engine
    node = engine.write(content, operation=operation, project=project)
    return f"Created memory: {node.name} (state={node.state.value})"

@mcp.tool()
async def amf_transition(ctx: Context, node_id: str, target_state: str, reason: str = None) -> str:
    engine = ctx.request_context.lifespan_context.engine
    node = engine.transition(node_id, target_state, reason)
    return f"Transitioned {node.name} to {node.state.value}"

@mcp.tool()
async def amf_status(ctx: Context, project: str = None) -> str:
    engine = ctx.request_context.lifespan_context.engine
    # Return counts by state, recent transitions, decay warnings
    ...
```

**Dependencies**: `mcp[cli]>=1.3.0` provides FastMCP.

---

## Module 8: Spaced Repetition / Proactive Injection

### Best Source

| Source | File | What | Adoptability |
|--------|------|------|-------------|
| **CortexGraph** | `src/cortexgraph/core/review.py:15-58` | "Danger zone" parabola: memories scoring 0.15-0.35 get review priority | AGPL — reimplement math |
| **CortexGraph** | `src/cortexgraph/core/review.py:91-137` | `blend_search_results()`: 30% review slots, 2:1 interleave | AGPL — reimplement pattern |

### Recommended Implementation (clean-room):

```python
def review_priority(decay_score: float, danger_min=0.15, danger_max=0.35) -> float:
    """Inverted parabola: peaks at midpoint of danger zone."""
    if decay_score < danger_min or decay_score > danger_max:
        return 0.0
    midpoint = (danger_min + danger_max) / 2
    half_range = (danger_max - danger_min) / 2
    normalized = (decay_score - midpoint) / half_range
    return max(0.0, 1.0 - normalized ** 2)

def blend_with_review(primary: list, review_candidates: list, blend_ratio=0.3) -> list:
    """Interleave fading memories into search results (2 primary : 1 review)."""
    total = len(primary)
    review_slots = int(total * blend_ratio)
    result = []
    p_iter = iter(primary[:total - review_slots])
    r_iter = iter(review_candidates[:review_slots])
    try:
        while True:
            result.append(next(p_iter))
            result.append(next(p_iter))
            result.append(next(r_iter))
    except StopIteration:
        result.extend(p_iter)
        result.extend(r_iter)
    return result[:total]
```

---

## Priority Matrix: What to Implement First

| AMF Module | Best Copyable Source | Effort | Phase |
|------------|---------------------|--------|-------|
| `mcp_server/server.py` | mcp-mem0 (MIT, template) | Low | Phase 4 |
| `read/scorer.py` — RRF | Hindsight (MIT, 70 lines) | Low | Phase 3 |
| `read/scorer.py` — PPR | GAAMA (MIT, 70 lines) | Low | Phase 3 |
| `read/scorer.py` — multiplicative boost | Hindsight (MIT, 30 lines) | Low | Phase 3 |
| `lifecycle/decay.py` — heat score | MemoryOS (Apache 2.0) | Low | Phase 2 |
| `write/router.py` — hash dedup | Mem0 (Apache 2.0, 5 lines) | Low | Phase 2 |
| `storage/sqlite_store.py` — FTS5 schema | Clean-room (basic-memory inspired) | Medium | Phase 1 |
| `storage/graph.py` — construction | GAAMA (MIT, full pipeline) | Medium | Phase 3 |
| `lifecycle/state_machine.py` — promotion | Clean-room (CortexGraph inspired) | Medium | Phase 2 |
| `read/gateway.py` — spaced repetition | Clean-room (CortexGraph inspired) | Medium | Phase 3 |
| `write/router.py` — LLM classification | Hindsight pattern (MIT) | High | Phase 2 |
| `storage/graph.py` — GEL self-healing | GAAMA (MIT, 800 lines) | High | Phase 3+ |

---

## Attribution Requirements

For the final AMF project, include in NOTICE or README:

```
This project incorporates or adapts code from:
- GAAMA (MIT) — Personalized PageRank, graph construction, scoring fusion
- HippoRAG (MIT) — Knowledge graph architecture reference
- Hindsight (MIT) — Reciprocal Rank Fusion, multiplicative scoring
- Mem0 (Apache 2.0) — Hybrid scoring, BM25 normalization, hash dedup
- MemoryOS (Apache 2.0) — Heat-based scoring formula
- mcp-mem0 (MIT) — MCP server template pattern

Algorithms inspired by (clean-room reimplemented):
- CortexGraph (AGPL-3.0) — Power-law decay, promote/forget thresholds, spaced repetition
- basic-memory (AGPL-3.0) — FTS5 schema design, watermark sync, recursive CTE traversal
```

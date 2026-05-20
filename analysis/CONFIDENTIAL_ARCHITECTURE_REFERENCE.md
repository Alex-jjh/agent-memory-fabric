# Confidential Architecture Reference: AgentCore Memory + Quick Desktop

*Generated: 2026-05-20 | Status: Architecture patterns only — NO code copied*

**Legal notice**: These systems are Amazon proprietary. This document describes architectural patterns and design decisions for research reference only. No code has been copied or will be copied. AMF implementations must be clean-room.

---

## 1. AgentCore Memory (Bedrock)

### Architecture Overview

Multi-layered microservices on AWS:
- **Core Engine** (Python): extraction, consolidation, retrieval, storage
- **Proxy Lambda** (TypeScript): API gateway, namespace routing
- **Dashboard** (React): admin UI for memory browsing, tuning, monitoring
- **Eval Suite** (HEAM): comprehensive benchmark framework
- **Canary Agents**: production health monitoring

### Key Patterns for AMF

#### Pattern A: Policy-Based Composition

Instead of monolithic extraction/consolidation logic:
```
MemoryManager orchestrates N MemoryPolicy objects
Each MemoryPolicy = Extractor + Consolidator (per memory type)
```

Policies are composable and independently configurable. Adding a new memory type = registering a new Policy. AMF should adopt this for strategy configuration.

#### Pattern B: Docstring-as-Prompt

Memory type Pydantic models use their class docstring as the extraction prompt hint. The LLM reads the schema definition (with docstring) and produces instances. This is elegant self-documentation — the type IS the instruction.

**AMF implication**: Define `MemoryNode` subclasses where the docstring guides extraction behavior.

#### Pattern C: Retrieve-then-Consolidate

Consolidation algorithm:
1. For each new memory, retrieve top-2 similar existing memories via vector search
2. Batch new + retrieved old (batch_size=4) → LLM decides: Add / Update / Skip
3. UpdateMemory merges old + new; SkipMemory prevents duplicates
4. **Fallback-to-add on failure** — never loses data

**AMF implication**: This is the core dedup algorithm. Better than global comparison (O(n²)) — only compare against nearest neighbors.

#### Pattern D: Windowed Chunking with Past Context

Long conversations processed in chunks:
- `turn_size` = how many turns per extraction call (2-12)
- `past_turn_size` = how many prior turns included for context (wrapped in `<past_conversation>` tags)
- Citation filtering: only keep memories sourced from `<current_conversation>`, not from historical context

**AMF implication**: Prevents re-extraction of already-known information from context windows.

#### Pattern E: Gaussian Recency Decay in Search

Uses OpenSearch `function_score` with Gaussian decay on timestamp:
- Configurable scale, decay factor, and weight
- Applied at query time (no re-indexing needed)
- Combined with namespace + policy_id filtering

**AMF implication**: Time-weighted retrieval without maintaining a separate decay score column. Query-time decay is more flexible than stored scores.

#### Pattern F: Namespace Hierarchy

```
/user/{hmac_hash}/lessons         -- manual memories
/user/{hmac_hash}/episodes/       -- raw conversation events
/user/{hmac_hash}/reflections/    -- promoted memories
/user/{hmac_hash}/{strategy_id}/  -- auto-distilled by policy
/group/general/                   -- cross-user aggregated knowledge
```

HMAC-SHA256 hashed user identifiers prevent enumeration.

#### Pattern G: Group Distillation

Novel pattern for multi-user systems:
- When N distinct users (default=3) independently create similar reflections
- Auto-promotes to group-level knowledge via LLM distillation
- Confidence scoring: semantic coherence (0.35) + independence (0.25) + actionability (0.25) + novelty (0.15)
- Rejects common-sense or single-source patterns

#### Pattern H: HEAM Evaluation Framework

Intrinsic memory quality metrics (MemoryLens):
- **Faithfulness**: Are memories grounded in source conversations?
- **Redundancy**: Semantic duplication rate
- **ConflictRate**: Factual contradiction detection
- **CompressionRate**: Token ratio (memory tokens / raw tokens)

Downstream benchmarks: LoCoMo, LongMemEval, KnowMeBench, PersonaMem, TauBench, RealMemBench (interleaved)

3-way classification (HaluMem): correct / hallucinated / omitted — more informative than binary accuracy.

---

## 2. Quick Desktop (Amazon Q)

### Architecture Overview

Python desktop application with strict layer separation:
- **L0 (qw_core)**: models, storage, metrics, bedrock client
- **L1 (qw_memory + qw_knowledge)**: memory system + knowledge graph
- **L2 (qw_agent)**: orchestration, prompt assembly, hooks

Memory and KG are separate systems:
- **Memory** = learned user preferences, procedures, strategies (mutable, confidence-tracked)
- **Knowledge Graph** = file/entity graph + RAG (indexed external documents)

### Key Patterns for AMF

#### Pattern I: TextGrad-Style Optimizer

Treats memories as "parameters" in a computation graph:
- **Single-agent mode**: One LLM call analyzes a conversation trace → invokes memory CRUD tools
- **Backprop mode**: Two-stage (compute_gradients → apply_feedback)
- Memories that lead to good outcomes get reinforced; memories that lead to failures get weakened

**AMF implication**: Consider treating state transitions as a learnable optimization problem rather than pure rule-based predicates.

#### Pattern J: Write Trigger Heuristics

When to extract:
- Every N turns (default=8)
- OR on explicit user "save" request
- OR after idle timeout (120s)
- **Skip heuristic**: If no tool calls AND no save request in the turn range → skip entirely (pure chitchat = nothing extractable)
- Single-slot concurrency: max 1 in-flight + 1 pending optimization

**AMF implication**: The skip heuristic is essential for efficiency. Claude Code's "every turn" approach is expensive; Quick's "every 8 turns with skip" is more practical for a daemon.

#### Pattern K: Bayesian Confidence with Recent Outcomes

Each memory has:
- `alpha` / `beta` (Beta distribution parameters)
- `recent_outcomes`: sliding window of last 15 {success, rationale, timestamp}
- `effective_confidence` = 0.7 × base_confidence + 0.3 × recency_weighted_outcomes
- Exponential recency weighting (decay = 0.8)

Anti-patterns are capped at 0.6 confidence to prevent them from becoming permanent.

**Self-correction**: When a tool succeeds but an anti-pattern warned against it → automatic failure recorded on the anti-pattern.

**AMF implication**: This is far more sophisticated than simple decay. It respects accumulated evidence while being responsive to recent signals. AMF's discrete states could incorporate this: `decay_score` becomes `effective_confidence` computed from a Beta distribution.

#### Pattern L: Multi-Pipeline Retrieval with Budgets

Named pipelines, each with a dedicated purpose and token budget:

| Pipeline | Purpose | Budget |
|----------|---------|--------|
| profile | User identity, location, workspace | 20% |
| procedure | Step-by-step instructions | 30% |
| facts | General knowledge/preferences | 30% |
| domain | Tag-overlap expansion for active tools | 10% |
| carryover | Multi-turn continuity (prior N turns) | 10% |
| tool_guidance | Reactive: fires on tool failure | on-demand |
| recall | Agent-initiated explicit search | on-demand |

Total budget = 2000 tokens. Within each pipeline, greedily select by quality score until budget exhausted.

**AMF implication**: AMF's proactive gateway should use a similar budget-based approach. The "domain expansion" pipeline (surfacing strategies by tag overlap rather than semantic similarity) is particularly clever for discovering relevant procedures.

#### Pattern M: Injection into User Message (KV-Cache Optimization)

- Memories formatted as `<learned_context>...</learned_context>` XML
- Injected by prepending to the LAST user message's first text block
- System prompt is kept static (no timestamps, no per-turn data)
- Dual cache-point strategy (last two assistant messages)
- Result: system prompt + all prior turns hit KV-cache on every request

**AMF implication**: This is critical for cost. AMF's proactive gateway must inject into user messages, not system prompt, to preserve caching. The constant system prompt constraint informs prompt architecture.

#### Pattern N: Interpretation Rules in System Prompt

Separate memories (DATA) from how to use them (INSTRUCTION):
- Memories are injected raw with metadata: `[provenance] [relevance: N%] [cert: N%] [age]`
- System prompt contains `<memory_interpretation_rules>` telling the agent:
  - How to handle low-confidence memories (hedge language)
  - How to prioritize by provenance (user-explicit > inferred)
  - When to ignore stale memories
  - How to handle anti-patterns

**AMF implication**: AMF should define interpretation rules separately from memory content. This enables changing injection behavior without re-extracting memories.

#### Pattern O: Injection Security

- `escape_context_tags()` prevents prompt injection via stored memory text
- `frame_untrusted()` wraps external data with boundary markers
- Global behaviors have restricted confidence range (can't exceed 0.9)

**AMF implication**: Any system that injects user-created content into prompts MUST sanitize for tag injection.

#### Pattern P: Auto-Trim with Protected Categories

When memory count exceeds limit (10000):
- Trim 10% of trimmable memories
- Score: `0.4 × effective_confidence + 0.3 × recency_sigmoid + 0.3 × utility_ratio`
- **Protected** (never trimmed): profile, preference, explicit provenance, global_behavior
- Effectively implements "cold death" for low-value memories

**AMF implication**: This is an alternative to AMF's discrete Expired state — continuous scoring with a trim floor. Both approaches have merit; AMF's discrete states make the decision explicit and user-visible.

#### Pattern Q: Knowledge Graph with Hybrid Search

- SQLite + FTS5 + vector embeddings (Cohere v3)
- Deterministic node IDs: `{node_class}:{md5[:12]}`
- Search modes: auto, keyword, semantic, hybrid, pagerank
- "Auto" mode: keyword priority for exact matches, semantic fills remaining slots
- PageRank for global importance scoring
- LLM-driven compaction for entity deduplication (7-day recheck interval)

#### Pattern R: Domain-Scoped Memory Injection

`applicable_domains` field on each memory allows tool-specific scoping:
- Memory "Use --format json for aws cli" only surfaces when AWS CLI tool is active
- Domain expansion pipeline discovers relevant memories by tag overlap
- Active domains detected from currently-available tools

**AMF implication**: Project-scoped memories in AMF serve a similar purpose. The tag-overlap discovery mechanism is more flexible than strict project assignment.

---

## 3. Synthesis: What AMF Should Adopt (As Design Patterns)

### High Priority (Phase 1-2)

| Pattern | Source | AMF Module | Why |
|---------|--------|-----------|-----|
| Retrieve-then-consolidate | AgentCore | `write/router.py` | Core dedup algorithm — compare against K nearest neighbors, not global |
| Bayesian confidence | Quick | `lifecycle/decay.py` | Better than simple temporal decay — incorporates usage outcomes |
| Skip heuristic | Quick | `write/extractor.py` | Don't extract from pure chitchat — saves cost |
| Fallback-to-add | AgentCore | `write/router.py` | Never lose data on consolidation failure |
| Injection into user message | Quick | `read/gateway.py` | Preserves KV-cache for all prior turns |
| Protected categories | Quick | `lifecycle/transitions.py` | User-explicit memories never auto-expire |

### Medium Priority (Phase 3)

| Pattern | Source | AMF Module | Why |
|---------|--------|-----------|-----|
| Multi-pipeline with budgets | Quick | `read/gateway.py` | Structured injection with per-category token allocation |
| Policy-based composition | AgentCore | `core/engine.py` | Extensible strategy registration |
| Gaussian recency in search | AgentCore | `read/scorer.py` | Query-time decay without stored scores |
| Windowed chunking | AgentCore | `write/extractor.py` | Handle long conversations without token overflow |
| Domain expansion | Quick | `read/gateway.py` | Tag-overlap discovery beyond semantic similarity |
| Interpretation rules | Quick | `read/gateway.py` | Separate data from usage instructions |

### Lower Priority (Phase 4+)

| Pattern | Source | AMF Module | Why |
|---------|--------|-----------|-----|
| Group distillation | AgentCore | future | Multi-user knowledge aggregation |
| Docstring-as-prompt | AgentCore | `core/node.py` | Self-documenting memory types |
| TextGrad optimizer | Quick | future | Learnable extraction optimization |
| MemoryLens eval | AgentCore | `amf-experiments/` | Intrinsic quality metrics for Paper 1 |
| Anti-pattern self-correction | Quick | `lifecycle/transitions.py` | Memories that conflict with observed reality auto-degrade |
| HEAM benchmarks | AgentCore | `amf-experiments/` | Comprehensive eval framework for Paper 1 |

---

## 4. Key Differences: AgentCore vs Quick vs AMF

| Dimension | AgentCore | Quick Desktop | AMF (proposed) |
|-----------|-----------|---------------|----------------|
| **Lifecycle** | None (only dedup/consolidation) | Bayesian confidence + auto-trim | Discrete state machine (Active/Decided/Archived/Expired) |
| **Decay model** | Gaussian at query time | Beta distribution + recent outcomes | Ebbinghaus/power-law + state transitions |
| **Write trigger** | Per-session (batch) | Every 8 turns + skip heuristic | Per-turn forked extraction (Claude Code style) + consolidation cron |
| **Consolidation** | LLM arbitrates Add/Update/Skip | TextGrad optimizer | State transitions + Graph Edit Learning |
| **Retrieval** | Dense + sparse + rerank | Multi-pipeline with budgets | Multi-signal scorer + proactive gateway |
| **Proactive** | No (reactive only) | Yes (inject every turn) | Yes (intent-aware gateway <100ms) |
| **Graph** | No | Separate KG system | Unified (memory nodes = graph nodes) |
| **Transparency** | Dashboard (admin-facing) | Hidden from user | Obsidian plugin (user-facing) |
| **Scoping** | Namespace hierarchy (user/policy/session) | Single-user + domain tags | Global/Project/Session three-tier |
| **User control** | Via dashboard | Explicit save only | Pin/archive/expire/browse |
| **Multi-user** | Yes (group distillation) | No (desktop-only) | Single-user for v1 |

---

## 5. Critical Insights for Paper 1

1. **AgentCore confirms "learn to forget" ≠ actual forgetting**: Despite the marketing, AgentCore has NO forgetting mechanism. Only dedup (consolidation) controls memory growth. This validates Paper 1's contribution.

2. **Quick's Bayesian confidence is the closest to lifecycle management**: But it's continuous (score fades), not discrete (state transitions). The difference:
   - Quick: memory at confidence 0.05 is effectively dead but still exists, could revive
   - AMF: memory in Expired state is explicitly excluded, architecturally dead, auditable

3. **Neither system makes lifecycle decisions visible to users**: Quick hides everything; AgentCore has admin dashboard only. AMF's Obsidian transparency is genuinely novel.

4. **Both validate the "proactive > reactive" thesis**: Quick's every-turn injection is effective. AgentCore's purely reactive retrieval is its main weakness (acknowledged in their eval results).

5. **HEAM framework provides ready-made benchmarks**: AMF can directly use LoCoMo, LongMemEval, and the MemoryLens metrics for Paper 1's evaluation. The interleaved evaluation pattern (RealMemBench) is essential for testing lifecycle effects over extended conversations.

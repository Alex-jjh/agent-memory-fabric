# Feature Specification: Agent Memory Fabric (AMF)

**Created**: 2026-05-20

**Status**: Draft

**Input**: Design documents in `discussion-files/` (04-project-plan, 08-multi-project-scope, 09-reference-systems-deep-dive) + 12-system comparative analysis (`analysis/SYNTHESIS.md`)

---

## Problem Statement

LLM agent memory systems today are purely additive — memories accumulate indefinitely with no principled mechanism for forgetting, state transitions, or lifecycle management. Analysis of 15 real systems (3 industrial + 12 open-source) confirms:

- **0/15** implement discrete lifecycle state machines with explicit transition predicates
- **Only 2/15** implement any form of temporal decay (CortexGraph: continuous power-law; MemoryOS: heat-based)
- **Only 1/15** implements proactive injection (CortexGraph: spaced repetition)
- **0/15** combine lifecycle states + graph + vector + proactive retrieval + user transparency

The result: stale memories compete with fresh ones for retrieval slots, contradictions accumulate silently, and users have no visibility into what their agent "knows" or how that knowledge evolves.

---

## User Scenarios & Testing

### User Story 1 - Memory Lifecycle Management (Priority: P1)

An AI agent creates memories during conversation. Over time, some become stale (user moved cities), some become decided (project direction confirmed), and some expire (meeting time passed). The system automatically transitions memory states based on configurable predicates, preventing stale information from polluting retrieval.

**Why this priority**: Core differentiator. Without lifecycle, AMF is just another memory store.

**Independent Test**: Create 10 memories with varying ages and interaction patterns. Verify state transitions fire correctly: Active memories with no interaction for 2 weeks → Archived; memories with TTL past due → Expired; memories confirmed by user → Decided.

**Acceptance Scenarios**:

1. **Given** a memory node in Active state with no interactions for 14 days, **When** the decay engine runs, **Then** the node transitions to Archived and is excluded from warm-tier retrieval.
2. **Given** a memory with `ttl: 2026-05-20T15:00`, **When** current time passes TTL, **Then** node transitions to Expired and is excluded from all retrieval tiers.
3. **Given** an Active memory about "considering option A vs B", **When** user says "we decided on A", **Then** the write router detects convergence and transitions to Decided state.

---

### User Story 2 - Write Semantics Classification (Priority: P1)

When new information arrives, the system classifies it into one of 6 write operations (Replace/Append/Synthesize/Expire/Branch/Promote) rather than blindly appending. This prevents contradictions, reduces noise, and maintains memory coherence.

**Why this priority**: Write quality directly determines retrieval quality. Mem0 V3 retreated to ADD-only because LLM-decides-CRUD was unreliable — AMF needs a better approach.

**Independent Test**: Feed 20 diverse memory updates (address changes, new events, conflicting facts, temporal expirations). Verify correct operation classification for each.

**Acceptance Scenarios**:

1. **Given** existing memory "User lives in Shanghai", **When** user says "I moved to Suzhou last week", **Then** write router classifies as Replace and updates the existing node.
2. **Given** existing memory about FYP project, **When** user discusses a new meeting with supervisor, **Then** write router classifies as Append (new event, non-contradictory).
3. **Given** 5 discussion memories about the same topic, **When** consolidation runs, **Then** write router classifies as Synthesize and creates a higher-order insight node.

---

### User Story 3 - Proactive Retrieval Gateway (Priority: P2)

When a user message arrives, the system predicts which memories will be relevant and injects them into the agent's context *before* the agent processes the message — within <100ms decision time.

**Why this priority**: Reactive retrieval (agent searches when it realizes it needs info) degrades 17 points over extended conversations. Proactive injection maintains accuracy.

**Independent Test**: Send 50 test messages spanning 5 different project contexts. Measure: (a) gateway decision latency <100ms, (b) precision@5 of injected memories vs ground truth relevance labels.

**Acceptance Scenarios**:

1. **Given** user sends "let's continue the AMF paper discussion", **When** proactive gateway fires, **Then** memories tagged with project=AMF in Active/Decided states are injected within 100ms.
2. **Given** user sends a generic greeting with no project context, **When** proactive gateway fires, **Then** only Global-scope Decided memories (user profile, preferences) are injected.
3. **Given** user references a person mentioned across multiple projects, **When** proactive gateway fires, **Then** the person's Global entity node plus relevant project context are injected.

---

### User Story 4 - Multi-Signal Retrieval Scoring (Priority: P2)

Retrieved memories are ranked by a multi-signal scorer combining: semantic similarity, graph proximity, hierarchy match, temporal decay, access frequency, and intent classification. This outperforms single-signal (vector-only) retrieval.

**Why this priority**: Literature shows retrieval method drives 14-23pt accuracy differential. Multi-signal is the proven approach (Hindsight, GAAMA, OpenClaw).

**Independent Test**: Benchmark against vector-only baseline on LoCoMo dataset. Target: +5pt retrieval precision improvement.

**Acceptance Scenarios**:

1. **Given** a query about "Brennan's feedback on the paper", **When** scorer runs, **Then** graph proximity to the "Brennan" entity node boosts relevant memories above unrelated ones with similar embeddings.
2. **Given** two semantically similar memories where one is Active and one is Archived, **When** scorer runs, **Then** Active memory scores higher due to lifecycle state weight.

---

### User Story 5 - Transparency & User Control (Priority: P3)

Users can browse their agent's memory through an Obsidian plugin that shows lifecycle states as visual badges, color-codes the graph view by state, and provides controls to pin, archive, expire, or refresh memories.

**Why this priority**: 96% of AI memories are created unilaterally (CHI 2026 study). Users need agency. But this is a UI layer that depends on P1-P2 being solid.

**Independent Test**: Install Obsidian plugin against a populated vault. Verify: state badges render correctly, graph view shows color differentiation, user can manually transition states, changes propagate to the core engine.

**Acceptance Scenarios**:

1. **Given** a memory vault with nodes in all 4 states, **When** user opens Obsidian graph view, **Then** Active=green, Decided=blue, Archived=gray, Expired=red with faded opacity.
2. **Given** an Active memory, **When** user right-clicks and selects "Archive", **Then** state transitions immediately, node moves to cold tier, and frontmatter updates.

---

### Edge Cases

- What happens when a memory is referenced by other nodes and transitions to Expired? (Answer: edges preserved but node excluded from retrieval; graph traversal skips it unless explicitly queried)
- How does the system handle conflicting state transitions? (Answer: explicit predicates have priority order; user manual override always wins)
- What if the proactive gateway injects too many memories and exceeds token budget? (Answer: tiered budget — hot: ~1300 tokens, warm: ~2000 tokens; overflow truncates lowest-scored memories)
- What happens during concurrent writes from multiple agents? (Answer: optimistic locking on per-node version field; last-write-wins with conflict detection)

---

## Requirements

### Functional Requirements

- **FR-001**: System MUST maintain a discrete lifecycle state for each memory node (Active, Decided, Archived, Expired)
- **FR-002**: System MUST evaluate transition predicates on configurable triggers (time-based, event-based, user-initiated)
- **FR-003**: System MUST classify incoming writes into one of 6 operation types before persisting
- **FR-004**: System MUST provide proactive retrieval that selects relevant memories before agent processes a message
- **FR-005**: System MUST score memories using multiple signals (semantic, graph, decay, frequency, intent)
- **FR-006**: System MUST store memories as human-readable Markdown files with YAML frontmatter
- **FR-007**: System MUST maintain a SQLite sidecar database for metadata, vectors, and graph edges
- **FR-008**: System MUST expose functionality via MCP (Model Context Protocol) server
- **FR-009**: System MUST support three memory scopes: Global, Project, Session
- **FR-010**: System MUST implement temporal decay functions (configurable: Ebbinghaus, power-law, exponential)
- **FR-011**: System MUST support dual-stream writes: fast synchronous append + async background consolidation
- **FR-012**: System MUST NOT require cloud services or API keys for core functionality (local-first)
- **FR-013**: System MUST be compatible with Obsidian vault structure (wikilinks, frontmatter, folder hierarchy)
- **FR-014**: System MUST provide a CLI for testing and manual operations

### Key Entities

- **MemoryNode**: A unit of memory with content, state, metadata, embeddings, and graph edges. Stored as one `.md` file.
- **LifecycleState**: Enum (Active, Decided, Archived, Expired) with per-state write permissions and retrieval visibility.
- **WriteOperation**: Typed operation (Replace, Append, Synthesize, Expire, Branch, Promote) applied to a MemoryNode.
- **TransitionPredicate**: A condition that, when true, triggers a state transition (e.g., `temporal_decay > 0.8 AND no_recent_access > 14d`).
- **Project**: A scoped memory namespace with its own lifecycle (Active, Paused, Completed, Abandoned).
- **RetrievalResult**: Scored list of memory nodes with injection tier (hot/warm/cold) and token budget allocation.

---

## Architecture

### System Components

```
┌─── Clients ────────────────────────────────────────────────────────┐
│  Claude Code │ Cursor │ Custom Agent │ Obsidian Plugin │ CLI       │
└──────────────────────────┬─────────────────────────────────────────┘
                           │ MCP Protocol / REST API
┌──────────────────────────▼─────────────────────────────────────────┐
│  AMF Core Daemon (Python, long-running)                             │
│                                                                     │
│  ┌─── Read Path ───────────────────────────────────────────────┐   │
│  │  Proactive Gateway → Scope Inference → Multi-Signal Scorer  │   │
│  │  → Tiered Budget Allocator → Injection Formatter            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─── Write Path ──────────────────────────────────────────────┐   │
│  │  Write Router (classify op) → Fast Append (sync)            │   │
│  │  → Background Consolidation (async) → State Transitions     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─── Lifecycle Engine ────────────────────────────────────────┐   │
│  │  State Machine → Transition Predicates → Decay Functions    │   │
│  │  → GC (archive/expire) → Consolidation (merge duplicates)  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─── Storage Layer ──────────────────────────────────────────┐    │
│  │  Markdown Files (source of truth)                           │    │
│  │  SQLite Sidecar (.amf/index.db): metadata, vectors, graph  │    │
│  │  Embeddings: local model (e5-small / BGE-small)            │    │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: pydantic (models), sqlite-vec (vector search), sqlite3 (metadata + FTS5), sentence-transformers (embeddings), mcp-sdk (MCP server), click (CLI), watchfiles (filesystem monitoring)

**Storage**: Markdown files + SQLite sidecar (`.amf/index.db`)

**Testing**: pytest + hypothesis (property-based testing for state machine)

**Target Platform**: macOS / Linux (local daemon)

**Project Type**: Library + Daemon + MCP Server

**Performance Goals**: Proactive gateway decision <100ms; write classification <200ms; full retrieval cycle <500ms

**Constraints**: No cloud dependencies for core; local embeddings only; Obsidian-compatible file format; <500MB memory footprint

---

## Key Interfaces

### MCP Tools (exposed to AI agents)

```
amf_retrieve(query, scope?, top_k=5, tier="warm")
  → Returns ranked memories with scores and injection tier

amf_write(content, operation?, project?, metadata?)
  → Classifies and persists a new memory, returns node ID

amf_transition(node_id, target_state, reason?)
  → Manually trigger a state transition

amf_search(query, scope?, filters?, include_archived=false)
  → Full search with filtering (vs proactive which is automatic)

amf_status(project?)
  → Returns memory statistics: counts by state, recent transitions, decay warnings
```

### Python API (for direct integration)

```python
from agent_memory_fabric import MemoryEngine

engine = MemoryEngine(vault_path="~/memory-vault")

# Write
node = engine.write("User decided on option A for the paper", operation="replace", project="amf")

# Read (proactive)
memories = engine.retrieve_proactive(message="let's discuss the paper", scope="amf")

# Lifecycle
engine.run_transitions()  # Evaluate all predicates, fire transitions
engine.run_consolidation()  # Merge duplicates, synthesize insights

# Query
results = engine.search("Brennan feedback", top_k=5, include_archived=False)
```

### Memory Node Frontmatter Schema

```yaml
---
id: uuid-v4
name: short-kebab-slug
state: active          # active | decided | archived | expired
type: project          # user | feedback | project | reference | entity
project: amf           # project scope (null = global)
created: 2026-05-20T14:30:00Z
modified: 2026-05-20T15:00:00Z
last_accessed: 2026-05-20T15:00:00Z
access_count: 3
decay_score: 0.85      # current decay value [0, 1]
strength: 1.2          # importance weight [1.0, 2.0]
ttl: null              # optional expiration datetime
tags: [paper, lifecycle, design-decision]
links: [node-id-1, node-id-2]  # graph edges
---
```

---

## Non-Goals

- **NOT a general-purpose RAG system**: AMF manages agent memory specifically, not arbitrary document retrieval
- **NOT a vector database**: SQLite-vec is used internally but AMF is not a database product
- **NOT a training data pipeline**: memories are for inference-time context, not model fine-tuning
- **NOT an agent framework**: AMF provides memory to agents but does not orchestrate them
- **NOT a note-taking app**: while Obsidian-compatible, AMF is infrastructure for AI agents, not a human PKM tool
- **NOT cloud-required**: core functionality works fully offline with local embeddings
- **NOT multi-user**: designed for single-user, multi-agent scenarios (one person, many AI assistants)

---

## Prior Art Acknowledgment

| System | Relationship to AMF | What We Borrow |
|--------|-------------------|----------------|
| **CortexGraph** | Closest prior art for lifecycle | Power-law decay math, promote/forget threshold concept, spaced repetition idea. **We diverge**: discrete states vs continuous decay |
| **Claude Code** | Paper 1 baseline (control condition) | 4-type taxonomy, forked-agent extraction, manifest pre-injection, Sonnet ranker pattern |
| **OpenClaw** | Scoring reference | 6-signal weighted scorer baseline weights (frequency 24%, relevance 30%, etc.) |
| **Hermes** | Plugin target | MemoryProvider interface contract; AMF will implement this to plug into Hermes ecosystem |
| **Mem0** | Write path reference | ADD-only V3 validates simplicity; hybrid scoring (semantic + BM25 + entity) |
| **Letta** | Tiering reference | Core/archival/recall three-tier model; "sleeptime" async consolidation concept |
| **MemoryOS** | Decay reference | Heat formula inspiration: `H = α·visits + β·interaction + γ·exp(-Δt/24)` |
| **GAAMA** | Graph retrieval reference | PPR-augmented retrieval; Graph Edit Learning (self-healing KG) concept |
| **basic-memory** | Architecture precedent | File-first design (Markdown = source of truth, DB = derived index); MCP server pattern |
| **HippoRAG** | Retrieval reference | Personalized PageRank over knowledge graph for associative recall |

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: Retrieval precision@5 improves by >=5 points over no-lifecycle baseline (Claude Code clone) on LoCoMo extended dialogues
- **SC-002**: Contradiction rate decreases by >=50% compared to no-lifecycle baseline after 100+ conversation turns
- **SC-003**: Proactive gateway decision latency p95 < 100ms on a corpus of 1000 memory nodes
- **SC-004**: Token efficiency: >=20% reduction in injected tokens with equal or better retrieval precision (lifecycle filtering removes stale candidates)
- **SC-005**: State machine transitions fire correctly for >=95% of test predicates (validated via property-based testing)
- **SC-006**: System handles 10,000 memory nodes without degradation in retrieval latency (<500ms p95)

---

## Assumptions

- Users have Python 3.11+ installed locally
- Primary deployment is macOS/Linux desktop (not mobile, not server-side)
- Memory corpus size is 100-10,000 nodes per user (not millions)
- LLM access is available for write classification and consolidation (but not required for retrieval)
- Obsidian is the primary UI but the system works without it (CLI + MCP are sufficient)
- Single-user deployment; multi-tenant is out of scope for v1
- English and Chinese content are both supported (embedding model must handle both)

---

## Implementation Phases

| Phase | Duration | Scope | Dependencies |
|-------|----------|-------|-------------|
| **Phase 1: Foundation** | 4 weeks | Storage layer, MemoryNode model, basic write/read, CLI, SQLite sidecar | None |
| **Phase 2: Lifecycle Engine** | 4 weeks | State machine, transition predicates, decay functions, write router | Phase 1 |
| **Phase 3: Retrieval** | 4 weeks | Vector index, BM25, multi-signal scorer, proactive gateway, tiered output | Phase 1-2 |
| **Phase 4: UI & Integration** | 4 weeks | MCP server, Obsidian plugin, project scoping, team sync | Phase 1-3 |

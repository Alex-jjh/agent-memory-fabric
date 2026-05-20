# AMF (Agent Memory Fabric) — 参考源码 & 项目清单
*Created: 2026-05-20 | Purpose: 开发参考索引*

---

## 一、完全开源（可直接参考 + 引用）

### 1.1 Graph + Retrieval 方向

| 项目 | Repo | License | Stars | 重点参考内容 |
|------|------|---------|-------|-------------|
| **GAAMA** | `swarna-kpaul/gaama` | 开源 | 小 | ★ 4 node types (Episode/Fact/Reflection/Concept) + 5 edge types + PPR augmented retrieval + 3-step write pipeline + **Graph Edit Learning (GEL) self-healing** |
| **HippoRAG** | `OSU-NLP-Group/HippoRAG` | 开源 | NeurIPS'24 | ★ KG + Personalized PageRank + entity linking → graph traversal → retrieval; Parquet-backed stores + igraph |
| **Hindsight** | `vectorize-io/hindsight` | MIT | 大 | ★ Conflict resolution 三策略 (Redundant/Direct contradiction/State update) + entity resolution + cross-encoder reranking + 94.6% LongMemEval; **4-way parallel retrieval (semantic/BM25/graph/temporal) → RRF**; schema-per-tenant PG; recency-weighted scoring |
| **Microsoft GraphRAG** | `microsoft/graphrag` | MIT | 大 | 图构建 pipeline + community detection + hierarchical summarization; **10-step LLM-heavy indexing pipeline**; 4 search modes (Local/Global/DRIFT/Basic); Parquet + LanceDB |
| **LightRAG** | `HKUDS/LightRAG` | 开源 (EMNLP'25) | 大 | 轻量 graph RAG 实现 + 快速 graph 构建; **5 query modes**; map-reduce summarization on entity description accumulation; purely additive (no decay) |
| **Cognee** | `topoteretes/cognee` | 开源 | 中 | "Memory for AI Agents in 6 lines" + graph-based pipeline; **dual-layer: permanent KG (Neo4j/Ladybug) + session cache (Redis, 7-day TTL)**; feedback-weighted retrieval; lazy bridging via `improve()` |

### 1.2 Memory System 方向

| 项目 | Repo | License | Stars | 重点参考内容 |
|------|------|---------|-------|-------------|
| **Mem0** | `mem0ai/mem0` | Apache 2.0 | 大 | ★ Write pipeline: **V3 went ADD-only** (validates "less is more" / Hermes philosophy); MD5 hash dedup replaces LLM judgment; hybrid scoring (semantic + BM25 + entity boost); spaCy NER; 30+ vector backends; **decay is platform-only, not in OSS SDK** |
| **Letta (MemGPT)** | `letta-ai/letta` | Apache 2.0 | 大 | ★ OS 比喻：**core memory (in-context blocks agent self-edits via tool calls)** + recall (hybrid RRF) + archival (pgvector, 4096 dims); **"sleeptime" background agents** for async consolidation; optional git-backed memory; optimistic locking for concurrent multi-agent writes |
| **Letta AI Memory SDK** | `letta-ai/ai-memory-sdk` | 开源 | 小 | 比 Letta 主 repo 更聚焦：pluggable agentic memory SDK |
| **MemoryOS** | `BAI-LAB/MemoryOS` | 开源 (EMNLP'25 Oral) | 中 | ★ **Three-tier: short-term (FIFO deque, cap 10) → mid-term (sessions, heat-based LFU eviction) → long-term (ChromaDB + structured profiles)**; Heat formula: `H = α·visits + β·interaction_len + γ·exp(-Δt/24)`; LLM summarization at write; parallel retrieval across tiers |
| **MemOS (MemTensor)** | `MemTensor/MemOS` | 开源 | 中 | 另一个 MemOS 实现，memory OS for LLM and Agent systems |

### 1.3 Temporal Decay / Forgetting 方向

| 项目 | Repo | License | Stars | 重点参考内容 |
|------|------|---------|-------|-------------|
| **CortexGraph** | `prefrontal-systems/cortexgraph` | 开源 | 小 | ★★★ **CLOSEST PRIOR ART FOR LIFECYCLE**. Power-law/exponential/two-component decay models; score = `(use_count+1)^0.6 * decay(dt) * strength`; threshold-based lifecycle (forget at 0.05, promote at 0.65); GC removes/archives forgotten; consolidation merges duplicates; **spaced repetition = proactive injection** (fading memories opportunistically blended into search when contextually relevant); JSONL/SQLite + Obsidian vault for LTM promotion; entity extraction (spaCy/regex); importance scoring (strength 1.0-2.0). **AMF differentiator: discrete state machine vs CortexGraph's continuous decay curve.** |
| **Generative Agents** | `joonspk-research/generative_agents` (Stanford 原版) | 开源 | 大 | ★ 原始 reflection 机制：importance scoring + recency + relevance → periodic reflection → higher-order observations |

### 1.4 Obsidian + AI Memory 方向

| 项目 | Repo | License | Stars | 重点参考内容 |
|------|------|---------|-------|-------------|
| **Basic Memory** | `basicmachines-co/basic-memory` | 开源 | ~1000 | ★ **File-first architecture**: Markdown on disk = source of truth, SQLite/Postgres = derived search index (FTS5/tsvector + optional vector embeddings); custom markdown-it plugins parse `[category] content` observations and `relation_type [[Target]]` relations; multi-strategy resolution (permalink → title → FTS fallback); graph traversal via `build_context`; forward references; stable permalinks; no decay |
| **obsidian-mind** | `breferrari/obsidian-mind` | 开源 | ~1000 (229 forks) | Vault 模板给 coding agents；目录结构设计参考 |
| **AMS Obsidian Plugin** | `plundrpunk/ams-obsidian-plugin` | 开源 | 4 | AI agent memory search/capture/graph sync 插件实现 |
| **Anamnesis** | `Chepech/anamnesis` | 开源 | 小 | Notes → vector store → MCP 暴露给 agent |
| **obsidian-mcp-server** | `cyanheads/obsidian-mcp-server` | 开源 | 中 | MCP bridge 实现：怎么让 AI agent 读写 Obsidian vault |
| **vault-operator** | `pssah4/vault-operator` | 开源 | 新 | "Agentic AI operating layer for vault" — 插件发现 + 统一记忆 |

### 1.5 MCP + Agent Integration 方向

| 项目 | Repo | License | Stars | 重点参考内容 |
|------|------|---------|-------|-------------|
| **mcp-mem0** | `coleam00/mcp-mem0` | 开源 | 558 | **Thin MCP wrapper** (~230 LOC) over mem0ai library; Supabase/PG + pgvector; LLM fact extraction delegated entirely to mem0; semantic search (limit 3) or paginated full retrieval; single hardcoded user ID; no lifecycle/decay/delete; **示范了 MCP memory 的最简实现** |
| **OpenClaw Mem0 Plugin** | `tensakulabs/openclaw-mem0` | 开源 | 小 | Self-hosted memory plugin for OpenClaw agents |

### 1.6 第三方复现 / Demo

| 项目 | Repo | 说明 |
|------|------|------|
| **MAGMA Demo** | `nishtobehonest/magma-agentic-memory-demo` | Streamlit demo of MAGMA multi-graph architecture — 非官方但能看架构 |
| **MAGMA PersonalAssistant** | `lty931112/PersonalAssistant` | "Reask Query Loop + MAGMA Multi-Graph Memory + Gateway" |
| **Generative Agents (Ollama)** | `daddy-gier/SMALLVILLE-OLLAMA` | Stanford Generative Agents patched for local Ollama |

---

## 二、可访问但有版权限制（只参考思路，不照抄代码）

| 项目 | 访问方式 | 重点参考内容 | 注意事项 |
|------|----------|-------------|----------|
| **Amazon Quick Desktop** | Alex 实习期间可访问源码 | ★ KG 系统实现、learned_context 注入逻辑、memory optimizer（何时写/何时读决策）、recall_memories 检索实现、prompt 冻结机制 | Copyright content，不可复制代码，只可参考架构思路和经验教训 |
| **Amazon Bedrock AgentCore Memory** | Alex 尽量找到源码/SDK | ★ 4 种 built-in strategy 实现（Semantic/UserPreference/Summary/Episodic）、Consolidation pipeline、Episodic Reflection 三阶段、Namespace 分层 | 同上；SDK 部分公开：`aws/bedrock-agentcore-sdk-python` |
| **Claude Code 记忆系统** | Alex 已下载（泄露版） | ★ Proactive injection 决策逻辑、memory extraction prompt 设计、conversation_search / recent_chats 实现、userMemories 管理 | 泄露版本，学术研究参考可用，不公开引用代码 |

---

## 三、确认无开源代码（从论文描述自行实现）

| 项目 | 论文 ID | 需要自己实现什么 | 复杂度 |
|------|---------|-----------------|--------|
| **FadeMem** | arxiv 2601.18642 | Adaptive exponential decay function: `score = recency × importance × relevance × frequency` | 低 — 一个函数 |
| **MAGMA（官方）** | arxiv 2601.03236 | Dual-stream: Fast Path (zero LLM, sub-second) + Slow Path (async 2-hop neighborhood LLM analysis) | 中 — 架构清晰，有 demo 参考 |
| **SCM (Sleep Consolidation)** | arxiv 2604.20943 | NREM phase (strengthen associations) + REM phase (novel associations + forgetting) | 中 — 概念映射明确 |
| **PASK/IntentFlow** | arxiv 2604.08000 | Streaming demand detection: `<silent>` / `<fast_intervention>` / `<full_assistance>` + hierarchical memory under ≤1s constraint | 中-高 — 但有 Claude Code 做参考 |
| **ProMem** | arxiv 2601.04463 | Iterative self-questioning: feed-forward → semantic matching → recurrent verification | 中 |
| **HiMem** | arxiv 2601.06377 | Episode↔Note dual-layer + Topic-Aware Event-Surprise segmentation + conflict-aware reconsolidation | 中 |
| **EverMemOS** | arxiv 2601.02163 | Engram lifecycle: Episodic Trace → Semantic Consolidation → Reconstructive Recollection | 中 |

---

## 四、AMF 各组件 → 对应参考源

| AMF 组件 | 主要参考（开源）| 补充参考（闭源/论文）| 备注 |
|----------|----------------|---------------------|------|
| **① State Machine** | ❌ 无参考（我们是 first）| EverMemOS lifecycle + Engram 二态模型（概念层面）| Paper 1 的核心 contribution |
| **② Write Semantics Router** | Mem0 pipeline + Hindsight conflict resolution | HiMem 分类 (independent/extendable/contradictory) | classify incoming → operation type |
| **③ Vector Index** | HippoRAG + LightRAG | — | local embeddings + graph-augmented |
| **④ Graph Construction** | GAAMA + Microsoft GraphRAG | — | entity extraction → relation → PPR |
| **⑤ Proactive Retrieval** | — | Claude Code 泄露版 + Quick Desktop | 消息到达时 injection 决策 |
| **⑥ Multi-signal Scorer** | Hindsight (cross-encoder) | MemTier 论文 (6-signal formula) | 6 信号融合 |
| **⑦ Temporal Decay** | CortexGraph (Ebbinghaus) + Generative Agents (recency) | FadeMem (adaptive, 从论文实现) | decay function |
| **⑧ Dual-stream** | — | MAGMA demo + 论文描述 | fast append + async consolidation |
| **⑨ Consolidation** | GAAMA (reflection) + Hindsight (merge) | AgentCore Episodic Reflection | 异步合成 |
| **⑩ MCP Server** | Basic Memory + mcp-mem0 | — | 暴露给外部 agent |
| **⑪ Obsidian Plugin** | Basic Memory + AMS plugin + vault-operator | — | frontmatter 读写 + graph view 增强 |
| **⑫ Storage Layer** | Basic Memory (Markdown + SQLite) + CortexGraph | — | .md + .amf/index.db |

---

## 五、优先级排序（按实现顺序）

| Phase | 需要读的代码 | 目的 |
|-------|-------------|------|
| **Phase 1 (Foundation)** | Basic Memory (架构), CortexGraph (storage format) | 搭骨架 |
| **Phase 2 (Lifecycle)** | EverMemOS (概念), Generative Agents (reflection), CortexGraph (decay) | 实现状态机 + decay |
| **Phase 3 (Retrieval)** | GAAMA (graph+PPR), HippoRAG (entity linking), Hindsight (cross-encoder) | 实现检索引擎 |
| **Phase 4 (UI)** | Basic Memory Obsidian 集成, AMS plugin | 实现 Obsidian 前端 |
| **Experiment** | Mem0 (baseline), Letta (baseline), MemOS (baseline) | 搭建对比实验 |

---

## 六、AgentCore Memory SDK（公开部分）

```
GitHub repos:
- aws/bedrock-agentcore-sdk-python     ← Python SDK，看 API 设计
- aws/bedrock-agentcore-starter-toolkit ← 快速上手模板

Docs:
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/episodic-memory-strategy.html
- https://strandsagents.com/latest/user-guide/concepts/memory/bedrock-agentcore/

Blog:
- https://aws.amazon.com/blogs/machine-learning/building-smarter-ai-agents-agentcore-long-term-memory-deep-dive/
```

---

---

## 七、12-System Analysis Summary（2026-05-20, post deep-dive）

Based on cloning and analyzing all 12 repos' source code. Full per-repo reports in `reference-repo/{name}/MEMORY_ANALYSIS.md`, synthesis in `reference-repo/SYNTHESIS.md`.

### Key Findings

| Finding | Data | Implication for AMF |
|---------|------|-------------------|
| **Decay/lifecycle extremely rare** | Only 2/12 (CortexGraph, MemoryOS) | Triple-validates research gap; Paper 1 contribution is real |
| **Proactive injection nearly absent** | Only 1/12 (CortexGraph, via spaced repetition) | Validates AMF's proactive gateway as novel contribution |
| **Graph support common but shallow** | 9/12 have graphs, but only for retrieval augmentation | AMF's graph for lifecycle decisions (promotion, consolidation) is novel |
| **LLM-at-write-time dominant** | 10/12 use LLMs during write | AMF must budget for this cost; consider GAAMA's GEL as alternative |
| **Mem0 V3 went ADD-only** | Removed LLM-decides-CRUD, now hash dedup only | Validates "less is more" / Hermes philosophy; AMF can adopt |
| **GAAMA's Graph Edit Learning** | Self-healing KG when retrieval fails (patches knowledge gaps) | AMF should consider GEL for its consolidation phase |

### Closest Prior Art Ranking (for AMF lifecycle contribution)

1. **★★★ CortexGraph** — power-law decay + promote/forget thresholds + consolidation + spaced-repetition injection. **Differentiator: continuous decay vs AMF's discrete states.**
2. **★★ MemoryOS** — heat-based decay + LFU eviction + three tiers. **Differentiator: no explicit state transitions, no graph, no proactive injection.**
3. **★ Letta** — three-tier (core/archival/recall) + sleeptime agents. **Differentiator: no decay at all, but "core memory = always in context" is a form of tiering.**
4. **★ Hindsight** — recency-weighted scoring + consolidation. **Differentiator: implicit decay (older = lower rank) but no lifecycle states.**

*Tags: #amf #reference #source-code #open-source #architecture*

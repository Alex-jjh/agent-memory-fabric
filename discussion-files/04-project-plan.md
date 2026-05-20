# Agent Memory Project — 双轨计划（工程 + 论文）
*Created: 2026-05-18 | Status: Draft for discussion*

---

## 决策记录（2026-05-20 确认）

### 项目正式命名：Agent Memory Fabric (AMF)
### Paper 1 标题：Let Agents Forget: A Lifecycle State Machine for Memory Management in LLM Agents
### 策略：Paper 做 niche ablation（state machine），开源做完整方案

### Repo 结构（三仓分离）：
```
├── agent-memory-fabric/          ← 开源产品（面向用户）
│   ├── core/                     Python 核心引擎
│   ├── obsidian-plugin/          TypeScript Obsidian 插件
│   ├── docs/                     用户文档
│   └── LICENSE (MIT/Apache 2.0)
│
├── amf-experiments/              ← 实验平台（面向研究者）
│   ├── baselines/                对比方案
│   ├── ablations/                消融实验
│   ├── datasets/                 LoCoMo 等处理脚本
│   └── results/                  实验结果 + 统计分析
│
└── let-agents-forget-paper/      ← 论文 LaTeX + figures
```

### 多篇论文潜力：

| # | Niche / Angle | Venue Target | 谁主导 |
|---|---|---|---|
| Paper 1 | State Machine lifecycle ablation | CHI 2027 LBW / NeurIPS Workshop | Alex |
| Paper 2 | Proactive Retrieval Gateway (systems) | IUI 2028 / UIST | Alex |
| Paper 3 | Memory Transparency & User Trust (HCI) | CHI 2028 / CSCW | Alex + Brennan 学生? |
| Paper 4 | Write Semantics Taxonomy (formalization) | ACL Findings / EMNLP | Alex |
| Paper 5 | Full AMF System Paper (if traction) | SIGCHI / AAAI | Alex + collaborators |
| Paper 6 | Real-world Write-Read Interaction (empirical) | CSCW / CHI | Alex |

### 与 Brennan 学生的合作可能：
- Brennan 有学生做 UI/HCI 方向
- Paper 3（Memory Transparency UI + Trust study）可以是联合项目
- Alex 做系统侧（AMF core + lifecycle visualization），Brennan 学生做 user study design + 数据采集
- 双方都有 contribution：Alex = system + formalization，学生 = HCI evaluation + trust instrument

### 时间线（final）：
```
2026.06-08  和 Brennan 确认方向 + 读文献 + 系统 design
2026.09     FYP 正式开始 + agent-memory-fabric/ Phase 1
2026.10     Phase 2 (lifecycle engine) + 搭建 amf-experiments/
2026.11-12  跑 ablation 实验 + Paper 1 写作
2027.01     投 CHI 2027 LBW + Phase 3 (retrieval)
2027.02-03  Phase 4 (UI) + user study（如果做 Paper 3）
2027.04-05  FYP 答辩 + 开源正式发布
2027.05+    Paper 2/3 继续推进
```

---

### Alex 的 meta observation（2026-05-20）：

> "你不知道什么时候该去编辑知识图谱——这本身也是我们的 research 话题。"

这是一个极好的 recursive observation：我们在研究 agent memory 的 write decision problem，同时我们自己的 KG 也面临同样的问题。AMF 如果做出来，第一个 dogfood 测试对象就是自己。

## 补充：AgentCore Memory 对比分析 & Agent Memory Fabric 定位

### 项目正式命名：Agent Memory Fabric (AMF)

"Fabric" 暗示多种异构材料编织成统一体，与 "data fabric"（统一异构数据源的治理层）有类比。

### AgentCore Memory vs AMF 核心异同

**相同理念**：
- 都认同"不是记更多，而是更聪明地整合"
- 都做短期→长期异步提炼（AgentCore 20-40s async extraction ≈ MAGMA dual-stream）
- 都有多种记忆策略/类型
- 都做语义去重（Consolidation）
- 都有 Reflection/Synthesize

**AMF 的独特点**（AgentCore 没有）：
1. **Lifecycle State Machine** — AgentCore 记忆只增不减（靠去重控制体积）；AMF 有 expire/archive
2. **Proactive Retrieval** — AgentCore reactive（query 时搜 ~200ms）；AMF 消息到达时预判（<100ms）
3. **Knowledge Graph** — AgentCore 纯文本/向量；AMF 用 graph 做检索路径先验
4. **Temporal Decay / Forgetting** — AgentCore 无主动遗忘；AMF 有 Ebbinghaus/Weibull
5. **User Transparency & Control** — AgentCore 是 developer-facing API；AMF 是 user-facing
6. **Local-first / Readable** — AgentCore 云托管黑箱；AMF 是 Markdown + Obsidian-compatible

**AgentCore 可借鉴的**：
- Episodic Memory 三阶段（Extraction → Consolidation → Reflection）很优雅
- Namespace 分层路径格式清晰
- Built-in → Override → Self-managed 三级渐进定制是好 DX
- top_k + relevance_score 简单有效

**核心定位差异**：
- AgentCore = 成熟的**工程实现**（解决 infra 问题）
- AMF = 更完整的**设计理论 + 开源实现**（解决 what/when/how/who-controls）

**AgentCore 标题说"学会忘记"，实际做的是"学会不重复记"——这不是同一件事。**
真正的"忘记"需要 lifecycle state machine + temporal decay + explicit expiration。

---

## 补充：Paper 策略 — Niche 切入 vs 整体方案

### 问题：AMF 太大，confounding 太多，怎么做假设检验？

整个 AMF 包含 10 个组件 × 4 层。如果做 A/B test "AMF vs baseline"：
- 到底是哪个组件贡献了效果？不清楚
- Confounding: proactive retrieval 和 state machine 同时开启，分不清各自贡献
- Reviewer 会问："你的改进来自哪里？"

### 策略：Paper 做单一 niche ablation，开源做整体方案

```
Paper (学术)                    Open Source (工程)
─────────────────               ─────────────────────
单变量控制实验                   完整 AMF 框架
isolate 一个创新点              所有组件集成
清晰的假设检验                   商业级可用性
可复现、可 benchmark            生态 + 社区 + 用户
```

### 最适合做 Paper 的 niche 方向（从 confound 最少到最多排序）

| Rank | Niche | 假设 | 实验设计 | Confound 程度 |
|------|-------|------|----------|--------------|
| ★★★★★ | **State Machine (lifecycle)** | "有 lifecycle state 的记忆系统在长期交互中 retrieval precision 更高" | 同一 baseline 有/无 state machine 的 ablation，在 LoCoMo 上测 | 最低 — 单一变量 |
| ★★★★ | **Proactive vs Reactive Retrieval** | "消息到达时注入 vs agent 自己搜，哪个在 extended conversation 中准确率衰退更少" | PASK 已有类似实验框架，可 replicate + extend | 低 — 但需控制注入量 |
| ★★★★ | **Write Semantics (Replace/Append/Synthesize)** | "区分 write operation type 是否减少记忆 noise 和冲突" | 对比 stateless write vs typed write，测 contradiction rate + retrieval precision | 低 — 但需定义 ground truth |
| ★★★ | **Memory Transparency UI + Trust** | "用户看到 lifecycle visualization 后 trust 和 control 是否提升" | Within-subjects A/B (transparent vs opaque), trust scale + think-aloud | 中 — 主观 measure |
| ★★ | **Full AMF vs Flat Memory** | "完整 AMF 比 flat vector store 好多少" | 全系统对比 | 高 — 分不清贡献 |

### 我的建议：Paper 1 做 State Machine ablation

理由：
1. **最 niche** — 单一变量，控制实验最干净
2. **文献确认空白** — "no formal state machine specification" 是原文确认的 gap
3. **12-system survey triple-confirms gap** — 只有 CortexGraph 有 decay，但无离散状态机；MemoryOS 有 heat decay 但无显式状态；其余 10/12 完全没有 lifecycle
4. **实验可行** — 在 LoCoMo 上跑有/无 state machine 的 ablation，不需要完整 AMF
5. **独立于工程进度** — 可以用简化版 prototype 做实验，不需要 Phase 3-4
6. **Story 清晰** — "We take the dominant industrial memory pattern (Claude Code's proactive + dedup extraction) and ask: what happens when you add a formal lifecycle state machine?"
7. **真实 baseline** — Control = Claude Code-like clone（4 types + Sonnet ranker + forked extraction + freshness caveat only），Treatment = same + state machine transitions
8. **双重对话** — 和 AgentCore（"learn to forget" but no forgetting）+ CortexGraph（continuous decay but no discrete states）都形成对话

### Paper 1 实验设计（Updated per doc-09 pivot）

| Condition | Memory schema | Recall | Extraction | Lifecycle |
|---|---|---|---|---|
| **Control (Claude Code clone)** | 4 types + frontmatter | Sonnet ranker (proactive prefetch) | Forked agent, per-turn, dedup via manifest | Freshness caveat only (binary: ≤1d / ≥2d) |
| **Treatment (+ state machine)** | + `state` field in frontmatter | Same ranker + state-aware filter (exclude Expired/Archived from warm tier) | Same fork + state transition predicates fire post-extraction | Active→Decided→Archived→Expired |

**为什么这个 baseline 更强**：
- 不是 strawman flat memory，是真实部署系统的精确克隆
- Claude Code 的 proactive + dedup 已经很好，证明 lifecycle 在这之上还能有增益
- 复现性：Claude Code 源码在手，可以精确控制对照组
- CortexGraph 作为 additional baseline：continuous decay vs discrete states 的对比

### Paper 2 可以做 Proactive Retrieval 或 Transparency (HCI)

两条路都好走：
- Proactive = 偏 systems，可以跑 benchmark
- Transparency = 偏 HCI，做 user study，Brennan 最对口

### 开源项目则不需要 isolate — 直接做完整 AMF

开源项目不需要证明"哪个组件有效"，只需要证明"整体好用"。用户不关心 ablation，关心的是：
- 装上能跑吗？
- 比 Basic Memory 好在哪？（lifecycle + decay + proactive = 直观可感知的差异）
- 和我的 Obsidian vault 兼容吗？

---

## 补充：Obsidian 生态调研 & 插件 vs 独立产品策略

### 现有竞品 star 数据（2026-05-18）

| 项目 | Stars | 定位 | 有什么 | 缺什么 |
|------|-------|------|--------|--------|
| **Basic Memory** | ~1,000+ | Python core + Obsidian 可视化 | semantic graph, MCP, local markdown | 无 lifecycle/decay/proactive |
| **obsidian-mind** | ~1,000+ (229 forks) | vault 模板给 coding agents | 目录结构 + Obsidian bases | 不是插件、无自动化 |
| **CortexGraph** | 小 | Temporal memory + Ebbinghaus | decay + local + Obsidian-compatible | 无 graph/write semantics |
| **vault-operator** | 新 (Feb 2026) | Agentic AI layer for vault | 插件发现 + 统一记忆 | 极早期 |
| **ams-obsidian-plugin** | 4 | AI agent memory search/capture | graph sync | 极早期 |
| **anamnesis** | 新 (Apr 2026) | notes → vector → MCP | RAG 索引 | 只做了 RAG |
| **obsidian-mcp-server** | 中等 | MCP bridge for Obsidian | 工具层 | 不是 memory system |

**结论：最火的 ~1000 stars，赛道没有 dominant player，无人做到完整度。**

### Obsidian 插件技术架构

```
- TypeScript 编写
- 运行在 Obsidian Electron 环境（desktop 有 Node.js 权限）
- 通过 Obsidian API：读写文件、解析 wikilinks/frontmatter、注册 views/commands
- community plugin marketplace 分发
- 限制：不能改核心 UI、mobile 无 Node.js、无官方 backend 集成
```

### 决策：做分层架构（两者都做）

```
┌──── Obsidian Plugin (UI layer) ────────────────────────────────────┐
│  • Lifecycle state badges on notes (frontmatter 读取)               │
│  • Graph view color-coding by state (Active=亮色, Archived=暗色)   │
│  • Memory dashboard panel (hot/warm/cold 统计)                      │
│  • User controls: pin, archive, expire, force-refresh               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ MCP / local REST API
┌──────────────────────────▼──────────────────────────────────────────┐
│   Core Memory Engine (独立 Python package)   ← 真正的核心产品      │
│  • State machine logic (transition predicates)                      │
│  • Write semantics router (classify → operation type)               │
│  • Multi-signal scorer (6 signals)                                  │
│  • Vector index (local embeddings) + BM25                           │
│  • Dual-stream (fast path + async consolidation)                    │
│  • Proactive retrieval gateway                                      │
│  • MCP server 暴露给任意 AI agent                                   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ reads/writes
┌──────────────────────────▼──────────────────────────────────────────┐
│   Storage Layer (Obsidian-compatible)                               │
│  • .md files with frontmatter (state, created, modified, decay...)  │
│  • [[wikilinks]] = graph edges                                      │
│  • SQLite sidecar (.memory.db) for metadata/vectors/scores          │
└─────────────────────────────────────────────────────────────────────┘
```

**为什么分层**：
- Core engine 独立 = 适用于任何 AI agent（Claude Code、Quick、Cursor、自定义）
- Obsidian plugin = 给 150 万用户免费 UI frontend
- 以后可加 VS Code 插件、Web UI、CLI
- Basic Memory 也是这个模式（Python core + Obsidian view），验证了可行性

**vs 纯插件的优势**：
- 不受 Obsidian API 限制
- 可以跑后台进程（async consolidation）
- 可以做 proactive retrieval（需要 server 常驻）
- 可以独立于 Obsidian 使用（有些人不用 Obsidian）

**vs 纯独立产品的优势**：
- 不需要自己做编辑器 / UI
- 直接获得 Obsidian 的 graph view / search / linking
- 用户获取成本低（marketplace 曝光）
- 社区生态（Obsidian Discord 活跃度极高）

---

## 总体判断

这个项目天然适合**双轨并行**：
- **工程轨**：做一个开源 memory framework → 产品影响力
- **论文轨**：formalization + evaluation + user study → 学术 credit

两条轨不冲突，反而互相支撑：论文给框架学术 legitimacy，框架给论文 real-world validation。

关键时间节点约束：
- SAT301 FYP: 2026.09 → 2027.05（答辩）
- CHI 2027 LBW: DDL ~2027.01（4 page extended abstract）
- IUI 2028 / CSCW 2027: DDL varies（full paper）
- 毕业: 2027.07
- 研究生申请: 2027 Fall（材料准备 2026.09-2027.01）

---

## Track A: 工程 / 产品计划

### A1. 产品定位

**一句话**：一个 local-first、Obsidian-compatible 的 AI agent memory framework，带 lifecycle state machine + proactive retrieval + transparency UI。

**命名建议**（可以之后再想）：
- `engram` — 神经科学术语，记忆的物理痕迹（但已被一个项目用了）
- `mnemonic` — 记忆术
- `cortex` — 大脑皮层（CortexGraph 已用）
- `synapse` — 突触（Synapse 已被用）
- `mneme` / `anamnesis` — 希腊语记忆相关
- 或者中文：`忆` / `念` 

### A2. 核心 Feature Set（MVP）

```
Phase 1 — Foundation (4 weeks)
├── Local Markdown storage (Obsidian-compatible)
├── Wikilink-based graph (auto bidirectional links)
├── Basic write operations (append, replace)
├── SQLite metadata store (node states, timestamps, scores)
└── CLI interface for testing

Phase 2 — Lifecycle Engine (4 weeks)
├── State machine per node (Active/Decided/Archived/Expired)
├── Transition predicates (time decay, conflict detection, user trigger)
├── Write semantics router (classify incoming info → operation type)
├── Dual-stream: fast append + async consolidation (background thread)
└── Ebbinghaus-inspired decay function

Phase 3 — Retrieval (4 weeks)
├── Vector index (local embeddings, e.g. sentence-transformers)
├── BM25 keyword search
├── Multi-signal scorer (semantic + graph + hierarchy + decay + frequency + intent)
├── Proactive retrieval gateway (triggered on message arrival)
└── Tiered memory output (hot/warm/cold with token budgets)

Phase 4 — User Interface (4 weeks)  
├── Obsidian plugin: lifecycle state badges on notes
├── Graph view enhancement: color-code by state, fade archived
├── Memory dashboard: what's hot/warm/cold, recent transitions
├── User controls: pin, archive, expire, force-refresh
└── "Agent is using these memories" transparency panel
```

### A3. 技术栈（初步）

| Component | Choice | 理由 |
|-----------|--------|------|
| Storage | Markdown files + SQLite sidecar | Obsidian 兼容 + 结构化 metadata |
| Graph | Wikilinks (parsed) + SQLite adjacency table | 轻量、不依赖 Neo4j |
| Vector | Local embeddings (e5-small / BGE-small) + FAISS or usearch | 本地、快、无 API 依赖 |
| Search | BM25 (rank_bm25 or sqlite-fts5) | 和 vector 互补 |
| State Machine | Python class + SQLite state column | 简单、可测试 |
| Decay | Configurable function (exponential / Weibull) | 参考 FadeMem / LiCoMemory |
| LLM Integration | MCP server (Claude/Quick/任意 client) | 标准协议，不绑定具体 agent |
| UI | Obsidian plugin (TypeScript) | 直接接入 150 万用户生态 |
| API | Python library + MCP server + REST (optional) | 多种接入方式 |

### A4. 和竞品的差异化（Updated 2026-05-20, post 12-system analysis）

```
       Lifecycle  Graph  Vector  Tiered  Proactive  Transparency  Local-first  Decay Model
       ─────────  ─────  ──────  ──────  ─────────  ────────────  ──────────  ───────────
Mem0       ❌       ⚠️      ✅      ❌       ❌          ❌            ❌          ❌ (platform-only)
CortexGr.  ✅★      ✅      ⚠️      ⚠️       ✅★         ⚠️            ✅          ✅ power-law
MemoryOS   ✅       ❌      ✅      ✅       ❌          ❌            ❌          ✅ heat+exp
Basic Mem   ❌       ✅      ✅      ❌       ❌          ✅            ✅          ❌
Letta       ❌       ❌      ✅      ✅       ⚠️          ⚠️            ❌          ❌
HippoRAG   ❌       ✅      ✅      ❌       ❌          ❌            ✅          ❌
GAAMA       ❌       ✅      ✅      ❌       ❌          ❌            ✅          ❌
GraphRAG    ❌       ✅      ✅      ❌       ❌          ❌            ❌          ❌
Hindsight   ⚠️       ✅      ✅      ❌       ❌          ❌            ❌          recency-weight
Ours       ✅       ✅      ✅      ✅       ✅          ✅            ✅          ✅ Ebbinghaus/Weibull
```

**★ CortexGraph = closest prior art for lifecycle.** Key differentiator:
- CortexGraph uses **continuous decay** (power-law score that fades to 0) — forgetting is implicit
- AMF uses **discrete lifecycle states** (Active→Decided→Archived→Expired) — forgetting is explicit state transitions with transition predicates
- CortexGraph has proactive injection via spaced repetition (fading memories blended into search results)
- AMF has proactive injection via intent-aware gateway (<100ms decision before agent sees message)

**Gap triple-confirmed**: Only 2/12 systems (CortexGraph + MemoryOS) implement any decay. Only 1/12 (CortexGraph) does proactive injection. **Zero** implement discrete lifecycle state machines.

**唯一一个全覆盖的方案，且唯一一个把 lifecycle 做成显式状态机的。**

### A5. 开源策略

- **License**: MIT 或 Apache 2.0（最大传播）
- **首发**：GitHub + arxiv preprint + HuggingFace Daily Papers 提交
- **社区切入**：Obsidian Discord（活跃度极高）+ r/ObsidianMD + AI Twitter
- **Demo**：录一个 2 分钟视频展示 lifecycle visualization
- **时机**：和论文同步发布形成双重传播

---

## Track B: 论文计划

### B1. 论文拆分策略

我建议拆成 **2-3 篇**，按时间线出：

#### Paper 1: Formalization（快速出手，占坑）
- **Title**: "Memory Has a Lifecycle: Formalizing Write Semantics and State Transitions for LLM Agent Memory"
- **Type**: 4-page extended abstract / position paper
- **Venue**: CHI 2027 Late-Breaking Work (DDL ~Jan 2027) 或 NeurIPS 2026 Workshop
- **Content**: 
  - Write operation taxonomy (6 types) 
  - Lifecycle state machine (4 states + transition predicates)
  - Quick KG case study as motivation
  - Preliminary implementation + pilot (N=5-10)
- **Story**: "We formalize what no one has formalized; here's why it matters; here's a first implementation"
- **Effort**: 中等（formalization + pilot，不需要大规模 user study）
- **Risk**: 低（LBW acceptance rate 高）

#### Paper 2: Full System + User Study（FYP 主体）
- **Title**: "Proactive Memory with Lifecycle Transparency: A Unified Framework for Human-AI Memory Collaboration"
- **Type**: 10-12 page full paper
- **Venue**: IUI 2028 (DDL ~Oct 2027) 或 CSCW 2027 (DDL ~Jun 2027) 或 CHI 2028 (DDL ~Sep 2027)
- **Content**:
  - Complete system design (10 components × 4 layers)
  - Implementation of proactive retrieval gateway
  - Within-subjects user study (N=20-30): lifecycle-transparent vs opaque
  - Metrics: task accuracy, trust (TAI/S-TIAS), perceived control, memory correction rate
  - LoCoMo/LongMemEval benchmark evaluation
- **Story**: "We built it, users prefer it, and it performs better"
- **Effort**: 高（完整系统 + user study + dual evaluation）
- **Risk**: 中等（需要充分的 user study design）

#### Paper 3 (Optional): Empirical / ML
- **Title**: "Write Precision Matters More Than You Think: Diagnosing Memory Quality in Real-World AI Conversations"
- **Type**: 8-page empirical paper
- **Venue**: EMNLP 2027 / ACL Findings
- **Content**:
  - Replicate Diagnosing paper's 3×3 factorial on real (noisy) conversations
  - Show write strategy impact is amplified in production (>3-8pt)
  - Introduce state-machine-aware write strategy as a new condition
  - Ablation: which lifecycle transitions matter most
- **Story**: "The benchmark finding that write doesn't matter is misleading for production"
- **Effort**: 中（需要真实数据 + 实验，但不需 user study）
- **Risk**: 中（需要 convincing 数据）

### B2. 时间线

```
2026.06-08  和 Brennan 确定方向 + 开始读文献 + 设计系统
2026.09     FYP 正式开始 + 同时启动工程 Phase 1
2026.10     Phase 1 完成 + Paper 1 开始写作
2026.11     Phase 2 完成 (lifecycle engine)
2026.12     Phase 3 完成 (retrieval) + Paper 1 投稿 CHI LBW
2027.01     Phase 4 开始 (UI) + CHI LBW DDL
2027.02     User study design + ethics approval
2027.03     User study 数据收集 (2-3 weeks)
2027.04     Data analysis + Paper 2 写作
2027.05     FYP 答辩 + Paper 2 投稿 (IUI 2028 或 CSCW)
2027.05-06  开源发布 (GitHub + Obsidian plugin)
```

### B3. Author 配置

- Paper 1: **Alex Jiang**, Brennan Jones
- Paper 2: **Alex Jiang**, Brennan Jones (+ 可能找一个 systems 方向的共同导师?)
- Paper 3: **Alex Jiang**, [co-author TBD if needed]

---

## Track C: 我的见解 — 两条轨的协同效应

### 为什么双轨比单轨好

1. **论文给开源 legitimacy**：有论文的开源项目被引用、被信任、被 star
2. **开源给论文 impact**：reviewers 看到有真实用户在用 = "practical contribution"
3. **User study 和开源 beta 可以合并**：Obsidian plugin 的早期用户 = user study participants
4. **研究生申请加分**：CHI/IUI publication + popular open-source = 顶级 material

### 风险管理

| 风险 | 缓解 |
|------|------|
| FYP 做不完 | Phase 1-2 就足够 FYP；Phase 3-4 是 bonus |
| Paper 被拒 | CHI LBW 是 safety net（高 acceptance）；Paper 2 有多个 venue 选择 |
| 开源没人用 | 论文本身就是 FYP deliverable，开源是 upside |
| 和 Brennan 方向不 match | 准备了从纯 HCI 到 hybrid 多个 option |
| 时间不够写论文 | Paper 1 只有 4 页，可以在 FYP 前期完成 |

### 研究生申请中的 positioning

- **CMU MISM-BIDA**: 展示 systems thinking + data-driven evaluation
- **UC Berkeley MIMS**: 展示 HCI + information management + user study 能力
- 有 CHI publication（哪怕 LBW）+ popular GitHub repo = 极强的 application differentiator

---

## 我的最终建议

**先做 Paper 1**。原因：
1. 只需要 formalization + case study + pilot（你现在就能开始写）
2. 不依赖工程完成度
3. CHI LBW 的 Jan 2027 DDL 给了你 7 个月
4. 一旦 accepted，为 Paper 2 和开源都铺好了路
5. 写作过程本身会帮你 clarify 系统设计

**工程和 Paper 1 可以并行**：formalization 指导实现，实现 validate formalization。

---

*Next actions:*
- [ ] 和 Brennan 讨论确认大方向
- [ ] 检查 CHI 2027 LBW 的具体 DDL 和 format 要求
- [ ] 决定项目命名
- [ ] 设置 GitHub repo（private initially, public at launch）
- [ ] 开始写 Paper 1 的 Related Work section（从今晚的 research 直接转化）

*Tags: #project-plan #agent-memory #fyp #paper #engineering #open-source*

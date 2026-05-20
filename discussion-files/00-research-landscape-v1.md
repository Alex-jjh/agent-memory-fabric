# Agent Memory 研究全景 & Deep Research Prompt

## 🔬 当前研究格局概览

你的直觉踩中了当前研究的几个热点交叉区。以下是我整理的关键文献和方向：

---

## 一、学术界现状：关键工作梳理

### 1. 分层记忆架构（Hierarchical Memory）— 最活跃方向

| 论文 | 时间 | 核心思路 |
|------|------|----------|
| **H-MEM** (Hierarchical Memory for High-Efficiency Long-Term Reasoning) | 2025 | 多层语义抽象 + 位置索引编码 → 逐层路由检索，避免穷举相似度搜索 |
| **LiCoMemory** + CogniGraph | 2025.11 → 2026 | 层次图结构做语义索引 + 实时 agentic memory controller → 跑赢 LoCoMo / LongMemEval |
| **HiMem** (Hierarchical Long-Term Memory) | 2026.01 | 受认知科学启发，支持构建→检索→动态更新的完整生命周期 |
| **CogMem** (Cognitive Memory Architecture) | 2025 | 三层：LTM（跨 session 策略）→ Direct Access（session 级笔记）→ Focus of Attention（每 turn 动态重构） |

**💡 和你想法的关联**：这些工作验证了 Hermes 的「冷热分层」理念，但把它推到了 3-4 层，并加入了**动态路由**和**时序维度**。

---

### 2. 图增强记忆（Graph-Augmented Memory）— 你在想的方向

| 论文 | 时间 | 核心思路 |
|------|------|----------|
| **GAAMA** (Graph Augmented Associative Memory for Agents) | 2026.03 | 4 种 node type + 5 种 edge type 的层次 KG；3 步 pipeline：原始保存 → 原子事实提取 → 高阶反思合成 |
| **Multi-Graph Agentic Memory** | 2025.12 | 指出单一 memory store 纠缠了 temporal/causal/entity 信息 → 用多图解耦 |
| **Graph-Augmented LLM Agents Survey** | 2025 | 图在 planning、long-term memory、tool management、multi-agent coordination 四个方面的增强 |

**💡 和你想法的关联**：Quick 已经有了 KG（node + edge）+ RAG indexing，这本质上就是 GAAMA 所说的「graph + vector」混合体。关键差异在于检索策略。

---

### 3. 主动/预判式记忆检索（Proactive Retrieval）— 你的「天马行空」想法

| 论文 | 时间 | 核心思路 |
|------|------|----------|
| **ProMem** (Proactive Memory Extraction) | 2026.01 | 不做被动摘要，用 self-questioning 循环主动探测对话历史、修正遗漏 |
| **Proactive Retrieval from Memory and Skills** | 2026.04 | ❗ 直接对标你的想法：现有方法只在 task 开始或 step 完成后被动触发检索 → 提出在执行过程中**主动预判**需要什么记忆 |
| **Intent-Aware Proactive Agents with Long-Term Memory** | 2026.04 | 从 ongoing context 推断用户**潜在需求** → 在 user memory 中定位 → 在延迟约束下主动介入 |
| **Memory Augmented Routing** | 2026.01 | 跨模型记忆注入 + confidence-based routing → 证明「memory 注入让小模型达到大模型质量」 |

**💡 这验证了你的想法**：在用户发消息时就做语义处理 + 记忆召回 → 注入 prompt，而不是等 agent 自己决定去不去找。学术上这叫 **anticipatory/proactive retrieval**，2026 年才刚开始被正式研究。

---

### 4. 记忆操作系统（Memory OS）— 系统级抽象

| 论文 | 时间 | 核心思路 |
|------|------|----------|
| **MemOS** (Memory Operating System) | 2025.05 | 把 memory 提升为 LLM 的一等操作系统资源；统一管理 parametric / activation / plaintext 三种记忆类型；Token 减少 61%，时序推理提升 159% |
| **Self-Organizing Memory OS** | 2026.01 | 长 horizon 推理场景下的自组织记忆结构 |

---

### 5. 检索 vs 利用的诊断（Retrieval vs Utilization）

| 论文 | 时间 | 核心思路 |
|------|------|----------|
| **ActMem** (Bridging Retrieval and Reasoning) | 2026.03 | 检索到了不代表能用好 → 把 memory 和 reasoning 桥接起来 |
| **Diagnosing Retrieval vs. Utilization Bottlenecks** | 2026.03 | 写入策略 vs 检索策略，到底哪个是瓶颈？实验证明两者都重要但机制完全不同 |
| **Dynamic Retrieval Scheduling** | 2026.02 | 压缩损失 vs 原始文本开销的 fundamental trade-off → 动态调度检索时机 |

---

### 6. 安全维度（Memory Attack）

- **MINJA** (Memory Injection Attack): 95% injection 成功率，70% 攻击成功率
- **SuperLocalMemory**: Local-first + Bayesian trust scoring 防御方案
- 视频里提到的 memory poisoning 确实是 2025-2026 的热门安全话题

---

## 二、Quick 现有架构 vs 研究前沿的映射

```
Quick 现有                          学术对应
─────────────────────────────────────────────────────────
learned_context (自动注入)    ≈     热层 / always-injected prompt memory
recall_memories (agent 调用)  ≈     温层 / on-demand retrieval (Claude 模式)
KG (node + edge)              ≈     GAAMA 的 hierarchical graph
RAG indexing (vector+BM25)    ≈     冷层 / semantic + keyword 混合检索
file hierarchy (folders)      ≈     Hermes 的 skills 组织 / spatial indexing
```

**Gap（你的洞察）**：Quick 目前的 `learned_context` 注入是基于规则/相关度静态筛选的。缺少的是：
1. **用户消息到达时的实时语义处理 → 动态决定注入什么**（proactive retrieval）
2. **Graph traversal 驱动的关联记忆召回**（不只是 embedding 相似度，而是沿 edge 走）
3. **时序衰减 + 重要性加权**（不是所有记忆都平等）

---

## 三、你的想法为什么有研究价值

你提出的「Graph + Vector + Folder Hierarchy + 冷热分层 + 用户消息时即时语义处理」的组合，在学术上对应一个**尚未被完整解决的系统设计问题**：

> **如何将多种异构记忆表征（graph topology、vector embedding、hierarchical namespace、temporal decay）统一到一个检索决策框架中，并在用户发消息的瞬间（< 100ms latency）完成主动召回？**

这比任何单篇论文涵盖的都更系统化。现有工作各自解决了一块：
- H-MEM / LiCoMemory 做了分层
- GAAMA 做了图增强
- ProMem / Intent-Aware 做了主动检索
- MemOS 做了系统级抽象

**但没有人把它们拼成一个完整的 memory fabric。**

---

## 四、Deep Research Prompt

以下是一个结构化的 deep research prompt，你可以直接喂给 deep research 工具或作为你自己的 research proposal 起点：

---

### 📋 Deep Research Prompt

**Title**: Unified Heterogeneous Memory Architecture for Autonomous AI Agents: Integrating Graph Topology, Vector Semantics, Hierarchical Namespace, and Proactive Retrieval

**Research Question**:
How can we design a memory system for LLM-based agents that unifies knowledge graph (entity-relation topology), vector embeddings (semantic similarity), file/folder hierarchy (spatial organization), and temporal decay into a single retrieval decision framework — with proactive (anticipatory) recall triggered at user message arrival rather than reactive agent-initiated search?

**Sub-questions to investigate**:

1. **Architectural Patterns**: What existing architectures (GAAMA, LiCoMemory/CogniGraph, H-MEM, MemOS, CogMem) have attempted multi-modal memory integration, and what are their limitations? Specifically:
   - How does each handle the retrieval decision (what to inject into context)?
   - What latency constraints do they operate under?
   - How do they handle memory that spans multiple representation types?

2. **Proactive vs Reactive Retrieval**: 
   - What work exists on anticipatory/proactive memory retrieval (ProMem, Intent-Aware Proactive Agents, Proactive Retrieval from Memory and Skills)?
   - What are the accuracy vs latency trade-offs of pre-retrieval (at message arrival) vs on-demand retrieval (agent decides to search)?
   - How does user intent prediction quality affect downstream task performance?

3. **Graph + Vector Fusion for Retrieval**:
   - How do systems like GAAMA and Multi-Graph Agentic Memory combine graph traversal with semantic search?
   - What role does PageRank / graph centrality play in memory prioritization?
   - Can edge-weighted graph walks replace or complement vector similarity for relevance scoring?

4. **Hierarchy as Memory Organizer**:
   - How does folder/namespace hierarchy (à la Hermes skills/, OpenClaw memory/) serve as an implicit categorization system?
   - Can hierarchical topic trees serve as an index structure that reduces the search space for vector retrieval?
   - What is the relationship between file-level organization and in-graph ontology?

5. **Hot/Warm/Cold Dynamics**:
   - What are the promotion/demotion heuristics between memory tiers (Hermes, CogMem, H-MEM)?
   - How should memory "temperature" be computed? (recency × frequency × relevance × graph centrality?)
   - What is the optimal size for the "always-injected" hot tier? (Hermes says ~1,300 tokens — is this empirically validated?)

6. **Context Window as Scarce Resource**:
   - Given the "context rot" / "Darwinian cliff" effect, what is the empirical relationship between injected memory tokens and output quality?
   - How do systems like MemOS achieve 61% token reduction without quality loss?
   - What compression/summarization techniques preserve retrieval-relevant signals?

7. **Security & Privacy**:
   - How do persistent memory systems defend against memory injection attacks (MINJA, plan injection)?
   - What role does Bayesian trust scoring (SuperLocalMemory) play?
   - How to maintain contextual integrity (the privacy concern from Hermes video)?

8. **Evaluation**:
   - What benchmarks exist? (LoCoMo, LongMemEval, EvolMem)
   - How do we measure "memory helped" vs "memory hurt" in a controlled way?
   - What metrics capture the proactive retrieval value (precision@recall_time)?

**Desired Output Format**:
- Literature map organized by the 8 sub-questions above
- For each paper: architecture diagram summary, key contribution, limitation, and relevance to the unified system
- Identification of open gaps that no existing work addresses
- A proposed system architecture sketch that integrates the best ideas
- Potential experimental protocol to validate the architecture

**Key Papers to Start From**:
- GAAMA (arxiv 2603.27910)
- LiCoMemory (arxiv 2511.01448)
- Proactive Retrieval from Memory and Skills (arxiv 2604.20572)
- Intent-Aware Proactive Agents (arxiv 2604.08000)
- MemOS (arxiv 2505.22101)
- H-MEM (arxiv 2507.22925)
- Memory Augmented Routing (arxiv 2603.23013)
- ActMem (arxiv 2603.00026)
- Agentic Memory Survey (arxiv 2502.12110)
- Multi-Graph Agentic Memory (arxiv 2601.03236)
- Diagnosing Retrieval vs Utilization (arxiv 2603.02473)
- Dynamic Retrieval Scheduling (arxiv 2602.13933)
- EvolMem Benchmark (arxiv 2601.03543)

---

## 五、概念性系统架构草图：Unified Memory Fabric

把你的想法、Hermes 的设计、和学术前沿整合，我画一个概念性的 memory 系统：

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER MESSAGE ARRIVES                         │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  PROACTIVE RETRIEVAL GATEWAY                        │
│  (< 100ms budget, runs BEFORE LLM sees the message)                │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Intent       │  │ Entity       │  │ Temporal                 │  │
│  │ Classifier   │  │ Extractor    │  │ Context Resolver         │  │
│  │ (lightweight │  │ (NER/linking │  │ (what time period is     │  │
│  │  model or    │  │  against KG) │  │  relevant? session       │  │
│  │  heuristic)  │  │              │  │  history window?)        │  │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘  │
│         │                  │                       │                │
│         └──────────────────┼───────────────────────┘                │
│                            ▼                                        │
│              ┌─────────────────────────────┐                        │
│              │   RETRIEVAL DECISION ENGINE  │                        │
│              │   (multi-signal scorer)      │                        │
│              │                             │                        │
│              │   score = f(                │                        │
│              │     semantic_sim,           │  ← vector embedding    │
│              │     graph_proximity,        │  ← KG edge traversal  │
│              │     hierarchy_match,        │  ← folder/topic tree  │
│              │     temporal_decay,         │  ← recency weight     │
│              │     access_frequency,       │  ← usage count        │
│              │     intent_relevance        │  ← user intent class  │
│              │   )                         │                        │
│              └──────────────┬──────────────┘                        │
│                             │                                       │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     MEMORY TIER SYSTEM                               │
│                                                                     │
│  ┌─── HOT (always injected, ~1000-1500 tokens) ──────────────────┐ │
│  │  • Core user profile (immutable facts)                         │ │
│  │  • Active project context (what they're working on NOW)        │ │
│  │  • Standing instructions / preferences                         │ │
│  │  ★ Frozen at session start (Hermes pattern)                    │ │
│  │  ★ Writes land immediately but prompt updates at next rebuild  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─── WARM (proactively injected per-turn, ~500-2000 tokens) ────┐ │
│  │  • Retrieval Gateway 决定的 top-K memories for THIS turn       │ │
│  │  • Graph-traversal 关联记忆 (e.g., 提到人名 → 拉出关系)       │ │
│  │  • Recent session summaries (sliding window)                   │ │
│  │  ★ THIS is the novel layer — 不是 agent 自己决定要不要搜       │ │
│  │  ★ 而是 gateway 在 LLM 看到消息之前就决定了                    │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─── COLD (agent-initiated on-demand, unlimited) ───────────────┐ │
│  │  • Full session history (SQLite + FTS)                         │ │
│  │  • Knowledge graph deep traversal                              │ │
│  │  • File content (RAG indexed folders)                          │ │
│  │  • Skills / procedures library                                 │ │
│  │  ★ Agent 明确调用 tools 来检索                                  │ │
│  │  ★ Latency tolerance: seconds                                  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 六、关键设计问题 & 研究可探索点

### 6.1 Proactive Retrieval Gateway 的核心挑战

| 挑战 | 说明 | 可能方案 |
|------|------|----------|
| **延迟约束** | 必须 < 100ms，否则用户感知到卡顿 | 轻量 intent 分类器（distilled BERT 或规则 + embedding cache） |
| **精度-召回 trade-off** | 注入太多 → context rot；太少 → 丢关键信息 | 动态 token budget（简单问题少注入，复杂问题多注入） |
| **多信号融合** | 如何权衡 vector sim vs graph proximity vs recency? | 可学习的 scorer（轻量 MLP / logistic regression on features） |
| **冷启动** | 新用户没有 graph，没有 history | 渐进式建图 + 回退到纯 vector retrieval |

### 6.2 Graph 在记忆系统中的独特价值

Vector embedding 擅长「语义相似」，但有两个致命盲点：
1. **关系推理**：「Alex 的导师是 Brennan → Brennan 研究 HCI → 提到 HCI 时应该召回 Brennan 的相关 context」—— 这是 2-hop graph traversal，vector 做不到
2. **结构化过滤**：「只要和 CPT204 相关的记忆，不要 MTH202 的」—— graph 的 category/edge type 天然支持，vector 需要额外 metadata filter

Graph 的作用不是替代 vector，而是**提供检索路径的先验**：
- 先用 entity linking 确定当前对话涉及哪些 graph nodes
- 沿 edges 展开 1-2 hop 邻域
- 在邻域范围内做 vector 精排
- 这样把全量搜索变成了**局部搜索**，既快又准

### 6.3 Folder Hierarchy 作为隐式本体论

文件夹结构本身就是用户对知识的分类表达：
```
knowledge-vault/
├── daily/          → 时间轴记忆（episodic）
├── projects/       → 项目记忆（project-scoped facts）
├── courses/        → 学业记忆
└── research/       → 研究记忆
```

这个 hierarchy 可以被映射为 graph 的 topic 节点层级，实现：
- **检索范围缩窄**：用户问课程问题 → 只搜 courses/ 子图
- **记忆组织可视化**：hierarchy = 用户可理解的 graph 投影
- **显式记忆原则**：用户能直接打开文件夹看到「AI 记住了什么」（你的偏好）

### 6.4 与你的 Accessibility 研究的潜在关联

你的 AMT 框架研究 AI agent 如何适应网页障碍。Memory 系统的设计也有 accessibility 维度：
- **记忆透明度** = accessibility 的一种形式（用户能否 "access" AI 的内部状态？）
- **Hermes 的 MEMORY.md 哲学** vs **黑箱向量数据库** = 可达性的设计选择
- 如果 FYP 方向是 AI Agent，这个 memory 系统设计完全可以作为 FYP 的一个子课题

---

## 七、如果要写成 Research Proposal / FYP 方向

### 可能的 Contribution 角度：

1. **系统论文**（Systems paper）：设计 + 实现一个 unified memory fabric，在 LongMemEval / LoCoMo 上跑实验证明 proactive retrieval + graph routing 比 naive RAG 更好
2. **实证研究**（Empirical study）：在 Quick-like 系统上 A/B test proactive vs reactive retrieval，量化 context rot vs information completeness 的 trade-off
3. **框架论文**（Framework paper）：提出 memory 系统的分类学（taxonomy）和设计空间，类似于你 AMT 框架对 accessibility manipulation 的分类

### 时间线适配：
- SAT301 FYP 跨全年（2026.09 - 2027.05）
- Brennan 的 HCI 方向 + 你的 AI agent 兴趣 → memory transparency & user control 完全是 HCI 话题
- 和 INT305 Machine Learning 有交叉（learned scorer 的部分）

---

## 八、我的判断

你提出的组合（graph + vector + hierarchy + hot/cold + proactive retrieval）目前**没有任何一篇论文完整覆盖**。最接近的是：
- GAAMA 做了 graph + hierarchy，但没有 proactive retrieval
- ProMem 做了 proactive extraction，但不涉及 graph
- LiCoMemory 做了 hierarchical graph + efficient retrieval，但是 reactive 的
- MemOS 做了系统级抽象，但偏底层 infra 不涉及检索策略

这个交叉点有论文空间，尤其如果你能拿 Quick 的真实使用数据做 case study（匿名化后），会是很有说服力的系统验证。

---

*Generated: 2026-05-17*

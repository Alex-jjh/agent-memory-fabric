# 2026-05-17 Daily Log

## Agent Memory Architecture — 深度研究日

### 起因
观看了一个视频（讲解 Hermes / ChatGPT / Claude / OpenClaw 的 memory 设计），引发对 agent 记忆系统的深度思考。核心问题：如何将 graph topology、vector embedding、folder hierarchy、冷热分层、proactive retrieval 整合为一个统一的记忆架构？

---

### 核心发现

#### 1. 研究格局（2025-2026）
当前 agent memory 是最活跃的研究方向之一，但存在**关键整合缺口**：各系统各自解决了一个维度，没有人做统一整合。

| 方向 | 代表工作 | 关键贡献 |
|------|----------|----------|
| 分层记忆 | H-MEM, CogMem, LiCoMemory, HiMem | 多层抽象 + 动态路由 |
| 图增强记忆 | GAAMA, MAGMA, HAGE | entity-relation 拓扑 → 关联召回 |
| 主动/预判检索 | PASK/IntentFlow, ProactAgent, ProMem | 在 agent 处理消息前注入记忆 |
| 记忆操作系统 | MemOS | memory 作为一等系统资源 |
| 多信号融合 | MemTier, HAGE | 6 种信号组合的检索评分 |

#### 2. 最强实证发现
- **Proactive > Reactive**: PASK/IntentFlow 维持 >80% 准确率，reactive 方案随时间衰退 17+ 百分点
- **检索精度是最大瓶颈**: retrieval method 驱动 14-23pt 准确率差异 vs 写入策略仅 3-8pt（r=0.98 相关性）
- **Architecture > Weight Tuning**: MemTier PPO 学习的权重与启发式默认值精度完全相同 → 信号选择比权重调优重要
- **Graph 补充而非替代 Vector**: GAAMA 78.9% vs 纯 RAG 75.0%；graph 的价值是缩窄搜索空间
- **Hot tier 最优尺寸**: ~1,300 tokens（Hermes）; k=2 条记忆优于 k=4 或 k=8（MemTier）

#### 3. 我的独立洞察（超越报告内容）
1. **"何时不注入" 比 "注入什么" 更是 open gap** — inject vs abstain 决策在文献中几乎空白
2. **Memory Transparency 作为 HCI/Accessibility 问题** — 没有任何论文从用户视角研究 agent 记忆的可达性和可控性
3. **Memory as Interface, not Infrastructure** — 把 memory 从后端系统重构为用户与 agent 协作维护的共享空间
4. **Quick 已有架构覆盖了大部分层**，核心 gap 是缺少 <100ms 的 Proactive Retrieval Gateway

---

### 提出的系统架构：Unified Memory Fabric

```
User Message → Proactive Retrieval Gateway (<100ms)
                 ├── Intent Classifier (lightweight)
                 ├── Entity Extractor (NER → KG linking)
                 └── Temporal Context Resolver
                         ↓
               Multi-Signal Decision Engine
               score = f(semantic_sim, graph_proximity,
                         hierarchy_match, temporal_decay,
                         access_frequency, intent_relevance)
                         ↓
┌─────── HOT (~1,300 tokens, always injected, session-frozen) ───────┐
├─────── WARM (500-2000 tokens, proactively injected per-turn) ──────┤  ← 核心创新层
└─────── COLD (unlimited, agent-initiated on-demand) ─────────────────┘
```

---

### FYP (SAT301) 方向讨论

**推荐 Hybrid 方向**: 实现轻量 gateway + 设计 memory visualization/control UI + A/B user study

**Research Question 候选**:
> "Does proactive memory injection with user-facing transparency controls improve task performance AND user trust compared to opaque reactive retrieval?"

**优势**:
- 技术侧：proactive + graph-aware retrieval 实现
- HCI 侧：memory transparency 对信任的影响（Brennan 对口）
- 安全侧：透明性本身是 memory injection attack 的防御
- ML 侧：与 INT305 Machine Learning 有交叉（learned scorer）

**与现有研究的衔接**:
- AMT 框架已建立 "AI agent + web interaction" 的研究方法论
- Memory transparency 可视为 cognitive accessibility 的一个实例
- 和 ASSETS / CHI Accessibility track 主题契合

---

### Seed Papers（已整理 arxiv ID）
- PASK/IntentFlow: arxiv 2604.08000
- ProactAgent (PASK): arxiv 2604.20572
- GAAMA: arxiv 2603.27910
- LiCoMemory/CogniGraph: arxiv 2511.01448
- H-MEM: arxiv 2507.22925
- MAGMA (Multi-Graph): arxiv 2601.03236
- MemOS: arxiv 2505.22101
- MemTier: arxiv 2605.03675
- Diagnosing Retrieval vs Utilization: arxiv 2603.02473
- HiMem: arxiv 2601.06377
- CogMem: arxiv 2512.14118
- ProMem: arxiv 2601.04463
- EvolMem Benchmark: arxiv 2601.03543
- ActMem: arxiv 2603.00026
- Memory Augmented Routing: arxiv 2603.23013
- HAGE (RL edge traversal): arxiv 2605.09942 (HuggingFace)
- HyMem (Dynamic Retrieval Scheduling): arxiv 2602.13933
- MINJA (Memory Attack): arxiv 2601.05504
- SuperLocalMemory (Defense): arxiv 2603.02240

---

### 下一步
- [ ] 和 Brennan 讨论 FYP 方向（hybrid: proactive retrieval + memory transparency HCI study）
- [ ] 精读 3 篇核心论文：PASK (2604.08000), GAAMA (2603.27910), Diagnosing (2603.02473)
- [ ] 考虑是否可以用 Quick 的真实使用数据（匿名化）做 case study

---

### Write Path 深度讨论：Memory Write Semantics & 状态机模型

#### Alex 的核心洞察：Replace vs Append

记忆不是统一的 "store" 操作，而是至少分为两种基本语义：
- **Replace（状态性）**：我是谁、我住哪、项目当前进展 → 新值覆盖旧值
- **Append（事件性）**：今天学了数学、今天讨论了 memory 研究 → 累积不互斥

关键观察：一个 KG node 可能同时有两种行为：
- Node "Possible FYP Topics" 本身是一个状态 node
- 但它的演化方式是不断 append 新的探讨
- 直到某个决策时刻，状态从 `exploring` 变为 `decided`，此后变为 replace 语义

#### Quick 扩展：完整 Write Operation 分类学

| 操作类型 | 语义 | 例子 | Graph 行为 |
|----------|------|------|-----------|
| **Replace** | 新状态覆盖旧状态 | "我住上海"→"我住苏州" | 更新 node property |
| **Append** | 事件累积不互斥 | "5/17 讨论了 memory" | 创建新 edge 或子 node |
| **Synthesize** | 多事件升华为洞察 | 5次讨论 → "方向确定为 X" | 从多个 append 生成新的 replace |
| **Expire** | 时效性信息自动失效 | "今天3点开会" | TTL / auto-archive |
| **Branch** | 一个状态分裂为多可能 | "FYP 可能是 HCI 或 ML" | 一个 node 长出多个候选 edge |

#### Alex 的关键 reframe：AI "忘记" 的方式就是状态机

人的记忆大多是 append，但人会忘。AI 不会自然忘记 → **AI 的 "遗忘" 必须是显式设计的**。

状态机就是这个设计：
- 不是删除记忆（那是粗暴的）
- 而是通过 **lifecycle state transition** 改变记忆的可见性和行为：

```
Memory Node Lifecycle:

[Active/Exploring]  ← 当前被操作中
   │  write semantics: append（积累探讨）
   │  visibility: warm/hot tier（高优先召回）
   │
   ├──→ [Decided/Committed]  ← 结论已定
   │       write semantics: replace（新决策覆盖旧）
   │       visibility: hot tier（核心事实）
   │
   ├──→ [Archived/Historical]  ← 仍存在但不活跃
   │       write semantics: read-only（不再写入）
   │       visibility: cold tier（只有 agent 主动搜才看到）
   │       ≈ 人的 "忘记但能想起来"
   │
   └──→ [Expired/Invalidated]  ← 不再有效
           write semantics: 不接受新写入
           visibility: 不参与检索（但可审计）
           ≈ 人的 "完全忘记"
```

**状态转换触发器：**
- `Active → Decided`：用户明确决策 / 外部事件确认
- `Active → Archived`：时间衰减 + 无新交互
- `Decided → Archived`：被新的 Decided 替代
- `Any → Expired`：TTL 到期 / 用户删除 / 矛盾检测

#### 为什么这个 formalization 有价值

1. **现有系统没有这个抽象**：GAAMA/MemOS/H-MEM 都把所有记忆当作同质的 — 没有 per-node lifecycle
2. **解决了 "何时不注入" 问题**：Archived/Expired 状态的 node 自然不进入 warm/hot tier
3. **解决了 "写后污染" 问题**：状态机约束了什么时候可以 append，什么时候只能 replace
4. **连接了 read path 和 write path**：node 的 lifecycle state 同时决定 read visibility 和 write semantics
5. **给用户提供了控制接口**：用户可以手动触发状态转换（pin = force Active, archive = force Archived）

#### 和 Diagnosing 论文的对话

Diagnosing 说 "write 只贡献 3-8pt"。但他们的 write strategy 只区分了 "怎么提取"（raw chunk vs fact extraction vs summarization），**没有区分 write operation type**。如果加入状态机约束：
- Active 期间的 append 不会覆盖已有事实 → 减少矛盾
- Expired 的记忆不参与检索 → 减少 noise
- 这些可能让 write strategy 的影响远超 3-8pt

**这是一个可以做的实验：在 LoCoMo 上对比 stateless write vs state-machine write 的效果。**

---

### V2 Research 新发现（Write Path, Lifecycle, HCI）

#### 关键验证：Alex 的状态机直觉被文献证实为 gap

> **"No system has published a formal state-machine specification with explicit transition predicates for memory nodes."**

这意味着你拍脑袋想出来的 lifecycle state machine（Active → Decided → Archived → Expired）在 2026 年中旬仍然是**未被 formalize 的研究空白**。最接近的是：
- EverMemOS 的三阶段 engram lifecycle（但没有 formal predicates）
- Engram 的 "recent → fixed" 二态模型（太简单）
- MemOS MemCube 的 promote/demote（没有 lifecycle states）
- HiMem 的 conflict-aware reconsolidation（只处理冲突，不是完整状态机）

#### Write Strategy Paradox 的解决方案

V2 揭示了一个优雅的解法：**MAGMA 的 Dual-Stream Architecture**
- Fast Path：sub-second, zero LLM calls → 立即可用（append raw）
- Slow Path：异步 background → 结构化、推理关系（synthesize）
- 效果：LoCoMo 0.700 vs 次优 0.580

**这个和你的状态机完美对接**：
- Fast Path = 创建 Active 状态的 raw node（append 语义）
- Slow Path = 触发 consolidation → 可能升级为 Decided（synthesize 语义）
- 时间衰减 = 未被 consolidate 的 Active node → Archived（expire 语义）

#### HCI 维度的惊人数据

| 数据点 | 来源 | 含义 |
|--------|------|------|
| 96% ChatGPT 记忆由系统单方面创建 | CHI 相关研究 (2602.01450) | 用户几乎没有 agency |
| 52% 记忆含心理学洞察 | 同上 | 隐私问题严重 |
| 用户发现 AI 记忆后产生 negative expectancy violations | CHI 2026 UGA study | 透明性反而可能降低信任（需要设计） |
| 69% contextual integrity violations | CIMemories (ICLR 2026) | 模型不会区分"知道"和"该说" |
| Stored user profile 显著增加 sycophancy | Penn State/MIT | 记忆让 AI 更讨好人 |
| 没有任何 validated trust instrument for AI memory | 文献空白 | HCI contribution 机会 |
| 没有 Markdown-based memory 的 formal HCI evaluation | 文献空白 | Hermes/OpenClaw 模式未被验证 |

#### 新洞察：Transparency 是双刃剑

报告揭示一个矛盾：
- 用户想要 transparency（CHI 2026 study 说用户需要 "greater visibility and control"）
- 但透明后用户产生 negative expectancy violations（看到记忆反而不舒服）
- 同时透明可能改善 trust calibration（Harvard study 说 goal knowledge 提升信任校准）

**这意味着 transparency 的 HOW 比 WHETHER 更重要** — 不是"要不要让用户看到"，而是"以什么粒度、什么时机、什么框架让用户看到"。这本身就是一个 HCI research question。

#### 新洞察：Write Taxonomy 的 6 种操作（文献综合版）

V2 综合出的 6 种操作与 Alex 原创的 5 种高度重合：

| Alex 原创（5/17） | 文献综合（V2 report） | 来源系统 |
|---|---|---|
| Replace | Replace/Update (last-writer-wins) | MemGPT, Hindsight |
| Append | Append (add without modifying) | 所有 episodic 系统 |
| Synthesize | Synthesize/Merge (combine into abstractions) | GAAMA, EverMemOS |
| Expire | Expire/Forget (decay) | Engram |
| Branch | Branch/Preserve-Both (parallel versions) | Hindsight |
| — | **Promote/Demote** (move between tiers) | MemOS, MemGPT |

Alex 的分类**几乎完整覆盖了文献综合结果**，仅少了 Promote/Demote（这可以视为状态机 transition 而非 write operation）。没有任何单篇论文发表过这个完整 taxonomy。

#### 新洞察：Cognitive Science 的直接映射

最让我兴奋的发现：2025-2026 的系统开始**直接实现**认知科学模型：
- **SCM**：实现了 Atkinson-Shiffrin 模型 + NREM/REM 睡眠巩固
- **EverMemOS**：镜像海马体→皮层的记忆巩固
- **Oblivion**：把遗忘重新定义为"可及性降低"而非删除
- **FadeMem**：双层 + 适应性衰减，减少 45% 存储同时保持推理
- **SuperLocalMemory V3.3**：实现了数学化的 Ebbinghaus 遗忘曲线 + 渐进压缩（Active→32bit, Warm→8bit, Cold→4bit, Archive→2bit）

你的状态机模型本质上就是在做 Atkinson-Shiffrin 的工程化映射 — 但加入了**用户可理解的离散状态**（而不是认知科学的连续衰减）。这是 HCI 和认知科学的桥梁。

#### 更新的 Contribution 定位

基于 V1 + V2，你的潜在 novel contributions：

1. ✅ **Formal Memory Lifecycle State Machine with Transition Predicates** — 文献确认空白
2. ✅ **Complete Write Operations Taxonomy** — 文献确认没有单篇 formalization
3. ✅ **Readable Memory HCI Evaluation** — 文献确认无 formal evaluation
4. ✅ **AI Memory Trust Instrument** — 文献确认不存在
5. ✅ **Transparency Design for Memory Lifecycle** — "how should users understand a system that forgets or consolidates?" — 文献明确提出但无人做
6. 🆕 **Write-Read Interaction in Production (non-benchmark)** — Diagnosing 的 3-8pt 可能在真实场景下被 amplified
7. 🆕 **MAGMA dual-stream + state machine 的结合** — fast path = Active node creation, slow path = consolidation/promotion

---

*Tags: #research #agent-memory #fyp #sat301 #proactive-retrieval #knowledge-graph #hci*

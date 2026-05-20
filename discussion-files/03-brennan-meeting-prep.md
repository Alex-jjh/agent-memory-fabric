# Brennan 讨论手册：Agent Memory × HCI 方向（完整版）
*Prepared: 2026-05-17/18 | For: SAT301 FYP 方向探讨*
*基于两轮 deep research（40+ 篇论文）+ 个人洞察整合*

---

## Part 0: 完整架构视图 — 十个组件 × 四个层面

> 核心论点：好的 agent memory 不是单一技术问题，而是跨 4 个层面 10 个组件的系统设计问题。

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 4: USER / INTERACTION                                        │
│  ⑩ Transparency & Control (用户可见、可编辑、可触发状态转换)         │
└─────────────────────────────────────────────────────────────────────┘
        ↕ 用户 pin/flag/browse/confirm
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 3: WRITE / DECISION                                          │
│  ⑧ Write Semantics (Replace/Append/Synthesize/Expire/Branch/Promote)│
│  ⑨ Dual-Stream (fast append + async consolidation, à la MAGMA)      │
└─────────────────────────────────────────────────────────────────────┘
        ↕ 什么时候存、怎么存
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 2: READ / RETRIEVAL                                          │
│  ⑥ Proactive Retrieval Gateway (<100ms, 用户消息到达时预判)          │
│  ⑦ Multi-Signal Scorer (semantic + graph + hierarchy + decay +       │
│     frequency + intent)                                              │
└─────────────────────────────────────────────────────────────────────┘
        ↕ 什么时候读、注入什么
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1: STORAGE / ORGANIZATION (← "四者" 在这里)                   │
│  ① Graph (KG 拓扑: entity-relation, 关联推理, 搜索范围缩窄)          │
│  ② State Machine (lifecycle: Active→Decided→Archived→Expired)        │
│  ③ Vector Index (embedding + BM25 hybrid, 语义匹配)                  │
│  ④ Tiered Memory (hot ~1300tok / warm ~2000tok / cold unlimited)     │
│  ⑤ Folder Hierarchy (命名空间 = 隐式本体论, 物理组织 = 检索先验)     │
└─────────────────────────────────────────────────────────────────────┘
```

**你说的"四者"（① ② ③ ④）是 Layer 1 的核心。但完整架构需要四层才能工作。**

没有 Layer 2 → 有记忆但不知道什么时候该注入（reactive 模式，衰退 17pt）
没有 Layer 3 → 所有东西都存、永不清理（noise 积累，污染检索）
没有 Layer 4 → 黑箱系统，用户无法纠错（96% unilateral，negative violations）

---

## Part 0.5: 活案例 — Quick 的 KG 现状作为 Motivation

> 以下是 Alex 自己的 KG 中观察到的实际问题，证明 lifecycle state machine 的必要性。

**当前 KG 快照（2026-05-18 凌晨）：**

| Node | KG 现状 | 问题 | 状态机下应该是 |
|------|---------|------|---------------|
| CPT202 Software Engineering | 仍然活跃返回 | 课程 5/11 答辩完成，已无任何后续 | **Expired** — 不参与常规检索 |
| heritage-resource-platform | 描述为 "Alex 的 CPT202 项目" | 项目已交付，不再开发 | **Archived** — cold tier |
| AWS SAA | "正在备考中" | 状态可能已变化，无法判断 | **Unknown** → 触发 Agent Ask |
| GRE | "即将开始备考" | 写入时间不明，无 temporal context | **Stale** → 需要 refresh |
| Same Barrier paper | summary 说 "N=1040" | 实际论文 N≈14,772，数据过时 | **Active** but needs **Replace** |
| knowledge-vault | "2026-05-10 搭建" | 持续使用中，信息准确 | **Active** ✅ |
| Alex Jiang (profile) | 信息完整 | 核心事实准确 | **Decided** ✅（稳定状态）|

**诊断：5/7 个抽样 node 有问题。核心原因 = 缺少 lifecycle management。**

**如果有状态机，会怎样：**

```
① CPT202 答辩完成 (event: 2026-05-11)
   → trigger: "course_completed" predicate
   → transition: Active → Expired
   → effect: 不再参与 warm/hot tier 检索
   → 但仍可通过 "我之前上过什么课" 的 cold-tier 搜索召回

② AWS SAA 超过 3 周无交互 + 无相关对话
   → trigger: temporal_decay > threshold AND no_recent_mention
   → transition: Active → Stale (中间态)
   → effect: Agent 主动问 "你 SAA 考完了吗？"
   → 用户回答 → Active (仍在考) OR Decided (考完了) OR Expired (放弃了)

③ Same Barrier paper summary ≠ 最新事实
   → trigger: conflict_detected (N=1040 vs N=14,772)
   → operation: Replace (更新 summary)
   → state remains: Active (论文仍在 revision)
```

**这个 case study 的价值**：
- 不是假设性的学术场景，是真实使用的系统
- 展示了 lifecycle 缺失的具体后果：旧信息和新信息竞争 retrieval slots
- 暗示了一个 evaluation 方法：比较有/无状态机时的 retrieval precision on real KG
- 对 Brennan：证明这不是纯理论问题，是有 real user pain 的

---

## 一句话 Pitch

> **"AI Agent 的记忆系统有一个核心设计空白：没有人形式化过记忆节点的生命周期状态机——什么时候该存、怎么存（覆盖/追加/合成/过期）、什么时候该'忘记'——也没有人从 HCI 角度研究用户如何理解和控制这个过程。我想做这件事。"**

---

## 30 秒背景

- 2025-2026 年 agent memory 是 AI 最活跃方向之一（两轮 research 覆盖 60+ 篇论文）
- **Read path** 已被研究得很成熟（分层检索、图增强、主动注入）
- **Write path + Lifecycle** 是明确的形式化空白（文献原文确认）
- **HCI/User 视角** 几乎完全空白（无 validated trust instrument，无 readable memory eval）
- 这三者的交叉是一个完整的、未被覆盖的研究课题

---

## Part 1: 核心研究发现（给 Brennan 的 Evidence Base）

### 1.1 文献确认的三个 Gap

| Gap | 文献原话 | 我的切入点 |
|-----|----------|-----------|
| **Lifecycle State Machine** | "No system has published a formal state-machine specification with explicit transition predicates for memory nodes" | 提出 4-state model + transition predicates |
| **Write Operations Taxonomy** | "No single paper presents a complete taxonomy of write operations" | 6 种操作的 formalization |
| **Memory Trust Instrument** | "No validated trust instrument specific to AI memory exists" | 设计 + validate 一个 |
| **Readable Memory HCI Eval** | "No formal HCI evaluation of readable-file memory pattern has been published" | User study 对比透明 vs 不透明 |

### 1.2 最强实证数据

| 发现 | 数据 | 来源 | 含义 |
|------|------|------|------|
| Proactive > Reactive retrieval | 84.2% vs 17pt 衰退 | PASK (2604.08000) | 主动注入记忆更稳定 |
| 检索精度是最大瓶颈 | 14-23pt (retrieval) vs 3-8pt (write) | Diagnosing (2603.02473) | 重点在读不在写——但见 1.3 |
| Graph + Vector > 纯 Vector | 78.9% vs 75.0% | GAAMA (2603.27910) | KG 辅助检索有 measurable gain |
| Architecture > Weight Tuning | PPO = 启发式 | MemTier (2605.03675) | 信号选择比 ML 调参重要 |
| Dual-stream write 效果最好 | 0.700 vs 0.580 | MAGMA (2601.03236) | Fast append + async consolidation |
| 96% 记忆由系统单方面创建 | N=80 users, 2050 entries | CHI study (2602.01450) | 用户几乎没有 agency |
| 用户看到记忆后 negative violations | N=20 qualitative | CHI 2026 UGA | 透明性需要 careful design |
| 69% contextual integrity violations | CIMemories benchmark | ICLR 2026 (2511.14937) | 模型分不清"知道"和"该说" |
| Memory 增加 sycophancy | N=38, 2 weeks | Penn State/MIT 2026 | 记忆让 AI 更讨好人 |

### 1.3 Write Strategy Paradox — 为什么"只贡献 3-8pt"可能有误导性

Diagnosing 论文在 **LoCoMo benchmark**（精心设计的对话，每段都有信息量）上发现 write 不重要。但：
- 真实场景 90%+ 对话是 noise（闲聊、确认、重复）
- 错误存储 noise → 污染检索池 → 间接伤害 read path（accumulation effect）
- 存了矛盾信息 → 人格漂移/事实错误
- STALE benchmark 发现：即使 frontier LLM 也只有 55.2% 的隐式冲突检测准确率

**所以在 production 中，write decision 的影响可能被 benchmark 严重低估。**

---

## Part 2: 我的原创洞察

### 2.1 Memory Write Semantics — Replace vs Append vs 更多

记忆不是统一的 "store" 操作。我提出的分类学：

| 操作 | 语义 | 例子 | Graph 行为 | 文献对应 |
|------|------|------|-----------|----------|
| **Replace** | 新状态覆盖旧 | "我住上海→苏州" | 更新 node property | MemGPT, Hindsight |
| **Append** | 事件累积不互斥 | "5/17 讨论了 memory" | 新 edge/子 node | 所有 episodic 系统 |
| **Synthesize** | 多事件升华为洞察 | 5 次讨论→"方向确定" | 合并为新 node | GAAMA, EverMemOS |
| **Expire** | 时效性信息失效 | "今天 3 点开会" | TTL/archive | Engram |
| **Branch** | 状态分裂为多可能 | "FYP 可能 HCI 或 ML" | 多候选 edge | Hindsight |
| **Promote/Demote** | 层级间迁移 | cold→hot tier | 改变可见性 | MemOS |

**没有任何单篇论文发表过这个完整 taxonomy。**

### 2.2 Memory Lifecycle State Machine — AI "忘记"的方式

核心 reframe：**人会忘，AI 不会自然忘。AI 的"遗忘"必须是显式设计的。状态机就是这个设计。**

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
   │       write semantics: read-only
   │       visibility: cold tier（agent 主动搜才看到）
   │       ≈ 人的 "忘记但能想起来"
   │
   └──→ [Expired/Invalidated]  ← 不再有效
           write semantics: 不接受写入
           visibility: 不参与检索（但可审计）
           ≈ 人的 "完全忘记"
```

**状态转换触发器（Transition Predicates）：**
- `Active → Decided`：用户明确决策 / consolidation 检测到收敛
- `Active → Archived`：时间衰减 × 无新交互 > threshold
- `Decided → Archived`：被新的 Decided node 替代
- `Any → Expired`：TTL 到期 / 用户删除 / 矛盾检测 invalidation

**MAGMA Dual-Stream 对接：**
- Fast Path (zero LLM, sub-second) = 创建 Active 状态的 raw node
- Slow Path (async consolidation) = 触发状态转换判断（synthesize? promote? expire?）

### 2.3 Transparency 的"HOW > WHETHER"问题

报告揭示矛盾：
- 用户**想要** transparency（CHI 2026: "greater visibility and control"）
- 但看到记忆后产生 **negative expectancy violations**（不舒服）
- 然而 goal knowledge transparency 又**改善 trust calibration**（Harvard）

**结论：不是"要不要让用户看到"，而是"以什么粒度、什么时机、什么框架让用户看到"。**

这本身就是一个 interaction design research question。

### 2.4 Memory as Interface, Not Infrastructure

把 memory 从后端系统重构为用户与 agent 协作维护的共享空间：
- 用户可以 **pin**（显式提权到 hot tier = force Active/Decided）
- 用户可以 **flag**（触发 reconsolidation = force contradiction check）
- 用户可以 **browse**（理解 agent 的世界模型）
- Agent 可以 **ask**（主动消歧 = "我记得你住苏州，现在还是吗？"）
- 用户可以 **see lifecycle**（node 从 Active → Decided → Archived 的视觉反馈）

---

## Part 3: Research Question 候选

### Option A: Full Hybrid（推荐，scope 最适合 FYP）
> **"Does a lifecycle-aware memory system with user-facing transparency controls improve both task performance and user trust compared to opaque flat memory?"**

Contributions: ① State machine formalization ② Transparency UI design ③ User study (N=20-30)

### Option B: HCI Focus
> **"How do different memory transparency designs (flat list vs. lifecycle visualization vs. readable files) affect user trust calibration and sense of control in long-term AI interaction?"**

Contributions: ① Design space exploration ② Trust instrument ③ User study

### Option C: Systems Focus
> **"Can formal write semantics (Replace/Append/Synthesize/Expire) with lifecycle state transitions improve long-term memory quality in production conversations?"**

Contributions: ① Formal taxonomy ② State machine implementation ③ Benchmark evaluation (LoCoMo + real data)

### Option D: Empirical
> **"How does write precision interact with retrieval strategy in real-world (noisy) conversations vs. curated benchmarks?"**

Contributions: ① Replication + extension of Diagnosing paper ② Real-world data analysis ③ Design recommendations

---

## Part 4: 可行性论证

### 技术可行性
- 不需要训练大模型
- State machine = 工程设计 + formal spec（不需要 GPU）
- Benchmark 现成（LoCoMo, LongMemEval, EvolMem, STALE）
- 有现成系统可做 testbed（Amazon Quick 有 KG + RAG + Memory + real usage data）
- Dual-stream 架构是 well-understood pattern

### HCI 可行性
- Within-subjects A/B study（transparent vs opaque）
- N=20-30 足够（qualitative + quantitative mixed）
- Trust scales 可用：TAI (N=1485 validated), S-TIAS (3-item short form)
- 可补充 think-aloud protocol + semi-structured interview
- XJTLU 有 ethics approval 流程

### 时间线适配（SAT301: 2026.09 - 2027.05）
| Phase | Time | Deliverable |
|-------|------|-------------|
| Literature + Design | Sep-Nov | Formal spec + prototype design |
| Implementation | Nov-Jan | Working prototype |
| User Study | Feb-Mar | Data collection |
| Analysis + Writing | Mar-May | Paper draft + FYP report |

---

## Part 5: 我想问 Brennan 的问题

1. **方向偏好**：你觉得 Option A-D 哪个最适合 SAT301 scope？需要多 HCI 还是可以偏 systems？
2. **方法论**：对于 memory transparency 的 user study，你推荐什么设计？Within-subjects? Diary study? Think-aloud?
3. **文献**："AI Transparency" / "Explainability for end users" 方面你觉得哪些 CHI 论文值得读？
4. **和 AMT 的关系**：你觉得这个和我之前的 accessibility manipulation 论文够 coherent 吗？还是太跳了？
5. **投稿**：如果时间线合适，CHI LBW / ASSETS Poster / IUI / CSCW 哪个最 fit？
6. **User study ethics**：涉及 AI 记住用户个人信息，ethics approval 有什么特殊考虑？

---

## Part 6: 可能的反对意见 & 回应

| 反对 | 回应 |
|------|------|
| "太偏 systems，不够 HCI" | 核心 contribution 是 transparency design + user study；系统是 means not end |
| "Scope 太大" | 可以只做 state machine + transparency UI + user study（Option A 精简版） |
| "和 AMT 论文关联不强" | 共同主题 = "AI Agent 行为的用户可控性"：AMT 是 web manipulation visibility，这是 memory manipulation visibility |
| "没有新意" | 文献原文确认：no formal state machine, no write taxonomy, no trust instrument, no readable memory eval |
| "状态机太简单，能发论文吗" | 简单的 formalization 恰好是空白；validation through user study 是 contribution |
| "Benchmark 上 write 不重要" | ① 真实场景不等于 benchmark ② 关注的是用户信任不只是准确率 |
| "和 Hermes 视频的观点不同？" | 不矛盾：Hermes 说"少存"，我说"用状态机来决定存什么和怎么存"——本质一样 |

---

## Part 7: 和 AMT 研究的关系

```
AMT Framework (已完成)              Agent Memory (FYP 提案)
──────────────────────              ─────────────────────────
AI Agent + Web                      AI Agent + Memory
用户不可见的操控                     用户不可见的记忆
Accessibility = 可达的网页           Accessibility = 可达的记忆
检测 manipulation                   检测 memory errors/drift
用户 awareness & control             用户 awareness & control
Structural vs Cosmetic taxonomy     Replace/Append/Synthesize taxonomy
     ↓                                    ↓
共同主题: User Agency over AI Agent Behavior
    （用户对 AI Agent 行为的主权）
```

**方法论延续**：
- AMT 提出了 taxonomy（structural vs cosmetic）→ Memory 也提出 taxonomy（write operations）
- AMT 用了 controlled experiment（48 tasks）→ Memory 也用 controlled user study
- AMT 度量了 agent adaptation → Memory 度量 user trust + task performance
- 都是 mixed-methods：定量 + 定性分析

---

## Part 8: 附录 — Key References（按主题分组）

### Write Path & Lifecycle
- ProMem (2601.04463): iterative extraction, 73.8% integrity
- MAGMA (2601.03236): dual-stream, 0.700 LoCoMo
- Diagnosing (2603.02473): write 3-8pt vs retrieval 14-23pt
- HiMem (2601.06377): conflict-aware reconsolidation
- EverMemOS (2601.02163): engram lifecycle, 3-phase consolidation
- GAAMA (2603.27910): 4 node types, 3-step write pipeline
- Hindsight (vectorize.io blog): state vs event, preserve-both strategy
- STALE (2605.06527): implicit contradiction, 55.2% ceiling
- SCM (2604.20943): NREM/REM sleep consolidation
- FadeMem (2601.18642): adaptive decay, 45% storage reduction
- Oblivion (2604.00131): forgetting as accessibility reduction

### HCI & Trust
- CHI 2026 UGA: user perception of AI memory, negative violations
- ChatGPT Memory Study (2602.01450): 96% unilateral, 52% psych insights
- CIMemories (2511.14937): 69% contextual integrity violations
- Penn State/MIT sycophancy study: memory increases agreeableness
- Trust in conversational AI (2604.22417): 4-week longitudinal, N=27
- TAI Trust Scale (2403.00582): N=1485 validated
- S-TIAS (Frontiers 2025): 3-item short form for longitudinal
- Harvard goal knowledge study: transparency improves calibration
- XAI → SMMs causal chain (2601.06030): explainability enables shared mental models

### Read Path (for context)
- PASK/IntentFlow (2604.08000): proactive, 84.2%, ≤1s
- MemTier (2605.03675): 6-signal scorer, architecture > weights
- H-MEM (2507.22925): 4-layer positional-index routing
- LiCoMemory (2511.01448): CogniGraph, Weibull decay

---

---

## Part 9: Latest Findings from 12-System Source Code Analysis（2026-05-20）

> 以下基于 clone 并分析 12 个开源 agent memory 系统的源码。详细报告见 `reference-repo/SYNTHESIS.md`。

### 9.1 Gap Triple-Confirmed（从 3 → 15 个系统）

之前 Part 0 基于论文综述确认了 gap。Doc-09 用 3 个工业系统（Hermes/OpenClaw/Claude Code）double-confirmed。
现在对 12 个额外开源系统做了源码级分析：

| Gap | 论文综述 (40+ papers) | 工业系统 (3) | 开源系统 (12) | 总计 0/15 有的系统 |
|---|---|---|---|---|
| **Discrete lifecycle state machine** | ❌ 无 | ❌ 无 | ❌ 无（CortexGraph 有 continuous decay 但无 discrete states）| **0/15** |
| **Write semantics taxonomy (tracked per-write)** | ❌ 无 | ❌ 无 | ❌ 无 | **0/15** |
| **Proactive injection (intent-aware gateway)** | ⚠️ PASK (论文) | ⚠️ Claude Code (Sonnet ranker) | ⚠️ CortexGraph (spaced repetition) | **~2/15 partial** |

**Conclusion for Brennan**: 这不是 "我 claim 有 gap，literature 也许遗漏了什么"。这是 "我检查了 15 个实际系统的源码，literally 没有人实现 discrete lifecycle state machine"。

### 9.2 CortexGraph = Closest Prior Art（必须在 Paper 1 Related Work 讨论）

**CortexGraph 有什么**：
- Power-law decay: `score = (use_count+1)^0.6 * decay(dt) * strength`
- Threshold-based lifecycle: forget < 0.05, promote > 0.65
- GC removes/archives forgotten memories
- Consolidation merges near-duplicates
- **Spaced repetition injection**: fading memories are opportunistically blended into search results when contextually relevant
- Obsidian vault for LTM promotion

**AMF 如何差异化**：
| Dimension | CortexGraph | AMF |
|---|---|---|
| Forgetting model | Continuous decay curve → implicit disappearance | Discrete states (Active→Decided→Archived→Expired) with explicit transition predicates |
| State semantics | Score ∈ [0, 1]（无语义意义，只是"强度"）| Named states with distinct write semantics (Active accepts Append, Decided accepts Replace, Archived is read-only) |
| Proactive injection | Spaced repetition (inject fading memories) | Intent-aware gateway (inject relevant memories based on incoming message intent) |
| Graph structure | Typed relations + clusters | KG topology + edge traversal for retrieval path prior |
| Evaluation | No formal evaluation in repo | Controlled ablation vs Claude Code baseline (Paper 1) |
| Write ops | add/search/consolidate | 6-type taxonomy (Replace/Append/Synthesize/Expire/Branch/Promote) |

**Positioning for Paper 1**: "CortexGraph demonstrates that decay improves memory systems. We ask: can we do better with *discrete, semantically meaningful states* rather than a continuous score? Our state machine makes forgetting an *explicit architectural decision* rather than an emergent property of a decay function."

### 9.3 Updated Paper 1 Experimental Design

Per doc-09's pivot, the baseline is now a Claude Code clone (not strawman flat memory):

```
┌─────────────────────────────────────────────────────────────────┐
│  Control: Claude Code Clone                                      │
│  • 4 types (user/feedback/project/reference)                     │
│  • Sonnet ranker (proactive prefetch)                           │
│  • Forked-agent extraction (per-turn, manifest pre-injected)    │
│  • Freshness caveat only (binary ≤1d / ≥2d)                    │
│  • No lifecycle, no decay, no state transitions                  │
└─────────────────────────────────────────────────────────────────┘
                              vs
┌─────────────────────────────────────────────────────────────────┐
│  Treatment: Claude Code Clone + State Machine                    │
│  • Same 4 types + same ranker + same extraction                 │
│  • + `state` field in frontmatter (Active/Decided/Archived/Exp) │
│  • + State-aware filter (exclude Expired from recall pool)       │
│  • + Transition predicates fire post-extraction                  │
│  • + Temporal decay informs state transitions (not score)        │
└─────────────────────────────────────────────────────────────────┘
                              vs (optional additional baseline)
┌─────────────────────────────────────────────────────────────────┐
│  CortexGraph Baseline: Continuous Decay                          │
│  • Same storage + same extraction                                │
│  • Power-law decay score                                         │
│  • Threshold-based forget/promote                                │
│  • No discrete states, no write semantics differentiation        │
└─────────────────────────────────────────────────────────────────┘
```

**DVs (dependent variables)**:
- Retrieval precision @ k=5 (LoCoMo + LongMemEval long-horizon dialogues)
- Contradiction rate (mock KG with planted stale/expired facts)
- Token efficiency (context tokens injected per useful retrieval)
- Graceful degradation over time (does precision decay flatten with lifecycle?)

### 9.4 Additional Design Insight: GAAMA's Graph Edit Learning

GAAMA implements a "self-healing" mechanism: when retrieval fails (query returns irrelevant results), the system automatically:
1. Detects the failure
2. Creates new facts/concepts to bridge the knowledge gap
3. Future queries benefit from the patched graph

**Relevance to AMF**: This is a form of *reactive lifecycle management* — the graph evolves in response to failure signals. AMF could incorporate GEL in its consolidation phase (Slow Path): when a memory retrieval fails, trigger state transition or graph patching rather than just degrading score.

### 9.5 Memo for Brennan Discussion

**Key talking points**:
1. "I've now analyzed 15 real systems' source code. Zero implement what we're proposing. CortexGraph is closest but uses continuous decay — we're proposing something architecturally different (discrete states)."
2. "The experimental design is now much stronger: baseline = literal clone of the most popular deployed system (Claude Code), not a strawman."
3. "CortexGraph gives us a natural second comparison point: continuous decay vs discrete states vs no lifecycle at all (three conditions)."
4. "Mem0 going ADD-only in V3 validates our stance that write semantics matter — they tried letting the LLM decide CRUD and pulled back."

---

*Remember: 这是探讨不是 defend。保持开放，听 Brennan 的建议调整。重点 pitch: ① 有明确 gap（文献原文确认）② 和 AMT coherent（同一 theme）③ 有可行 testbed（Quick）④ scope 可调（从纯 HCI 到 hybrid 都行）*

*Tags: #meeting-prep #brennan #fyp #sat301 #agent-memory #hci #write-semantics #lifecycle*

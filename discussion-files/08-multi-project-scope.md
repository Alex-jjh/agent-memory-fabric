# AMF Multi-Project Memory Architecture
*Created: 2026-05-20 | Status: Design concept*

---

## 核心问题

> 当记忆不是单一平面，而是分布在多个"项目上下文"中时，整体架构应该怎么设计？

人类的工作是 **project-centric**（项目为中心），但记忆天然是 **entity-centric**（实体/人/概念为中心）。项目是人为的边界，但知识是跨边界流动的。

---

## 三层记忆空间模型

```
┌─────────────────────────────────────────────────────────────────┐
│  GLOBAL MEMORY (跨项目共享)                                      │
│  ─────────────────────────────────────                          │
│  • User Profile (我是谁、住哪、风格)                              │
│  • People Graph (Brennan, collaborators, contacts)              │
│  • Skills & Tools (Python, LaTeX, Git, 怎么用 Quick)            │
│  • Standing Preferences (dark mode, 中文回复, etc.)             │
│  • Life Goals (申研、毕业、career)                               │
│                                                                  │
│  lifecycle: mostly Decided/Committed, 很少变                     │
│  scope: 所有项目都能看到                                          │
│  检索优先级: 最高（总是注入）                                      │
└──────────────────────────────┬──────────────────────────────────┘
                               │ 继承 (所有项目自动继承 Global)
┌──────────────────────────────▼──────────────────────────────────┐
│  PROJECT MEMORY (项目隔离)                                       │
│  ─────────────────────────────────────                          │
│  每个项目有独立的 memory fabric instance:                         │
│                                                                  │
│  ┌─── AMF Project ───┐  ┌─── AMT Paper ───┐  ┌─── CPT204 ───┐ │
│  │ decisions          │  │ experiment log   │  │ (Expired)     │ │
│  │ architecture       │  │ review feedback  │  │              │ │
│  │ paper strategy     │  │ revision plan    │  │              │ │
│  │ code patterns      │  │                  │  │              │ │
│  └────────────────────┘  └──────────────────┘  └──────────────┘ │
│                                                                  │
│  lifecycle: Active / Paused / Completed / Abandoned              │
│  scope: 只在该项目上下文中被主动检索                                │
│  隔离: 项目 A 的记忆不会 noise 到项目 B 的检索                     │
└──────────────────────────────┬──────────────────────────────────┘
                               │ 沉淀 (session 结束时决定是否 promote)
┌──────────────────────────────▼──────────────────────────────────┐
│  SESSION MEMORY (会话级，最短暂)                                  │
│  ─────────────────────────────────────                          │
│  • 当前对话的 working context                                    │
│  • 本次任务的中间状态                                             │
│  • 临时想法、草稿、未确认的信息                                    │
│                                                                  │
│  lifecycle: 会话结束 → promote 到 Project Memory，或消失          │
│  scope: 仅当前会话可见                                            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 项目 Lifecycle = 记忆 Lifecycle

| Project State | Memory Behavior | 检索 | 写入 |
|---|---|---|---|
| **Active** (正在做) | Hot/Warm tier, 主动注入相关记忆 | 全量检索 | 允许所有 write ops |
| **Paused** (暂停) | 降级到 Cold tier, 不主动注入但可搜索 | On-demand only | Append only |
| **Completed** (完成) | Archive 整个 project memory space | 仅 explicit recall | Read-only |
| **Abandoned** (放弃) | Expire, 除非有 cross-project 价值 | 不参与 | No |

**项目状态转换触发器：**
- Active → Paused: 2+ 周无交互且无 calendar 事件
- Active → Completed: 用户明确声明 / 外部事件（答辩通过、paper accepted）
- Paused → Active: 用户重新提及 / 新交互发生
- Paused → Abandoned: 长期无活动（可配置，默认 3 个月）
- Completed → (Insights promote to Global): 项目中的通用洞察升级为全局知识

---

## Cross-Project 记忆流动规则

### 从 Project → Global 的 Promotion 条件

| 触发条件 | 例子 | 操作 |
|---|---|---|
| 多个项目引用同一条记忆 | "Brennan 偏好 within-subjects design" 在 AMT 和 AMF 都用到 | Auto-promote to Global People |
| 项目完成后，insight 有通用价值 | "lifecycle state machine 有效" 从 AMF 实验得出 | Synthesize → Global Skill |
| 项目失败的教训 | "那个方案不 work 因为 XX" | Promote 为 Global Anti-pattern |
| 跨项目实体（人、工具、概念）| "Brennan" 出现在多个 project 中 | 自动归入 Global People Graph |

### 从 Global → Project 的 Inheritance

- 所有项目默认继承 Global Memory 的全部内容
- 项目可以 **override** Global 记忆（项目特定的偏好覆盖全局默认）
- 项目可以 **exclude** 某些 Global 类别（如技术项目不需要注入 life goals）

### 从 Session → Project 的 Promotion

| Session 内容 | 是否 Promote | 条件 |
|---|---|---|
| 明确的决策 | ✅ 自动 | "我们决定用 Beta 分布做信心度" |
| 探讨中的想法 | ⚠️ 标记为 Active/Exploring | 待后续确认 |
| 纯执行操作 | ❌ 不存 | "帮我格式化这个文件" |
| 错误/失败 | ✅ 如果有教训价值 | "这个方法不 work，因为..." |

---

## 检索时的 Scope 决策

Proactive Retrieval Gateway 在决定检索范围时，需要做 **scope inference**：

```
用户消息分析:
├── 提到特定项目名/术语 → Scope = 该 Project + Global
├── 提到跨项目实体 (人名) → Scope = Global People + 相关 Projects
├── 问"最近进展" → Scope = 所有 Active Projects (summaries only)
├── 问归档项目 → Scope = 指定 Archived Project (cold recall)
├── 通用问题 → Scope = Global only
└── 不确定 → Scope = Current Active Project + Global (default)
```

**默认行为**: 如果用户在某个项目的工作流中（如刚讨论完 AMF），scope 默认锁定到该 project + global。除非用户明确切换话题。

---

## 文件系统映射（Obsidian vault 实现）

```
~/memory-vault/
├── _global/                         ← Global Memory
│   ├── profile.md                   (identity, goals)
│   ├── preferences.md               (standing instructions)
│   ├── people/                      (entity nodes for people)
│   │   ├── brennan-jones.md
│   │   └── ...
│   ├── skills/                      (tools, languages, patterns)
│   └── anti-patterns.md             (global lessons learned)
│
├── projects/                        ← Project Memories
│   ├── agent-memory-fabric/         state: active ✅
│   │   ├── _project.md              (state, dates, description, tags)
│   │   ├── decisions.md
│   │   ├── architecture.md
│   │   ├── paper-strategy.md
│   │   └── ...
│   ├── amt-paper/                   state: active ✅
│   │   ├── _project.md
│   │   └── ...
│   ├── grad-applications/           state: active ✅
│   ├── cpt204/                      state: archived 📦
│   └── heritage-platform/           state: archived 📦
│
└── _sessions/                       ← Session scratch (auto-cleanup)
    └── (ephemeral, promote or expire)
```

### _project.md Frontmatter 格式

```yaml
---
state: active          # active / paused / completed / abandoned
created: 2026-05-17
last_active: 2026-05-20
description: "Agent Memory Fabric - lifecycle state machine for LLM agent memory"
tags: [research, fyp, engineering, open-source]
inherit_global: true
exclude_global: []     # 可以排除某些 global 类别
---
```

---

## 和项目管理工具的整合

| 工具 | 整合方式 | 实现 |
|------|---------|------|
| **GitHub repos** | 每个 repo → 对应一个 project memory namespace | 通过 repo name 自动关联 |
| **Obsidian folders** | 每个 projects/ 子目录 = 一个 project scope | 原生 |
| **Calendar** | 项目 2+ 周无事件 → 触发 Paused | fswatch + calendar API |
| **Git activity** | 最近 commit 时间 → 判断 active/paused | `git log` 时间戳 |
| **Manual override** | `amf project pause "cpt204"` | CLI 命令 |

---

## 对 AMF 现有设计的扩展

之前的 10 组件 × 4 层模型现在加入**第 5 个维度：Scope**

```
原来的 4 层:
  Layer 1: Storage/Organization (graph + state machine + vector + tiered + hierarchy)
  Layer 2: Read/Retrieval (proactive gateway + multi-signal scorer)
  Layer 3: Write/Decision (write semantics + dual-stream)
  Layer 4: User/Interaction (transparency + control)

新增维度:
  Dimension 5: SCOPE (global / project / session)
  - 影响 Layer 1: 每个 scope 有独立的存储分区
  - 影响 Layer 2: 检索时做 scope inference，决定搜索哪个分区
  - 影响 Layer 3: 写入时决定写到哪个 scope (session → project? project → global?)
  - 影响 Layer 4: 用户可以切换当前 active project context
```

---

## 竞品对比（scope 维度）

| 系统 | Multi-project scope? |
|------|---------------------|
| Mem0 | ❌ Flat namespace |
| Letta | ⚠️ 有 agent-level 隔离，但不是 project-aware |
| AgentCore | ⚠️ Namespace 分层 (/actor/session)，但不是 project 语义 |
| Basic Memory | ❌ 单一 vault |
| Quick Desktop | ❌ 所有记忆在一个 SQLite |
| **AMF** | ✅ Global → Project → Session 三层 scope + cross-project flow |

**这是 AMF 的又一个独特差异化点。**

---

## 潜在的论文角度

这个 multi-project scope 设计可以独立产出一篇：

> **"Scoped Memory for Multi-Project AI Assistants: Managing Knowledge Isolation and Cross-Project Flow"**

核心 contribution:
- Formalize 三层 scope model (Global/Project/Session)
- Cross-project promotion rules
- Scope inference at retrieval time
- Evaluation: scoped vs flat memory 在 multi-task 场景下的 retrieval precision

---

*Tags: #amf #architecture #multi-project #scope #design*

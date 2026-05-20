# 三方对比：Hermes / OpenClaw / Claude Code 记忆系统深度调研
*Created: 2026-05-20 | Source: 直接读源码（Hermes Python, OpenClaw TS, Claude Code TS leaked 2026-03-31）*

---

## 调研动机

之前的设计文档（00-08）基于 V1+V2 deep research 论文综述，确认了三个 gap（lifecycle state machine / write taxonomy / memory transparency）。但论文综述不等于工程现实——AMF 真正要差异化的对手是**已部署的工业系统**，不是论文。

本次调研直接读了三套源码的 memory 模块，目的：
1. 验证 AMF 的 novelty claim 是否真的还成立
2. 找出 AMF 应该照搬而不是重写的工程模式
3. 确定 Paper 1 的 baseline 应该选谁

**最重要的发现**：Alex 现在每天用的 "auto memory" 系统（user/feedback/project/reference 4 类型 + MEMORY.md 索引 + frontmatter schema）**就是 Claude Code 的设计**——不是 AMF 原创。这迫使 Paper 1 的 framing 必须调整。

---

## Part 1: 三个系统的架构骨架

### 1.1 Hermes Agent (Python)

源码位置：`reference-repo/hermes-agent/`

**存储**
- `~/.hermes/memories/` 下两个文件：`MEMORY.md`（agent notes）+ `USER.md`（user profile）
- 纯 Markdown，entries 用 `\n§\n` 分隔，**无 per-entry frontmatter**
- 字符预算（不是 token）：MEMORY 2200 chars / USER 1375 chars (`hermes_cli/config.py:1194-1195`)
- 原子写入：temp file + `atomic_replace()` (`tools/memory_tool.py:434-462`)

**Read path**
- 内置工具暴露给 LLM 的只有 `add` / `replace` / `remove` —— **没有 read/search action**
- 召回方式：session 开始时把 memory 整段塞进 system prompt 的 `volatile` tier，**整个 session 期间冻结**（KV-cache 优化）
- 中途的写入立即落盘但**直到下次 session 才对模型可见**
- 真正的检索委托给外部 `MemoryProvider` plugin（Honcho / Hindsight / Mem0）

**Write path**
- Agent 显式工具调用，立即原子写盘
- **无后台 extraction**
- 外部 provider 暴露丰富的钩子：`on_session_end` / `on_pre_compress` / `on_delegation` / `on_memory_write`

**Lifecycle**：完全没有。无 TTL、衰减、归档、版本历史、stale 标记。二元存在。

**Skills**：`skills/{cat}/{name}/SKILL.md` 平级文件夹 + frontmatter，**与 memory 完全不互通**。

---

### 1.2 OpenClaw (TypeScript)

源码位置：`reference-repo/openclaw/`

**存储**
- `MEMORY.md` 在 workspace root + `memory/YYYY-MM-DD.md` 短期日记 + `memory/dreaming/{light,rem,deep}/YYYY-MM-DD.md` 三阶段输出
- `memory/.dreams/short-term-recall.json` 是**结构化召回事件日志**（关键设计）
- 字符预算：MEMORY.md 10KB（`memory-budget.ts:25`）
- Phase 边界用 HTML 注释 `<!-- openclaw:dreaming:light:start -->`

**Read path**
- LLM 工具**只读**：`memory_search` + `memory_get`
- Reactive only：agent 必须显式调用 search
- 检索：LanceDB vector + BM25 FTS hybrid
- Corpus 模式：`memory` / `wiki` / `sessions` / `all`

**Write path — Dreaming 系统**（核心创新）
- Cron-driven，默认 `"0 3 * * *"`（凌晨 3 点）
- 三个阶段：
  - **Light sleep**: 去重最近高置信度召回
  - **REM sleep**: 模式聚类 + 叙事生成
  - **Deep sleep**: 加权评分 + 提升候选到 MEMORY.md
- **6 信号加权 promotion scorer** (`short-term-promotion.ts:57-64`)：
  | 信号 | 权重 |
  |---|---|
  | frequency（召回次数）| 24% |
  | relevance（平均匹配分）| 30% |
  | diversity（不同 query 数）| 15% |
  | recency（指数衰减，14 天半衰期）| 15% |
  | consolidation（窗口内重复召回）| 10% |
  | conceptual（概念 tag 覆盖度）| 6% |

**LLM 没有 write tool**——所有写入靠 dreaming + 手动 CLI promote。

**Lifecycle**：仍然没有显式的 expire/archive/delete。仅有"溢出时丢最老的 auto-promoted 段"。

**Plugin 架构**：memory 是 single-active plugin slot。已有 `memory-core` / `memory-wiki` / `memory-lancedb` / `active-memory` 四种。

---

### 1.3 Claude Code (TypeScript, leaked)

源码位置：`reference-repo/claude-code-main/`（2026-03-31 通过 npm sourcemap 泄露）

**存储**
- `~/.claude/projects/{sanitized-git-root}/memory/` —— **git-root-aware**，所有 worktree 共享一个 memory dir
- 4 种 memory type 写死：
  ```ts
  // memdir/memoryTypes.ts:14-21
  export const MEMORY_TYPES = ['user', 'feedback', 'project', 'reference'] as const
  ```
- 每个 entry 一个独立 `.md` 文件，frontmatter:
  ```yaml
  ---
  name: {kebab-slug}
  description: {one-liner for relevance scoring}
  type: {user | feedback | project | reference}
  ---
  ```
- `MEMORY.md` 是**索引文件**（无 frontmatter），≤200 行 / ≤25KB，每行一条 `- [Title](file.md) — hook`，<150 字符

**Read path — 混合 hybrid**
- **Proactive prefetch**: `startRelevantMemoryPrefetch()` 在 LLM 看到消息前异步运行
- **Ranker = Sonnet sideQuery**（不是 embeddings！）：
  ```
  SELECT_MEMORIES_SYSTEM_PROMPT =
    "You are selecting memories that will be useful to Claude Code
     as it processes a user's query. Return a list of filenames
     for the memories that will clearly be useful (up to 5).
     Only include memories you are certain will be helpful."
  ```
- 返回 JSON `{selected_memories: string[]}`
- 最近用过的工具排除出排序池（避免你正在用某工具时召回它的 API doc）
- 注入为 `<system-reminder>` 块；每条截断到 200 行 / 4096 字节
- `alreadySurfaced` set 防止 session 内重复召回

**Write path — Forked-agent extraction**
- Trigger: `handleStopHooks()` 在每轮 model 输出无 tool_use 的 final response 后触发
- 执行：`runForkedAgent()` 完整克隆主对话，**共享 prompt cache**（`createCacheSafeParams()`）—— 这是它每轮跑都不贵的关键
- Tool perms for fork: `FILE_READ`, `GREP`, `GLOB`, read-only `BASH`, Edit/Write **only to memory paths**
- 5 turn budget
- **Mutual-exclusion gate** (`extractMemories.ts:121-148`)：
  ```ts
  if (hasMemoryWritesSince(messages, lastMemoryMessageUuid)) {
    return  // 主 agent 已经写过了，跳过 fork
  }
  ```
- **Manifest 预注入**: `scanMemoryFiles()` + `formatMemoryManifest()` 把现有 memory 列表塞进 fork 的 prompt，省一个 `ls` turn
- 异步 fire-and-forget，不阻塞用户
- 节流：feature flag `tengu_bramble_lintel`，默认每轮跑

Extraction prompt 关键段：
> "Step 1 — write each memory to its own file using this frontmatter format ...
> Step 2 — add a pointer to MEMORY.md (one line, <150 chars).
> You have a limited turn budget (max 5 turns).
> Do not waste turns investigating — no grepping source files, no git commands.
> Do not write duplicate memories. First check if there is an existing memory you can update before writing a new one."

**Lifecycle = 仅 freshness caveat**（`memdir/memoryAge.ts:49-53`）：
```ts
if (d <= 1) return ''
return `This memory is ${d} days old. Memories are point-in-time
  observations, not live state — claims about code behavior or
  file:line citations may be outdated. Verify against current code
  before asserting as fact.`
```
**二元**：fresh (≤1d) vs stale (≥2d)。无 graduated decay，无 auto-archival，无 state。

**Team sync — production-grade**
- `fs.watch()` + 2000ms debounce push（不是 polling）
- 服务器权威 pull；delta push（仅 SHA256 不同的）
- ETag-based 409 conflict resolution，最多重试 2 次
- 不传播 delete（删本地不会删服务器，下次 pull 会恢复）
- 作用域：per-git-remote-hash

**Secret scanner** (`secretScanner.ts`) — 精选 gitleaks 规则子集：
- AWS（AKIA/ASIA/ABIA/ACCA）/ Anthropic / OpenAI / HuggingFace API keys
- GitHub PAT (`ghp_`) / GitLab PAT (`glpat-`)
- Slack bot (`xoxb-`) / Twilio (`SK[hex32]`) / npm / PyPI / Stripe / Sentry / Grafana
- PEM private key blocks
- 上传前扫描；**`redactSecrets()` 只替换匹配组为 `[REDACTED]`**（保留边界字符），block push，warn user

**`/memory` slash command**：React/Ink dialog，列出 memory file 分组 by type，开 `$EDITOR` 编辑。**没有 delete、filter、age、graph view**——只是个文件选择器。

---

## Part 2: 三方对比矩阵

### 2.1 架构维度

| 维度 | Hermes | OpenClaw | Claude Code |
|---|---|---|---|
| **存储格式** | Markdown + `§` 分隔 | Markdown + HTML phase markers | Markdown + frontmatter per file |
| **Per-entry metadata** | ❌ | ❌（在 sidecar JSON）| ✅ frontmatter |
| **Type taxonomy** | ❌ | ❌ | ✅ 4 types (user/feedback/project/reference) |
| **预算单位** | char (2200/1375) | char (10KB) | char (200 lines / 25KB index) |
| **Tool surface** | write-only (add/replace/remove) | read-only (search/get) | read-only |
| **Read 触发** | Session-start frozen snapshot | Reactive only | Hybrid: proactive prefetch + reactive |
| **Read ranker** | 外部 provider | LanceDB vector + BM25 | Sonnet sideQuery |
| **Write 触发** | Agent 显式工具调用 | Cron dreaming（夜间）| Forked-agent，每轮 |
| **Write tool exposed to LLM** | ✅ | ❌ | ❌（只有 fork 有）|
| **Dedup** | 加载时 exact-match | REM phase 去重 | Prompt-driven（manifest 预注入）|
| **Lifecycle** | 无 | 仅 overflow 截断 | 仅 2-day freshness caveat |
| **State machine** | ❌ | ❌ | ❌ |
| **Memory↔memory graph** | ❌ | ❌ | ❌ |
| **Multi-user / sync** | ❌（单 profile）| ❌ | ✅ 完整 team sync + secret scan |
| **Scope key** | profile (`HERMES_HOME`) | workspace + agentId | git remote hash |
| **User UI** | 编辑文件本身 | CLI 命令 + Obsidian (memory-wiki) | React/Ink editor 选择器 |
| **Plugin 架构** | `MemoryProvider` ABC | single memory plugin slot | 单体（不可换）|

### 2.2 Read path 三种范式

```
Hermes:                    OpenClaw:                  Claude Code:
session start              user message               user message
    ↓                          ↓                          ↓
load MEMORY.md             prompt-section advice:     startRelevantMemoryPrefetch()
freeze snapshot              "search before answer"      ├── scan memory dir
inject as system prompt        ↓                          ├── Sonnet ranker
    ↓                      LLM decides                   └── return ≤5 filenames
turn 1, 2, 3...                ↓                          ↓
(snapshot unchanged)       memory_search tool         inject as <system-reminder>
                               ↓                          ↓
                           LanceDB + BM25             LLM sees augmented message
```

三种 read 范式各代表一个设计选择：
- **Hermes**：精度由外部 provider 负责，内核保持极简 + KV-cache 友好
- **OpenClaw**：让 agent 自己决定何时检索，避免无谓注入
- **Claude Code**：每轮自动 prefetch，但用 Sonnet 做精确排序而不是向量

### 2.3 Write path 三种范式

```
Hermes:                    OpenClaw:                  Claude Code:
agent 决定                  cron 凌晨 3 点              每轮结束 (no tool_use)
    ↓                          ↓                          ↓
memory.add() 工具调用       light → REM → deep         hasMemoryWritesSince? skip
    ↓                          ↓                          ↓
原子写盘                    6 信号加权评分              fork agent (cache shared)
                                ↓                          ↓
                           append to MEMORY.md         5-turn budget
                                                        ├── manifest pre-injected
                                                        ├── update existing first
                                                        └── 4 types frontmatter
```

---

## Part 3: 对 AMF 设计的颠覆性影响

### 3.1 不再是 novel 的部分（必须从 AMF claim 中撤回或重新归因）

| AMF 之前 claim | 现实 | 调整方向 |
|---|---|---|
| 4 类型 memory taxonomy（user/feedback/project/reference）| **就是 Claude Code 的**，Alex 的 auto-memory 一直在用 | 明确归因 Claude Code，AMF 在此基础上扩展 |
| Proactive Retrieval Gateway < 100ms | Claude Code 已有 proactive prefetch | 差异化 = "<100ms 轻量"（Claude Code 用 Sonnet 排序，~1-2s）|
| Multi-signal Scorer | OpenClaw 已有 6 信号加权 | 差异化 = 加 **intent classification + graph proximity** |
| Dual-stream（fast append + async consolidation）| OpenClaw 的 dreaming 是 daily-batch 版本；Claude Code 的 forked-agent 是 per-turn 版本 | 差异化 = "**sub-second slow path**"，介于两者之间 |
| Write semantics 分类 | Claude Code prompt 区分 corrections vs confirmations，但**不 track operation type per write** | AMF 形式化 6 ops 仍然 novel |
| Local-first + readable | 三个系统全是 | 已经是 baseline，不是差异点 |

### 3.2 Triple-confirmed gap（三方系统都没有 → AMF 的真正 novelty）

| Gap | Hermes | OpenClaw | Claude Code | AMF 答案 |
|---|---|---|---|---|
| **Lifecycle state machine** | ❌ | ❌ | ❌（仅二元 freshness caveat）| ✅ Active→Decided→Archived→Expired + transition predicates |
| **Write semantics taxonomy（per-write tracking）** | ❌ | ❌ | ❌ | ✅ Replace/Append/Synthesize/Expire/Branch/Promote |
| **Memory↔memory graph edges** | ❌ | ❌ | ❌ | ✅ KG topology + edge traversal |
| **Transparency UI > editor list** | 看 Markdown | CLI only | editor 选择器 | ✅ Obsidian state badges + graph color-code |
| **Multi-project Global tier** | ❌ | ⚠️ workspace-level | ⚠️ git-repo-level | ✅ Global / Project / Session 三层 + cross-project promotion |
| **Graduated staleness curve** | ❌ | ❌ | ❌（二元）| ✅ Ebbinghaus / Weibull |
| **Intent classification + graph proximity in scorer** | ❌ | ❌ | ❌ | ✅ |
| **HCI evaluation of readable memory** | ❌ | ❌ | ❌ | ✅ Paper 3 |

### 3.3 必须照搬的工程模式（不要重新发明轮子）

来自 **Claude Code**：
1. **Manifest 预注入** —— extraction fork 启动前把现有 memory 列表塞进 prompt，省一个 `ls` turn
2. **Forked-agent + 共享 prompt cache** —— `createCacheSafeParams()` 是每轮跑 extraction 还能不贵的根本
3. **Mutual-exclusion gate** (`hasMemoryWritesSince`) —— 主 agent 已写过就跳过 fork
4. **Tool perm 限制** —— extraction fork 只允许 read tools + Edit/Write to memory paths
5. **Gitleaks 子集 + boundary-preserving redaction** —— 直接照搬，blocks 一类关键漏洞
6. **2-day freshness caveat 措辞** —— 调过的，cite 具体失败模式（file:line citations 过期）

来自 **OpenClaw**：
7. **Recall event log**（`short-term-recall.json`）—— AMF transparency UI 的现成数据底座
8. **6 信号加权 scorer 的 baseline 权重** —— frequency 24% / relevance 30% / diversity 15% / recency 15% / consolidation 10% / conceptual 6%
9. **HTML phase markers** 在 Markdown 文件里 —— 让人类可读、机器可解析的 zone 标记
10. **Cron-based dreaming** —— 作为 AMF slow path 的一种触发模式（除了 per-turn fork 外）

来自 **Hermes**：
11. **`MemoryProvider` plugin 契约** —— AMF 可作为该契约的实现，**直接接入 Hermes 生态**而不必自建 host
12. **字符预算（不是 token）** —— 跨模型代际稳定，所有三个系统都用 char
13. **Frozen snapshot pattern** —— per-turn injection 会破坏 KV-cache，AMF 必须显式论证 trade-off
14. **`atomic_replace()` for writes** —— 防止并发读取看到撕裂状态

---

## Part 4: Paper 1 framing pivot（核心建议）

### 旧 framing
> "We formalize memory lifecycle, implement it, show it helps retrieval"

问题：baseline 是 strawman flat memory，reviewer 会问"vs 哪个真实系统"。

### 新 framing
> **"We take the dominant industrial memory pattern (Claude Code's 4-type extracted-memory + Sonnet-ranker recall) and ask: what happens when you add a formal lifecycle state machine on top of it?"**

为什么更强：

1. **Baseline 是 Claude Code 自己** —— 一个真实部署、用户量极大的系统，不是 strawman
2. **Ablation 变量纯粹**：相同 4 type + 相同 Sonnet ranker + 相同 forked extraction，**只加 state machine**
3. 故事变成"the dominant pattern + lifecycle"，不是"another memory system"
4. AgentCore 那条对话仍然成立，只是现在主对手是 Claude Code（更有相关性，因为 Anthropic 自家东西）
5. **复现性**：Claude Code 源码在手，我们可以精确控制对照组

### 实验设计草稿

| Condition | Memory schema | Recall | Extraction | Lifecycle |
|---|---|---|---|---|
| **Control (Claude Code clone)** | 4 types + frontmatter | Sonnet ranker | Forked agent, per-turn | Freshness caveat only |
| **Treatment (+ state machine)** | + `state` field in frontmatter | Same ranker but state-aware filter | Same fork + state transition predicates | Active→Decided→Archived→Expired |

依变量：
- Retrieval precision @ k=5（在长 horizon 对话中）
- Contradiction rate（mock-Quick 真实 KG case）
- Token efficiency（context tokens injected per useful retrieval）

数据集：LoCoMo + LongMemEval + Alex 自己的真实 Quick KG（匿名化后）

---

## Part 5: 项目策略调整

### 5.1 开源策略

之前计划：独立产品 + Obsidian plugin。

调整后：**双向适配作为开源切入点**
- AMF Core 同时作为 **Claude Code memory system** 的 drop-in（替换 `memdir/`）
- 也作为 **Hermes MemoryProvider** 实现
- 也作为 **OpenClaw memory plugin slot** 的一种 plugin

这样获得：
- 三个生态的现成用户曝光，不需要从零拉
- 三套真实数据来对比 ablation
- 论文里可以说"deployed in 3 production agents"

### 5.2 文档归因

需要更新：
- `00-research-landscape-v1.md`：添加 Claude Code（论文综述里没覆盖的，因为是源码而非论文）
- `04-project-plan.md`：差异化矩阵需要把 Claude Code 加进去
- `05-reference-sources.md`：Claude Code 加入 § 二（可访问但有版权限制）
- 这个文档本身（09）作为 reference baseline 引用

### 5.3 AMF 设计原则的更新

之前：每个组件需 ablation contribution > 0。

补充：
- **每个 claim 必须先和 Claude Code / Hermes / OpenClaw 对照**——三方都已经做了的不是 contribution
- **借鉴的部分必须明确归因**（Claude Code 的 forked-agent / OpenClaw 的 6-signal scorer）
- **真正的 contribution 集中在 §3.2 的 8 个 triple-confirmed gap**

---

## Part 6: 一句话总结

**AMF 的 novelty 不是"我们做了 memory 系统"——而是"我们在 Claude Code 那条已经被工业证明可行的路径上，加了 lifecycle states + write taxonomy + graph + multi-project Global tier + transparency UI + HCI evaluation"。**

Paper 1 单挑 lifecycle states 这一条做 ablation；其余各 component 是开源 product 完成度，论文里以 follow-on 出现。

---

*Tags: #amf #reference-systems #claude-code #hermes #openclaw #comparison #paper-1*

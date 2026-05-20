# Agent Memory Fabric (AMF) — Discussion Files
*FYP 项目 | 2026-2027 | Supervisor: Brennan*

> "Let Agents Forget: A Lifecycle State Machine for Memory Management in LLM Agents"

---

## 文件索引

| # | 文件 | 内容 | 创建日期 | 最近更新 |
|---|------|------|----------|----------|
| 00 | [[00-research-landscape-v1]] | V1 研究全景（Read path 文献梳理 + 架构草图） | 2026-05-17 | — |
| 01 | [[01-research-log]] | 研究日志主文档（核心发现 + 原创洞察 + V2 findings + 状态机模型） | 2026-05-17 | — |
| 02 | [[02-deep-research-prompt-v2]] | Write path deep research prompt（未来 deep research 用） | 2026-05-17 | — |
| 03 | [[03-brennan-meeting-prep]] | Brennan 讨论完整手册（架构图 + case study + AgentCore 对比 + **12-system findings**） | 2026-05-18 | 2026-05-20 |
| 04 | [[04-project-plan]] | 双轨计划（工程+论文+Obsidian策略+repo结构+多篇论文规划+时间线 + **updated competitive landscape**） | 2026-05-18 | 2026-05-20 |
| 05 | [[05-reference-sources]] | 参考源码完整清单（18 开源 + 3 闭源 + 7 论文实现 + **12-system analysis summary**） | 2026-05-20 | 2026-05-20 |
| 06 | [[06-agentcore-comparison]] | AgentCore Memory 深度对比 | 2026-05-20 | — |
| 07 | [[07-quick-memory-analysis]] | Quick Desktop 记忆系统分析 | 2026-05-20 | — |
| 08 | [[08-multi-project-scope]] | 多项目记忆 scoping 设计 | 2026-05-20 | — |
| 09 | [[09-reference-systems-deep-dive]] | Hermes / OpenClaw / Claude Code 源码级深度对比 + Paper 1 framing pivot | 2026-05-20 | — |

---

## 项目概要

- **开源产品**: `agent-memory-fabric/` — Python daemon + Obsidian plugin + MCP server
- **实验平台**: `amf-experiments/` — 消融实验 + LoCoMo benchmark
- **论文**: `let-agents-forget-paper/` — Paper 1: State Machine lifecycle ablation
- **参考库**: `reference-repo/` — 12 个开源系统 clone + 每个的 `MEMORY_ANALYSIS.md` + `SYNTHESIS.md`

## 关键决策

- 项目名：Agent Memory Fabric (AMF)
- Paper 1 标题：Let Agents Forget
- Paper 1 Baseline：Claude Code clone (proactive + dedup, no lifecycle) vs Treatment (+ state machine)
- 三仓分离：产品 / 实验 / 论文
- 6 篇潜力论文：State Machine / Proactive Retrieval / HCI Transparency / Write Semantics / Full System / Empirical
- ★ Closest prior art: CortexGraph (continuous decay) — AMF differentiates with discrete states

## Gap Validation (2026-05-20)

**15 systems analyzed** (3 industrial + 12 open-source), **0/15** implement discrete lifecycle state machine:
- CortexGraph: continuous power-law decay (closest, but no discrete states)
- MemoryOS: heat-based decay + LFU eviction (no state semantics)
- All others: purely additive, no decay at all

---

*Tags: #amf #fyp #agent-memory #index*

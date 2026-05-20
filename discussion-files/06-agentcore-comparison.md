# AgentCore Memory 内部架构对比分析
*Created: 2026-05-20 | Source: 内部文档 + 公开 API docs*

---

## AgentCore 核心架构总结

```
STM (raw events, 7-365天 TTL)
    → Extraction (turn_size=2, 多种 Extractor)
    → Consolidation (Add / Update / Skip, batch_size=4)
    → [Episodic only] Reflection (跨 episode 模式识别)
    → LTM (永久存储, 向量索引)
```

### 检索信号（5 种）：
Dense (向量) + Sparse (关键词) + Reranking (cross-encoder) + Recency boost (时间加权) + Namespace filter

---

## 与 AMF 的精确对比

### 写入操作映射

| AgentCore Consolidation 输出 | AMF Write Operation |
|---|---|
| `AddMemory` | **Append** |
| `UpdateMemory` | **Replace** |
| `Skip` | "决定不存"（salience 筛选）|
| — | **Synthesize**（多记忆合并为高阶洞察）|
| — | **Expire**（时效性失效）|
| — | **Branch**（并行版本）|
| — | **Promote/Demote**（层级迁移）|

### 检索信号对比

| 信号 | AgentCore | AMF |
|------|-----------|-----|
| Vector similarity | ✅ Dense retrieval | ✅ |
| Keyword | ✅ Sparse retrieval | ✅ BM25 |
| Reranking | ✅ Cohere/Amazon rerank | ✅ Cross-encoder |
| Recency boost | ✅ 检索时加权 | ✅ + Storage-level decay |
| Namespace filter | ✅ | ✅ Hierarchy match |
| **Graph proximity** | ❌ | ✅ KG edge traversal + PPR |
| **Intent classification** | ❌ | ✅ 轻量 intent 分类器 |

### 核心架构差异

| 维度 | AgentCore | AMF |
|------|-----------|-----|
| 检索触发 | **Reactive** (Agent 调用 RetrieveMemoryRecords) | **Proactive** (消息到达时自动 <100ms) |
| LTM 生命周期 | ❌ 永久存活（除非手动 BatchDelete）| ✅ State Machine (Active→Archived→Expired) |
| 遗忘机制 | ❌ 无（靠 Consolidation Skip 控制增长）| ✅ Temporal decay + state transitions |
| Knowledge Graph | ❌ 纯向量 | ✅ Entity-relation topology |
| 用户可见性 | ❌ Developer API only | ✅ Transparency UI + user control |
| 存储模式 | Cloud (OpenSearch/Aurora) | Local-first (Markdown + SQLite) |
| 定制层级 | Built-in → Override → Self-managed | 开源，完全可修改 |

---

## 关键 Insight

### 1. AMF 的 lifecycle 从 AgentCore pipeline 终点开始

AgentCore pipeline 终点 = LTM 写入。AMF 的 state machine 从这之后管理记忆的后续生命。两者互补不冲突。

### 2. Recency Boost ≠ Temporal Decay

- AgentCore recency_boost = **检索时**加权（新记忆排名高，但旧的不消失）
- AMF temporal decay = **存储时**状态变化（旧记忆 Active → Archived → Expired）
- **两者应该共存**：storage-level decay 决定"活着吗"，retrieval-level boost 在活着的中优先返回新的

### 3. AgentCore 说"学会忘记"实际是"学会不重复记"

`Skip` 操作 = 决定不存新信息。但已有 LTM 永不过期、永不降级。
真正的"忘记"需要：① lifecycle state transition ② temporal decay ③ explicit expiration

### 4. 可借鉴的工程模式

| 模式 | 说明 |
|------|------|
| `turn_size=2` + `past_turn_size` | Extraction 按 turn 分块而非全 session |
| `batch_size=4` | 批量 Consolidation 减少 LLM 调用 |
| 临时 UUID 映射 | 安全设计，不暴露内部 ID |
| Consolidation fallback → Add | 容错：失败则直接添加 |
| Namespace `/actors/{id}/facts` | 直接映射 folder hierarchy |
| STM TTL 7-365 天 | 短期记忆有生命周期，长期没有 ← 这就是 gap |

---

## AMF 项目宗旨（2026-05-20 确认）

> **做一个覆盖所有功能的全面 fabric——但前提是每个功能经过验证确实有效果才加入。**

设计原则：
- 不是为了"多"而加功能
- 每个组件需要 ablation 证明 contribution > 0
- 如果某个组件在实验中没有 measurable gain → 不加
- "有效记忆保持精简"同样适用于 AMF 的设计本身

---

*Tags: #amf #agentcore #comparison #architecture*

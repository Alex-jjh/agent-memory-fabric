# QuickSuite (Merlin) & QuickWork Desktop 记忆系统分析
*Created: 2026-05-20 | Source: 内部代码分析 (版权内容，仅参考思路)*

---

## 一、两个系统概要

| 维度 | QuickSuite (Merlin) Gen 2 | QuickWork Desktop |
|------|--------------------------|-------------------|
| 定位 | 轻量，AgentCore 全托管 | 重量级，自建 optimizer |
| 存储 | AgentCore 云服务 | 本地 SQLite (FTS5 + sqlite-vec) |
| 提取 | AgentCore 异步 pipeline | 自建 Memory Optimizer (每 8 turn) |
| 检索 | AgentCore 语义检索 (top_k=8) | 8 条并行 pipeline + budget 分配 |
| 安全 | Bedrock Guardrail (fail-closed) | Extraction Guard + Hard Gates |
| 信心度 | 无 | Beta 分布 + citation + 指数衰减 |
| 遗忘 | 无 | Score-based trimming (超 10000 条淘汰 10%) |

---

## 二、QuickWork Desktop 的核心设计（最有参考价值）

### 2.1 它实际上已经有 Proactive Retrieval！

```
BeforeModelCallEvent → 注入相关记忆到用户消息
```

这就是我们提出的 "Proactive Retrieval Gateway" 的工业实现：
- 在 LLM 处理消息之前注入
- 不等 agent 自己决定搜不搜
- 有 budget 控制（默认 2000 tokens）

**但它的实现方式和我们设想的有差异：**
- Quick: 基于 query expansion + 8 个并行管道各自检索 → budget selection
- AMF: 基于 intent classification + entity linking + multi-signal scorer → unified ranking

### 2.2 信心度模型（Beta Distribution）— 极优雅

```python
confidence = alpha / (alpha + beta)           # 贝叶斯基础
trust = max(trust_signals)                    # 来源可信度
effective_confidence = confidence^0.7 * recent_outcome_score^0.3
```

**Citation-driven 初始信心度：**
- user_stated = 0.90
- directory_lookup = 0.85
- file_read / code_output = 0.75
- messaging_content / web = 0.50
- agent_inference = 0.50

**这比我们想的任何方案都更精细。AMF 应该直接借鉴。**

### 2.3 "遗忘"机制 — Score-based Trimming

```python
score = 0.4 * effective_confidence + 0.3 * recency_sigmoid + 0.3 * utility_ratio
# 超过 10000 条 → 淘汰 10% 最低分
# 保护: explicit provenance, global_behavior, profile/preference
```

**这是一种"被动遗忘"**——只在数量超限时才触发。和我们的 lifecycle state machine 的本质区别：
- Quick: "太满了才清理"（reactive，量触发）
- AMF: "过时了就降级"（proactive，时间/状态触发）

两者互补：AMF 的 lifecycle 管日常降级，Quick 的 trimming 管极端情况的兜底。

### 2.4 Extraction 触发策略

| 触发条件 | 说明 |
|---|---|
| 每 8 个 turn | 批量化降成本 |
| `save_to_memory` 信号 | 用户显式要求 |
| 120 秒空闲 | 对话暂停时处理 |
| 跳过：纯文本对话（无工具调用）| 无操作 = 无新知识 |

**这比 MAGMA 的 dual-stream 更实际**——不是 fast/slow 分离，而是 batched extraction + skip heuristic。

### 2.5 安全护栏（值得全套借鉴）

**Extraction Guard 8 条规则：**
1. 单一可靠来源 + 用户真实分享 + 高信心 + 未已捕获
2. 禁止推测生活事件
3. People 需唯一标识符
4. 禁止跨工具结果污染
5. 组织信息 ≠ 用户偏好
6. 处理内容 ≠ 用户资料
7. 一次性风格 ≠ 持久偏好
8. 第三方信息 ≠ 用户偏好

**Hard Gate：**
- 推断 fact 必须有 `Source: <category>.` 前缀
- 重复检测: cosine similarity > 0.85
- 信心操作互斥（每次优化每条记忆只允许一个信心修改）

---

## 三、和 AMF 的对比

### Quick Desktop 有、AMF 应该借鉴的

| Quick 的做法 | AMF 怎么借鉴 | 优先级 |
|---|---|---|
| **Beta 分布信心度** | 直接采用作为 memory 的 confidence 属性 | ★★★★★ |
| **Citation-driven 初始信心** | 写入时根据来源设定初始 alpha/beta | ★★★★★ |
| **8 管道并行 + budget 分配** | 简化为 3-4 管道（profile/facts/domain/recall）| ★★★★ |
| **Extraction Guard 8 规则** | 直接参考作为 write decision 的 heuristic | ★★★★ |
| **每 8 turn 批量触发** | 作为 slow path consolidation 的触发策略 | ★★★★ |
| **跳过无工具调用的 turn** | 降低无意义 extraction 的成本 | ★★★ |
| **Prior update summaries** | 避免重复提取相同信息 | ★★★ |
| **Anti-pattern 自动衰减** | 可以映射为我们的 state transition trigger | ★★★ |
| **Score-based trimming 兜底** | 作为 lifecycle 之外的最后防线 | ★★ |

### AMF 有、Quick Desktop 缺少的

| AMF 独特点 | 为什么 Quick 没做 | 价值 |
|---|---|---|
| **Lifecycle State Machine (4 states)** | Quick 用 trimming 代替了显式 lifecycle | 更可预测、用户可理解 |
| **Write Semantics (6 种操作)** | Quick 只有 add/update/delete | 更精细的写入控制 |
| **Graph-driven retrieval** | Quick 有 KG 但不用于 memory 检索路由 | 关系推理能力 |
| **User Transparency** | Quick 注入 `<learned_context>` 但用户看不到完整记忆 | 信任 + 可控性 |
| **Temporal decay (主动)** | Quick 只在满了才清理 | 更及时的信息降级 |
| **Local-first readable** | Quick 是 SQLite binary | 用户可直接阅读/编辑 |
| **Obsidian-compatible** | Quick 自有 UI | 接入 150 万用户生态 |

### 关键 Insight：Quick Desktop 的 KG 和 Memory 是分离的

> "Memory 系统和知识图谱共享同一个 knowledge_v1.db，但功能不同：
> - Memory: 从对话中学习的隐式知识
> - KG: 从文件/集成中显式提取的实体和关系"

**这正是我们 AMF 要打破的分离** — 在 AMF 里，KG 的 entity-relation 结构应该直接参与 memory 的检索路由（entity linking → graph traversal → vector reranking within neighborhood）。Quick 有这个基础设施但没有连通它们。

---

## 四、AMF 的设计可以从 Quick 学到的"坑"

| 可能的坑 | Quick 的经验 |
|---|---|
| Extraction 太频繁 → 成本爆炸 | 每 8 turn 批量 + 跳过纯文本对话 |
| 推断不准 → 存了错误记忆 | Extraction Guard 8 规则 + citation 要求 |
| 记忆太多 → 检索 noise | Budget 分配 + score-based trimming |
| 信心度不好校准 | Beta 分布 + recent_outcome 加权 |
| 重复存储 | cosine > 0.85 检测 + consolidation |
| 安全风险 | Fail-closed guardrail + 工具输出检查 |

---

## 五、更新 AMF 设计决策

基于 Quick Desktop 分析，AMF 增加以下设计考虑：

1. ✅ **采用 Beta 分布信心度模型**（而非简单 binary confidence）
2. ✅ **Extraction Guard 规则** 作为 write decision 的 safety layer
3. ✅ **Batched extraction** 作为 slow path 的默认触发策略
4. ✅ **Score-based trimming** 作为 lifecycle state machine 之外的兜底机制
5. ✅ **Budget allocation** 给不同 retrieval pipeline 设 token 预算
6. ✅ **打通 KG 和 Memory** — Quick 证明了两者分离的局限性

---

*Tags: #amf #quick-desktop #quicksuite #comparison #architecture #internal*

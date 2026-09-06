# Context Resolution Layer: Volatility & Freshness Rules

> **Status**: Production Standard  
> **Applicability**: Parameter stability classification and stale context prevention

---

## 1. 参数时效波动性三级分类 (Volatility Tiers)

项目上下文中的信息并非同等稳定。ScholarFlow 将所有上下文事实划分为三个波动性层级：

| 波动层级 | 稳定性特征 | 典型参数示例 | 继承与复用策略 |
|---|---|---|---|
| **`STATIC`** | 高度稳定，贯穿整个课题周期基本不变 | 目标物种学名、目标疾病生理机制、理论数学模型 | **默认长期有效**，可安全从项目历史文件中读取并复用 |
| **`SEMI_STATIC`** | 中度稳定，但在特定阶段或任务子集可能调整 | 纳排文献时间窗、语言偏好、数据抽取 Schema 字段集合 | **任务级复用**，但必须在 Stage 0 简报中向用户显式确认 |
| **`VOLATILE`** | 高度易变，随每次检索与实验进展实时更新 | 候选文献总篇数、已提取样本数、当前抽检通过率 | **严禁盲目继承历史数值**；每次必须现场重新计算或盘点 |

---

## 2. 避免过期信息锚定 (Stale Context Guard)

1. **时效性警示**：若所读取的项目文件最后修改时间超过 90 天，且涉及 `SEMI_STATIC` 维度的设置，必须在协议快照中注明 `[CONTEXT: STALE_NOTICE]`；
2. **易变数据实时核实**：对于 `VOLATILE` 类型的数据（如“当前已入库文献数”），Context Resolver 必须直接统计当前实际物理文件或题录条目，严禁直接照抄几周前历史纪要中的旧数字。

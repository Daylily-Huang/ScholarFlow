# ScholarFlow Stage 0 Decision Priority & Dimension Tiers

> **Status**: Production Standard  
> **Applicability**: Dimension classification and dynamic question selection logic

---

## 1. 四级决策层级 (Decision Tiers)

为了避免将用户淹没在琐碎的技术细节中，ScholarFlow 将所有科研决策维度划分为四个严密层级：

| 层级 | 等级名称 | 提问策略 | 解释与判定标准 |
|---|---|---|---|
| **Tier 1** | `CRITICAL` (核心关键) | **必须闭环** | 决定研究成败的核心定义。若未在用户初始提示中明确，**必须列入第一轮提问**；未解决前严禁开工。例如：研究对象范畴、纳排红线、核心因果命题。 |
| **Tier 2** | `HIGH_IMPACT` (高度影响) | **按预算择优提问** | 显著改变检索深度、抽取成本或学术争议聚类粒度，但在缺乏特定约束时可通过学科惯例推进。在不超过 3~5 题预算的前提下按影响力降序提问。例如：时间跨度、文献类型门槛、学校聚类灵敏度。 |
| **Tier 3** | `DEFAULTABLE` (默认闭环) | **静默应用默认值** | 已有成熟学术规范或安全保守默认解。**默认不提问**，直接根据学科透镜赋予推荐值，并在协议快照中标注为 `[DEFAULTED]` 供用户查阅。例如：语言范围 (中英双语)、搜索深度 (深搜2层)。 |
| **Tier 4** | `COSMETIC` (格式修饰) | **严禁在 Stage 0 提问** | 文档排版、图表配色、表格列宽、导出文件名等外围细节。**绝对禁止占用 Stage 0 宝贵的提问槽位**，推迟至最终交付前阶段 (Stage 4/5) 询问或采用标准模板。 |

---

## 2. 动态问题筛选算法 (Dynamic Selection Algorithm)

给定一个技能的全部预设维度集合 $D = \{d_1, d_2, \dots, d_n\}$，系统按以下流程输出本轮提问列表：

```text
输入:
  - 任务初始提示词 (Task Prompt)
  - 学科透镜 (Domain Lens)
  - 维度集合 D

步骤 1: 实体与意图分析
  - 解析提示词中已明确包含的信息 (例如用户写明 "筛选 2015-2023 年 CRISPR 基因编辑人体临床试验")
  - 将匹配到的维度直接标记为 [INFERRED]，移出候选提问池

步骤 2: 优先级初筛
  - 将池中剩余维度按 (Tier 1: CRITICAL) > (Tier 2: HIGH_IMPACT) 排序
  - 剔除所有 Tier 3 (DEFAULTABLE) 与 Tier 4 (COSMETIC)

步骤 3: 槽位预算截断 (Budget Cutoff: 3 ~ 5 题)
  - 首先放入所有未决的 Tier 1 维度 (假设有 k 个)
  - 若 k < 3: 从 Tier 2 中按学科影响力挑选 (3 - k) 到 (5 - k) 个填补槽位
  - 若 3 <= k <= 5: 恰好满足预算，直接输出
  - 若 k > 5: 选取影响力最高的 5 个 Tier 1 输出，其余暂时设为保守默认，若后续冲突再在 Round 2 调准

步骤 4: 默认值补全
  - 对所有未被选入提问池的 Tier 3 维度，自动注入学科透镜默认值并打上 [DEFAULTED] 标签

输出:
  - 包含 3 ~ 5 个带 (Recommended) 的高质量结构化问题
```

---

## 3. 防呆与禁忌模式 (Anti-Patterns)

1. ❌ **已知反问 (Asking the Known)**：
   - 错误案例：用户提示词已写明“只要 2020 年以后的中英文文献”，Agent 第一题仍提问“请问您希望检索哪一年的文献？”
   - 规范要求：已明确要素必须自动解析为 `[INFERRED]`，不得浪费槽位。

2. ❌ **琐碎修饰 (Cosmetic Distraction)**：
   - 错误案例：在 Stage 0 询问“综述输出时二级标题需要加粗还是斜体？”或“Markdown 表格中数值是否需要右对齐？”
   - 规范要求：Stage 0 仅关注科研边界与方法学，严禁涉及外观修饰。

3. ❌ **无理由推荐 (Unjustified Recommendation)**：
   - 错误案例：标了 `(Recommended)` 却不说明为什么推荐。
   - 规范要求：必须附带 1 句话的方法学Rationale，并标明置信度。

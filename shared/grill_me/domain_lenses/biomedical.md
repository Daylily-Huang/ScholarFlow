# Domain Lens: Biomedical & Clinical Sciences (生物医药与临床医学)

> **Lens Code**: `biomedical`  
> **Applicability**: Clinical medicine, pharmacology, epidemiology, translational research, public health

---

## 1. 学科透镜特征

- **框架基石**: 严格遵循 PICO (Population, Intervention, Comparison, Outcome) 循证分析范式；
- **证据等级 (Evidence Hierarchy)**: 系统评价/Meta分析 > 双盲RCT > 前瞻性队列 > 回顾性病例对照 > 动物实验 > 体外细胞实验；
- **核心风险**: 注册发表偏倚 (Publication Bias)、样本量不足导致假阳性、利益冲突赞助偏倚。

---

## 2. 默认科学标准与参数配置 (Tier 3 Defaults)

- **核心数据库边界**: PubMed / Europe PMC / Cochrane Library / ClinicalTrials.gov
- **文献类型门槛**: 优先同质化临床试验与观察性队列；动物及体外细胞研究在临床综述中默认排除或独立隔离
- **数据提取粒度**: 必须提取治疗组 vs 对照组样本量 (N)、效应量指标 (RR / OR / HR / MD)、95%置信区间 (CI) 及 p 值
- **偏倚风险评估**: 默认激活 Cochrane RoB 2.0 / ROBINS-I 维度映射

---

## 3. 推荐项生成偏好 (Recommendation Tendency)

- **纳入标准**: 严格限定确诊人群及标准干预方案，排除合并症复杂且未作亚组分析的混合样本 `[高置信度]`；
- **阴性结果处理**: 明确要求检索未发表试验与非显著性结果，防御发表偏倚 `[高置信度]`；
- **上下文隔离**: 强制要求同一临床试验的长期随访文章（Multiple follow-up publications of single trial）进行去重与试验编号（NCT ID）归并。

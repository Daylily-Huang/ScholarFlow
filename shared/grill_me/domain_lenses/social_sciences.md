# Domain Lens: Social & Behavioral Sciences (社会与行为科学)

> **Lens Code**: `social_sciences`  
> **Applicability**: Economics, Sociology, Psychology, Political Science, Education, Management

---

## 1. 学科透镜特征

- **方法范式**: 定量实证（因果推断、计量经济学、调查问卷实验） vs 定性深度研究（访谈、民族志、扎根理论）；
- **因果推断前沿**: 工具变量 (IV)、双重差分 (DiD)、断点回归 (RDD)、综合控制法 (Synthetic Control)；
- **核心风险**: 内生性遗漏变量偏倚 (Endogeneity / Confounding)、选择性报告与 P-hacking、问卷有效回收率不足、复现危机 (Replication Crisis)。

---

## 2. 默认科学标准与参数配置 (Tier 3 Defaults)

- **核心数据库边界**: SSRN, NBER, JSTOR, PsycINFO, Web of Science (SSCI), CNKI
- **文献类型门槛**: 优先 SSCI/CSSCI 期刊长文及 NBER/IZA 顶级工作论文
- **数据提取粒度**: 样本群体与地域、样本容量 (N)、识别策略 (Identification Strategy)、控制变量集、核心系数与标准误
- **方法隔离**: 严禁将相关性统计关联（Correlation）与因果推断结论（Causality）混同提取

---

## 3. 推荐项生成偏好 (Recommendation Tendency)

- **因果识别检验**: 优先提取通过平行趋势检验（Parallel Trends Test）或安慰剂检验（Placebo Test）的稳健结论 `[高置信度]`；
- **预注册与复现**: 优先采纳在 OSF 或 AsPredicted 预注册的研究 `[中置信度]`；
- **流派与争议**: 梳理结构性理论学派 vs 行为学派的经验实证分歧。

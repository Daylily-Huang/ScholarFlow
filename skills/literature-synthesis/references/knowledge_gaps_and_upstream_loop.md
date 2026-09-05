# 研究空白系统识别与上游闭环反馈规程 (Knowledge Gaps & Upstream Loop)

## 一、系统化研究空白分类体系 (10 Knowledge Gap Types)

学术文献综合分析的一大高阶价值，是帮助学者发掘高价值的研究空白（Knowledge Gaps）。
**严禁输出泛泛无物的套话**（如“未来需要更多研究”、“仍需加强探索”）。所有空白必须严格归类为以下 10 类具体形态之一：

| 空白类型代码 | 空白类型名称 | 判定标准与实证表征 | 典型研究启示 |
|---|---|---|---|
| **`GAP-01`** | **Evidence Gap (数据空白)** | 该科学假设在当前目标区域或物种中**完全没有任何实测数据** | 开展奠基性填补实验 |
| **`GAP-02`** | **Taxon / Cohort Gap (群体空白)** | 仅有成年个体或某一性别的研究，缺乏幼体或雌性群体的专用数据 | 针对特定亚群定向取样 |
| **`GAP-03`** | **Geographic Gap (地理空白)** | 现有研究 90% 集中于核心保护区，周边次生林或外围孤立分布区数据缺失 | 拓宽地理取样范围 |
| **`GAP-04`** | **Temporal Gap (时间空白)** | 缺乏跨年份长期监测数据，无法评估气候波动与极端天气的滞后影响 | 建立固定长期样线监测 |
| **`GAP-05`** | **Methodological Gap (方法空白)** | 仍在使用早期的传统样线或非空间模型，尚未应用先进的空间显式 SECR 模型 | 升级方法学技术路线 |
| **`GAP-06`** | **Mechanistic Gap (机制空白)** | 观测到了种群分化现象，但背后的行为隔离或生理驱动机制完全未知 | 引入生理/功能生态实验 |
| **`GAP-07`** | **Replication Gap (独立重复空白)** | 某一关键结论仅有一篇论文报告，至今未见任何第三方的独立实验复现 | 开展严格的独立平行复验 |
| **`GAP-08`** | **Scale Gap (尺度空白)** | 仅在极小微生境尺度做过调查，无法将规律外推至区域景观尺度 | 开展多尺度分层建模 |
| **`GAP-09`** | **Measurement Gap (测量指标空白)** | 仍在使用间接替代指标（如粪便堆密度），缺乏直接的个体生物学标记 | 引入微卫星/SNP高精标记 |
| **`GAP-10`** | **Contradiction Gap (争议决绝空白)** | 存在 Type A 或 Type B 的正反对立结论，但学界**尚未设计正交控制实验去专门裁决该矛盾** | **极高科研立项价值！** 设计针对性裁决实验 |

---

## 二、从学术争议派生前沿课题公式 (Research Opportunity Generator)

本技能支持利用对撞出的学术争议，自动派生具有高度立项价值的课题建议（标记为 `RESEARCH OPPORTUNITY`）：

$$\text{Research Question} = \text{Unresolved Controversy} + \text{Uncontrolled Variable} + \text{Methodological Advancement}$$

- **示例**：
  > “现有研究关于道路对特定小型鹿类基因流的影响存在显著争议（Type B/C：早期微卫星未见阻隔 vs 景观模型推测阻隔）。
  > 鉴于以往研究未严格控制道路通车年限（Uncontrolled Variable）且缺乏高分辨率基因组标记（Methodological Limitation），
  > **建议开展的前沿课题为**：基于大样本 RAD-seq 高密 SNP 标记，结合道路通车年代梯度的微景观阻力面建模，精确测定阻隔效应出现的时间滞后阈值。”

---

## 三、闭环反馈上游前序技能的任务载荷格式 (Upstream Gap Payloads)

当综合分析受阻时，必须自动在报告末尾生成机器可直接消费的【上游技能任务请求包】：

### 1. `SEARCH GAP` 任务包（发往下游 `literature-discovery-acquisition`）
```markdown
```json
{
  "gap_type": "SEARCH_GAP",
  "target_skill": "literature-discovery-acquisition",
  "reason": "缺乏 2020 年后采用 SECR 空间模型评估该物种密度的现代实证研究",
  "suggested_query": "(\"Panthera uncia\" OR \"Felidae\") AND (\"spatially explicit capture-recapture\" OR \"SECR\") AND (\"density\" OR \"abundance\")",
  "date_range": "2020-2026",
  "mode": "deep"
}
```
```

### 2. `EXTRACTION GAP` 任务包（发往下游 `literature-evidence-extraction`）
```markdown
```json
{
  "gap_type": "EXTRACTION_GAP",
  "target_skill": "literature-evidence-extraction",
  "target_paper": "2018_Author_Wildlife_Conservation.pdf",
  "reason": "当前证据表缺少该文献的 PCR 多重复孔数与等位基因脱落率控制参数，导致方法学归因受阻",
  "required_fields": [
    "PCR replicate strategy",
    "Allelic dropout rate (ADO)",
    "False allele rate (FA)",
    "Consensus genotype calling threshold"
  ],
  "mode": "extract"
}
```
```

# 结构化证据矩阵模板 (Evidence Matrix Template)

## 文献基本元数据
- **论文题目**：[Paper Title]
- **第一作者 / 通讯作者**：[Author 1 et al. / Corresponding Author]
- **发表年份与期刊**：[Year, Journal Name]
- **数字对象标识符 (DOI)**：[DOI / DOI = NR]
- **本地源文件路径**：`[File Path / PDF URI]`
- **抽取模式**：Extract Mode (标准字段抽取)
- **多实验体系说明**：[Assay-01: STR PCR / Assay-02: Species ID]

---

## 🎯 相关性前置快速剪枝评估 (Relevance Gatekeeper)
- **主题契合度打分 (0-10)**：`[ 8 / 10 ]`
- **剪枝裁决**：`[x] PROCEED (继续深度抽取)` / `[ ] PRUNE (相关性过低建议剪枝)`
- **评分简述**：[一句话说明该文献为何契合当前课题目标，或为何因研究方向偏离建议跳过全文精读]

---

## 📋 顶刊审稿人四象限审计 (Reviewer 4-Quadrant Rubric)
- **Q1 核心科学问题与动机 (Scientific Motivation)**：[本研究旨在解决的核心科学难题与保护学紧迫性]
- **Q2 前人局限与方法学瓶颈 (Prior Limitations)**：[指出了前人哪些采样缺陷、位点分辨率不足或模型假定错误]
- **Q3 本文方法学创新与设计 (Methodological Novelty)**：[提出了怎样的新型引物组、严格多管PCR方案或空间模型]
- **Q4 实验严谨性与潜在混杂 (Rigor & Confounding Caveats)**：[对照设置是否充分？阴阳性对照是否完整？有哪些潜在未控制的生态学或实验学混杂变量？]

---

## 📊 结构化事实证据表 (Verified Evidence Table)

| Field ID | Parameter Field | Assay ID | Extracted Value | Evidence Level | Verbatim Original Quote | Source Type | Location | Evidence Status | Notes / Derivation Formula |
|:---:|---|:---:|---|:---:|---|:---:|---|:---:|---|
| **M01** | Target Species | — | *Muntiacus crinifrons* | E1 | “...fecal samples from black muntjac (*Muntiacus crinifrons*)...” | Text | Page 2, Intro | SUPPORTED | 中国特有鹿科动物 |
| **M02** | Sample Size (N) | — | 108 | E1 | “A total of 108 noninvasive fecal samples were collected...” | Text | Page 3, Section 2.1 | SUPPORTED | 野外采集粪便样 |
| **P01** | Total PCR Volume | Assay-01 | 20 μL | E1 | “PCR amplifications were performed in a 20 μL reaction volume...” | Text | Page 4, Section 2.3 | SUPPORTED | 微卫星多重体系 |
| **P02** | Template DNA Volume | Assay-01 | 2.0 μL | E1 | “...containing 2.0 μL of fecal DNA template...” | Text | Page 4, Section 2.3 | SUPPORTED | — |
| **P03** | Annealing Temperature | Assay-01 | 55°C (正文) / 53°C (表1) | E1 | Methods: “annealed at 55°C”; Table 1: “Ta = 53°C” | Text & Table | Page 4 & Table 1 | CONTRADICTORY | 存在 2°C 分歧需复核 |
| **P04** | BSA Concentration | Assay-01 | NR | E4 | — | NR | Full text scanned | NOT_REPORTED | 全文未报告是否添加BSA |
| **P05** | DNA Extraction Kit | — | following Waits et al. 2001 | E3 | “DNA was extracted according to Waits et al. (2001)...” | Text | Page 3, Section 2.2 | SUPPORTED | 引用Waits 2001，细节NR |

---

## 🔍 证据链独立审查决议 (Evidence Auditor Verdict)
- **核验字段总数**：[N] 项
- **四级证据构成**：E1=[X], E2=[Y], E3=[Z], E4=[W]
- **异常警示**：CONTRADICTORY=[M1] 项, OCR_UNCERTAIN=[M2] 项
- **14 项硬指标核验**：14/14 项机械式审查通过
- **终审裁决**：**[x] PASS (放行)**
- **审查员签署**：Evidence Auditor

---

*(仅在用户于 Stage 0 明确要求解释时呈现)*
## 💡 科学解释与分析推论 (Phase C: Scientific Interpretation)
> *声明：本节为基于上述事实记录的方法学推论与横向评价，不作为原文事实论断。*
1. [推论点 1...]
2. [推论点 2...]

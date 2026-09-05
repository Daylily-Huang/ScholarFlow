# 快速精准检索案例：KRAS G12D 抑制剂耐药机制 (Quick Search Biomedical Case)

本案例演示 `literature-discovery-acquisition` Skill 在【快速探索模式 (Quick Search)】下的标准执行流。该模式追求高查准率（High Precision），旨在以最快速度抓取 10–30 篇顶尖核心文献，帮助研究者建立领域全景认知，同时遵循严谨的学术免责声明。

---

## 模式定位与免责声明

> **Quick Search 核心约束**：
> 本模式主要面向科研立项初期的靶向摸底、快速组会汇报或前沿问题定位。系统将通过四层级期刊限定与高精检索式，迅速锁定发表在顶级期刊上的 15–25 篇里程碑成果。**本检索并非系统评价级的全量穷尽检索，不进行多轮边际饱和度收敛计算。**

---

## Stage 0: 快速 Grill-Me 与协议锁定

### 1. 用户提问
> “我需要快速了解目前针对 KRAS G12D 突变小分子抑制剂的获得性耐药机制，有哪些代表性研究？请帮我找 15 篇左右最核心的高质量文献。”

### 2. Grill-Me 极速对齐
Agent 呈现解析初稿，并仅提出 1 个最关键的聚焦确认：
```markdown
【学科识别】：肿瘤药理学 / 分子靶向治疗
【推荐期刊定位】：聚焦顶刊 (Nature, Science, Cancer Discovery, NEJM, Lancet Oncology)
【预设检索模式】：Quick Search（高查准率，15–20 篇顶刊代表作）

请确认：是否严格限定近 5 年（2020–2026）经过同行评议的临床前与临床队列文献？
- (Recommended) 是，聚焦近 5 年最新突破（KRAS G12D 靶向药突破主要爆发于近数年）
- 否，需包含早期非特异性 RAS 抑制剂的历史对照文献
```
用户回复确认推荐方案。

---

## Stage 1-2: 概念矩阵与四层级期刊限定检索式

### 1. PICO 概念解构
- **P (Population/Disease)**: Non-Small Cell Lung Cancer, Pancreatic Ductal Adenocarcinoma, Colorectal Cancer, Advanced Solid Tumors.
- **I (Intervention/Target)**: KRAS G12D inhibitors (MRTX1133, RMC-6236, HRS-4642).
- **O (Outcome/Mechanism)**: Acquired resistance mechanisms, secondary mutations, bypass pathway activation (MET, EGFR amplification).

### 2. 四层级重点期刊限定式
利用 PubMed 与 OpenAlex 执行来源限制：
```text
("Cancer Discov"[Journal] OR "Nat Med"[Journal] OR "Nature"[Journal] OR "Science"[Journal] OR "Clin Cancer Res"[Journal] OR "Lancet Oncol"[Journal])
```

### 3. 精准检索式 (High-Precision Query)
```text
("KRAS G12D" OR "KRAS-G12D") AND ("inhibitor" OR "MRTX1133" OR "targeting") AND ("resistance" OR "acquired resistance" OR "bypass pathway") AND ("2020/01/01"[Date - Publication] : "3000"[Date - Publication])
```

---

## Stage 3-5: 快速执行、去重与质量初筛

1. **检索命中**：PubMed 返回 43 篇，OpenAlex 返回 38 篇；
2. **DOI 去重**：合并重复后得到 51 篇独立候选论文；
3. **期刊优先级过滤**：优先排序发表在 Tier 1 (Nature, Science, Nature Medicine, Cancer Discovery) 与 Tier 2 (Clinical Cancer Research, Cancer Research) 上的论文；
4. **精选输出**：剔除 28 篇非 G12D 专属（泛 RAS 综述）文献，精准锁定 **18 篇** 顶级实证与机制解析文献（均标注 `evidence_level: VERIFIED`）。

---

## 交付产物与报告摘要 (Deliverable Sample)

### 核心成果清单（精选展示 3 篇）

| ID | 标题 (Title) | 第一作者 | 年份 | 期刊 | DOI | 核心机制归纳 (基于摘要提取) |
|:---:|---|---|:---:|---|---|---|
| **REC01** | *Targeting KRAS(G12D) with MRTX1133 in pancreatic ductal adenocarcinoma* | Wang, X. | 2022 | *Cancer Discovery* | `10.1158/2159-8290.CD-22-0415` | MRTX1133 临床前活性及诱导免疫微环境重塑的机制 |
| **REC02** | *Genomic mechanisms of acquired resistance to KRAS G12D inhibition* | Hallin, J. | 2023 | *Nature Medicine* | `10.1038/s41591-023-02400-w` | 揭示旁路激活（MET 扩增与二次突变 Y96D）导致的获得性耐药 |
| **REC03** | *Clinical response and mechanisms of resistance to KRAS(G12D) targeting* | Tanaka, N. | 2024 | *NEJM* | `10.1056/NEJMoa2311234` | 实体瘤患者首个人体临床试验的耐药克隆演化图谱 |

> **合规警示与下一步建议**：
> 1. 上述 18 篇文献已导出为 `quick_kras_g12d_pool.bib` 与 `quick_kras_g12d_pool.csv`；
> 2. 本报告仅供快速参考。若未来用于撰写系统综述或博士开题，必须切换为 `Deep Search` 模式以执行完整的多库覆盖与引文双向追踪。

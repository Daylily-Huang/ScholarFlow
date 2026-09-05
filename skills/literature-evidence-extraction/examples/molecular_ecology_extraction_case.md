# 分子生态学文献证据抽取实战全流程案例 (Molecular Ecology Extraction Case)

## 一、案例背景与前置输入

- **目标文献**：`2021_Auth_Muntiacus_microsatellite_fecal.pdf`
- **文献题目**：*Noninvasive genetic individual identification and population estimation of black muntjac using a validated 15-microsatellite multiplex panel*
- **研究领域**：保护遗传学 / 非损伤性粪便 DNA 微卫星分型
- **用户 Prompt**：
  > “请帮我提取这篇黑麂论文里的核心实验条件，包括粪便 DNA 提取方法、微卫星多重 PCR 反应体积与各组分、退火温度、引物信息以及扩增成功率。”

---

## 二、Stage 0: 动态 Schema 协商与任务基线锁定 (Grill-Me)

### 1. Agent 快速扫描与动态 Schema 推荐
Agent 快速浏览文档目录与摘要后向用户汇报：
> “已识别论文为非损伤性分子生态学实证文献，同时包含【物种鉴定 PCR (Cytb)】与【微卫星多重 PCR (15 STR)】两个实验。
> 为防止参数混淆，建议采用动态 Schema 并启用 Assay Context 隔离：
> - 模块 1：研究样本元数据（物种、样本类型、总样本数）
> - 模块 2：DNA 提取与纯化试剂（试剂盒、洗脱体积）
> - 模块 3：[Assay-STR] 微卫星多重 PCR 体系（总体积、模板量、酶、退火温度、循环数）
> - 模块 4：[Assay-STR] 引物与多态性参数（位点数、荧光染料、等位基因跨度）
> - 模块 5：分型质控与扩增结果（成功率、多管复孔策略、等位基因丢失控制）
> 
> **请确认**：
> 1. 运行模式：`(Recommended) Extract Mode (标准结构化提取)`
> 2. 科学解释：`(Recommended) 禁用 Phase C，仅输出客观事实证据矩阵`”

### 2. 任务快照锁定
用户确认推荐方案，任务基线锁定。

---

## 三、Phase A & Phase B: 结构化事实证据矩阵交付

### 📊 结构化证据矩阵 (Verified Evidence Table)

| Field ID | Parameter Field | Assay ID | Extracted Value | Evidence Level | Verbatim Original Quote | Source Location | Status | Notes / Derivation Formula |
|:---:|---|:---:|---|:---:|---|---|:---:|---|
| **M01** | Target Species | — | *Muntiacus crinifrons* (黑麂) | E1 (EXPLICIT) | “...noninvasive genetic monitoring of the vulnerable black muntjac (*Muntiacus crinifrons*)...” | Page 1, Abstract & Intro | SUPPORTED | 确认为黑麂 |
| **M02** | Sample Type & Count | — | 108 noninvasive fecal samples | E1 (EXPLICIT) | “A total of 108 fecal pellet groups were collected from Gutianshan National Nature Reserve.” | Page 3, Section 2.1 | SUPPORTED | 粪便样本 N=108 |
| **D01** | DNA Extraction Method | — | following Waits et al. (2001) using QIAamp DNA Stool Mini Kit | E3 (REFERENCED) | “Fecal genomic DNA was extracted using the QIAamp DNA Stool Mini Kit (Qiagen) following the modified protocol by Waits et al. (2001).” | Page 3, Section 2.2 | SUPPORTED | 核心操作遵循 Waits 2001 改良方案，具体裂解时间未在此处报告 |
| **D02** | DNA Elution Volume | — | 60 μL | E1 (EXPLICIT) | “Purified DNA was eluted in 60 μL of sterile AE buffer and stored at -20°C.” | Page 3, Section 2.2 | SUPPORTED | 终洗脱体积 60 μL |
| **P01** | Total PCR Volume | Assay-STR | 10 μL | E1 (EXPLICIT) | “Multiplex PCR amplifications were conducted in a 10 μL total volume...” | Page 4, Section 2.3 | SUPPORTED | 微卫星多重体系为 10 μL |
| **P02** | Template DNA Volume | Assay-STR | 2.0 μL | E1 (EXPLICIT) | “...containing 2.0 μL of template DNA (~5–15 ng/μL)...” | Page 4, Section 2.3 | SUPPORTED | 模板加样量 2.0 μL |
| **P03** | Master Mix / Polymerase | Assay-STR | 5.0 μL Qiagen Multiplex PCR Master Mix | E1 (EXPLICIT) | “...5.0 μL 2× Qiagen Multiplex PCR Master Mix (HotStarTaq DNA Polymerase)...” | Page 4, Section 2.3 | SUPPORTED | 预混酶 2× 体系，加 5.0 μL |
| **P04** | BSA Concentration | Assay-STR | NR | E4 (NR) | — | Page 4, Section 2.3 | NOT_REPORTED | 全文检索 BSA，作者未提及添加牛血清白蛋白 |
| **P05** | Primers Total Volume | Assay-STR | 1.8 μL (15 pairs pooled) | E2 (DERIVED) | “...primer mix containing 15 fluorescently labeled primer pairs (0.12 μL each primer pair at 10 μM)...” | Page 4, Section 2.3 | SUPPORTED | 推导公式：15 × 0.12 μL = 1.8 μL |
| **P06** | Annealing Temperature ($T_a$) | Assay-STR | 55°C (正文) / 53–56°C (表1) | E1 (EXPLICIT) | 正文：“...annealed at 55°C for 90 s...”; 表1附注：“Loci Mcr-01,04 annealed at 53°C, remaining loci at 56°C.” | Page 4 & Table 1 Footnote | CONTRADICTORY | 存在方法叙述与具体位点表注冲突，多重优化后实际位点退火为梯度 |
| **P07** | PCR Cycling Times | Assay-STR | 40 cycles | E1 (EXPLICIT) | “...followed by 40 cycles of 94°C for 30 s, 55°C for 90 s, and 72°C for 60 s...” | Page 4, Section 2.3 | SUPPORTED | 粪便微卫星常采用 40 循环 |
| **R01** | Overall Genotyping Success | Assay-STR | 78.7% (85/108) | E1 (EXPLICIT) | “A total of 85 fecal samples (78.7%) yielded reliable consensus genotypes at ≥10 loci.” | Page 6, Section 3.1 | SUPPORTED | 准入达标率为 78.7% |
| **R02** | Multi-tube PCR Replicates | Assay-STR | 3–7 replicates per locus | E1 (EXPLICIT) | “Heterozygotes were confirmed after at least 3 independent PCRs; homozygotes required at least 7 identical replicates.” | Page 5, Section 2.4 | SUPPORTED | 遵循经典多管法准则 |

---

## 四、证据链独立审查决议 (Evidence Auditor Sign-off)

```markdown
---
### 🔍 证据链独立审查决议 (Evidence Auditor Verdict)
- **审查文献**：2021_Auth_Muntiacus_microsatellite_fecal.pdf
- **核验字段总数**：12 项
  - E1 (EXPLICIT 明示)：10 项
  - E2 (DERIVED 推导)：1 项 (P05 Primer total volume 1.8 μL，换算公式清晰)
  - E3 (REFERENCED 引述)：1 项 (D01 引用 Waits 2001)
  - E4 (NR 未报告)：1 项 (P04 BSA 未提及，严禁脑补)
- **异常标注**：
  - CONTRADICTORY：1 项 (P06 退火温度正文 55°C 与表注 53–56°C 冲突，已完整列出双重原句与提示)
- **14 项硬指标核查结论**：14/14 项审查全数合规，无引文伪造，无常识填空，Assay 隔离完全。
- **终审裁决**：[x] PASS (放行交付)
- **审查员签署**：Evidence Auditor
---
```

---

## 五、伴生落盘 JSON 实体 (`2021_Auth_Muntiacus_evidence.json`)

```json
{
  "paper_metadata": {
    "title": "Noninvasive genetic individual identification and population estimation of black muntjac using a validated 15-microsatellite multiplex panel",
    "authors": ["Author A", "Author B"],
    "year": 2021,
    "journal": "Molecular Ecology Resources",
    "doi": "10.1111/1755-0998.12345",
    "file_path": "d:/papers/2021_Auth_Muntiacus_microsatellite_fecal.pdf"
  },
  "extraction_metadata": {
    "mode": "extract",
    "timestamp": "2026-09-05T21:30:00Z",
    "schema_type": "dynamic"
  },
  "assays": [
    {
      "assay_id": "Assay-STR",
      "assay_name": "Microsatellite Multiplex PCR",
      "target_locus_or_gene": "15 STR Loci",
      "section": "Section 2.3 & Table 1"
    }
  ],
  "evidence_records": [
    {
      "field_id": "P01",
      "field_name": "Total PCR Volume",
      "module": "parameters",
      "assay_id": "Assay-STR",
      "extracted_value": "10 μL",
      "evidence_level": "E1_EXPLICIT",
      "verbatim_quote": "Multiplex PCR amplifications were conducted in a 10 μL total volume...",
      "source_type": "Text",
      "location": { "page": 4, "section": "Section 2.3" },
      "status": "SUPPORTED",
      "notes": "微卫星多重体系为 10 μL"
    },
    {
      "field_id": "P06",
      "field_name": "Annealing Temperature",
      "module": "parameters",
      "assay_id": "Assay-STR",
      "extracted_value": "55°C (正文) / 53–56°C (表1附注)",
      "evidence_level": "E1_EXPLICIT",
      "verbatim_quote": "正文: annealed at 55°C for 90 s; 表1: Loci Mcr-01,04 annealed at 53°C, remaining loci at 56°C.",
      "source_type": "Text",
      "location": { "page": 4, "section": "Section 2.3 & Table 1" },
      "status": "CONTRADICTORY",
      "notes": "正文与表格附注存在温度差异，实际为两档梯度"
    }
  ],
  "auditor_verdict": {
    "verdict": "PASS",
    "checklist_passed": true,
    "auditor_notes": "12/12 字段严格核验通过，P06 矛盾已透明披露。"
  }
}
```

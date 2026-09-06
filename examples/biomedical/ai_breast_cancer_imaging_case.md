# Cross-Disciplinary Case: Biomedical & Clinical Sciences

> **Research Focus**: Clinical Diagnostic Efficacy of Deep Learning Algorithms in Screening Mammography  
> **Domain Lens**: `biomedical`  
> **Workflow**: Discovery -> Evidence Extraction -> Cross-Paper Synthesis

---

## 1. Stage 0: Adaptive Grill-Me Gate (PICO Framework)

```markdown
# Stage 0 Protocol Snapshot (Biomedical)
- **Skill**: literature-discovery-acquisition
- **Domain Lens**: biomedical
- **Gate Status**: CONFIRMED

| Dimension ID | Dimension Name | Selected Setting | Provenance | Rationale |
|---|---|---|---|---|
| `D1` | 研究目标 | 临床诊断测试准确性系统评价 (DTA Meta-analysis) | `[USER]` | 遵循 PRISMA-DTA 指南 |
| `D2` | 核心问题 | AI 独立读片 vs 放射科医生双读对乳腺癌检出率的非劣效性 | `[INFERRED]` | PICO 临床假说收敛 |
| `D3` | 目标实体/人群 | 40–74岁无症状筛查女性人群 (Asymptomatic Screening Cohort) | `[USER]` | 排除有症状诊断性就诊者 |
| `D4` | 纳入标准 | 必须具备病理活检 Gold Standard 确诊与假阴性随访 | `[USER]` | 防范金标准不完全偏倚 |
| `D5` | 排除红线 | 排除未做独立测试集外部验证（External Validation）的单一中心回顾性模型 | `[SYSTEM_RULE]` | 生物医学泛化性门禁 |
```

---

## 2. Stage 1: Concept Matrix (Biomedical)

| Concept ID | 分类 | Core Term | Synonyms | Hierarchy / Clinical Category | Controlled Vocabulary |
|---|---|---|---|---|---|
| **C1** | Population | Breast Cancer Screening | mammography screening, asymptomatic women | female breast neoplasm | MeSH: Breast Neoplasms |
| **C2** | Intervention | Deep Learning CADe/CADx | artificial intelligence, convolutional neural network | CAD, AI triaging algorithm | MeSH: Deep Learning |
| **C3** | Comparator | Radiologist Double Reading | radiologist review, clinical standard of care | single reading, expert consensus | MeSH: Radiographic Image Interpretation |
| **C4** | Outcome | Diagnostic Accuracy | sensitivity, specificity, AUC-ROC | cancer detection rate, recall rate | MeSH: Sensitivity and Specificity |

---

## 3. Evidence Extraction (Context Units: Clinical Cohorts & Subgroups)

```markdown
| Field Name | [Context-01: Multi-center Screening Cohort A] | [Context-02: External Validation Cohort B] | Location | Epistemic Status |
|---|---|---|---|---|
| **Sample Size (N)** | 24,560 women (E1) | 8,240 women (E1) | Section 2.1 | SUPPORTED |
| **Cancer Detection Rate** | 6.2 per 1,000 (E1) | 5.8 per 1,000 (E1) | Table 2, Page 5 | SUPPORTED |
| **Sensitivity** | 88.2% [85.1, 90.8] (E1) | 84.6% [79.8, 88.5] (E1) | Table 3, Page 6 | SUPPORTED |
| **Specificity** | 92.4% [91.8, 93.0] (E1) | 90.1% [89.2, 91.0] (E1) | Table 3, Page 6 | SUPPORTED |
| **AUC-ROC** | 0.941 (E1) | 0.923 (E1) | Figure 3 | SUPPORTED |
| **Recall Rate Reduction** | 18.5% (E2: calculated from 9.2% vs 11.3%) | 14.2% (E2: calculated from 10.2% vs 11.9%) | Section 3.3 | DERIVED |
```

---

## 4. Synthesis & Universal Boundaries

```markdown
> **核心共识命题**: 经严格多中心外部验证的高质量 AI 算法在灵敏度和特异性上达到甚至部分超越单名初年资放射科医生水平。
> **共识评级**: `CONDITIONAL_CONSENSUS`
> **适用边界**:
> 1. **Population Boundary**: 在致密型乳腺（BI-RADS C/D 类）人群中灵敏度显著下降约 12-15%，假阳性率增加；
> 2. **Context Boundary**: 依赖全视野数字化乳腺摄影（FFDM 2D），对于数字乳腺断层合成（DBT 3D）需重新标定算法；
> 3. **Methodological Boundary**: 适用于作为“第一审查员（First reader）”初筛，最终确诊仍需临床医师复核。
```

# Cross-Disciplinary Case: Life Sciences & Wildlife Genetics

> **Research Focus**: Non-invasive Fecal DNA Microsatellite Genotyping and Population Size Estimation in Cervids  
> **Domain Lens**: `life_sciences` / `ecology_environment`  
> **Workflow**: Discovery -> Evidence Extraction -> Cross-Paper Synthesis

---

## 1. Stage 0: Adaptive Grill-Me Gate (Sampling & Genetic Markers)

```markdown
# Stage 0 Protocol Snapshot (Life Sciences)
- **Skill**: literature-discovery-acquisition
- **Domain Lens**: life_sciences
- **Gate Status**: CONFIRMED

| Dimension ID | Dimension Name | Selected Setting | Provenance | Rationale |
|---|---|---|---|---|
| `D1` | 研究目标 | 鹿科动物非损伤遗传取样与个体识别方法学综述 | `[USER]` | 规范分子生态学评估 |
| `D2` | 核心问题 | 粪便 DNA 降解率对微卫星等位基因脱落率 (ADO) 与种群估算的影响 | `[INFERRED]` | 聚焦核心技术分歧 |
| `D3` | 目标实体 | 鹿科动物 (Cervidae: Cervus, Capreolus) | `[USER]` | 明确分类学实体边界 |
| `D4` | 纳入标准 | 具备多管 PCR 重复实验数据、位点多态性指标 (PIC) 与检出率 | `[USER]` | 保障实证可比性 |
| `D5` | 排除红线 | 排除未报告阴性对照或单次扩增即定型的非可靠分型文献 | `[SYSTEM_RULE]` | 分子生态学防错红线 |
```

---

## 2. Stage 1: Concept Matrix (Life Sciences)

| Concept ID | 分类 | Core Term | Synonyms | Hierarchy / Taxon | Controlled Vocabulary |
|---|---|---|---|---|---|
| **C1** | Target System | Cervidae | deer, cervids | Cervus elaphus, Capreolus capreolus | NCBI: Cervidae |
| **C2** | Method | microsatellite | STR, short tandem repeat | multiplex PCR, capillary electrophoresis | MeSH: Microsatellite Repeats |
| **C3** | Medium/Context | fecal DNA | scat, dung, pellet | noninvasive sampling, environmental DNA | MeSH: Feces |
| **C4** | Outcome Metric | individual identification | genetic tagging, PID-sibs | capture-recapture, population size N | MeSH: DNA Fingerprinting |

---

## 3. Evidence Extraction (Context Units: Independent Assays)

```markdown
| Field Name | [Context-01: Assay Species ID (Cytb)] | [Context-02: Assay STR Multiplex (12 Loci)] | Location | Epistemic Status |
|---|---|---|---|---|
| **Target Marker** | mtDNA Cytb (420 bp) (E1) | 12 Nuclear STR Loci (110-240 bp) (E1) | Section 2.2, 2.3 | SUPPORTED |
| **Reaction Volume** | 25 μL (E1) | 10 μL (E1) | Section 2.2, 2.3 | SUPPORTED |
| **Annealing Temp** | 56°C (E1) | 52–58°C Gradient (E1) | Table 1, Page 3 | SUPPORTED |
| **Replication Strategy**| Single run (E1) | Multi-tube: 3x (hetero) / 7x (homo) (E1) | Section 2.4 | SUPPORTED |
| **Genotyping Success** | 92.4% (E1) | 71.8% (E1) | Table 2, Page 4 | SUPPORTED |
| **Mean ADO Rate** | Not Applicable (NR) (E4) | 0.042 [0.021, 0.063] (E1) | Table 3, Page 5 | SUPPORTED |
```

---

## 4. Synthesis & Universal Boundaries

```markdown
> **核心共识命题**: 在新鲜样本（<48h）且严格执行多管 PCR 重复扩增准则下，粪便微卫星分型个体识别准确率可达 98%+。
> **共识评级**: `CONDITIONAL_CONSENSUS`
> **适用边界**:
> 1. **Entity Boundary**: 经线粒体 Cytb 测序确认为目标鹿科粪便，杜绝同域分布近缘物种误采；
> 2. **Context Boundary**: 累积位点识别能力必须满足 $PID_{sibs} < 0.001$；
> 3. **Methodological Boundary**: 必须剔除扩增成功位点数 < 80% 的严重降解样本，防范伪个体（Ghost individuals）虚增种群量。
```

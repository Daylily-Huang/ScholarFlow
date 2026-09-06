# Cross-Disciplinary Case: Social & Behavioral Sciences (Economics)

> **Research Focus**: Causal Effects of Hybrid and Remote Work on Worker Productivity and Firm Retention  
> **Domain Lens**: `social_sciences`  
> **Workflow**: Discovery -> Evidence Extraction -> Cross-Paper Synthesis

---

## 1. Stage 0: Adaptive Grill-Me Gate (Causal Identification)

```markdown
# Stage 0 Protocol Snapshot (Social Sciences)
- **Skill**: literature-discovery-acquisition
- **Domain Lens**: social_sciences
- **Gate Status**: CONFIRMED

| Dimension ID | Dimension Name | Selected Setting | Provenance | Rationale |
|---|---|---|---|---|
| `D1` | 研究目标 | 远程办公因果效应量定量 Meta 分析与异质性综合 | `[USER]` | 聚焦因果推断 |
| `D2` | 核心问题 | 混合办公制 (Hybrid) 对客观工作绩效与员工流失率的因果影响 | `[INFERRED]` | 明确自变量与因变量 |
| `D3` | 目标群体 | 知识密集型行业全职白领员工 (Knowledge Workers) | `[USER]` | 排除一线体力劳动工种 |
| `D4` | 纳入标准 | 必须具备准实验设计 (DiD, IV, RDD) 或随机对照试验 (RCT) | `[USER]` | 严格排除截面相关性偏倚 |
| `D5` | 排除红线 | 排除无对照组的主观感悟问卷调查与非代表性抽样报告 | `[SYSTEM_RULE]` | 计量经济学严密性门禁 |
```

---

## 2. Stage 1: Concept Matrix (Social Sciences)

| Concept ID | 分类 | Core Term | Synonyms | Hierarchy / Construct | Controlled Vocabulary |
|---|---|---|---|---|---|
| **C1** | Target System | Knowledge Workers | professional employees, office workers | corporate staff, IT workers, engineers | JEL: J24 (Human Capital) |
| **C2** | Method/Treatment | Hybrid Work | telecommuting, working from home (WFH) | flexible work arrangement, remote work | JEL: M54 (Labor Management) |
| **C3** | Design/Setting | Randomized Workplace Trial | natural experiment, difference-in-differences | field experiment, IV regression | JEL: C93 (Field Experiments) |
| **C4** | Outcome Metric | Worker Productivity | performance ratings, weekly output volume | attrition rate, promotion rate | JEL: D24 (Productivity) |

---

## 3. Evidence Extraction (Context Units: Waves & Occupational Subgroups)

```markdown
| Field Name | [Context-01: Software Engineers (Creative)] | [Context-02: Customer Support (Routine)] | Location | Epistemic Status |
|---|---|---|---|---|
| **Identification Method** | Firm-level RCT (Trip assignment) (E1) | Firm-level RCT (Trip assignment) (E1) | Section 2.2 | SUPPORTED |
| **Sample Size (N)** | 1,612 workers (E1) | 940 workers (E1) | Table 1, Page 3 | SUPPORTED |
| **Productivity Change** | +1.8% [-0.5%, +4.1%] (p=0.14, n.s.) (E1) | +13.0% [+8.2%, +17.8%] (p<0.01) (E1) | Table 3, Page 8 | SUPPORTED |
| **Attrition Rate (Resignation)** | -35.0% relative reduction (p<0.01) (E1) | -50.0% relative reduction (p<0.01) (E1) | Section 4.1 | SUPPORTED |
| **Manager Evaluation Gap**| 0.02 SD (p=0.82, n.s.) (E1) | 0.05 SD (p=0.61, n.s.) (E1) | Table 4, Page 9 | SUPPORTED |
```

---

## 4. Synthesis & Universal Boundaries

```markdown
> **核心共识命题**: 混合办公制（每周 2-3 天到岗）在不损害整体生产率的前提下，显著降低员工离职率并改善工作满意度。
> **共识评级**: `STRONG_CONSENSUS`
> **适用边界**:
> 1. **Entity Boundary**: 仅在任务可模块化度量、且依赖数字化协同的知识型岗位中成立；
> 2. **Context Boundary**: 混合办公 (Hybrid 2-3天) 表现稳固，而完全永久远程办公 (100% Remote) 存在新人入职辅导障碍与跨部门协同摩擦；
> 3. **Methodological Boundary**: 必须控制工作时长（避免通过加班隐性补偿产出）。
```

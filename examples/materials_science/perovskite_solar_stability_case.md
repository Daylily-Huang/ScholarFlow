# Cross-Disciplinary Case: Materials Science & Chemistry

> **Research Focus**: Degradation Mechanisms and 2D/3D Interface Passivation in Perovskite Solar Cells  
> **Domain Lens**: `chemistry_materials`  
> **Workflow**: Discovery -> Evidence Extraction -> Cross-Paper Synthesis

---

## 1. Stage 0: Adaptive Grill-Me Gate

```markdown
# Stage 0 Protocol Snapshot (Materials Science)
- **Skill**: literature-discovery-acquisition
- **Domain Lens**: chemistry_materials
- **Gate Status**: CONFIRMED

| Dimension ID | Dimension Name | Selected Setting | Provenance | Rationale |
|---|---|---|---|---|
| `D1` | 研究目标 | 钙钛矿电池光照与湿热降解机理横向对比 | `[USER]` | 聚焦相变与缺陷钝化 |
| `D2` | 核心问题 | 2D/3D 异质结钝化层对抑制相分离与离子迁移的长期实效 | `[INFERRED]` | 从提示词直接提炼 |
| `D3` | 目标材料 | 甲脒基铅碘钙钛矿 (FAPbI3-based system) | `[USER]` | 采纳当前高效率主流体系 |
| `D4` | 纳入标准 | 必须具备明确的测试环境标准 (ISOS-D-2 等) 与互补物相表征 | `[USER]` | 确保条件可比性 |
| `D5` | 排除红线 | 排除未报告测试温度/湿度条件的孤立光电转化效率数据 | `[SYSTEM_RULE]` | 物理化学严谨性防错 |
```

---

## 2. Stage 1: Concept Matrix (Materials Science)

| Concept ID | 分类 | Core Term | Synonyms | Hierarchy / Composition | Controlled Vocabulary |
|---|---|---|---|---|---|
| **C1** | Target System | Perovskite Solar Cells | PSCs, hybrid organic-inorganic perovskite | FAPbI3, FA0.9Cs0.1PbI3 | Chem: Photovoltaic materials |
| **C2** | Method | Interface Passivation | 2D/3D heterojunction, surface treatment | PEAI, BDAS, 2D capping layer | Chem: Surface modification |
| **C3** | Condition | Damp Heat Testing | ISOS protocol, accelerated aging | 85°C / 85% RH, continuous 1-sun | ASTM: Environmental testing |
| **C4** | Outcome Metric | Power Conversion Efficiency | PCE, stability half-life T80 | fill factor (FF), open-circuit voltage (Voc) | IEEE: Solar energy conversion |

---

## 3. Evidence Extraction (Context Units: Synthesis Batches & Environments)

```markdown
| Field Name | [Context-01: Control FA0.9Cs0.1PbI3] | [Context-02: 2D Passivated with PEAI] | Location | Epistemic Status |
|---|---|---|---|---|
| **Initial PCE (%)** | 22.8% [22.4, 23.1] (E1) | 24.2% [23.9, 24.5] (E1) | Table 1, Page 4 | SUPPORTED |
| **Testing Protocol** | ISOS-D-2 (85°C, 85% RH) (E1) | ISOS-D-2 (85°C, 85% RH) (E1) | Section 2.4 | SUPPORTED |
| **T80 Lifetime** | 240 hours (E1) | 1,450 hours (E1) | Figure 4c | SUPPORTED |
| **Defect Density** | 1.8e16 cm^-3 (E1) | 4.2e15 cm^-3 (E1) | Table 2, Page 5 | SUPPORTED |
| **Stability Factor** | 1.0x (Baseline) | 6.04x (E2: calculated from 1450h / 240h) | Section 3.2 | DERIVED |
```

---

## 4. Synthesis & Universal Boundaries

```markdown
> **核心共识命题**: 引入疏水性芳香胺类 2D 钙钛矿包覆层，可通过界面空间位阻有效阻断水分侵蚀并大幅降低铅空位缺陷。
> **共识评级**: `STRONG_CONSENSUS`
> **适用边界**:
> 1. **Material Boundary**: 在甲脒/铯混合阳离子体系中最为稳固；在全无机 CsPbI3 体系中因界面晶格失配存在应力失效风险；
> 2. **Context Boundary**: 钝化层厚度必须控制在 5–10 nm（薄层）；厚度超过 20 nm 时因 2D 相垂直导电性差导致填充因子 FF 显著下降；
> 3. **Measurement Boundary**: 稳定性以未经封装的受控环境加速老化测试为准。
```

# ScholarFlow RFCs & Architecture Design Documents

This directory archives historical Request for Comments (RFCs) and design specifications implemented across ScholarFlow milestones.

Status vocabulary:

- `IMPLEMENTED` — every section of the document is reflected in code and covered by tests.
- `PARTIALLY IMPLEMENTED` — the named stages are implemented; later stages of the same document are still open.
- `PENDING` — the design exists but the code has not been written yet.

| RFC ID | Document Name | Target Milestone | Implementation Status |
|---|---|---|---|
| **RFC-001** | [Grill-Me 重构设计方案](./archive/ScholarFlow_Grill-Me_重构设计方案.md) | v0.5 | `IMPLEMENTED` |
| **RFC-002** | [跨学科中立化与去偏整改方案](./archive/ScholarFlow_跨学科中立化与去偏整改方案.md) | v0.5 | `IMPLEMENTED` |
| **RFC-003** | [Context-Aware Grill-Me 操作设计文档](./archive/ScholarFlow_Context-Aware_Grill-Me_操作设计文档.md) | v0.6 | `IMPLEMENTED` |
| **RFC-004** | [审查问题与整改方案](./archive/ScholarFlow_审查问题与整改方案.md) | v0.6 | `IMPLEMENTED` |
| **RFC-005** | [全仓遗留隐患扫描与整改操作手册](./archive/ScholarFlow_v0.6_全仓遗留隐患扫描与整改操作手册.md) | v0.6.1 | `IMPLEMENTED` |
| **RFC-006** | [Contract Closure 修复操作手册](./archive/ScholarFlow_v0.6.2_Contract_Closure_修复操作手册.md) | v0.6.2 | `IMPLEMENTED` |
| **RFC-007** | [Hardening 修复操作手册](./archive/ScholarFlow_v0.6.3_Hardening_修复操作手册.md) | v0.6.3 | `IMPLEMENTED` |
| **RFC-008** | [Universal Claim–Evidence Alignment 实施操作文档](./archive/ScholarFlow_Universal_Claim_Evidence_Alignment_实施操作文档.md) | v0.6.4 | `IMPLEMENTED` |
| **RFC-009** | [Skill 1 Metadata Coverage First 强化实施操作文档](./archive/ScholarFlow_Skill1_Metadata_Coverage_First_强化实施操作文档.md) | v0.6.5 | `IMPLEMENTED` |
| **RFC-010** | [Skill 2 Adaptive Evidence Context Expansion 强化实施操作文档](./archive/ScholarFlow_Skill2_Adaptive_Evidence_Context_Expansion_强化实施操作文档.md) | v0.6.5 | `IMPLEMENTED` |
| **RFC-011** | [三Skill 全仓复审与Contract Integration Closure 操作手册](./archive/ScholarFlow_三Skill_全仓复审与Contract_Integration_Closure_操作手册.md) | v0.6.4 | `IMPLEMENTED` |
| **RFC-012** | [v0.6.4 验收复审与残余问题修复操作手册](./archive/ScholarFlow_v0.6.4_验收复审与残余问题修复操作手册.md) | v0.6.4.1 | `IMPLEMENTED` |
| **RFC-013** | [文献解析抽取与跨文献综合增强操作文档](../implementation/ScholarFlow_文献解析抽取与跨文献综合增强操作文档.md) | v0.6.5 | `PARTIALLY IMPLEMENTED` — M0/F0x、M3 与 §17 D0 已落地；M1/M2/M4 与 D1–D5 仍为设计 |
| **RFC-014** | [统一执行深度架构接入操作手册](../implementation/ScholarFlow_统一执行深度接入操作手册.md) | v0.6.5 | `IMPLEMENTED` — 三档 profile、`EXECUTION_DEPTH` 门禁、T01–T20 验收 |
| **RFC-015** | [执行深度实现审查与详细修改建议（2026-09-10）](../implementation/ScholarFlow_执行深度实现审查与详细修改建议_2026-09-10.md) | v0.6.6 | `IMPLEMENTED` — R01–R12 全部修复，验收见该文档附录 |
| **RFC-016** | [研究构想与假说推敲技能设计稿](./research-idea-debate-design.md) | 新技能 `research-idea-debate` | `PARTIALLY IMPLEMENTED` — M1 完成（`skills/research-idea-debate/` 21 个文件：SKILL、7 角色、5 规程、3 schema、2 模板、2 示例、校验器）；M2 部分完成（schema + 校验器可用，事件重放/原子写入未实现）；M3/M4 未开始。未安装，未运行真实对话验收 |

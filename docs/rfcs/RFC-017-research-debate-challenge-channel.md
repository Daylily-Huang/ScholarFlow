# RFC-017：research-idea-debate 反证（CHALLENGE）通道的核验状态

- **状态**：`PROPOSED`（设计待裁定，**未实现**）
- **目标里程碑**：v0.6.7（提议）
- **前置**：`docs/implementation/ScholarFlow_四技能完整审查与改进建议_2026-09-12.md` F09（当时判定暂缓）、
  `ScholarFlow_第三次修改独立验收与评分_2026-09-13.md`（确认 F09 仍为 `DEFERRED`）
- **实测依据**：`端到端真实跑/20260913-debate闭环/`（2026-09-13 真实任务试跑，第 4 节）

---

## 1. 问题（实测，非推测）

`to_evidence_link()` 对 `relation in ("CONTEXT", "BOUNDARY", "CHALLENGE")` 一律返回
`alignment = "UNRESOLVED"`——这是**故意的**保守设计：这些关系是背景、限定或削弱，
不是支持，不得记 `VERIFIED`。

但在 2026-09-13 的真实试跑中，反证通道出现了可用性缺口：

- 抽取环节对真实 PDF 逐字核验了 5 条反证引句（`quote_audit.py` 全部 `EXACT`，数值
  `0.86` / `0.65` / `17.31%` 全部对齐），例如：
  - 学位稿：「同域分布的黑麂与小麂的营养生态位重叠 Pianka 指数高达 **0.86**，往往重叠值
    高于 0.5 即可视为……竞争排斥作用较为强烈」；
  - 胡娟：「二者……**食性十分相似**，都喜食蔷薇科、百合科和杜鹃花科等灌丛植物」，
    且「冬季……通过调整日活动节律，增加时间生态位分化程度，从而实现同域共存」。
- 这 5 条经 `ingest_returns(..., relations=CHALLENGE)` 回流后**全部停在 `UNRESOLVED`**，
  与"只是一句背景描述"在结构上**无法区分**。
- 后果：会话无法用机械字段表达"这条反证已逐字核验、方向明确、且足以动摇子命题 SP2"，
  只能靠宿主在 `summary` 里写自然语言。`decisions[]` 的 `triggered_by=EXTERNAL_OPINION`
  与 `user_confirmation` 字段也接不住"证据级反证"。

> 注意：这不是要求放松 SUPPORT 门槛，也不是要求给 `CHALLENGE` 记 `VERIFIED`。
> 缺口在于**缺少一个与 SUPPORT 同级严格、但语义独立的反证状态**。

## 2. 目标与非目标

**目标**

1. 让"已逐字核验、方向明确的反证"与"未核验的削弱性文本"可机械区分；
2. 复用一个已有、且已被反例覆盖的严格性：溯源（`artifact_ref`）、定位锚点、
   `checked_scope`、命题绑定、语义凭据（`semantic_verification` 同构）；
3. 不改变 `alignment` 的现有语义（`SUPPORT` 之外仍不是 `VERIFIED`），不破坏现有消费者。

**非目标**

- 不给 `CHALLENGE` 增加"提高主张为真"的能力；
- 不引入"反证计数→多数决"式聚合（`literature-synthesis` 的非篇数多数决原则不变）；
- 不让 AI 自证反证成立（仍需绑定凭据 + 可追溯核验记录）。

## 3. 方案

### 方案 A（推荐）：新增独立字段，不动 `alignment`

`to_evidence_link()` 为非 SUPPORT 关系新增：

```json
{
  "relation": "CHALLENGE",
  "alignment": "UNRESOLVED",              // 保持不变
  "challenge_status": "VERIFIED_CHALLENGE", // 新增：NONE | UNRESOLVED | VERIFIED_CHALLENGE | REJECTED
  "challenge_scope": "MECHANISM_DISPUTED",  // 新增：被削弱的是哪一层（MECHANISM/PREMISE/SCOPE/MAGNITUDE）
  "challenge_basis": {                      // 新增：与 SUPPORT 同级的绑定要求
    "evidence_id": "...", "artifact_ref": "...", "location_anchor": true,
    "checked_scope": "...", "proposition_fingerprint": "...",
    "verifier": "...", "verification_ref": "..."
  }
}
```

升级为 `VERIFIED_CHALLENGE` 的条件（与 SUPPORT 同构，缺一即 `UNRESOLVED`）：
`artifact_ref` 非空、定位锚点有效、`checked_scope` 非空、命题指纹匹配、语义凭据绑定完整、
且 `quote_audit` 对该引句为 `EXACT`/`OVERLAP`（引句真实存在）。

优点：零破坏（`alignment` 语义不变，旧消费者忽略新字段）；可独立回归。
代价：新增字段需要 schema 声明与消费者（`literature-synthesis` 的输入映射、HTML 报告）。

### 方案 B：扩展 `alignment` 枚举

新增 `VERIFIED_CHALLENGE` 枚举值。语义最直观，但：
`alignment` 已被 `schemas/` 与综合技能的加权逻辑消费，属于**公共契约变更**，
需要版本化迁移 + 全消费者更新 + 历史数据兼容说明。本轮不建议。

### 方案 C：只做结构化标注，不给"已核验"状态

只新增 `challenge_direction` / `challenge_strength` 枚举，任何反证都不升级。
成本最低，但没有解决"已核验 vs 未核验"无法区分的问题——不满足目标 1。

## 4. 验收标准（若实施）

1. 反例：`relation=CHALLENGE` 且缺 `artifact_ref` / 缺定位 / 缺 `checked_scope` / 缺语义凭据
   → `challenge_status=UNRESOLVED`，且**不得**影响 `alignment`（仍 `UNRESOLVED`）；
2. 反例：否定句（`NEGATION_MISMATCH`）与"词面相反但语义同向"不得被判为 `VERIFIED_CHALLENGE`；
3. 正例：真实试跑那 5 条引句（已逐字核验）→ `VERIFIED_CHALLENGE`，`challenge_scope` 正确落到
   `MECHANISM_DISPUTED`；
4. 回归：现有 `TestEvidenceAlignmentHardRules::test_boundary_and_challenge_never_verified`
   必须仍然通过——`alignment` 不得因本 RFC 变成 `VERIFIED`；
5. 文档：`docs/CAPABILITY_STATUS.md` 的 F09 行由 `DEFERRED` 更新为 `CODE_VERIFIED`（实施后），
   并说明反证状态**不参与**共识梯队加权。

## 5. 迁移影响

- `schemas/evidence_record.schema.json` 增加三个可选字段（`additionalProperties` 未收紧，向后兼容）；
- `shared/execution/debate_handoff.py::to_evidence_link` 增加分支；
- `literature-synthesis` 若要消费，需在 `comparability.py` / `contrastive` 路径显式声明；
- `docs/CAPABILITY_STATUS.md` §3.5 的 F09 行状态更新。

## 6. 待裁定问题

1. `VERIFIED_CHALLENGE` 是否必须由 `HUMAN_CONFIRMED` 复核（反证影响更大）？
2. 反证是否参与 `literature-synthesis` 的加权？若参与，权重上限如何避免"反证多数决"？
3. 是否需要 `challenge_strength`（削弱/推翻）分级，还是只保留"是否已核验 + 削弱层级"？
4. 中文命题 + 英文反证的 0.85 覆盖率门槛（见能力表「命题—引句一致性门槛」）是否同样适用于反证？

> 本 RFC 只落设计，不改代码；实施方案需先解决第 6 节四个问题。

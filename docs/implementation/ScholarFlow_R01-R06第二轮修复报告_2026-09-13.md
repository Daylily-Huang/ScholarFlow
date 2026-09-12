# R01–R06 第二轮修复报告（2026-09-13）

> 触发文档：`docs/implementation/ScholarFlow_R01-R06第二轮独立核查_2026-09-13.md`（判定 70/100，"部分验收"）。
> 前置文档：`ScholarFlow_四技能整改复核验收_2026-09-12.md`（R01–R06 原始定义）。
> 基线：本地 HEAD `d6155fa` **加**上一轮未提交改动（R01–R06 首轮修复）。
> 本报告记录本轮实际改动、验证结果、跳过项、契约迁移影响与**仍未验证**范围。

---

## 结论（先说不成立的）

- 本轮修掉了独立核查列出的 5 个问题（3 个 P1 + 2 个 P2）的**机制**，不是只挡例句。
- **仍未完成**：真实宿主四技能闭环、L3 科研质量金标、L4 工作流对照、隔离安装复用性。
- 本轮**改变了三处公共契约**（见下），旧调用方需要更新，不提供静默放行兼容层。

---

## 1. P1-1 语义核验：从"默认放行"改为"默认未决"

**原缺陷**：`verify_semantic_support()` 未命中有限黑名单时直接 `return VERIFIED / EMPIRICAL_FINDING`；
研究问句、模拟假设都被判为"经结构化语义核验的确定性实证发现"。

**改动**（`shared/execution/debate_handoff.py`）：

- 模式规则**降级为排除规则**（`_SEMANTIC_EXCLUSION_RULES`）：命中即 `UNRESOLVED` 并给出具体问题码
  （`RESEARCH_QUESTION_NOT_RESULT` / `HYPOTHESIS_NOT_RESULT` / `REFERENCED_WORK_NOT_RESULT` /
  `CONDITIONAL_NOT_RESULT` / `REFUTED_CLAIM`），新增"central question / open question / we assume /
  for this simulation we assume"等改写族与中文设问族。
- **默认返回 `UNRESOLVED` + `SEMANTIC_VERIFICATION_REQUIRED`**：未命中排除规则 ≠ 已证实。
- 只有绑定完整的显式凭据才升级（`_validate_explicit_semantic_record`）：
  `evidence_id` 必须等于本条证据、`proposition_fingerprint` 必须等于当前命题指纹、
  `verifier` 与 `verification_ref` 必须非空、语义角色必须是 `CURRENT_STUDY_RESULT` /
  `CURRENT_STUDY_OBSERVATION`；携带 `idea_version` 且与当前版本不一致 → `SEMANTIC_VERIFICATION_STALE`。
- 升级条件同时要求：命题字面支持 + 语义凭据通过 + 无其他问题。

**验证**（`tests/test_four_skill_review_f01_f06.py::TestR01SemanticSupportGate`，13 例）：
核查文档中的两条反例（`Our central question is whether …`、`For this simulation we assume …`）
现均为 `UNRESOLVED`；问句改写族 4 条全部被排除；未绑定/换命题/版本过期的凭据全部被拒；
绑定完整且版本一致的真实结果正例仍 `VERIFIED`。

---

## 2. P1-2 数值解析：完整数量 + 量纲比较

**原缺陷**：单位被丢弃或截断——`2.5 microliters` 抽成 `2.5`、`15.4%` 抽成 `4%`、`20.5` 抽成 `20`、
`0.054 meters` 与 `5.4%` 互认、`999 mL` 抽不出 token 而 `value_checked=0` 直接放行。

**改动**（`skills/literature-evidence-extraction/scripts/quote_audit.py`）：

- 新增单位表 `_UNIT_GROUPS` / `_UNIT_LOOKUP`（量纲 + 换算因子）与数量解析器
  `extract_quantities()`：符号 + 数值 + 指数 + 单位整体解析；`_NUMBER_RE` 用数字边界禁止从
  `55.4` 中间起匹配；符号只在合法位置生效（`10-20` 的 `-` 不当负号）。
- 单位匹配**区分大小写**：`mL`/`µL`/`μL`/`uL` 等常见写法显式入表；`ML`（兆升）、`Mm` 不折成
  毫升/毫米；只有 ≥4 个字母的词形单位允许忽略大小写。
- 比较改为**数值 + 量纲**：同量纲按换算因子比较（`2.5 mL == 2500 µL`，`2.5 mL ≠ 2.5 µL`）；
  跨量纲一律不匹配（百分比 ≠ 长度）；`%` ↔ 裸比例**仅当字段声明** `value_type` /
  `quantity_type` ∈ {proportion, ratio, percentage, percent} 时互认；抽取值无单位而源文是
  计数单位（samples/individuals/…）时按原值比较。
- 新增判定 `UNIT_MISMATCH`（数字对上、单位/量纲不同）与 `UNPARSEABLE_VALUE`（含数字却解析不出
  数量）；两者都计入 `unverified` 并进入 `gate_failed()` 与汇总门禁。
- 数量扫描使用保留空格的 `numeric_view()`（旧的 `fold_numeric()` 把 `2.5 microliters` 粘成
  `2.5microlitersin…`，反而破坏单位词边界）。

**验证**：核查文档 5 条数值反例全部被阻断；正例（单位别名 `20 µl`、同量纲换算 `2.5 mL` ↔ `2500 µL`、
声明比例字段的 `0.054` ↔ `5.4%`、行首/行尾/括号内数值、纯整数匹配）全部通过
（`TestR02UnitPreservationAndBareInteger`、`TestR03BoundaryAndSignAudit`）。

---

## 3. P1-3 授权核验：可信事件上下文 + 用户来源

**原缺陷**：范围指纹只是任务内容摘要，却被当作授权证明；`events=` 或 `gap._events` 可自述事件；
同 ID 的 `CHECKPOINT`/SYSTEM 事件也能让 `dispatchable=true`。

**改动**（`shared/execution/debate_handoff.py::prepare_dispatch`）：

- **删除** `events=` 参数与 `gap._events` / `gap._session_store` 回退——调用方自述的事件不构成授权证据。
- 新增 `_trusted_event_list()`：只接受带 `read_events()` / `_read_events()` 的存储对象；
  无上下文 → `CONFIRMATION_CONTEXT_MISSING`（失败关闭）。
- 新增 `_validate_confirmation_event()` 逐项核对：事件类型必须 ∈ {`GAP_CONFIRMED`, `GAP_APPROVED`,
  `USER_CONFIRMATION`}；`execution_kind` 必须为 `USER`（`SYSTEM`/`ROLE_SWITCH`/`INDEPENDENT_AGENT`/
  `SELF_CHECK` 一律拒绝）；`session_id`、`gap_id`、`idea_id`、`idea_version` 必须与缺口一致；
  事件必须携带 `scope_fingerprint` 且等于当前指纹。
- 版本绑定改为**双向必需**：`approved_idea_version` 或 `idea_version` 缺任一侧 →
  `APPROVAL_IDEA_VERSION_UNBOUND`。
- 明确拒绝码：`CONFIRMATION_EVENT_TYPE_INVALID`、`CONFIRMATION_EVENT_NOT_USER`、
  `CONFIRMATION_EVENT_GAP_MISMATCH`、`CONFIRMATION_EVENT_SCOPE_UNBOUND`、
  `CONFIRMATION_EVENT_SCOPE_MISMATCH`；`RUNNING`/`IN_PROGRESS` 仍为在途幂等拒绝。

**验证**（`TestF05ApprovalBindingGate` 18 例 + `TestR05AuthorizationTruth` 5 例，全通过）：
假事件、CHECKPOINT 事件、助手/系统事件、跨会话、跨缺口、指纹不符、缺指纹事件、缺版本、
`gap._events` 自述、无上下文——逐条独立断言；有效用户确认 + 版本一致的正例仍可派发。

---

## 4. P2-4 事件先行：绑定可信检查点与事件位置

**原缺陷**：任意当前快照都是重放基底，日志未涉及的字段无法与"未记录修改"区分；
改 docstring 不等于实施协议。

**改动**（`shared/execution/session_store.py`）：

- 新增 `CHECKPOINT_FILENAME = checkpoint.json` 与 `seal_checkpoint()`：封存**全量状态** +
  `last_event_id` + `event_count` + 事件前缀 `sha256` 摘要；封存前校验状态与事件无冲突
  （冲突 → `ProjectionError`），并把"事件从未定义、由基底承载"的字段记入 `inherited_fields`。
- `consistency_report()` 改为：有检查点 → 从**检查点状态 + 其后事件**重放，并校验前缀摘要
  （`CHECKPOINT_EVENT_PREFIX_CHANGED` / `CHECKPOINT_EVENT_MISSING`）；**没有检查点 →
  `SNAPSHOT_BASE_UNVERIFIED`，不再默认判为一致**；报告新增 `replay_base` 字段。
- CLI 新增 `seal` 子命令（`session_store_cli.py seal <dir> --expected-revision N [--session-json ...]`）。
- `save_snapshot()` 文档明确：事件先行是**调用约定**，代码无法阻止写入未记录字段；
  要机械核验须 `seal_checkpoint()`。**该整改标为 `PARTIAL`**（见能力表）。

**验证**（`TestR07EventFirstReplayBase` 5 例 + `test_research_debate_session_store.py` 3 例）：
未封存 → `SNAPSHOT_BASE_UNVERIFIED`；封存后塞入未记录 `ideas` → `STATE_PROJECTION_MISMATCH`；
前缀被改写 → `CHECKPOINT_EVENT_PREFIX_CHANGED`；与事件冲突的状态拒绝封存。

---

## 5. P2-5 Gap Schema：非 CONFIRMED 的执行限制与空关联范围

**原缺陷**：null 放宽覆盖了全部非 CONFIRMED 状态；占位可被改成 `RUNNING` 而 Schema 零报错。

**改动**（`schemas/research_debate_gap.schema.json`，`schema_version` 仍为 `0.1`）：

| 情形 | 约束 |
|---|---|
| `approval.healed_placeholder = true` | 必须 `status=PENDING`、`confirmed_event_id=null`、`scope_fingerprint=null`、`heal_reason` 非空、`execution_status=NOT_STARTED`；`idea_id`/`idea_version` 可为 null |
| 非占位 | `idea_id` 与 `idea_version` 必须是具体值 |
| `status = PENDING`（非占位） | `scope_fingerprint` 必须是具体值 |
| `status = CONFIRMED` | `confirmed_event_id`、`scope_fingerprint` 必须具体值；`execution_status` ∈ {NOT_STARTED, RUNNING, COMPLETE, PARTIAL, FAILED} |
| `status ∈ {PENDING, REJECTED, INVALIDATED}` | `execution_status` ∈ {NOT_STARTED, REFUSED_BY_USER} |

- 兼容依据写进 schema `description`：null 只对显式占位生效，既有完整产物不受影响；
  读到 null 的消费者按"未绑定占位、不得派发"处理。
- `heal_referential_integrity()` 生成占位后**立即**过 `research_debate_gap.schema.json`；
  不合规输出移入 `repair_proposals` 并记 `SCHEMA_REJECTED` 动作，不混入正式 `gap_requests`。

**验证**（`TestR08GapSchemaStateConstraints` 5 例）：占位零报错；改 `RUNNING` 被拒；
CONFIRMED 空关联被拒；普通 PENDING 缺指纹被拒；REJECTED 不得 `RUNNING`。

---

## 6. 文档一致性清理（核查 §4）

| 位置 | 改动 |
|---|---|
| `skills/literature-discovery-acquisition/SKILL.md` | Stage 8B 从"可选路径"改为**无执行分支**（遇 `PAYWALLED` 停在缺口输出）；Stage 4 标题与正文改为**两级**去重，PMID/相似度明确标为"未实现"；检查清单第 13 项标注"当前不生效" |
| `references/stage8b_browser_fallback.md` | 顶部加 `NOT_SUPPORTED — 本文档不可执行` 声明 |
| `references/stage8_oa_download.md` | 删除"自动进入 Stage 8B"指令，改为 `NO_BROWSER_FALLBACK` 停在缺口输出 |
| `references/screening_and_chasing.md` | 流程图由四级改为两级 + 虚线"规划项"节点 |
| `references/prisma_s_checklist.md`、`references/saturation_and_qc.md`、`examples/*.md` | 四级去重表述改为两级，并要求报告如实披露未做的层级 |
| `assets/download_ledger_template.md`、`role/quality_gatekeeper.md` | Stage 8B 记录项/审查项标注为"当前无执行路径" |
| `docs/CAPABILITY_STATUS.md` | 新增 `DEFERRED` 状态、事件先行可信基底（`PARTIAL`）、语义核验与数值量纲行、§6 误导清单第 12–14 条；F09 反证契约标 `DEFERRED` |

> 核查提到的「总加载量 <15KB、节约 >90%」在当前树中**已不存在**（`grep -rn "15 *KB\|节约"` 无命中）。

---

## 7. 测试与检查结果

| 项 | 结果 |
|---|---|
| 全量套件（本轮修复后） | `Ran 800 tests ... OK` |
| 新增反例回归 | `tests/test_four_skill_review_f01_f06.py` 共 87 例（F01–F06 + R01–R08） |
| 旧探针 `probe.py` | 8 项行为全部符合预期（阻断/差异报告/恢复后追加） |
| 复核探针 `recheck_probe.py` | 反例全部阻断、正例全部通过、恢复后 E1/E2 均可读、占位 schema 零报错 |
| 独立探针 `independent_r06_probe.py` | 语义两条反例 `UNRESOLVED`；5 条数值反例全部 `failed=True`；无上下文/非用户事件均被拒；未封存快照 `consistent=false`；占位改 `RUNNING` 报错 |
| `scripts/domain_neutrality_linter.py` | PASS |
| `scripts/verify_package_assets.py` | PASS |

### 跳过项（跳过 ≠ 通过）

- 本机本轮 `skipped=0`：`jsonschema 4.19.2` 已安装（严格契约测试因此真正执行），
  bash 可用（子进程用例未跳过）。**跳过为 0 不代表覆盖面变广**，只说明这两类
  "环境缺失导致的跳过"在本机没有发生。
- 隔离安装环境下的四项安装/复用性检查：**未补验**，仍属未验证。

---

## 8. 契约迁移影响（需调用方配合）

1. `prepare_dispatch(gap)` **不再能派发**：必须传 `session_store=<SessionStore>`，且会话内要有
   类型为 `GAP_CONFIRMED`、`execution_kind=USER`、绑定 gap/构想/版本/指纹的事件。
2. `to_evidence_link()` 的 `VERIFIED` **不再由词面命中决定**：记录必须带
   `semantic_verification` 凭据（`evidence_id` + `proposition_fingerprint` + `verifier` +
   `verification_ref`），否则一律 `UNRESOLVED`。
3. 数值字段：单位参与比较，跨量纲不匹配；`%` ↔ 裸比例需声明 `value_type`；
   含数字但无法解析的值会被判待核验并阻断交付。
4. `consistency_report()` 在未 `seal_checkpoint()` 的会话上返回 `consistent=false`
   （`SNAPSHOT_BASE_UNVERIFIED`）——这是有意的诚实报告，不是故障。

---

## 9. 仍未验证（不得据本轮结果外推）

- **L3 科研质量**：无真实论文金标；字段准确率、数值/单位正确率、主张方向准确率未测。
- **L4 工作流**：无同任务/同模型/同预算对照。
- **真实宿主闭环**：缺口确认 → 上游返回 → 支持/反证分别回流 → 保存 → 恢复，**尚未执行**。
- **历史数据**：旧 `VERIFIED` 记录未做审计器版本标注与重审清单。
- **事件先行**：仍无强制事件先行的写入入口（`save_snapshot()` 只是约定），标 `PARTIAL`。
- **F09 反证契约**（CHALLENGE/BOUNDARY 独立分级）：明确**暂缓**，当前保守阻断。

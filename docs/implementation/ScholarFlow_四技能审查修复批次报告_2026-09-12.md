# ScholarFlow 四技能审查修复批次报告（2026-09-12）

> 对应文档：`docs/implementation/ScholarFlow_四技能完整审查与改进建议_2026-09-12.md`（F01–F10）。
> 基线 HEAD：`5913f83`。本报告按该文档 §15 要求，分 A/B/C 三批记录改动文件、测试结果、跳过项、迁移影响与剩余未验证范围。
>
> ---
>
> ⚠️ **后续更正（2026-09-13）**：本报告的"修复完成"表述**过度**。两轮独立复核
> （`ScholarFlow_四技能整改复核验收_2026-09-12.md`、`ScholarFlow_R01-R06第二轮独立核查_2026-09-13.md`）
> 判定 F01/F02/F04/F05/F09 **只算部分通过**：当时只挡住了具体例句，通用行为未达标
> （语义核验默认放行、数值丢单位/截断、授权可省略可信上下文、快照仍被默认为可信基底）。
> 相关缺陷已在 R01–R06 第二轮修复中处理，见
> `docs/implementation/ScholarFlow_R01-R06第二轮修复报告_2026-09-13.md`。
> **不得再以本报告宣称 F01–F10 全部验收。**

---

## 批次 A：阻止错误放行（F01 / F02 / F05 / F06）

### 改动文件

| 文件 | 改动 |
|---|---|
| `shared/execution/debate_handoff.py` | F01：`_compare()` 只有 `proposition ⊂ quote` 才 `EXACT`；反向子串改判 `FRAGMENT` 并给出覆盖比；新增 `SUBSTANTIVE_COVERAGE_THRESHOLD=0.5`、`NEGATION_MARKERS`、`location_anchor()`、`upstream_audit_failed()`、`is_text_match()`、`detect_negation_mismatch()`；`to_evidence_link()` 新增 `text_match` 字段与 `INVALID_LOCATION` / `MISSING_CHECKED_SCOPE` / `UPSTREAM_AUDIT_*` / `NEGATION_MISMATCH` / `INSUFFICIENT_PROPOSITION_COVERAGE` 问题码。F05：`prepare_dispatch()` 缺指纹 → `APPROVAL_BINDING_MISSING`；新增 `confirmed_event_id` 必需 → `APPROVAL_CONFIRMATION_UNBOUND`；会话/构想版本不一致 → `SCOPE_CHANGED_APPROVAL_STALE`。 |
| `skills/literature-evidence-extraction/scripts/quote_audit.py` | F02：重写数值 token 正则（含带符号/科学计数/区间/**带单位整数**）；`_variants()` 不再生成裸数字变体；新增数字边界感知的 `_token_present()`；`NOT_IN_QUOTE_CONTEXT` / `NOT_FOUND_IN_SOURCE` 计入 `unverified`；`gate_failed()` 与摘要门禁对 `value_not_in_quote_context > 0` 一律失败。 |
| `shared/execution/session_store.py` | F06：`heal_referential_integrity()` 只写 `PENDING` 占位（`confirmed_event_id` / `scope_fingerprint` 为 `None`，标记 `healed_placeholder=True`）；无法确定 idea 归属时记 `ORPHAN_RELATION`，不再猜第一条。 |

### 复现与回归

- 反例（修复前）：`roads` 对 `roads reduce gene flow` 返回 `EXACT/1.0` 并被 `VERIFIED`；`5.4%` 在 `55.4%` 内命中；`status=CONFIRMED` 无指纹即可派发；修复器为孤儿引用伪造 `CONFIRMED` + 指纹。
- 修复后：片段引句与否定引句均 `UNRESOLVED`；三类数值反例 `strict_gate_failed=True`；裸 `CONFIRMED` → `APPROVAL_BINDING_MISSING`；占位缺口 `approval.status=PENDING`。
- 正例保持：完整覆盖引句仍 `VERIFIED`；对齐数值仍通过；指纹 + 确认事件齐备仍可派发。

### 迁移影响

- **公共契约变更**：`to_evidence_link()` 新增 `text_match` 字段；`prepare_dispatch()` 新增 `confirmed_event_id` 必需项。仅写 `approval.status=CONFIRMED` 的旧请求将回到"待重新确认"，属预期收紧，不提供静默放行兼容层。
- 历史已自动判 `VERIFIED` 的记录**未做静默删除或改判**；按审查要求应标注审计器版本并生成重审清单，此项**尚未执行**（见"剩余未验证范围"）。

---

## 批次 B：保证会话可恢复（F03 / F04）

### 改动文件

| 文件 | 改动 |
|---|---|
| `shared/execution/session_store.py` | F03：坏尾部未解除时 `append_event()` 抛 `CorruptEventLog(reason="RECOVERY_REQUIRED")`，不再把新事件拼到坏尾部之后；恢复事务移入显式入口 `rebuild(repair=True)` → `_recover_tail()`（按内容 sha256[:12] 命名隔离副本与恢复前备份，可重复执行不重复生成）；`_read_events()` 改为只读，不再就地隔离；新增 `recovery_notes()`。F04：`consistency_report()` 增加 `STATE_PROJECTION_MISMATCH`，比较 `_business_projection()`（剔除 `revision` / `_events_applied` / `last_applied_event_id` / `_*` / `recovery_*`）并列出差异字段。 |

### 复现与回归

- 反例：快照 `E1/state=CLOSED`、事件重放 `E1/state=WAITING_USER`，旧实现因末尾事件 ID 相同判为一致。
- 修复后：`consistent=False`，`divergence` 含 `STATE_PROJECTION_MISMATCH fields=['state']`；只读诊断不产生隔离文件、不改写日志；恢复后追加正常，重复恢复不新增副本。

### 迁移影响

- 旧会话只需**只读诊断**即可获得差异报告；`rebuild()` 默认 `repair=True` 会写隔离副本与恢复前备份，属有据可查的显式事务。
- 未对任何真实旧会话执行恢复（本批仅在临时目录的合成会话上验证）。

---

## 批次 C：清理入口与能力声明（F07–F10）

| 文件 | 改动 |
|---|---|
| `skills/literature-discovery-acquisition/SKILL.md` | F07：删除与执行深度冲突的"运行模式（默认科研模式）"表，改为 §2.1 执行深度三档（standard 为推荐而非默认）+ §2.2 执行模式；"四级去重"更正为"两级去重（DOI + 标题）"；Stage 8B 标注 `NOT_SUPPORTED`。 |
| `skills/literature-synthesis/SKILL.md` | F07：深度声明删除"且含敏感性分析"。 |
| `skills/research-idea-debate/SKILL.md` | F08：恢复路由改为指向 `references/convergence_and_recovery.md`（原"同上一行文件"歧义）。 |
| `skills/literature-evidence-extraction/SKILL.md` | F09：补 `NR` 五种语义（`inaccessible` / `unchecked` / `cited_only` / `derived` / `not_reported`）与五个正交维度说明；**反证独立契约迁移标为 `DEFERRED`（暂缓）**，非 SUPPORT 关系在当前契约下保守返回 `UNRESOLVED` 阻断放行。 |
| `docs/CAPABILITY_STATUS.md` | F10：标题更正为"四个 Skill"；新增 `PARTIAL` 状态；新增 §3.5 第四技能能力台账；新增 `CODE_VERIFIED` 四层验收分级（L1 结构 / L2 行为 / L3 科研质量 / L4 工作流）与测试→能力映射；§6 增加第 8–11 条误导表述；F09 反证独立契约标为 `DEFERRED`。 |
| `CLAUDE.md` | F10：同步"三个技能" → "四个技能"、能力状态定义（含 `PARTIAL` 与 `CODE_VERIFIED` 仅覆盖 L1/L2）。 |
| `tests/test_four_skill_review_f01_f06.py`（新增） | F01–F06 反例转正为自动回归（26 个用例）。 |
| `tests/test_quote_audit_gate.py` | 原"数值远离引句只标记不致命"用例改为"必须阻断交付"，与新门禁一致。 |

---

## 批次 D：整改复核验收与行为边界深化（R01–R06）

> 对应复核文档：`docs/implementation/ScholarFlow_四技能整改复核验收_2026-09-12.md`（R01–R06 及第 4 节未完成规则清理）。

### 改动文件与修复内容

| 编号 / 位置 | 缺陷与风险 | 修复机制与行为保证 |
|---|---|---|
| **R01** / `shared/execution/debate_handoff.py` | 设问句（如 `tested whether...`）因字面覆盖被升级为 `VERIFIED`；缺少 `artifact_ref` 溯源 | 新增 `verify_semantic_support()` 语义角色核验：设问（`RESEARCH_QUESTION`）、假说（`HYPOTHESIS`）、转引（`REFERENCED_WORK`）、条件句与反驳结论一律禁止升级为 `VERIFIED`，强制返回 `UNRESOLVED` 与语义诊断；强制要求非空 `artifact_ref` 溯源。 |
| **R02** / `skills/literature-evidence-extraction/scripts/quote_audit.py` | 单位互换被错误放行；负号被忽略；纯整数（如样本量 999）未受字段级核验 | 删除 `_variants()` 中的裸数字生成逻辑（彻底禁止带单位数值退化为裸数）；支持单位别名映射（µl/microliters、ml/milliliters、百分比与比值）；边界感知新增符号匹配（防止 `5.4%` 匹配 `-5.4%`）；支持纯整数 token 抽取与核验。 |
| **R03** / `skills/literature-evidence-extraction/scripts/quote_audit.py` | 句首/句尾数值由于 Python `"" in "0123456789"` 为 True 被误判为 `NOT_FOUND_IN_SOURCE` | 重构 `_token_present()` 边界探测：显式区分无相邻字符（None）与相邻字符为数字，彻底消除空串包含陷阱，保护句首、句尾、括号包围数值合法通过。 |
| **R04** / `shared/execution/session_store.py` | 事件日志最后一条为合法 JSON 但无换行时，追加导致行拼接损坏 | `append_event()` 在写盘前检测已有日志末尾字节，若非 `\n` 则自动前置换行补充分隔符，保证原有事件与新追加事件各自成独立行，E1 与 E2 均可完整读取。 |
| **R05** / `shared/execution/debate_handoff.py` | 缺口派发前版本比对字段错位；未比对事件存储；RUNNING 状态未阻断 | 修正版本比对字段：`approval.approved_idea_version` 与 `gap.idea_version` 比对；支持传入事件列表或 SessionStore 核验确认事件真实存在；新增 `RUNNING` / `IN_PROGRESS` 在途状态幂等拦截（`ALREADY_RUNNING_IN_FLIGHT`）。 |
| **R06** / `shared/execution/session_store.py` & `schemas/research_debate_gap.schema.json` | 孤儿引用修复生成的 PENDING 占位缺口缺少 `schema_version` 且不可空导致 Schema 校验失败 | 在 `new_gap` 中补齐 `schema_version: "0.1"`；在 Schema 中将 `idea_id`、`idea_version`、`scope_fingerprint` 设为全局允许可空，但在 `approval.status == "CONFIRMED"` 时通过 `allOf` 严格强制非空且有效，彻底杜绝伪造授权。 |
| **规则清理** / 多个文件 | 文档与代码存在多处遗留矛盾声明 | 1. 检索入口断开 Stage 8B 流程图连接，标题与说明标为 `NOT_SUPPORTED`，未获取文献落盘为 Acquisition Gap；<br>2. 检索入口去重标题修改为“两级去重（DOI + 标题，规划扩展为四级）”；<br>3. 检索入口删除未测算的“<15KB，节约 >90% 上下文”声明；<br>4. 抽取入口修改总则第 17 行，对齐五态细分说明；<br>5. `save_snapshot()` 注释删除虚假自动写入 CHECKPOINT 的声明，明确事件先行协议（Event-First Protocol）。 |

---

## 测试结果

| 项 | 结果 |
|---|---|
| 全量套件（修复前基线） | `Ran 709 tests ... OK (skipped=4)` |
| 全量套件（修复后，提交 `48adfed`） | `Ran 735 tests in 13.7s ... OK` |
| 新增回归 | `tests/test_four_skill_review_f01_f06.py`：26 用例全通过（F01 6 / F02 4 / F03 4 / F04 2 / F05 5 / F06 5） |
| 领域中立性 linter | `python3 scripts/domain_neutrality_linter.py` 通过 |
| 打包资产校验 | `python3 scripts/verify_package_assets.py` 通过 |

### 跳过项（跳过 ≠ 通过）

1. `jsonschema` 严格契约校验：本机未装 `[dev]`，测试跳过。
2. Windows 侧 bash 不可用导致的子进程用例：以 `@unittest.skipUnless(BASH_AVAILABLE)` 跳过。
3. 隔离安装环境的四项安装/复用性检查：**未补验**（"单技能目录复制即可用"仍不成立，技能依赖 `shared/`）。

---

## 剩余未验证范围

- **L3 科研质量**：无真实论文金标，字段准确率、数值/单位正确率、主张-证据方向准确率均未测。
- **L4 工作流**：无同任务/同模型/同预算的对照评测，召回、交付质量、时间与 token 未测。
- **真实宿主端到端流程**（缺口确认 → 上游返回 → 支持/反证回流 → 保存 → 恢复）：**尚未执行**。
- **历史记录重审**：旧 `VERIFIED` 记录未标注审计器版本、未生成重审清单。
- **隔离安装复用性**：未在可用隔离环境补验。

> 以上未验证项已在 `docs/CAPABILITY_STATUS.md` 显式标注；不得以"735 项测试通过"外推科研正确性。

# 第三次修改验收（T01–T05）修复报告（2026-09-13）

> 触发文档：`docs/implementation/ScholarFlow_第三次修改独立验收与评分_2026-09-13.md`（78/100，"不能完全验收"）。
> 基线：HEAD `a2f6950`，实现提交 `2073350`。
> 本轮范围：**只修 T01–T05**，不新增角色、不扩功能（遵循该文档"下一轮建议"）。

---

## 结论

- T01–T05 的**机制**已修：相等判定改十进制定点、单位倍率与千分比更正、未知单位诚实阻断、
  封存原子化可识别中断、零事件检查点正确重放。
- 每条反例都配了正例（换算、极小量、零值、空会话首次追加），避免"只挡反例"。
- **仍未完成**：真实宿主闭环、L3 科研质量金标、L4 工作流对照、隔离安装复用性。

---

## T01 / P1 小数量相等容差过宽

**反例**：源文 `1 nL`、抽取 `2 nL`，换算到 L 后差 1e-9，旧容差 `1e-9 * max(1, |a|, |b|)` 判为相等。

**改动**（`quote_audit.py`）：

- 单位因子改为**字符串十进制**（`"0.001"` 等），数量值改用 `decimal.Decimal` 解析与换算，
  比较为 `Decimal` **精确相等**，删除 `_NUMERIC_TOLERANCE` 与"宽容差"兜底。
- 解析、换算本身不引入二进制浮点误差，因此不需要用容差掩盖；真实差异（1 nL vs 2 nL）不再被吞。

**验证**：`1 nL ≠ 2 nL`、`0 L ≠ 1 nL`、`1 ng ≠ 2 ng`、`1 nm ≠ 2 nm` 全部阻断；
`2000 nL == 2 µL`、`2500 µL == 2.5 mL`、`2000 ng == 2 µg`、`2000 nm == 2 µm` 全部通过。

---

## T02 / P1 单位倍率与千分比

**反例**：`5 kb` 与 `5 bp` 同组（factor=1）而放行；比例字段 `0.05` 对 `5‰` 放行、
正确的 `0.005` 对 `5‰` 反被拒（percent 与 permille 都按 /100 折算）。

**改动**：

- `bp`=1、`kb`=1e3、`mb`=1e6 分列为三个倍率；体积/长度/质量各级倍率复核（`pL`=1e-12 补齐）。
- `percent` 因子 = `0.01`、`permille` 因子 = `0.001`，比例字段比较时按各自因子折算到裸比例，
  不再共用 /100。

**验证**：`5 bp ≠ 5 kb`、`1 mb ≠ 1 kb` 阻断；`5000 bp == 5 kb` 通过；
`0.05 ≠ 5‰`（比例字段）阻断、`0.005 == 5‰` 通过、`0.05 == 5%` 通过。

---

## T03 / P1 未知单位退化为无单位数字

**反例**：源文 `5 Gy`、抽取 `5 Sv`——两者都不在单位表内，于是都被解析成无量纲 5 而互相命中。

**改动**：

- `extract_quantities()` 新增 `dimension="unknown"`：数字后跟**未知或复合单位**时保留单位原文
  （`5 Sv` / `2 m/s`），不再静默降级为无单位。
- "像单位"判定保守化：紧贴数字，或空白分隔但形态为 SI 符号（`Gy`/`Sv`/`Pa`，含 µ/°/‰ 或汉字单位）；
  普通英文词（`The`/`This`/`Table`）不会误判。
- 新判定 `UNKNOWN_UNIT`：本层不支持的量纲一律标待核验并纳入硬门禁；只有字段显式声明
  `value_type=count/dimensionless/...` 时才按数值比较。未知单位之间的比较还要求**单位原文一致**。

**验证**：`5 Gy ≠ 5 Sv` 判 `UNKNOWN_UNIT` 阻断；即使 `5 Gy == 5 Gy` 也标待核验（诚实阻断）；
字段声明 `count` 时按数值比较；`20`/`30` 后跟普通英文词的既有正例不受影响。

---

## T04 / P1 封存前已覆盖检查点

**反例**：已有 WAITING_USER 检查点，用过期 `expected_revision` 封存 CLOSED → 抛 `RevisionConflict`，
但 `checkpoint.json` 已被写成 CLOSED（先写检查点、后由 `save_snapshot` 抛错）。

**改动**（`session_store.py`）：

- `seal_checkpoint()` **先校验 revision**（`_current_revision()`），不一致立即抛 `RevisionConflict`，
  此前不写任何文件。
- 快照与检查点改为**两文件一致提交**：先写 `commit_journal.json`（含两份完整载荷与 `commit_id`），
  再原子替换快照、原子替换检查点，最后删除提交日志。
- 中断识别：`consistency_report()` 检测到残留提交日志即报 `INCOMPLETE_COMMIT`（附 `commit_id`
  与 `expected_revision`，报告新增 `pending_commit_id`）；`recover_commit()` 完成或回滚该次提交。

**验证**：过期 revision 失败后**两个文件字节级不变**且无提交日志；模拟中断 → `INCOMPLETE_COMMIT`
+ `recover_commit()` → `COMMIT_COMPLETED` 且随后一致；成功封存不留日志。

---

## T05 / P2 零事件检查点跳过后续事件

**反例**：空日志封存 WAITING_USER → 追加 E1（CLOSED）→ 一致性重放仍停在 WAITING_USER、
`last_event_id=null`（`tail = events[len(events):]`）。

**改动**：重放边界改为**以已核验的 `event_count` 为准**，并新增三项校验：

- `CHECKPOINT_EVENT_COUNT_AHEAD`：`event_count` 超过日志长度（日志被截断）；
- `CHECKPOINT_EVENT_PREFIX_CHANGED`：前缀摘要不符（既有）；
- `CHECKPOINT_EVENT_BOUNDARY_MISMATCH`：`event_count` 指向的事件与 `last_event_id` 不符；
- 缺少 `event_count` 的旧检查点退回按 `last_event_id` 推断，并如实记 `CHECKPOINT_EVENT_COUNT_MISSING`。

**验证**：零事件封存后追加 E1 → `consistent=true` 且 `replayed_last_applied_event_id=E1`；
日志被清空 → `CHECKPOINT_EVENT_COUNT_AHEAD`；边界被篡改 → `CHECKPOINT_EVENT_BOUNDARY_MISMATCH`。

---

## 检查点信任边界（核查"仍需说明"一节）

**改动**：

- 检查点新增 `trust_boundary` 自述字段与 `import_mode` / `import_reason` / `import_source`；
  `consistency_report()` 暴露 `checkpoint_inherited_fields` 与 `checkpoint_import_mode`。
- **首次初始化/历史导入与日常封存分离**：已有检查点之后，若本次封存引入事件未记录的**新**业务字段，
  必须显式 `import_mode=True` **且**同时给出 `import_reason` 与 `import_source`，否则拒绝封存；
  导入信息写入检查点供审计。
- CLI `seal` 增加 `--import-mode` / `--import-reason` / `--import-source`。
- 能力表明确写：**不得宣称"全部业务状态由事件证明"**；检查点 = 事件推导字段 + 封存时已有的历史字段。

**验证**：已有检查点后追加未记录 `decisions` → `ProjectionError`；带 `import_mode` 但缺理由/来源 →
`ProjectionError`；带齐三者 → 封存成功且检查点记录 `import_source`。

---

## 自检补漏（提交 T01–T05 之后自查发现并修复）

首轮修复后自查构造反例矩阵，发现 5 个仍然放行的漏洞——**首轮并未做全**，在此如实记录：

| # | 漏洞 | 现状 |
|---|---|---|
| 1 | 源文 `5 Gy`、抽取值写成无量纲 `5`：源文扫描先用 `normalize_text()` 转小写，`Gy` 变成 `gy` 后不再"像单位"，于是静默降级为无量纲 5 并通过 | 源文数量扫描改为**保留大小写**（`numeric_view(..., fold_case=False)`），现判 `UNIT_MISMATCH` 阻断 |
| 2 | 声明 `value_type=count` 后，未知单位 `20 Gy` 能与 `20 samples` 撞上 | 未知单位一侧只在**另一侧确实无量纲**时才允许按声明比较，与已知量纲一律不可比 |
| 3 | 复合单位 `2 m/s` 只匹配到前缀 `m`，当成"2 米"通过 | 已知单位后紧跟连接符/数字（`/ · * ^ ×`、指数位）→ 整体按未知单位 `UNKNOWN_UNIT` 阻断 |
| 4 | `m2` 之类带指数单位同样只取前缀 | 同上 |
| 5 | 比例字段下 `5%` 与 `50‰` 本应等价却被拒（percent 与 permille 之间没有可比路径） | 两者在比例字段下可比并按各自倍率折算（`5% == 50‰`、`5% ≠ 5‰`） |
| 6 | 千分位 `1,000 reads` 被解析成 `1.000`，合法抽取会被误拒 | `\d{1,3}(,\d{3})+` 识别为千分位整数；`2,5` 仍按欧洲小数逗号解析 |
| 7 | 抽取值写成 `1 mb` / `999 zorks` 时，尾部陌生 token 被当成普通单词丢掉，退化为无量纲数字 | 抽取值按**严格模式**解析：数字后任何字母 token 都按单位处理，不认得即 `UNKNOWN_UNIT` 阻断 |
| 8 | `mb`（megabase / millibar）含义不明确却登记为 1e6 碱基 | 从单位表移除，按未知单位阻断；源文侧新增"两字母小写、非虚词"判据（`mb`/`cd` 等），并登记虚词表避免误判 `20 in` / `5 of` |

自查同时加固了另两条绑定（未被上述矩阵覆盖，但属同类风险）：

- **授权事件真实性**：`applied=false` 的确认事件 → `CONFIRMATION_EVENT_NOT_APPLIED`；
  同一 `event_id` 出现多次 → `CONFIRMATION_EVENT_AMBIGUOUS`；事件日志损坏 →
  `CONFIRMATION_CONTEXT_UNREADABLE`（与"没给上下文"区分，避免把损坏误报成漏参）。
- **语义凭据绑定**：凭据可携带 `quote_fingerprint` 绑定到具体引句，不符即拒
  （`SEMANTIC_VERIFICATION_QUOTE_MISMATCH`）；凭据结论与确定性排除规则冲突时**不静默通过**，
  在 `semantic_verification.semantic_warnings` 留痕供人工复核。

以上 10 项均已加入自动回归（`tests/test_third_review_t01_t05.py`、
`tests/test_four_skill_review_f01_f06.py`），并同步到
`skills/literature-evidence-extraction/SKILL.md` 与 `role/evidence_auditor.md` 的规程描述。

## 测试与检查

| 项 | 结果 |
|---|---|
| 全量套件 | `Ran 834 tests ... OK`（本机 0 跳过） |
| 新增回归 | `tests/test_third_review_t01_t05.py` 31 例（T01 5 / T02 7 / T03 10 / T04 5 / T05 4）+ `tests/test_four_skill_review_f01_f06.py` 追加 5 例自检用例 |
| 自查矩阵 | 数值层 25 条反例/正例（T01–T03 + R02/R03）全部符合预期；会话层 5 条边界（未完成提交/不可解析日志/重复封存/日志截断/前缀改写）全部符合预期 |
| 旧探针 `probe.py` / `recheck_probe.py` / `independent_r06_probe.py` | 全部反例仍阻断，正例仍通过 |
| 第三方探针 `third_review_probe.py` | `failed_seal_exception=RevisionConflict`、`checkpoint_after_failed_seal=WAITING_USER`、`empty_checkpoint_divergence=[]`、`nano_tolerance/base_unit_scale/permille_wrong_ratio/unknown_unit` 均 `failed=true`、`conversion_positive/permille_correct_ratio` 均通过 |
| `scripts/domain_neutrality_linter.py` | PASS |
| `scripts/verify_package_assets.py` | PASS |

---

## 契约迁移影响

1. 数值判定新增 `UNKNOWN_UNIT`：单位表未覆盖的单位/复合单位会被阻断（原先是静默降级）。
   需要支持时把单位加入 `_UNIT_GROUPS`（含量纲与十进制倍率），而不是放宽门禁。
2. `seal_checkpoint()` 新增 `import_mode` / `import_reason` / `import_source` 关键字参数；
   已有检查点后引入新继承字段而缺这些参数会抛 `ProjectionError`。
3. 会话目录新增 `commit_journal.json`（仅在提交过程中存在）；读到它的读者应报
   `INCOMPLETE_COMMIT` 并调用 `recover_commit()`，不要手工删除。
4. `consistency_report()` 新增字段：`pending_commit_id`、`checkpoint_inherited_fields`、
   `checkpoint_import_mode`（既有字段语义未变）。

---

## 仍未验证（不得外推）

- **真实宿主闭环**：缺口确认 → 上游返回 → 支持/反证分别回流 → 保存 → 恢复，**尚未执行**。
- **L3 科研质量**：无真实论文金标；字段准确率、数值/单位正确率、主张方向准确率未测。
- **L4 工作流**：无同任务/同模型/同预算对照。
- **隔离安装复用性**：四项安装检查仍未补验。
- **旧数据**：历史 `VERIFIED` 记录仍未标注审计器版本、未生成重审清单。
- **F09 反证契约**（CHALLENGE/BOUNDARY 独立分级）：仍为 `DEFERRED`，当前保守阻断。

# ScholarFlow 第二轮集群端到端测试报告（2026-09-13）

- **触发**：在第一轮集群测试（18 agent，发现 6 P0 + 8 P1 并完成修复 `7278934`）基础上，为了进一步检验高复杂度任务、深层跨技能交接、极端敌意对抗与持久层高并发安全性，开展第二轮多 Agent 集群测试。
- **方式**：编排 **22 个隔离 Agent**（12 个执行/验证/对抗 Agent + 2 个汇总/裁决 Agent + 4 位 Panelist [A: 正确性守门, B: 契约架构, C: 文档真相, D: 修复工程] + 1 位 Moderator 终审合议）。
  - 素材全真实：真实学术语料（PDF/文本）、真实多源检索、真实会话状态与深层构造攻击用例。
- **原始产物**：`端到端真实跑/20260913-e2e-cluster2/`（各阶段 findings.json / REPORT.md / 夹具 / 辩论立场书 / CONSENSUS.md，已受 gitignore 保护）。
- **去重结果**：12 份报告 190 条原始发现 → 经同根因合并去重为 **112 条**（H-01 至 H-112，见 `findings_matrix.json`）。
  - 严重度分布：**P0 8 条 / P1 49 条 / P2 48 条 / P3 7 条**。
  - 8 条 P0 经 harvest 与 panel 逐条核实，无一误报，全部确认为真缺陷并安排着落。

---

## 一、编排架构与评审流程

```
[01-debate] (runner / verifier)
[02-discovery] (runner / verifier)
[03-extraction] (runner / verifier / adversary)   ──▶ 12 份 findings.json ──▶ [06-harvest] (190 原始 → 112 去重)
[04-synthesis] (runner / verifier / adversary)
[05-integration] (runner / adversary)
                                                                                  │
                                                                                  ▼
                                                            [07-panel] 4 Panelists (A/B/C/D 两轮立场辩论)
                                                                                  │
                                                                                  ▼
                                                            [07-panel] Moderator 终版合议 (CONSENSUS.md)
                                                                                  │
                                                                                  ▼
                                                            施工落地: C0 ➔ B1 ➔ B2 ➔ B3 ➔ B4 ➔ B5 ➔ B6 ➔ C7
```

---

## 二、P0 缺陷与修复闭环（8 条全着落）

8 条 P0 缺陷直接涉及“产出错误科研结论”或“静默放行伪造数据”，本轮已全部完成代码修复与回归测试验证：

| 编号 | 缺陷现象与根因 | 修复落点与实现机制 | 验证结果与保护用例 |
|---|---|---|---|
| **H-01** | **方向洗白**：反向主张与证据（如 `Drug X decreases tumor growth` vs `X increases... while control decreases survival`）经全管道判为 `SUPPORTED/EXPLICIT`。根因在于 `check_polarity` 在同句含 `increase/decrease` 时判 `BOTH` 跳过比较，且无子句级谓词-宾语绑定。 | `claim_alignment.py` [B2]：拆除 L613 语义短路，实现三值化极性判断与子句级谓词绑定，混合方向句强制拒绝或降级。 | EXT-C-01 四项反向攻击均被判为 `CONTRADICTORY` 或 `UNRESOLVED`，成对正例不回归。 |
| **H-02** | **否定/反义词表缺口**：`reversed the increase in mortality` 被判支持 `increases mortality`；`neither... nor...` 与缩写（如 `don't`）未识别。三技能否定词表各自维护且互不一致。 | `shared/text/polarity.py` / `negation_lexicon.py` [B2/B3]：建立统一共享否定与反转词表，收敛各技能调用，补充 `neither/nor`、收缩词（`n't`）与动词反转（`abolish/reverse/eliminate` 等）。 | `reversed the increase`、`neither nor`、`don't reduce` 均被有效拦截；合法双重否定正常通过。 |
| **H-03** | **引句篡改容忍 + 值锚定自证 + 文本值零核验**：篡改引句中 1 个 token 恰达阈值，伪造数值在源文他处存在即判放行；`P<0.05` 篡改 `P>0.05` 翻转；文本型显著性（`not significant`）零核验直通。 | `quote_audit.py` [B2]：落地五件半边——FUZZY 值核验强制回源文邻近窗口，数值集合比对为第一道防线，双侧比较符整体核验，新增 `NOT_VERIFIABLE` 状态禁止非法提升。 | 伪造 42 改 45、P 值符号翻转均被拦截 (`FAILED` rc≠0)；`not significant` 标记为 `NOT_VERIFIABLE`；带入真实论文 FUZZY 正例护航。 |
| **H-04** | **表格对比 metric_direction 反转**：`false positive rate` 或 `infection rate` 翻倍被判目标方“胜出”。根因在于 `HIGHER_IS_BETTER` 采用脆弱黑名单。 | `claim_alignment.py` [B2]：重构为受益指标白名单（`accuracy/survival/yield...`），词表外或非受益指标标记为 `UNKNOWN_METRIC_DIRECTION` 且 `eligible=False`。 | 假阳性率、感染率、复发率翻倍均不再判胜出；正例生存率与精度保持正常。 |
| **H-05** | **非证据状态变体满权**：`support_type` 的 15 种变体（如 `NOT REPORTED`、`un-checked`、`N/A`）绕过门禁拿满权重 1.0；二级转引 `REFERENCED_ONLY` 同样满权。 | `evidence_states.py` [B1]：15 种变体统一纳入 `NON_EVIDENCE_CLASSES` 表驱动归一化为 0 权重；`REFERENCED_ONLY` 强制零权并不入共识分母；空值归 `UNPARSEABLE`。 | 变体输入一律归零，不再将未测变体计入强共识；原合法正例保持一致。 |
| **H-06** | **词表外 stance 静默归 NEUTRAL**：`REFUTED` 或非法数字/空值静默转为 `NEUTRAL`，反证证据权重无声消失，共识等级发生翻转。 | `controversy_analyzer.py` [B1]：词表外值移出共识立场分母，产物显式输出 `stance_original` 与 `invalid_stance` 标志（fail-closed）。 | 非法 stance 不再隐式变为中立稀释分母，产物完整暴露原始值与清洗痕迹。 |
| **H-07** | **反证通道全信任自声明**：伪造 `challenge_status=VERIFIED_CHALLENGE` 与虚假 `basis` 把强共识清零，内嵌矛盾凭据依然照扣分。 | `controversy_analyzer.py` [B1]：消费端执行止血语义——对 `scope` 进行严格枚举校验（拦截 `GALAXY` 等非法范围），凭据与状态矛盾时不罚并告警留痕，factors 披露封顶。 | 矛盾反证与非法 scope 均被拦截；RFC-017 正例测试保持全绿。 |
| **H-08** | **recover_commit 零校验写回 journal（授权复活）**：伪造或过期的 `commit_journal` 经自愈入口写回，可将撤销的授权复活，且使一致性检查失明。 | `session_store.py` [B3]：在 `recover_commit` 中增加 revision 单调性守卫、commit_id 前缀摘要核对；非法提交另存为 `.rejected` 归档并写入不可抵赖审计事件。 | 伪造与回退 journal 被直接拒绝；合法中断提交通过 `session_store_cli recover-commit` 正常收敛。 |

---

## 三、施工批次与改动全集 (C0–C7)

本次整改严格遵循合议施工图（CONSENSUS.md §三），按批次独立 commit 推进：

| 批次 | Commit / 说明 | 涉及核心文件 | 测试用例增量与保证 |
|---|---|---|---|
| **C0** | `38e86b5` 文档诚实化先导 | `CAPABILITY_STATUS.md`, `README.md`, `SKILL.md`, `KNOWN_ISSUES.md` | 能力表 3 行降 PARTIAL，4 行加注实测边界；README 对齐两级去重口径；RFC-016/017 标明适用域。 |
| **B1** | `737200a` synthesis 语义与资格族 | `evidence_states.py`, `controversy_analyzer.py`, `evidence_to_claim.py` | 修复 H-05, H-06, H-50, H-52, H-54, H-49, H-91, H-53 及 H-07 止血（42 测试通过）。 |
| **B2** | `1ed632a` extraction 极性与值锚定族 | `claim_alignment.py`, `quote_audit.py`, `shared/text/polarity.py`, `context_expansion.py` | 修复 H-01, H-02, H-82, H-04, H-03 (五件半边), H-30, H-32, H-33, H-35, H-37, H-17（75 测试通过）。 |
| **B3** | `2ff5a6f` session 持久层加固族 | `session_store.py`, `debate_handoff.py`, `session_store_cli.py` | 修复 H-08, H-16, H-15 (NTFS 并发 O_EXCL 锁), H-101, H-10, H-13, H-45, H-09②（39 测试通过）。 |
| **B4** | `19efaea` discovery 台账与解析族 | `agent_search.py`, `ingest_external_records.py`, `calculate_screening_agreement.py` | 修复 H-18 (CJK 按字符计长), H-23 (DOI 归一化 v2), H-24 (CNKI 冒号拆解), H-25 (GB18030 回退), H-26, H-27 (κ 同源拦截), H-60（47 测试通过）。 |
| **B5** | `97c3f7a` 校验器与 CLI 健壮性族 | `validate_session.py`, `audit_claims.py` | 修复 H-11 (成熟度段连续/时间单调), H-79 (kind 枚举), H-12 (GP6 显式报告), H-17 (schema FAIL rc=1), H-38 (完整 token 匹配), H-39, H-40 (SOURCE_UNREADABLE)（35 测试通过）。 |
| **B6** | `cb343aa` 版本可见性与预算构造 | `context.py`, `shared/build_stamp.py`, 4 技能 CLI main, `verify_package_assets.py` | 修复 H-36 (内置 build stamp + CLI --version), H-19 (RunContext 构造重放台账 + 终结 run 拒写)（30 测试通过）。 |
| **C7** | 本次收尾 | `shared/build_stamp.py`, `CAPABILITY_STATUS.md`, `tests/test_cluster2_b5_cli_robustness.py` | 刷新版本戳至最终代码提交；Windows 跨平台 UTF-8 编码加固；更新能力表验证绑定；产出本测试报告。 |

---

## 四、跨技能契约拍板与演进规则 (`CROSS_SKILL_CONTRACT_DECISIONS`)

针对第一轮与第二轮暴露的跨技能边界失明问题，Panel 合议正式形成并在 `docs/CROSS_SKILL_CONTRACT_DECISIONS_2026-09-13.md` 中固化了跨技能契约决议：

1. **威胁模型明确**：明确本契约族旨在防御**宿主 Agent 伪造输入与自我欺骗**（伪造上游产物、自我授权、跨技能交接逃逸），将其转化为 fail-closed 可检出信号。
2. **本轮拍板 10 项**：
   - H-03: 值锚定回源与 `NOT_VERIFIABLE` 状态；
   - H-05: 非证据语义归一化（15 变体表驱动零权，REFERENCED_ONLY 零权）；
   - H-07: 反证消费端止血（scope 枚举，矛盾不罚）；
   - H-14: `confirmed_by` 降为描述性，确立 `*_evidence` 成对凭据规则；
   - H-41: 反证三字段（`target_claim_id/paper_id/independence_group_id`）归 `evidence_record` 所有，确立 `challenge_basis` 必需键集；
   - H-42: 生产者必写 `artifact_ref` 与 `checked_scope`；
   - H-43: `claim_record` 为唯一 canonical 形状，拒绝双形状兼容；
   - H-49: 资格门禁接入生产为常态要求，`NEUTRAL` 出分母；
   - H-58: CLI `--format json` 输出包装为根类型 Object；
   - H-90: schema 关键节点封口方向与盘点先行。
3. **留白 5 项（维护者裁定）**：密码学通道选型 (H-09)、数量类型互认矩阵终审 (H-29)、真实链继承接线排期 (H-46)、content_hash 封口计划 (H-90)、反证主导阈值语义 (H-93)。
4. **Schema 演进规则**：严格区分 minor（加可选字段/枚举）与 major（改必填集/封口需走 RFC），杜绝为通过测试破坏契约。

---

## 五、最终验收结果

1. **全量单元测试套件**：
   - 自动化测试规模：由修复前基线 **900** 个用例扩充至 **1168** 个用例（新增 268 个针对集群测试反例与真实语料的深度回归用例）。
   - 执行结果：**1168 tests passed, 0 failures, 0 errors (skipped=4)**。
   - 严格契约测试：在 `SCHOLARFLOW_STRICT_CONTRACT_CI=1` 环境变量下，契约测试套件（50 用例）全数通过。
2. **静态与资产合规检查**：
   - `python scripts/domain_neutrality_linter.py`：**PASS**（全核心文件严格保持学科中立）。
   - `python scripts/verify_package_assets.py`：**PASS**（全资产包完整性、引擎版本、Schema 与 Manifest 检验通过）。
3. **部署版本戳与 CLI 可见性**：
   - 四个技能 CLI 支持 `--version` 命令，直接输出对应 Git Commit、时间戳与版本号。

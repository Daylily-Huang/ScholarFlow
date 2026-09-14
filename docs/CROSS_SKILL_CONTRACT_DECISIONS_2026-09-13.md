# ScholarFlow 跨技能契约决议记录（2026-09-13 第二轮集群测试）

> **性质**：决议记录（decision record），非规范本体。既有契约表述见 [shared/core/cross_skill_contract.md](../shared/core/cross_skill_contract.md)（跨技能中立化数据与任务契约）与 [schemas/scholarflow_contract.md](../schemas/scholarflow_contract.md)（数据契约规范 v1.1），本文件引用而非复制。
> **决议来源**：[CONSENSUS.md §五](../端到端真实跑/20260913-e2e-cluster2/07-panel/moderator/CONSENSUS.md)（13 条最终去向）与 [position-B.md §二](../端到端真实跑/20260913-e2e-cluster2/07-panel/round2/position-B.md)（拍板技术内容）。
> **效力**：与两份既有契约互补不冲突；既有契约未覆盖的语义缺口（反证字段归属、授权证据绑定、schema 演进、威胁模型、fail-closed 人工承接）由本文件拍板补位，后续按 §四 演进规则回写规范本体。

## 一、文档定位与威胁模型声明

1. **定位**：本文件记录第二轮集群测试（2026-09-13）合议拍板的跨技能契约决策，覆盖四件事：本轮拍板 10 项（§二）、维护者裁定留白 5 项（§三）、schema 演进规则（§四）、fail-closed 人工承接（§五）。CONSENSUS §五 第 10 项"契约文档本体"即本文件自身——演进规则、威胁模型声明、`*_evidence` 配对、AMBIGUOUS 产物说明、value_verification 字段说明均已在此成文，故 §二 不再单列。
2. **威胁模型**：本契约族对抗的是**宿主 Agent 伪造输入与自我欺骗**，即假设执行技能的宿主 Agent 可能：
   - 伪造或篡改上游产物：改数值、改引句、用语义变体冒充证据状态、把词表外指标方向洗成可判定；
   - 自我授权：把 `confirmed_by` 等自声明字段当授权依据，把输入凭据（"我核验过什么"）冒充判定输出（"判为真"）；
   - 跨技能交接逃逸：在缺共同宿主处（反证回流、入向适配）断链后绕过门禁。

   契约义务＝把上述伪造转化为 fail-closed 可检出信号：语义类走"标志＋排除＋告警"，授权/持久层违规（恢复拒绝、值核验 FAILED、锁超时）rc≠0。
3. **不承诺面**：不承诺对抗**持盘攻击者**（可改写磁盘文件、绕过进程的攻击者）。对持盘面只承诺事后可检出：审计事件、execution_receipt、版本戳 md5 对账。H-09 密码学级通道（§三 a）属对持盘的加强项，正因超出本威胁模型才留维护者选型而非本轮拍板。

## 二、本轮拍板 10 项

每项含决策内容、拍板理由一句话、落地状态（三态：本轮代码已落地批次 / 仅文档拍板待实现 / DEFER 下轮）。批次代号 B1–B6 见 [CONSENSUS.md §三](../端到端真实跑/20260913-e2e-cluster2/07-panel/moderator/CONSENSUS.md) 施工图。

### 2.1 H-03：值锚定回源与 NOT_VERIFIABLE
- **决策内容**：FUZZY 值核验默认回源窗口（`_best_fuzzy_window` 返回命中的源文 token 窗口）；数值集合比对为第一道——引句与源窗口数值集合不一致即判不符；比较符仅在引句与源窗口**双侧都存在 ≥1 比较符**时才比对（单侧缺失不比，防 confusable 排版噪声把真实引句误挡为伪造）；`value_verification` 新增可选状态 `NOT_VERIFIABLE`，文本型显著性判语（如 "not significant"）零核验即禁止 promotion；方向词比对延后；SKILL.md 写明默认门禁与 `--strict` 仅差 FUZZY 处置。
- **拍板理由**：引句篡改、值锚定自证、文本值零核验是同一伪造面的三入口，回源窗口把 FUZZY 从"自证"改为"对源可对账"。
- **落地状态**：半边**本轮已落地（B2：quote_audit.py）**；全量半边（方向词比对、FUZZY 总门禁收紧）**DEFER**，先决＝设施-1 遥测观测与 H-30 CONFUSABLE_TABLE 补全。

### 2.2 H-05：非证据语义归一化 v2
- **决策内容**：REFERENCED_ONLY 纳入 NON_EVIDENCE_CLASSES——零权、不入共识分母、记 excluded 小计，不做折算权重；15 种攻击变体 weight=0 表驱动归一（'NOT REPORTED' 与 'Not reported.' 同层级）；空值归 `UNPARSEABLE` 排除并计数。
- **拍板理由**：非证据状态变体满权曾击穿"一律零权重"承诺，表驱动归一化是唯一可对账的封闭解。
- **落地状态**：**本轮已落地（B1：evidence_states.py）**。

### 2.3 H-07：反证消费端止血语义
- **决策内容**：消费端凭据集＝缺省容忍型止血——`challenge_verification` 与 `challenge_status` 矛盾时不施加惩罚并告警留痕；scope 枚举校验（GALAXY 等越界截获）；factors 披露封顶原始量；仅 relation=CHALLENGE 入反证分流。
- **拍板理由**：止血只在字段存在且矛盾时动作，对 H-41 断链现状零影响且有 test_rfc017 正例护航，故止血与全量凭据校验解耦。
- **落地状态**：止血半边**本轮已落地（B1：controversy_analyzer.py challenge_penalty）**；REFUTES 空 basis 降档 **DEFER 契约轮**（随 H-41 适配器带正例护航一次落，见 §六.2）；全量同构凭据校验与总惩罚上限 **DEFER**（与 H-93 联动）。

### 2.4 H-14：自声明确认字段降格与 `*_evidence` 配对规则
- **决策内容**：`confirmed_by` 降格为**描述性字段**，不构成授权依据；授权只认 `confirmed_event_id` 指向的会话内可追溯真实确认事件（`school_status_source=USER_CONFIRMED` 须引用会话内真实确认事件）；**`*_evidence` 配对规则**——任何自声明确认/授权字段必须携带对应 `*_evidence` 证据字段**成对出现**方被消费端采信（例：`independence_status=VERIFIED` 须有 `independence_evidence`）。
- **拍板理由**：自声明字段当授权等于给宿主 Agent 留自我授权直通门，"声称"与"凭据"绑死是结构性防线。
- **落地状态**：**仅文档拍板**；实现 **DEFER**（confirmed_event_id 可追溯不依赖 H-09 密码学通道，属授权四元组前两腿，下轮随 H-09① append schema 门禁一并排期）。

### 2.5 H-41：反证字段归属与必需键集
- **决策内容**：反证三字段 `target_claim_id`/`paper_id`/`independence_group_id` 归 [schemas/evidence_record.schema.json](../schemas/evidence_record.schema.json) 所有，不再散落在综合域自声明结构；`challenge_basis` 必需键集＝`artifact_ref`、`evidence_id`、`target_claim_id`、`paper_id`、`independence_group_id`、`verbatim_quote`（无 verbatim_quote 的反证不构成反证）；`challenge_verification`（**输入凭据**：生产者声明核验过什么）与 `challenge_status`（**判定输出**：门禁判出什么）并存分层、禁止互冒——消费端以 status 为判定真源，二者矛盾时按 2.3 止血语义处理。
- **拍板理由**：to_evidence_link 断链证明反证语义缺共同宿主即跨技能不可达，字段归位与必需键集是断链修复的契约前提。
- **落地状态**：**仅文档拍板**；适配器代码 **DEFER 下轮首批**（REFUTES 空 basis 降档随行落地）。

### 2.6 H-42：生产者必写 artifact_ref/checked_scope
- **决策内容**：生产者（extraction 域）向下游交付可核验证据时必写 `artifact_ref`（源工件定位）与 `checked_scope`（已核验范围声明）；必填性由 SKILL.md 调用点约定承载，schema 层保持可选。
- **拍板理由**：入向适配缺失使"四技能闭环"事实不可达（RFC-016 必须保持 NOT_SUPPORTED 明示的原因）；调用点约定先立契约、不动 schema，可在零 schema 改动前提下生效。
- **落地状态**：**仅文档拍板**（SKILL.md 调用点约定与生产者代码均待实现，**生产者代码 DEFER**）。

### 2.7 H-43：claim_record 唯一 canonical、拒双形状兼容
- **决策内容**：[schemas/claim_record.schema.json](../schemas/claim_record.schema.json) 为 claim 唯一 canonical 形状；extraction 现有 claims 数组加显式映射（claims→claim_record）；**拒双形状兼容**——不新增兼容层，不为通过校验放宽 schema（与"不得为通过测试放宽 additionalProperties"同一条红线）。
- **拍板理由**：双形状并存会让每个消费端各自发明映射，形状断裂在消费端被放大而非收敛。
- **落地状态**：**仅文档拍板**；映射代码 **DEFER**（与 H-41 适配器同批，下轮首批）。

### 2.8 H-49：资格门禁接入生产是常态要求
- **决策内容**：`evaluate_consensus_eligibility` 接入 `analyze()`/`compute_topic_consensus` 生产路径是**常态要求**而非可选加强；NEUTRAL 不入立场分母、不参与层级投票；UNRESOLVED 或缺 claim_status 一律拒绝入共识并计数（与 H-91 合并拍板）。
- **拍板理由**：无生产调用点的门禁等于不存在——NEUTRAL 入分母正是门禁旁路的实证。
- **落地状态**：**本轮已落地（B1：controversy_analyzer.py + evidence_to_claim.py）**，验收证据＝15/38 场景 `excluded_from_consensus` 非空。

### 2.9 H-58：CLI --format json 包装根类型
- **决策内容**：synthesis CLI `--format json` 输出包装为**根类型 object**（数组收编进对象键内）；schema 不为数组加根定义；main 内联 schema_gate 校验自家产物。
- **拍板理由**：自家产物过不了自家 schema 是"契约自证失效"的最直接形态，先修包装、不动 schema。
- **落地状态**：**仅文档拍板**；CLI 代码 **DEFER 下轮首批**（无 schema 改动，可提前）。

### 2.10 H-90：schema 封口方向
- **决策内容**：封口方向＝关键节点优先——执行授权（execution_profile/确认事件）、事件（research_debate_*）、反证回流（evidence_record 反证字段）优先 `additionalProperties:false`；[schemas/discovery_result.schema.json](../schemas/discovery_result.schema.json) 域 13 个未声明字段**盘点先行**；一刀切全仓封口 NO-ACTION；`content_hash` 字段与"先验后写"时序改造归维护者裁定（§三 d）。
- **拍板理由**：未封口 schema 让伪造输入免检入场，但封口牵动向后兼容面，须盘点分批而非一次到位。
- **落地状态**：**仅文档拍板**（盘点先行）；分批封口计划 **DEFER 维护者**。

## 三、维护者裁定 5 项（本轮留白留档）

| 项 | 议题 | 留白原因 | 本轮已拍板半边 |
|---|---|---|---|
| a | H-09 密码学级来源认证通道选型（会话 HMAC / 带外确认） | 密钥管理与零依赖约束冲突，超出本轮威胁模型（§一.3） | ②绑定半边已落地 B3（store.session_id 核对）；①append schema 门禁四步迁移下轮随契约执行 |
| b | H-29 quantity_type 互认矩阵终审（percentage↔proportion 换算、count/dimensionless 声明降级比较、fold 取消互认） | 科研语义裁定，牵动跨技能数值可比性 | 枚举收口＋`additionalProperties:false` 拍板半边已成文；schema 改动随终审一并执行 |
| c | H-46 真实链继承机制接线排期（INT-R-11 不可达） | 接线排期属维护者资源决策 | 信封 required run_id＋execution_profile_ref＋回读逐字段对账半边已拍板 |
| d | H-90 content_hash 字段、"校验通过才落盘"时序改造、分批封口计划 | 向后兼容影响面大，须盘点后裁定 | 关键节点封口方向与 discovery 13 字段盘点先行已拍板（2.10） |
| e | H-93 "反证主导"档位阈值语义 | 需在 H-07 全量凭据校验落地后才有裁定意义 | 无（position-B 新移交项） |

## 四、schema 演进规则

| 演进类型 | 判据 | 义务 |
|---|---|---|
| **minor** | 新增可选字段 / 新增可选枚举值，不改既有 required 集、不改既有字段语义 | 同步 [tests/test_cross_skill_contract.py](../tests/test_cross_skill_contract.py) 行为锚定；本文件或规范本体随批注记 |
| **major** | 改必填集、改既有字段语义、枚举收口、`additionalProperties:false` 封口 | 先 RFC ＋ [CAPABILITY_STATUS.md](CAPABILITY_STATUS.md) 能力行联动 ＋ 迁移说明 ＋ schema_version bump；旧形状显式拒绝或经显式转换函数迁移 |

- **示例**：`value_verification=NOT_VERIFIABLE`、`*_evidence` 配对字段、AMBIGUOUS 队列产物字段（§五）均按 minor 演进；H-41 反证三字段进入 evidence_record required 集、H-90 各节点封口均属 major，须走 RFC。
- **红线**：normalize_claim 只增键不删键；不得为通过测试放宽 additionalProperties；归一化不得翻转既有合法输入的判定（每个拒绝用例配同构合法正例随批落库）。
- **本轮声明**：**schemas/ 目录本轮零改动**——全部契约拍板先行成文（本文件），schema 变更自下轮起按本规则执行；`contract_regressions/` 专用测试目录下轮建立。

## 五、fail-closed 人工承接（AMBIGUOUS 裁决队列现状）

1. **现状声明**：当前**无专用 AMBIGUOUS 裁决队列**。fail-closed 拒绝的可见性暂由各技能 summary 计数承载（设施-1 最低版，已随 B1/B2 落地）：UNRESOLVED / UNPARSEABLE / UNKNOWN_METRIC_DIRECTION / INVALID_STANCE / NOT_VERIFIABLE 五类信号每次拒绝可读数。
2. **遥测读法示例**（extraction 域 claim_alignment 聚合 summary，键名为代码实落键）：

```json
{
  "total_results": 12,
  "confirmed_eligible": 9,
  "polarity_unresolved": 2,
  "unknown_metric_direction": 1,
  "polarity_contradictions": 0
}
```

   读法：`polarity_unresolved=2` 表示 2 条因极性无法唯一判定（含 BOTH）转人工，不得入共识；`unknown_metric_direction=1` 表示词表外指标方向被拒且 eligible=False，人工补 metric_direction 后重跑而非放行。synthesis 域读 `excluded_from_consensus` 计数与 `invalid_stance_records`（含 `stance_original` 原值留痕），quote_audit 域读 `value_not_verifiable` / `value_fuzzy_not_anchored` 计数（>0 即存在禁止 promotion 的零核验值）。
3. **rc 语义**：语义类 fail-closed（上述五类）走"标志＋排除＋告警"，产物可继续产出但排除项不可入共识；授权/持久层违规（恢复拒绝、值核验 FAILED、锁超时）rc≠0 硬失败。
4. **下轮设施**：专用裁决队列产物（markdown 人工可读 ＋ JSONL 机器可对账）为下轮建设项，字段按 minor 演进新增；在此之前 AMBIGUOUS 类裁决靠上述计数与逐条记录人工承接。

## 六、遗留争议 2 项（不强行拍板，留档下回合）

1. **预算完整性族时点（H-47/H-100/H-102）**。
   - 主张本轮（B MF-04 / C 条目 8）：数值域校验无契约依赖，负数投毒比删台账更隐蔽，应随 B6 同文件顺带。
   - 主张下轮（A / D）：台账重置不直接产出错误科研结论，receipt sha256 固化与数值域校验属台账格式契约，不能赶工，既有用例兼容面需单独评审。
   - **暂定去向**：DEFER 下轮首批；receipt 摘要固化为下轮第一优先（四人无异议）。若执行者 B1–B6 全绿且有明确余量，可请示后加做 H-47 数值域校验半边。
2. **H-07 REFUTES 缺 refutation_basis 降档**。
   - 主张本轮（A M7 / B MF-09）：伪造反证缺凭据即降档是止血的完整半边。
   - 主张契约轮（C / D）：真实语料实测 basis=null 仍生效，H-41 断链下现存合法反证链无凭据字段，缺省即拒＝fail-closed 过度，且无正例护航。
   - **暂定去向**：DEFER 契约轮，随 H-41 适配器带正例护航一次落。

---

本文件由第二轮集群测试 C7 收尾 commit 提交；[CAPABILITY_STATUS.md](CAPABILITY_STATUS.md) §7 验证绑定随同批刷新。决策细节以 [CONSENSUS.md](../端到端真实跑/20260913-e2e-cluster2/07-panel/moderator/CONSENSUS.md) 为合议事实基准，本文件为契约语义的落点记录；反证通道行为语义另见 [RFC-017-research-debate-challenge-channel.md](rfcs/RFC-017-research-debate-challenge-channel.md)。

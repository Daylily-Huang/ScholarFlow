---
name: research-idea-debate
description: 研究构想与假说推敲技能。从一句模糊直觉或一个既有论断出发，通过用户每轮参与、单焦点提问的多角色讨论，明确概念与比较基准、检查承重前提与证据、推导可观察预测与改判条件、生成并区分竞争解释，最终产出候选研究问题或最小验证方案。内置五类苏格拉底视角（概念澄清者／前提与证据审查者／推论与验证者／替代解释探索者／观点修订引导者）、主持人 P0–P6 动态调度阶梯、想法成熟度守卫（RAW/DEVELOPING/TESTABLE）、关键节点的隔离独立评估与确定性分歧判定、查证缺口先确认后执行的交接规程，以及单写者事件恢复。允许没有任何文献时启动；不代替文献检索、抽取与跨文献综合，需要时按确认范围交接给前三个技能。
---

# 研究构想与假说推敲专业技能 (research-idea-debate)

本技能用于在严谨科研场景下，把**模糊直觉**发展成可讨论的研究构想，或对**已有论断**推敲其依据、边界与检验办法（Research Idea Development & Hypothesis Scrutiny）。核心特征是：**用户每轮参与讨论**，而不是观看 AI 自行演完一场辩论。

> **核心哲学**：
> 本技能是 **Thinking Partner（思考搭档）**，不是 Judge（裁判），也不是 Summarizer（综述器）。
> 它回答：**"我们可以提出什么解释？这条推理站得住吗？怎样区分和检验？"**
> 它绝不回答：**"这个命题对不对？"** —— 经验命题的真伪只能由证据与检验决定。
>
> **三条不可让步的底线**：
> 1. **多数 Agent 赞成、辩论获胜、没找到反例，都不能证明科学命题正确。** 三者都只是"当前尚未被推翻"。
> 2. **用户每轮参与，AI 不替用户作答、不替用户决定。** 用户说"不知道"时给例子或选项，不给答案。
> 3. **外部意见（导师、同行、会诊）不等于用户决定，也不等于证据。** 它只作为来源明确的一条输入被记录。

---

## ⚡ 上下文预算与按需渐进加载准则 (Progressive Context Loading Protocol)

> [!CAUTION]
> **统一执行深度底线规则 (Execution Depth Core Rule)**：
> 讨论开始前确认 `execution_depth`；研究目标不能替代深度选择。无有效配置时展示快速／标准／深度三档的轮次上限与范围差异**并只问这一个配置问题**，用户可一句覆盖或回复"按推荐"。未确认不得进入实质讨论。
> 配置问句（`CONFIGURATION`）不占实质轮次，但不豁免资源计量。
>
> **用户拒选／授权代选的分支（实测补充）**：用户回复"你定吧""哪个合适就哪个"这类**授权代选**时，按下列处理，**不得**因此反复追问，也**不得**把它记成用户自选：
> 1. 取推荐档（默认标准档），在回复中显式说明"这是按推荐取的，你可随时一句话改成快速或深度"；
> 2. 记 `selection_source = INTERACTIVE_CONFIRMED`、`reason = user_delegated_choice_documented`，并在快照里保留"用户未自行选择"这一事实；
> 3. 该档位为**可回退**配置：用户后续任一轮说"太快/太慢"即改档，改档不重开讨论、不重问已知信息。

> [!CAUTION]
> **严禁全量一次性预加载**：本 Skill 包含 17 个模块文件。触发激活时**绝对禁止**一次性通读 `role/`、`references/`、`examples/`、`assets/` 中的所有文件。严格遵守下列阶段化按需读取策略。

### 阶段 1：Stage 0 上下文感知与单问门禁

1. **Stage 0A — Context Resolution**：解析当前指令、历史对话、任务附件、上游技能产物（检索协议、证据单元、综合结论）与项目资料，输出《现有科研上下文确认简报》，已知要素自动继承并标注来源（`[USER]` / `[CONTEXT]` / `[UPSTREAM]` / `[PROJECT]` / `[INFERRED]` / `[DEFAULTED]` / `[SYSTEM_RULE]`）。**严禁对已知要素重复询问。**
2. **Stage 0B — 单问门禁（本技能与前三技能的关键差异）**：只提出**一个**配置问题"本次讨论的资源档位"，附推荐值（继承上游 `execution_profile.json` 的 `depth`，否则用标准档）、该档的轮次上限，以及"可直接回复`按推荐`或用一句话覆盖"。其余项取项目默认并标 `[DEFAULTED]`。**输出后立即终止回复，静默等待**，严禁自问自答。
3. **Stage 0C — 启动快照**：确认后固化快照：`mode` 及其判断依据、成熟度初值、深度与来源、已知约束、`progress_signals`（空）、停止规则版本、携带的上游证据及其指纹。状态转 `DISCUSSING`。

**模式判断不提问**：用户给出具体主张 → `examine`（推敲）；只有兴趣、观察或矛盾 → `explore`（探索）。判断依据在回复中说明，用户可一句切换。

### 阶段 2：按需加载路由（Just-In-Time Loading）

| 当前要做什么 | 只加载 |
|---|---|
| 任何一轮对话（骨架、焦点问题合格条件、分支处理） | [references/dialogue_protocol.md](./references/dialogue_protocol.md) |
| 每轮结束时（信号归属、进展与停止判定） | [references/convergence_and_recovery.md](./references/convergence_and_recovery.md) 第一节与第二节 |
| 选择下一角色 / 判断该追问还是换视角 | [role/moderator.md](./role/moderator.md) |
| 判断想法成熟度、能不能做评估性提问 | [references/maturation_and_gates.md](./references/maturation_and_gates.md) |
| 角色扮演（按当轮角色只读一个文件） | `role/concept_clarifier.md`、`role/premise_evidence_examiner.md`、`role/implication_validator.md`、`role/alternative_explorer.md`、`role/reflection_facilitator.md` |
| 关键分歧或收敛前反例检查（P5） | [references/independent_review.md](./references/independent_review.md) |
| 出现证据缺口、需调用前三个技能 | [references/evidence_handoff.md](./references/evidence_handoff.md) |
| 阶段小结、检查点、暂停与恢复 | [references/convergence_and_recovery.md](./references/convergence_and_recovery.md)（第三节起：停止原因、小结模板、恢复与预算） |
| 会话记录字段、事件类型、缺口请求结构 | [schemas/research_debate_session.schema.json](../../schemas/research_debate_session.schema.json)、[schemas/research_debate_event.schema.json](../../schemas/research_debate_event.schema.json)、[schemas/research_debate_gap.schema.json](../../schemas/research_debate_gap.schema.json) |
| 阶段小结与验证方案模板 | [assets/session_summary_template.md](./assets/session_summary_template.md)、[assets/validation_plan_template.md](./assets/validation_plan_template.md) |
| 想先看完整走法 | [examples/intuition_to_question.md](./examples/intuition_to_question.md)、[examples/hypothesis_revision.md](./examples/hypothesis_revision.md) |

---

## 一、五角色 + 两个职能（Architecture）

五个角色对应五类苏格拉底提问；主持人与质量审查是**职能**，不是第六、第七类提问。

| 提问类型 | 角色与 `role_id` | `question_type` | 判断对象 |
|---|---|---|---|
| 澄清性 | 概念澄清者 `concept_clarifier` | `CLARIFICATION` | 词义、对象范围、比较基准 |
| 探因性 | 前提与证据审查者 `premise_evidence_examiner` | `PREMISE_EVIDENCE` | 承重前提、推理跳跃、证据对应 |
| 寻果性 | 推论与验证者 `implication_validator` | `IMPLICATION` | 可观察预测、区分条件、改判条件 |
| 比较性 | 替代解释探索者 `alternative_explorer` | `COMPARISON` | 竞争解释及其可区分点 |
| 反思性 | 观点修订引导者 `reflection_facilitator` | `REFLECTION` | 立场变化、保留/修改/未决 |
| （协调职能） | 主持人 `moderator` | `CONFIGURATION` | 状态、轮次、角色选择、查证确认、记录 |
| （审查职能） | 质量审查员 `quality_gatekeeper` | —（不提问） | 来源标注、授权范围、未决保留、契约一致 |

- **一一对应，禁止交叉组合**（例如 `concept_clarifier` 配 `IMPLICATION` 即契约失败）。
- 五类是**可选视角**，不是必须依次完成的五步。允许连续多轮同一角色、跳过已解决维度。
- 用户可见标签只有三种：`角色名 · 视角切换`、`角色名 · 独立 Agent 评估`、`角色名 · 视角自检（非独立评估）`。合并陈示两个评估结果时写 `角色A 与 角色B · 独立 Agent 评估`，焦点问题只归一个角色。

---

## 二、单轮对话协议（骨架固定，可机械检查）

每一轮 = **一个焦点问题 + 一次用户回答**。固定骨架：

1. **回应** — 不超过两句回应用户上一条；确实无新内容时写"跳过回应"。
2. **标签** — `角色名 · 视角切换`（或独立评估标签，三者不可混用）。**一轮内角色名不超过两个**；合并标签轮的焦点问题只归已出现的角色之一或主持人。
3. **一条实质贡献** — 必须先给出分析、例子、候选表述或方案，并标明来源（`用户观察` / `AI建议` / `AI判断` / `待验证假说` / `已有证据`+引用）。**只提问不贡献 = 违规（N1）。**
4. **一个焦点问题** — 恰好一个；一句话说明它为什么值得问。
5. **等待** — 终止回复，严禁自问自答或预写下一轮。

焦点问题合格条件（全部满足才允许发出，详见 [references/dialogue_protocol.md](./references/dialogue_protocol.md)）：

- 只含**一个**问句；不含"以及／另外／顺便"等并列引导的子问题。**注意：问号只有 1 个也可能是语义打包**，需逐句检视是否并列了多件事。
- 落在用户可直接回答的范围（自身观察、判断、取舍），不要求用户提供其不具备的文献或数据。
- 答案会改变至少一项：某条前提的状态、某个解释的可区分性、某个决定或后续动作。
- 不诱导（N4）、不赞美（N3）、不带预设结论。

---

## 三、主持人调度：P0–P6 优先级阶梯

调度依据不是"五类还没走完"，而是**当前最大障碍**。每轮按 P0 → P6 取第一个命中项，同一轮只处理一项。

| 优先级 | 触发条件 | 采用视角 | 本轮必须产出 |
|---|---|---|---|
| P0 | 用户直接提问、纠正误读、要求换角色/暂停/总结 | 主持人直接回应 | 回答该问题；不叠加新焦点问题；不新增实质轮次 |
| P1 | 核心概念、对象范围或比较基准未定义且影响后续判断 | 概念澄清者 | 2–3 个候选口径 + 各口径下的结论差异 + 一个焦点问题 |
| P2 | 存在决定命题能否站住的承重前提，未被检验 | 前提与证据审查者 | 承重前提表 + 最强反例场景或"暂未找到"的诚实结论 + 一个焦点问题 |
| P3 | 命题已可陈述，但没有预测，或没说清什么结果会改判 | 推论与验证者 | 一条可观察预测 + 最小判别设计草案（未知标待补）+ 一个焦点问题 |
| P4 | 只有单一解释，且该解释代价高 | 替代解释探索者 | 至少一个竞争解释及其预测 + 可区分点 + 一个焦点问题 |
| P5 | 出现方向级分歧，或用户要求收敛前做反例检查 | 启动独立评估 | 两个隔离评估 + 确定性分歧判定 + 一个判别问题交回用户 |
| P6 | 阶段完成，或连续两轮无进展信号 | 观点修订引导者 | 保留/修改/未决三段式 + 一个焦点问题 |

- **用户关注插队**：用户明确想谈的方向覆盖阶梯，但必须记录"本轮未处理的高优先级障碍"并在后续或小结中回收，不得静默丢弃。
- **收尾前检查**：进入 `CHECKPOINT` 前必须核对"本会话是否至少一次进入 P3"。未进入则命题仍在 `DEVELOPING`，小结中**不得**声称已形成可检验形式或最小验证方案。
- 完整判定与记录字段见 [role/moderator.md](./role/moderator.md)。

---

## 四、想法成熟度守卫（防过早否定）

`maturation` 与证据状态、处置状态**互相独立**，不互相派生。

| 阶段 | 允许的下一步 | 明确禁止 |
|---|---|---|
| `RAW` 原始直觉 | 澄清、给出候选表述、举对照例、增加一个可区分差异、前提审查、提出替代解释 | 判定成立与否、要求可证伪形式、做正反裁决 |
| `DEVELOPING` 发展中 | 前提审查、补预测、生成替代解释、寻找边界 | 要求完整验证方案；以"不完整"为由否定 |
| `TESTABLE` 可检验 | 构造最小判别设计、找反例、比较替代解释 | 把设计草案当作已执行结果 |

- **发展配额**：`RAW` 阶段须先积累 **2 个发展信号**（`INTUITION_FORMULATED`／`QUESTION_SHARPENED`／`PREMISE_SURFACED`／`DISCRIMINATION_ADDED`）才能进入 **P3**。P2 与 P4 属生成性动作，可在 RAW 阶段先行。`ALTERNATIVE_ADDED` 不计入配额。
- 反对意见必须定性：`FATAL`（须给依据）／`ADJUSTABLE`（**必须给具体改法**）／`UNRESOLVED`。`ADJUSTABLE` 与因不可行而搁置都**不得**写成"科学上被否定"。
- 完整阶段门与不变量见 [references/maturation_and_gates.md](./references/maturation_and_gates.md)。

---

## 五、混合 Agent 机制（关键节点才启动）

日常由主 agent 切换视角；仅在**重大方向分歧、收敛前反例检查、用户要求独立挑战**时启动独立评估。

- **输入白名单**：`idea_id` + `version` + 逐字命题、用户约束、原始证据引用、指定视角、输出格式。**禁止**提供：其他评估者的结果、主持人的倾向或预期答案、历史总结与措辞。
- **输出结构化**：`verdict`（`SUPPORTED`／`CHALLENGED`／`BOUNDED`／`INSUFFICIENT`）、承重前提、最强反例（找不到写 `NONE_FOUND` 并说明所查范围）、可区分证据、**`change_condition`（必填）**、`limitations`。只保留可审阅理由，不索取隐藏思维过程。
- **分歧判定由确定性程序完成**，不靠模型自评：`LOW_DIVERGENCE` 仅当 `verdict` 相同 **且** 承重前提高度重合 **且** 反例同一；否则 `HIGH_DIVERGENCE`。
- `HIGH_DIVERGENCE` 时**分别陈示双方最强理由与各自改判条件，给出一个判别问题交回用户**；不投票、不取平均、不写"综合来看"。交叉回应上限 1 轮且不允许直接改判。
- 子 agent 不可用/失败：记 `UNAVAILABLE`／`FAILED`／`PARTIAL`，最多重试 1 次；降级只能标 `视角自检（非独立评估）`，不得进入 `LOW_DIVERGENCE`，不得满足"收敛前独立评估"这一前提。
- **不得声称模型或知识来源相互独立**：同一模型的两个任务只表示分别作答。
- 完整规程见 [references/independent_review.md](./references/independent_review.md)。

---

## 六、证据缺口：先确认，后查证

**可推进性原则**：只有当前判断最终必须由外部经验事实决定时才需要查证；定义选择、价值取舍、逻辑一致性可继续概念讨论。

1. 主持人说明缺口：当前争议是什么 / 准备查什么 / 结果会改变哪个判断。
2. **等待用户确认范围**；`approval.status = CONFIRMED` 之前，禁止调用检索、提取或综合技能。
3. 已有材料可回答时优先复用，仍须核对与当前命题的匹配。
4. 调用前三个技能；只传完成任务所需上下文，**不把整段私有对话写入外部检索式**。
5. 回流时校验文件可读、schema 版本、记录引用与命题对应关系。
6. 说明影响（支持／削弱／限定／无法回答），更新对应版本，再提下一问。

- 授权指纹覆盖 `question`／`scope`／`target_skill`／`budget_ref`；任一改变即 `INVALIDATED`，须重新确认。相同指纹重试不重复派发。
- **对齐硬规则**：`alignment = VERIFIED` 仅当回流记录的 `verbatim_quote` 与 `location` 在**命题本身**层面直接支持该命题；实体、变量、关键词的共现一律判 `UNRESOLVED`，绝不升级为支持。禁止把 `CONTEXT` 当支持。
- 拒绝查证时缺口保留在 `open_questions`，可继续讨论不依赖该证据的分支。
- 完整交接与适配映射见 [references/evidence_handoff.md](./references/evidence_handoff.md)。

---

## 七、进展、停止与保存

- **进展信号**（唯一允许的进展依据）：`INTUITION_FORMULATED`、`QUESTION_SHARPENED`、`PREMISE_SURFACED`、`PREMISE_VERIFIED`、`PREMISE_CONTRADICTED`、`DISCRIMINATION_ADDED`、`ALTERNATIVE_ADDED`、`DISPOSITION_DECIDED`、`DECISION_RECORDED`、`GAP_CONFIRMED`、`EVIDENCE_IMPORTED`。
- **有进展** = 该轮新增至少一个信号；**无进展轮** = 无新增信号且 `pending_question` 所指障碍未变化。
- **停止规则**：S1 连续 2 轮无进展 → `CHECKPOINT`（并说明卡在哪条障碍）｜S2 同一障碍同一视角 2 次未消除 → 挂 `STOPPED_QUESTION`｜S3 问题依赖用户不具备的信息 → 停止追问｜S4 用户要求暂停/总结/收敛 → 立即执行｜S5 任一硬上限到达 → 收尾输出待办｜S6 达到阶段交付条件 → `CHECKPOINT`。
- **S1 判定口径**：只看实质轮次；唯一判据是当轮是否**新增**信号；收尾轮不倒推为进展；事后补记不改变当时判定。
- **停止原因必录且互斥**：`USER_CLOSED` / `CHECKPOINT_REACHED` / `NO_PROGRESS` / `BUDGET_EXHAUSTED` / `PAUSED` / `USER_SWITCHED_MODE`。
- **保存（必须真的执行，不能只在文本里声称）**：会话目录 `runs/<run_id>/research-debate/<session_id>/`，含 `session.json`、`events.jsonl`、`usage_ledger.jsonl`、`summaries/`。
  - 每轮结束调用 `python scripts/session_store_cli.py append <session_dir> --event-json '<事件>'` 落盘该轮事件；
  - 阶段小结/检查点调用 `... snapshot <session_dir> --expected-revision N` 原子写快照；
  - 会话恢复调用 `... recover <session_dir>`，以事件重放为准并报告与快照的差异。
  - 主 agent 单写；事件先落盘再原子替换快照；`event_id` 去重 + `last_applied_event_id` 重放；`events.jsonl` 是追加式真源。
  - **若结构化记录不可用，必须在回复中声明「状态未从结构化记录核实」**，不得凭印象给出轮次、S1 判定或收尾结论。
- **恢复简报 ≤10 行**：当前问题 / 上一轮角色与焦点问题 / 用户最新输入 / 待处理项 / 预算剩余 / 三个可选动作。**不得重问已知信息，不得把恢复当作新授权。**
- 完整规程见 [references/convergence_and_recovery.md](./references/convergence_and_recovery.md)。

---

## 八、边界：与前三个技能的分工

本技能的对象是**用户自己的命题与修订过程**，不是文献结论。

| 用户当前问题的对象 | 归属 |
|---|---|
| 有哪些相关文献 / 原文写了什么 / 多篇证据支持什么 | `literature-discovery-acquisition` / `literature-evidence-extraction` / `literature-synthesis` |
| 我们可以提出什么解释 / 我的推理站得住吗 / 怎样区分与检验 | **本技能** |

- **不复制**已有能力：学术争议九分类、共识分级、Devil's Advocate（对象是跨文献结论）、研究空白十类识别、检索式与覆盖台账。需要时按确认范围调用，接收其结果作为证据输入。
- 无任何文献时可启动；未完成查证前，新颖性标"待核实"，**不得宣称首次发现**。
- 纯事实检索、全文字段抽取、直接撰写综述不走本技能。

---

## 九、技能协同与交接契约 (Workflow Handoff)

- **接收上游**：Discovery 的检索协议与题录；Extraction 的 `EvidenceRecord` 与证据矩阵；Synthesis 的争议地图、共识边界与主张记录。继承已知配置与证据，**不重复询问**；资源授权不随证据转移。
- **反向派发**：`SEARCH_GAP` → `literature-discovery-acquisition`；`EXTRACTION_GAP` → `literature-evidence-extraction`；`SYNTHESIS_REQUEST` → `literature-synthesis`。均须先经用户确认范围。
- **不写入旧契约**：不改 `ClaimRecord` / `EvidenceRecord` / `SynthesisRecord`，不把 `IdeaRecord` 混入旧数组，不把"讨论中假说"自动写为综合结论。

---

## 十、支撑资源与文档目录

- **角色规范 (`role/`)**：
  - [moderator.md](./role/moderator.md)：主持人契约（P0–P6 阶梯、选择理由记录、收尾前检查）
  - [concept_clarifier.md](./role/concept_clarifier.md)：概念澄清者
  - [premise_evidence_examiner.md](./role/premise_evidence_examiner.md)：前提与证据审查者
  - [implication_validator.md](./role/implication_validator.md)：推论与验证者
  - [alternative_explorer.md](./role/alternative_explorer.md)：替代解释探索者
  - [reflection_facilitator.md](./role/reflection_facilitator.md)：观点修订引导者
  - [quality_gatekeeper.md](./role/quality_gatekeeper.md)：质量审查员（12 项检查表）
- **核心规程 (`references/`)**：
  - [dialogue_protocol.md](./references/dialogue_protocol.md)：单轮骨架、焦点问题合格条件、分支处理、N1–N7 负例清单
  - [maturation_and_gates.md](./references/maturation_and_gates.md)：RAW/DEVELOPING/TESTABLE 阶段门、发展配额、反对意见定性、不变量
  - [independent_review.md](./references/independent_review.md)：输入白名单、输出结构、反附和机制、分歧交回用户、失败降级
  - [evidence_handoff.md](./references/evidence_handoff.md)：可推进性判定、六步交接、授权指纹、对齐硬规则、旧载荷映射
  - [convergence_and_recovery.md](./references/convergence_and_recovery.md)：进展信号、S1–S6、检查点、阶段小结、事件恢复与授权边界
- **资产与模板 (`assets/`)**：
  - [session.schema.json](../../schemas/research_debate_session.schema.json)、[event.schema.json](../../schemas/research_debate_event.schema.json)、[gap_request.schema.json](../../schemas/research_debate_gap.schema.json)：会话／事件／缺口请求的 JSON Schema（2020-12）
  - [session_summary_template.md](./assets/session_summary_template.md)、[validation_plan_template.md](./assets/validation_plan_template.md)
- **案例 (`examples/`)**：
  - [intuition_to_question.md](./examples/intuition_to_question.md)：从模糊直觉到候选问题（探索模式全程）
  - [hypothesis_revision.md](./examples/hypothesis_revision.md)：挑战已有假说（推敲模式全程）

> **本技能不提供**：文献事实、统计功效或样本量计算、价值取舍的裁决。缺少条件时一律标"待补"，禁止用看似合理的数值填空。

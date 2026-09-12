# 进展、收敛、小结与恢复 (Convergence & Recovery)

> 加载时机：登记进展信号、判断是否停止、生成阶段小结、暂停或恢复会话时读取。

## 一、进展信号（唯一允许的进展依据）

| 信号 | 含义 | 可核对证据 |
|---|---|---|
| `INTUITION_FORMULATED` | 模糊直觉变成可陈述的命题 | 出现有主谓的命题文本 |
| `QUESTION_SHARPENED` | 问题更精确或范围收窄 | 前后两版问题文本对照 |
| `PREMISE_SURFACED` | 隐含前提变为显式 | 新增 assumption 记录 |
| `PREMISE_VERIFIED` / `PREMISE_CONTRADICTED` | 前提状态改变 | 附证据引用或推理依据 |
| `DISCRIMINATION_ADDED` | 新增可区分两个解释的预测 | predictions 记录含 `distinguishes_from` |
| `ALTERNATIVE_ADDED` | 新增竞争解释 | alternatives 记录 |
| `DISPOSITION_DECIDED` | 对某想法作出保留/修订/否定/搁置决定 | decisions 记录且 `author` 明确 |
| `DECISION_RECORDED` | 记录一项影响后续动作的用户决定 | decisions 记录 |
| `GAP_CONFIRMED` | 确认了一项查证范围 | `approval.status = CONFIRMED` |
| `EVIDENCE_IMPORTED` | 证据回流并完成对齐判定 | evidence_links 更新 |

- **有进展轮** = 该轮新增至少一个信号。
- **无进展轮** = 无新增信号，且 `pending_question` 所指障碍未变化。
- **信号归属哪一轮（实测补充，强制）**：信号归属**产生该信号的那一轮**，即用户作出相应回答的轮次；不是主持人事后判定它的轮次。
  - 例：用户在 R1 回答中把含糊表述收窄为具体观测对象 → `QUESTION_SHARPENED` 记在 **R1**，不得记到 R2。
  - 若主持人在后续轮次才识别出来，须以 `backdated_to_round` 回填到正确轮次，并在事件里注明回填时间与原因；
  - 回填会改变 S1 判定时，必须同时说明判定是否随之改变；不得静默改写历史。
  - 每轮结束时按"本轮用户回答产生了哪些信号"登记，而不是按"本轮我讨论了什么"登记。
- 用户仅表示"知道了""继续"而无新信息时，记为**无进展轮**，不记为进展。

## 二、停止规则 S1–S6

| 编号 | 条件 | 动作 |
|---|---|---|
| S1 | 连续 2 轮无进展信号 | 进入 `CHECKPOINT`，**具体说明卡在哪条障碍、缺什么信息**；禁止笼统写"没有进展" |
| S2 | 同一障碍在同一视角下 2 次未消除 | 挂为 `STOPPED_QUESTION`，保留问题与已知信息，转到其他分支 |
| S3 | 焦点问题所依赖的信息用户不具备（明确表示不知道且给不出估计） | 停止追问该点，改为提供候选选项或转出查证 |
| S4 | 用户要求暂停、总结、收敛或换深度 | 立即执行，不补完当前问答 |
| S5 | 任一硬上限（轮次、评审批次、活跃时长、事件写入数）到达 | 收尾：输出阶段小结与待办，**不自动扩额** |
| S6 | 达到阶段交付条件 | 进入 `CHECKPOINT`，由用户决定继续或结束 |

### 2.0 状态查询规则（实测补充，强制）

**会话状态一律从结构化记录读取，不得凭叙述记忆判断。** 收尾前检查、S1 计数、轮次余量、已进入过哪些阶梯项，都必须查 `session.json` / `events.jsonl`，而不是回看对话文本。

- 具体地：「本会话是否进入过 P3」查 `rounds[].trigger` 是否含 `P3`；「实质轮次用了多少」查按 `kind` 过滤后的条数；「还有几轮」用 `budget.max_rounds - 已用`。
- 若结构化记录不可用，**必须显式声明"状态未核实"**，不得凭印象给出结论。
- 背景：实测中出现过主持人在同一会话内自相矛盾的判断（先在一轮里声明"本会话首次进入 P3"，两轮后又写"本会话尚未进入 P3"），而该错误**脚本抓不到**——检查器只核对结构化字段，不会读叙述。

### 2.1 S1 判定口径（避免歧义）

- 只看**实质轮次**（`SUBSTANTIVE`／`EXTERNAL_INPUT`／`REVIEW_SUBMISSION`）；配置轮与检查点轮不参与计数。
- 唯一判据是「该轮是否**新增**了第一节的信号」；一轮里出现新的决定或新的未决项但**未登记新信号**，仍按无进展计。
- 收尾轮（`CHECKPOINT`）即便带来新的三段式内容，也**不倒推**为进展；收尾之后不再触发 S1。
- 会话结束后补记的信号不改变当时判定；若补记导致判定改变，必须在事件里说明补记时间与原因。

## 三、停止原因（必录且互斥）

`USER_CLOSED` / `CHECKPOINT_REACHED` / `NO_PROGRESS` / `BUDGET_EXHAUSTED` / `PAUSED` / `USER_SWITCHED_MODE`

## 四、阶段小结

必含：

1. 当前问题（用户原始表达与当前问题分列）；
2. 候选想法及其版本链（含每次修订理由）；
3. 支持／挑战／边界证据（附引用与 `checked_scope`）；
4. 未决分歧与未决问题；
5. 被否定或搁置的想法**及原因与定性**（`FATAL`／`ADJUSTABLE`／`UNRESOLVED`）；
6. 进展信号清单；
7. 下一步最小验证方案——**仅当本会话至少一次进入 P3**；否则写"尚未形成验证方案，缺的是哪一步"；
8. 停止原因与计划／实际结果分栏；未知参数标"待补/待核实"。

模板见 [session_summary_template.md](../assets/session_summary_template.md)。

**最小验证方案**必须说明：竞争解释、各自预测、要观察的差异、测量或比较方式、必要资源、混杂风险，以及什么结果会改变判断。缺少条件时保留待补，避免伪精确的样本量或阈值。模板见 [validation_plan_template.md](../assets/validation_plan_template.md)。

## 五、失败情况与降级行为

| 失败情况 | 行为 |
|---|---|
| 用户跳过问题 | 记录未决，可换分支；不能自动填答案 |
| agent 相互矛盾 | 由确定性规则判分歧，呈现共同前提与真正分歧，提出判别问题，**不投票** |
| agent 超时或不可用 | 保存部分评估、明确降级并标 `SELF_CHECK`；最多重试 1 次 |
| 上游产物不兼容 | 保存引用与错误，暂停该产物导入，不静默丢字段 |
| 证据已更新 | 标记依赖旧指纹的判断待复核，不覆盖历史 |
| 恢复时有待回答问题 | 按第六节简报呈现，不重新进行全套问询 |
| 写入中断 | 以完整事件恢复；不发布损坏快照 |
| 用户要求的动作超出预算 | 说明超出部分，请用户决定加额或收尾，不默认继续 |

## 六、持久化与恢复

### 6.1 存储与一致性

- 路径：`runs/<run_id>/research-debate/<session_id>/`，含 `session.json`、`events.jsonl`、`summaries/`；阶段交付时生成 `report.html`。
- **`events.jsonl` 是追加式真源，`session.json` 是检查点快照。** 两者冲突时以事件重放为准，并**显式报告差异**（差异内容、涉及事件 ID、修复动作），不静默选边。
- 跨恢复时同时核对**两类**一致性，且各有归属：① run bundle 的 `run_id` 对账由 `shared/execution/artifacts.py` 的 `load_run_artifacts` 负责；② 会话自身的 `last_applied_event_id` 重放由 `SessionStore` / `scripts/session_store_cli.py recover` 负责。**本技能不重复实现前者**，只在恢复时把两者结果并列呈现；任一不一致都须报告，不得择一采信。

### 6.2 写入协议

- 主 agent 是**唯一写入者**；子 agent 只返回结构化结果。
- 事件先落盘 → 快照写到同目录临时文件 → 原子替换。
- `event_id` 去重 + `last_applied_event_id` 重放。
- 末尾不完整事件：保留隔离副本后忽略该条；**中段损坏则停下并报告**，不猜测恢复。
- 并发 `revision` 冲突：拒绝覆盖并重新读取。

### 6.3 恢复简报模板（不超过 10 行）

```text
会话 <session_id>｜模式 <explore|examine>｜状态 <state>
当前问题：<current_question>
上一轮：<role_id> 提出「<pending_question.text>」（针对 idea v<version>）
你的最新输入：<最近一条 USER_INPUT 摘要>
待处理：待确认查证 <n> 项；待导入证据 <n> 项；未决问题 <n> 条
预算：轮次 <used>/<max>｜评审批次 <used>/<max>｜活跃 <used>/<max> 秒
可选：1) 回答上述问题  2) 换一个方向  3) 生成阶段小结并结束
```

### 6.4 恢复后禁止的行为

- 重问已在快照或上游产物中确认的信息（目标、约束、深度、已确认的查证范围）。
- 把旧授权用于新范围：指纹不匹配时必须回到 `WAITING_GAP_CONFIRMATION`。
- 用随机或重新分配的角色替换已保存的待答角色与 `target_version`。
- 把恢复本身当作一次新的资源授权（预算沿用原值，**不重置、不扩额**）。
- 把恢复简报写成完整上下文复述；超过 10 行视为不合格。

### 6.5 新会话的判定

用户改变原始问题的**语义**（不是用词）时开新会话；旧会话保留 `CLOSED` 状态并通过 `parent_session_id` 引用。同一会话内只做范围收窄或措辞澄清。

## 七、预算与计量

### 7.1 硬约束（可测量，到达即执行 S5）

| 深度 | 轮次上限 | 评审批次上限 | 单批子任务上限 | 活跃时长上限 | 事件写入上限 |
|---|---:|---:|---:|---:|---:|
| 快速 quick | 4 | 1 | 2 | 600 秒 | 120 |
| 标准 standard | 8 | 2 | 2 | 1800 秒 | 400 |
| 深度 deep | 16 | 3 | 2 | 3600 秒 | 1200 |

上表为**待标定参数**，不是性能承诺，也未实测；应按真实会话记录回归修正。

**写入会话时必须映射，不能搬运 run 级预算**（2026-09-13 真实试跑发现）：run 级
`ExecutionProfile.budgets`（`max_search_candidates` / `snowball_rounds` /
`extraction_unit_limit` / `max_token_ceiling` …）与本表的五个字段**不重叠**；
`schema` 对 `execution.budget` 设了 `additionalProperties: false`，直接搬运会被
`validate_session.py` 的 **BU1** 拒绝。正确做法：`shared.execution.to_session_execution(config)`
（或 `to_session_budget(depth)`），它按本表生成 quick/standard/deep 三档预算。

### 7.2 观测字段（不作硬判据）

- `usage.tokens_observed` 与 `usage.tokens_metering`（`MEASURED`／`ESTIMATED`／`UNAVAILABLE`）只作观测记录。
- 宿主无可靠 token 计量时记 `UNAVAILABLE`，**不得**以 token 作为唯一停止理由。
- 不声称 token 硬限已验证；不把估计值写成实测值。

### 7.3 继承与扩额

- 上游 `selection.status == "confirmed"` 且 `run_id` 一致时，可继承深度并标 `RUN_PROFILE_INHERITED`，不重复询问。
- **资源授权不随证据转移**：上游文献与证据可继续使用，但本会话的轮次与批次上限独立确认一次。
- 默认**不并入**上游预算，也不自动增加原预算；用户主动加额记为新的确认并写入 `execution.selection.reason`。

字段定义见 [session.schema.json](../../../schemas/research_debate_session.schema.json) 与 [event.schema.json](../../../schemas/research_debate_event.schema.json)。

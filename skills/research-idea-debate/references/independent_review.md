# 独立评估规程 (Independent Review)

> 加载时机：P5 触发（重大方向分歧、收敛前反例检查、用户要求独立挑战）时读取。
> **适用边界**：本规程只保证"分别作答 + 输入隔离 + 由确定性规则判分歧"，**不保证知识来源独立**。同一模型的两个任务不是两个独立专家。

## 一、何时启动

| 触发 | 说明 |
|---|---|
| 重大方向分歧 | 用户与 AI、或两条推理路径给出方向级不同的判断 |
| 收敛前反例检查 | 准备进入 `CHECKPOINT` 或形成验证方案前 |
| 用户要求独立挑战 | 用户明确要求"再听一个不同意见" |

**不得**为五类视角常驻五个 agent；**不得**在已授权预算内为常规调用重复询问用户。

启动前先用**一个** `CONFIGURATION` 问句征询用户是否启动；用户同意后在本轮内启动并陈示结果。**独立评估的启动、提交与分歧判定都不是用户轮次。**

## 二、批次规模与分工

- 每批 **2 个子任务**，隔离并行，**提交前互不可见**。
- 同批**不使用同一视角**；按**理论最大分歧**分工，例如：
  - 前提与证据审查者 × 替代解释探索者（论证结构 vs 竞争机制）
  - 推论与验证者 × 前提与证据审查者（可检验性 vs 前提稳固性）
- 单批子任务数不得超过深度档的 `max_subtasks_per_batch`。

## 三、输入白名单（不多给）

每个任务收到一份自包含输入包：

| 允许字段 | 内容 |
|---|---|
| `target` | `idea_id` + `version` + **逐字命题文本**（不得由主持人改写润色） |
| `user_constraints` | 用户已声明的资源、对象、范围约束，标注 `[USER]` |
| `evidence_refs` | 原始证据引用（`evidence_id`、来源文件、对齐状态），不含主持人的解读 |
| `assigned_lens` | 指定的一个视角（`role_id`）与其职责说明 |
| `answer_format` | 输出字段与取值枚举要求 |

**禁止提供**：

- 其他评估者的结果（提交前与提交后均不提供，除非进入交叉回应）；
- 主持人的倾向、预期答案或结论草稿；
- 主持人的历史总结与措辞；
- 用户对某结论的偏好表述（若与可行性有关，只保留客观约束）。

评估者**不得**自行检索、不得调用其他技能、不得创建子 agent、不得改动共享会话文件。

## 四、输出结构（只收可审阅理由）

```text
task_id / input_idea_version   核对评估对象，防止对旧版本作答
verdict                        SUPPORTED | CHALLENGED | BOUNDED | INSUFFICIENT
load_bearing_premises[]        premise / type / fragility(HIGH|MEDIUM|LOW)
                               / what_observation_would_test_it
strongest_counterexample       具体场景 + 类型 + 可观察结果；
                               找不到写 NONE_FOUND 并说明所查范围
discriminating_evidence        能区分竞争解释的证据或观察
change_condition               ★必填：什么条件下评估者会改变自己的判断
evidence_refs[]                引用到的既有证据 ID，无则空数组
limitations                    本次评估未覆盖的范围
```

- `change_condition` 为空视为输出不合格（`status = PARTIAL`）。
- 只保存可审阅的判断理由；**不索取、不保存隐藏思维过程**。
- 找不到反例不等于命题成立；`NONE_FOUND` 必须附所查范围。

## 五、反附和机制

1. **同批隔离**：并行启动，提交前互不可见。
2. **按最大分歧分工**：不固定正反，也不使用"赞成方／反对方"这类标签。
3. **确定性分歧判定**（不靠模型自评）：

```text
LOW_DIVERGENCE   同时满足下列三条：
                 (a) verdict 相同；
                 (b) 反例类型标签相同（或同为 NONE_FOUND）；
                 (c) 结论层面无冲突（未出现一方给出的具体反例被另一方明确否定）
HIGH_DIVERGENCE  其余情形
NOT_APPLICABLE   任一评估者未 COMPLETE
```

   判定程序须记录 `computed_by = deterministic_program`、各条准则的满足情况，以及所用的反例**类型标签**。
   **缺任一评估者时不得推定 LOW。**

   **不得用字面集合重合代替语义比较（实测补充）**：曾出现两名评估者 `verdict` 相同、且都把"归一化内参不可比"列为第一障碍，却因措辞不同（一方写"归一化转换对两基因对称"，另一方写"两基因方向可直接比较不受内参切换影响"）导致字面重合度为 0，被判为 `HIGH_DIVERGENCE`。这是**误报**——把"结论一致、表述不同"渲染成方向级分歧，会浪费一轮并向用户传递错误的紧张感。
   因此：
   - 判定只比较**可枚举字段**：`verdict`、反例**类型标签**（从固定集合中选，见下）、以及"是否存在被对方明确否定的具体反例"；
   - **不比较** `load_bearing_premises` 的文本重合度；
   - 反例类型标签固定为：`MEASUREMENT_ARTIFACT`（测量/归一化伪影）、`SAMPLING_ARTIFACT`（抽样或分组伪影）、`ALTERNATIVE_MECHANISM`（替代机制）、`CONFOUNDING`（混杂）、`SCOPE_LIMIT`（适用边界）、`NONE_FOUND`；
   - 若两者 `verdict` 相同、反例类型相同、且无相互否定的反例，则判 `LOW_DIVERGENCE`，并仍然**不得**表述为"评估通过"或"命题成立"。
   - 判定结果与用户的沟通方式：`HIGH_DIVERGENCE` 才交回一个判别问题；`LOW_DIVERGENCE` 只说明"两方结论一致、各自理由如下"，随后照常推进下一障碍（不额外占用一轮）。
4. **交叉回应上限 1 轮**，计入评审批次；只允许补充理由或证据，**不允许直接改判**，避免一轮内级联趋同。
5. 不得声称模型或知识来源相互独立；该限制写入回复标签与记录。

## 六、分歧交回用户

`HIGH_DIVERGENCE` 时，主持人**必须**：

1. 分别陈示双方最强理由与各自的 `change_condition`；
2. 给出**一个**能区分双方判断的问题交给用户；
3. 请用户决定如何处理命题版本。

**禁止**：投票、取平均、写"综合来看"式调和结论、宣称"分歧已解决"、把 `LOW_DIVERGENCE` 表述为"评估通过"或"命题成立"。

若分歧源于对命题本身的读法不同，先回到概念澄清者统一口径，**不要**增加更多评估者。

## 七、失败与降级

| 情况 | 行为 |
|---|---|
| 子 agent 工具不可用 | 记 `UNAVAILABLE`，不启动；明确告知本轮无独立评估 |
| 超时或返回不合格 | 记 `FAILED`／`PARTIAL`；最多重试 1 次，仍失败则降级 |
| 降级为视角自检 | 标签必须写 `视角自检（非独立评估）`；记 `execution_kind = SELF_CHECK`；**不得进入 `LOW_DIVERGENCE` 判定**，**不得**用于满足"收敛前独立评估"这一前提 |
| 一个成功一个失败 | 展示成功的一份，如实说明缺少对照；不得据此宣称分歧已检查 |
| 用户把独立评估设为收敛前提 | 独立评估不可用时该前提不成立，需用户重新决定 |

## 八、记录字段

- `REVIEW_REQUESTED`：`batch_id`、`input_version`、指定视角、输入白名单与排除项。
- `REVIEW_RETURNED`：任务输出结构 + `status`。
- `DISAGREEMENT_ASSESSED`：`verdicts`、`premise_overlap`、`counterexample_overlap`、`disagreement_signal`、`computed_by`。
- `DEGRADED_REVIEW`：降级原因与替代方式。

字段定义见 [event.schema.json](../../../schemas/research_debate_event.schema.json)。

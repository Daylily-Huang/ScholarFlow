# 阶段小结模板 (Session Summary Template)

> 使用时机：进入 `CHECKPOINT`、`PAUSED` 或 `CLOSED` 时填写。**不要每轮重建**。
> 未知参数一律写"待补/待核实"，禁止用看似合理的数值填空。计划与实际分栏。

---

## 一、会话标识

| 项 | 值 |
|---|---|
| session_id | |
| run_id | |
| 模式 | explore / examine |
| 当前状态 | |
| 深度与来源 | quick/standard/deep（`[USER]` / `[UPSTREAM]` / `[DEFAULTED]`） |
| 停止原因 | `USER_CLOSED` / `CHECKPOINT_REACHED` / `NO_PROGRESS` / `BUDGET_EXHAUSTED` / `PAUSED` / `USER_SWITCHED_MODE` |
| 轮次使用 | 实质 <used>/<max>｜评审批次 <used>/<max> |

## 二、问题

- **用户原始表达**（逐字）：
- **当前问题**：
- 变化说明（若有）：

## 三、候选想法与版本链

| idea_id | 版本 | 命题（逐字） | 成熟度 | 证据状态 | 处置 | 修订理由 |
|---|---|---|---|---|---|---|
| | v1 | | RAW | INTUITION | REVISED | |
| | v2 | | DEVELOPING | HYPOTHESIS | ACTIVE | |

## 四、承重前提

| 前提 | 类型 | 脆弱性 | 核验状态 | 判定它需要什么观察 |
|---|---|---|---|---|
| | EMPIRICAL / DEFINITIONAL / METHODOLOGICAL / VALUE | HIGH/MEDIUM/LOW | UNVERIFIED / VERIFIED / CONTRADICTED | |

## 五、证据

| evidence_id | 来源 | relation | alignment | checked_scope | 说明 |
|---|---|---|---|---|---|
| | | SUPPORT / CHALLENGE / BOUNDARY / CONTEXT | VERIFIED / UNRESOLVED | | |

> 提醒：`CONTEXT` 不等于支持；共现不等于关系。

## 六、竞争解释与可区分点

| 解释 | 来源 | 若成立应观察到 | 与谁可区分 | 当前状态 |
|---|---|---|---|---|
| | USER / AI建议 / 外部分享（external_opinion） | | | 已排除 / 未决 / 待检验 |

## 七、用户决定清单

| 决定 | 针对版本 | 理由 | author | triggered_by | 用户确认 |
|---|---|---|---|---|---|
| | | | USER | ROLE_QUESTION / EXTERNAL_OPINION / INDEPENDENT_REVIEW / EVIDENCE / CHECKPOINT | 是/否 |

## 八、未决问题（会话级 + 想法级双写）

| 编号 | 问题 | 缺什么 | 什么信息能让它继续 | 停止规则 |
|---|---|---|---|---|
| | | | | S1 / S2 / S3 |

## 九、被否定或搁置的想法

| 想法 | 处置 | 定性 | 原因 |
|---|---|---|---|
| | REJECTED / DEFERRED | FATAL / ADJUSTABLE / UNRESOLVED | |

> 因不可行而搁置（`DEFERRED`）不等于科学上被否定。

## 十、进展信号清单

| 信号 | 轮次 | 证据 |
|---|---|---|
| | | |

## 十一、下一步最小验证方案

> **前置条件**：本会话必须至少一次进入 P3。未进入时本节只能写："尚未形成验证方案，缺的是哪一步（哪条预测或哪个改判条件）。"

见 [validation_plan_template.md](./validation_plan_template.md)。

## 十二、计划 vs 实际

| 项 | 计划 | 实际 | 差异原因 |
|---|---|---|---|
| 轮次 | | | |
| 评审批次 | | | |
| 阶段交付 | | | |

## 十三、审查签署

| 检查项 | 结果（PASS / FAIL / NOT_RUN） | 证据 |
|---|---|---|
| Q1–Q12（见 [quality_gatekeeper.md](../role/quality_gatekeeper.md)） | | |
| 收尾前 P3 检查 | | |
| 旧契约未被写入 | | |

> 未执行的项一律 `NOT_RUN`，不得推断为通过。本表不含对科学命题真伪的判断。

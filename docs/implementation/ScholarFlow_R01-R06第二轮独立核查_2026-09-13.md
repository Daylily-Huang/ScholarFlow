# R01–R06 第二轮独立核查与评分

## 结论

**修复质量评分：70/100；部分验收，不能宣称全部达标。** 此分是依据本次源码和合成反例的审查判断，不是科研准确率。撤回仅阅读执行 AI 报告时给出的 80 分作为实现质量参考。

审查对象为 2026-09-13 本地 `d6155fa` 加未提交修改，不是新的已提交版本。本次未改业务实现，保留工作区所有原有改动。检查了改动源码、Schema、入口文档与测试，重跑旧探针，并独立构造未覆盖边界；不是重新逐行审计整个仓库。

## 已独立确认的成绩

- 全量测试：`Ran 757 tests in 9.258s`，`OK (skipped=4)`；即 753 项通过、4 项跳过，不是 757 项全部通过。
- `scripts/domain_neutrality_linter.py`：PASS。
- `scripts/verify_package_assets.py`：PASS。
- 上轮 `recheck_probe.py` 的原 8 场景行为与执行报告一致。
- R03 原句首数值误拒、R04 完整 JSON 无换行追加，原始故障场景已通过。
- R06 原孤儿占位通过当前修改后的 Schema；NR 总则、Stage 8B 主流程、两级去重标识等确有清理。
- 未运行真实外部检索、真实宿主四技能全链路或真实论文金标评测。领域中立检查及打包检查不证明科学结果正确。

## 仍然存在的关键问题

### 1. P1：所谓语义分类器仍是默认放行的模式规则

位置：`shared/execution/debate_handoff.py:613`，尤其末尾 `:759` 的默认 CURRENT_STUDY_RESULT。

独立用例提供实际存在的临时源文件、有效定位和 checked_scope；命题为 `roads reduce gene flow`：

| 原文 | 实际返回 |
|---|---|
| `Our central question is whether roads reduce gene flow.` | VERIFIED / EMPIRICAL_FINDING |
| `For this simulation we assume that roads reduce gene flow.` | VERIFIED / EMPIRICAL_FINDING |

两者分别是研究问题和模拟前提，均不是实证结果。程序还生成“经结构化语义核验……确定性实证发现”的肯定理由。

根因：没有命中有限正则黑名单时，直接设 VERIFIED；函数名和结构化输出并没有改变这个判定机制。显式 semantic_verification 的 VERIFIED 标记也缺少与证据、命题版本的实际绑定验证。

必须修改：规则只用于排除/告警，默认 UNRESOLVED；只有来源、命题和审计记录绑定完整，且语义判断确实完成时才升级。不继续堆两条正则来代替修复。补问句改写、模拟假设、跨语言、命题版本变化和真正结果正例。

### 2. P1：数值解析仍会丢单位或截取部分数字

位置：`skills/literature-evidence-extraction/scripts/quote_audit.py:153`、`:202`、`:222`、`:259`。

| 原文内容 | 抽取值 | 独立实跑结果 |
|---|---|---|
| 2.5 microliters | 2.5 milliliters | token 仅为 `2.5`，strict 放行 |
| 15.4% | 4% | strict 放行 |
| 20.5 | 整数 20 | strict 放行 |
| 0.054 meters | 5.4% | strict 放行 |
| 20 mL | 999 mL | tokens=[]，value_checked=0，strict 放行 |

根因分别为：正则的小数分支先于带单位分支；边界不把小数点纳入数值；百分比与裸比例无条件互转而不检查量纲；单位识别区分大小写导致合法常见写法漏识别。

报告“彻底防止带单位数值降级”不成立：虽然删除了 _variants 中原裸数退化，数值提取阶段仍会产生同样结果。

必须修改：先识别完整数量（数值/符号/指数/单位），再比较；不能靠字符邻居是否是数字完成词法边界判断。转换须经字段类型和单位量纲约束，百分比不能匹配长度。无法解析的数值字段标待核验，不可算作通过。注意不要为大小写兼容而无差别折叠所有大小写敏感单位。

### 3. P1：授权核验可以省略，非确认事件也可充当授权

位置：`shared/execution/debate_handoff.py:180`、`:255`。

独立测试分别得到：

- 不传 events/session_store，只给合法范围指纹和不存在的 confirmed_event_id：dispatchable=true。
- 提供同 ID、同 session 的 assistant/SYSTEM CHECKPOINT 事件，而非用户 GAP_CONFIRMED：dispatchable=true。

范围指纹是任务内容摘要，不是用户授权证明。当前只有 `event_list is not None` 才检查事件存在；找到 ID 后主要比较 session，未强制检查事件类型、用户来源、gap、构想版本及批准范围。

必须修改：缺可信事件上下文即停止；不能以 gap 自带的任意 _events 当成已认证授权。核对真实用户确认事件及其绑定，不只核对字符串 ID。旧调用者应更新调用契约，而不是通过可选参数保留绕过路径。

本次证明的是函数门禁放行，没有发起真实外部调用。源码检索未发现 skills/shared 下其他 Python 派发调用者，因此宿主实际传参仍需要端到端验收。

### 4. P2：事件先行仍只有说明，没有完整一致性保障

位置：`shared/execution/session_store.py:227`、`:280`。

独立用例：E1 只记录 state；随后快照新增未记录在事件中的 idea `UNLOGGED`。当前 consistency_report 返回 true，重放也保留该 idea。

原因：任意当前快照仍作为重放可信基底；日志未涉及的字段无法辨别是否为未记录修改。改 docstring 为 Event-First Protocol 不等于实施事件先行协议。

必须修改：绑定可信初始状态/检查点和事件位置，使用可审计的状态投影写入口。若暂时要求调用方保证事件先行，须明确这是调用约定而非代码保证，并标注该整改未完成。

### 5. P2：占位 Schema 通过，不等于状态约束完整

位置：`schemas/research_debate_gap.schema.json`。

将修复产生的 PENDING 占位改为 execution_status=RUNNING，Schema 仍返回零错误。原有说明却要求未确认只能 NOT_STARTED 或 REFUSED_BY_USER。该弱约束并非本轮首次引入，但新报告没有补齐，不能以一个 PENDING 正例通过作为完整授权状态验收。

此外，本轮 null 放宽实际上覆盖全部非 CONFIRMED 状态，不仅是报告所称“PENDING 占位态”。

必须修改：增加非 CONFIRMED 状态的执行限制，明确哪些状态允许空关联；验证旧消费者能处理这些 null。若保持 schema_version=0.1，需说明兼容依据，否则进行版本化迁移。

## 本轮各项验收判断

| 项目 | 判断 |
|---|---|
| R01 | 原例通过，机制未通过 |
| R02 | 原例通过，通用数值核验未通过 |
| R03 | 报告所述边界修复通过 |
| R04 | 报告所述无换行修复通过，不代表全部持久化问题已解决 |
| R05 | 版本字段和 RUNNING 原例通过，授权真实性未通过 |
| R06 | 原占位 Schema 校验通过，状态约束/兼容验收未完成 |
| 文档清理 | 有实质完成，不抵消关键代码缺陷 |

## 评分解释与下一步

给 70 分而非 80 分：确有实现、回归和文档改善；但证据、数值、授权三条高风险路径依然放行错误输入，修复仍明显围绕已知例句展开。这个分数只评价此次整改质量，不评价整个 ScholarFlow 的潜力。

下一轮先修上述三条 P1，把本次反例变为带断言测试，再补真实宿主闭环。不要再把“未命中反例规则”当作科学正确，也不要把“传了一个确认 ID”当作用户授权。

复现脚本：`.planning/four-skill-review/independent_r06_probe.py`；命令：`python -B .planning/four-skill-review/independent_r06_probe.py`。该文件为本地审查辅助文件，可能受 .gitignore 忽略；正式修复时应将用例纳入 tests。所有探针均使用合成材料和自建临时目录。

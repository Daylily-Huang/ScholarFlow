# ScholarFlow Skill 2 — Universal Claim–Evidence Alignment Principle
## 全学科通用“主张—证据对齐”底层原则与实施操作文档

> 适用模块：`literature-evidence-extraction`  
> 适用范围：**所有学科**  
> 目标：修复 Skill 2 在“关系型事实抽取”中可能出现的核心错误——**把实体出现、共同出现、背景描述、上下文邻近或被引用，错误升级为用户要求的科学关系或结论。**
>
> 本文不是食性专用规则，不得将其实现成生态学、医学、分子生物学或计算机科学的特例。  
> 核心设计必须保持：
>
> ```text
> Discipline-neutral Core
> +
> Domain-specific examples only
> ```

---

# 1. 本次修改的核心目标

Skill 2 当前已有：

```text
Quote
→ Extract
→ Verify
→ Optional Interpret
```

这套结构能够有效防止：

- 无原文证据的参数脑补；
- 引用前人工作冒充本文结果；
- Discussion 推测冒充实验结论；
- 多实验上下文参数串染；
- 未报告内容被自动填充；
- OCR 错误被静默修正。

但对于**关系型科学信息**，仅有 Quote-First 仍然不够。

原因是：

> 原文能够证明“一个实体出现过”，并不等于原文证明“用户要求的关系成立”。

因此本次必须新增一个更底层、更通用的原则：

# Universal Claim–Evidence Alignment Principle

中文：

# 主张—证据对齐原则

其核心要求是：

> **Skill 2 输出的每一个结构化事实、关系或结论，都必须由证据支持“用户真正要求的那个主张”，而不仅仅支持主张中的若干实体、变量或关键词。**

---

# 2. 最核心的底层规则

必须写入 Skill 2 的 Core：

> **Mention ≠ Relation.**
>
> **Co-occurrence ≠ Relation.**
>
> **Contextual proximity ≠ Relation.**
>
> **Entity evidence ≠ claim evidence.**

中文：

> **提及 ≠ 关系。**
>
> **共现 ≠ 关系。**
>
> **上下文邻近 ≠ 目标关系。**
>
> **实体存在证据 ≠ 主张成立证据。**

只有当原文证据能够支持用户要求的**完整科学主张**时，才允许输出该主张。

---

# 3. 为什么不能只用 Subject–Predicate–Object 作为 Core

Subject–Predicate–Object 对很多关系任务很好用：

```text
Animal → consumes → Plant
Drug → reduces → Mortality
Gene A → regulates → Gene B
Model A → outperforms → Model B
```

但 ScholarFlow 面向所有学科。

在人文、历史、法学、理论科学、数学或哲学中，很多主张不一定天然适合实体三元组。

例如：

```text
某理论解释某历史现象
某法律原则适用于某判例
某作者将某概念视为规范性而非描述性
某数学结论依赖某假设
```

因此：

```text
Subject–Predicate–Object
```

只能是 Relation Binding 的一种实现形式。

真正的底层抽象应该是：

```text
Target Claim
        ↓
Relevant Evidence Context
        ↓
Does the evidence actually support the requested claim?
```

所以架构关系应定义为：

```text
Claim–Evidence Alignment Principle
        ↓
Relation Binding Gate
        ↓
Domain-specific interpretation
```

---

# 4. Skill 2 必须区分两类抽取任务

## 4.1 Attribute / Value Extraction

典型：

```text
Sample Size = 108
Temperature = 55°C
Study Period = 2018–2022
Dataset Size = 50,000
```

这类任务通常是：

```text
Entity / Study
→ Attribute
→ Value
```

核心要求仍然是：

```text
Quote supports Value
```

---

## 4.2 Claim / Relation Extraction

典型：

```text
X affects Y
A causes B
A is associated with B
A outperforms B
A regulates B
X supports Theory Y
A feeds on B
Treatment A reduces Outcome B
```

这类任务必须额外执行：

```text
Claim–Evidence Alignment Gate
```

也就是：

> 证据不仅要包含 A 和 B，还必须真正支持“A 与 B 之间存在用户要求的关系”。

---

# 5. 什么时候触发 Claim–Evidence Alignment Gate

如果用户要求提取的是：

```text
关系
作用
因果
关联
比较
影响
机制
交互
依赖
支持
反驳
调控
传播
优势
劣势
结果方向
```

就应自动判定为：

```text
CLAIM_OR_RELATION_EXTRACTION
```

不需要用户再确认。

例如：

```text
“这篇文章说什么因素影响死亡率？”
“哪些基因调控这个通路？”
“算法 A 是否优于算法 B？”
“这个理论支持什么结论？”
“这种动物吃什么？”
```

都属于：

```text
CLAIM_OR_RELATION_EXTRACTION
```

---

# 6. 不要只做关键词匹配

禁止把任务识别写成简单：

```text
if "eat" in query:
    relation_task = True
```

应该由 Agent 语义判断：

```text
用户是在问：
“某个实体是什么？”
还是：
“某个实体和另一个实体之间有什么关系？”
```

推荐内部状态：

```yaml
extraction_semantics:
  type: ATTRIBUTE
```

或：

```yaml
extraction_semantics:
  type: CLAIM_RELATION
```

---

# 7. Claim–Evidence Alignment 的五个强制条件

任何关系型或主张型输出都必须至少通过以下五个问题。

## Gate 1 — Target Claim Identity

先明确用户真正要的主张是什么。

例如：

```text
A affects B
```

不能退化成：

```text
A exists
B exists
```

---

## Gate 2 — Evidence Context Match

证据必须来自与目标主张相关的上下文。

检查：

```text
同一研究
同一实验
同一队列
同一数据集
同一比较
同一理论论证
同一物种
同一处理组
同一时间/空间范围
```

不能跨 Context 拼接。

---

## Gate 3 — Relation / Proposition Support

原文必须支持目标关系本身。

不能因为：

```text
A 与 B 同时出现
```

就输出：

```text
A affects B
```

---

## Gate 4 — Source Role

证据必须判断属于：

```text
CURRENT_STUDY_RESULT
CURRENT_STUDY_METHOD
BACKGROUND
REFERENCED_WORK
DISCUSSION_INTERPRETATION
ENVIRONMENT_OR_CONTEXT
OTHER_ENTITY_CONTEXT
```

如果用户要“本文发现”，则：

```text
REFERENCED_WORK
BACKGROUND
```

不能进入 Confirmed Result。

---

## Gate 5 — Inference Boundary

如果关系不是原文明确表达，而是模型推出来的：

必须判断：

```text
是否唯一可推导？
是否存在替代解释？
是否需要领域假设？
```

只要需要未经声明的额外假设：

```text
不得输出为 CONFIRMED
```

---

# 8. 推荐的通用状态体系

建议对 Claim/Relation 输出使用：

```text
SUPPORTED
PARTIALLY_SUPPORTED
DERIVED
AMBIGUOUS
CONTRADICTORY
BACKGROUND_ONLY
CONTEXT_ONLY
OTHER_ENTITY_CONTEXT
REFERENCED_ONLY
NOT_REPORTED
```

---

# 9. 各状态定义

## SUPPORTED

原文明确或结构化地支持完整目标主张。

---

## PARTIALLY_SUPPORTED

原文支持主张核心方向，但：

```text
条件
范围
对象
数值
时间
比较边界
```

有部分未完全匹配。

---

## DERIVED

关系可由原始数据或结构信息唯一推导，但不是原文直接陈述。

必须记录：

```text
derivation logic
assumptions
source values
```

---

## AMBIGUOUS

实体存在，但目标关系不清楚。

---

## CONTRADICTORY

原文明确反对用户要求的主张。

---

## BACKGROUND_ONLY

只存在于背景介绍中。

---

## CONTEXT_ONLY

只描述研究环境、条件、资源、系统组成等。

---

## OTHER_ENTITY_CONTEXT

关系属于另一个对象，而不是目标对象。

---

## REFERENCED_ONLY

关系来自被引用文献，不是当前研究直接证据。

---

## NOT_REPORTED

当前论文没有报告目标关系。

---

# 10. Confirmed Output 的硬门槛

最终 Confirmed 输出只能包含：

```text
SUPPORTED
PARTIALLY_SUPPORTED
DERIVED
```

其中：

```text
PARTIALLY_SUPPORTED
DERIVED
```

必须显式保留不确定性和推导说明。

以下永远不得自动进入 Confirmed：

```text
AMBIGUOUS
BACKGROUND_ONLY
CONTEXT_ONLY
OTHER_ENTITY_CONTEXT
REFERENCED_ONLY
NOT_REPORTED
```

---

# 11. 核心禁止规则

必须写入 Skill 2：

```text
If evidence supports only the entities but not the requested proposition,
the proposition MUST NOT be emitted as confirmed.
```

中文：

> **如果证据只能证明主张中的实体存在，却不能证明目标主张本身成立，则该主张不得作为已确认事实输出。**

---

# 12. 通用示例：不同学科

以下只能作为 Example，不得写成 Core 特定逻辑。

---

## 生命科学

```text
Gene A and Gene B were both expressed.
```

不能推出：

```text
Gene A regulates Gene B.
```

---

## 医学

```text
Drug A was used in the hospital.
Mortality was measured.
```

不能推出：

```text
Drug A reduced mortality.
```

---

## 生态学

```text
Plant A occurred in the study area.
Animal X occurred in the same area.
```

不能推出：

```text
Animal X consumed Plant A.
```

---

## 计算机科学

```text
Model A and Model B were both evaluated.
```

不能推出：

```text
Model A outperformed Model B.
```

---

## 社会科学

```text
Income and education were both measured.
```

不能推出：

```text
Education caused higher income.
```

---

## 历史学

```text
Author A discussed Theory B.
```

不能推出：

```text
Author A endorsed Theory B.
```

---

## 法学

```text
Case A cites Principle B.
```

不能推出：

```text
Principle B controlled the holding.
```

---

# 13. Relation Binding 只是这个 Core 的具体实现

对于天然适合关系表达的任务，可以内部使用：

```text
Subject
Predicate
Object
Context
Evidence
```

例如：

```yaml
subject: A
predicate: affects
object: B
context: Study-01
evidence: quote/table
```

但不能要求所有学科都必须转成三元组。

因此代码层建议支持：

```text
ClaimRecord
```

作为通用核心。

RelationRecord 可以是 ClaimRecord 的一种结构化 subtype。

---

# 14. 推荐数据模型

不要立即破坏现有 `EvidenceRecord`。

建议保持：

```text
EvidenceRecord
= 属性型证据

ClaimEvidenceRecord
= 主张型证据
```

推荐结构：

```yaml
claim_id: CLM001

target_claim:
  text: "A affects B"
  claim_type: RELATION

claim_components:
  subject: A
  predicate: affects
  object: B

evidence_context:
  context_id: CTX01
  source_role: CURRENT_STUDY_RESULT

support_status: SUPPORTED

support_type: EXPLICIT

verbatim_evidence:
  text: "..."

location:
  page: 6
  section: Results

current_study: true

notes: null
```

对于不适合三元组的主张：

```yaml
claim_id: CLM002

target_claim:
  text: "The author interprets X as a normative rather than descriptive concept"
  claim_type: PROPOSITION

claim_components: null
```

这样保持通用性。

---

# 15. Skill 2 主流程应该如何改

当前：

```text
Phase A Extraction
↓
Phase B Verification
↓
Auditor
```

建议改成：

```text
Phase A1 Candidate Evidence Detection
↓
Phase A2 Claim–Evidence Alignment
↓
Phase B Verification
↓
Evidence Auditor
```

---

# 16. Phase A1 — Candidate Evidence Detection

目标：

```text
找出可能相关的实体
变量
数值
句子
表格
结果
```

此阶段允许高召回。

但：

> Candidate 不能直接进入最终结果。

---

# 17. Phase A2 — Claim–Evidence Alignment

对每一个候选检查：

```text
这个证据到底支持什么？
```

而不是：

```text
这里有没有目标关键词？
```

核心问题：

```text
Does this evidence support the exact target claim?
```

---

# 18. Phase B — Verification

验证：

```text
证据是否真实
证据是否完整
证据是否同一上下文
关系是否真正成立
是否发生跨 Context 转移
```

---

# 19. Auditor 必须新增一条通用硬门

建议把 Auditor 从 14 项升级到 15 项。

新增：

# 15. Claim–Evidence Alignment Audit

检查：

```text
[ ] 用户目标主张是否明确
[ ] 当前证据是否支持主张本身，而不仅支持相关实体
[ ] 是否存在“共现 → 关系”的偷换
[ ] 是否跨实验/队列/对象/数据集/章节拼接
[ ] 是否引用前人结果冒充当前研究
[ ] 是否背景/环境信息被升级为目标关系
[ ] 是否作者推测被升级为结果
[ ] 是否模型增加了原文未提供的 Predicate
```

只要任一失败：

```text
不得进入 Confirmed Output
```

---

# 20. 建议修改 `specialist_role.md`

新增铁律：

## 铁律 9：实体出现绝不等于目标主张成立

建议正文：

```markdown
当用户要求抽取关系、作用、因果、关联、比较、支持/反驳等主张型信息时，
任何实体、变量或概念即使真实出现在论文中，也不得仅凭出现或共现就被写入目标结论。

必须验证原文证据是否真正支持用户要求的完整主张。

例如：
A 与 B 同时出现，只能证明 A 与 B 被共同提及；
不能自动推出 A 导致 B、A 影响 B、A 优于 B、A 支持 B 或 A 与 B 存在用户要求的关系。
```

---

# 21. 建议修改 `SKILL.md`

在 Core Philosophy 后增加：

```markdown
### Universal Claim–Evidence Alignment Rule

For any claim-oriented or relation-oriented extraction task,
ScholarFlow MUST verify the requested proposition itself.

The mere presence, co-occurrence, contextual proximity, or shared measurement
of relevant entities is not evidence that the requested relation or proposition holds.

A confirmed claim may be emitted only when the source explicitly or structurally
supports that claim within the correct evidence context.
```

---

# 22. 建议新增 reference 文件

新增：

```text
skills/literature-evidence-extraction/references/
└── claim_evidence_alignment.md
```

这个文件应该成为所有 Claim/Relation 类型任务的 mandatory reference。

不要叫：

```text
diet_filter.md
relation_ecology.md
```

---

# 23. 触发规则

在 SKILL.md 中增加：

```text
If extraction_semantics == CLAIM_RELATION:
    MUST load references/claim_evidence_alignment.md
```

如果只是：

```text
属性值抽取
```

则不必额外加载。

---

# 24. Stage 0 如何处理

Context Resolution 应自动判断：

```text
ATTRIBUTE
CLAIM_RELATION
MIXED
```

例如：

```text
“提取样本量、PCR参数以及处理是否提高成功率”
```

属于：

```text
MIXED
```

其中：

```text
样本量/PCR参数 → Attribute
处理提高成功率 → Claim Relation
```

只有关系部分进入 Claim–Evidence Alignment Gate。

---

# 25. 不应增加无意义 Grill-Me

如果用户已经明确：

```text
“这个因素是否影响死亡率？”
```

不要问：

```text
“你是要提取关系吗？”
```

直接识别：

```text
CLAIM_RELATION
```

并写入：

```text
INFERRED_HIGH_CONFIDENCE
```

---

# 26. 推荐内部 Claim Context

每个主张候选最好绑定：

```text
context_id
```

例如：

```text
CTX01 = Cohort A
CTX02 = Cohort B
CTX03 = Dataset X
CTX04 = Experiment 2
CTX05 = Discussion interpretation
```

这样防止：

```text
从 CTX01 提取 Subject
从 CTX02 提取 Object
再拼成一个不存在的关系
```

---

# 27. 禁止 Cross-Context Claim Assembly

必须写成硬规则：

> **A claim MUST NOT be assembled by combining evidence fragments from incompatible contexts unless the source itself explicitly establishes that cross-context relation.**

中文：

> **不得将不同、不兼容上下文中的证据片段自行拼接成一个原文未建立的科学主张。**

---

# 28. 表格证据特别规则

关系型表格不能只保存单元格。

例如表中只有：

```text
Model A | 0.91
```

如果表头是：

```text
Accuracy on Dataset X
```

完整证据必须包含：

```text
Table title
Column header
Row
```

才能证明：

```text
Model A accuracy = 0.91 on Dataset X
```

如果要进一步证明：

```text
Model A outperforms Model B
```

还必须比较对应行，并确认：

```text
same dataset
same metric
same evaluation protocol
```

所以关系证据应允许：

```text
STRUCTURED_EVIDENCE_BUNDLE
```

而不是只允许一句 Quote。

---

# 29. 推荐 Evidence Bundle

```yaml
evidence_bundle:
  type: TABLE_HEADER_ROW
  components:
    - table_title
    - column_header
    - row
```

其他可能：

```text
FIGURE_CAPTION_POINT
METHOD_RESULT_PAIR
THEORETICAL_ARGUMENT_SPAN
MULTI_SENTENCE_LOCAL_CONTEXT
```

---

# 30. 允许多句证据，但必须局部且必要

当前 Quote-First 强调 Minimal Sufficient Quote。

对主张型任务可扩展为：

```text
Minimal Sufficient Evidence Span
```

不要求一定是一句话。

例如一个主张可能需要：

```text
前一句定义比较组
+
后一句报告结果
```

这种可以允许。

但严禁：

```text
从全文不同位置拼出模型自己想要的关系
```

---

# 31. 当前研究 vs 引用文献必须严格隔离

用户问：

```text
“本文发现什么？”
```

则：

```text
REFERENCED_ONLY
```

不能进入 Confirmed。

如果用户问：

```text
“这篇论文提到了哪些已有研究结论？”
```

才可以纳入，但必须：

```text
current_study = false
```

---

# 32. Discussion 的处理

Discussion 中的主张要区分：

```text
Restatement of Result
Author Interpretation
Hypothesis
External Citation
Speculation
```

只有：

```text
Restatement of Result
```

可以与 Results 联合确认。

其他必须标：

```text
AUTHOR_INTERPRETATION
REFERENCED_ONLY
AMBIGUOUS
```

---

# 33. 用户要的是“所有提及”时怎么办

如果用户明确：

```text
“列出文章里所有出现过的植物”
“列出所有提到的模型”
“列出所有变量”
```

这属于：

```text
ENTITY_MENTION_EXTRACTION
```

此时不应执行 Claim–Evidence Alignment Gate。

这非常重要：

> 不能为了防误抽，把“实体清单任务”也过度过滤。

---

# 34. 最终输出建议分层

主张型任务建议输出：

```text
A. Confirmed Claims
B. Derived / Partial Claims
C. Ambiguous Claims
D. Excluded Non-supporting Mentions
E. Referenced Claims
```

这样可以让用户看到：

> Agent 不是没找到，而是明确判断这些内容不能支持目标主张。

---

# 35. Excluded Non-supporting Mentions 的价值

建议保留：

```text
candidate
source context
reason excluded
```

例如：

```yaml
candidate: A
context: Study Area
decision: CONTEXT_ONLY
reason: entity mentioned without target relation
```

好处：

1. 可审计；
2. 防止重复判断；
3. 可用于 Benchmark；
4. 方便用户人工复核。

---

# 36. 推荐新增 Benchmark 指标

针对所有学科通用：

```text
Claim Precision
Claim Recall
False Relation Rate
Context Leakage Rate
Cross-Entity Leakage Rate
Referenced-to-Current Leakage Rate
Co-occurrence-to-Relation Error Rate
Unsupported Predicate Insertion Rate
```

---

# 37. 最重要的核心指标

建议新增：

# False Relation Rate

定义：

> 原文只支持实体出现/共现，但 Skill 错误输出目标关系成立的比例。

目标：

```text
0%
```

---

# 38. 再增加一个指标

# Unsupported Predicate Insertion Rate

定义：

> 原文没有表达某关系 Predicate，但 Agent 自动补上该 Predicate 的比例。

例如：

```text
A 与 B 同时出现
→ 自动补成 A affects B
```

目标：

```text
0%
```

---

# 39. 建议构建跨学科 Gold Set

至少：

```text
6 disciplines × 10 cases = 60 cases
```

建议：

```text
Life Sciences
Medicine
Computer Science
Social Science
Physical/Materials Science
Humanities/Law
```

每个领域至少包含：

```text
direct relation
co-occurrence only
background only
referenced relation
wrong entity context
ambiguous claim
structured-table relation
```

---

# 40. 必须加入的对抗测试

## Test A — Co-occurrence Only

```text
A and B were both measured.
```

目标：

```text
A affects B
```

预期：

```text
AMBIGUOUS / NOT SUPPORTED
```

---

## Test B — Background Mention

```text
Previous research has discussed A and B.
```

目标：

```text
Current study supports A→B
```

预期：

```text
REFERENCED_ONLY / BACKGROUND_ONLY
```

---

## Test C — Wrong Entity Context

```text
Group Y showed the effect.
```

目标：

```text
Group X
```

预期：

```text
OTHER_ENTITY_CONTEXT
```

---

## Test D — Direct Claim

```text
Treatment A significantly reduced Outcome B.
```

预期：

```text
SUPPORTED
```

---

## Test E — Structured Table Relation

```text
Table title + headers + rows
```

共同建立主张。

预期：

```text
SUPPORTED
```

---

## Test F — Discussion Speculation

```text
A may explain B.
```

没有结果证据。

预期：

```text
AUTHOR_INTERPRETATION / AMBIGUOUS
```

---

## Test G — Cross-context Assembly

一个段落出现 A，另一个无关实验出现 B。

模型不得拼：

```text
A affects B
```

---

# 41. 建议新增 Schema

如果需要机器可验证：

```text
schemas/claim_evidence_record.schema.json
```

但不要强迫所有 EvidenceRecord 变成 ClaimRecord。

推荐：

```text
EvidenceRecord
= 属性型证据

ClaimEvidenceRecord
= 主张型证据
```

---

# 42. ExtractionResult 扩展建议

```json
{
  "evidence_records": [],
  "claim_records": []
}
```

支持：

```text
attribute-only
claim-only
mixed
```

---

# 43. Backward Compatibility

如果：

```text
claim_records
```

缺失：

```text
视为旧版 Attribute-only ExtractionResult
```

不破坏已有流程。

---

# 44. 建议修改文件清单

## 必改

```text
skills/literature-evidence-extraction/SKILL.md
skills/literature-evidence-extraction/role/specialist_role.md
skills/literature-evidence-extraction/role/evidence_auditor.md
```

## 新增

```text
skills/literature-evidence-extraction/references/claim_evidence_alignment.md
```

## 建议新增

```text
tests/test_claim_evidence_alignment.py
benchmarks/data/claim_relation_gold_set.json
```

## 可选

```text
schemas/claim_evidence_record.schema.json
```

---

# 45. SKILL.md 推荐插入文本

```markdown
## Universal Claim–Evidence Alignment Principle

When the requested output is a scientific relation, proposition, comparison,
causal statement, association, interaction, support/refutation judgment,
or other claim-oriented fact, ScholarFlow MUST verify the target claim itself.

The mere presence, co-occurrence, proximity, or shared measurement of relevant
entities is insufficient evidence that the requested claim holds.

A claim may enter Confirmed Output only if the evidence explicitly or structurally
supports that claim within the correct evidence context.

Entity evidence must never be silently promoted into relation evidence.
```

---

# 46. specialist_role.md 推荐插入文本

```markdown
### 铁律 9：主张必须由主张级证据支持

当用户请求的是关系型或命题型信息时，
原文中出现相关实体、变量或概念并不足以支持该关系。

必须确认：
1. 用户要求的目标主张是什么；
2. 原文是否支持该主张本身；
3. 证据是否来自正确的研究/实验/队列/对象/数据集/论证上下文；
4. 是否存在被引用研究、背景信息、环境信息或其他对象关系的串入；
5. 模型是否添加了原文不存在的关系谓词。

如果只能证明实体存在，不能证明关系成立，则不得进入 Confirmed Output。
```

---

# 47. evidence_auditor.md 推荐新增第 15 项

```markdown
| 15 | Claim–Evidence Alignment | 证据只支持相关实体/变量出现，却被输出为目标关系或科学主张 | 强制降级为 AMBIGUOUS / CONTEXT_ONLY / REFERENCED_ONLY，或直接 REJECT |
```

并在审计表增加：

```text
[ ] Target claim explicitly identified
[ ] Evidence supports the claim itself
[ ] Correct evidence context
[ ] No cross-context assembly
[ ] No referenced-to-current leakage
[ ] No unsupported predicate insertion
```

---

# 48. `claim_evidence_alignment.md` 的推荐结构

建议内容结构：

```text
1. Principle
2. Attribute vs Claim Extraction
3. Trigger Conditions
4. Target Claim Identification
5. Evidence Context Matching
6. Claim Support Test
7. Source Role Classification
8. Inference Boundary
9. Output Status
10. Confirmed Output Gate
11. Structured Table Evidence
12. Multi-span Evidence
13. Cross-context Prohibition
14. Auditor Checklist
15. Cross-disciplinary Examples
16. Adversarial Cases
```

---

# 49. 不允许另一个 AI 做的事情

非常重要。

请明确告诉实施 AI：

## 禁止 1：不要把本修复写成食性专用

不得把 Core 写成：

```text
Animal
Plant
Diet
Vegetation
```

这些只能是 Example。

---

## 禁止 2：不要把所有关系任务强制转换成 SPO

SPO 是可选实现，不是底层 ontology。

---

## 禁止 3：不要靠巨大关键词表解决

不要创建：

```text
eat_words
medical_relation_words
cs_relation_words
...
```

Core 必须依靠：

```text
semantic claim identification
+
evidence-context alignment
```

---

## 禁止 4：不要取消 Quote-First

新原则是在 Quote-First 上增加一层：

```text
Quote must support the target claim
```

不是替换 Quote-First。

---

## 禁止 5：不要自动把 Discussion 全排除

Discussion 可能重述 Results。

应分类，而不是机械删除。

---

## 禁止 6：不要把 REFERENCED_ONLY 当成错误

它可能是有效信息。

只是：

```text
不能冒充 Current Study Evidence
```

---

# 50. 最低可行修复 MVP

如果暂时不修改 Schema 和代码，至少马上完成：

```text
1. SKILL.md 加 Universal Claim–Evidence Alignment Rule
2. specialist_role.md 加铁律 9
3. evidence_auditor.md 加第 15 项
4. 新增 claim_evidence_alignment.md
5. 增加至少 7 个跨学科对抗测试
```

只做这 5 项，就能显著减少：

```text
Entity Mention
→ False Relation
```

问题。

---

# 51. 推荐 PR 拆分

## PR 1 — Core Principle

```text
feat(extraction): add universal claim-evidence alignment gate
```

修改：

```text
SKILL.md
specialist_role.md
evidence_auditor.md
claim_evidence_alignment.md
```

---

## PR 2 — Tests

```text
test(extraction): add cross-domain false-relation adversarial cases
```

---

## PR 3 — Optional Schema

```text
feat(schema): add claim-evidence record support
```

这一步可以晚一些。

---

# 52. Definition of Done

只有全部满足才算完成。

## Core

```text
[ ] Core 不出现单学科默认 ontology
[ ] Mention ≠ Relation 明确写入
[ ] Co-occurrence ≠ Relation 明确写入
[ ] Contextual proximity ≠ Relation 明确写入
```

## Skill 2

```text
[ ] 自动区分 ATTRIBUTE vs CLAIM_RELATION
[ ] Claim task 强制加载 alignment protocol
[ ] Confirmed output 必须经过 claim-level verification
```

## Auditor

```text
[ ] 增加第 15 项 Claim–Evidence Alignment
[ ] 能识别 entity-only evidence
[ ] 能识别 cross-context leakage
[ ] 能识别 referenced-to-current leakage
[ ] 能识别 unsupported predicate insertion
```

## Tests

```text
[ ] Life sciences case PASS
[ ] Medicine case PASS
[ ] CS case PASS
[ ] Social science case PASS
[ ] Humanities/Law case PASS
[ ] False Relation Rate = 0 in gold set
```

---

# 53. 最终执行算法

```text
User asks for information
        ↓
Determine extraction semantics
        ↓
ATTRIBUTE ?
    YES
      → normal Quote-First extraction

CLAIM / RELATION ?
    YES
      ↓
Identify Target Claim
      ↓
Find Candidate Evidence
      ↓
Classify Evidence Context
      ↓
Does evidence support the claim itself?
      ↓
NO
→ AMBIGUOUS / CONTEXT_ONLY / REFERENCED_ONLY / etc.
      ↓
YES
→ Verify context compatibility
      ↓
Verify no cross-context assembly
      ↓
Verify inference boundary
      ↓
Evidence Auditor
      ↓
Confirmed Claim
```

---

# 54. 最终正式原则

建议将以下文字作为 ScholarFlow Skill 2 的正式底层原则：

> **A scientific claim must be supported at the level of the claim itself. Evidence that merely mentions, measures, or co-locates the entities involved is insufficient to establish the requested relation or proposition. ScholarFlow must preserve the distinction between entity evidence and claim evidence, and must never silently promote co-occurrence, contextual proximity, background description, cited work, or shared observation into a confirmed scientific relation.**

中文：

> **科学主张必须由“主张级证据”支持。仅仅提及、测量或共同出现于同一上下文中的实体，不足以证明用户要求的关系或命题成立。ScholarFlow 必须严格区分“实体证据”和“主张证据”，不得将共现、上下文邻近、背景描述、引用前人研究或共同观测静默升级为已确认的科学关系。**

---

# 55. 最终定位

这次修改不应该被描述为：

```text
Relation Extraction Feature
```

更准确的是：

# Evidence Semantics Hardening

因为它解决的是一个比关系抽取更底层的问题：

> **证据到底支持什么层级的主张？**

最终目标是：

```text
Quote exists
≠
Claim supported

Entity exists
≠
Relation supported

Only aligned evidence
→ confirmed claim
```

这条原则应当成为 ScholarFlow Skill 2 面向所有学科的长期底层证据纪律。

# ScholarFlow Skill 2 — Adaptive Evidence Context Expansion 强化实施操作文档
## 全学科通用“候选证据上下文扩展与语义核验”增量增强方案

> 适用 Skill：`literature-evidence-extraction`  
> 改造性质：**增量强化，不重构 Skill 2 主体架构**  
> 面向对象：**所有学科、普通用户与专业用户**  
> 核心目标：让 Skill 2 在“定位到关键词/候选句”后，不立即抽取，而是先主动扩展并理解上下文，确认该信息是否真正回答用户的问题，再进入结构化抽取与审计。
>
> 本方案必须保持：
>
> ```text
> Discipline-neutral Core
> +
> Domain-aware Interpretation
> ```
>
> 禁止将本方案实现为生态学、医学、计算机科学等任何单一学科的专用逻辑。

---

# 1. 本次增强解决的问题

当前 Skill 2 已经具备：

```text
Stage 0
→ Dynamic Schema
→ Candidate Detection
→ Claim–Evidence Alignment
→ Verification
→ Evidence Auditor
```

并已经建立：

```text
Mention ≠ Relation
Co-occurrence ≠ Relation
Entity Evidence ≠ Claim Evidence
```

这些原则继续保留。

本轮要补的是更基础的一层：

> **Candidate Hit ≠ Evidence**

关键词、实体、数值、表格行、图注或句子被命中，只能说明“这里可能有关”，不能直接说明“这里已经足够回答用户的问题”。

因此应新增正式底层原则：

> **A candidate evidence hit is only a retrieval clue. It becomes eligible evidence only after sufficient surrounding context has been examined and its semantic role has been verified against the user's target information need.**

中文：

> **候选命中只是定位线索。只有在读取了足够上下文，并确认其语义角色确实与用户目标信息一致后，该候选才能升级为合格证据。**

---

# 2. Skill 2 应采用的核心链路

建议正式定义：

```text
Understand
↓
Formalize
↓
Locate
↓
Expand Context
↓
Interpret Context
↓
Align
↓
Extract
↓
Verify
↓
Audit
```

中文：

```text
理解用户问题
↓
形式化目标信息
↓
高召回定位候选
↓
自适应扩展上下文
↓
理解局部语义
↓
判断是否真正回答问题
↓
执行结构化抽取
↓
反向核验证据
↓
最终审计
```

必须固定顺序：

```text
Locate → Context → Interpret → Align → Extract
```

禁止：

```text
Locate → Extract → 再看 Context
```

---

# 3. 新增核心机制：Adaptive Evidence Context Expansion

建议正式命名：

# Adaptive Evidence Context Expansion（AECE）

中文：

# 自适应证据上下文扩展

基本循环：

```text
Candidate Hit
↓
读取最小局部上下文
↓
语义是否足够明确？
    ├─ YES → Semantic Verification
    └─ NO  → 扩展一个层级
                ↓
              再判断
```

直到：

```text
MEANING_RESOLVED
```

或：

```text
CONTEXT_EXHAUSTED
```

若上下文耗尽仍无法确定，必须输出 `AMBIGUOUS`，不得脑补。

---

# 4. 为什么固定 ±150 / ±250 字符不够

固定字符窗口可以保留，但只能作为：

```text
Candidate Localization
```

不能作为：

```text
Final Semantic Verification
```

原因是论文中的含义常依赖：

```text
前一句
后一句
整个段落
Section / Subsection 标题
表格标题与表头
图注与图例
脚注
方法定义
实验组/队列/数据集
比较对象
时间/空间条件
```

因此必须新增原则：

> **Context size is determined by semantic sufficiency, not by a fixed character count.**

---

# 5. 上下文扩展层级

建议使用以下通用层级。

## Level 0 — Exact Hit

仅查看：

```text
关键词
实体
数字
单元格
短语
```

作用：定位。

不得做最终证据判断。

## Level 1 — Sentence

读取完整句子，判断：

```text
主语是谁
说了什么
对象是谁
是否有否定
是否有条件
是否有不确定语气
```

## Level 2 — Adjacent Sentences

读取：

```text
前一句 + 当前句 + 后一句
```

主要解决：

```text
代词
省略主语
上下句承接
转折
前置定义
后置限定
```

## Level 3 — Paragraph

读取完整局部段落，判断该段的主要语义角色：

```text
背景
方法
结果
比较
解释
局限
定义
论证
```

## Level 4 — Section Context

读取：

```text
Section heading
Subsection heading
```

用于确定宏观语境。

## Level 5 — Structured Evidence Context

若候选来自结构化信息，必须读取：

### Table

```text
Table title
Column header
Row header
Cell
Footnote
```

### Figure

```text
Figure caption
Panel label
Axis label
Legend
Unit
```

### Equation

```text
Equation
Variable definitions
Applicable conditions
```

### Supplement / Appendix

```text
Supplement title
Section heading
Table/Figure context
```

## Level 6 — Context Unit

必要时绑定到独立研究单元，例如：

```text
Experiment
Cohort
Dataset
Treatment Arm
Population
Model
Sample
Time Period
Case
Argument
Historical Period
```

---

# 6. 上下文扩展停止条件

## STOP-A — Meaning Resolved

已经能明确回答：

```text
这里在说什么？
属于谁？
属于什么 Context？
是否回答用户问题？
```

## STOP-B — Structured Context Resolved

表题/表头/图注/章节信息已经足以确定含义。

## STOP-C — Context Exhausted

扩展到合理边界仍无法判断。

此时：

```text
AMBIGUOUS
```

不得继续推断。

---

# 7. 在定位之前先建立 Target Information Need（TIN）

建议新增内部对象：

# Target Information Need

简称：`TIN`

用户问题必须先被转成结构化目标。

推荐模型：

```yaml
target_information_need:
  task_type: ATTRIBUTE | CLAIM | RELATION | COMPARISON | PROCEDURE | INTERPRETATION
  target_entity: optional
  target_field: optional
  target_claim: optional
  required_context: optional
  exclusion_scope: optional
```

示例：

```text
用户：这篇论文用了多少样本？
```

```yaml
task_type: ATTRIBUTE
target_field: sample_size
```

```text
用户：这个处理是否提高存活率？
```

```yaml
task_type: CLAIM
target_claim: treatment increases survival
```

```text
用户：作者对理论 X 的态度是什么？
```

```yaml
task_type: INTERPRETATION
target_claim: author stance toward theory X
```

---

# 8. Search Clues 与 Evidence Criteria 必须分开

TIN 可以生成 Search Clues：

```text
目标实体
字段名
同义词
缩写
关系表达
变量名
常见表头
结构位置
```

但必须写成硬规则：

> **Search clues are retrieval aids, not evidence criteria.**

也就是说：

```text
关键词命中
≠
证据成立
```

---

# 9. Candidate Detection 应保持高召回

Phase A1 的目标应优先：

```text
Recall
```

而不是过早追求 Precision。

正确策略：

```text
宁可多找候选
↓
再通过上下文理解过滤
```

而不是：

```text
依靠越来越复杂的关键词规则
直接决定真伪
```

---

# 10. Candidate 类型

建议通用标记：

```text
TEXT_SENTENCE
PARAGRAPH
TABLE_ROW
TABLE_CELL
FIGURE_CAPTION
FIGURE_VALUE
SUPPLEMENT_ENTRY
EQUATION
FOOTNOTE
REFERENCE_CONTEXT
```

---

# 11. Candidate Lifecycle

建议新增正式生命周期：

```text
LOCATED
↓
CONTEXT_EXPANDING
↓
SEMANTICALLY_CLASSIFIED
↓
ALIGNED / PARTIALLY_ALIGNED / NOT_ALIGNED / AMBIGUOUS
↓
EXTRACTED
↓
VERIFIED
↓
AUDITED
```

硬规则：

```text
LOCATED
```

不得直接跳到：

```text
EXTRACTED
```

---

# 12. Semantic Context Classification

每个候选在抽取前必须判断“它在文献中扮演什么角色”。

推荐通用 enum：

```text
CURRENT_STUDY_METHOD
CURRENT_STUDY_RESULT
CURRENT_STUDY_OBSERVATION
BACKGROUND
REFERENCED_WORK
DISCUSSION_INTERPRETATION
LIMITATION
CONTEXT_DESCRIPTION
COMPARATOR_CONTEXT
OTHER_ENTITY_CONTEXT
DEFINITION
THEORETICAL_ARGUMENT
UNKNOWN
```

这套 enum 应保持跨学科通用。

---

# 13. Semantic Role 不等于 Section 名称

例如 `Discussion` 中可以存在：

```text
Results restatement
External citation
Interpretation
Speculation
Limitation
```

因此不得：

```text
section == Discussion
→ 自动判定同一种角色
```

Section 只能提供先验线索，最终需要语义理解。

---

# 14. Target Alignment 判定

上下文解释完成后必须回答：

> **Does this candidate actually answer the Target Information Need?**

推荐状态：

```text
ALIGNED
PARTIALLY_ALIGNED
NOT_ALIGNED
AMBIGUOUS
```

## ALIGNED

直接回答目标问题，可进入抽取。

## PARTIALLY_ALIGNED

只回答目标信息的一部分，例如报告方向但未报告数值。可以抽取，但必须保留缺失与边界。

## NOT_ALIGNED

关键词相关，但并未回答用户问题。不得进入最终结果。

## AMBIGUOUS

扩展上下文后仍无法确定。不得静默升格。

---

# 15. CandidateContextRecord

建议增加一个内部中间结构：

```yaml
candidate_id: CAND001

target_information_need_id: TIN01

locator:
  type: TEXT_SENTENCE
  page: 5
  offset: 2318

hit:
  text: "..."

context_expansion:
  level_reached: PARAGRAPH
  spans:
    - sentence
    - adjacent_sentences
    - paragraph
    - section_heading

semantic_role:
  value: CURRENT_STUDY_RESULT

alignment:
  status: ALIGNED

context_sufficiency:
  status: SUFFICIENT

decision:
  eligible_for_extraction: true
```

它不是替代 `EvidenceRecord`，而是成为：

```text
Candidate
↓
CandidateContextRecord
↓
EvidenceRecord
```

之间的中间门禁层。

---

# 16. Attribute Extraction 流程

对于样本量、温度、年份、剂量、参数等：

```text
TIN
↓
Locate Candidate
↓
Expand Context
↓
Confirm field/value/context binding
↓
Extract
↓
Verify
```

属性任务也必须做 Context Verification。

---

# 17. Claim / Relation Extraction 流程

对于关系、因果、比较、作用、支持/反驳等：

```text
TIN
↓
Locate Candidate
↓
Expand Context
↓
Semantic Role Classification
↓
Claim–Evidence Alignment
↓
Extract Claim
↓
Verify
```

因此：

```text
Context Verification
```

解决：

> 这里到底在说什么？

而：

```text
Claim–Evidence Alignment
```

解决：

> 它真的支持用户要求的主张吗？

顺序必须是：

```text
Context Verification
↓
Claim–Evidence Alignment
```

---

# 18. Quote-First 的升级

原：

```text
Quote → Extract → Verify
```

建议升级：

```text
Locate
→ Contextualize
→ Quote
→ Extract
→ Verify
```

更准确的公式：

```text
Candidate Hit
+
Sufficient Context
+
Semantic Match
=
Eligible Evidence
```

---

# 19. Minimal Sufficient Evidence Span

建议将 `Minimal Sufficient Quote` 扩展为：

# Minimal Sufficient Evidence Span

因为有效证据不一定是一句话。

可以是：

```text
Single sentence
Adjacent sentences
Paragraph fragment
Table title + header + row
Figure caption + panel/axis/legend
Equation + variable definition
Footnote + main statement
```

原则：

> 证据跨度应当最小，但必须足够独立理解其含义。

---

# 20. Multi-Span Evidence 边界

允许：

```text
前一句定义对象
+
下一句报告结果
```

条件：

```text
同一局部逻辑单元
同一 Context
无跨实验/跨对象
```

禁止：

```text
Page 2 提到 A
+
Page 15 提到 B
↓
模型自行拼接 A → B
```

应新增铁律：

> **Evidence fragments from distant or incompatible contexts MUST NOT be silently assembled into a single claim.**

---

# 21. 表格证据特别规则

如果候选来自单元格，必须至少扩展：

```text
Cell
↓
Row Header
↓
Column Header
↓
Table Title
↓
Relevant Footnote
```

直到可以回答：

```text
这个数值是谁的？
是什么指标？
在哪个条件下？
与谁比较？
单位是什么？
```

单独的 `0.91` 不能成为 EvidenceRecord。

---

# 22. 图表证据规则

来自 Figure 时至少考虑：

```text
Figure caption
Panel label
Axis labels
Legend
Unit
Comparator
```

不能只依靠图中的一个数字或图例颜色。

---

# 23. Supplement / Appendix

补充材料可以是正式证据来源。

但必须绑定：

```text
Supplement Context
```

不能因为是补充材料就自动降级，也不能脱离其表题/章节读取。

---

# 24. Section Priority 只能用于定位优先级

例如：

```text
Results → 通常优先找结果
Methods → 通常优先找方法
```

但严禁：

```text
Results = 一定有效证据
Discussion = 一定无效证据
```

最终裁决仍由上下文语义决定。

---

# 25. Context Sufficiency 核验维度

每个候选至少检查：

```text
Who / What
What is being reported
Which Context Unit
Current study or external source
Method / Result / Interpretation / Background
Conditions
Comparator
Scope
Negation
Modality
Quantifier
```

---

# 26. Negation 检查

例如：

```text
A did not significantly affect B.
```

只检索 `affect` 会严重误判。

必须检查：

```text
not
no evidence
failed to
did not
non-significant
```

---

# 27. Modality 检查

例如：

```text
may
might
could
suggest
possibly
likely
```

这些词会改变主张强度。

不能把：

```text
may affect
```

升级成：

```text
affects
```

---

# 28. Quantifier 检查

例如：

```text
some
most
all
subset
only
primarily
occasionally
```

量词必须保留，防止过度泛化。

---

# 29. Condition 检查

例如：

```text
under condition X
in subgroup A
during period Y
on Dataset Z
after adjustment
```

条件必须绑定到抽取结果。

---

# 30. Comparator 检查

例如：

```text
compared with control
relative to baseline
versus Model B
```

比较对象不得丢失。

---

# 31. Scope 检查

例如结论只适用于：

```text
one population
one country
one dataset
one historical period
one legal jurisdiction
```

不得自动升级为一般性结论。

---

# 32. 用户问题很宽泛时

例如：

```text
“提取这篇论文的重要信息”
```

应先构建动态 Schema，再执行 AECE。

不要直接对全文做无目标关键词扫描。

---

# 33. 用户问题明确时

例如：

```text
“样本量是多少？”
```

无需额外 Grill。

直接形成 TIN 并执行。

---

# 34. AECE 是内部协议，不应增加用户负担

除非 TIN 本身存在真正关键歧义，否则：

```text
读取上下文
```

是默认义务，不需要问用户：

```text
“是否需要我看上下文？”
```

---

# 35. 工具与 AI 的职责分工

## Deterministic Tools

负责：

```text
PDF parse
page/offset location
keyword candidate search
sentence/paragraph extraction
OCR anomaly detection
quote back-check
structured table context retrieval
cross-context hard checks
```

## AI Agent

负责：

```text
理解用户问题
构建 Target Information Need
动态 Schema
判断上下文是否足够
理解语义角色
判断是否回答目标问题
处理学科语义
判断不确定性
```

---

# 36. 不要用正则替代语义理解

必须明确：

```text
Regex / keyword matching
```

只能作为：

```text
locator
guard
risk detector
```

不能作为完整：

```text
semantic verifier
```

---

# 37. 不建立巨大领域关键词库

禁止将 Core 实现成：

```text
ecology_keywords
medical_keywords
legal_keywords
cs_keywords
...
```

底层应保持：

```text
Target Information Need
+
Adaptive Context Expansion
+
Semantic Interpretation
+
Domain Lens
```

Domain Lens 只能辅助解释，不能替代通用证据纪律。

---

# 38. SKILL.md 主流程建议

当前 Phase A 可强化成：

```text
Phase A1 — Candidate Detection
↓
Phase A1.5 — Adaptive Evidence Context Expansion
↓
Phase A1.6 — Semantic Context Verification
↓
Phase A2 — Claim–Evidence Alignment（仅 Claim/Relation 必需）
```

属性任务：

```text
A1 → A1.5 → A1.6 → Phase B
```

关系/主张任务：

```text
A1 → A1.5 → A1.6 → A2 → Phase B
```

---

# 39. 建议新增 reference 文件

新增：

```text
skills/literature-evidence-extraction/references/
└── adaptive_evidence_context_expansion.md
```

建议结构：

```text
1. Principle
2. Target Information Need
3. Candidate Detection
4. Context Expansion Levels
5. Semantic Role Classification
6. Alignment Decision
7. Context Sufficiency
8. Structured Evidence
9. Multi-span Evidence
10. Stop Conditions
11. Ambiguity Handling
12. Auditor Rules
13. Cross-disciplinary Examples
14. Anti-patterns
15. Tests
```

---

# 40. specialist_role.md 建议新增铁律 10

```markdown
### 铁律 10：候选命中绝不等于合格证据

关键词、实体、数值、句子或表格单元格的命中只用于候选定位。

在执行抽取前，主导抽取专员必须读取足够的局部上下文，明确该候选的语义角色、所属对象、Context Unit、来源角色、条件与比较边界，并确认其确实回答用户的 Target Information Need。

未经上下文核验的 Candidate Hit 不得直接创建 EvidenceRecord。
```

---

# 41. Evidence Auditor 建议升级为 16 项

新增：

# 16. Context Sufficiency Audit

检查：

```text
[ ] 是否只凭关键词命中抽取
[ ] 是否至少读取完整语义单元
[ ] 必要时是否扩展到相邻句/段落
[ ] 是否检查 Section / Table / Figure Context
[ ] 是否明确 Semantic Role
[ ] 是否明确 Context Unit
[ ] 是否确认候选真正回答 Target Information Need
[ ] 是否存在远距离证据拼接
```

若 EvidenceRecord 只有 hit、没有 sufficient context：

```text
REJECT
```

---

# 42. Context Sufficiency 状态

建议：

```text
SUFFICIENT
PARTIALLY_SUFFICIENT
INSUFFICIENT
```

Confirmed Evidence 默认要求：

```text
context_sufficiency = SUFFICIENT
```

`PARTIALLY_SUFFICIENT` 只能进入带不确定性的输出，不得无标记确认为事实。

---

# 43. Cross-disciplinary Examples

以下仅作为测试与理解示例，禁止硬编码进 Core。

## Life Sciences

```text
Gene A and Gene B were expressed.
```

上下文若只支持共同表达，则不能输出：

```text
Gene A regulates Gene B
```

## Medicine

命中：

```text
Mortality was 8%.
```

必须进一步确认：

```text
哪个组？
什么时间点？
原始还是调整后？
```

## Computer Science

命中：

```text
92.4
```

必须确认：

```text
哪个模型？
哪个 Dataset？
什么 Metric？
哪个 split？
```

## Social Sciences

命中：

```text
income increased
```

必须确认：

```text
描述统计？
相关性？
因果估计？
哪个群体？
什么模型？
```

## Materials / Engineering

命中：

```text
650°C
```

必须确认：

```text
合成温度？
退火温度？
测试温度？
```

## Law

命中：

```text
the court cited Principle A
```

必须继续判断：

```text
仅引用？
采用？
区分？
拒绝？
```

## Humanities

命中理论名，不等于作者支持该理论。必须结合论证语境判断其立场。

---

# 44. Anti-patterns

## Anti-pattern 1 — Keyword-to-Fact Jump

```text
关键词命中
→ 直接抽值/下结论
```

禁止。

## Anti-pattern 2 — Fixed Window Absolutism

```text
永远 ±250 字符
```

禁止作为最终上下文充分性标准。

## Anti-pattern 3 — Section Shortcut

```text
Results = 自动可信
Discussion = 自动无效
```

禁止。

## Anti-pattern 4 — Table Cell Isolation

只抽单元格，不带标题/行列头。

禁止。

## Anti-pattern 5 — Long-distance Evidence Stitching

跨页面、跨实验、跨对象拼成一个关系。

禁止。

## Anti-pattern 6 — Domain Keyword Hardcoding

用巨大领域词表替代语义理解。

禁止。

---

# 45. 测试建议

至少新增：

```text
1. test_candidate_hit_not_directly_extracted
2. test_sentence_context_sufficient
3. test_adjacent_sentence_expansion
4. test_paragraph_expansion_when_reference_requires_context
5. test_section_heading_changes_semantic_role
6. test_table_cell_requires_header_context
7. test_figure_value_requires_caption_context
8. test_context_exhausted_returns_ambiguous
9. test_cross_context_stitching_rejected
10. test_negation_detected
11. test_modal_language_downgrades_claim
12. test_condition_scope_preserved
13. test_comparator_context_preserved
14. test_attribute_task_uses_context_verification
15. test_claim_task_adds_claim_alignment
```

---

# 46. 跨学科测试矩阵

建议至少覆盖：

```text
Life Sciences
Medicine
Computer Science
Social Sciences
Physical Sciences
Engineering
Humanities
Law
```

每个学科至少包含：

```text
1 positive case
1 context trap
1 ambiguous case
```

---

# 47. Benchmark 指标

新增：

```text
Candidate-to-Evidence Precision
Candidate-to-Evidence False Promotion Rate
Context Misclassification Rate
Context Leakage Rate
Unsupported Extraction Rate
Long-distance Stitching Error Rate
Context Expansion Success Rate
Context Sufficiency Failure Rate
```

最重要两个指标：

## Candidate-to-Evidence False Promotion Rate

定义：候选命中被错误升级成 EvidenceRecord 的比例。

目标：

```text
0%
```

## Context Sufficiency Failure Rate

定义：最终输出证据无法从其绑定上下文独立理解含义的比例。

目标：

```text
0%
```

---

# 48. 工具实现建议

不建议把 AECE 全部写成 Python。

Python 可提供：

```text
get_sentence()
get_adjacent_sentences()
get_paragraph()
get_section_heading()
get_table_context()
get_figure_caption()
```

Agent 决定：

```text
当前上下文是否足够？
是否需要继续扩展？
真实语义角色是什么？
```

概念 API：

```python
expand_candidate_context(
    candidate,
    level="paragraph"
)
```

---

# 49. MVP

第一版不要求完整 layout parser。

最低可行实现：

```text
1. SKILL.md 增加 A1.5 / A1.6
2. 新增 adaptive_evidence_context_expansion.md
3. specialist_role.md 增加铁律 10
4. evidence_auditor.md 增加 Context Sufficiency Audit
5. locator 支持 sentence / adjacent sentences / paragraph / section heading
6. 表格至少支持 title + header + row
7. 增加跨学科对抗测试
```

---

# 50. 推荐 PR 拆分

## PR 1

```text
feat(extraction): add adaptive evidence context expansion protocol
```

## PR 2

```text
feat(extraction): add context-aware candidate lifecycle
```

## PR 3

```text
test(extraction): add cross-domain context verification adversarial suite
```

## PR 4

```text
docs(extraction): formalize candidate-hit-to-evidence promotion rules
```

---

# 51. Definition of Done

## Core

```text
[ ] Candidate Hit ≠ Evidence 明确写入 Core
[ ] Locate → Context → Interpret → Align → Extract 顺序明确
```

## Context Expansion

```text
[ ] 支持 sentence
[ ] 支持 adjacent sentences
[ ] 支持 paragraph
[ ] 支持 section context
[ ] 支持 structured evidence context
```

## Semantic Verification

```text
[ ] 每个 Candidate 有 semantic_role
[ ] 每个 Candidate 有 alignment_status
[ ] 每个 Candidate 有 context_sufficiency
[ ] UNKNOWN / INSUFFICIENT 不得自动确认
```

## Evidence Promotion

```text
[ ] LOCATED 不能直接创建 EvidenceRecord
[ ] 必须通过 Context Sufficiency
[ ] Claim/Relation 还必须通过 Claim–Evidence Alignment
```

## Auditor

```text
[ ] 新增 Context Sufficiency Audit
[ ] 能识别 keyword-only extraction
[ ] 能识别 fixed-window insufficiency
[ ] 能识别 table-cell isolation
[ ] 能识别 long-distance stitching
```

## Cross-disciplinary

```text
[ ] Core 无单学科硬编码
[ ] 至少 6 个学科测试
[ ] Domain Lens 只做辅助解释
```

---

# 52. 最终架构

```text
User Question
↓
Context Resolution
↓
Target Information Need
↓
Dynamic Schema / Target Claim
↓
Candidate Detection
↓
Adaptive Context Expansion
↓
Semantic Context Verification
↓
Target Alignment
↓
Extraction
↓
Evidence Verification
↓
Evidence Auditor
↓
Structured Output
```

---

# 53. Skill 2 的强化职责定义

建议写入：

> **Skill 2 should not merely locate information. It must determine whether the located information actually means what the user is asking for.**

中文：

> **Skill 2 不只是“找到相关文字”，更重要的是判断“找到的文字是否真的表达了用户想知道的内容”。**

每个候选至少回答三问：

```text
1. Did I find something relevant?
2. What does this passage actually mean?
3. Does it actually answer the user's target question?
```

只有全部通过：

```text
Candidate
→ Evidence
```

---

# 54. 最终底层原则

建议作为正式 Core 文案：

> **Localization finds candidates; context establishes meaning; alignment determines evidential relevance. Only after all three stages may ScholarFlow extract a scientific fact, relation, interpretation, or claim.**

中文：

> **定位只能找到候选，上下文决定候选的真实含义，目标对齐决定其是否具有证据相关性。只有这三个阶段全部完成后，ScholarFlow 才能将其抽取为事实、关系、解释或主张。**

---

# 55. 最终结论

本次不需要推翻 Skill 2。

现有：

```text
Dynamic Schema
Candidate Detection
Claim–Evidence Alignment
Verification
Evidence Auditor
```

全部保留。

只需在：

```text
Candidate Detection
```

与：

```text
Claim–Evidence Alignment / Verification
```

之间增加正式、强制、可审计的：

# Adaptive Evidence Context Expansion & Semantic Verification Layer

最终 Skill 2 从：

```text
Find → Extract → Verify
```

强化为：

```text
Understand
→ Locate
→ Contextualize
→ Interpret
→ Align
→ Extract
→ Verify
```

这套机制面向大众、跨学科通用，不依赖任何单一领域。

它解决的核心问题是：

> **AI 不仅要搜到关键词，还必须真正理解关键词所在的上下文，再决定它是不是用户要的证据。**

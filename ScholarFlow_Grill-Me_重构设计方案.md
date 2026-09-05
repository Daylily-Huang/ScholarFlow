# ScholarFlow Grill-Me 重构设计方案

> 适用仓库：`Daylily-Huang/ScholarFlow`  
> 目标：将当前三个 Skill 中偏固定问卷式的 `stage0_grill_me.md`，重构为一个**面向通用科研领域、动态适配学科、带推荐答案、有限轮次、有状态硬门禁**的交互决策系统。  
> 核心原则：**预设决策方向，不预设具体问题；根据用户任务、学科和当前上下文动态生成问题。**

---

# 一、为什么需要重构 Grill-Me

当前三个 Skill 的 Grill-Me 已经具备以下优点：

- 有 Stage 0 前置门禁；
- 有推荐选项；
- 有任务快照；
- 能区分 Search / Extraction / Synthesis 三类任务。

但实际使用中仍存在几个明显问题：

1. Agent 有时直接进入执行，不主动 Grill-Me；
2. 当前问题偏固定问卷，不够适应不同学科；
3. 某些真正决定科研结果的问题没有被问到；
4. 有些低影响问题反而被固定设置为“必问”；
5. 三个 Skill 各维护一套 Grill-Me 逻辑，后续容易分叉；
6. 问题虽然有 Recommended，但缺少统一、低成本的用户作答协议；
7. 缺少明确的状态机：Agent 不知道何时必须停下等待用户，何时可以开始执行。

因此，建议把 Grill-Me 从：

> “一组推荐问题”

升级为：

> **ScholarFlow Adaptive Research Grill Engine**

---

# 二、核心设计思想

建议采用：

```text
预设 Decision Dimensions
        ↓
识别用户任务与学科
        ↓
判断哪些维度已经明确
        ↓
找出真正影响结果的未决变量
        ↓
根据学科动态生成 3–5 个问题
        ↓
每题提供 Recommended 答案
        ↓
用户快速选择
        ↓
必要时第二轮深挖
        ↓
Protocol Snapshot
        ↓
CONFIRMED
        ↓
允许执行
```

核心原则：

> **不预设具体问题，预设需要解决的科研决策方向。**

---

# 三、为什么“Recommended Answer”应该保留并强化

Recommended 不是装饰，而应该成为 ScholarFlow Grill-Me 的核心交互机制。

它有三个作用。

## 1. 降低用户输入成本

用户不需要每次重新组织自然语言。

支持：

```text
按推荐
```

或者：

```text
1B 2C 3A 4B
```

或者：

```text
Q2 改成 C，其余按推荐
```

---

## 2. 让 Agent 展示专业判断

Grill-Me 不应该把所有决策都推给用户。

例如：

> 是否需要硕博论文？

如果任务明显是：

```text
实验方法比较 / 参数提取
```

Agent 可以推荐：

```text
(Recommended) Include theses
```

并给简短理由：

> 学位论文通常报告更完整的方法细节。

---

## 3. 推荐答案必须是“可解释推荐”

每个 Recommended 选项建议附一个非常短的理由。

推荐格式：

```text
B. Deep Literature Review (Recommended)
   适合当前任务，因为你需要建立较完整的方法与证据版图。
```

不要只写：

```text
B. Deep Search (Recommended)
```

而没有解释为什么。

---

# 四、Grill-Me 不应固定问题，应固定“Decision Dimensions”

建议统一定义四类变量。

## Critical

未解决时：

```text
禁止执行。
```

---

## High Impact

不同选择会明显改变科研结果。

优先 Grill。

---

## Defaultable

存在合理默认值。

不必占用宝贵提问额度。

---

## Cosmetic

仅涉及输出形式、排版等。

通常不要 Grill。

---

例如：

| 变量 | 级别 |
|---|---|
| 核心科学问题 | Critical |
| 纳入边界 | Critical |
| 是否允许跨物种扩展 | High Impact |
| 时间范围 | Defaultable |
| Markdown 还是 CSV | Cosmetic |

---

# 五、统一的 Grill-Me 状态机

建议所有 Skill 使用同一个状态模型。

```text
STAGE0_UNRESOLVED
        ↓
GRILL_REQUIRED
        ↓
QUESTIONS_EMITTED
        ↓
AWAITING_USER
        ↓
USER_RESPONSE_PARSED
        ↓
RECHECK_UNRESOLVED_DIMENSIONS
        ↓
    ┌───────────────┐
    │               │
还有 Critical       已全部解决
    │               │
ROUND_2_GRILL        ↓
    │            SNAPSHOT_READY
    │               ↓
    └────────→ CONFIRMED
                    ↓
             EXECUTION_ALLOWED
```

另外允许两个特殊状态：

```text
BYPASSED_BY_USER
HEADLESS_CONFIGURED
```

---

# 六、最重要的执行规则：问完必须 STOP

当前最容易导致 Grill-Me 被跳过的问题，就是 Agent 一边问，一边继续干活。

建议在 shared protocol 中写成硬规则：

```text
INTERACTIVE HARD GATE

In interactive mode, if unresolved Critical or High-Impact
decision dimensions remain, the Agent MUST:

1. Generate Grill-Me questions.
2. Provide a Recommended option for every question.
3. Emit no substantive Search / Extraction / Synthesis result.
4. STOP the current turn immediately after the questions.
5. Wait for the user's answer.

Execution is forbidden while:
stage0_status != CONFIRMED
```

再强调：

```text
Do not ask Grill-Me questions and then continue execution
using assumed answers in the same turn.
```

---

# 七、允许跳过 Grill-Me 的情况

只允许：

## A. 用户明确说

例如：

```text
直接执行
不用问我
全部按推荐
skip grill-me
```

状态：

```text
BYPASSED_BY_USER
```

---

## B. Headless 模式已经提供完整配置

例如：

```json
{
  "research_goal": "...",
  "scope": "...",
  "inclusion": "...",
  "exclusion": "..."
}
```

状态：

```text
HEADLESS_CONFIGURED
```

---

## C. 当前用户请求已经把所有 Critical variables 明确说完

此时不应该为了“形式上 Grill-Me”而重复问。

可以直接：

```text
Protocol Snapshot
```

然后进入执行。

---

# 八、不要重复问已经明确的信息

每个变量必须记录来源。

推荐四种状态：

```text
RESOLVED_FROM_USER
INFERRED_HIGH_CONFIDENCE
DEFAULTED
UNRESOLVED
```

例如：

```yaml
publication_range:
  value: 2015-2026
  status: RESOLVED_FROM_USER
```

就禁止再次问：

> 你需要哪个时间范围？

---

# 九、动态学科适配：Domain Lens

ScholarFlow 是开源通用 Skill，不应该在问题里硬编码：

- 分子生态学；
- 种群生态学；
- 医学；
- 计算机。

建议采用：

```text
Generic Decision Dimensions
        +
Domain Lens
```

---

# 十、Domain Lens 不是问题库

Domain Lens 只告诉 Agent：

> 在当前学科，哪些变量尤其值得关注。

例如：

```yaml
biomedicine:
  high_risk_dimensions:
    - population
    - intervention
    - comparator
    - outcome
    - study_design

ecology:
  high_risk_dimensions:
    - taxon
    - spatial_scale
    - temporal_scale
    - detection_process
    - environmental_context

computer_science:
  high_risk_dimensions:
    - task
    - dataset
    - model_family
    - evaluation_metric
    - train_test_protocol

chemistry:
  high_risk_dimensions:
    - compound_class
    - reaction_condition
    - catalyst
    - solvent
    - yield_metric
```

这些不是固定问句。

Agent 根据当前用户问题动态生成问题。

---

# 十一、同一个 Decision Dimension 应根据学科变化

例如：

```text
Comparability Boundary
```

## 医学

Agent 可以问：

> 成人和儿童研究是否允许作为同一个证据组进行综合？

---

## 生态学

可以问：

> 不同物种或不同地理区域的研究是否允许直接进入同一 Claim 比较？

---

## 机器学习

可以问：

> 不同 benchmark dataset 上的性能结果是否允许直接比较，还是只比较同一数据集？

---

## 材料科学

可以问：

> 不同制备温度和工艺条件下的材料性能是否视为同一比较体系？

底层变量完全相同：

```text
Comparability Boundary
```

只是问题动态变化。

---

# 十二、Question Generator 的核心公式

建议写入 shared Grill-Me protocol：

```text
Question
=
Unresolved Decision Dimension
×
Domain Context
×
User Goal
×
Current Evidence
```

---

# 十三、每个问题必须满足的格式

推荐统一格式：

```markdown
### Q1｜<决策主题>

<一句话解释为什么这个决定会影响结果>

A. ...
B. ... **(Recommended)**
   - 推荐理由：...
C. ...
D. 自定义

> 快速回复：`1B`
```

---

# 十四、Recommended 选项生成规则

Recommended 不能随意产生。

Agent 应基于：

1. 用户当前目标；
2. 学科惯例；
3. 当前输入数据；
4. ScholarFlow 安全与证据原则；
5. 尽量保留用户控制权；

给出推荐。

---

## 推荐答案必须标记置信度

可选：

```text
Recommendation confidence:
HIGH
MEDIUM
LOW
```

例如：

```text
B. Include dissertations (Recommended)
   Reason: 当前目标是方法学检索，学位论文通常包含更完整的实验参数。
   Confidence: HIGH
```

如果推荐置信度 LOW：

Agent 应明确：

> 两种选择都合理。

---

# 十五、统一快速回复协议

ScholarFlow 应明确支持：

```text
按推荐
```

等价于：

```text
选择全部 Recommended 项
```

---

还应支持：

```text
1B 2C 3A
```

---

支持：

```text
除了 Q2 选 C，其他按推荐
```

---

支持自然语言：

```text
只搜英文，其他都按你推荐的来
```

Agent 应解析为参数，而不是要求用户严格按编号回复。

---

# 十六、Question Budget

为避免 Grill-Me 臃肿，建议设置：

```yaml
grill_me:
  target_questions_per_round: 3
  max_questions_per_round: 5
  max_rounds: 2
```

---

## Round 1

目标：

> 广度优先。

问最影响结果的 3–5 个问题。

---

## Round 2

只针对上一轮仍然模糊的重要 branch 继续追问。

---

## 第二轮后

如果只剩 Defaultable 变量：

```text
自动采用推荐默认值。
```

并记录：

```text
DEFAULTED
```

---

## Critical unresolved

如果第二轮后仍然存在真正无法执行的 Critical 变量：

允许继续问。

Question Budget 不应覆盖科学上不可忽略的核心不确定性。

---

# 十七、Decision Impact Score

建议每个候选问题先做影响评级。

```text
CRITICAL
HIGH
MEDIUM
LOW
```

然后优先问：

```text
CRITICAL
↓
HIGH
↓
MEDIUM
```

LOW 通常不进入 Grill-Me。

例如：

| 问题 | Impact |
|---|---|
| 核心纳入条件 | CRITICAL |
| 是否跨物种扩展 | HIGH |
| 是否纳入学位论文 | MEDIUM |
| 输出 Markdown / CSV | LOW |

---

# 十八、Skill 1：Literature Discovery 的 Grill-Me 方向

Discovery 的核心问题应该是：

> **What exactly should count as relevant evidence?**

建议预设以下 Decision Dimensions。

---

## D1. Research Purpose

目标：

> 为什么要搜？

可能动态生成：

```text
Exploratory Scan
Deep Literature Review
Systematic / Scoping Review
Method-focused Search
Evidence / Claim Search
```

建议级别：

```text
HIGH
```

---

## D2. Core Research Question

识别：

- 研究现象；
- 因果/关联问题；
- 方法问题；
- 比较问题；
- 理论问题。

级别：

```text
CRITICAL
```

---

## D3. Target Entity / Research Object

不要预设只能是：

```text
species
```

必须通用支持：

```text
population
disease
material
algorithm
technology
ecosystem
policy
compound
dataset
theory
```

级别：

```text
CRITICAL / HIGH
```

---

## D4. Inclusion Logic

这是 Discovery 最重要的 Grill 方向之一。

问题应该围绕：

> 哪些条件必须同时满足才算相关文献？

级别：

```text
CRITICAL
```

---

## D5. Exclusion Logic

问：

> 明确哪些研究不需要？

例如：

- 不纳入动物实验；
- 不纳入非目标物种；
- 不纳入纯理论研究；
- 不纳入未进行个体识别的遗传多样性研究。

级别：

```text
CRITICAL / HIGH
```

---

## D6. Scope Expansion

例如：

```text
目标种
↓
同属
↓
同科
↓
相似系统
↓
跨系统方法研究
```

医学可能变成：

```text
目标疾病
↓
同类疾病
↓
相同机制疾病
```

级别：

```text
HIGH
```

---

## D7. Geographic Scope

级别：

```text
HIGH / DEFAULTABLE
```

重点支持：

```text
Empirical Scope
```

和：

```text
Methodological Scope
```

分开。

例如：

```text
实证研究：中国
方法学论文：全球
```

---

## D8. Time Scope

级别：

```text
DEFAULTABLE
```

不要硬编码年份。

选项动态：

```text
All years + highlight recent 10 years
Last 10 years
Last 5 years
Custom
```

---

## D9. Document Types

动态选：

```text
Primary Articles
Reviews
Dissertations
Preprints
Conference Papers
Technical Reports
Government Reports
Standards
```

级别：

```text
MEDIUM
```

---

## D10. Language Scope

级别：

```text
DEFAULTABLE / MEDIUM
```

---

## D11. Seed Literature

问：

> 是否已有确定相关论文？

级别：

```text
HIGH
```

因为有 Seed 可以明显改善 citation chasing。

---

## D12. Database / Access Boundary

区分：

```text
AUTOMATED
USER_ASSISTED
UNAVAILABLE
```

级别：

```text
MEDIUM
```

---

## D13. Search Depth

Quick / Deep 不应该再承担“研究目的”。

它只代表执行强度。

例如：

```text
Quick
Deep
Systematic-like
```

级别：

```text
HIGH
```

---

## D14. Deliverable

级别：

```text
LOW / MEDIUM
```

不应该优先占用问题额度。

---

# 十九、Discovery 示例

用户：

> 帮我系统找一下 transformer 在病理图像分析里的研究。

Agent 不应该机械问固定 Q1–Q4。

应该先解析：

```text
Domain: Medical AI / Computational Pathology
Entity: pathological image analysis
Technology: transformer
Goal: literature discovery
```

然后动态 Grill：

```markdown
### Grill-Me · Literature Discovery · Round 1/2

我已经确定：
- 研究对象：病理图像分析
- 核心技术：Transformer
- 初步目标：系统性梳理相关研究

还剩 4 个会实质改变检索结果的决定：

### Q1｜技术边界
是否纳入 Vision Transformer 之外的多模态 Transformer / foundation model？

A. 仅纯视觉 Transformer
B. Transformer 家族全部纳入，包括多模态模型 **(Recommended)**
   - 推荐理由：当前领域的技术演化已经明显扩展到多模态与基础模型。
C. 仅纳入模型名称明确包含 Transformer 的研究
D. 自定义

### Q2｜任务范围
病理图像研究是否覆盖所有任务？

A. 仅分类
B. 分类 + 分割
C. 分类、分割、检测、预后等全部主要任务 **(Recommended)**
D. 自定义

### Q3｜研究类型
A. 仅同行评议原始研究
B. 原始研究 + 高质量综述 **(Recommended)**
C. 再加入预印本
D. 自定义

### Q4｜执行深度
A. Quick
B. Deep **(Recommended)**
   - 推荐理由：你的措辞是“系统找一下”，需要覆盖同义词、任务分支和引用扩展。

> 快速回复：`按推荐`
> 或：`1A 2C 3B 4B`
```

---

# 二十、Skill 2：Literature Evidence Extraction 的 Grill-Me 方向

Extraction 的核心问题：

> **What exactly are we allowed to take from each source?**

建议维度：

---

## E1. Extraction Purpose

例如：

```text
method extraction
result extraction
database building
reproducibility
claim audit
batch comparison
```

级别：

```text
HIGH
```

---

## E2. Evidence Boundary

核心问题：

```text
Strict paper-only
Paper + Supplement
Referenced methods tracing
External contextual explanation
```

级别：

```text
CRITICAL
```

---

## E3. Target Schema

例如：

```text
Methods Only
Results Only
Full Structured
Custom Schema
Dynamic Schema
```

级别：

```text
CRITICAL
```

---

## E4. Context Unit

根据学科动态：

### 分子实验

```text
Assay
PCR system
marker panel
```

### 医学

```text
Cohort
treatment arm
subgroup
```

### 机器学习

```text
dataset
model variant
experiment
train/test split
```

### 生态学

```text
site
season
species
population
```

级别：

```text
HIGH
```

---

## E5. Derived Evidence Permission

```text
Explicit only
Explicit + Derived
```

级别：

```text
HIGH
```

推荐通常：

```text
Explicit + Derived
```

但 Derived 必须独立标记。

---

## E6. Value Normalization

```text
raw only
raw + normalized
normalized only
```

推荐：

```text
raw + normalized
```

---

## E7. Supplement / Tables / Figures

Agent 检测到 Supplement 时再问。

不需要固定必问。

级别：

```text
CONDITIONAL
```

---

## E8. Interpretation Boundary

```text
Evidence only
Evidence + separated interpretation
```

级别：

```text
HIGH / DEFAULTABLE
```

默认：

```text
Evidence only
```

---

## E9. Batch Consistency

只有 Batch 模式问。

```text
Same schema across all papers?
```

级别：

```text
CRITICAL in Batch
```

---

# 二十一、Extraction 不需要问的内容

以下更适合做系统硬规则，而不是 Grill：

```text
冲突不得静默解决
OCR 风险必须标记
Not Reported ≠ Not Used
Discussion 不得当作实验结果
Referenced Method 不得自动回填
```

原因：

> 这些属于科研证据纪律，不是用户偏好。

---

# 二十二、Skill 3：Literature Synthesis 的 Grill-Me 方向

Synthesis 的核心问题：

> **What exactly are we allowed to compare and conclude across sources?**

建议维度：

---

## S1. Synthesis Purpose

例如：

```text
Controversy Scan
Deep Evidence Synthesis
School / Paradigm Mapping
Claim Audit
Methodological Review
```

级别：

```text
HIGH
```

---

## S2. Core Proposition

必须确定：

> 到底比较什么科学命题？

级别：

```text
CRITICAL
```

---

## S3. Evidence Corpus Boundary

例如：

```text
Primary studies = main evidence
Reviews = context only
All studies equal
Custom hierarchy
```

级别：

```text
CRITICAL
```

---

## S4. Unit of Comparison

例如：

```text
Scientific Conclusion
Mechanism
Method
Theory
Metric
Multi-layered
```

级别：

```text
CRITICAL / HIGH
```

---

## S5. Comparability Boundary

根据学科动态生成。

### 医学

```text
成人 vs 儿童
不同疾病亚型
不同 treatment arm
```

### 生态学

```text
不同物种
不同区域
不同尺度
```

### AI

```text
不同 dataset
不同 metric
不同 train/test protocol
```

级别：

```text
CRITICAL
```

---

## S6. Evidence Appraisal Strategy

例如：

```text
ScholarFlow multidimensional appraisal
User-defined framework
No strength grading
```

级别：

```text
HIGH
```

---

## S7. School Detection Strictness

推荐：

```text
Conservative
```

只在有明确证据时称：

```text
ESTABLISHED SCHOOL
```

否则：

```text
ANALYTICAL GROUPING
```

级别：

```text
HIGH
```

---

## S8. Temporal Evolution

只有用户需要学术史/方法演进时问。

级别：

```text
CONDITIONAL
```

---

## S9. Counterevidence Policy

建议默认：

```text
强制寻找反证、null results、contradictory evidence
```

这更适合做系统原则，不一定问用户。

---

## S10. Gap Handling

```text
Report only
Generate Search / Extraction Payload
Automatically call upstream skill
```

级别：

```text
HIGH
```

---

## S11. Narrative Output

```text
Structured maps only
Maps + narrative review
```

级别：

```text
MEDIUM
```

---

# 二十三、Synthesis 示例

用户：

> 帮我分析这些论文里关于 AI 是否能提高乳腺癌影像诊断准确率的争议。

动态 Grill：

```markdown
### Grill-Me · Evidence Synthesis · Round 1/2

我已确定：
- 核心命题：AI 是否提高乳腺癌影像诊断准确率
- 领域：Medical Imaging / Diagnostic AI
- 当前任务：跨研究证据综合

### Q1｜主证据范围

A. 所有文章同等作为证据
B. 原始诊断研究作为主证据；综述仅作背景和引文导航 **(Recommended)**
C. 仅纳入前瞻性研究
D. 自定义

### Q2｜可比性边界

A. 不同影像模态全部直接比较
B. 先按 mammography / MRI / ultrasound 分层，再比较总体结论 **(Recommended)**
C. 只分析 mammography
D. 自定义

### Q3｜性能比较指标

A. 只比较 accuracy
B. 以 AUC / sensitivity / specificity 为核心，并避免把不同指标直接混算 **(Recommended)**
C. 所有性能指标都综合
D. 自定义

### Q4｜证据强度

A. 不评级，只展示支持/反对
B. 使用 ScholarFlow 多维证据质量评估 **(Recommended)**
C. 用户自定义评价标准

### Q5｜发现证据缺口后

A. 只报告
B. 自动生成 Search / Extraction Gap Payload **(Recommended)**
C. 允许继续调用上游 Skill

> 快速回复：`按推荐`
```

---

# 二十四、Shared Grill Engine 的推荐文件结构

建议新增：

```text
shared/
└── grill_me/
    ├── core_protocol.md
    ├── state_model.md
    ├── question_generation.md
    ├── recommendation_policy.md
    ├── decision_priority.md
    ├── response_parser.md
    └── domain_lenses/
        ├── generic.md
        ├── biomedical.md
        ├── life_sciences.md
        ├── physical_sciences.md
        ├── computer_science.md
        └── social_sciences.md
```

---

三个 Skill 各自只保留：

```text
references/grill_dimensions.md
```

例如：

```text
literature-discovery-acquisition/
└── references/
    └── grill_dimensions.md
```

里面只描述：

```text
Research Purpose
Core Question
Target Entity
Inclusion
Exclusion
Scope Expansion
...
```

不再维护大量固定问句。

---

# 二十五、`core_protocol.md` 应该写什么

至少包含：

1. Grill-Me 是 Interactive Hard Gate；
2. 未解决 Critical 时禁止执行；
3. 每次 3–5 题；
4. 最多常规两轮；
5. 每题必须有 Recommended；
6. Recommended 必须给一句理由；
7. 用户说“按推荐”必须支持；
8. 问完 STOP；
9. 已解决变量不得重复询问；
10. 所有决定进入 Protocol Snapshot。

---

# 二十六、`recommendation_policy.md`

建议明确：

Recommended 答案必须基于：

```text
User Goal
Domain Norm
Evidence Discipline
Task Efficiency
Reproducibility
```

---

禁止：

```text
为了让 ScholarFlow 使用更多功能而推荐复杂模式
```

例如不能总是：

```text
Deep Search (Recommended)
```

必须根据用户目标决定。

---

## 推荐答案的优先原则

如果两个方案都科学合理：

优先推荐：

1. 更符合用户目标；
2. 更可复现；
3. 更少引入证据污染；
4. 更低过度推断风险；
5. 成本合理。

---

# 二十七、Protocol Snapshot 升级

Grill 完成后生成：

```yaml
stage0_status: CONFIRMED

research_goal:
  value: Deep Literature Review
  source: USER

core_question:
  value: ...
  source: INFERRED_HIGH_CONFIDENCE

scope:
  value: ...
  source: USER

publication_range:
  value: All years
  source: DEFAULTED
  reason: No explicit restriction; historical foundation may be relevant

document_types:
  value:
    - primary_article
    - review
    - dissertation
  source: USER
```

---

每个参数来源：

```text
USER
INFERRED
DEFAULTED
SYSTEM_RULE
```

这样以后可以审计：

> 到底是谁决定了这个边界？

---

# 二十八、Protocol Snapshot 后是否还要再确认一次？

建议：

## 如果用户刚刚明确回答 Grill-Me

无需再次要求：

> “请确认。”

直接输出快照，然后执行下一阶段。

否则会增加无意义的一轮交互。

---

## 如果大量参数是 Agent 推断/default

可以问：

```text
以上为我的执行基线。如无异议，回复“继续”即可。
```

但不应每次强制。

---

# 二十九、避免 Grill-Me 臃肿的规则

最关键的不是问题少，而是：

> **只问会改变科研结果的问题。**

不要问：

```text
你要 Markdown 还是表格？
```

除非输出格式本身是任务要求。

---

优先问：

```text
什么算相关？
什么不能纳入？
哪些研究可以比较？
证据允许用到哪里？
```

---

# 三十、一个完整的 ScholarFlow Grill-Me 逻辑

```text
1. Parse user task
2. Detect current Skill
3. Detect domain
4. Load Skill decision dimensions
5. Apply Domain Lens
6. Mark dimensions:
   - resolved
   - inferred
   - defaultable
   - unresolved
7. Score unresolved dimensions by impact
8. Generate top 3–5 questions
9. Generate Recommended answer + reason
10. STOP
11. Parse user response
12. Update state
13. If Critical remains:
       Round 2
14. Generate Protocol Snapshot
15. Set stage0_status = CONFIRMED
16. Execute
```

---

# 三十一、推荐的三个 Skill 核心 Grill-Me 哲学

## Discovery

```text
What exactly should count as relevant evidence?
```

---

## Extraction

```text
What exactly are we allowed to take from each source?
```

---

## Synthesis

```text
What exactly are we allowed to compare and conclude across sources?
```

这三句建议直接写进三个 Skill 的 `grill_dimensions.md` 顶部。

---

# 三十二、建议的开发顺序

## v0.2.1

先做：

```text
shared/grill_me/core_protocol.md
shared/grill_me/state_model.md
shared/grill_me/recommendation_policy.md
```

---

## v0.2.2

把三个：

```text
stage0_grill_me.md
```

逐步替换为：

```text
grill_dimensions.md
```

---

## v0.2.3

增加 Domain Lens：

```text
generic
biomedical
life_sciences
computer_science
physical_sciences
social_sciences
```

不要第一版就分几十个学科。

---

## v0.2.4

加入测试。

例如：

### Test A

用户已明确时间范围。

验证：

```text
Agent 不再问时间。
```

### Test B

用户说“全部按推荐”。

验证：

```text
Agent 正确解析所有 Recommended。
```

### Test C

有 Critical 未解决。

验证：

```text
Agent 不执行 Search。
```

### Test D

问完 Grill。

验证：

```text
Agent STOP 当前 turn。
```

### Test E

生态学 vs 医学输入。

验证：

```text
同一 Decision Dimension 生成不同领域问题。
```

---

# 三十三、最终建议

ScholarFlow Grill-Me 最理想的定位不是：

> “科研问卷”

而是：

> **Adaptive Research Decision Gate**

它的价值是：

```text
识别真正影响科研结果的未决变量
+
根据学科生成针对性问题
+
给出专业 Recommended 答案
+
让用户低成本作出决策
+
固化为可审计任务协议
```

因此最终结构应遵循：

```text
Fixed questions        ✗
Fixed decision axes    ✓

Domain-specific forms  ✗
Dynamic domain lens    ✓

Ask everything         ✗
Ask high-impact gaps   ✓

Open-ended only        ✗
Recommended choices    ✓

Unlimited grilling     ✗
Bounded adaptive grill ✓

Ask and continue       ✗
Ask → STOP → wait      ✓
```

---

# 三十四、最重要的实现原则

可以把下面这句话写进 shared Grill-Me 核心协议：

> **The purpose of Grill-Me is not to maximize the number of questions. It is to minimize consequential ambiguity before scientific work begins.**

中文：

> **Grill-Me 的目标不是尽可能多地提问，而是在科研工作开始前，以尽可能低的交互成本消除那些会实质改变结果的关键歧义。**

以及：

> **Every Grill-Me question should provide a recommended answer whenever a defensible default exists, so the user can accept the recommendation with minimal typing while retaining final control.**

中文：

> **只要存在合理、可辩护的默认方案，每一道 Grill-Me 问题都应提供 Recommended 答案，使用户可以低成本接受专业建议，同时保留最终决策权。**

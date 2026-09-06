# ScholarFlow 跨学科中立化与去偏整改方案

> 适用仓库：`Daylily-Huang/ScholarFlow`  
> 目标：将 ScholarFlow 从“以生态学/分子生态学为主要语境的通用科研工作流”，进一步重构为**真正面向所有学科的跨学科科研文献工作流**。  
> 核心原则：**Core 必须学科中立；领域知识只能通过按需加载的 Domain Lens / Domain Profile 注入。**

---

# 一、当前偏向性的总体判断

当前 ScholarFlow 的方法论框架本身是可以跨学科的：

```text
Discovery
→ Evidence Extraction
→ Synthesis
```

这三步本质上适用于：

- 生命科学
- 医学
- 计算机科学
- 材料科学
- 化学
- 物理学
- 社会科学
- 工程学
- 环境科学
- 经济学
- 教育学

真正的问题不在三段式架构，而在于：

> **当前 Core 文档、示例、模板、Domain Profile 和部分术语明显以生态学 / 分子生态 / PCR 实验作为默认世界观。**

这种偏向会产生一种隐性的：

```text
Domain Anchoring Bias
```

即：

> Agent 在面对其他学科任务时，可能仍然用生态学或实验生命科学的方式理解问题。

---

# 二、当前偏向性的具体表现

## 1. Synthesis 的 Domain Profile 目前主要是生态学

当前主要存在：

```text
ecology_profile.md
molecular_ecology_profile.md
```

这意味着 Synthesis 在执行“学科偏倚核查”时，默认领域模型非常偏生命科学。

风险：

- 医学任务可能缺少 cohort / intervention / comparator / diagnostic design；
- 机器学习任务可能缺少 dataset / benchmark / split / metric；
- 社会科学任务可能缺少 construct / identification strategy / sampling frame；
- 材料学任务可能缺少 synthesis condition / characterization / performance metric。

---

## 2. Extraction 中大量示例围绕 PCR

例如：

```text
PCR volume
annealing temperature
primer
BSA
ADO
PID
microsatellite
assay isolation
```

这些例子本身没有问题。

问题在于：

> 如果它们大量出现在 Core protocol、role contract 和模板中，就会让 Agent 将“实验体系隔离”理解得过于分子生物学化。

实际上不同学科的“上下文隔离单元”完全不同。

---

## 3. Synthesis 模板中存在明显生态学边界

例如：

```text
时间与季节窗口
空间尺度
多管 PCR
PID-sibs
生物学与生态学假定
```

这些更适合：

```text
domain-specific example
```

而不是通用模板字段。

---

## 4. README 示例基本集中在野生动物遗传和 PCR

如果 README 的三个主要场景都是：

- 野生动物
- 粪便 DNA
- PCR
- 微卫星

那么外部用户会自然把 ScholarFlow 理解成：

> “一个生态学科研 Skill，被包装成了通用框架。”

即使代码本身并不限制其他学科。

---

# 三、最核心的整改原则

建议确立一条项目级原则：

> **No domain-specific concept should appear in the Core execution logic unless it is presented only as an example.**

中文：

> **任何学科特有概念都不应成为 Core 执行逻辑的一部分，除非它只是示例。**

---

# 四、Core 中应该只保留“通用科研概念”

建议 ScholarFlow Core 统一使用以下抽象术语。

## 1. Research Question

```text
研究问题
```

---

## 2. Target Entity / System

统一表示：

```text
研究对象 / 系统
```

可对应：

- species
- patient population
- material
- model
- algorithm
- dataset
- policy
- institution
- social group
- molecule

---

## 3. Method / Approach

表示：

```text
研究方法 / 技术路线
```

可对应：

- PCR
- RCT
- Transformer
- finite element
- spectroscopy
- econometric model
- survey
- field experiment

---

## 4. Outcome / Claim

表示：

```text
结果变量 / 科学主张
```

---

## 5. Context

统一表示：

```text
研究上下文
```

而不是默认：

```text
assay
```

Context 可以对应：

- assay
- cohort
- site
- dataset
- model variant
- experimental condition
- policy regime
- subgroup

---

## 6. Evidence Source

统一：

```text
正文
表格
补充材料
附录
外部引用
```

---

## 7. Comparability Boundary

统一表示：

> 哪些研究结果可以放在一起比较？

---

## 8. Uncertainty

统一表示：

```text
UNKNOWN
AMBIGUOUS
NOT_REPORTED
CONTRADICTORY
LOW_CONFIDENCE
```

---

# 五、建议新增 Shared Domain Architecture

建议从：

```text
Skill-specific domain profiles
```

改为：

```text
shared/
└── domain_lenses/
```

推荐结构：

```text
shared/
└── domain_lenses/
    ├── generic.md
    ├── biomedical.md
    ├── life_sciences.md
    ├── ecology_environment.md
    ├── computer_science.md
    ├── physical_sciences.md
    ├── chemistry_materials.md
    ├── engineering.md
    └── social_sciences.md
```

---

# 六、Domain Lens 的职责

Domain Lens 不应该是一整套独立 Skill。

它只负责告诉 Agent：

> 在当前学科，哪些变量值得重点关注。

例如：

```yaml
domain: computer_science

high_risk_dimensions:
  - task_definition
  - dataset
  - train_test_split
  - model_family
  - evaluation_metric
  - baseline_selection
  - reproducibility

common_context_units:
  - dataset
  - model_variant
  - experiment
  - benchmark
```

---

# 七、不要把 Domain Lens 写成固定问题库

错误：

```text
Q1 是否有 PCR？
Q2 是否有退火温度？
Q3 是否有引物？
```

正确：

```text
high_risk_dimension:
  experimental_condition
```

然后 Agent 根据学科动态问。

例如：

## 分子生物学

```text
不同 PCR 体系是否需要分别提取？
```

---

## 机器学习

```text
不同 dataset / model variant 是否需要分别提取？
```

---

## 医学

```text
不同 patient cohort 是否需要分别提取？
```

---

## 材料学

```text
不同制备条件或测试温度是否视为独立实验上下文？
```

---

# 八、建议的学科映射表

| 通用维度 | 生命科学 | 医学 | 计算机 | 材料/化学 | 社会科学 |
|---|---|---|---|---|---|
| Target Entity | species / gene | patient / disease | model / task | material / compound | population / institution |
| Context | assay / site | cohort / arm | dataset / split | condition / batch | subgroup / setting |
| Method | PCR / sequencing | trial / diagnostic test | model architecture | synthesis / spectroscopy | survey / regression |
| Outcome | abundance / expression | clinical outcome | accuracy / AUC | yield / strength | effect / association |
| Boundary | taxon / space | population / disease | dataset / benchmark | condition / composition | population / institution |
| Bias | detection bias | selection bias | benchmark leakage | batch effect | confounding |

---

# 九、Skill 1：Literature Discovery 去偏方案

Discovery 的核心应该是：

> **What exactly should count as relevant evidence?**

而不是：

> 当前是哪个生态学对象？

---

## 应保留的通用 Decision Dimensions

```text
Research Purpose
Core Research Question
Target Entity
Concept Scope
Inclusion Logic
Exclusion Logic
Scope Expansion
Geographic / Context Scope
Time Scope
Document Type
Language
Seed Literature
Search Depth
Database Access
Deliverable
```

---

## 需要移出 Core 的生态学特有概念

例如：

```text
物种
分类群
野生动物
非损伤取样
鹿科
```

它们可以作为：

```text
examples/life_science/
```

而不是通用字段名。

---

## 建议术语替换

把：

```text
Target Taxon
```

改成：

```text
Target Entity / System
```

---

把：

```text
Taxonomic Expansion
```

改成：

```text
Scope Expansion
```

然后 Domain Lens 再解释：

### 生态学

```text
species → genus → family
```

### 医学

```text
target disease → disease family → shared mechanism
```

### 机器学习

```text
specific architecture → model family → broader method class
```

---

# 十、Skill 2：Evidence Extraction 去偏方案

Extraction 的核心应该是：

> **What exactly are we allowed to take from each source?**

---

## Core 中保留

```text
Extraction Purpose
Evidence Boundary
Target Schema
Context Unit
Granularity
Derived Evidence
Normalization
Conflict Handling
Missingness
Interpretation Boundary
Batch Consistency
High-risk Fields
```

---

## 不应把 Assay 作为唯一上下文概念

建议将：

```text
Assay Context Isolation
```

改为：

```text
Context Isolation
```

然后根据 Domain Lens 映射。

---

## Context Isolation 示例

### 分子实验

```text
Assay
PCR panel
marker set
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
train/test split
```

### 材料学

```text
synthesis condition
batch
temperature
composition
```

### 社会科学

```text
population
wave
institution
subgroup
```

---

# 十一、Extraction Role 改名建议

当前类似：

```text
context_modeler
```

这个名称本身已经比较通用。

但内容需要去掉：

> PCR 是默认例子。

建议 Role 结构：

```text
Context Modeler
```

负责：

```text
Identify independent experimental / observational contexts.
```

而不是：

```text
Identify different PCR assays.
```

---

# 十二、Extraction 示例迁移

建议：

```text
examples/
├── life_science/
├── biomedical/
├── computer_science/
├── materials_science/
└── social_science/
```

每类至少一个案例。

---

# 十三、Skill 3：Literature Synthesis 去偏方案

Synthesis 是当前最需要去偏的模块。

核心应该是：

> **What exactly are we allowed to compare and conclude across sources?**

---

## Core 中保留

```text
Core Proposition
Evidence Corpus
Unit of Comparison
Comparability Boundary
Methodological Differences
Evidence Appraisal
Counterevidence
Temporal Evolution
School / Paradigm Detection
Consensus Boundary
Knowledge Gaps
```

---

## 删除 Core 中默认生态学边界

不要直接写：

```text
spatial scale
season
taxon
PCR
ADO
PID
```

改成：

```text
contextual boundary
population/system boundary
methodological boundary
measurement boundary
temporal boundary
```

---

# 十四、Synthesis 的通用 Boundary Model

推荐统一使用：

```text
Population / Entity Boundary
Context Boundary
Methodological Boundary
Measurement Boundary
Temporal Boundary
Geographic Boundary
Data Boundary
Theory Boundary
```

不同学科按需激活。

---

# 十五、不同学科的 Comparability 检查

## 医学

```text
population
intervention
outcome
study design
diagnostic modality
```

---

## 生态学

```text
species
site
season
scale
detection process
```

---

## 计算机

```text
dataset
metric
benchmark protocol
model size
train/test split
```

---

## 材料学

```text
composition
temperature
processing condition
testing method
```

---

## 社会科学

```text
population
measurement construct
institutional context
identification strategy
time period
```

---

# 十六、School / Paradigm 模块需要进一步去偏

“学派”在不同学科含义差异很大。

例如：

### 社会科学

可能真的存在：

```text
theoretical schools
```

---

### 机器学习

很多时候更合理的是：

```text
method families
```

---

### 材料科学

可能是：

```text
processing paradigms
```

---

因此建议统一上层术语：

```text
Intellectual / Methodological Grouping
```

再分类：

```text
ESTABLISHED SCHOOL
THEORETICAL FRAMEWORK
METHOD FAMILY
ANALYTICAL GROUPING
TECHNOLOGICAL GENERATION
```

不要默认都叫：

```text
school
```

---

# 十七、README 的去偏修改

README 对外的第一印象非常重要。

当前应避免：

> 三个主要例子全部来自野生动物与 PCR。

建议首页至少展示 4 个不同学科案例。

---

## 示例 A：生命科学

```text
非损伤遗传取样与个体识别
```

---

## 示例 B：医学

```text
AI 辅助乳腺癌影像诊断
```

---

## 示例 C：计算机科学

```text
Long-context Transformer 的压缩与评测
```

---

## 示例 D：材料科学

```text
钙钛矿太阳能电池稳定性影响因素
```

---

可以再加：

## 示例 E：社会科学

```text
远程办公对生产率的影响
```

---

# 十八、README 的定位文案建议

建议明确写：

```text
ScholarFlow is domain-agnostic at its core.
Domain-specific reasoning is injected through optional, dynamically loaded Domain Lenses.
```

中文：

> ScholarFlow 的核心协议保持学科中立，领域特定的术语、风险点与比较逻辑通过按需加载的 Domain Lens 动态注入。

---

# 十九、Template 去偏

当前模板应避免：

```text
BIOLOGICAL_ASSUMPTIONS
PCR
PID-sibs
SEASON
```

改成：

```text
SYSTEM_ASSUMPTIONS
METHODOLOGICAL_CONSTRAINTS
TEMPORAL_BOUNDARY
CONTEXT_BOUNDARY
MEASUREMENT_BOUNDARY
```

---

# 二十、Template 示例不要写死

建议模板主体：

```markdown
## Boundary Conditions

- Entity / Population Boundary:
- Context Boundary:
- Temporal Boundary:
- Methodological Boundary:
- Measurement Boundary:
- Data Boundary:
- Theory Boundary:
```

---

生态学案例可以放：

```text
examples/ecology/
```

---

# 二十一、Role 文件去偏

建议检查所有 Role 文件。

如果出现大量：

```text
PCR
microsatellite
species
site
season
```

应该判断它到底是：

### A. 通用原则中的例子

保留，但加多学科并列例子。

### B. 执行规则本身

必须抽象。

---

# 二十二、多学科示例原则

Core 文件中如果需要举例，建议：

> 每出现一个生命科学例子，最好同时给一个非生命科学例子。

例如：

```text
Context Isolation:
- biology: different PCR assays
- machine learning: different datasets/model variants
- medicine: different cohorts
- materials science: different processing conditions
```

这样可以显著减少锚定。

---

# 二十三、建议的目录结构

推荐最终：

```text
ScholarFlow/
│
├── shared/
│   ├── core/
│   │   ├── evidence_principles.md
│   │   ├── uncertainty_model.md
│   │   └── cross_skill_contract.md
│   │
│   ├── grill_me/
│   │   ├── core_protocol.md
│   │   ├── state_model.md
│   │   └── recommendation_policy.md
│   │
│   └── domain_lenses/
│       ├── generic.md
│       ├── biomedical.md
│       ├── life_sciences.md
│       ├── ecology_environment.md
│       ├── computer_science.md
│       ├── chemistry_materials.md
│       ├── physical_sciences.md
│       ├── engineering.md
│       └── social_sciences.md
│
├── skills/
│   ├── literature-discovery-acquisition/
│   ├── literature-evidence-extraction/
│   └── literature-synthesis/
│
└── examples/
    ├── life_sciences/
    ├── biomedical/
    ├── computer_science/
    ├── materials_science/
    └── social_sciences/
```

---

# 二十四、Domain Lens 第一版不要做太多

不要一开始创建几十个：

```text
ecology
genetics
molecular ecology
medicine
oncology
radiology
AI
NLP
CV
materials
chemistry
physics
...
```

这会迅速臃肿。

---

推荐第一版只做：

```text
generic
biomedical
life_sciences
computer_science
chemistry_materials
physical_sciences
engineering
social_sciences
```

---

以后根据真实用户需求再扩展。

---

# 二十五、Domain Detection

Agent 首先判断：

```yaml
primary_domain:
  value: computer_science
  confidence: 0.82

secondary_domains:
  - biomedical
```

例如：

```text
medical imaging AI
```

就是跨学科：

```text
biomedical
+
computer_science
```

---

此时不要二选一。

应该组合 Lens。

---

# 二十六、Multi-Domain Lens

建议支持：

```text
primary lens
+
secondary lens
```

例如：

```text
AI drug discovery
```

激活：

```text
computer_science
chemistry_materials
biomedical
```

但：

> 只提取各 Lens 中与当前任务相关的高风险维度。

避免全文全部加载。

---

# 二十七、学科 Lens 的优先级

建议：

```text
Generic Core
        ↓
Primary Domain Lens
        ↓
Secondary Domain Lens
        ↓
Task-specific adaptation
```

Generic Core 永远优先。

Domain Lens 不允许覆盖 Core evidence rules。

---

# 二十八、不能让 Domain Lens 改变的规则

例如以下必须全学科一致：

```text
No unsupported completion
Not Reported != Not Used
Inference must be labeled
Contradictions must be preserved
Evidence provenance must be traceable
Uncertainty must be explicit
```

这些属于：

```text
epistemic core
```

不能被任何学科覆盖。

---

# 二十九、需要区分“学科方法规范”与“证据纪律”

## Evidence Discipline

通用：

```text
quote binding
source traceability
uncertainty
NR
conflict preservation
```

---

## Domain Methodology

动态：

```text
PICO
PRISMA
benchmark leakage
pseudoreplication
batch effect
PCR dropout
```

---

这个分离非常关键。

---

# 三十、Discovery 去偏测试案例

至少测试以下 5 类任务：

## Case 1 — Ecology

```text
Search non-invasive genetic individual identification in cervids
```

---

## Case 2 — Medicine

```text
Search diagnostic accuracy of AI in breast cancer imaging
```

---

## Case 3 — Computer Science

```text
Search long-context compression methods for transformers
```

---

## Case 4 — Materials Science

```text
Search degradation mechanisms of perovskite solar cells
```

---

## Case 5 — Social Science

```text
Search causal evidence on remote work and productivity
```

---

验证：

> Agent 生成的 Concept Matrix、Grill-Me 和 Inclusion Logic 是否学科合适。

---

# 三十一、Extraction 去偏测试案例

准备五篇不同学科论文。

验证 Context Isolation 是否正确映射：

| 学科 | 应识别的 Context Unit |
|---|---|
| Molecular Biology | assay |
| Medicine | cohort / arm |
| Computer Science | dataset / model |
| Materials | processing condition |
| Social Science | sample / wave |

如果所有任务最终都出现：

```text
Assay-01
```

说明仍然偏生命科学。

---

# 三十二、Synthesis 去偏测试案例

测试：

## 医学

是否检查：

```text
population
intervention
study design
```

---

## AI

是否检查：

```text
dataset
metric
benchmark
```

---

## 材料

是否检查：

```text
processing condition
measurement method
```

---

## 社科

是否检查：

```text
confounding
identification strategy
population
```

---

## 生态

是否检查：

```text
species
scale
site
season
```

---

# 三十三、一个重要 Benchmark：Domain Neutrality Test

建议以后增加：

```text
benchmarks/domain_neutrality/
```

---

每个学科准备 10 个任务。

总共例如：

```text
8 domains × 10 tasks = 80 tasks
```

---

评估：

```text
Domain-appropriate question rate
Irrelevant-domain terminology rate
Correct context-unit identification
Correct evidence-risk identification
```

---

最重要指标：

```text
Irrelevant Domain Leakage Rate
```

例如：

> 计算机任务中错误出现 PCR / species / cohort 等无关概念。

目标：

```text
< 2%
```

---

# 三十四、建议新增 lint 思路

可以做一个简单仓库级检查：

```text
core files
```

中是否大量出现领域特定词。

例如：

```text
PCR
microsatellite
species
PID
ADO
```

如果出现，应人工判断：

```text
是规则？
还是例子？
```

---

# 三十五、建议标记示例

Core 中领域例子统一使用：

```text
Example:
```

或者：

```text
Domain example:
```

避免模型把例子当成规则。

---

# 三十六、建议修改顺序

## Phase 1 — Core Neutralization

优先修改：

```text
SKILL.md
shared rules
templates
role contracts
```

把领域概念抽象。

---

## Phase 2 — Domain Lens Extraction

把原本 Core 中的：

```text
ecology
molecular ecology
PCR
microsatellite
```

迁移到：

```text
domain_lenses/
examples/
```

---

## Phase 3 — Multi-domain Examples

补：

```text
medicine
computer science
materials science
social science
```

案例。

---

## Phase 4 — Domain Neutrality Tests

增加：

```text
tests/
benchmarks/
```

---

# 三十七、推荐版本路线

## v0.2.x

```text
Core terminology neutralization
```

---

## v0.3.x

```text
Shared Domain Lens architecture
```

---

## v0.4.x

```text
Multi-domain examples + tests
```

---

## v0.5.x

```text
Domain Neutrality Benchmark
```

---

## v1.0

条件：

- Core 不依赖任何单一学科；
- 至少覆盖 5–8 个领域的公开案例；
- Grill-Me 可动态领域化；
- Extraction 可以识别不同 Context Unit；
- Synthesis 可以采用不同 Comparability 逻辑；
- Domain Leakage benchmark 达标。

---

# 三十八、建议的项目原则

建议加入 README / CONTRIBUTING。

## Principle 1

```text
Domain-neutral core, domain-aware execution.
```

---

## Principle 2

```text
Examples must not become rules.
```

---

## Principle 3

```text
Domain knowledge may specialize the workflow,
but may not override evidence integrity.
```

---

## Principle 4

```text
No single discipline defines the default ontology of ScholarFlow.
```

---

# 三十九、最终目标架构

```text
                       ScholarFlow Core
                             │
              ┌──────────────┼──────────────┐
              │              │              │
          Discovery      Extraction      Synthesis
              │              │              │
              └──────────────┼──────────────┘
                             │
                      Generic Research Model
                             │
                  Dynamic Domain Detection
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
     Biomedical        Computer Science    Materials
          │                  │                  │
     Domain Lens         Domain Lens         Domain Lens
          │                  │                  │
          └──────────────────┼──────────────────┘
                             ↓
                     Task-specific Execution
```

---

# 四十、最终结论

当前 ScholarFlow 的问题不是：

> “只能做生态学。”

而是：

> **核心框架虽然通用，但默认语言、示例和已有 Domain Profile 会让 Agent 形成生命科学锚定。**

因此最合理的整改方式不是删除生态学内容，而是：

```text
Core 去领域化
+
生态内容迁移到 Domain Lens
+
增加多学科 Lens
+
增加多学科 examples
+
建立 Domain Neutrality Tests
```

最终目标应该是：

> **ScholarFlow does not think like an ecologist, a clinician, or a computer scientist by default.  
> It thinks like a research evidence system first, then adopts the appropriate disciplinary lens.**

中文：

> **ScholarFlow 默认不以生态学家、临床医生或计算机科学家的方式思考。它首先作为一个科研证据系统工作，再根据任务动态加载对应学科视角。**

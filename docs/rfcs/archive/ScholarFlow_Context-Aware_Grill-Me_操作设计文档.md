# ScholarFlow Context-Aware Grill-Me 操作设计文档

> 适用仓库：`Daylily-Huang/ScholarFlow`  
> 目标：为 ScholarFlow 的三个 Skill 引入统一的 **Context Resolution Layer**，使 Grill-Me 能自动利用当前对话、当前附件、上游 Skill 输出和项目资料，减少重复提问，并只针对真正影响科研结果的未决变量进行动态追问。

---

# 一、为什么需要 Context-Aware Grill-Me

传统 Grill-Me 容易出现：

- 用户已经说明过时间范围，Agent 又问一次；
- 项目文件里已经写明研究对象，Agent 仍重复询问；
- 上游 Search 已经确定纳排标准，下游 Synthesis 又重新问；
- Agent 不读取已有 Evidence Table，却重新让用户解释文献内容。

更合理的流程应为：

```text
用户请求
↓
Context Resolution
↓
识别已知信息
↓
识别真正未决变量
↓
只 Grill 高影响未知项
↓
用户选择 Recommended / 自定义
↓
Protocol Snapshot
↓
执行
```

核心原则：

> **能从可靠上下文中确定的内容，不再问用户；只有真正需要用户决策的变量才进入 Grill-Me。**

---

# 二、整体架构

建议在三个 Skill 之前增加统一层：

```text
                 User Request
                      ↓
            Context Resolution Layer
                      ↓
         Existing Decision State Builder
                      ↓
          Unresolved Variable Detector
                      ↓
           Adaptive Grill-Me Engine
                      ↓
             Protocol Snapshot
                      ↓
        Discovery / Extraction / Synthesis
```

---

# 三、Context Resolution Layer 的职责

Context Resolution Layer 不负责科学分析，只负责：

1. 找到已有上下文；
2. 提取和当前任务相关的信息；
3. 判断这些信息是否足以解决某个决策变量；
4. 给每个变量标记来源与可信状态。

---

# 四、可读取的上下文来源

建议分为五层。

## Layer 1：Current User Message

当前这一轮用户明确说的话，优先级最高。

例如：

```text
“帮我找 2018 年以后英文的医学影像 AI 论文。”
```

可以直接解析：

```yaml
time_scope:
  value: 2018-present
  source: current_user
  status: RESOLVED

language:
  value: English
  source: current_user
  status: RESOLVED
```

## Layer 2：Current Conversation Context

读取当前对话中已经确认过的内容。

例如前面用户已经说：

```text
“这次不需要硕博士论文。”
```

后面就不要再问：

> 是否纳入学位论文？

## Layer 3：Current Attachments / Current Task Files

包括：

- 当前上传的 PDF；
- CSV；
- Excel；
- Word；
- 当前明确指定的文件。

这些文件属于高相关上下文。

## Layer 4：Upstream ScholarFlow Outputs

三个 Skill 应形成上下文链：

```text
Discovery
↓
LiteratureRecord / Search Protocol
↓
Extraction
↓
EvidenceRecord
↓
Synthesis
```

下游 Skill 应优先读取上游结构化输出。

## Layer 5：Project Knowledge / Historical Files

只有在以下情况才检索：

> 当前存在一个未解决变量，并且项目资料中很可能已有答案。

例如：

```text
研究区域？
研究对象？
既有纳排标准？
已有 seed papers？
```

不要默认把整个项目全部加载。

---

# 五、上下文优先级

推荐固定为：

```text
当前用户明确指令
    >
当前对话已确认内容
    >
当前任务文件
    >
上游 ScholarFlow 结构化输出
    >
项目历史文件
    >
Agent 推断
    >
默认值
```

---

# 六、冲突解决原则

如果出现冲突：

项目文件：

```text
Target = Cervidae
```

当前用户：

```text
这次扩大到所有 mammals
```

必须采用：

```text
Mammals
```

并记录：

```yaml
target_scope:
  value: Mammals
  source: current_user
  overrides:
    previous_value: Cervidae
    source: project_file
```

如果两个来源优先级相同且冲突：

```text
UNRESOLVED_CONFLICT
```

进入 Grill-Me。

---

# 七、每个变量的标准状态

建议统一使用：

```text
RESOLVED_FROM_USER
RESOLVED_FROM_CONTEXT
INFERRED_HIGH_CONFIDENCE
DEFAULTABLE
UNRESOLVED
UNRESOLVED_CONFLICT
```

---

# 八、推荐的数据结构

```yaml
decision_state:

  research_goal:
    value: Deep Literature Review
    status: RESOLVED_FROM_USER
    source:
      type: conversation
      reference: current_turn

  target_entity:
    value: Breast cancer imaging
    status: RESOLVED_FROM_CONTEXT
    source:
      type: project_file
      reference: research_protocol.md

  language:
    value: English
    status: DEFAULTABLE
    source:
      type: system_default

  comparability_boundary:
    value: null
    status: UNRESOLVED
```

---

# 九、Context Resolution 核心流程

```text
Step 1
Parse current user request

Step 2
Load current conversation decisions

Step 3
Inspect current task files

Step 4
Read upstream ScholarFlow outputs

Step 5
Identify unresolved high-impact variables

Step 6
Search project knowledge only for those variables

Step 7
Update decision state

Step 8
Send remaining unresolved variables to Grill-Me
```

---

# 十、不要全量读取项目文件

错误方式：

```text
每次启动 Skill
↓
读取整个 Project
↓
把所有历史资料塞进上下文
```

风险：

- 上下文膨胀；
- 成本增加；
- 旧信息污染新任务；
- Agent 被历史方向锚定；
- 更容易把不相关项目事实误认为当前任务条件。

正确方式：

```text
先找 unresolved variable
↓
再针对变量检索项目资料
```

---

# 十一、Context Retrieval 应 Query-Driven

例如当前缺少：

```text
geographic_scope
```

项目检索应围绕：

```text
study area
geographic scope
study region
site
location
```

而不是读取所有项目文件。

---

# 十二、Context-Aware Grill 核心公式

```text
Grill Question
=
Unresolved Decision Dimension
×
Domain Context
×
User Goal
×
Available Evidence
×
Existing Project Context
```

---

# 十三、什么情况下不要 Grill

变量如果已经：

```text
RESOLVED_FROM_USER
```

禁止再问。

如果：

```text
RESOLVED_FROM_CONTEXT
```

且来源可靠、无冲突：

通常不问。

如果：

```text
INFERRED_HIGH_CONFIDENCE
```

建议在 Protocol Snapshot 中展示推断，而不是立即提问。

如果：

```text
DEFAULTABLE
```

直接给默认值。

只有：

```text
UNRESOLVED
UNRESOLVED_CONFLICT
```

且变量属于：

```text
CRITICAL / HIGH IMPACT
```

才进入 Grill。

---

# 十四、Context Resolution 不等于自动决定一切

必须区分：

## Factual Context

可以从资料中读取。

例如：

```text
研究对象是成年患者
```

## Preference / Decision

不能因为历史文件有旧设置，就默认用户现在还要一样。

例如：

```text
这次是否排除 preprint？
```

这种属于当前任务决策。

如果当前上下文没有明确答案：

应该 Grill。

---

# 十五、信息类型分类

建议每条 Context Fact 标记：

```text
FACT
USER_PREFERENCE
TASK_DECISION
INFERENCE
DEFAULT
```

例如：

```yaml
study_region:
  value: China
  type: FACT
```

历史 Preference 的可信度应低于当前事实。

---

# 十六、三个 Skill 的 Context 读取重点不同

## Skill 1：Literature Discovery

Discovery 应优先寻找：

```text
Research Purpose
Core Question
Target Entity
Inclusion Criteria
Exclusion Criteria
Scope Boundary
Geography
Time
Language
Seed Papers
Known Terminology
```

优先来源：

```text
Current request
↓
Conversation
↓
Research protocol / proposal
↓
Existing literature list
↓
Project files
```

### 示例

用户：

```text
帮我继续找这个课题相关论文。
```

Agent 应先从 Context 找：

```text
“这个课题”是什么？
```

如果项目里已经有：

```text
research_question
target_entity
time_scope
```

则不要再问。

只问仍未确定的高影响变量。

---

# 十七、Discovery 应重点读取 Seed Papers

如果项目中已有：

```text
known_relevant_papers
```

自动识别为：

```text
seed literature
```

直接用于：

```text
backward citation chasing
forward citation chasing
query expansion
```

而不需要再次问：

> 你有没有已知核心论文？

---

# 十八、Skill 2：Evidence Extraction

Extraction 应优先读取：

```text
Target Schema
Previous Extraction Rules
Evidence Boundary
Context Unit
Normalization Rules
Derived Evidence Policy
Interpretation Boundary
```

优先来源：

```text
Current request
↓
Current PDF / attachment
↓
Previous extraction snapshot
↓
Upstream LiteratureRecord
↓
Project extraction schema
```

### 示例

用户：

```text
继续按之前的标准提取这篇。
```

正确行为：

```text
读取之前的 Extraction Protocol Snapshot
↓
复用字段 Schema
↓
确认当前论文是否存在特殊 Context
↓
只在真正新增的不确定性上 Grill
```

---

# 十九、Extraction 必须检测“当前论文特异变量”

即使复用历史 Schema，也不能盲目套用。

例如：

前一篇：

```text
single dataset
```

当前论文：

```text
3 datasets
```

则 Context Isolation 出现新的 unresolved variable。

这时需要动态 Grill：

> 是否将三个 dataset 分别提取？

---

# 二十、Skill 3：Literature Synthesis

Synthesis 最依赖 Context。

优先读取：

```text
Evidence Tables
Claim Records
Search Protocol
Inclusion / Exclusion
Core Proposition
Previous Gap Records
```

理想输入优先级：

```text
EvidenceRecord
↓
Structured Extraction Table
↓
Full Text
↓
Abstract
```

---

# 二十一、Synthesis 不应重新询问已确认 Corpus

如果上游 Discovery 已固定：

```text
included studies = 25
```

Extraction 已处理：

```text
20
```

Synthesis 应识别：

```text
5 EXTRACTION GAP
```

而不是重新问：

> 你希望纳入哪些论文？

---

# 二十二、Context Gap 应转化为上游任务

例如：

```text
Synthesis
发现 4 篇关键研究缺少 effect size
```

应该生成：

```text
EXTRACTION_GAP
```

而不是直接 Grill 用户。

只有当需要用户做任务策略选择时，才问：

```text
是否暂停综合并先补抽？
```

---

# 二十三、Context Resolver 与 Grill-Me 的分工

## Context Resolver

回答：

> 我们已经知道什么？

## Grill-Me

回答：

> 哪些关键事情必须由用户决定？

不要让 Grill-Me 去做 Context Resolver 的工作。

---

# 二十四、Context Snapshot

建议每次 Stage 0 生成内部 Snapshot：

```yaml
context_snapshot:

  sources_checked:
    - current_user_message
    - conversation
    - current_attachments
    - upstream_outputs
    - project_search

  resolved:
    research_goal: ...
    target_entity: ...
    time_scope: ...

  unresolved:
    - inclusion_boundary
    - comparability_boundary

  conflicts:
    - none
```

---

# 二十五、用户可见 Snapshot 不需要太长

用户只需要看到：

```markdown
已从当前上下文确认：
- 研究对象：...
- 时间范围：...
- 语言：...

还需你决定：
- 纳入边界
- 是否允许跨系统扩展
```

然后进入 Grill。

---

# 二十六、Context Provenance

所有上下文值必须能追踪来源。

例如：

```yaml
target_entity:
  value: glioblastoma
  provenance:
    source_type: project_file
    source_name: protocol_v2.md
```

---

# 二十七、过期信息与 Volatility

项目资料可能过期。

建议支持：

```text
STATIC
SEMI_STATIC
VOLATILE
```

## STATIC

例如：

```text
研究对象定义
理论框架
```

## SEMI_STATIC

例如：

```text
纳排标准
方法路线
```

## VOLATILE

例如：

```text
当前样本数
当前候选论文数
已完成提取数量
```

VOLATILE 信息冲突时优先最新 timestamp；如果无法判断，则：

```text
UNRESOLVED_CONFLICT
```

---

# 二十八、项目上下文不能强行覆盖当前任务

例如项目主要研究：

```text
ecology
```

但用户当前问：

```text
帮我检索 Transformer long-context benchmark
```

Context Resolver 应识别：

```text
当前任务与项目历史领域不一致
```

此时：

```text
不要加载 ecology Domain Lens
```

---

# 二十九、相关性门槛

项目文件只有与当前任务：

```text
HIGH RELEVANCE
```

时才自动用于决策。

建议：

```text
HIGH
MEDIUM
LOW
```

只自动应用：

```text
HIGH
```

MEDIUM 可作为提示。

LOW 忽略。

---

# 三十、推荐的 Context Resolver 输出

```yaml
context_resolution:

  current_task:
    domain: computer_science
    skill: literature-discovery-acquisition

  resolved_variables:
    research_goal:
      value: Deep Literature Review
      source: conversation

    target_entity:
      value: Long-context Transformer
      source: current_user

  unresolved_variables:
    - benchmark_scope
    - model_family_boundary

  ignored_context:
    - file: ecology_project_notes.md
      reason: low relevance
```

---

# 三十一、与 Domain Lens 的关系

建议流程：

```text
Current Task
↓
Context Resolution
↓
Domain Detection
↓
Domain Lens
↓
Unresolved Variable Detection
↓
Grill-Me
```

不要先根据历史项目加载 Domain Lens。

---

# 三十二、Context-Aware Recommended Answer

Recommended 也应该利用上下文。

例如项目中已有：

```text
上次 Search 使用中英文双语
```

当前任务是：

```text
继续补检
```

那么 Grill：

```text
A. English only

B. Chinese + English (Recommended)
   原因：与现有检索协议保持一致，避免新增结果产生语种偏差。
```

如果 Recommendation 只是历史惯例，必须说明：

```text
Recommended because of existing project protocol
```

不能伪装成学科标准。

---

# 三十三、用户覆盖权与 Reset

任何时候用户都可以说：

```text
这次不要沿用之前的设置
重新开始
不要读取项目历史
只看当前对话
```

此时可以支持：

```text
CONTEXT_SCOPE = CURRENT_ONLY
```

建议定义三种 Context Scope：

```text
CURRENT_ONLY
CURRENT_PLUS_UPSTREAM
PROJECT_AWARE
```

默认建议：

```text
PROJECT_AWARE
```

但项目检索必须 query-driven。

---

# 三十四、缺少项目访问能力时怎么办

ScholarFlow 必须 graceful degradation。

如果运行环境没有：

```text
Project Files
Memory
Connector
```

不要报错。

直接记录：

```text
context_capability:
  project_search: unavailable
```

然后 Grill-Me 多问必要的问题。

---

# 三十五、不能假设所有 Agent 平台都有相同 Context 能力

开源项目可能运行于：

```text
Claude Code
Codex
ChatGPT
Cursor
local agent
```

因此 Context Resolver 应抽象成能力接口。

推荐：

```text
ContextProvider
```

可以有：

```text
ConversationProvider
AttachmentProvider
UpstreamArtifactProvider
ProjectSearchProvider
MemoryProvider
```

没有某个 Provider：

```text
skip
```

---

# 三十六、推荐目录结构

```text
shared/
└── context_resolution/
    ├── core_protocol.md
    ├── source_priority.md
    ├── conflict_resolution.md
    ├── volatility_rules.md
    ├── relevance_filter.md
    └── provider_contract.md
```

Grill-Me：

```text
shared/
└── grill_me/
    ├── core_protocol.md
    ├── state_model.md
    └── recommendation_policy.md
```

---

# 三十七、三个 Skill 的接入方式

每个 `SKILL.md` 加入：

```text
Stage 0A — Context Resolution
Stage 0B — Adaptive Grill-Me
Stage 0C — Protocol Snapshot
Stage 1 — Execution
```

## Stage 0A

```text
1. Parse current task
2. Resolve existing context
3. Detect conflicts
4. Mark unresolved dimensions
```

## Stage 0B

只问：

```text
Critical / High-impact unresolved variables
```

每题必须提供：

```text
Recommended + reason
```

## Stage 0C

生成：

```text
Protocol Snapshot
```

并记录来源：

```text
USER
CONTEXT
INFERRED
DEFAULT
SYSTEM_RULE
```

## Stage 1

只有：

```text
stage0_status = CONFIRMED
```

才能执行。

---

# 三十八、建议写入 Shared Protocol 的硬规则

```text
1. Never ask for information already reliably resolved from context.

2. Never silently inherit stale or conflicting project settings.

3. Current explicit user instructions override historical context.

4. Project context must be retrieved on demand, not loaded wholesale.

5. Context facts and user preferences must be distinguished.

6. Only unresolved Critical / High-impact variables should trigger Grill-Me.

7. Every inherited decision must retain provenance.

8. Context availability is optional; ScholarFlow must degrade gracefully.
```

---

# 三十九、测试设计

至少加入以下测试。

## Test 1：重复信息不再问

对话已说明：

```text
English only
2018-present
```

期望：

```text
Grill 不出现 Language / Time
```

## Test 2：项目文件补全研究对象

项目文件已有：

```text
Target disease = breast cancer
```

当前用户：

```text
继续搜相关文献
```

期望：

```text
自动继承 breast cancer
```

## Test 3：当前用户覆盖项目文件

项目：

```text
Adults only
```

当前用户：

```text
这次包括儿童
```

期望：

```text
population = adults + children
```

## Test 4：无关项目文件不得污染

项目里大量：

```text
ecology PCR
```

当前任务：

```text
Transformer benchmark
```

期望：

```text
无 PCR / species / ecology 问题
```

## Test 5：Extraction 复用历史 Schema

用户：

```text
继续按上一篇的标准提取
```

期望：

```text
自动复用 schema
```

## Test 6：新论文出现新 Context

历史：

```text
single cohort
```

当前：

```text
3 cohorts
```

期望：

```text
触发 cohort isolation Grill
```

## Test 7：Synthesis 读取 Evidence Tables

已存在结构化 Extraction 输出。

期望：

```text
优先使用 EvidenceRecord
```

而不是重新从摘要推测。

## Test 8：项目文件冲突

两个同级文件：

```text
sample size = 120
sample size = 135
```

无法判断最新。

期望：

```text
UNRESOLVED_CONFLICT
```

## Test 9：无项目能力

环境没有 Project Search。

期望：

```text
Skill 正常运行
```

只增加必要 Grill。

---

# 四十、Benchmark 指标

未来可以加入：

```text
Context Reuse Rate
Duplicate Question Rate
Wrong Inheritance Rate
Conflict Detection Rate
Irrelevant Context Leakage Rate
```

建议目标：

```text
Duplicate Question Rate < 5%
Wrong Inheritance Rate → 尽可能接近 0
Irrelevant Context Leakage Rate < 2%
```

---

# 四十一、推荐开发顺序

## Phase 1

先实现：

```text
Current Conversation
Current Attachments
Upstream Outputs
```

这三类最稳定。

## Phase 2

增加：

```text
Project Search
```

但必须 query-driven。

## Phase 3

增加：

```text
Conflict Resolution
Volatility
Freshness
```

## Phase 4

增加：

```text
Context benchmark
```

---

# 四十二、推荐最终流程

```text
                     User Request
                          ↓
                   Parse Current Task
                          ↓
                 Context Resolution
                          ↓
       ┌──────────────────┼──────────────────┐
       │                  │                  │
 Conversation        Attachments        Upstream Data
       │                  │                  │
       └──────────────────┼──────────────────┘
                          ↓
                Unresolved Variables
                          ↓
              Targeted Project Search
                          ↓
                 Decision State
                          ↓
                 Domain Detection
                          ↓
                   Domain Lens
                          ↓
                 Adaptive Grill-Me
                          ↓
        Recommended Options + User Choice
                          ↓
                 Protocol Snapshot
                          ↓
                     CONFIRMED
                          ↓
                       Execute
```

---

# 四十三、最终原则

## Principle 1

```text
Context before questions.
```

先读取已有信息，再提问。

## Principle 2

```text
Retrieve context on demand, not in bulk.
```

按问题检索，不全量加载。

## Principle 3

```text
Current intent overrides historical context.
```

当前用户意图优先。

## Principle 4

```text
Facts, preferences, and decisions are different.
```

客观事实、历史偏好和当前决策必须分开。

## Principle 5

```text
Ask only what cannot be reliably resolved.
```

只有真正不能从上下文确定的高影响变量才 Grill。

## Principle 6

```text
Every inherited value must retain provenance.
```

所有继承值必须能追溯来源。

---

# 四十四、最终定位

Context-Aware Grill-Me 不应该只是：

> “一个会读历史记录的问卷。”

更合理的定位是：

> **A context-resolving adaptive research decision gate.**

中文：

> **一个先解析现有科研上下文，再针对关键未决变量进行动态追问的科研决策门禁。**

最终目标不是：

```text
让 Agent 问更多问题
```

而是：

```text
让 Agent 少问重复问题，
多问真正会改变科研结果的问题。
```

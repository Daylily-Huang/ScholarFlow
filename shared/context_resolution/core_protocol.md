# ScholarFlow Context Resolution Layer: Core Protocol

> **Status**: Production Standard  
> **Applicability**: Upstream context parsing for all ScholarFlow research skills  
> **Core Axiom**: **Context before questions. (先解析已知科研上下文，再针对关键未决变量动态提问)**

---

## 一、为什么需要 Context Resolution Layer？

传统 Agent 的交互问答经常陷入“失忆式复读”：
- 用户在前几轮对话中已明确限定时间范围（如近五年），Agent 却依然在 Stage 0 弹出时间选项；
- 上传的论文附件或项目计划书中已写明研究对象，Agent 仍重新向用户发问；
- 上游 Discovery 已经确定纳排标准，下游 Synthesis 又重新质问用户纳入哪些文献；
- 上游 Extraction 已经生成结构化证据表，下游却让用户重新提供文献摘要。

**Context Resolution Layer 的使命**：
在向用户发出任何 Grill-Me 决策问题之前，**自动感知、提取、校验并沉淀现有可靠上下文**。
> **铁律**：能从可靠上下文中确定的内容，不再向用户发问；只有真正需要用户裁决的高影响未决变量才进入 Grill-Me。

---

## 二、六大核心原则 (The Six Core Principles)

### 原则 1：先读上下文，再提问题 (Context Before Questions)
在生成任何 Stage 0 提问清单前，系统必须先执行上下文解析流水线，盘点已知事实。

### 原则 2：按需针对检索，严禁全量粗放加载 (Retrieve on Demand, Not in Bulk)
项目资料与历史文档只针对未决的高影响变量（Unresolved Variables）进行精准定向查询，严禁一股脑将整个项目的全部历史文档填入上下文。

### 原则 3：当前明确意图覆盖历史上下文 (Current Intent Overrides Historical Context)
用户在当前对话中提出的显式新指令拥有最高仲裁权，自动覆盖历史文件中记录的旧设置。

### 原则 4：客观事实、历史偏好与当前决策严格区分 (Facts vs Preferences vs Decisions)
- **事实 (Fact)**：如“目标化合物分子量为 342.3”，可直接信赖；
- **历史偏好 (Preference)**：如“上次调研排除了预印本”，可作为参考但不能假设用户本次必然相同；
- **当前任务决策 (Decision)**：本次研究的核心边界，必须由当前用户或任务上下文明确。

### 原则 5：仅对未决的高影响变量发起提问 (Ask Only What Cannot Be Reliably Resolved)
只有标记为 `UNRESOLVED` 或 `UNRESOLVED_CONFLICT` 的 `CRITICAL` / `HIGH_IMPACT` 级别变量，才允许进入提问池。

### 原则 6：所有继承值必须具备可审计来源追溯 (Every Inherited Value Must Retain Provenance)
从对话、附件、上游产物或项目文件继承的每一个参数，都必须在最终快照中明确注明来源层级与文件引用。

---

## 三、标准三段式门禁流转 (Stage 0A -> 0B -> 0C)

```text
┌─────────────────────────────────────────────────────────────┐
│ Stage 0A: Context Resolution (现有科研上下文解析与盘点)       │
│  1. 解析当前用户提示词 (Layer 1)                             │
│  2. 解析会话历史与附件 (Layer 2 & 3)                         │
│  3. 解析上游产物与定向检索项目文件 (Layer 4 & 5)              │
│  4. 识别已解决变量 -> 标记来源与置信度                       │
│  5. 识别未解决变量与潜在冲突 -> 输出决策状态字典             │
└──────────────────────────────┬──────────────────────────────┘
                               │ 仅传递 UNRESOLVED / CONFLICT 项
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 0B: Adaptive Grill-Me (针对性决策质询门禁)             │
│  1. 呈现极简上下文确认摘要 ("已从上下文确认...")             │
│  2. 仅对 3~5 个高影响未决要素发起选项提问                    │
│  3. 严格执行 STOP Rule，等待用户反馈                         │
└──────────────────────────────┬──────────────────────────────┘
                               │ 用户极速确认 (按推荐 / 序号 / 覆盖)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 0C: Protocol Snapshot (全量来源追溯协议快照)           │
│  - 标记 USER / CONTEXT / INFERRED / DEFAULT / SYSTEM_RULE   │
│  - 签署 CONFIRMED 放行令，解锁 Stage 1 实质执行               │
└─────────────────────────────────────────────────────────────┘
```

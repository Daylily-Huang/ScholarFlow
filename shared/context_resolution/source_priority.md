# Context Resolution Layer: Source Priority & Layer Hierarchy

> **Status**: Production Standard  
> **Applicability**: Precedence resolution when determining parameters from multi-source contexts

---

## 1. 五层上下文来源体系 (The 5-Layer Hierarchy)

ScholarFlow 将所有可访问的上下文划分为五个具备明确优先级的来源层级：

```text
┌───────────────────────────────────────────────────────────┐
│ Layer 1: Current User Message (最高优先级)                │
│ - 当前轮次用户直接输入的指令、提示词与约束条件            │
├───────────────────────────────────────────────────────────┤
│ Layer 2: Current Conversation Context                     │
│ - 本次会话前序轮次中用户已明确确认或陈述过的决定          │
├───────────────────────────────────────────────────────────┤
│ Layer 3: Current Attachments / Task Files                 │
│ - 本任务直接提供的文献全文 PDF、题录 CSV、表格与附件      │
├───────────────────────────────────────────────────────────┤
│ Layer 4: Upstream ScholarFlow Outputs                     │
│ - 上游 Discovery 输出的检索快照、Extraction 结构化证据表 │
├───────────────────────────────────────────────────────────┤
│ Layer 5: Project Knowledge / Historical Files (定向检索)   │
│ - 项目根目录下的课题方案、立项书、长期记忆与配置文件      │
└───────────────────────────────────────────────────────────┘
```

---

## 2. 来源判定优先级铁律 (Precedence Order)

当不同来源层级对同一个变量提供了信息时，严格按以下降序优先采纳：

$$
\text{Current User (L1)} > \text{Conversation (L2)} > \text{Attachments (L3)} > \text{Upstream Output (L4)} > \text{Project Files (L5)} > \text{High-Conf Inferred} > \text{Default}
$$

### 优先规则细则：
1. **当前用户指令绝对优先**：若项目文件记录“纳入范围：仅限成人”，而当前用户输入“本次调研扩大至儿童与青年”，系统必须无条件采纳当前用户指令，并在变更记录中注明覆盖旧设置；
2. **上游产物优先于离线文档**：下游 Synthesis 在盘点纳入文献时，以 Discovery/Extraction 实际输出的结构化列表为准，而非项目历史早期草稿；
3. **定向激活原则**：Layer 5（项目历史文件）只在 Layer 1–4 均未提供该必要变量时，才执行针对该变量的 Query-Driven 定向查询，绝不预先盲目读取全库。

# ScholarFlow Core Evidence Principles (跨学科证据纪律铁律)

> **Status**: Core Grounding Standard (Epistemic Invariant)  
> **Applicability**: All ScholarFlow skills and workflows across all disciplines  
> **Fundamental Axiom**: **Domain-neutral core, domain-aware execution. (核心必须学科中立；领域知识按需注入)**

---

## 一、证据纪律 vs 学科方法规范 (Evidence Discipline vs Domain Methodology)

为了根除学科锚定偏见（Domain Anchoring Bias），ScholarFlow 必须严格区分**不可动摇的认识论证据纪律**与**按学科动态调整的方法学规范**：

```text
┌────────────────────────────────────────────────────────┐
│      Evidence Discipline (通用认识论证据纪律 - 永不变更)     │
│  - Quote binding (原句绑定)                             │
│  - Source traceability (来源可追溯性)                    │
│  - Objective vs Interpretation separation (事实/推论隔离) │
│  - Explicit uncertainty (显式不确定性建模)                │
│  - Non-smoothing of contradictions (不抹杀学术矛盾)       │
│  - Not Reported != Not Used (未提及绝不常识脑补)           │
└──────────────────────────┬─────────────────────────────┘
                           │ 动态特化 (Specialized by)
                           ▼
┌────────────────────────────────────────────────────────┐
│     Domain Methodology (学科动态方法学规范 - 按 Lens 注入)   │
│  - 生物医药: PICO, RCT, CONSORT, 偏倚风险 (RoB)          │
│  - 计算机科学: Benchmark, Split, Code/Data Leakage      │
│  - 材料与化学: Synthesis condition, Characterization    │
│  - 社会科学: Identification strategy, Confounding       │
│  - 生态与演化: Sampling design, Detection probability   │
└────────────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> **铁律**：学科透镜（Domain Lens）只允许特化或细化关注维度，**绝不允许放宽、绕过或覆盖通用证据纪律**。

---

## 二、六大通用证据原则 (The Six Invariant Principles)

### 原则 1：零常识脑补与严格明示 (No Unsupported Completion)
- 提取或综述时，若文献中未明确提供某参数、条件或数值，必须将其记录为 `NOT_REPORTED`（或代码 `E4`）；
- 严禁基于领域常识、行业惯例或模型猜测将缺失值补齐；
- 严禁将“未提及（Not Reported）”等同于“未使用（Not Used）”或“不存在（Absent）”。

### 原则 2：最小充分原句与来源锚定 (Verbatim Quote Binding)
- 任何提取的事实或定量参数，必须绑定原文中的“最小充分原句（Minimum Sufficient Verbatim Quote）”及其定位指针（章节、段落、表格编号或页码）；
- 杜绝脱离原文上下文的悬空抽取（Floating Extractions）。

### 原则 3：客观事实与主观解释物理隔离 (Strict Separation of Findings and Interpretations)
- 文献的实际观测结果（Objective Findings / Empirical Data）与作者在讨论部分的推论假说（Subjective Interpretations）、以及 AI 智能体的评述，必须保持物理隔离；
- 严禁将推论或模型重计算值无标记地混同为作者直接报告的事实。

### 原则 4：不确定性显式建模 (Explicit Uncertainty Modeling)
- 所有模糊、条件受限或存在推导误差的参数，必须显式标注不确定性标签（`UNKNOWN`, `AMBIGUOUS`, `NOT_REPORTED`, `CONTRADICTORY`, `LOW_CONFIDENCE`）；
- 严禁将不确定性隐匿在平滑的文本叙述中。

### 原则 5：学术争议忠实保留，严禁多数决抹杀 (Preservation of Contradictions)
- 跨篇文献之间出现数值、方向或机制上的冲突时，必须完整保留分歧两方的证据，探究导致分歧的方法学与环境边界（Comparability Boundary）；
- 严禁简单以“发表篇数多寡”进行民主投票（Majority Voting）从而抹杀关键反例。

### 原则 6：示例严禁上升为通用执行规则 (Examples Must Not Become Rules)
- 核心规范中出现的一切学科特定案例（如 PCR、临床试验队列、神经网络层数等），仅仅作为理解辅助示例；
- 执行规则本身必须使用学科中立的抽象术语（如 `Target Entity`, `Method`, `Context Unit`, `Outcome`）。

### 原则 7：主张必须由主张级证据支持 (Claim–Evidence Alignment Principle)
- **认识论红线**：**Mention ≠ Relation**（提及 ≠ 关系），**Co-occurrence ≠ Relation**（共现 ≠ 关系），**Contextual proximity ≠ Relation**（上下文邻近 ≠ 目标关系），**Entity evidence ≠ Claim evidence**（实体证据 ≠ 主张证据）；
- 提取科学关系、机制、因果、优劣对比、调控或命题型事实时，必须验证目标主张本身；实体在同一上下文中的共现、共测或邻近，绝不能作为该关系成立的充分证据；
- 仅当证据在正确的同质上下文内直接、结构化支持目标主张本身时，才允许进入确认输出（Confirmed Output）；严禁模型擅自添加关系谓词，严禁跨不兼容上下文拼凑断言。

---

## 三、跨学科通用本体映射 (Universal Ontology)

| 核心抽象概念 | 抽象定义 | 生命科学示例 | 生物医药示例 | 计算机科学示例 | 材料/化学示例 | 社会科学示例 |
|---|---|---|---|---|---|---|
| **Target Entity / System** | 研究所聚焦的核心实体或系统 | 物种 / 基因 / 种群 | 患者群体 / 靶点 / 疾病 | 模型架构 / 算法 / 任务 | 晶体材料 / 化合物 / 合金 | 目标人口 / 组织 / 市场 |
| **Method / Approach** | 核心技术路线与操作范式 | 测序 / 标记扩增 | 临床试验 / 诊断测试 | 预训练 / 微调 / 剪枝 | 水热合成 / 光谱表征 | 双重差分 / 问卷抽样 |
| **Context Unit** | 保证数据内部同质的最小隔离单元 | 独立 Assay / 采样样点 | 试验组别 (Arm) / 队列 | 数据集 / 评测 Split | 合成批次 / 测试温度 | 调查轮次 / 亚群样本 |
| **Outcome / Claim** | 观测得到的定量指标或核心主张 | 丰度 / 杂合度 / 多态性 | 治愈率 / 风险比 (HR) | 准确率 / F1 / 延迟 | 转化率 / 晶格常数 / 强度 | 边际效应 / 弹性系数 |
| **Comparability Boundary** | 决定跨研究能否横向对比的边界 | 生境 / 空间尺度 / 季节 | 入组标准 / 年龄 / 剂量 | Benchmark / 评测协议 | 纯度 / 气氛 / 测试仪器 | 制度背景 / 样本时段 |

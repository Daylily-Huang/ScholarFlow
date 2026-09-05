# 海量文献多 SubAgent 并发初筛规程 (Multi-SubAgent Concurrent Screening Protocol)

## 一、为什么需要多 SubAgent 并发初筛 (Map-Reduce)？

在系统化文献检索中，经过跨库检索与四级去重后，往往会产生 50–300 篇候选文献。
如果由单一 Agent 在同一个对话上下文中逐篇阅读摘要进行判断，将面临两大严重缺陷：
1. **上下文严重膨胀 (Context Bloat)**：数百篇文献的标题与摘要会迅速消耗数万 Token，极度挤占宝贵的推理窗口；
2. **注意力衰减与漂移 (Attention Drift)**：大模型在长文本单次处理后半段时，对纳入/排除标准的执行尺度容易发生疲劳漂移（出现首尾标准不一）。

**本规程引入 Map-Reduce 并发架构**：当文献量达到阈值时，自动将文献分块（Chunking），并发派生轻量子智能体（SubAgents）独立打分，最后由主导专家进行聚合与争议仲裁。

---

## 二、并发初筛触发阈值与分块策略 (Batching Strategy)

```mermaid
flowchart TD
    Raw[Stage 4 去重后的候选文献池 N 篇] --> Check{文献总量 N 是否 >= 30 篇?}
    Check -- 否 (<30篇) --> Single[主检索专家就地单智能体初筛]
    Check -- 是 (>=30篇) --> Split[Map 阶段: 自动分片 15~25 篇/分片]
    
    Split --> S1[SubAgent 1: 审查 Batch 1]
    Split --> S2[SubAgent 2: 审查 Batch 2]
    Split --> S3[SubAgent 3: 审查 Batch 3]
    Split --> S4[SubAgent n: 审查 Batch n]
    
    S1 & S2 & S3 & S4 --> Reduce[Reduce 阶段: 主专家聚合评分与冲突仲裁]
    Reduce --> UncertainCheck{是否存在争议或边界文献?}
    UncertainCheck -- 是 --> KeepUncertain[全部保守保留为 Uncertain]
    UncertainCheck -- 否 --> FinalPool[生成初筛合格文献池 Stage 5]
```

- **触发阈值**：$N \ge 30$ 篇；
- **分块尺寸**：每个 Batch 固定为 **15–25 篇**（单次调用 Token 控制在 4k–8k 内，处于 LLM 逻辑判断的最佳敏锐区间）；
- **最大并发度**：同时派生 2–5 个 SubAgent 并发运行。

---

## 三、SubAgent 独立初筛指令与输入契约 (SubAgent Prompt Contract)

当调用 `invoke_subagent` 派生子审查员时，必须传递标准化的微型提示词：

### 1. 角色与任务定义 (Role & Task)
```text
你是一名极其严谨的科研文献初筛审查员 (Literature Screening SubAgent)。
你的唯一任务是：对照给定的【科学问题】与【纳入/排除标准】，逐条审查下述文献批次（Batch）的标题与摘要，输出纯 JSON 格式的初筛裁决结果。
```

### 2. 传递的输入数据 (Input Payload)
```json
{
  "research_question": "利用粪便 DNA 微卫星进行鹿科动物个体识别与种群评估",
  "inclusion_criteria": [
    "I1: 研究涉及鹿科或有蹄类物种",
    "I2: 涉及粪便等非损伤性样本或微卫星 (STR) 标记",
    "I3: 涉及个体识别、遗传标记或种群估算"
  ],
  "exclusion_criteria": [
    "EXC_TAXON: 非目标动物类群",
    "EXC_METHOD: 纯非遗传学食性分析或解剖学",
    "EXC_DOC_TYPE: 征稿通知、书评、勘误"
  ],
  "batch_records": [
    {
      "id": "REC001",
      "title": "...",
      "abstract": "..."
    }
  ]
}
```

### 3. SubAgent 产出契约 (Output Schema)
SubAgent 必须严格返回如下 JSON 数组，严禁包含任何前缀闲聊：
```json
[
  {
    "id": "REC001",
    "status": "Include",
    "reason_code": "MATCH_ALL",
    "reason_detail": "摘要明确使用粪便微卫星进行个体识别与种群计数",
    "confidence_score": 0.95
  },
  {
    "id": "REC002",
    "status": "Exclude",
    "reason_code": "EXC_TAXON",
    "reason_detail": "研究对象为食肉目豹属，非鹿科有蹄类",
    "confidence_score": 0.98
  },
  {
    "id": "REC003",
    "status": "Uncertain",
    "reason_code": "BORDERLINE_TOPIC",
    "reason_detail": "摘要仅提及有蹄类调查，未说明具体分子标记类型，建议保留全文复核",
    "confidence_score": 0.60
  }
]
```

---

## 四、模式一：高吞吐分块并行初筛 (High-Throughput Chunked Map-Reduce)

适用于常规科研立项、快速调研或开题文献筛选：
1. **结构化拼装**：将各分片的打分结果按 `id` 回填至全局文献库；
2. **保守保留兜底 (Conservative Principle)**：
   - 凡有任何 SubAgent 标记为 `Uncertain` 或置信度 $\text{confidence} < 0.70$ 的文献，**一律直接归入 `Uncertain` 候选池**，禁止降级为 Exclude；
3. **排除原因审计**：
   - 检查所有 `Exclude` 文献是否附带标准错误代码（`EXC_TAXON`, `EXC_METHOD` 等），对未说明具体理由的排除项强制回退为 `Uncertain`；
4. **统计各批次初筛产出**：
   - 记录初筛批次总览表，作为检索报告中 Stage 5 的流转证据。

---

## 五、模式二：PRISMA 2020 Item 8 双盲独立初筛规程 (Dual-Reviewer Blind Protocol)

> [!IMPORTANT]
> **PRISMA 2020 Item 8 发表级硬规范**：
> 系统综述 (Systematic Review) 与 Meta 分析的国际同行评审明确要求：**必须由至少两名独立审查员背对背（背靠背盲审）独立完成初筛**，报告评阅者一致性统计指标（如 Cohen's Kappa），任何分歧由第三人仲裁。
> 单一智能体切片分工（单人初筛）在方法学上无法满足 PRISMA 2020 发表标准。本规程通过**真双盲并发双审 + 确定性程序仲裁**全面履约。

### 1. 双盲初筛架构图

```mermaid
flowchart TD
    Pool[待初筛文献池 N 篇] --> Dispatch[双盲隔离派发]
    Dispatch --> RevA[审查员 A SubAgent-A<br/>独立上下文 / 盲审]
    Dispatch --> RevB[审查员 B SubAgent-B<br/>独立上下文 / 盲审]
    
    RevA --> ResA[审查员 A 决策集 JSON]
    RevB --> ResB[审查员 B 决策集 JSON]
    
    ResA & ResB --> Calc[运行脚本 calculate_screening_agreement.py]
    
    Calc --> Metric[计算 Cohen's Kappa 系数与混淆矩阵]
    Calc --> AuditCSV[生成 PRISMA 审计追踪表 screening_dual_audit.csv]
    
    Metric --> SplitCheck{双方裁决是否一致?}
    SplitCheck -- 完全一致 Include/Include --> DirectInclude[直接纳入 Stage 6 全文获取池]
    SplitCheck -- 完全一致 Exclude/Exclude --> DirectExclude[正式排除并归档双重剔除理由]
    SplitCheck -- 存在分歧 Include vs Exclude/Uncertain --> ArbQueue[分流至待仲裁池 arbitration_queue.json]
    
    ArbQueue --> SeniorHuman[第三评阅人 / 资深学者仲裁]
    SeniorHuman --> FinalDecide[最终录入裁决意见]
```

### 2. 双评阅人隔离执行机制 (Blind Isolation)

- **完全上下文隔离**：Reviewer A 与 Reviewer B 分别在独立的 SubAgent 实例中运行（或通过无共享历史的独立 API 会话调用），双方**互不知晓对方的身份、存在及打分决策**；
- **提示词对称但可适度差异化**：
  - Reviewer A 侧重于目标科学问题与实验方法的正面符合度；
  - Reviewer B 侧重于排除标准与边界陷阱的反面严格校验；
- 双方遵循统一的 3 分类标定：`Include`、`Exclude`、`Uncertain`。

### 3. 一致性量化评定标准 (Cohen's Kappa 判准)

系统调用内置脚本 `calculate_screening_agreement.py`，根据经典统计学标尺（Landis & Koch 1977）自动生成一致性检验报告：

$$\kappa = \frac{P_o - P_e}{1 - P_e}$$

| Cohen's Kappa (κ) | 一致性评级 (Interpretation) | PRISMA 发表合规度 | 后续操作建议 |
|:---:|:---:|:---:|:---|
| **0.81 – 1.00** | **Almost Perfect (极佳)** | ⭐⭐⭐ 顶级发表级 | 双一致项直接通过，仅对极少分歧项人工确认 |
| **0.61 – 0.80** | **Substantial (良好)** | ⭐⭐ 国际规范级 | 双方一致项流转，分歧项移交第三评阅人仲裁 |
| **0.41 – 0.60** | **Moderate (中度)** | ⚠️ 需补充对齐 | 需召开双人校准会议，由资深学者全量复核分歧项 |
| **< 0.40** | **Fair / Poor (不可信)** | ❌ 不合规 | 纳入/排除标准定义有重大歧义，勒令重构标准后重筛 |

### 4. 自动化脚本调用指引 (CLI Tool)

在完成 Reviewer A 与 Reviewer B 独立初筛后，直接执行内置评估脚本：

```bash
# 执行双盲一致性检验，并同步生成发表级 Markdown 总结、PRISMA 审计追踪 CSV 与待仲裁队列
python skills/literature-discovery-acquisition/scripts/calculate_screening_agreement.py \
  -a ./scratch/screening_reviewer_a.json \
  -b ./scratch/screening_reviewer_b.json \
  -o ./output/screening_agreement_report.md \
  --csv ./output/screening_dual_audit.csv \
  --arbitration-json ./output/arbitration_queue.json
```

### 5. PRISMA 2020 审计追踪文件说明 (`screening_dual_audit.csv`)

脚本导出的 CSV 包含完整的可审计字段，可直接作为系统综述与 Meta 分析投稿的 Supplementary File：
- `record_id` / `title`：文献唯一标识与题名；
- `reviewer_a_decision` / `reviewer_a_code` / `reviewer_a_reason`：审查员 A 裁决及具体判准代码；
- `reviewer_b_decision` / `reviewer_b_code` / `reviewer_b_reason`：审查员 B 裁决及具体判准代码；
- `consensus_status`：`AGREED`（完全一致）或 `DISCREPANCY`（分歧冲突）；
- `arbitrated_decision`：仲裁后最终决策（一致项自动填入，分歧项预留待填）；
- `arbitrator_notes`：资深评阅专家签署的仲裁理由。


# Literature Evidence Extraction: Stage 0 Grill Dimensions

> **Status**: Production Reference  
> **Skill**: `literature-evidence-extraction`  
> **Core Question of Stage 0**: **"究竟允许从每篇文献中提取什么事实与参数，边界何在？"**

---

## 1. 维度总览与优先级分类

| 维度 ID | 维度名称 | 决策层级 | 默认推荐方案 (Recommended) | 默认置信度 |
|---|---|---|---|---|
| `E1` | 抽取目的与任务类型 | `CRITICAL` | 系统综述 / Meta 分析结构化参数与定量数据提取 | `[高置信度]` |
| `E2` | 待抽取的文献范围与输入边界 | `CRITICAL` | 初筛合格的全文 PDF / 权威解析全文文本 | `[高置信度]` |
| `E3` | 抽取 Schema 选择与定制 | `CRITICAL` | 通用实证研究双轨 Schema (`schemas/v1.0/general_empirical.json`) | `[高置信度]` |
| `E4` | 证据单元切分与多实验隔离粒度 | `CRITICAL` | 细粒度拆分：每个独立 Assay/Trial/采样点单独一行记录 | `[高置信度]` |
| `E5` | 推导证据与重计算策略 | `HIGH_IMPACT` | 允许透明重计算（必须附带明确公式、原始输入与代码） | `[高置信度]` |
| `E6` | 计量单位与数值归一化要求 | `HIGH_IMPACT` | 保留原文原始数值与单位，并在标准列并列给出 SI 国际标准换算值 | `[高置信度]` |
| `E7` | 表格与附录补充材料处理策略 | `DEFAULTABLE` | 优先深入挖掘附录与大表，正文与附录冲突以详细表格为准 | `[高置信度]` |
| `E8` | 事实核验与解释边界 | `DEFAULTABLE` | 严格执行 Quote-before-Extract，客观 Findings 与主观 Interpretations 物理隔离 | `[高置信度]` |
| `E9` | 批量一致性与抽检策略 | `DEFAULTABLE` | 完成批次后执行 10% 随机高危字段（CI、p值、样本量）对齐审计 | `[高置信度]` |

---

## 2. 详细维度说明与选项设计

### E1: 抽取目的与任务类型 (`CRITICAL`)
- **[A] (Recommended)** 系统综述 / Meta 分析结构化参数与定量数据提取 — *[依据：遵循标准循证医学与定量综合规范，提取高精度参数]* `[高置信度]`
- **[B]** 特定论文事实核验（Claim Audit 模式） — *[依据：对照原文审计已有论断的真实性与歪曲程度]* `[中置信度]`
- **[C]** 方法学与实验协议关键参数对比 — *[依据：聚焦试剂、设备与具体操作步骤]* `[中置信度]`

### E2: 待抽取的文献范围与输入边界 (`CRITICAL`)
- **[A] (Recommended)** 初筛合格的全文 PDF / 权威解析全文文本 — *[依据：保证表格、附录大表与方法细节完全可见]* `[高置信度]`
- **[B]** 仅限公开发表的摘要 (Abstract) 与标题粗提 — *[依据：无全文时的降级应急模式]* `[需权衡]`

### E3: 抽取 Schema 选择与定制 (`CRITICAL`)
- **[A] (Recommended)** 通用实证研究双轨 Schema (`schemas/v1.0/general_empirical.json`) — *[依据：内置 E1-E4 证据隔离与双轨输出规范]* `[高置信度]`
- **[B]** 生物医药临床干预 Schema (`schemas/v1.0/biomedical_intervention.json`) — *[依据：聚焦 PICO、对照组与临床效应量]* `[高置信度]`
- **[C]** 生态种群与野外调查 Schema (`schemas/v1.0/ecological_population.json`) — *[依据：聚焦野外样带、种群参数与分子标记]* `[高置信度]`

### E4: 证据单元切分与多实验隔离粒度 (`CRITICAL`)
- **[A] (Recommended)** 细粒度拆分：每个独立 Assay / Trial / 样点单独形成一行记录 — *[依据：杜绝组间混杂，保障横向精准对比]* `[高置信度]`
- **[B]** 粗粒度整篇文献单条记录（仅提取主要综合结论） — *[依据：宏观概览适用]* `[需权衡]`

### E5: 推导证据与重计算策略 (`HIGH_IMPACT`)
- **[A] (Recommended)** 允许透明重计算（必须附带明确公式、原始输入与计算代码，标记为 Derived） — *[依据：极大提升数据可用性且完全可审计]* `[高置信度]`
- **[B]** 严禁任何重计算，仅提取作者字面显式陈述数值 — *[依据：极度保守核验适用]* `[中置信度]`

### E6: 计量单位与数值归一化要求 (`HIGH_IMPACT`)
- **[A] (Recommended)** 保留原文原始数值与单位，并在标准列并列给出 SI 国际标准换算值 — *[依据：兼顾原文审计对照与跨文献横向定量合成]* `[高置信度]`
- **[B]** 仅保留作者原文单位（不执行任何自动换算） — *[依据：保留原始面貌]* `[中置信度]`

### E7: 表格与附录补充材料处理策略 (`DEFAULTABLE`)
- **[A] (Recommended)** 优先深入挖掘附录与大表，正文与附录冲突以详细表格为准 — *[依据：高精定量参数绝大多数沉淀在附录与大表]* `[高置信度]`
- **[B]** 仅提取正文主体内容，忽略外部补充附件 — *[依据：节省计算带宽]* `[需权衡]`

### E8: 事实核验与解释边界 (`DEFAULTABLE`)
- **[A] (Recommended)** 严格执行 Quote-before-Extract，客观 Findings 与主观 Interpretations 物理隔离 — *[依据：ScholarFlow 核心可信抽取铁律]* `[高置信度]`

### E9: 批量一致性与抽检策略 (`DEFAULTABLE`)
- **[A] (Recommended)** 完成批次后执行 10% 随机高危字段（CI、p值、样本量）对齐审计 — *[依据：发现模型幻觉与数字转录错位的标准 QC 机制]* `[高置信度]`

---

## 3. 提问生成与默认规则

1. 启动时解析已有任务指示，将已确定项标记为 `[INFERRED]`；
2. 动态挑选未决的 `CRITICAL` 维度（E1-E4）与关键 `HIGH_IMPACT` 维度（E5-E6），组合为 **3~5 题**；
3. 其余 `DEFAULTABLE` 维度（E7-E9）自动应用默认选项 A，并在 Protocol Snapshot 中打上 `[DEFAULTED]` 标签；
4. 提问输出后，**Agent 必须执行 STOP Rule**，等待用户回复。

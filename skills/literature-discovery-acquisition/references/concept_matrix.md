# Stage 1-2: 概念矩阵构建与检索式扩展规程 (Concept Matrix & Query Expansion)

> **Status**: Production Standard  
> **Applicability**: Literature Discovery across all disciplines  
> **Core Principle**: Domain-neutral core concept buckets with multi-disciplinary expansion rules.

---

## 一、概念矩阵 (Concept Matrix) 核心方法论

单关键词检索是文献调研中造成严重遗漏（False Negatives）与查全率极低的首要原因。系统化文献检索的核心基石是**正交概念解构 (Orthogonal Concept Decomposition)**。

### 1. 通用正交概念桶划分原则
任何科研问题必须在逻辑上拆解为 2–4 个互不重叠、彼此独立的通用“概念桶”（Concept Buckets）：
- **Concept A（研究对象 / 目标实体与系统 Target Entity / System）**：
  - *跨学科对应*：物种/种群 (生态)、患者/疾病 (医学)、模型/算法 (计算机)、材料/化合物 (材料)、目标群体/制度 (社科)。
- **Concept B（核心方法 / 技术范式 Method / Approach）**：
  - *跨学科对应*：分子标记/PCR、临床试验/RCT、注意力机制/微调、水热法/光谱、双重差分/IV回归。
- **Concept C（试验环境 / 介质 / 基准 Context / Environment / Benchmark）**：
  - *跨学科对应*：生境/野外采样、血清/组织、基准数据集/评测Split、薄膜/手套箱惰性气体、调查轮次/区域。
- **Concept D（研究目的 / 结果变量 / 科学主张 Outcome / Metric / Claim）**：
  - *跨学科对应*：个体识别/丰度、风险比/治愈率、准确率/F1/延迟、光电转换效率/晶格参数、因果效应/弹性。

### 2. 词汇全维度发掘规则
每个概念桶内部必须全面挖掘以下 7 个维度的同义表述：
1. **核心词 (Core Term)**：最通用、标准的学术规范术语；
2. **同义词 (Synonyms)**：学术界使用的其他等价表述；
3. **拼写与语法变体 (Spelling Variants)**：美式/英式拼写（fecal/faecal, behavior/behaviour, modeling/modelling）、单复数、连字符；
4. **缩写与全称 (Acronyms & Expansions)**：如 STR ↔ short tandem repeat, LLM ↔ large language model, RCT ↔ randomized controlled trial；
5. **层级范围扩展 (Scope & Hierarchy Expansion)**：
   - *生命科学*：物种 → 亚种/变种 → 属/科上位类群
   - *医学*：具体疾病 → 疾病大类 → 共有生物标志物
   - *计算机*：具体模型 (e.g. LLaMA) → 架构族 (Transformer) → 通用算法类 (SSM / Attention)
   - *材料科学*：具体组分化学式 → 材料大类 (钙钛矿 / 二维材料)
6. **历史与演进术语 (Historical & Alternative Terms)**：早期文献常用而近现代演变的称谓；
7. **受控词表规范词 (Controlled Vocabulary)**：如 MeSH、Emtree、ACM Computing Classification、IEEE Terms。

---

## 二、多学科通用概念矩阵结构示范

### 示例 1：计算机科学 (AI / NLP 场景)
| Concept ID | 概念分类 | 核心词 (Core) | 同义词与缩写 (Synonyms) | 拼写变体 (Variants) | 层级拓展 (Hierarchy) | 受控词 (Controlled) |
|---|---|---|---|---|---|---|
| **C1** | 研究对象 | Large Language Models | LLMs, Foundation Models | large language model | Transformer-based models, generative AI | ACM: Natural language generation |
| **C2** | 核心方法 | Context Compression | prompt compression, token reduction | context-compression | attention distillation, KV-cache pruning | IEEE: Information compression |
| **C3** | 试验基准 | Long-context Benchmark | L-Eval, Needle In A Haystack, BABILong | long context benchmark | evaluation dataset, synthetic benchmark | ACM: Evaluation |
| **C4** | 评价指标 | Retrieval Accuracy | recall, needle retrieval rate | accuracy, retrieval precision | Macro-F1, perplexity degradation | IEEE: Performance evaluation |

### 示例 2：生命科学与生态演化场景
| Concept ID | 概念分类 | 核心词 (Core) | 同义词与缩写 (Synonyms) | 拼写变体 (Variants) | 层级拓展 (Hierarchy) | 受控词 (Controlled) |
|---|---|---|---|---|---|---|
| **C1** | 研究对象 | Panthera uncia | snow leopard, ounce | Uncia uncia | Panthera, Felidae, apex carnivore | NCBI: Panthera uncia |
| **C2** | 核心方法 | microsatellite | STR, SSR | short tandem repeat | simple sequence repeat, VNTR | MeSH: Microsatellite Repeats |
| **C3** | 样本环境 | noninvasive genetics | fecal DNA, scat, pellet | faecal DNA, non-invasive | excrement, environmental DNA | MeSH: Feces |
| **C4** | 评价指标 | individual identification | genetic tagging, fingerprinting | individual recognition | population size estimation, capture-recapture | MeSH: DNA Fingerprinting |

---

## 三、Stage 2：差异化检索式梯队构建 (Query Expansion)

绝对禁止将所有概念简单地用一个巨大而冗长的布尔检索式一次性提交。必须按**差异化检索意图**构建一组互相补充、编号可溯源的检索式（Queries）：

| Query ID | 检索类型 | 目标与特征 | 逻辑表达式设计模板 |
|---|---|---|---|
| **Q01** | **高精核心式 (High Precision)** | 精确捕获核心主题直接相关的最优质文献 | `(C1_core OR C1_syn) AND (C2_core) AND (C3_core) AND (C4_exact)` |
| **Q02** | **高召回扩展式 (High Recall)** | 扩大范围防遗漏，覆盖变体与层级扩展词 | `(C1_all) AND (C2_all) AND (C4_all)` (适当放宽 C3) |
| **Q03** | **方法与技术导向式 (Method-driven)** | 聚焦方法学突破、算法架构与实验细节协议 | `(C1_all) AND (C2_all) AND ("protocol" OR "algorithm" OR "method" OR "architecture")` |
| **Q04** | **领域/系统导向式 (System-driven)** | 覆盖该系统或上层类别的全部同类实证工作 | `(C1_broader) AND (C2_core) AND (C4_core)` |
| **Q05** | **中文高精检索式 (Chinese Precision)** | 国内权威学术期刊与学位论文针对性检索 | `(C1_中文) AND (C2_中文) AND (C3_中文) AND (C4_中文)` |
| **Q06** | **中文扩展检索式 (Chinese Broad)** | 放宽限定词检索中文文献 | `(C1_中文 OR C2_中文) AND (C4_中文)` |

---

## 四、跨数据库语法转义注意项
- **通配符处理**：PubMed / WoS / IEEE 支持截词符 `*`（如 `compress*` 同时匹配 compress, compression, compressed）；
- **布尔逻辑符大写**：`AND`, `OR`, `NOT` 必须全部大写；
- **字段限定符**：
  - PubMed: `[Title/Abstract]`, `[MeSH Terms]`
  - IEEE Xplore: `("Document Title":...) OR ("Abstract":...)`
  - Web of Science: `TS=`, `TI=`, `SO=`
  - Scopus: `TITLE-ABS-KEY()`
  - CNKI: `主题=`, `篇名=`, `关键词=`

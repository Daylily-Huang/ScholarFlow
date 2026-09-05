# Stage 1-2: 概念矩阵构建与检索式扩展规程 (Concept Matrix & Query Expansion)

## 一、概念矩阵 (Concept Matrix) 核心方法论

单关键词检索是文献调研中造成严重遗漏（False Negatives）与查全率极低的首要原因。系统化文献检索的核心基石是**正交概念解构 (Orthogonal Concept Decomposition)**。

### 1. 正交概念桶划分原则
任何科研问题必须在逻辑上拆解为 2–4 个互不重叠、彼此独立的“概念桶”（Concept Buckets）：
- **Concept A（研究对象 / 目标分类群 / 人群 / 疾病）**：如 Cervidae, Muntiacus, NSCLC, Transformer.
- **Concept B（核心方法 / 技术 / 分子标记 / 干预措施）**：如 microsatellite, PCR, CRISPR, Attention mechanism.
- **Concept C（样本类型 / 介质 / 试验环境）**：如 fecal DNA, noninvasive sampling, serum, benchmark dataset.
- **Concept D（研究目的 / 结果变量 / 科学产出）**：如 individual identification, population size estimation, survival rate.

### 2. 词汇全维度发掘规则
每个概念桶内部必须全面挖掘以下 7 个维度的同义表述：
1. **核心词 (Core Term)**：最通用、标准的学术词汇；
2. **同义词 (Synonyms)**：学术界使用的其他完全等价术语；
3. **拼写与语法变体 (Spelling Variants)**：美式/英式拼写（如 fecal / faecal, behaviour / behavior, modeling / modelling）、单复数、连字符（noninvasive / non-invasive）；
4. **缩写与全称 (Acronyms & Expansions)**：如 STR ↔ short tandem repeat, SSR ↔ simple sequence repeat；
5. **分类层级扩展 (Taxonomic Hierarchy)**：
   - 目标物种拉丁学名 + 俗名
   - 下位分类单元（亚种、变种）
   - 上位分类单元（属名、科名、总科、亚目、目）
6. **历史与演进术语 (Historical & Alternative Terms)**：早期文献常用而近现代逐渐演变的称谓；
7. **受控词表规范词 (Controlled Vocabulary)**：如 MeSH 词、Emtree 词、CAB Thesaurus 词。

---

## 二、标准概念矩阵结构规范

每个检索任务必须输出至少包含以下字段的结构化表格：

| Concept ID | 概念分类 | 核心词 (Core) | 同义词与缩写 (Synonyms) | 拼写变体 (Variants) | 上位/下位词 (Hierarchical) | 受控词 (Controlled) |
|---|---|---|---|---|---|---|
| **C1** | 样本类型 | fecal DNA | scat, pellet, dung | faecal DNA, non-invasive, noninvasive | excrement, environmental DNA | MeSH: Feces |
| **C2** | 分子标记 | microsatellite | STR, SSR | short tandem repeat | simple sequence repeat, VNTR | MeSH: Microsatellite Repeats |
| **C3** | 科学目标 | individual identification | genetic tagging, fingerprinting | individual recognition | population estimation, capture-recapture | MeSH: DNA Fingerprinting |
| **C4** | 研究对象 | Muntiacus crinifrons | black muntjac | Muntiacus | Cervidae, deer, cervid, ungulate | NCBI: Muntiacus crinifrons |

---

## 三、Stage 2：检索式扩展与多组检索策略 (Query Expansion)

绝对禁止将所有概念简单地用一个巨大而冗长的布尔检索式一次性提交。必须按**差异化检索意图**构建一组互相补充、编号可溯源的检索式（Queries）。

### 1. 标准检索式梯队设计

| Query ID | 检索类型 | 目标与特征 | 逻辑表达式设计模板 |
|---|---|---|---|
| **Q01** | **高精核心式 (High Precision)** | 精确捕获核心主题直接相关的最优质文献 | `(C1_core OR C1_syn) AND (C2_core) AND (C3_core) AND (C4_exact)` |
| **Q02** | **高召回扩展式 (High Recall)** | 扩大范围防遗漏，覆盖变体与同义词 | `(C1_all) AND (C2_all) AND (C4_all)` (适当放宽 C3) |
| **Q03** | **方法与技术导向式 (Method-driven)** | 聚焦方法学突破与实验细节协议 | `(C1_all) AND (C2_all) AND ("protocol" OR "method" OR "primer" OR "genotyping")` |
| **Q04** | **分类群/领域导向式 (Taxon-driven)** | 覆盖该分类群或学科的全部同类工作 | `(C4_broader) AND (C1_core OR C2_core) AND (C3_core)` |
| **Q05** | **中文高精检索式 (Chinese Precision)** | 国内学术期刊与学位论文针对性检索 | `(C1_中文) AND (C2_中文) AND (C3_中文) AND (C4_中文)` |
| **Q06** | **中文扩展检索式 (Chinese Broad)** | 放宽分类群限定检索中文研究 | `(C1_中文 OR C2_中文) AND (C4_上位中文 OR C4_核心中文)` |

### 2. 跨数据库语法转义注意项
- **通配符处理**：
  - PubMed / WoS 支持截词符 `*`（如 `microsatellit*` 同时匹配 microsatellite, microsatellites）；
  - 注意短语引号：双引号 `" "` 在不同平台中的严格短语检索语义；
- **布尔逻辑符大写**：`AND`, `OR`, `NOT` 必须全部大写；
- **字段限制限定符**：
  - PubMed: `[Title/Abstract]`, `[MeSH Terms]`, `[Author]`
  - Web of Science: `TS=`, `TI=`, `SO=`
  - Scopus: `TITLE-ABS-KEY()`, `EXACTSRCTITLE()`
  - CNKI: `主题=`, `篇名=`, `关键词=`

# 检索概念矩阵模板 (Concept Matrix Template)

## 研究主题：[填写核心研究问题]

### 1. 正交概念桶划分 (Orthogonal Concept Buckets)

- **Concept A（研究对象 / 目标分类群 / 疾病）**：`[核心对象描述]`
- **Concept B（核心方法 / 技术标记 / 干预措施）**：`[核心方法描述]`
- **Concept C（样本类型 / 介质 / 测试环境）**：`[样本/环境描述]`
- **Concept D（目标产出 / 结果变量 / 评价指标）**：`[研究目的描述]`

---

### 2. 概念矩阵详表 (Detailed Concept Matrix)

| Concept ID | 概念分类 | 核心词 (Core Term) | 同义词与缩写 (Synonyms & Acronyms) | 拼写变体 (Spelling Variants) | 上位词 (Broader Terms) | 下位词 (Narrower Terms) | 受控词 (MeSH / Controlled) | 中文对应词 (Chinese Terms) |
|---|---|---|---|---|---|---|---|---|
| **C1** | [概念A] | [term_a1] | [syn_a1, syn_a2] | [var_a1] | [broad_a1] | [narr_a1] | [mesh_a1] | [cn_a1, cn_a2] |
| **C2** | [概念B] | [term_b1] | [syn_b1, syn_b2] | [var_b1] | [broad_b1] | [narr_b1] | [mesh_b1] | [cn_b1, cn_b2] |
| **C3** | [概念C] | [term_c1] | [syn_c1, syn_c2] | [var_c1] | [broad_c1] | [narr_c1] | [mesh_c1] | [cn_c1, cn_c2] |
| **C4** | [概念D] | [term_d1] | [syn_d1, syn_d2] | [var_d1] | [broad_d1] | [narr_d1] | [mesh_d1] | [cn_d1, cn_d2] |

---

### 3. 布尔检索式派生清单 (Derived Queries)

- **Q01 (高精核心式)**：
  ```text
  (C1_core OR C1_syn) AND (C2_core) AND (C3_core) AND (C4_core)
  ```
- **Q02 (高召回扩展式)**：
  ```text
  (C1_core OR C1_syn OR C1_var OR C1_broad) AND (C2_core OR C2_syn) AND (C3_core OR C3_var)
  ```
- **Q03 (方法导向式)**：
  ```text
  (C2_core OR C2_syn) AND (C3_core) AND ("protocol" OR "method" OR "primer" OR "pipeline")
  ```
- **Q04 (中文核心式)**：
  ```text
  (C1_中文) AND (C2_中文) AND (C3_中文)
  ```

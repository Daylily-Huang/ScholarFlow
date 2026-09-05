# 初筛决策记录表模板 (Screening Decision Template)

## 纳入与排除标准基线 (Inclusion / Exclusion Baseline)

- **纳入标准 (Inclusion Criteria)**：
  - I1: 研究涉及目标生物类群/研究对象
  - I2: 使用了目标方法、分子标记或模型
  - I3: 发表在同行评议期刊或具有完整实证学术价值的学位论文
- **排除标准 (Exclusion Criteria)**：
  - E1 (`EXC_TAXON`): 非目标生物类群/非目标研究实体
  - E2 (`EXC_METHOD`): 未采用目标方法或技术路径
  - E3 (`EXC_TOPIC`): 非目标研究科学问题
  - E4 (`EXC_DOC_TYPE`): 非学术实证论文（会议征稿通知、书评、勘误、通告）

---

## 候选文献初筛决策矩阵 (Screening Decision Matrix)

| 记录 ID | 题录信息 (Title, First Author, Year, Journal) | DOI / 标识符 | 来源库 (Databases) | 初筛决策 (Status) | 决策依据与理由 (Reason) | 证据级别 (Evidence) |
|---|---|---|---|:---:|---|:---:|
| **REC001** | [Paper Title 1] ([Author], [Year], [Journal]) | 10.xxxx/xxxx | PubMed, OpenAlex | **Include** | 完全符合 I1, I2, I3 | `VERIFIED` |
| **REC002** | [Paper Title 2] ([Author], [Year], [Journal]) | 10.xxxx/xxxx | Europe PMC | **Exclude** | 触发 E1: 目标物种错误 | `VERIFIED` |
| **REC003** | [Paper Title 3] ([Author], [Year], [Journal]) | NR | Google Scholar | **Uncertain** | 摘要未说明具体标记，保留至全文复审 | `INFERRED` |

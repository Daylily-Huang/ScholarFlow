# 推荐检索重点期刊模板 (Journal Recommendation Template)

## 研究领域与学科大类：[填写学科分类，如生命科学-分子生态学]

### 1. 四层级推荐期刊列表

| 层级 (Tier) | 期刊定位 | 推荐代表期刊 (Journal Titles) | 影响因子/分区 (JCR/CAS) | 学术战略价值 |
|---|---|---|:---:|---|
| **Tier 1** | **顶级综合与旗舰** | *[Journal 1]*, *[Journal 2]* | Q1 / 顶刊 | 领域重大范式转移、宏观理论突破 |
| **Tier 2** | **主题核心与专业顶刊** | *[Journal 3]*, *[Journal 4]*, *[Journal 5]* | Q1 / 1区 | 本领域绝大多数高信度实证研究与方法 |
| **Tier 3** | **权威综述期刊** | *[Review Journal 1]*, *[Review Journal 2]* | Q1 / 综述 | **引文追踪最佳种子池**，系统梳理领域脉络 |
| **Tier 4** | **中文核心 / CSCD** | 《[中文期刊 1]》、《[中文期刊 2]》 | CSCD / 北大核心 | 本土实证数据、特有种调查与本土政策 |

---

### 2. 数据库来源限定检索代码块 (Ready-to-use Source Filters)

#### A. Web of Science (WoS 来源限定)
```text
SO=("[Journal 1]" OR "[Journal 2]" OR "[Journal 3]" OR "[Journal 4]" OR "[Review Journal 1]")
```

#### B. PubMed / MEDLINE (期刊字段限定)
```text
("[J1 NlmAbbr]"[Journal] OR "[J2 NlmAbbr]"[Journal] OR "[J3 NlmAbbr]"[Journal])
```

#### C. Scopus (来源标题限定)
```text
(EXACTSRCTITLE("[Journal 1]") OR EXACTSRCTITLE("[Journal 2]") OR EXACTSRCTITLE("[Journal 3]"))
```

#### D. 中国知网 CNKI (文献来源限定)
```text
(文献来源='[中文期刊 1]' OR 文献来源='[中文期刊 2]')
```

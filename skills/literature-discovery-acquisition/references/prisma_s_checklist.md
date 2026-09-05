# PRISMA-S 16 项系统评价文献检索扩展标准机审规程 (PRISMA-S Checklist Protocol)

## 一、标准概述与制定背景

**PRISMA-S (Preferred Reporting Items for Systematic Reviews and Meta-Analyses literature search extension)** 是国际循证医学与跨学科系统评价（Systematic Review）领域公认最高等级的文献检索报告规范。

为了确保 `literature-discovery-acquisition` Skill 输出的检索过程完全符合 SCI 论文发表、国家自然科学基金立项与硕博毕业论文开题的方法学要求，我们将 PRISMA-S 的 16 项准则完全转化为**最终质量审查员 (Quality Gatekeeper)** 的机器化机审规则。

---

## 二、PRISMA-S 16 项核心准则与机器审计要点 (The 16-Item Checklist)

| 准则编号 | PRISMA-S 标准项目 | 规范要求 | 技能内部映射与机审断言 (Gatekeeper Assertion) |
|:---:|---|---|---|
| **Item 1** | **数据库名称与服务商 (Database Name & Platform)** | 必须报告每个检索数据库的正式名称、数据提供商或访问平台（如 PubMed via NCBI, OpenAlex REST API）。 | ✅ 检查 Stage 3 审计日志是否明确区分平台服务商。 |
| **Item 2** | **多数据库联合检索 (Multi-database Searching)** | 系统评价严禁单一数据库，必须跨两个以上学术源。 | ✅ 检查是否至少调用 2 个以上学术数据源。 |
| **Item 3** | **临床试验与预注册库 (Registries)** | 涉及临床或实证注册时，需指明注册平台（如 ClinicalTrials.gov）。 | ✅ 检查医学/临床课题是否检索了试验注册库。 |
| **Item 4** | **网络与搜索引擎 (Online Resources & Web Engines)** | 若使用了 Google Scholar、网页搜索或预印本平台，需明确记录。 | ✅ 检查 Stage 3 是否显式记录了 Web/Scholar 探测。 |
| **Item 5** | **其他检索方法 (Other Search Methods)** | 必须报告引文双向追踪（Backward / Forward Chasing）与作者追溯。 | ✅ 检查 Stage 6 是否执行了种子论文引文追踪。 |
| **Item 6** | **限定条件与理由 (Limits & Restrictions)** | 对检索年份、语言、文献类型的限定，必须在报告中说明学术理由。 | ✅ 检查 Stage 0 Grill-Me 协议快照中是否有边界理由。 |
| **Item 7** | **检索过滤式 (Search Filters)** | 若使用了经同行验证的方法学过滤器（如 JCR Q1 来源限定、MeSH 限词），需明确声明。 | ✅ 检查四层级重点期刊与来源限定代码块。 |
| **Item 8** | **前人检索参考 (Prior Strategies)** | 说明是否复用了前人经典系统评价的检索式或引物位点。 | ✅ 检查是否将前人综述作为引文追踪种子。 |
| **Item 9** | **全量检索式呈现 (Full Search Strategies)** | 必须完整呈现每个数据库所用的全部、可直接复现的布尔检索式全文。 | ✅ 检查 Stage 2 是否对 Q01–Q04 提供了无折叠的完整检索式。 |
| **Item 10** | **检索式同行评议 (Peer Review of Strategy)** | 检索策略需经过独立第三方或专业评议（如 PRESS 准则）。 | ✅ **由 Quality Gatekeeper 独立执行布尔语法与漏词审查**。 |
| **Item 11** | **分库检索命中数 (Records Found per Source)** | 必须汇报每一个检索式在每一个数据库中的原始命中数量（Raw Hits）。 | ✅ 检查检索审计日志（Search Log）中的 Hits 计数。 |
| **Item 12** | **去重软件与流程 (Managing Records & Deduplication)** | 必须详细说明去重规则（如 DOI 精确匹配、标题归一化模糊匹配）。 | ✅ 检查 Stage 4 四级级联去重算法的执行记录。 |
| **Item 13** | **检索更新频次 (Updating Searches)** | 若研究周期较长，需说明检索更新与重跑机制。 | ✅ 检查是否支持输入历史去重池进行增量更新。 |
| **Item 14** | **检索执行日期 (Dates of Searches)** | 必须精确到具体年月日。 | ✅ 检查报告元数据中的执行时间戳。 |
| **Item 15** | **纳入排除标准一致性 (Eligibility & Screening)** | 纳入与排除标准必须透明，排除文献必须附带标准代码。 | ✅ 检查 Stage 5 初筛是否严格附带分类排除理由。 |
| **Item 16** | **PRISMA 流转账本 (PRISMA Flow Diagram Data)** | 必须提供从识别、去重、初筛到纳入的四阶段完整流转数字账本。 | ✅ 检查报告中是否有完整的识别/去重/初筛/纳入账本。 |

---

## 三、质量审查员 PRISMA-S 评分卡输出模板 (Scorecard)

Quality Gatekeeper 在最终报告末尾不倾倒冗长的 16 条细则，而是输出紧凑的合规评分卡：

```markdown
### 📋 PRISMA-S 国际系统评价检索标准合规卡 (PRISMA-S Scorecard)

- **综合评级**：⭐ **PRISMA-S 16/16 完全合规 (FULLY COMPLIANT)**
- **核心合规审计项**：
  - [x] 多数据库与服务商透明声明 (Items 1-4)
  - [x] 经典综述引文双向追踪闭环 (Item 5)
  - [x] 限制条件学术理由与四层级过滤 (Items 6-7)
  - [x] 检索式可复现全文与编号审计 (Item 9)
  - [x] 质量审查员独立逻辑与语法评议 (Item 10)
  - [x] 分库命中数与四级去重算法明确 (Items 11-12)
  - [x] 精确检索执行时间戳与防老化 (Items 13-14)
  - [x] 标准初筛代码与 PRISMA 四阶段流转账本 (Items 15-16)
- **学术效力**：本检索记录符合国际权威期刊 (SCI/Q1) 及国家级学位论文“材料与方法”附录规范，可直接引用。
```

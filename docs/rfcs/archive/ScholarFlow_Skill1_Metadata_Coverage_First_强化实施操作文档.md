# ScholarFlow Skill 1 — Metadata Coverage First 强化实施操作文档
## 题录覆盖优先、全文尽力获取的增量增强方案

> 适用 Skill：`literature-discovery-acquisition`  
> 改造性质：**增量强化，不重构 Skill 1 主体架构**  
> 核心目的：在保留现有检索、去重、初筛、全文获取与质量审计体系的前提下，强化 Skill 1 对“文献题录发现完整性”的优先级管理与可审计性。
>
> 本文只解决一个核心问题：
>
> > **Skill 1 首要职责是尽量不漏文献；全文下载是次要但仍然保留的重要职责。**
>
> 不应将本次增强理解为“取消下载”或“改成纯题录工具”。

---

# 1. 是否需要重构整个 Skill 1？

不需要。

当前 Skill 1 已经具备较完整的：

```text
Stage 0 Context Resolution
↓
Adaptive Grill-Me
↓
Query Construction
↓
Multi-source Search
↓
Metadata Normalization
↓
Deduplication
↓
Screening
↓
Full-text Acquisition
↓
Quality Gate
```

现有以下部分原则上保留：

```text
✓ 多数据源检索
✓ OpenAlex / PubMed / Europe PMC / Web 搜索
✓ CNKI / 万方等受限数据库的用户辅助路径
✓ 查询式构造
✓ 术语扩展
✓ 文献类型控制
✓ 学位论文检索
✓ 去重
✓ Title/Abstract Screening
✓ OA 获取
✓ Stage 8 全文下载
✓ Stage 8B 浏览器辅助兜底
✓ Download Ledger
✓ Quality Gatekeeper
```

本轮只需要补强：

# Retrieval Completeness Layer

中文：

# 文献题录检索完整性强化层

其位置建议为：

```text
Multi-source Retrieval
        ↓
Retrieval Coverage Audit   ← 本次新增/强化
        ↓
Metadata Corpus Freeze
        ↓
Deduplication / Screening
        ↓
Full-text Acquisition
```

---

# 2. Skill 1 的两个有序目标

建议正式写入 Skill 1：

## Primary Objective — Comprehensive Metadata Discovery

> 最大化相关文献的发现率和题录覆盖率。

重点是：

```text
有哪些相关文献存在？
```

至少尽量获取：

```text
Title
Authors
Year
Journal / Conference / Institution
Abstract
Keywords
Document Type
DOI / PMID / Database ID
Source Database
Landing Page / URL
Query ID
Retrieval Status
```

---

## Secondary Objective — Best-Effort Full-Text Acquisition

> 对已经发现的文献，在合法、技术可行且资源允许范围内，尽力获取全文。

可以使用：

```text
OA repository
publisher PDF
Unpaywall
PMC
arXiv
institutional repository
browser-assisted fallback
```

但：

> **全文下载失败绝不能删除题录记录。**

---

# 3. 两个目标的优先级必须明确

正式原则：

```text
Metadata Discovery Completeness
>
Full-text Acquisition Success
```

也就是说：

如果当前仍存在明显：

```text
未检索数据库
未遍历分页
检索结果截断
题录抓取失败
```

则不能优先花大量资源反复撞：

```text
PDF 403
登录墙
验证码
WAF
JS 页面
```

---

# 4. 核心铁律

建议增加 Skill 1 的新核心原则：

> **A discovered record remains part of the candidate corpus regardless of full-text acquisition status.**

中文：

> **凡已经被可靠发现的文献题录，无论全文是否成功获取，都必须保留在候选文献集中。**

严禁：

```text
PDF unavailable
→ drop record
```

必须：

```text
Metadata found
→ candidate retained
→ fulltext status separately recorded
```

---

# 5. Discovery Success 与 Download Success 必须彻底解耦

禁止：

```text
下载成功 = 文献已发现
下载失败 = 文献不存在
```

正确模型：

```yaml
record_id: REC001

metadata_retrieval:
  status: RETRIEVED

fulltext_acquisition:
  status: AUTH_REQUIRED
```

这表示：

```text
文献被成功发现
但全文没拿到
```

两者完全可以同时成立。

---

# 6. 新增两个独立 Ledger

Skill 1 不应该只保留 Download Ledger。

建议明确分为：

# Ledger A — Retrieval Coverage Ledger

回答：

> **我到底有没有真正检索这个数据库？搜了多少？抓了多少？完整吗？**

---

# Ledger B — Full-Text Acquisition Ledger

回答：

> **已经发现的文献中，我拿到了多少全文？哪些没拿到？为什么？**

---

# 7. Retrieval Coverage Ledger

推荐字段：

| 字段 | 含义 |
|---|---|
| `source_id` | 数据源 |
| `query_id` | 检索式 ID |
| `query_text` | 实际执行检索式 |
| `execution_status` | 是否执行 |
| `reported_total_hits` | 数据库显示总命中数 |
| `metadata_records_retrieved` | 实际抓取题录数 |
| `unique_records_after_source_dedup` | 单库内部去重数 |
| `pagination_status` | 是否完成全部分页 |
| `coverage_status` | COMPLETE / PARTIAL / UNKNOWN |
| `failure_reason` | 失败原因 |
| `timestamp` | 执行时间 |
| `notes` | 补充说明 |

---

# 8. 推荐的 Retrieval Status

统一 enum：

```text
SEARCHED_COMPLETE
SEARCHED_PARTIAL
SEARCHED_WITH_ERRORS
SEARCHED_VIA_USER_EXPORT
USER_ASSISTED_REQUIRED
AUTH_REQUIRED
JS_BROWSER_REQUIRED
BOT_BLOCKED
RATE_LIMITED
TEMPORARILY_UNAVAILABLE
NOT_SEARCHED
```

---

# 9. Coverage Status

建议：

```text
COMPLETE
PARTIAL
UNKNOWN
NOT_APPLICABLE
```

---

# 10. 绝对禁止“访问失败 = 0 篇”

例如 CNKI 无法访问。

错误：

```yaml
source: CNKI
hits: 0
```

正确：

```yaml
source: CNKI
execution_status: AUTH_REQUIRED
reported_total_hits: null
metadata_records_retrieved: 0
coverage_status: UNKNOWN
```

因为：

```text
没有执行
≠
检索结果为零
```

---

# 11. “0 Results” 只有一种合法情况

只有当：

```text
数据库实际成功执行检索
+
数据库明确返回 0 条结果
```

才允许：

```yaml
execution_status: SEARCHED_COMPLETE
reported_total_hits: 0
metadata_records_retrieved: 0
coverage_status: COMPLETE
```

---

# 12. Pagination Completion 必须成为硬要求

这是防止漏文献的关键。

如果数据库显示：

```text
Total Hits = 863
```

而系统只获取：

```text
50
```

不能写：

```text
CNKI searched
```

而必须：

```yaml
source: CNKI
reported_total_hits: 863
metadata_records_retrieved: 50
pagination_status: TRUNCATED_BY_LIMIT
coverage_status: PARTIAL
```

---

# 13. 新增分页状态

```text
COMPLETE
PARTIAL
TRUNCATED_BY_LIMIT
FAILED_MIDWAY
UNKNOWN
```

---

# 14. Metadata Retrieval Rate

建议计算：

```text
Metadata Retrieval Rate
=
metadata_records_retrieved
/
reported_total_hits
```

仅当：

```text
reported_total_hits
```

已知时计算。

---

# 15. Query Coverage 也要审计

不仅记录数据库，还要记录：

```text
哪些 Query 真正执行了
```

例如：

```text
Q01 核心概念
Q02 同义词
Q03 学名/英文名
Q04 方法词
Q05 结果词
Q06 学位论文检索
```

每个 Query 都要有独立状态。

---

# 16. Query Matrix 的目标是降低漏检

推荐：

```text
Concept Bucket A
×
Concept Bucket B
×
Optional Method Bucket
×
Language Variants
×
Synonyms
```

生成多个 Query，而不是依赖一个过长检索式。

---

# 17. 中文数据库尤其需要 Query Variation

CNKI / 万方 / 维普建议至少考虑：

```text
中文正式名
中文俗名/旧名
拉丁学名/英文名
方法中文名
方法英文缩写
同义表达
学位论文过滤版本
```

---

# 18. 中文数据库的正确支持模式

建议正式定义：

## Mode A — DIRECT_METADATA_SEARCH

环境可以直接检索并读取题录。

## Mode B — BROWSER_METADATA_SEARCH

需要浏览器执行 JS / session，但可以访问搜索结果页。

## Mode C — USER_ASSISTED_EXPORT

用户自己登录数据库：

```text
执行 ScholarFlow 生成的检索式
↓
导出全部题录
↓
交给 ScholarFlow
```

ScholarFlow：

```text
解析
标准化
去重
筛选
```

---

# 19. 三种模式都可以算数据库被覆盖

前提：

```text
A/B：Agent 真正执行数据库检索
C：用户使用确认后的 Query 并导出完整结果
```

---

# 20. 不要让 OpenAlex 替代 CNKI / 万方

必须写成硬规则：

> **Cross-database discovery is complementary, not substitutive.**

即：

```text
OpenAlex
Google Scholar
Web Search
```

可能发现 CNKI 文献，但不代表完成 CNKI 数据库检索。

---

# 21. Source Coverage Matrix

建议最终报告加入：

| Source | Search Mode | Executed | Total Hits | Retrieved | Coverage |
|---|---|---:|---:|---:|---|
| OpenAlex | DIRECT_API | Yes | 315 | 315 | COMPLETE |
| PubMed | DIRECT_API | Yes | 42 | 42 | COMPLETE |
| CNKI | USER_ASSISTED_EXPORT | Yes | 138 | 138 | COMPLETE |
| Wanfang | BROWSER_METADATA_SEARCH | Yes | 91 | 74 | PARTIAL |
| VIP | — | No | — | — | NOT_SEARCHED |

---

# 22. Metadata Corpus Freeze

建议新增：

# Metadata Corpus Freeze

在开始批量下载前先固化：

```text
已发现候选文献全集
```

例如：

```text
all_candidates_raw.json
```

记录：

```yaml
metadata_corpus:
  raw_records: 623
  unique_records: 417
  sources: 6
```

---

# 23. 为什么要 Freeze

这样即使：

```text
后续 PDF 下载失败
```

也不会影响：

```text
已发现文献全集
```

---

# 24. 推荐主流程

```text
Discovery Search
↓
Coverage Ledger
↓
Metadata Corpus Freeze
↓
Cross-source Deduplication
↓
Title/Abstract Screening
↓
Candidate Priority Ranking
↓
Full-text Acquisition
```

---

# 25. Screening 默认顺序

推荐：

```text
全题录
↓
去重
↓
Title/Abstract Screening
↓
只下载 Include / Uncertain
```

这样可以减少不必要下载。

---

# 26. Full-text Acquisition 继续保留

Stage 8 不删除。

继续支持：

```text
OpenAlex OA
Unpaywall
PMC
arXiv
publisher direct PDF
institutional repositories
browser-assisted fallback
```

---

# 27. 下载状态独立

建议：

```text
FULLTEXT_AVAILABLE
OA_DOWNLOADED
BROWSER_DOWNLOADED
USER_PROVIDED
PAYWALLED
AUTH_REQUIRED
BOT_BLOCKED
JS_REQUIRED
CAJ_ONLY
DOWNLOAD_FAILED
NOT_ATTEMPTED
```

---

# 28. Full-text Acquisition Rate

```text
Full-text Acquisition Rate
=
successfully obtained fulltexts
/
records selected for acquisition
```

---

# 29. Download Rate 不能判断检索完整度

例如：

```text
CNKI metadata = 286
PDF success = 43
```

正确结论：

```text
Discovery Coverage = COMPLETE
Fulltext Acquisition = PARTIAL
```

---

# 30. 两个独立 Quality Gate

## Gate A — Discovery Coverage Gate

优先执行。

## Gate B — Full-text Acquisition Gate

后执行。

---

# 31. Gate A 检查项

```text
[ ] 所有计划数据库均有明确状态
[ ] 没有 ACCESS FAILED 被写成 0 hit
[ ] 每个 executed query 有执行记录
[ ] total hits 能取则必须记录
[ ] pagination 完整性已记录
[ ] truncation 已显式披露
[ ] metadata corpus 已冻结
[ ] 未获取全文的记录仍保留
```

---

# 32. Gate B 检查项

```text
[ ] 对 Include / Uncertain 文献尝试获取全文
[ ] OA source 优先
[ ] 下载失败有原因
[ ] 没有因为 download failure 删除 record
[ ] 下载文件与题录匹配
```

---

# 33. Skill 1 成功状态建议

建议：

```yaml
discovery_status: COMPLETE
fulltext_status: PARTIAL
overall_status: SUCCESS_WITH_ACQUISITION_GAPS
```

---

# 34. Overall Status

```text
SUCCESS
SUCCESS_WITH_RETRIEVAL_GAPS
SUCCESS_WITH_ACQUISITION_GAPS
SUCCESS_WITH_RETRIEVAL_AND_ACQUISITION_GAPS
FAILED
```

---

# 35. Retrieval Gap 与 Acquisition Gap 分开

## Retrieval Gap

意味着：

> 可能漏文献。

例如：

```text
CNKI NOT_SEARCHED
Wanfang PARTIAL
pagination truncated
```

属于高风险。

## Acquisition Gap

意味着：

> 已经知道文献存在，但没拿到全文。

属于操作限制，用户可后续手动补。

---

# 36. 风险等级

建议：

```text
Retrieval Gap = HIGH SCIENTIFIC RISK
Acquisition Gap = OPERATIONAL LIMITATION
```

---

# 37. 内部优先级策略

```text
If unresolved retrieval gaps exist:
    prioritize metadata discovery

If metadata coverage is acceptable:
    continue full-text acquisition
```

不要硬编码固定 80/20 资源比例，只保留优先级原则。

---

# 38. 对 CNKI / 万方 / 维普的强化

本轮只需要强化：

```text
Query Adapter
Metadata Retrieval Adapter
Export Adapter
Coverage Ledger
```

不需要推翻 Stage 8B。

---

# 39. CNKI 建议

保留：

```text
CNKI professional query generation
RefWorks import
thesis retrieval
```

强化：

```text
total hit logging
pagination completeness
export count reconciliation
query-level coverage
```

---

# 40. 万方建议

当前可继续依赖：

```text
RIS
EndNote
CSV/TSV
```

建议增加：

```text
Wanfang export profile
field mapping tests
title/abstract/keyword completeness checks
```

---

# 41. 维普建议

当前支持较弱。

建议至少加入：

```text
VIP Query Adapter
VIP export ingestion
VIP source normalization
coverage ledger integration
```

第一阶段不要求直接登录自动化。

---

# 42. Source Capability Registry

建议复用现有 registry 思路，但把题录检索能力也纳入：

```yaml
id: cnki

metadata_search:
  modes:
    - BROWSER_METADATA_SEARCH
    - USER_ASSISTED_EXPORT

fulltext:
  modes:
    - BROWSER_ASSISTED
    - USER_MANUAL

supports_total_hits: true
supports_abstract_metadata: true

supports_export:
  - RefWorks
  - EndNote
```

---

# 43. Capability 与 Runtime Status 分开

例如：

```yaml
source: CNKI

capability:
  metadata_search: true
  fulltext: true

runtime:
  metadata_search: USER_ASSISTED_REQUIRED
  fulltext: NOT_ATTEMPTED
```

---

# 44. Open Access 与 Runtime Accessibility 分开

例如：

```yaml
oa_status: OPEN_ACCESS
runtime_access_status: BOT_BLOCKED
```

避免：

```text
403
→ 错误认为 paywall
```

---

# 45. 下载 Retry Budget

题录检索优先情况下：

对 PDF 403 不应无限重试。

原则：

```text
Download failure
→ classify
→ move on
```

避免下载环节消耗过多资源，影响前面的题录覆盖。

---

# 46. 用户手动补全文列表

最终输出：

# Recommended Manual Download List

字段：

```text
Record ID
Title
DOI
Source
Reason needed
Fulltext status
Priority
```

---

# 47. 下载优先级

建议：

```text
P1 — Included + critical
P2 — Included
P3 — Uncertain
P4 — Excluded
```

通常：

```text
P4 不下载
```

---

# 48. Metadata 完整性检查

题录本身可能不完整。

建议：

```text
TITLE_ONLY
TITLE_AUTHOR
TITLE_ABSTRACT
FULL_METADATA
```

---

# 49. Title-only 记录不能直接丢

如果只有标题但高度相关：

```text
metadata_status = PARTIAL
```

然后尝试通过：

```text
Crossref
OpenAlex
Web search
DOI lookup
```

补齐。

---

# 50. Metadata Enrichment

例如：

```text
CNKI title-only record
↓
Cross-source metadata enrichment
↓
OpenAlex / Crossref / Web
↓
fill missing DOI / abstract
```

但必须保留 provenance：

```text
title source = CNKI
abstract source = Crossref
```

---

# 51. 不允许跨源静默覆盖冲突

例如：

```text
CNKI year = 2019
Crossref year = 2020
```

必须：

```text
CONFLICTING_METADATA
```

不能静默覆盖。

---

# 52. Cross-source Deduplication

Dedup 后要保留：

```text
source_databases
```

例如：

```json
"source_databases": [
  "CNKI",
  "Wanfang",
  "OpenAlex"
]
```

---

# 53. Source Unique Contribution

建议增加：

```text
CNKI-only records
Wanfang-only records
VIP-only records
OpenAlex-only records
```

这能直接回答：

> 某个数据库到底补了多少其他来源没找到的文献？

---

# 54. Primary Metrics

```text
Database Coverage Rate
Query Execution Rate
Metadata Retrieval Rate
Pagination Completion Rate
Unique Source Contribution
Known Seed Recovery
```

---

# 55. Secondary Metrics

```text
Fulltext Acquisition Rate
OA Acquisition Rate
Wrong-document Download Rate
Download Integrity Rate
```

---

# 56. Known Seed Recovery

如果用户提供若干已知核心文献：

```text
Skill 1 应尽量找回来
```

否则可能说明：

```text
query strategy 过窄
```

---

# 57. Saturation 不能替代数据库覆盖

即使新增文献已经很少：

```text
也不能证明没执行的数据库已经覆盖
```

例如 CNKI 根本没跑：

```text
仍是 Retrieval Gap
```

---

# 58. 建议新增模板

## `retrieval_coverage_ledger.json`

示例：

```json
{
  "source": "CNKI",
  "query_id": "Q01",
  "execution_status": "SEARCHED_COMPLETE",
  "reported_total_hits": 138,
  "metadata_records_retrieved": 138,
  "pagination_status": "COMPLETE",
  "coverage_status": "COMPLETE"
}
```

---

# 59. 建议新增 `metadata_corpus_summary.json`

例如：

```json
{
  "raw_records": 623,
  "unique_records": 417,
  "records_with_abstract": 381,
  "records_without_abstract": 36,
  "sources": {
    "OpenAlex": 230,
    "CNKI": 138,
    "Wanfang": 91
  }
}
```

---

# 60. SKILL.md 建议新增章节

建议标题：

```markdown
## Retrieval Completeness Priority
```

建议正文：

```markdown
### Ordered Objectives

Skill 1 has two ordered objectives:

1. **Primary — Comprehensive Metadata Discovery**  
   Maximize the completeness of relevant literature discovery and bibliographic metadata coverage.

2. **Secondary — Best-Effort Full-Text Acquisition**  
   Attempt to obtain accessible full text for discovered literature without compromising discovery completeness.

Full-text acquisition failure MUST NOT remove a discovered record from the candidate corpus.

Retrieval coverage and full-text acquisition coverage MUST be measured and reported separately.
```

---

# 61. Stage 3 建议新增 Stage 3B

```text
Stage 3B — Retrieval Coverage Reconciliation
```

职责：

```text
1. 对每个 Source 汇总 Query 执行状态
2. 记录 total hits
3. 对账 retrieved records
4. 判断 pagination
5. 标记 COMPLETE / PARTIAL / UNKNOWN
6. 生成 Retrieval Coverage Ledger
7. 存在严重 gap 则提示或补检
```

---

# 62. Mode-aware Coverage

## Quick

```text
coverage target = practical breadth
```

## Deep

```text
coverage target = high recall
```

## Systematic

```text
coverage target = auditable database completeness
```

无论哪种模式，都必须诚实披露数据库状态。

---

# 63. Stage 8 保留，但调整定位

写成：

```text
Stage 8 is a post-discovery acquisition layer.
```

而不是：

```text
Stage 8 defines discovery success.
```

---

# 64. Quality Gatekeeper 新增检查

建议增加：

# Retrieval Completeness Audit

包括：

```text
[ ] planned source coverage
[ ] query execution completeness
[ ] hit/retrieval reconciliation
[ ] pagination completeness
[ ] no access-failure-as-zero
[ ] no download-failure-as-record-drop
```

---

# 65. 新增 Anti-pattern

## Phantom Completeness

```text
数据库 800 hits
只摄取 50 条
却称“检索完成”
```

## Download Bias

```text
只保留下载成功的论文
```

## Access Failure = Zero

```text
CNKI 登录失败
→ CNKI hits = 0
```

## Cross-source Substitution

```text
OpenAlex 找到部分中文文献
→ 声称已完成 CNKI 检索
```

---

# 66. 新增测试建议

至少：

```text
1. test_auth_required_is_not_zero_hits
2. test_partial_pagination_is_not_complete
3. test_download_failure_keeps_candidate
4. test_metadata_corpus_frozen_before_acquisition
5. test_user_export_can_complete_source_coverage
6. test_openalex_records_do_not_mark_cnki_searched
7. test_total_hits_reconciles_with_retrieved
8. test_truncated_results_mark_partial
9. test_retrieval_and_fulltext_status_are_independent
10. test_cnki_unique_records_survive_cross_source_dedup
11. test_cnki_refworks_count_matches_export
12. test_wanfang_ris_records_preserve_source
13. test_vip_import_profile
14. test_chinese_title_only_record_is_retained
15. test_chinese_metadata_can_be_enriched_cross_source
```

---

# 67. Benchmark 建议

新增：

# Metadata Retrieval Coverage Benchmark

先做 fixture：

```text
Database reports 100
Retrieved 100
→ COMPLETE

Database reports 100
Retrieved 60
→ PARTIAL

AUTH_REQUIRED
→ UNKNOWN

0-hit successful query
→ COMPLETE + 0
```

后续真实 benchmark 再测：

```text
Known Core Paper Recovery
CNKI-only Recovery
Wanfang-only Recovery
Cross-source Unique Gain
Metadata Abstract Availability
```

---

# 68. 输出报告建议

新增：

# Retrieval Coverage Summary

例如：

```text
Metadata discovery:
OpenAlex COMPLETE
PubMed COMPLETE
CNKI COMPLETE via user export
Wanfang PARTIAL
VIP NOT_SEARCHED

Full-text acquisition:
142 / 207 Include/Uncertain records obtained
65 require user/manual access
```

---

# 69. 用户最关心的一句话

最终报告必须明确：

```text
本轮存在 / 不存在可能影响召回率的 Retrieval Gap。
```

例如：

```text
⚠ Retrieval Gap:
VIP 未执行，万方仅覆盖 74/91 条，因此当前候选集不能视为中文数据库完全覆盖。
```

---

# 70. 推荐最终交付物

```text
01_Search_Protocol.md
02_Query_Matrix.json
03_Retrieval_Coverage_Ledger.json
04_All_Raw_Metadata.json
05_Deduplicated_Candidates.json
06_Title_Abstract_Screening.csv
07_Metadata_Corpus_Summary.json
08_Fulltext_Acquisition_Ledger.md
09_Manual_Download_List.md
```

---

# 71. 哪些现有模块不要动

本次不要重写：

```text
Context Resolver
Grill-Me
Domain Lens
Query construction core
Evidence discovery schema
Dedup engine
Screening agreement
OA download
browser fallback
```

除非为了接入 Coverage 状态做最小修改。

---

# 72. 本轮最佳开发策略

建议：

# Incremental Patch

而不是：

# Skill 1 Rewrite

---

# 73. 推荐 PR 1

```text
feat(discovery): add metadata-first retrieval coverage ledger
```

包含：

```text
SKILL.md
databases_and_tools.md
retrieval ledger template
coverage evaluator
tests
```

---

# 74. 推荐 PR 2

```text
feat(discovery): add source-level completeness reconciliation
```

包含：

```text
pagination status
total hit reconciliation
query-level execution
coverage status
```

---

# 75. 推荐 PR 3

```text
feat(discovery): strengthen Chinese database metadata ingestion coverage
```

包含：

```text
CNKI export reconciliation
Wanfang profile
VIP profile
source provenance
```

---

# 76. 推荐 PR 4

```text
docs(discovery): separate retrieval gaps from acquisition gaps
```

更新：

```text
README
Quality Gatekeeper
Anti-patterns
Capability matrix
```

---

# 77. MVP 最小修复

如果暂时不想写大量代码，至少完成：

```text
1. SKILL.md 加两个有序目标
2. 增加 Retrieval Coverage Ledger
3. AUTH/BOT/NOT_SEARCHED 不再算 0 hits
4. Fulltext failure 不删除候选
5. total hits 与 retrieved count 对账
6. Quality Gate 输出 Retrieval Gap
```

---

# 78. Definition of Done

## Primary Objective

```text
[ ] Metadata discovery 被明确写为 Skill 1 首要目标
[ ] Fulltext acquisition 被明确写为次要但保留目标
```

## Coverage

```text
[ ] 每个数据库有 execution status
[ ] 每个 query 有 execution status
[ ] total hits 可获得时被记录
[ ] retrieved count 被记录
[ ] pagination 被记录
[ ] COMPLETE / PARTIAL / UNKNOWN 有严格定义
```

## Integrity

```text
[ ] AUTH_REQUIRED ≠ 0 results
[ ] NOT_SEARCHED ≠ 0 results
[ ] BOT_BLOCKED ≠ 0 results
[ ] download failure 不删除 candidate
```

## Chinese Databases

```text
[ ] CNKI user export 可以计入完整 coverage
[ ] Wanfang export 可以统一摄取
[ ] VIP 至少有标准补检/导入路径
[ ] OpenAlex 不得替代 CNKI coverage
```

## Acquisition

```text
[ ] Stage 8 保留
[ ] Stage 8B 保留
[ ] Download Ledger 保留
[ ] Acquisition Rate 独立统计
```

## Reporting

```text
[ ] Retrieval Gap 单独报告
[ ] Acquisition Gap 单独报告
[ ] 用户能一眼判断“可能漏文献”还是“只是没下载”
```

---

# 79. 最终架构

```text
                    User Research Need
                            ↓
                    Context Resolution
                            ↓
                     Adaptive Grill-Me
                            ↓
                       Query Matrix
                            ↓
                  Multi-source Retrieval
                            ↓
             Retrieval Coverage Reconciliation
                            ↓
                   Metadata Corpus Freeze
                            ↓
                 Cross-source Deduplication
                            ↓
                Title / Abstract Screening
                            ↓
                  Candidate Literature Set
                            ↓
              Best-Effort Fulltext Acquisition
                            ↓
             Fulltext Acquisition Reconciliation
                            ↓
                     Final Skill 1 Output
```

---

# 80. Skill 1 最终职责定义

建议正式写成：

> **Skill 1 exists first to minimize missed relevant literature, and second to maximize legally and technically obtainable full text.**

中文：

> **Skill 1 的首要职责是尽量减少相关文献漏检；其次是在合法、技术可行范围内尽可能获取已发现文献的全文。**

---

# 81. 三个 Skill 的职责边界

```text
Skill 1
尽量别漏文献
+
尽力拿全文

Skill 2
尽量别读错证据

Skill 3
尽量别综合过头
```

---

# 82. 最终原则

```text
1. Metadata discovery is primary; full-text acquisition is secondary.
2. A discovered record survives any full-text acquisition failure.
3. Access failure is never equivalent to zero search results.
4. Database coverage must be measured independently from cross-database discovery.
5. Partial pagination must never be reported as complete retrieval.
6. Retrieval gaps and acquisition gaps are scientifically different risks.
7. User-assisted export is a valid database coverage pathway.
8. Skill 1 should optimize recall before optimizing download success.
```

---

# 83. 最终结论

本次不需要推翻 ScholarFlow Skill 1。

当前 Skill 1 的主要架构已经具备良好基础。

真正需要强化的是：

```text
“搜到了多少”
和
“下载了多少”
```

这两个概念之间的边界。

应把 Skill 1 从：

```text
Search + Download Workflow
```

强化成：

```text
Recall-first Discovery
+
Auditable Metadata Coverage
+
Best-effort Fulltext Acquisition
```

这样既保留现有的全文获取能力，又能确保整个系统首先围绕用户最重要的问题优化：

> **不要因为访问墙、403、登录限制或下载失败，而误以为文献不存在，进而造成系统性漏检。**

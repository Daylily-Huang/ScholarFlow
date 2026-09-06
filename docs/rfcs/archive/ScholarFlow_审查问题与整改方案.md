# ScholarFlow 审查问题与整改方案

> 适用仓库：`Daylily-Huang/ScholarFlow`  
> 目标：把当前“设计理念很强”的 ScholarFlow，推进到“数据契约一致、实现与文档匹配、可验证、可测试”的科研级开源项目。  
> 本文基于当前仓库的 README、三个 Skill、角色文件与主要 Python 脚本的审查结果整理。

---

# 一、问题总览

## P0：必须优先修复

1. **三个 Skill 之间的 E1–E4 证据等级语义冲突**
2. **README 与代码存在过强承诺：`zero hallucination guarantee`、`PRISMA-S compliant` 等**
3. **`audit_claims.py` 将“关键词/数字匹配”直接升级为 `SUPPORTED / CONTRADICTORY`，证据审计强度不足**
4. **`literature-synthesis` 的共识评分仍然偏向“加权多数决”，与项目宣称的“拒绝文献民主投票”存在张力**

## P1：重要结构问题

5. **Headless Deep Search 实际主要依赖 OpenAlex，但 README 呈现得像自动多数据库系统**
6. **PDF 证据提取强调“零依赖”，但这会牺牲分页、文本提取和 Quote-First 的可靠性**
7. **`school_clustering.py` 当前更像“按已有标签分组”，还不足以称为真正的学派/范式发现**
8. **缺少统一的跨 Skill 数据契约与 schema version**
9. **缺少自动化测试、端到端测试与 Benchmark**

## P2：建议增强

10. **README 横向比较其他项目的措辞过于竞争性，缺少版本和实证依据**
11. **缺少明确的 `Validation Status / Known Limitations`**
12. **缺少能力级别标注：Protocol / Heuristic / Deterministic / Validated**
13. **缺少真正的科研性能指标：Search Recall、Evidence Precision、Citation Accuracy 等**

---

# 二、P0 问题及详细解决方案

# 1. E1–E4 在不同 Skill 中含义冲突

## 问题现状

当前 `literature-evidence-extraction` 将 E1–E4 定义为：

| Code | 含义 |
|---|---|
| E1 | EXPLICIT |
| E2 | DERIVED |
| E3 | REFERENCED |
| E4 | NR / Not Reported |

这描述的是：

> **“这个字段是如何从当前论文中得到的？”**

但 `literature-synthesis/scripts/controversy_analyzer.py` 又将 E1–E4 用作：

| Code | 含义 |
|---|---|
| E1 | 原始实验/直接数据 |
| E2 | 统计模型/经验结果 |
| E3 | Discussion 假说 |
| E4 | 专家观点/二级引用 |

这描述的是：

> **“这项证据本身有多强？”**

两者不是同一个维度。

---

## 风险

这是当前最严重的跨 Skill 数据契约问题。

例如：

```json
{
  "evidence_level": "E4"
}
```

在 Extraction 中代表：

```text
Not Reported
```

进入 Synthesis 后可能被解释成：

```text
Expert Opinion / Secondary Citation
```

这会使后续共识权重计算产生系统性错误。

---

## 解决方案

### 第一步：彻底取消跨 Skill 共享的 `E1–E4`

建议拆成两个正交变量。

### A. `support_type`

表示：

> 当前字段与论文原文之间是什么关系？

推荐：

```text
EXPLICIT
DERIVED
REFERENCED
NOT_REPORTED
```

JSON：

```json
{
  "support_type": "EXPLICIT"
}
```

---

### B. `evidence_strength`

表示：

> 该研究证据本身在综合分析中属于什么层级？

不要直接绑定固定权重。

建议：

```text
DIRECT_EMPIRICAL
MODELED_EMPIRICAL
AUTHOR_INTERPRETATION
SECONDARY_EVIDENCE
EXPERT_OPINION
UNKNOWN
```

例如：

```json
{
  "support_type": "EXPLICIT",
  "evidence_strength": "MODELED_EMPIRICAL"
}
```

意思是：

> 这个结果是论文明确报告的，而且它属于模型估计型实证证据。

两个维度完全独立。

---

## 第二步：增加 `claim_status`

建议：

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
CONTRADICTORY
AMBIGUOUS
OCR_UNCERTAIN
```

因此一个标准 Evidence Record 应类似：

```json
{
  "field": "PCR_volume",
  "value": "20 μL",
  "support_type": "EXPLICIT",
  "claim_status": "SUPPORTED",
  "source_type": "TEXT",
  "page": 4,
  "section": "Methods 2.3",
  "quote": "PCR amplification was performed in a final volume of 20 μL.",
  "evidence_strength": null
}
```

对于实验参数：

```text
evidence_strength
```

通常可以为空，因为这不是“科学证据强度”问题。

---

## 建议修改文件

至少修改：

```text
skills/literature-evidence-extraction/SKILL.md
skills/literature-evidence-extraction/references/evidence_levels_and_status.md
skills/literature-evidence-extraction/assets/evidence_extraction_schema.json

skills/literature-synthesis/SKILL.md
skills/literature-synthesis/scripts/controversy_analyzer.py
skills/literature-synthesis/references/consensus_levels_and_boundaries.md
```

---

## 验收标准

执行：

```text
Extraction → JSON → Synthesis
```

时，不允许任何字段在两个 Skill 中改变语义。

建议新增测试：

```text
tests/test_cross_skill_contract.py
```

验证：

```python
assert extraction_record["support_type"] == "NOT_REPORTED"
```

不会被 Synthesis 转换成“弱专家证据”。

---

# 2. `Zero Hallucination Guarantee` 和 `PRISMA-S Compliant` 过度承诺

## 问题现状

当前项目存在类似：

```text
零幻觉保证
PRISMA-S compliant
PaperQA2 rigor
```

的强声明。

同时 Headless 输出中存在类似：

```python
"prisma_s_compliant": True
"zero_hallucination_guarantee": True
```

这实际上是静态常量，而不是经过真实审计后计算出来的结果。

---

## 风险

对于一个强调科研证据纪律的项目，这是非常敏感的问题。

因为用户会自然理解为：

> ScholarFlow 已经被实验证明可以实现零幻觉。

或：

> 当前运行严格满足 PRISMA-S 所有适用条目。

实际上目前无法从实现或 benchmark 中验证这种结论。

---

## 解决方案

## A. 修改项目级措辞

将：

```text
Zero Hallucination Guarantee
```

改为：

```text
Hallucination-resistant by design
```

中文：

```text
面向幻觉抑制的证据约束设计
```

---

将：

```text
PRISMA-S Compliant
```

改为：

```text
PRISMA-S-informed workflow
```

或者：

```text
Supports PRISMA-S-oriented search audit
```

---

## B. 只有真正执行审计后才能输出 Compliance

设计：

```json
{
  "prisma_s_audit": {
    "status": "NOT_EVALUATED",
    "items_applicable": 0,
    "items_passed": 0,
    "items_failed": 0
  }
}
```

实际执行 Gatekeeper 后：

```json
{
  "prisma_s_audit": {
    "status": "PASS",
    "items_applicable": 14,
    "items_passed": 14,
    "items_failed": 0
  }
}
```

注意：

PRISMA-S 的适用性取决于具体工作流，不应该简单写死 `16/16`。

---

## C. 删除“零幻觉布尔字段”

不要输出：

```json
"zero_hallucination_guarantee": true
```

建议改成：

```json
"grounding_controls": {
  "quote_required": true,
  "unsupported_claims_forbidden": true,
  "nr_fallback_enabled": true
}
```

这描述的是：

> 系统采取了哪些控制措施。

而不是宣称：

> 系统绝不会错。

---

## 建议修改文件

```text
README.md
skills/literature-discovery-acquisition/scripts/agent_search.py
skills/literature-discovery-acquisition/SKILL.md
```

---

## 验收标准

全仓搜索：

```bash
grep -R "zero_hallucination_guarantee" .
grep -R "PRISMA-S Compliant" .
```

不得再出现未经审计的绝对保证。

---

# 3. `audit_claims.py` 当前不能直接充当“事实裁判”

## 问题现状

当前脚本主要依据：

- Claim 关键词是否出现在全文；
- Claim 中数字是否出现在全文；
- 最佳关键词重合页；

判断：

```text
SUPPORTED
UNSUPPORTED
CONTRADICTORY
```

这属于：

> lexical matching / heuristic retrieval

而不是严格：

> semantic claim verification

---

## 典型错误案例

论文：

```text
16S PCR volume = 20 μL
Microsatellite PCR volume = 10 μL
```

待验证 Claim：

```text
Microsatellite PCR volume was 20 μL.
```

全文中确实存在：

```text
microsatellite
PCR
20
μL
```

但 20 μL 属于另一个 assay。

简单词频和数字出现检测可能误判。

---

## 解决方案

把整个流程拆成：

```text
Evidence Candidate Retrieval
        ↓
Context Matching
        ↓
Semantic Verification
        ↓
Final Verdict
```

---

## A. 第一层：候选定位

当前 `audit_claims.py` 可以保留，但职责改为：

```text
Candidate Evidence Locator
```

输出：

```json
{
  "claim": "...",
  "candidate_passages": [
    {
      "page": 4,
      "score": 0.81,
      "text": "..."
    }
  ]
}
```

不要直接输出最终：

```text
SUPPORTED
```

---

## B. 第二层：Context Matching

必须检查以下字段是否在同一上下文内匹配：

```text
assay
target
parameter
value
unit
condition
```

例如：

```json
{
  "assay": "microsatellite PCR",
  "parameter": "reaction_volume",
  "value": 20,
  "unit": "μL"
}
```

候选句必须至少同时满足：

```text
microsatellite context
+
PCR/reaction context
+
20 μL
```

---

## C. 第三层：Evidence Auditor

由 Agent / LLM 执行语义核验：

```text
Does the quoted passage entail the claim?
```

输出：

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
CONTRADICTORY
AMBIGUOUS
```

并强制附：

```text
verbatim_quote
page
reason
```

---

## D. 数值 Claim 必须执行强校验

例如：

```text
20 μL
55 °C
0.2 mg/mL
15 loci
```

要求：

```text
value + unit + entity context
```

必须位于同一证据窗口。

不能：

> 数字在第 2 页，关键词在第 5 页 → 判定支持。

---

## 建议重构

将：

```text
audit_claims.py
```

拆为：

```text
locate_claim_evidence.py
verify_claim_context.py
```

或保留原名，但内部输出：

```text
CANDIDATE
```

而不是直接 `SUPPORTED`。

---

## 验收标准

至少加入以下 adversarial test：

### Case 1：数字出现在错误 assay

期望：

```text
UNSUPPORTED / CONTRADICTORY
```

### Case 2：方法只引用其他文献

期望：

```text
REFERENCED
```

### Case 3：Discussion 中说“may be caused by”

期望：

```text
AUTHOR_INTERPRETATION
```

不得升级为实证结论。

---

# 4. 共识算法仍然过度依赖“加权投票”

## 问题现状

当前逻辑大致为：

```text
SUPPORT 权重 / 总权重
```

然后依据阈值，例如：

```text
≥ 0.85
≥ 0.70
```

判断：

```text
Robust Consensus
Strong Consensus
Controversy
```

虽然比单纯按论文数量投票更好，但仍然是：

> weighted vote

---

## 风险

三篇来自同一数据集的小样本研究可能获得：

```text
3 × 1.0
```

而一篇大型、独立、多地点、严格验证研究只有：

```text
1 × 1.0
```

这种算法无法准确表达证据结构。

---

## 解决方案

不要再将 Evidence Strength 压缩为单一 `E1–E4 权重`。

改成多维 Evidence Appraisal。

推荐字段：

```text
directness
independence
sample_size_quality
precision
risk_of_bias
method_validation
spatial_coverage
temporal_coverage
replication
relevance_to_target
```

每项建议：

```text
HIGH
MEDIUM
LOW
UNKNOWN
```

而不是一开始就转换成数值。

例如：

```json
{
  "paper_id": "Smith2024",
  "stance": "SUPPORT",
  "appraisal": {
    "directness": "HIGH",
    "independence": "HIGH",
    "precision": "HIGH",
    "risk_of_bias": "LOW",
    "replication": "MEDIUM",
    "target_relevance": "HIGH"
  }
}
```

---

## Consensus Assessor 的逻辑

### STRONG CONSENSUS

要求：

- 多个独立数据源；
- 方法之间存在一定异质性；
- 结论方向一致；
- 没有高质量直接反证；
- 适用边界相对稳定。

---

### MODERATE CONSENSUS

- 多数高质量证据支持；
- 存在部分例外；
- 或方法/地区覆盖不足。

---

### CONDITIONAL CONSENSUS

- 不同研究结果可由边界条件解释；
- 例如地区、尺度、季节、方法。

---

### ACTIVE CONTROVERSY

- 至少两组高质量、相对独立研究存在真正冲突。

---

### INSUFFICIENT EVIDENCE

- 研究数量少；
- 独立性低；
- 方法质量差；
- 关键数据缺失。

---

## 如果仍希望保留数值

可以保留：

```text
Heuristic Evidence Balance Score
```

但必须：

1. 明确只是辅助指标；
2. 不直接决定科学共识；
3. 不使用 `Universal Consensus` 这类过强术语。

---

## 建议修改文件

```text
skills/literature-synthesis/scripts/controversy_analyzer.py
skills/literature-synthesis/references/consensus_levels_and_boundaries.md
skills/literature-synthesis/SKILL.md
```

---

# 三、P1 问题及详细解决方案

# 5. Headless Deep Search 与 README 描述存在能力落差

## 问题现状

当前自动检索主脚本主要实现：

```text
OpenAlex keyword search
OpenAlex backward citation chasing
OpenAlex forward citation chasing
```

但 README 中整体架构容易给用户一种印象：

> ScholarFlow 可以自动联合 WoS / Scopus / CNKI / 万方等数据库完成系统检索。

实际上这些受限数据库更多依赖：

```text
用户导出题录
↓
ScholarFlow ingest
```

---

## 解决方案

明确区分两类 source。

### Tier A：Machine-searchable Sources

例如：

```text
OpenAlex
PubMed（如果以后接入）
Crossref
Semantic Scholar（如果以后接入）
```

标签：

```text
AUTOMATED
```

---

### Tier B：User-assisted Restricted Sources

例如：

```text
Web of Science
Scopus
CNKI
万方
ProQuest
```

流程：

```text
ScholarFlow generates query
↓
User executes database search
↓
Export RIS/CSV/EndNote
↓
ScholarFlow ingests records
```

标签：

```text
USER_ASSISTED
```

---

## 关键修改

README 应明确写：

```text
ScholarFlow does not bypass database access controls.
Restricted commercial databases are integrated through reproducible query generation
and user-exported metadata ingestion.
```

这会显著提升可信度。

---

## Deep / Quick 模式要真正不同

当前 `--mode deep` 与 `--mode quick` 应产生真实执行差异。

建议：

### Quick

```text
1–2 query
OpenAlex
limit 10–30
no saturation
optional no snowballing
```

### Deep

```text
multiple query variants
concept expansion
deduplication
citation chasing
multiple rounds
saturation tracking
external ingestion hooks
```

不能只是：

```text
metadata["mode"] = "deep"
```

---

# 6. “零依赖 PDF”与证据可靠性冲突

## 问题现状

项目强调：

```text
Zero External Pip Dependencies
```

但 PDF 工具又需要：

```python
pypdf
```

否则 fallback 到直接解析 PDF binary stream。

对于现代 PDF：

- 压缩对象；
- 字体映射；
- 多栏；
- 图表；
- 表格；
- 特殊字符；

这种 fallback 不够可靠。

---

## 解决方案

采用 optional dependencies。

例如：

```text
ScholarFlow core
```

仍然可以：

```text
zero mandatory dependency
```

但：

```text
ScholarFlow[pdf]
```

安装：

```bash
pip install pypdf
```

或：

```bash
pip install pymupdf
```

---

## 推荐能力等级

### Level 0

```text
TXT / Markdown
```

可靠。

### Level 1

```text
PDF + pypdf
```

基础全文抽取。

### Level 2

```text
PDF + PyMuPDF / pdfplumber
```

更好的页面定位。

### Level 3

```text
OCR / scanned PDF
```

需要 OCR 工具。

---

## Skill 必须报告解析质量

例如：

```json
{
  "document_parse": {
    "parser": "pypdf",
    "page_count": 12,
    "text_extraction_status": "GOOD",
    "ocr_used": false
  }
}
```

如果 fallback：

```json
{
  "text_extraction_status": "LOW_CONFIDENCE"
}
```

此时禁止输出：

```text
page-grounded verified evidence
```

---

# 7. `school_clustering.py` 还不足以叫真正的学派发现

## 问题现状

当前脚本主要根据输入已有字段：

```text
paradigm
school_label
is_established_school
```

进行聚合。

因此：

> 学派其实是输入提前告诉脚本的。

脚本本身并没有真正从文献网络发现学派。

---

## 解决方案分两阶段

## v0.x：诚实定位

改名：

```text
school_landscape_summary.py
```

或者：

```text
paradigm_grouping.py
```

功能描述：

> Aggregate user-/agent-labeled methodological and theoretical groupings.

避免说：

> 自动发现真实学派。

---

## v1.x：真正做 School Discovery

加入：

### Citation Network

```text
paper → cited papers
```

### Co-citation

两篇文献经常一起被引用。

### Bibliographic Coupling

两篇论文引用了大量相同文献。

### Author Network

作者共同体。

### Terminology Similarity

理论关键词：

```text
niche
neutral
optimal foraging
landscape resistance
```

### Method Similarity

例如：

```text
SCR
Capwire
traditional capture-recapture
```

最终：

```text
network clustering
+
semantic grouping
+
LLM interpretation
```

再判断：

```text
ESTABLISHED SCHOOL
ANALYTICAL GROUPING
METHOD FAMILY
```

---

## `ESTABLISHED SCHOOL` 必须提高门槛

不能：

```python
any(is_established_school)
```

建议必须满足至少一种：

1. 文献自己明确使用某学派/理论传统名称；
2. 多篇独立综述承认该流派；
3. Citation / author / theory network 有稳定结构；
4. 有长期方法或理论传承。

否则：

```text
ANALYTICAL GROUPING
```

---

# 8. 缺少统一跨 Skill Contract

## 问题

当前三个 Skill 都已经有各自 JSON Schema，但缺少一个真正统一的 pipeline contract。

---

## 解决方案

新增：

```text
schemas/
```

目录。

例如：

```text
schemas/
├── literature_record.schema.json
├── evidence_record.schema.json
├── claim_record.schema.json
├── synthesis_record.schema.json
└── scholarflow_contract.md
```

---

## Literature Record

来自 Search：

```json
{
  "schema_version": "1.0",
  "record_id": "LIT0001",
  "title": "...",
  "doi": "...",
  "source_databases": ["OpenAlex"],
  "retrieval_path": "keyword_search",
  "screening_status": "INCLUDE"
}
```

---

## Evidence Record

来自 Extraction：

```json
{
  "schema_version": "1.0",
  "evidence_id": "EV0001",
  "record_id": "LIT0001",
  "field": "PCR_volume",
  "value": "20 μL",
  "support_type": "EXPLICIT",
  "quote": "...",
  "page": 4,
  "claim_status": "SUPPORTED"
}
```

---

## Claim Record

来自 Synthesis：

```json
{
  "schema_version": "1.0",
  "claim_id": "CLM0001",
  "proposition": "...",
  "evidence_ids": ["EV0001", "EV0012"],
  "stance": "SUPPORT",
  "boundary": {
    "spatial": "...",
    "temporal": "...",
    "taxonomic": "..."
  }
}
```

---

## 所有 Skill 强制包含

```text
schema_version
```

这样以后升级：

```text
1.0 → 1.1 → 2.0
```

不会 silently break。

---

# 9. 缺少 Tests 与 Benchmark

这是工程成熟度最大的差距。

## 解决方案

建立：

```text
tests/
benchmarks/
.github/workflows/
```

---

## A. 单元测试

例如：

```text
tests/test_agent_search.py
tests/test_claim_locator.py
tests/test_cross_skill_contract.py
tests/test_controversy_analyzer.py
tests/test_school_grouping.py
```

---

## B. Adversarial Tests

特别重要。

### Extraction

设计：

```text
同篇论文有两个 PCR assay
```

测试是否串值。

### Claim Audit

设计：

```text
数字存在于全文但不属于目标实验
```

### Synthesis

设计：

```text
10 篇共享数据的支持文献
vs
2 篇独立高质量反对研究
```

检查是否还会机械多数决。

---

## C. End-to-End Test

固定一个小型公开文献集：

```text
Search
↓
Extraction
↓
Synthesis
```

输出固定 artifact。

---

## D. GitHub Actions

建议：

```yaml
python 3.9
python 3.10
python 3.11
python 3.12
```

运行：

```bash
python -m unittest
```

或：

```bash
pytest
```

---

# 四、P2 问题及详细解决方案

# 10. README 中同类项目横向比较过于竞争性

## 问题

类似：

```text
项目A没有XX
项目B只是多数投票
项目C没有独立对抗
```

这种描述很容易随项目更新而过时。

---

## 解决方案

将：

```text
Feature superiority comparison
```

改成：

```text
Primary focus comparison
```

例如：

| Project | Primary Focus |
|---|---|
| PaperQA | Scientific document QA and citation-grounded RAG |
| STORM | Knowledge curation and long-form report generation |
| GPT-Researcher | General autonomous deep research |
| ChatPaper | Paper reading and academic assistance |
| ScholarFlow | Evidence lifecycle: discovery → extraction → controversy synthesis |

这样无需证明：

> 我比你多一个 feature。

---

# 11. 增加 Validation Status / Known Limitations

建议 README 增加：

```markdown
## Validation Status
```

例如：

```text
Current status: Experimental / Early-stage

Validated:
- Schema generation
- OpenAlex retrieval
- Citation snowballing
- Metadata ingestion

Heuristic:
- Relevance scoring
- Claim candidate matching
- Controversy typing
- Consensus assessment

Not yet benchmarked:
- Search recall against systematic-review gold sets
- Claim verification accuracy
- Cross-domain controversy detection
```

---

再增加：

```markdown
## Known Limitations
```

明确：

- OpenAlex coverage limitations；
- paywalled database access；
- scanned PDF parsing；
- table extraction；
- heuristic claim scoring；
- no guarantee of complete literature recall；
- no guarantee of hallucination elimination。

这反而会提高专业可信度。

---

# 12. 给每项能力标注成熟度

推荐标签：

```text
[PROTOCOL]
[DETERMINISTIC]
[HEURISTIC]
[LLM-ASSISTED]
[EXPERIMENTAL]
[VALIDATED]
```

例如：

```text
Citation snowballing — [DETERMINISTIC]
Claim context verification — [LLM-ASSISTED]
Consensus classification — [EXPERIMENTAL]
PRISMA-S checklist — [PROTOCOL]
```

用户一眼知道：

> 哪些是程序保证，哪些是 Agent 推理。

---

# 13. 建立 ScholarFlow Benchmark

这是项目下一阶段最值得做的事情。

## Benchmark 1：Literature Discovery

### 指标

```text
Recall
Precision
Unique relevant records discovered
Citation-chasing gain
Database contribution
```

Gold set：

使用公开系统综述中的已纳入论文作为 ground truth。

例如：

```text
known included papers = 100
ScholarFlow found = 87

Recall = 0.87
```

---

## Benchmark 2：Evidence Extraction

准备人工标注：

```text
PCR volume
primer
sample size
annealing temperature
main result
```

指标：

```text
Exact Match
Field Precision
Field Recall
Quote Accuracy
Page Accuracy
NR Accuracy
```

其中：

```text
NR Accuracy
```

尤其重要。

因为 ScholarFlow 的核心价值之一就是：

> 不知道时敢于输出 NR。

---

## Benchmark 3：Claim Verification

人工构造：

```text
Supported
Unsupported
Contradictory
Ambiguous
Referenced-only
```

测：

```text
Precision
Recall
F1
False-support rate
```

最重要的是：

```text
False-support rate
```

因为科研场景中：

> 错把不支持的 Claim 判为支持

比：

> 漏掉一个支持证据

通常更危险。

---

## Benchmark 4：Synthesis

可以人工建立 20–50 个争议主题。

评估：

```text
Conflict detection accuracy
Apparent-conflict rejection
Boundary-condition detection
Unsupported-school hallucination rate
Consensus calibration
```

---

# 五、推荐整改顺序

不要一次性重构全部。

建议按照以下版本推进。

---

# v0.2 — Contract Fix

优先：

1. E1–E4 语义拆分；
2. 统一 schema；
3. 去掉绝对保证；
4. 修复 README claim overreach。

这是最优先版本。

---

# v0.3 — Evidence Audit Hardening

重点：

1. `audit_claims.py` 降级为 candidate locator；
2. assay/context matching；
3. 数值 + 单位 + 实体绑定；
4. Evidence Auditor 二次核验。

---

# v0.4 — Synthesis Hardening

重点：

1. 移除单一 Evidence Weight；
2. 引入 Evidence Appraisal Matrix；
3. Consensus 改为多维判断；
4. 改造 controversy classifier。

---

# v0.5 — Validation

加入：

```text
tests/
benchmarks/
GitHub Actions
```

并发布：

```text
ScholarFlow Benchmark v0.1
```

---

# v1.0 — Stable Research Workflow

建议达到以下条件再标 `1.0`：

- 三个 Skill schema 稳定；
- CI 全通过；
- 至少 2–3 个领域 benchmark；
- Search / Extraction / Synthesis 都有公开测试结果；
- README 中所有关键能力声明都有对应实现或 benchmark 支持；
- 已知限制清楚；
- 一个完整公开案例可以端到端复现。

---

# 六、最终目标架构

建议最终形成：

```text
Research Question
       ↓
literature-discovery-acquisition
       ↓
LiteratureRecord
       ↓
literature-evidence-extraction
       ↓
EvidenceRecord
       ↓
literature-synthesis
       ↓
ClaimRecord
       ↓
ControversyMap / ConsensusMap
       ↓
Narrative Review
```

同时：

```text
Synthesis
   │
   ├── SEARCH_GAP ─────────→ Discovery
   │
   └── EXTRACTION_GAP ─────→ Extraction
```

每一次跨 Skill 交接都通过：

```text
versioned JSON schema
```

而不是依赖自然语言。

---

# 七、整改后的 ScholarFlow 应遵循的核心原则

建议把下面几条真正作为项目工程原则，而不仅仅是 README 口号。

## 1. Evidence before narrative

```text
先证据，后叙述。
```

## 2. Unknown is a valid result

```text
NR / UNKNOWN 不是失败，而是科研信息。
```

## 3. Protocol is not validation

```text
设计了严格流程 ≠ 已经证明流程可靠。
```

## 4. Heuristic is not ground truth

```text
启发式评分只能辅助，不能伪装成科学裁决。
```

## 5. Search coverage is bounded

```text
检索接近饱和 ≠ 文献绝对找全。
```

## 6. Agreement is not consensus

```text
论文数量一致 ≠ 科学共识。
```

## 7. Difference is not controversy

```text
研究结果不同 ≠ 真正学术争议。
```

## 8. Tool output must expose uncertainty

所有自动化模块必须能输出：

```text
UNKNOWN
AMBIGUOUS
NOT_EVALUATED
LOW_CONFIDENCE
```

而不是被迫给出确定答案。

---

# 八、最值得优先做的 5 个 GitHub Issue

如果要马上进入开发，建议先开以下 Issue。

## Issue 1

```text
[BREAKING] Separate extraction support type from synthesis evidence strength
```

## Issue 2

```text
[DOCS] Remove unvalidated zero-hallucination and PRISMA-S compliance claims
```

## Issue 3

```text
[CORE] Refactor claim audit into candidate retrieval + semantic verification
```

## Issue 4

```text
[SYNTHESIS] Replace fixed E1-E4 consensus weights with multidimensional evidence appraisal
```

## Issue 5

```text
[TEST] Add cross-skill contract tests and benchmark scaffold
```

---

# 九、结论

当前 ScholarFlow 最大的优势不是某一个算法，而是已经建立了一个非常清晰的科研证据链框架：

```text
发现
→ 抽取
→ 核验
→ 综合
→ 争议
→ 共识边界
→ 研究空白
```

下一阶段最重要的工作不是继续增加更多功能，而是：

```text
统一数据契约
+
收敛过强声明
+
加强证据核验
+
替换过度简化的共识算法
+
建立 tests / benchmark
```

完成这些以后，ScholarFlow 才会从：

> **“设计非常完整的科研 Agent Skill Suite”**

逐渐转变为：

> **“具有公开验证证据的科研文献智能工作流”。**


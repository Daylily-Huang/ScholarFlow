# ScholarFlow 三 Skill 全仓复审与 Contract Integration Closure 操作手册

> 仓库：`Daylily-Huang/ScholarFlow`  
> 审查基线：`main @ c90e8e2c908fb9ae5c078710a93e92c50da9542c`  
> 当前项目版本：`0.6.3`  
> 最新功能提交：`feat(extraction): implement adaptive evidence context expansion (AECE), semantic verification layer, and 16th auditor check`
>
> 本文目标：对 `literature-discovery-acquisition`、`literature-evidence-extraction`、`literature-synthesis` 做一次跨 Skill 全链路复审，并给出**增量整改手册**。
>
> 核心结论：
>
> **三个 Skill 的总体架构已经成立，不建议再次重构。下一步应做的是 `Contract Integration Closure`：让真实 producer 输出、Canonical Schema、下游 consumer 三者彻底一致。**

---

# 1. 当前总体状态

最新 GitHub Actions 已全绿：

```text
contract-validation       PASS
unittest Python 3.9       PASS
unittest Python 3.11      PASS
unittest Python 3.13      PASS
packaging                 PASS
scientific benchmarks     PASS
domain-neutrality linter  PASS
```

这说明当前仓库已经比前几个版本稳定很多。

但当前仍有一类 CI 没覆盖的问题：

```text
脚本自己能跑
+
Schema 自己能校验
≠
脚本真实输出真的符合 Schema
≠
下一 Skill 真的能直接消费该输出
```

因此本轮不应继续新增大量角色、状态或规则，而应把以下主链焊死：

```text
Discovery producer
→ LiteratureRecord
→ Extraction producer
→ EvidenceRecord
→ Evidence-to-Claim mapping
→ ClaimRecord
→ Synthesis producer
→ SynthesisRecord
```

---

# 2. 不要重新改掉的现有设计

以下设计已经正确，应保留。

## Skill 1

```text
Context-Aware Stage 0
Query Matrix
Multi-source Retrieval
Metadata Coverage First
Retrieval Coverage Ledger
Retrieval Gap / Acquisition Gap 分离
Metadata Corpus Freeze
Deduplication
Title/Abstract Screening
Stage 8 OA 下载
Stage 8B 浏览器兜底
```

## Skill 2

```text
Target Information Need
Candidate Hit ≠ Evidence
AECE
Semantic Context Verification
Claim–Evidence Alignment
Context Unit Isolation
Quote / Evidence Binding
Evidence Auditor
```

## Skill 3

```text
Claims First, Narrative Later
Controversy Mapping
Consensus Boundary
No majority voting
Devil's Advocate
School / Paradigm Mapping
SEARCH GAP
EXTRACTION GAP
```

## 全局

继续坚持：

```text
Discipline-neutral Core
+
Domain Lens on demand
```

不要重新写成某一个学科的专用系统。

---

# 3. P0 问题总表

以下问题建议在下一次真实论文 Benchmark / 对外发布前全部修复。

| ID | Skill | 问题 |
|---|---|---|
| P0-01 | Skill 1 | `ingest_external_records.py` 的真实输出不满足 Canonical `LiteratureRecord` |
| P0-02 | Skill 2 | AECE 与 Claim–Evidence Alignment 没有真正程序级串联 |
| P0-03 | Skill 2 | AECE 仍用“句子长度”等启发式替代真正语义充分性 |
| P0-04 | Skill 2 | Semantic Role 默认 `CURRENT_STUDY_OBSERVATION`，属于 fail-open |
| P0-05 | Skill 2 | 六类 TIN 未全部实现，`INTERPRETATION` 目前过度放行 |
| P0-06 | Skill 2 | 关系过程状态与 Canonical `EvidenceRecord.claim_status` 混杂 |
| P0-07 | Skill 3 | 文档称可直接消费 EvidenceRecord，但缺少 Evidence→Claim Adapter |
| P0-08 | Skill 3 | 共识准入没有消费 Skill 2 的质量门禁字段 |
| P0-09 | Skill 3 | 本地 Claim Matrix / linter 仍使用旧 E1–E4 契约 |
| P0-10 | Skill 3 | `controversy_analyzer.py` 真实输出不符合 `synthesis_record.schema.json` |
| P0-11 | 全局 | 缺少 producer→schema→consumer 的 roundtrip contract tests |

---

# 4. Skill 1：Discovery 修复

## P0-01 — External ingestion 必须真正产出 Canonical LiteratureRecord

当前文件：

```text
skills/literature-discovery-acquisition/scripts/ingest_external_records.py
schemas/literature_record.schema.json
```

当前 parser 能解析 CNKI / Wanfang / VIP / RIS / EndNote / CSV，但真实 record 存在以下合同问题：

```text
缺 schema_version
缺 record_id
year 可能为 None
ingestion_method 使用 CNKI_Refworks_Import / Wanfang_Import / VIP_Import 等非 Canonical Enum
```

Canonical LiteratureRecord 要求：

```text
schema_version
record_id
title
authors
year
source_databases
```

### 修法

不要让每个 parser 自己拼最终 Record。

增加统一函数：

```python
def finalize_literature_record(
    raw_record,
    source_database,
    ingestion_method,
):
    ...
```

最终必须注入：

```yaml
schema_version: "1.0"
record_id: "REC-xxxxxxxxxxxx"
title: ...
authors: [...]
year: ...
source_databases:
  - CNKI
ingestion_method: Refworks_Import
screening_status: Uncertain
metadata_verification_status: IMPORTED_USER_SOURCE
fulltext_verification_status: NOT_CHECKED
```

### `record_id`

必须稳定。

推荐：

```text
有 DOI：
normalized DOI

无 DOI：
normalized title + year + first author
```

再做 SHA256：

```python
record_id = "REC-" + sha256(key.encode()).hexdigest()[:12]
```

### 缺失年份

为了不立即改变 schema，可以：

```text
year = "NR"
```

不要输出 `None`。

### Source 与 ingestion method 必须正交

错误：

```yaml
ingestion_method: CNKI_Refworks_Import
```

推荐：

```yaml
source_databases: [CNKI]
ingestion_method: Refworks_Import
```

万方 RIS：

```yaml
source_databases: [Wanfang]
ingestion_method: RIS_Import
```

维普 CSV：

```yaml
source_databases: [VIP]
ingestion_method: Table_Import
```

不要把：

```text
RIS
EndNote
RefWorks
```

当成数据库来源。

### 删除题录阶段 `evidence_tier`

题录只需要：

```text
metadata_verification_status
```

不要再把 `evidence_tier=UNVERIFIED` 混入 Discovery。

---

# 5. Skill 1 P1 Hardening

## P1-01 — 每个 planned query 都要单独对账

当前 `reconcile_retrieval_coverage_ledger()` 主要按 `source_id` 对账。

应改为：

```text
(source_id, query_id)
```

作为唯一执行键。

```python
planned_keys = {(source_id, query_id)}
executed_keys = {(source_id, query_id)}
missing_keys = planned_keys - executed_keys
```

每个缺失 Query 都产生：

```text
NOT_SEARCHED
```

Query Execution Rate 使用：

```text
unique executed planned keys / planned keys
```

不能直接使用 `len(executed_entries)`。

---

## P1-02 — Pagination 默认必须 UNKNOWN

当前默认 `COMPLETE` 过度乐观。

改成：

```python
pagination_status = UNKNOWN
```

只有以下情况才允许 `COMPLETE`：

```text
API cursor 明确耗尽
最后一页明确到达
retrieved_count == reported_total_hits
用户完整导出且 exported_count == total_hits
平台返回 has_more=false
```

用户仅仅上传一个 CNKI 导出文件，不等于“完整导出”。

建议 Ledger 增加：

```yaml
completion_evidence:
  type: USER_CONFIRMED_FULL_EXPORT
  reported_total_hits: 138
  exported_records: 138
```

---

## P1-03 — Query hits 与 Unique Source Corpus 分开

多个检索式结果有大量重叠。

因此：

```text
sum(Q01 hits + Q02 hits + Q03 hits)
```

不能叫 source unique records。

建议输出：

```yaml
sum_query_reported_hits: 250
sum_query_retrieved_records: 250
unique_records_after_cross_query_dedup: 137
```

---

## P1-04 — Freeze → Dedup 必须有 Lineage

Metadata Freeze 是对的，但合法去重会减少记录数。

不能用：

```text
dedup 后数量 >= freeze 前数量
```

判断记录是否存活。

新增：

```text
Dedup Lineage Map
```

例如：

```yaml
RAW-CNKI-001:
  canonical_record_id: REC-ABC123

RAW-WANFANG-045:
  canonical_record_id: REC-ABC123
```

真正应该检查的是：

> 每个 raw record 是否能够追溯到一个 canonical record 或明确的排除/错误状态。

---

## P1-05 — 自动导入时保持真实 source provenance

如果只知道文件是 RIS，但不知道来自哪个数据库：

```yaml
source_databases:
  - UNKNOWN_EXTERNAL_SOURCE
ingestion_method: RIS_Import
```

不要：

```yaml
source_databases:
  - RIS_Import
```

---

# 6. Skill 2：Extraction P0 修复

## P0-02 — 强制串联 AECE → A2

当前：

```text
build_candidate_context_record()
```

中的：

```python
requires_claim_alignment = False
```

是固定值。

这意味着 CLAIM / RELATION 理论上可能：

```text
AECE 通过
→ promote_candidate_to_evidence()
```

却没有真正运行：

```text
verify_claim_alignment()
```

### 推荐新增

```text
skills/literature-evidence-extraction/scripts/extraction_pipeline.py
```

统一 orchestration：

```python
def process_candidate(tin, candidate, document):
    context = expand_candidate_context(...)

    semantic = semantic_context_verification(
        tin,
        context,
    )

    ccr = build_candidate_context_record(...)

    if tin["task_type"] in {
        "CLAIM",
        "RELATION",
        "COMPARISON",
    }:
        ccr["decision"]["requires_claim_alignment"] = True
        ccr["claim_alignment"] = verify_claim_alignment(...)

    return promote_with_required_gates(ccr)
```

### Hard Gate

如果：

```text
requires_claim_alignment = true
```

但：

```text
claim_alignment 缺失
```

则：

```text
REJECT
```

不能放行。

### Schema

`candidate_context_record.schema.json` 可增加条件：

```text
IF requires_claim_alignment == true
THEN claim_alignment is required
```

---

# 7. Skill 2 P0 — AECE 必须真正语义驱动

当前 `expand_candidate_context()` 有类似：

```python
if not needs_adj and len(cur_text.split()) >= 6:
    STOP_A_MEANING_RESOLVED
```

这并不能证明：

```text
上下文已经足够回答用户问题
```

一句 6 个词的句子可能仍然缺：

```text
主语
实验对象
比较组
前一句定义
时间范围
来源角色
```

### 正确设计

AECE 每扩一层后检查：

```text
Target Entity resolved?
Target Field resolved?
Subject resolved?
Predicate resolved?
Object resolved?
Context Unit resolved?
Source Role resolved?
Condition resolved?
Comparator resolved?
Negation resolved?
Modality resolved?
```

如果仍有 TIN-required slot 未解析：

```text
继续扩展
```

直到：

```text
SUFFICIENT
```

或：

```text
CONTEXT_EXHAUSTED
```

字符数/词数只能作为“可能需要扩展”的 hint，不能作为 `Meaning Resolved` 的最终依据。

---

# 8. Skill 2 P0 — Semantic Role 必须 Fail Closed

当前 `classify_semantic_role()` 无法识别时最终会落到：

```text
CURRENT_STUDY_OBSERVATION
```

这是危险的。

正确默认：

```text
UNKNOWN
```

之后只有 Agent 在读取足够上下文后才能升级：

```text
UNKNOWN
→ CURRENT_STUDY_RESULT
```

并记录 rationale。

核心规则：

```text
Unknown origin
≠
Current-study evidence
```

---

# 9. Skill 2 P0 — 六类 TIN 全部真正实现

当前定义：

```text
ATTRIBUTE
CLAIM
RELATION
COMPARISON
PROCEDURE
INTERPRETATION
```

但执行逻辑并没有完整实现所有类型。

## ATTRIBUTE

增加：

```yaml
expected_value_type:
  NUMERIC
  TEXT
  CATEGORY
  DATE
  IDENTIFIER
  STRUCTURED
  UNKNOWN
```

不能因为没有数字就默认只算部分支持。

## COMPARISON

必须验证：

```text
Target A
Comparator B
Metric
Direction
Same Context
```

例如：

```yaml
comparison:
  target: Model A
  comparator: Model B
  metric: RMSE
  metric_direction: LOWER_IS_BETTER
```

## PROCEDURE

至少验证：

```text
Procedure
Step / Action
Target / Input
Context
```

## INTERPRETATION

绝不能：

```text
INTERPRETATION → automatically ALIGNED
```

必须确认：

```text
谁在解释？
解释的命题是什么？
支持 / 反对 / 保留 / 仅介绍？
属于作者还是被引用者？
```

---

# 10. Skill 2 P0 — 状态维度保持正交

不要把：

```text
BACKGROUND_ONLY
CONTEXT_ONLY
REFERENCED_ONLY
OTHER_ENTITY_CONTEXT
```

全部塞进 `EvidenceRecord.claim_status`。

Canonical `claim_status` 保持：

```text
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
CONTRADICTORY
AMBIGUOUS
OCR_UNCERTAIN
```

其他信息独立保存：

```yaml
semantic_role: BACKGROUND
alignment_status: NOT_ALIGNED
context_sufficiency: SUFFICIENT
```

这样：

```text
Claim verification outcome
Source role
Alignment reason
Context sufficiency
```

不会互相污染。

---

# 11. Skill 2 P1 Hardening

## 11.1 中文/Unicode

当前 text segmentation 与 guard 仍偏英文。

至少支持：

```text
。 ！ ？ ；
```

并增加中文 adversarial tests：

```text
“未发现显著影响”
“并未支持该假设”
“可能与……有关”
“提示潜在机制”
“显著高于”
“显著低于”
“相比对照组”
```

不要建立巨大中文领域词库。

---

## 11.2 Context 与 Evidence Span 分开

当前 expanded context 可能直接成为：

```text
verbatim_quote
```

应拆：

```yaml
interpretation_context:
  text: "为了理解而读取的完整上下文"

evidence_span:
  text: "最终最小充分证据"
```

核心：

```text
Context can be broad.
Evidence span remains minimal sufficient.
```

---

## 11.3 source_type 正确映射

```text
TEXT_SENTENCE / PARAGRAPH / EQUATION / FOOTNOTE
→ Text

TABLE_ROW / TABLE_CELL
→ Table

FIGURE_CAPTION / FIGURE_VALUE
→ Figure

SUPPLEMENT_ENTRY
→ Supplement
```

---

## 11.4 spans 必须保存结构

不要只保存字符串。

应：

```yaml
spans:
  - text: "..."
    page: 5
    start: 321
    end: 502
    section: Results
```

这样 long-distance stitching 才能真正检查：

```text
page
offset
section
```

---

## 11.5 增加 `CONTRADICTS_TARGET`

用户目标：

```text
A increases B
```

原文：

```text
A did not increase B
```

这不是：

```text
NOT_ALIGNED
```

而是：

```text
CONTRADICTS_TARGET
```

最终映射：

```text
EvidenceRecord.claim_status = CONTRADICTORY
```

Skill 3 才能把它转成 REFUTE evidence。

---

## 11.6 Structured Context 更严格

Table 默认：

```text
title + row + column + value
```

除非表本身只有一维。

Figure 根据场景要求：

```text
caption
panel
axis
legend
value
```

建议使用：

```yaml
required_context_elements: [...]
```

而不是简单 bool。

---

# 12. Skill 3：Synthesis P0 修复

## P0-07 — EvidenceRecord → ClaimRecord Adapter

当前 `literature-synthesis/SKILL.md` 声称可以直接消费 Skill 2 的 EvidenceRecord。

但 `controversy_analyzer.py` 实际只接受：

```text
list of claims
```

或：

```json
{"claims": []}
```

EvidenceRecord 并没有：

```text
claim
stance
topic
paper_id
```

因此不能真正“直接消费”。

### 新增

```text
skills/literature-synthesis/scripts/evidence_to_claim.py
```

### 流程

```text
Synthesis Stage 0
↓
确定 Target Question / Target Proposition
↓
读取 EvidenceRecords
↓
Agent Claim Mapper 语义映射
↓
Deterministic Validator
↓
Canonical ClaimRecord
```

### 为什么不能纯规则生成 stance

因为：

```text
SUPPORT / REFUTE
```

必须相对于：

```text
当前综合命题
```

例如同一句结果：

```text
Treatment decreases mortality.
```

对于命题：

```text
Treatment is beneficial
```

可能 SUPPORT。

对于命题：

```text
Treatment has no effect
```

则 REFUTE。

所以 stance 必须由 synthesis target 决定。

---

# 13. Skill 3 P0 — Consensus Eligibility 消费上游质量字段

新增统一：

```python
evaluate_consensus_eligibility(
    claim_record,
    evidence_index,
)
```

默认要求：

```text
EvidenceRecord exists
AND
Evidence Auditor accepted
AND
context_sufficiency == SUFFICIENT
AND
claim_status is evidence-bearing
AND
evidence_strength != UNKNOWN
AND
support_type != NOT_REPORTED
```

### CONTRADICTORY

不能简单排除。

如果 EvidenceRecord：

```text
claim_status = CONTRADICTORY
```

Claim Mapper 可相对于目标命题转换为：

```text
stance = REFUTE
```

这正是争议分析需要的证据。

---

# 14. Skill 3 P0 — Canonical Claim-Evidence Matrix

当前：

```text
skills/literature-synthesis/assets/claim_evidence_matrix_schema.json
```

仍要求：

```text
claim_text
evidence_tier E1–E4
```

这与当前：

```text
schemas/claim_record.schema.json
schemas/scholarflow_contract.md v1.1
```

冲突。

当前 Contract 已经明确：

```text
support_type
≠
evidence_strength
```

不能再让 E1–E4 成为 Synthesis 必填层级。

### 推荐新增真正 Canonical Envelope

```text
schemas/claim_evidence_matrix.schema.json
```

逻辑：

```yaml
matrix_id: ...
topic: ...
claims:
  - ClaimRecord
evidence_records:
  - EvidenceRecord
```

ClaimRecord 使用：

```text
evidence_ids
```

绑定 EvidenceRecord。

---

# 15. 更新 claim_linter

当前：

```python
REQUIRED_CLAIM_KEYS = [
    "claim_id",
    "paper_id",
    "stance",
    "evidence_tier",
    "claim_text",
]
```

改成：

```python
REQUIRED_CLAIM_KEYS = [
    "claim_id",
    "paper_id",
    "stance",
    "claim",
]
```

Legacy：

```text
claim_text
E1–E4
```

只用于迁移，不作为 canonical required contract。

---

# 16. Skill 3 P0 — Synthesis 输出必须符合 Canonical Schema

当前 `controversy_analyzer.analyze()` 返回：

```text
dict keyed by topic
```

而 canonical `synthesis_record.schema.json` 要求每个 record 有：

```text
schema_version
topic
consensus_classification
controversy_diagnosis
```

此外 canonical：

```text
heuristic_balance_score
```

要求：

```text
support_pct
refute_pct
conditional_pct
neutral_pct
```

实际 analyzer 使用：

```text
SUPPORT
REFUTE
CONDITIONAL
NEUTRAL
```

### 推荐输出

```json
[
  {
    "schema_version": "1.0",
    "topic": "...",
    "total_claims": 10,
    "consensus_classification": "MODERATE_CONSENSUS",
    "heuristic_balance_score": {
      "support_pct": 70,
      "refute_pct": 20,
      "conditional_pct": 10,
      "neutral_pct": 0
    },
    "controversy_diagnosis": {
      "type": "...",
      "confidence": "...",
      "reason": "..."
    }
  }
]
```

CLI 的真实 JSON 输出逐条 validate：

```text
schemas/synthesis_record.schema.json
```

---

# 17. Skill 3 P1 Hardening

## 17.1 Strong Consensus 必须按独立证据源

当前同一篇 paper 出两个 SUPPORT claim，不能算：

```text
2 independent papers
```

至少使用：

```python
unique_papers = set(paper_id)
```

更推荐增加：

```text
independence_group_id
```

例如多个 paper 来自同一 dataset：

```yaml
independence_group_id: DATASET-001
```

只能算一个独立 evidence group。

---

## 17.2 Interpretation-only evidence 不应产生 Level 1

多个：

```text
AUTHOR_INTERPRETATION
SECONDARY_EVIDENCE
```

可以影响 narrative 和条件共识。

但单靠它们不应该升级：

```text
Strong Prevailing Consensus - Replicated Evidence
```

Level 1 至少要求：

```text
>= 2 independent evidence groups
+
存在 DIRECT_EMPIRICAL / MODELED_EMPIRICAL
```

---

## 17.3 Boundary 使用标准 Enum

不要靠英文：

```text
season
region
scale
```

判断。

增加：

```yaml
boundary_types:
  - TEMPORAL
  - SPATIAL
  - SCALE
  - POPULATION
  - METHOD
  - DATASET
  - CONDITION
```

原始文字继续保留：

```text
boundary
```

---

## 17.4 时间先后 ≠ 范式演化

`school_clustering.py` 当前可能：

```text
A 起始早
B 起始晚
→ A → B methodological evolution
```

这是过度推断。

默认只能：

```text
TEMPORAL_ORDERING
```

或：

```text
PARADIGM_SHIFT_CANDIDATE
```

只有明确文献/历史证据支持时：

```text
CONFIRMED_TRANSITION
```

---

## 17.5 Established School 必须有 provenance

不要：

```text
任何一个 is_established_school=true
→ 整组 Established School
```

增加：

```yaml
school_status_source:
  LITERATURE_EXPLICIT
  USER_CONFIRMED
  ANALYTICAL_INFERENCE
```

只有前两者可升级：

```text
ESTABLISHED_SCHOOL
```

否则：

```text
ANALYTICAL_GROUPING
```

---

# 18. 文档真实性整改

## Skill 1 Gatekeeper

删除类似：

```text
国际顶级 SCI / 硕博“免审发表级”
```

这种保证。

改成：

> PRISMA-S 对齐与检索审计能够提升检索报告的透明度和可复现性，但不保证任何期刊接收、免审或固定出版等级。

## Skill 3 Gatekeeper

当前声称：

```text
controversy_analyzer.py 自动检测并合并共享数据集伪重复
```

但当前脚本没有真实 dataset identity detection。

两种方案：

```text
A. 推荐：降低文档承诺
```

写成：

> 当输入提供 `independence_group_id` / shared dataset metadata 时，程序执行确定性去重或降权。

或者：

```text
B. 真正实现 dataset identity layer
```

不能继续声称尚未实现的能力。

## Skill 1 Gatekeeper 计数

标题仍写：

```text
六大审计维度
```

实际已有维度 1–9。

统一修正，避免文档漂移。

---

# 19. P0-11 — Producer Contract Integration Test Suite

这是本轮最重要的新测试。

新增：

```text
tests/test_cross_skill_roundtrip_contract.py
```

以及：

```text
tests/fixtures/roundtrip/
```

至少包含以下测试。

## Test A — CNKI → LiteratureRecord

```text
CNKI RefWorks fixture
→ parser
→ finalizer
→ literature_record.schema.json
PASS
```

## Test B — Wanfang / VIP → LiteratureRecord

同理逐条 strict validate。

## Test C — Retrieval Ledger

真实：

```text
build_retrieval_ledger_entry()
reconcile_retrieval_coverage_ledger()
```

validate：

```text
retrieval_coverage_ledger.schema.json
```

## Test D — AECE → EvidenceRecord

```text
Candidate
→ AECE
→ Semantic
→ Alignment
→ Promotion
```

真实输出 validate：

```text
evidence_record.schema.json
```

## Test E — Claim path cannot bypass A2

```text
CLAIM / RELATION / COMPARISON
```

没有：

```text
claim_alignment verdict
```

时：

```text
promotion blocked
```

有 PASS 后才允许。

## Test F — ExtractionResult

真实 EvidenceRecords 组装：

```text
extraction_result.schema.json
```

必须 0 error。

## Test G — Evidence → Claim

真实 adapter 输出逐条：

```text
claim_record.schema.json
```

PASS。

并验证：

```text
ClaimRecord.evidence_ids
```

全部能 resolve。

## Test H — Claim → Synthesis

真实 analyzer 输出逐条：

```text
synthesis_record.schema.json
```

PASS。

## Test I — Full Roundtrip

```text
DiscoveryResult
→ LiteratureRecord
→ ExtractionResult
→ EvidenceRecord
→ ClaimRecord
→ SynthesisRecord
```

全部 schema + cross-reference PASS。

---

# 20. 推荐 PR 顺序

不要一次提交一个巨大 PR。

## PR 1

```text
fix(discovery): canonicalize external literature producers and query coverage reconciliation
```

## PR 2

```text
fix(extraction): enforce AECE-to-claim-alignment orchestration and fail-closed semantic roles
```

## PR 3

```text
feat(extraction): complete universal TIN semantics and multilingual context guards
```

## PR 4

```text
feat(synthesis): add canonical evidence-to-claim adapter and upstream quality gate
```

## PR 5

```text
fix(synthesis): align claim matrix, linter and analyzer output with canonical schemas
```

## PR 6

```text
test(contract): add producer-to-consumer roundtrip integration suite
```

## PR 7

```text
docs: remove capability overclaims and synchronize gatekeeper contracts
```

---

# 21. 版本建议

当前仍是：

```text
0.6.3
```

完成上述 P0 后建议：

```text
0.6.4
```

推荐名称：

```text
v0.6.4 Contract Integration Closure
```

不要机械把全部 Schema 一起升级。

原则：

```text
先让 producer 适配现有 canonical schema。
```

只有真正发生契约变化时，才单独升级对应 atomic schema。

---

# 22. Definition of Done

## Skill 1

```text
[ ] CNKI producer validates LiteratureRecord
[ ] Wanfang producer validates LiteratureRecord
[ ] VIP producer validates LiteratureRecord
[ ] stable record_id
[ ] schema_version present
[ ] ingestion method canonical
[ ] source provenance preserved
[ ] every planned query reconciled
[ ] pagination default UNKNOWN
[ ] raw→canonical dedup lineage exists
```

## Skill 2

```text
[ ] CLAIM/RELATION/COMPARISON cannot bypass A2
[ ] requires_claim_alignment dynamic
[ ] Semantic Role default UNKNOWN
[ ] AECE semantic completion no longer determined by sentence length
[ ] all six TIN types implemented
[ ] INTERPRETATION no longer auto-ALIGNED
[ ] CONTRADICTS_TARGET supported
[ ] interpretation context and evidence span separated
[ ] structured spans retain location
[ ] source_type mapping correct
[ ] Chinese punctuation/negation/modality tests pass
```

## Skill 3

```text
[ ] EvidenceRecord → ClaimRecord canonical adapter exists
[ ] evidence_ids all resolvable
[ ] claim linter uses canonical ClaimRecord
[ ] synthesis no longer requires legacy E1–E4
[ ] consensus gate checks upstream evidence quality
[ ] analyzer emits canonical SynthesisRecord
[ ] strong consensus uses independent evidence groups
[ ] interpretation-only evidence cannot yield Level 1
[ ] paradigm chronology not automatically called evolution
[ ] established school requires provenance
```

## Cross-Skill

```text
[ ] Discovery producer → schema PASS
[ ] Extraction producer → schema PASS
[ ] Evidence→Claim → schema PASS
[ ] Synthesis producer → schema PASS
[ ] Full roundtrip PASS
[ ] strict schema tests 0 skipped
[ ] Python 3.9 PASS
[ ] Python 3.11 PASS
[ ] Python 3.13 PASS
[ ] packaging PASS
[ ] domain neutrality PASS
```

---

# 23. 最终目标架构

```text
User Research Question
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Skill 1 — Discovery
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Query Matrix
↓
Multi-source Retrieval
↓
Coverage Reconciliation
↓
Raw Metadata Freeze
↓
Canonical LiteratureRecord
↓
Dedup + Lineage
↓
Screening
↓
Best-effort Fulltext
        ↓
LiteratureRecord[]
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Skill 2 — Extraction
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIN
↓
Candidate Detection
↓
AECE
↓
Semantic Sufficiency
↓
Semantic Role
↓
Target Alignment
↓
Claim Alignment if required
↓
Minimal Evidence Span
↓
Evidence Verification
↓
Auditor
        ↓
EvidenceRecord[]
        ↓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Skill 3 — Synthesis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Target Proposition
↓
Evidence-to-Claim Mapping
↓
ClaimRecord[]
↓
Consensus Eligibility Gate
↓
Normalization / Clustering
↓
Controversy Diagnosis
↓
Independence-aware Weighting
↓
Consensus + Boundaries
↓
Devil's Advocate
↓
SEARCH GAP / EXTRACTION GAP
↓
Narrative
        ↓
SynthesisRecord[]
```

---

# 24. 最终 12 条系统铁律

```text
1. Access Failure ≠ Zero Results

2. Download Failure ≠ Literature Absence

3. Imported Metadata ≠ Canonical Record
   until schema validation passes

4. Candidate Hit ≠ Evidence

5. Context Length ≠ Semantic Sufficiency

6. Entity Co-occurrence ≠ Relation

7. Unknown Semantic Role ≠ Current-study Evidence

8. EvidenceRecord ≠ ClaimRecord
   until synthesis-target mapping occurs

9. Claim Count ≠ Independent Evidence Count

10. Temporal Ordering ≠ Intellectual Evolution

11. Green Unit Tests ≠ Producer Contract Closure

12. Documentation MUST NOT claim capabilities
    executable code does not actually provide
```

---

# 25. 最终结论

ScholarFlow 当前已经不是“缺核心框架”的阶段。

三个 Skill 的核心定位已经比较清楚：

```text
Skill 1：
尽量别漏文献，并尽力获取全文

Skill 2：
不仅找到文字，还要确认文字在正确上下文中真的表达用户要的信息

Skill 3：
只基于经过验证、可比较、可追溯的证据形成跨文献结论
```

下一轮最重要的是：

```text
不要再新增更多概念
↓
把已有概念变成真实程序级硬契约
↓
让每一个 producer 的真实输出通过 Canonical Schema
↓
让下一个 Skill 真正消费上一个 Skill 的质量字段
↓
用 end-to-end roundtrip test 验证
```

完成这些 P0 后，再进入：

```text
Real Paper Benchmark
```

会比继续增加新的角色、Gate 或规则更有价值。

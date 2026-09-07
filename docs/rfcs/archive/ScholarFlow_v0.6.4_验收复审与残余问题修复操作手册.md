# ScholarFlow v0.6.4 验收复审与残余问题修复操作手册
## Semantic & Audit Closure — 三 Skill 最终验收前的剩余修复

> 仓库：`Daylily-Huang/ScholarFlow`  
> 验收基线：`main @ 529feaf9a0446805618eb63decad02e3c73e8d25`  
> 当前项目版本：`0.6.4`  
> 本轮性质：验收复审，不重新设计 ScholarFlow  
> 建议修复版本：`v0.6.4.1 Semantic & Audit Closure`，或直接并入下一次 `v0.6.5`

---

# 0. 最终判断

## 结论

**大部分符合上一版整改要求，但尚不能判定“完全验收通过”。**

这次修改已经把 ScholarFlow 从“文档层的 Contract 设计”推进到了真实代码闭环：

```text
Discovery
→ LiteratureRecord
→ Extraction
→ EvidenceRecord
→ ClaimRecord
→ SynthesisRecord
```

最新 CI 已经真实跑通：

```text
contract-validation
Python 3.9
Python 3.11
Python 3.13
packaging
scientific benchmark
domain neutrality
```

严格测试结果：

```text
244 tests
0 failed
0 skipped
```

而且已经存在 A–I 的跨 Skill roundtrip：

```text
A CNKI → LiteratureRecord
B Wanfang/VIP → LiteratureRecord
C Retrieval Coverage Ledger
D AECE → EvidenceRecord
E A2 bypass prevention
F ExtractionResult
G Evidence → Claim
H Claim → Synthesis
I Full end-to-end roundtrip
```

因此：

> **v0.6.4 的“结构闭环”基本完成。**

但还剩少数会影响科研真实性的实现级问题。主要集中在：

```text
1. Skill 2 仍有 semantic sufficiency fail-open
2. Skill 2 的 Evidence Auditor 还不是最终 hard gate
3. Skill 3 的 Evidence→Claim Adapter 又把 support_type 与 evidence_strength 部分耦回去了
4. Schema 版本和唯一真源仍有少量漂移
```

不需要推翻架构，做一轮 **Semantic & Audit Closure** 即可。

---

# 1. 已确认完成的整改

## 1.1 Skill 1 — Discovery / Acquisition

已确认：

```text
[x] LiteratureRecord finalizer
[x] stable record_id
[x] schema_version
[x] source_database / ingestion_method 正交化
[x] CNKI canonical ingestion
[x] Wanfang canonical ingestion
[x] VIP canonical ingestion
[x] pagination 默认 UNKNOWN
[x] source_id + query_id 级 coverage ledger
[x] planned-but-unexecuted query → NOT_SEARCHED
[x] retrieval status 与 acquisition status 解耦
[x] dedup lineage 基础机制
```

因此 Skill 1 已经从“脚本能搜”升级到了“能产生可审计 canonical retrieval artifact”。

---

## 1.2 Skill 2 — Evidence Extraction

已确认：

```text
[x] extraction_pipeline.py orchestration
[x] AECE 接入 TIN
[x] Semantic Role 默认 UNKNOWN
[x] ATTRIBUTE / CLAIM / RELATION / COMPARISON / PROCEDURE / INTERPRETATION 分支
[x] Claim/Relation/Comparison 路径进入 A2 Claim-Evidence Alignment
[x] CONTRADICTS_TARGET
[x] 中文否定/情态/比较 guard
[x] Table/Figure structured context 基础支持
[x] Context Sufficiency 概念
[x] CandidateContextRecord
[x] EvidenceRecord promotion gate
```

架构方向正确。

---

## 1.3 Skill 3 — Synthesis

已确认：

```text
[x] evidence_to_claim.py
[x] EvidenceRecord → ClaimRecord adapter
[x] canonical claim_evidence_matrix.schema.json
[x] ClaimRecord.evidence_ids
[x] canonical SynthesisRecord transformer
[x] consensus eligibility 基础 gate
[x] UNKNOWN/NOT_REPORTED zero/blocked 机制
[x] independent evidence group 概念
[x] Strong Consensus 增加 empirical support 条件
[x] method-associated disagreement 降级为 Candidate
[x] paradigm temporal ordering 与 evolution 开始分离
```

因此原来最严重的“Skill 2 与 Skill 3 没接口”已经修复。

---

# 2. 当前剩余问题总表

## P0 — 必须修复

| ID | 模块 | 问题 |
|---|---|---|
| P0-01 | Skill 2 | AECE 在未解决语义时仍可能返回 `STOP_A_MEANING_RESOLVED` |
| P0-02 | Skill 2 | textual AECE 最终硬编码 `context_sufficiency=SUFFICIENT` |
| P0-03 | Skill 2 | `evidence_span` / `structured_spans` 在 CCR 中被丢失 |
| P0-04 | Skill 2 | long-distance audit 丢失 page/offset/section |
| P0-05 | Skill 2 | Auditor 失败后仍可能 `promoted=True` |
| P0-06 | Skill 2 | ExtractionResult 自动伪造 `checklist_passed=True` / PASS |
| P0-07 | Contract | ExtractionResult producer 输出 1.0，但 Contract 定义 1.1 |
| P0-08 | Skill 3 | `support_type → evidence_strength` 自动推断 |
| P0-09 | Skill 3 | Adapter 自动填充乐观 appraisal |
| P0-10 | Skill 3 | Adapter 把 section/default 文本伪装成 method |
| P0-11 | Skill 3 | Skill2 claim_status 直接映射 Skill3 stance，未检查是否同一命题 |
| P0-12 | Skill 3 | 没有 EvidenceIndex / audit provenance 时 eligibility 仍可放行 |
| P0-13 | Contract | canonical Claim Matrix 已存在，但 Skill-local 第二份 schema 仍在充当 active schema |

---

## P1 — 本轮 P0 后继续修

| ID | 模块 | 问题 |
|---|---|---|
| P1-01 | Skill 1 | `unique_records_after_cross_query_dedup` 名称/计算不完全一致 |
| P1-02 | Skill 1 | CLI 简单 title dedup 绕过 canonical lineage merge |
| P1-03 | Skill 2/3 | `CONTRADICTORY` 的“有效反证”与“正向确认失败”混在一起 |
| P1-04 | Skill 2/3 | `PARTIALLY_SUFFICIENT` 与 `SUFFICIENT` 的 consensus 权限未严格区分 |
| P1-05 | Skill 3 | independence 缺失时 fallback 到 paper_id，可能虚构独立重复 |
| P1-06 | Skill 3 | analyzer legacy map 仍把 EXPLICIT/DERIVED/REFERENCED 映射成 strength |
| P1-07 | Skill 3 | appraisal 子字段缺失时默认偏乐观 |
| P1-08 | Skill 3 | school provenance 缺失时 backward compatibility 仍可升级 established school |
| P1-09 | Skill 3 | school clustering 文案仍残留“演进/演化”暗示 |
| P1-10 | Skill 3 | generic warning 仍硬编码 SECR/PCR 示例 |
| P1-11 | Contract | Claim ID regex 与 ClaimRecord schema 未统一 |
| P1-12 | Benchmark | 主要仍是 synthetic / fixture，尚未进入真实论文 benchmark |

---

# 3. P0-01 — 修复 AECE 假语义完成

目标文件：

```text
skills/literature-evidence-extraction/scripts/context_expansion.py
```

当前存在等价逻辑：

```python
stop_cond = (
    StopCondition.STOP_A_MEANING_RESOLVED
    if is_complete_adj
    else StopCondition.STOP_A_MEANING_RESOLVED
)
```

也就是说：

```text
is_complete_adj = True  → STOP_A
is_complete_adj = False → STOP_A
```

这属于确定性逻辑 bug。

同时是否扩展到 paragraph 还受到：

```python
len(cur_text.split()) < 15
```

影响。

这会产生：

```text
文本已经很长
但 target entity / comparator / predicate 仍没解析
↓
因为词数 > 15 不扩展
↓
又错误 STOP_A
```

## 修改原则

```text
Context size is determined by semantic sufficiency,
not by text length.
```

## 推荐实现

```python
final_complete = False
final_missing_slots = []
final_stop_condition = None

is_complete_adj, missing_adj = check_sentence_semantic_completeness(
    cur_text,
    tin=tin,
)

if is_complete_adj:
    final_complete = True
    final_missing_slots = []
    final_stop_condition = StopCondition.STOP_A_MEANING_RESOLVED

elif max_level not in (
    ExpansionLevel.SENTENCE,
    ExpansionLevel.ADJACENT_SENTENCES,
):
    para_span = get_paragraph_span(doc_text, offset)
    cur_level = ExpansionLevel.PARAGRAPH
    cur_text = para_span["text"]

    is_complete_para, missing_para = check_sentence_semantic_completeness(
        cur_text,
        tin=tin,
    )

    final_complete = is_complete_para
    final_missing_slots = missing_para

    final_stop_condition = (
        StopCondition.STOP_A_MEANING_RESOLVED
        if is_complete_para
        else StopCondition.STOP_C_CONTEXT_EXHAUSTED
    )

else:
    final_complete = False
    final_missing_slots = missing_adj
    final_stop_condition = StopCondition.STOP_C_CONTEXT_EXHAUSTED
```

## 禁止继续使用

```python
if len(cur_text.split()) < 15:
    # semantic expansion
```

长度最多只能作为优化 hint，不能成为语义判决。

---

# 4. P0-02 — context_sufficiency 必须根据最终解析状态产生

当前 textual AECE 最终 return 仍会：

```python
"context_sufficiency": ContextSufficiency.SUFFICIENT
```

这会导致：

```text
STOP_C_CONTEXT_EXHAUSTED
missing_elements != []
context_sufficiency = SUFFICIENT
```

出现自相矛盾。

## 正确规则

```python
if final_complete:
    final_context_sufficiency = ContextSufficiency.SUFFICIENT

elif final_stop_condition == StopCondition.STOP_C_CONTEXT_EXHAUSTED:
    final_context_sufficiency = ContextSufficiency.INSUFFICIENT

else:
    final_context_sufficiency = ContextSufficiency.PARTIALLY_SUFFICIENT
```

最终 return：

```python
"context_sufficiency": final_context_sufficiency,
"missing_elements": final_missing_slots,
"stop_condition": final_stop_condition,
```

不要再用 Level-1 初始 `is_complete` 决定最终 missing fields。

---

# 5. P0-03 — Evidence Span 必须真正穿过 CCR

AECE 已经构造了：

```text
interpretation_context
evidence_span
structured_spans
```

但 `build_candidate_context_record()` 没有完整保存。

结果：

```text
AECE
  evidence_span = 最小证据句
↓
CCR
  evidence_span 丢失
↓
Promotion
  找不到 evidence_span
↓
fallback 到 context_text
```

于是：

```text
理解上下文
```

和：

```text
最小充分证据引句
```

在 integrated pipeline 中又重新合并。

## 修改 schema

文件：

```text
schemas/candidate_context_record.schema.json
```

在 `context_expansion` 中加入：

```json
"interpretation_context": {
  "type": ["object", "null"]
},
"evidence_span": {
  "type": ["object", "null"],
  "properties": {
    "text": {"type": "string"},
    "start": {"type": ["integer", "null"]},
    "end": {"type": ["integer", "null"]},
    "page": {"type": ["integer", "null"]},
    "section": {"type": ["string", "null"]}
  }
},
"structured_spans": {
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "text": {"type": "string"},
      "page": {"type": ["integer", "null"]},
      "start": {"type": ["integer", "null"]},
      "end": {"type": ["integer", "null"]},
      "offset": {"type": ["integer", "null"]},
      "section": {"type": ["string", "null"]}
    }
  }
},
"missing_elements": {
  "type": "array",
  "items": {"type": "string"}
}
```

## Builder

```python
"context_expansion": {
    "level_reached": expanded_ctx.get("level_reached"),
    "stop_condition": expanded_ctx.get("stop_condition"),
    "context_text": expanded_ctx.get("context_text", ""),
    "spans": expanded_ctx.get("spans", []),
    "interpretation_context": expanded_ctx.get("interpretation_context"),
    "evidence_span": expanded_ctx.get("evidence_span"),
    "structured_spans": expanded_ctx.get("structured_spans", []),
    "missing_elements": expanded_ctx.get("missing_elements", []),
}
```

---

# 6. P0-04 — long-distance stitching audit 必须保留位置元数据

当前 Auditor 近似：

```python
spans = candidate_context["context_expansion"]["spans"]

verify_context_coherence(
    [{"text": s} for s in spans]
)
```

这里把：

```text
page
offset
section
start/end
```

全部丢掉。

因此所谓：

```text
cross-page
cross-section
long-distance
```

在 integrated path 中实际上无法严格判断。

## 修复

```python
ctx_exp = candidate_context.get("context_expansion", {})

structured_spans = ctx_exp.get("structured_spans", [])
string_spans = ctx_exp.get("spans", [])

if len(structured_spans) > 1:
    coherent, err = verify_context_coherence(structured_spans)

elif len(string_spans) > 1:
    coherent = False
    err = (
        "Multiple evidence spans exist but page/offset/section provenance "
        "is unavailable; coherence cannot be verified."
    )
```

建议新增检查：

```text
location_traceability
```

严格区分：

```text
verified coherent
```

与：

```text
could not verify
```

未知不能默认通过。

---

# 7. P0-05 — Evidence Auditor 必须是真正最终 Hard Gate

当前：

```text
promote_candidate_to_evidence()
↓
audit_context_sufficiency()
↓
promoted = evidence_record is not None
```

所以即使 Auditor：

```text
passed = False
```

正式返回仍可能：

```text
promoted = True
```

这是典型 fail-open。

## 正确流程

```text
CCR
↓
Provisional Evidence
↓
Evidence Auditor
├─ PASS
│   ↓
│ EvidenceRecord
│
├─ PASS_WITH_DOWNGRADES
│   ↓
│ downgraded EvidenceRecord
│
└─ REJECT
    ↓
  no canonical EvidenceRecord
```

## 推荐代码

```python
provisional_record, promotion_error = promote_candidate_to_evidence(...)

if provisional_record is None:
    return {
        "candidate_context_record": ccr,
        "provisional_evidence_record": None,
        "evidence_record": None,
        "audit_result": None,
        "error": promotion_error,
        "promoted": False,
    }

audit_result = audit_context_sufficiency(
    evidence_record=provisional_record,
    candidate_context=ccr,
    doc_text=doc_text,
)

if not audit_result.get("passed", False):
    return {
        "candidate_context_record": ccr,
        "provisional_evidence_record": provisional_record,
        "evidence_record": None,
        "audit_result": audit_result,
        "error": "AUDIT_REJECTED",
        "promoted": False,
    }

return {
    "candidate_context_record": ccr,
    "provisional_evidence_record": provisional_record,
    "evidence_record": provisional_record,
    "audit_result": audit_result,
    "error": None,
    "promoted": True,
}
```

---

# 8. P0-06 — ExtractionResult 不得自动伪造审核结论

当前 envelope builder 的逻辑本质是：

```python
len(evidence_records) > 0
→ PASS

checklist_passed = True
```

而 timestamp 也是固定常量。

这不能称为 audit result。

## 新接口

```python
def build_extraction_result_envelope(
    paper_metadata,
    evidence_records,
    audit_results,
    mode="deep_evidence_extraction",
    schema_type="universal",
    rejected_candidates=None,
):
```

## 汇总规则

```python
required_failures = [
    a for a in audit_results
    if not a.get("passed", False)
]

if required_failures:
    verdict = "REJECT"
    checklist_passed = False

elif any(a.get("downgraded", False) for a in audit_results):
    verdict = "PASS_WITH_DOWNGRADES"
    checklist_passed = True

else:
    verdict = "PASS"
    checklist_passed = True
```

## 时间戳

```python
from datetime import datetime, timezone

timestamp = datetime.now(timezone.utc).isoformat()
```

## 0 条 EvidenceRecord 必须区分原因

不能统一写：

```text
PASS_WITH_DOWNGRADES
```

至少区分：

```text
A. 用户请求的字段确实 NOT_REPORTED
B. 没找到 candidate
C. candidate 找到但全部 audit rejected
```

其中 C 必须：

```text
REJECT
```

---

# 9. P0-07 — ExtractionResult 版本必须从“文档声明”变成机器硬约束

当前统一 Contract：

```text
ExtractionResult = 1.1
```

`shared/version.py`：

```python
EXTRACTION_RESULT_SCHEMA_VERSION = "1.1"
```

但 producer：

```python
"schema_version": "1.0"
```

Schema 又只是：

```json
"type": "string"
```

所以 CI 无法发现版本漂移。

## Producer

```python
from shared.version import EXTRACTION_RESULT_SCHEMA_VERSION
```

然后：

```python
"schema_version": EXTRACTION_RESULT_SCHEMA_VERSION
```

## Schema

```json
"schema_version": {
  "type": "string",
  "const": "1.1"
}
```

同理建议：

```text
discovery_result.schema.json
```

也使用：

```text
const: "1.1"
```

## 测试

```text
schema_version=1.0 → FAIL
schema_version=1.1 → PASS
```

现有 Test F 对 `1.0` 的断言必须同步更新。

---

# 10. P0-08 — 彻底禁止 support_type → evidence_strength

这是本轮最重要的 Skill 3 问题。

当前：

```text
skills/literature-synthesis/scripts/evidence_to_claim.py
```

会做：

```text
EXPLICIT   → DIRECT_EMPIRICAL
DERIVED    → MODELED_EMPIRICAL
REFERENCED → SECONDARY_EVIDENCE
```

但 canonical Contract 已经明确：

```text
support_type
≠
evidence_strength
```

## 为什么错误

`support_type=EXPLICIT` 只表示：

> 这句话/数值在原文中明确出现。

它可能属于：

```text
CURRENT_STUDY_RESULT
DISCUSSION_INTERPRETATION
THEORETICAL_ARGUMENT
DEFINITION
POLICY_ARGUMENT
LEGAL_REASONING
EXPERT_OPINION
```

因此绝不能：

```text
EXPLICIT
→ DIRECT_EMPIRICAL
```

## 正确逻辑

```python
ev_strength = evidence_record.get("evidence_strength")

if not ev_strength:
    ev_strength = "UNKNOWN"
```

如果：

```text
UNKNOWN
```

则：

```text
可以保存
可以展示
可以进入后续 appraisal
不能进入正式 consensus weighting
```

---

# 11. P0-09 — 禁止 Adapter 自动生成乐观 Appraisal

当前 Adapter 自动输出类似：

```yaml
directness: HIGH
independence: HIGH
risk_of_bias: LOW
replication: HIGH
```

这属于没有来源的质量升级。

尤其：

```text
replication=HIGH
```

不可能从单篇 EvidenceRecord 自动得出。

## 推荐默认

方案 A：

```yaml
appraisal:
  directness: UNKNOWN
  independence: UNKNOWN
  risk_of_bias: UNKNOWN
  replication: UNKNOWN
```

方案 B：

```text
不创建 appraisal
```

直到正式：

```text
Synthesis Appraisal Stage
```

执行。

建议增加 provenance：

```yaml
appraisal_provenance:
  status: UNASSESSED
  source: null
```

---

# 12. P0-10 — 不要把 section 或 placeholder 当 method

当前：

```python
method = evidence_record.get("location", {}).get("section")
```

可能出现：

```text
method = Results
```

明显不是 scientific method。

默认：

```text
Empirical measurement
```

也不是来源事实。

## 修复

```python
method = evidence_record.get("method")
```

没有：

```python
method = None
```

只有输出 Markdown/HTML 时才显示：

```text
Unspecified Method
```

不要把显示 placeholder 写入 canonical ClaimRecord。

---

# 13. P0-11 — Skill2 Claim Status 与 Skill3 Stance 之间增加 Target Compatibility Gate

当前 Adapter：

```text
SUPPORTED → SUPPORT
CONTRADICTORY → REFUTE
PARTIALLY_SUPPORTED → CONDITIONAL
```

只有一个前提：

> Skill 2 正在审核的命题，与 Skill 3 当前 synthesis target proposition 是同一命题。

否则不成立。

## 示例

Skill 2：

```text
Drug A reduces blood pressure
```

Skill 3：

```text
Drug A reduces cardiovascular mortality
```

Skill 2 即使：

```text
SUPPORTED
```

也不能自动生成：

```text
SUPPORT cardiovascular mortality
```

## 增加 provenance

Skill 2 / CCR / EvidenceRecord 保留：

```yaml
source_tin_id: TIN-001
source_target_claim: "Drug A reduces blood pressure"
```

Skill 3 输入：

```yaml
synthesis_target:
  target_proposition: "Drug A reduces cardiovascular mortality"
```

先做：

```text
SAME_PROPOSITION
COMPATIBLE_SUBCLAIM
DIFFERENT_PROPOSITION
AMBIGUOUS
```

只有：

```text
SAME_PROPOSITION
```

允许 deterministic mapping。

其他情况：

```text
COMPATIBLE_SUBCLAIM
→ semantic Claim Mapper

DIFFERENT_PROPOSITION
→ NEUTRAL / other cluster

AMBIGUOUS
→ unresolved
```

---

# 14. P0-12 — Consensus Eligibility 必须 Fail Closed

当前：

```python
evaluate_consensus_eligibility(
    claim_record,
    evidence_index=None
)
```

当 `evidence_index` 没提供时，Evidence ID 和上游 audit 其实没有被验证。

Canonical synthesis 不能这样。

## 推荐区分两种模式

### Mode A — AUDITED_CANONICAL

必须有：

```text
ClaimRecord
EvidenceIndex
Extraction audit provenance
```

缺任何一个：

```text
consensus_eligible=False
```

### Mode B — LEGACY_DISPLAY

允许没有 index，但只能：

```text
display_only=True
consensus_eligible=False
```

## Evidence strength

以下都必须禁止正式 consensus：

```text
None
""
UNKNOWN
```

## Context sufficiency

正式 full-strength consensus 默认只接受：

```text
SUFFICIENT
```

`PARTIALLY_SUFFICIENT`：

```text
允许显示
允许 conditional synthesis
不进入 full-strength consensus
```

---

# 15. P0-13 — Claim-Evidence Matrix 必须只有一个 Active Canonical Schema

当前：

```text
schemas/claim_evidence_matrix.schema.json
```

已经是正确方向。

但仓库还保留：

```text
skills/literature-synthesis/assets/claim_evidence_matrix_schema.json
```

且：

```text
SKILL.md
claim_linter.py
```

仍把 Skill-local 文件当 schema。

这会重新形成：

```text
Schema A
Schema B
```

## 推荐

删除：

```text
skills/literature-synthesis/assets/claim_evidence_matrix_schema.json
```

所有引用统一指向：

```text
schemas/claim_evidence_matrix.schema.json
```

如果需要示例：

```text
claim_evidence_matrix_example.json
```

并写：

```text
NON-CANONICAL EXAMPLE
```

---

# 16. P1-01 — Skill 1 Cross-query Unique 仍不是真正跨 Query Dedup

字段：

```text
unique_records_after_cross_query_dedup
```

当前更接近：

```text
各 query 的 unique count 求和
```

如果 Q1/Q2 返回同一篇论文，仍会重复计数。

## 方案 A — 推荐

reconciliation 接收真正 record IDs：

```python
all_record_ids = []

for query_entry in entries:
    all_record_ids.extend(query_entry.get("record_ids", []))

cross_query_unique = len(set(all_record_ids))
```

## 方案 B

如果拿不到 IDs，则重命名：

```text
sum_unique_records_after_per_query_dedup
```

禁止叫 cross-query unique。

---

# 17. P1-02 — Skill 1 CLI Dedup 必须走 Canonical Merge

当前最终 CLI 仍有简单：

```text
seen_titles
```

式 dedup。

这会绕过：

```text
merge_candidate_records()
```

里的：

```text
DOI precedence
source union
metadata enrichment
conflict detection
lineage
```

## 修复

```python
merge_result = merge_candidate_records(
    existing_records=[],
    new_records=all_records,
)

deduped_records = merge_result["merged_records"]
dedup_lineage = merge_result["dedup_lineage_map"]
```

CLI summary 增加：

```text
raw_records
canonical_records
duplicates_merged
metadata_conflicts
lineage_entries
source_distribution
```

---

# 18. P1-03 — CONTRADICTORY 应拆成两个 eligibility 维度

当前单个：

```text
is_confirmed_eligible
```

不能同时表达：

```text
是否支持目标命题
```

与：

```text
是否属于有效证据
```

明确反证：

```text
不是坏证据
```

它只是：

```text
不能作为正向确认
```

## 推荐

```yaml
positive_confirmation_eligible: false
evidence_bearing_eligible: true
```

例如：

```yaml
status: CONTRADICTORY
positive_confirmation_eligible: false
evidence_bearing_eligible: true
```

这样 Skill 3 才能保留 counterevidence。

---

# 19. P1-04 — PARTIALLY_SUFFICIENT 分层

推荐：

```text
Display:
允许

Narrative:
允许，但必须带 boundary/uncertainty

Conditional Synthesis:
允许

Full-strength Consensus:
默认不允许
```

不要把：

```text
PARTIALLY_SUFFICIENT
```

直接等价于：

```text
SUFFICIENT
```

---

# 20. P1-05 — Independence 缺失时不能默认 paper 独立

当前：

```python
independence_group_id or paper_id
```

会导致：

```text
没有 independence metadata
→ 每篇论文自动视为独立
```

但真实研究中可能存在：

```text
同一 cohort
同一 trial registry
同一数据库
同一样地
同一公开 benchmark dataset
二次分析
```

## 增加

```yaml
independence_status:
  VERIFIED
  ASSUMED
  UNKNOWN
```

Level-1 Strong Consensus 推荐要求：

```text
>= 2 VERIFIED independent evidence groups
```

如果只是：

```text
paper_id fallback
```

最高：

```text
MODERATE_CONSENSUS
```

并加：

```text
independence unverified
```

---

# 21. P1-06 — controversy_analyzer 删除 Support Type → Strength Legacy Map

当前 legacy map 仍有：

```text
EXPLICIT → DIRECT_EMPIRICAL
DERIVED → MODELED_EMPIRICAL
REFERENCED → SECONDARY_EVIDENCE
```

必须删除。

Backward compatibility 只能对真正旧版：

```text
E1
E2
E3
E4
```

做映射。

当前 canonical extraction 字段：

```text
support_type
```

不能继续冒充 scientific strength。

---

# 22. P1-07 — Appraisal 缺失不能默认“好”

当前 analyzer 内部对 appraisal 缺失项仍有偏乐观默认：

```text
directness → HIGH
independence → HIGH
risk_of_bias → LOW
replication → MEDIUM
```

这不符合 fail-closed。

## 推荐

```text
missing → UNKNOWN
```

计算 multiplier 时：

```text
UNKNOWN → 1.0 neutral
```

但同时记录：

```text
APPRAISAL_INCOMPLETE
```

未知不能直接奖励，也不能直接惩罚。

---

# 23. P1-08 — School Provenance 必须 Fail Closed

当前：

```python
is_established_school
and (
    school_status_source in (...)
    or "school_status_source" not in p
)
```

因此旧数据：

```yaml
is_established_school: true
```

但没有来源时仍能变成：

```text
ESTABLISHED SCHOOL
```

## 修复

```python
has_explicit_provenance = any(
    p.get("is_established_school", False)
    and p.get("school_status_source")
        in {"LITERATURE_EXPLICIT", "USER_CONFIRMED"}
    for p in papers
)
```

旧数据缺 provenance：

```text
LEGACY_UNVERIFIED
```

最多：

```text
ANALYTICAL GROUPING
```

不能升级为 established fact。

---

# 24. P1-09 — School 文案继续去“因果演化化”

程序已经将：

```text
shift_type = TEMPORAL_ORDERING
```

这是正确的。

但标题/文案仍有：

```text
范式演进
范式更迭
paradigm evolution
```

建议默认替换为：

```text
Paradigm Temporal Ordering
范式出现时间排序
Chronological Landscape
```

只有来源明确支持：

```text
replacement
transition
historical influence
methodological evolution
```

时才允许更强措辞。

---

# 25. P1-10 — 通用 Synthesis 不要硬编码生态/PCR例子

当前 Red-Team warning 中仍出现：

```text
样线法 vs SECR
单管 PCR vs 多管 PCR
```

对通用 Skill 不必要。

改成：

> 请进一步检查测量定义、研究对象、采样设计、比较边界、分析模型、数据独立性及时间/空间尺度是否可比。

跨学科中立性更好。

---

# 26. P1-11 — Claim ID Contract 统一

当前 linter：

```python
CLM-\d{3,}
```

但 ClaimRecord schema 只要求：

```text
string
```

且 Adapter 可能生成：

```text
CLM-EV_xxx
```

三者不一致。

## 推荐 Schema

```json
"claim_id": {
  "type": "string",
  "pattern": "^CLM-[A-Za-z0-9_.:-]+$"
}
```

## Linter

```python
CLAIM_REF_RE = re.compile(
    r"\bCLM-[A-Za-z0-9_.:-]+\b",
    re.IGNORECASE,
)
```

更稳的方案：

```text
直接读取 matrix 中全部 claim_id，
然后在 narrative 中查找这些真实 ID
```

---

# 27. P1-12 — 下一阶段必须进入 Real Paper Benchmark

现在：

```text
244 tests PASS
synthetic benchmark PASS
fixture roundtrip PASS
```

已经足够证明：

```text
代码契约
状态机
基本 guard
```

下一步不能只继续堆 synthetic unit tests。

应该进入：

# Real Paper Benchmark

---

# 28. Real Paper Benchmark — Skill 1

至少三类真实主题：

```text
A. 英文数据库主导
B. 中文数据库主导
C. 中英文混合
```

指标：

```text
Known-seed Recovery
Database Unique Contribution
Retrieval Completeness
Metadata Completeness
False Zero-result Reporting Rate
Cross-source Dedup Accuracy
```

Gold truth 由人工建立。

---

# 29. Real Paper Benchmark — Skill 2

选真实论文，必须故意包含：

```text
Introduction 中出现目标词
Discussion 推测
引用前人研究
结果表格
Figure caption
多 cohort
多 assay
多个实验条件
显式否定
Supplement
上下文歧义
```

人工标注：

```text
TRUE_EVIDENCE
CONTRADICTORY_EVIDENCE
CONTEXT_ONLY
REFERENCED_WORK
OTHER_ENTITY_CONTEXT
AMBIGUOUS
NOT_REPORTED
```

重点指标：

```text
False Promotion Rate
False Relation Rate
Wrong Context Unit Rate
Unsupported Predicate Insertion Rate
Contradictory Evidence Recall
Context Sufficiency Error Rate
```

---

# 30. Real Paper Benchmark — Skill 3

选 10–20 篇真实同主题论文。

人工建立：

```text
Target Propositions
Evidence Strength
Evidence Independence
Counterevidence
Context Boundaries
Method Comparability
```

比较 ScholarFlow：

```text
Claim Mapping Accuracy
Stance Mapping Accuracy
Consensus Eligibility Accuracy
Controversy Classification Accuracy
Boundary Preservation
Independence Handling
```

---

# 31. 必须新增的 v0.6.4.1 回归测试

建议新增：

```text
tests/test_semantic_audit_closure_v0641.py
```

---

## Test 1 — Long Sentence ≠ Meaning Resolved

```text
30+ words
但 target entity 缺失
```

期望：

```text
继续扩展
```

而不是：

```text
STOP_A
```

---

## Test 2 — Context Exhausted

最大上下文仍缺关键 slot。

期望：

```text
STOP_C_CONTEXT_EXHAUSTED
context_sufficiency = INSUFFICIENT
promoted = False
```

---

## Test 3 — Evidence Span Survives CCR

断言：

```text
AECE.evidence_span
→ CCR.evidence_span
→ EvidenceRecord.verbatim_quote
```

一致。

---

## Test 4 — Structured Spans Keep Location

构造：

```text
Page 2 evidence fragment
Page 12 evidence fragment
```

期望：

```text
coherence audit fails
```

---

## Test 5 — Auditor Reject Revokes Promotion

构造：

```text
provisional evidence valid
audit fails
```

期望：

```text
promoted == False
evidence_record is None
```

---

## Test 6 — Extraction Envelope Audit Truth

一个 audit failed：

```text
verdict = REJECT
checklist_passed = False
```

---

## Test 7 — Dynamic Timestamp

期望：

```text
不是固定 2026-09-07T00:00:00Z
```

且符合 ISO 8601。

---

## Test 8 — ExtractionResult Version Contract

```text
1.0 → schema fail
1.1 → pass
```

---

## Test 9 — Explicit ≠ Direct Empirical

输入：

```yaml
support_type: EXPLICIT
semantic_role: DISCUSSION_INTERPRETATION
evidence_strength: null
```

期望：

```text
ClaimRecord.evidence_strength = UNKNOWN
consensus_eligible = False
```

---

## Test 10 — No Fabricated Appraisal

输入没有 appraisal。

期望：

```text
appraisal absent
```

或全：

```text
UNKNOWN
```

不能自动：

```text
HIGH/HIGH/LOW/HIGH
```

---

## Test 11 — No Fabricated Method

Evidence：

```text
section = Results
method missing
```

期望：

```text
ClaimRecord.method = None
```

不能：

```text
Results
Empirical measurement
```

---

## Test 12 — Different Target Proposition

Skill 2：

```text
A reduces X
```

Skill 3：

```text
A reduces Y
```

即使 Skill 2：

```text
SUPPORTED
```

也不能自动：

```text
stance = SUPPORT
```

---

## Test 13 — Missing Evidence Index

Canonical mode：

```text
evidence_index=None
```

期望：

```text
consensus_eligible=False
```

---

## Test 14 — Partial Sufficiency

```text
PARTIALLY_SUFFICIENT
```

不得进入 full-strength consensus。

---

## Test 15 — Duplicate Active Schema Prevention

仓库测试：

```text
only schemas/ contains active canonical JSON schemas
```

Skill assets 不能再声明自己是 canonical schema。

---

## Test 16 — Unknown Independence

两篇不同 paper：

```text
independence_group_id missing
```

不能产生：

```text
Level 1 replicated strong consensus
```

---

## Test 17 — School Missing Provenance

```yaml
is_established_school: true
school_status_source: missing
```

期望：

```text
status != ESTABLISHED SCHOOL
```

---

# 32. 推荐 PR 拆分

## PR 1 — Skill 2 Semantic Sufficiency

Commit：

```text
fix(extraction): close AECE semantic sufficiency fail-open paths
```

修改：

```text
context_expansion.py
candidate_context_record.schema.json
tests
```

---

## PR 2 — Skill 2 Audit Finalization

Commit：

```text
fix(extraction): make evidence auditor a true final promotion gate
```

修改：

```text
extraction_pipeline.py
extraction_result.schema.json
tests
```

---

## PR 3 — Skill 3 Evidence Strength Orthogonality

Commit：

```text
fix(synthesis): prevent support type from inflating evidence strength
```

修改：

```text
evidence_to_claim.py
controversy_analyzer.py
tests
```

---

## PR 4 — Skill 3 Target Compatibility

Commit：

```text
feat(synthesis): add extraction-target to synthesis-target compatibility gate
```

修改：

```text
evidence_to_claim.py
claim_record.schema.json
tests
```

---

## PR 5 — Canonical Schema Single Source

Commit：

```text
refactor(contract): enforce one canonical claim matrix schema and schema versions
```

修改：

```text
schemas/
SKILL.md
claim_linter.py
shared/version.py consumers
tests
```

---

## PR 6 — Remaining Provenance Hardening

Commit：

```text
fix(synthesis): fail closed on independence and school provenance
```

---

# 33. 是否需要 Schema 升级

## ExtractionResult

不用发明新版本。

Contract 已明确：

```text
1.1
```

只需让：

```text
producer
schema const
tests
```

都真实使用：

```text
1.1
```

---

## CandidateContextRecord

如果新增：

```text
evidence_span
structured_spans
missing_elements
```

且都 optional，可暂不升级。

如果变成 required，建议独立升级。

---

## ClaimRecord

如果加入：

```text
source_tin_id
source_target_claim
stance_mapping_status
independence_status
```

建议：

```text
ClaimRecord 1.0 → 1.1
```

不要因为一个 artifact 升级，就强迫所有 schema 一起变成 1.1。

---

# 34. 推荐 ClaimRecord 1.1

```yaml
schema_version: "1.1"

claim_id: CLM-...
topic: ...

paper_id: REC-...

claim: ...

stance:
  SUPPORT
  REFUTE
  CONDITIONAL
  NEUTRAL

stance_mapping_status:
  VERIFIED_SAME_PROPOSITION
  AGENT_MAPPED
  UNRESOLVED

source_tin_id: TIN-...
source_target_claim: "..."

evidence_ids:
  - EV-...

evidence_strength:
  DIRECT_EMPIRICAL
  MODELED_EMPIRICAL
  AUTHOR_INTERPRETATION
  SECONDARY_EVIDENCE
  EXPERT_OPINION
  UNKNOWN

independence_group_id: DATASET-...
independence_status:
  VERIFIED
  ASSUMED
  UNKNOWN

appraisal:
  directness: UNKNOWN
  independence: UNKNOWN
  risk_of_bias: UNKNOWN
  replication: UNKNOWN

boundary: ...
```

关键原则：

```text
UNKNOWN
```

不是错误。

它表示：

```text
当前证据不足以安全推断。
```

这才符合 ScholarFlow 的 evidence-grounded 哲学。

---

# 35. 推荐 Skill 2 最终执行链

```text
Candidate Hit
↓
AECE Sentence
↓
Semantic sufficient?
├─ YES
│
└─ NO
   ↓
Adjacent Context
   ↓
Semantic sufficient?
├─ YES
│
└─ NO
   ↓
Paragraph / Structured Context / Context Unit
   ↓
Semantic sufficient?
├─ NO → STOP_C → INSUFFICIENT
└─ YES
↓
Semantic Role
↓
TIN Alignment
↓
Claim-Evidence Alignment when required
↓
Minimal Evidence Span
↓
Provisional Evidence
↓
Evidence Auditor
├─ PASS → EvidenceRecord
├─ DOWNGRADE → downgraded EvidenceRecord
└─ REJECT → no EvidenceRecord
```

最关键变化：

> **正式 EvidenceRecord 必须在最终 Auditor 之后产生。**

---

# 36. 推荐 Skill 3 最终执行链

```text
ExtractionResult / EvidenceRecord
↓
Verify upstream audit provenance
↓
Read source_target_claim
↓
Compare with synthesis_target
↓
Target Compatibility
├─ SAME_PROPOSITION
│  ↓
│ deterministic stance mapping
│
├─ COMPATIBLE_SUBCLAIM
│  ↓
│ semantic Claim Mapper
│
├─ DIFFERENT_PROPOSITION
│  ↓
│ other cluster / NEUTRAL
│
└─ AMBIGUOUS
   ↓
 unresolved
↓
Independent Evidence Strength Appraisal
↓
Independence Appraisal
↓
ClaimRecord
↓
Consensus Eligibility Gate
↓
Controversy / Consensus Analysis
```

---

# 37. Definition of Done

本轮 P0 修完后，要求：

## CI

```text
contract-validation = PASS
Python 3.9 = PASS
Python 3.11 = PASS
Python 3.13 = PASS
packaging = PASS
domain-neutrality = PASS
scientific benchmark = PASS
```

且：

```text
0 failed
0 skipped
```

---

## Semantic DoD

必须满足：

```text
context exhausted but SUFFICIENT = 0

audit failed but promoted EvidenceRecord = 0

support_type → evidence_strength auto mapping = 0

missing appraisal → optimistic HIGH/LOW defaults = 0

section → method inference = 0

different proposition → automatic SUPPORT/REFUTE = 0

canonical mode without evidence provenance → consensus eligible = 0

unknown independence → Level 1 strong consensus = 0

unverified school → ESTABLISHED SCHOOL = 0

duplicate active Claim Matrix schemas = 0
```

---

# 38. 本轮不要做的事

不要：

```text
继续堆更多 domain-specific ontology
```

不要：

```text
再设计第 17/18/19 个 auditor 项来掩盖 orchestration bug
```

不要：

```text
用更多关键词表解决所有 claim semantics
```

不要：

```text
为了 CI 通过放宽 schema
```

不要：

```text
重新设计三个 Skill
```

真正应该做的是：

```text
让 producer 更诚实
让 UNKNOWN 保持 UNKNOWN
让 audit 真正有否决权
让 provenance 真正贯穿
让 canonical schema 成为唯一真源
```

---

# 39. 分 Skill 最终评级

## Skill 1

当前评价：

```text
基本通过
```

只剩两个主要 P1：

```text
cross-query unique 真正计算
CLI dedup lineage
```

不需要大改。

---

## Skill 2

当前评价：

```text
架构通过
实现需最后收口
```

重点：

```text
AECE final sufficiency
Evidence Span propagation
location-aware coherence
Auditor hard gate
ExtractionResult truthful audit
```

---

## Skill 3

当前评价：

```text
接口已经闭合
但 Adapter 引入新的证据质量升格风险
```

必须优先处理：

```text
EXPLICIT ≠ DIRECT_EMPIRICAL
UNKNOWN ≠ HIGH QUALITY
section ≠ method
SUPPORTED ≠ SUPPORT
unless target proposition is actually the same
```

---

# 40. 推荐执行顺序

```text
1. 修 AECE STOP_A / context_sufficiency
↓
2. 修 Evidence Span / structured span propagation
↓
3. 把 Evidence Auditor 变成真正 final hard gate
↓
4. 修 ExtractionResult audit aggregation + timestamp + v1.1
↓
5. 删除 Skill 3 support_type → evidence_strength
↓
6. 删除自动 appraisal 与伪 method
↓
7. 增加 Target Compatibility Gate
↓
8. 合并为唯一 Claim Matrix Canonical Schema
↓
9. 修 independence / school provenance fail-open
↓
10. 增加 v0.6.4.1 semantic regression tests
↓
11. 跑全 CI
↓
12. 开始 Real Paper Benchmark
```

---

# 41. 一句话最终结论

当前版本可以准确概括为：

> **v0.6.4 已完成 ScholarFlow 的结构闭环，但还差最后一轮语义闭环与审计闭环。**

把本手册 P0 全部修完后，可以停止内部 Contract 重构，正式进入：

```text
v0.7 Real Paper Benchmark
```

阶段。

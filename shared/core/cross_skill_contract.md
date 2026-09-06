# ScholarFlow Cross-Skill Interface Contract (跨技能中立化数据与任务契约)

> **Status**: Production Interface Standard  
> **Applicability**: Handoff protocols between Discovery, Extraction, and Synthesis  
> **Core Principle**: Data exchange must use abstract, domain-neutral schemas. Discipline-specific terms are encapsulated inside metadata.

---

## 1. 技能间协作总览

```text
┌──────────────────────────────────────┐
│  Skill 1: Discovery & Acquisition    │
│  - 产出: Standardized Literature Map │
└──────────────────┬───────────────────┘
                   │ Candidate Papers (DOIs / Clean Texts / PDFs)
                   ▼
┌──────────────────────────────────────┐
│  Skill 2: Evidence Extraction        │
│  - 产出: Structured Evidence Matrix  │
│          + Accompanying JSON         │
└──────────────────┬───────────────────┘
                   │ Validated Evidence Units (E1-E4 + Context Units)
                   ▼
┌──────────────────────────────────────┐
│  Skill 3: Cross-Paper Synthesis      │
│  - 产出: Controversy Map, Consensus  │
│          Matrix, Narrative Review    │
└──────────────────┬───────────────────┘
                   │
         ┌─────────┴─────────┐
         │ Upstream Gap Loop │
         ▼                   ▼
┌─────────────────┐ ┌───────────────────┐
│ SEARCH GAP      │ │ EXTRACTION GAP    │
│ (回传给 Skill 1) │ │ (回传给 Skill 2)  │
└─────────────────┘ └───────────────────┘
```

---

## 2. 证据单元抽象契约 (Evidence Unit Schema)

无论在何种学科，从文献中提取的最小有效证据单元（Evidence Unit）必须满足以下中立数据结构：

```json
{
  "$schema": "https://scholarflow.org/schemas/v1.0/evidence_unit.json",
  "evidence_id": "EV-001",
  "source_doi": "10.1016/j.jbi.2023.104250",
  "source_title": "Comparative evaluation of deep learning architectures on clinical records",
  "domain_lens": "computer_science",
  "target_entity": "BioBERT-Large",
  "context_unit": {
    "context_type": "DATASET_SPLIT",
    "context_id": "MIMIC-III_Benchmark_v1.4",
    "parameters": {
      "split_ratio": "80/10/10",
      "batch_size": 32,
      "learning_rate": 2e-5
    }
  },
  "finding": {
    "metric_name": "Macro-F1",
    "reported_value": 0.842,
    "confidence_interval": [0.835, 0.849],
    "unit": "ratio",
    "normalized_value": 0.842,
    "verbatim_quote": "BioBERT-Large achieved a Macro-F1 score of 0.842 (95% CI: 0.835-0.849) on the test split.",
    "location": "Page 5, Section 4.2, Table 3"
  },
  "epistemic_status": {
    "support_type": "EXPLICIT",
    "evidence_strength": "DIRECT_EMPIRICAL",
    "uncertainty_status": "SUPPORTED",
    "bias_risk_rating": "LOW"
  },
  "comparability_boundaries": {
    "system_boundary": "In-domain electronic health record texts only",
    "methodological_boundary": "Fine-tuning without parameter freezing",
    "temporal_boundary": "Pre-2023 data distribution"
  }
}
```

---

## 3. 上游闭环反馈任务包契约 (Upstream Gap Payloads)

当综合分析（Synthesis）发现证据断裂或缺失时，自动触发向对应上游技能的定向派发。

### 3.1 SEARCH GAP Payload 示例 (Example: Materials Science Case)
```json
{
  "gap_type": "SEARCH_GAP",
  "triggered_by": "SYNTHESIS_CONTRADICTION_ANALYSIS",
  "hypothesis_id": "HYP-04",
  "missing_facet": "Lack of replication studies under low-temperature conditions",
  "recommended_query_elements": {
    "must_include": ["perovskite solar cells", "low-temperature", "stability degradation"],
    "time_range": "2020-2026",
    "preferred_document_types": ["Peer-reviewed Journal Articles"]
  },
  "priority": "HIGH"
}
```

### 3.2 EXTRACTION GAP Payload 示例 (Example: Biomedical Case)
```json
{
  "gap_type": "EXTRACTION_GAP",
  "triggered_by": "SYNTHESIS_APPRAISAL",
  "target_doi": "10.1038/s41586-021-03819-2",
  "missing_fields": [
    "exact_sample_size_per_arm",
    "attrition_rate",
    "baseline_confounder_distribution"
  ],
  "location_hint": "Check Supplementary Information Section 3 (Tables S4-S7)",
  "priority": "CRITICAL"
}
```

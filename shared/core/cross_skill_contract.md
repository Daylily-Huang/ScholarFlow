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
  "$schema": "schemas/evidence_record.schema.json",
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

---

## 4. 运行级执行深度与预算契约 (Execution Profile Contract)

跨技能全流水线执行中，首个技能完成 Stage 0 确认后生成统一运行级配置，固化于 `runs/<run_id>/execution_profile.json`，遵循 `schemas/execution_profile.schema.json`。

```json
{
  "schema_version": "1.0",
  "profile_version": "depth-v1",
  "run_id": "sf-run-20260908-001",
  "execution_depth": "standard",
  "interaction_mode": "interactive",
  "selection": {
    "status": "confirmed",
    "source": "current_user",
    "scope": "pipeline",
    "selected_value": "standard"
  },
  "budget": {
    "token_limit": 90000,
    "active_seconds_limit": 1800,
    "finalization_reserve_fraction": 0.1,
    "enforcement": "best_effort"
  }
}
```

### 跨技能继承守卫规则：
1. **同流水线继承**：下游技能（Extraction / Synthesis）接收到上游产物及关联的 `run_id` 时，优先自动加载并继承 `execution_profile.json`，明确提示“沿用本次流水线标准档”，严禁重复向用户发起深度追问；
2. **异任务隔离**：若下游独立启动且未携带有效运行配置，或历史配置属于不同研究任务，严禁隐式继承，必须重新进入 Stage 0 独立确认 `EXECUTION_DEPTH`；
3. **总预算唯一性**：跨阶段流转共享同一份总预算实例，阶段切换不重置总额度；预算耗尽时各阶段统一切换至收尾保护并输出 `partial` 回执与待办清单。


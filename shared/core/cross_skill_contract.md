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

## 4. 运行级执行深度与预算契约 (Run Execution Config Contract)

### 4.1 概念区分：档位预设 ≠ 已确认运行配置

| 概念 | 类 | 含义 | 可否授权执行 |
|---|---|---|---|
| **档位预设** (Tier Preset) | `ExecutionProfile` | quick / standard / deep 三档的**资源上限模板**，全局不可变 | **否**。预设只是模板，不构成任何一次运行的授权 |
| **运行配置** (Run Execution Config) | `RunExecutionConfig` | **某一次运行**经确认后的完整配置，含确认记录与阶段范围 | 仅当 `selection.status == "confirmed"` 时授权 |

> [!CAUTION]
> 严禁把档位预设直接当作已确认配置保存或传递。由预设构造运行配置时，`selection.status` 必须为 `pending`，未经显式确认不得解锁实质执行。

### 4.2 唯一 Canonical 结构

跨技能全流水线执行中，首个技能完成 Stage 0 确认后生成统一运行级配置，固化于 `runs/<run_id>/execution_profile.json`，遵循 `schemas/execution_profile.schema.json`。保存前校验、读取后校验，任一步失败即拒绝。

```json
{
  "schema_version": "1.0",
  "profile_version": "depth-v1",
  "run_id": "sf-run-20260908-001",
  "depth": "standard",
  "execution_depth": "standard",
  "name_zh": "标准档 (推荐)",
  "selection_source": "INTERACTIVE_CONFIRMED",
  "selection": {
    "status": "confirmed",
    "source": "INTERACTIVE_CONFIRMED",
    "scope": "pipeline",
    "selected_value": "standard",
    "confirmed_by": "user",
    "confirmed_at": "2026-09-08T12:00:00+00:00",
    "intent": "DECISION",
    "reason": "affirmative_user_selection",
    "notes": ""
  },
  "interaction_mode": "interactive",
  "stages": ["discovery", "extraction", "synthesis", "full_pipeline"],
  "budgets": {
    "max_search_candidates": 50,
    "snowball_rounds": 1,
    "concept_expansion_rounds": 1,
    "extraction_unit_limit": 20,
    "max_active_seconds": 1200,
    "max_model_requests": 30,
    "max_token_ceiling": 200000
  },
  "capabilities": {
    "ocr_scan_policy": "essential_tables_only",
    "figure_table_verification": "sample_crosscheck",
    "cross_validation_budget": 1,
    "spot_check_rate": 0.1,
    "devils_advocate_mode": "standard"
  },
  "enforcement": "best_effort",
  "created_at": "2026-09-08T12:00:00+00:00",
  "updated_at": "2026-09-08T12:00:00+00:00",
  "parent_run_id": null,
  "limitations": []
}
```

**字段命名唯一性**：`depth`（与别名 `execution_depth` 同值）、`selection_source`（扁平冗余字段）、`selection`（确认记录对象）、`budgets`（有效预算对象）、`capabilities`（能力开关对象）。Schema、序列化器、保存器、loader、文档与上下游一律使用这组名称，旧格式由显式转换函数迁移，不得为通过测试而放宽 `additionalProperties`。

### 4.3 跨技能继承守卫规则

1. **同流水线继承**：下游技能（Extraction / Synthesis）接收到上游产物及**同一 `run_id`** 时，可自动继承该 `execution_profile.json`，明确提示“沿用本次流水线标准档”，严禁重复向用户发起深度追问；
2. **异任务隔离**：若下游独立启动且未携带有效运行配置，**或配置的 `run_id` 与当前运行不一致**，或 `selection.status != "confirmed"`，严禁隐式继承，必须重新进入 Stage 0 独立确认 `EXECUTION_DEPTH`；
3. **证据与授权分离**：上游文献元数据、证据记录等科研证据可继续使用；但**资源授权不随之转移**。「上游文章证据可继续使用」不蕴含「上游资源授权适用于当前运行」；
4. **总预算唯一性**：跨阶段流转共享同一份总预算实例，阶段切换不重置总额度；预算耗尽时各阶段统一切换至收尾保护并输出 `partial` 回执与待办清单；
5. **运行恢复一致性**：`usage_ledger.jsonl` / `execution_receipt.json` / `execution_profile.json` 必须来自同一 run_id 的同一版本组合，禁止配置已更新而回执依旧的混合快照。

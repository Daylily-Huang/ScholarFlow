# 上游技能协同空白请求单 (Upstream Gap Dispatch Request)

> **任务标识**：`{{TASK_ID}}` | **发起时间**：`{{TIMESTAMP}}` | **发起模块**：`literature-synthesis`

---

## 1. 检索扩展请求 (To: `literature-discovery-acquisition`)

当文献综合分析发现核心证据链存在系统性文献缺失、新派系研究未召回或时间窗口断裂时，生成此请求：

### 检索请求详情
- **关联空白编号**：`GAP-DISCOVERY-{{ID}}`
- **引发争议 / 主题**：`{{CONTROVERSY_OR_TOPIC}}`
- **检索目的**：{{SEARCH_PURPOSE}}
- **目标时空 / 方法范围**：{{TARGET_SCOPE}}

```json
{
  "gap_id": "GAP-DISCOVERY-{{ID}}",
  "source_skill": "literature-synthesis",
  "target_skill": "literature-discovery-acquisition",
  "timestamp": "{{TIMESTAMP}}",
  "search_payload": {
    "recommended_queries": [
      "{{QUERY_1}}",
      "{{QUERY_2}}"
    ],
    "date_range": {
      "start_year": {{START_YEAR}},
      "end_year": {{END_YEAR}}
    },
    "must_include_keywords": [
      "{{KEYWORD_1}}",
      "{{KEYWORD_2}}"
    ],
    "must_exclude_keywords": [
      "{{EXCLUDE_1}}"
    ],
    "target_method_filters": [
      "{{METHOD_FILTER}}"
    ],
    "rationale": "{{SEARCH_RATIONALE}}"
  }
}
```

---

## 2. 深度抽取与审计回溯请求 (To: `literature-evidence-extraction`)

当两篇文献出现 Type A 实证数据冲突或 Type B 方法人工产物冲突，但现有抽取结果缺少底层实验细节（如多管 PCR 次数、探测概率公式、相机高度、引物序列）时，生成此请求：

### 抽取请求详情
- **关联空白编号**：`GAP-EXTRACTION-{{ID}}`
- **目标文献**：`{{TARGET_PAPER_ID}}` (DOI: `{{DOI}}`)
- **审计重点章节**：{{TARGET_SECTIONS}} (如：Methods & Materials, Supplementary Table S2)

```json
{
  "gap_id": "GAP-EXTRACTION-{{ID}}",
  "source_skill": "literature-synthesis",
  "target_skill": "literature-evidence-extraction",
  "timestamp": "{{TIMESTAMP}}",
  "extraction_payload": {
    "paper_id": "{{TARGET_PAPER_ID}}",
    "doi": "{{DOI}}",
    "required_evidence_tier": "E1",
    "target_parameters": [
      "{{PARAM_1}}",
      "{{PARAM_2}}"
    ],
    "target_sections": [
      "Materials and Methods",
      "Supplementary Information"
    ],
    "audit_questions": [
      "{{AUDIT_QUESTION_1}}",
      "{{AUDIT_QUESTION_2}}"
    ],
    "rationale": "{{EXTRACTION_RATIONALE}}"
  }
}
```

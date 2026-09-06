# Provenance Boundary & External Safety Classification

ScholarFlow enforces strict data boundaries between local project context and external network retrieval.

## 1. 上下文事实安全标签 (Context Safety Tagging)

Every contextual fact resolved from local project workspaces or attachments carries an `external_safe` flag:

```yaml
research_topic:
  value: "long-context transformer compression"
  external_safe: true

target_method:
  value: "quantization-aware training"
  external_safe: true

internal_sample_inventory:
  value: "Plate_20260901_Well_A1_to_H12"
  external_safe: false

local_draft_hypothesis:
  value: "Confidential preliminary findings on team dataset"
  external_safe: false
```

## 2. 工具调用边界路由 (Tool Invocation Boundary)

| 上下文类别 | 本地分析 / Project Search | 外部检索 / OpenAlex / Web |
|---|:---:|:---:|
| `external_safe == True` | 允许全面使用 | 允许用于构建检索表达式 |
| `external_safe == False` | 允许在本地环境分析 | **严格禁止向外传输或拼接进 URL** |

## 3. 防泄露自检门禁 (Leakage Prevention Audit)

Automated tests and agent runtime checks must verify that no fact flagged `external_safe == False` is exported to outbound HTTP query parameters or external search requests.

# ScholarFlow v0.6.2 Contract Closure 修复操作手册

> 仓库：`Daylily-Huang/ScholarFlow`  
> 复审基线：`main @ c0fa7a6f09161b6f34c16d29614299c2fcc2818b`  
> 当前版本：`0.6.1`  
> 建议目标版本：`0.6.2`  
> 文档目的：收口 v0.6.1 之后剩余的契约、行为与文档一致性问题，确保 ScholarFlow 在继续扩展新功能前，形成稳定、单一、可验证的内部执行协议。

---

# 一、总体结论

v0.6.1 已经完成了大部分关键整改：

- Stage 0A → Stage 0B → Stage 0C 已进入三个 Skill 主执行链；
- Context Resolution 已具备历史决策优先级、附件分类、冲突检测与项目上下文过滤；
- Domain Lens 已收敛为单一目录；
- Extraction 的 Locator / Auditor 权限已拆开；
- PDF 解析已默认 fail-closed；
- 裸 `E4` 已封禁歧义；
- Python 版本、Packaging、CI、Benchmark、Domain Neutrality Linter 均已加强；
- 当前 CI 已达到 105 tests 全通过。

因此 v0.6.2 **不建议继续新增大功能**。

本轮只做 6 件事：

```text
1. Discovery 输出契约统一
2. --no-theses 全链路一致
3. JSON Schema 真正执行验证
4. 清除 Skill-local 重复 Schema
5. Synthesis heuristic 降权限
6. README / Version / Capability 声明最终同步
```

修完这 6 项后，可以将 ScholarFlow 视为完成第一阶段的“内部契约稳定化”。

---

# 二、P0-01：统一 Discovery Headless 输出契约

## 2.1 当前问题

当前 `literature-discovery-acquisition/SKILL.md` 的 Headless 分支仍要求：

```text
输出 JSON 必须严格遵循：
assets/candidate_literature_schema.json
```

但 `agent_search.py` 当前实际输出的是 envelope：

```json
{
  "schema_version": "1.1",
  "status": "SUCCESS",
  "search_target": "...",
  "search_protocol": {},
  "candidates": [],
  "prisma_s_audit": {},
  "saturation_tracking": {},
  "grounding_controls": {},
  "metadata": {}
}
```

这显然已经不是单个 CandidateLiteratureRecord。

当前真正匹配的 canonical schema 应为：

```text
schemas/discovery_result.schema.json
```

其中：

```text
candidates[]
```

再引用：

```text
schemas/literature_record.schema.json
```

因此目前存在：

```text
文档声明
    ↓
candidate_literature_schema.json

实际代码
    ↓
DiscoveryResult envelope

canonical schema
    ↓
discovery_result.schema.json
```

三者不一致。

---

## 2.2 修改目标

形成唯一结构：

```text
agent_search.py
      ↓
DiscoveryResult
      ↓
schemas/discovery_result.schema.json
      ↓
candidates[]
      ↓
schemas/literature_record.schema.json
```

---

## 2.3 修改文件

### 文件 1

```text
skills/literature-discovery-acquisition/SKILL.md
```

将类似：

```text
硬性输出契约：输出 JSON 必须严格遵循
assets/candidate_literature_schema.json
```

改为：

```text
硬性输出契约：

1. Headless 顶层 JSON 输出必须遵循：
   schemas/discovery_result.schema.json

2. 其中 candidates[] 中的每一条文献记录必须遵循：
   schemas/literature_record.schema.json

3. Skill-local assets 中的模板不得作为 canonical executable schema。
```

建议进一步写成：

```markdown
#### 🤖 Headless / Agent 模式

Headless 输出采用两层 canonical contract：

- Envelope:
  `schemas/discovery_result.schema.json`
- Literature record:
  `schemas/literature_record.schema.json`

任何与上述 schema 不一致的输出均应由 Quality Gatekeeper REJECT。
```

---

### 文件 2

```text
skills/literature-discovery-acquisition/assets/candidate_literature_schema.json
```

推荐方案：

### 方案 A：直接删除（推荐）

如果仓库中没有旧版本兼容需求：

```text
DELETE candidate_literature_schema.json
```

理由：

- 防止形成第二套真源；
- 未来维护时只修改 `/schemas/`；
- Skill assets 只放模板、示例，不放 executable contract。

### 方案 B：保留兼容层

如果担心外部用户依赖旧文件，则：

```text
candidate_literature_schema.json
↓
legacy_candidate_literature_schema.json
```

并在文件首部 description 写明：

```text
LEGACY / DEPRECATED.
Do not use for new ScholarFlow outputs.
Canonical contract:
schemas/discovery_result.schema.json
```

---

## 2.4 新增测试

建议新增：

```python
def test_discovery_skill_points_to_canonical_schema():
    text = read("skills/literature-discovery-acquisition/SKILL.md")

    assert "schemas/discovery_result.schema.json" in text
    assert "schemas/literature_record.schema.json" in text
    assert "assets/candidate_literature_schema.json" not in text
```

如果删除旧 schema：

```python
def test_no_legacy_discovery_schema_as_active_contract():
    assert not Path(
        "skills/literature-discovery-acquisition/assets/candidate_literature_schema.json"
    ).exists()
```

---

## 2.5 验收标准

必须全部满足：

```text
[ ] SKILL.md 顶层契约指向 discovery_result.schema.json
[ ] candidates[] 明确指向 literature_record.schema.json
[ ] 旧 candidate_literature_schema 不再作为 canonical contract
[ ] 测试防止未来重新引用旧 schema
```

---

# 三、P0-02：修复 `--no-theses` 在 Snowball 路径失效的问题

## 3.1 当前问题

主查询：

```python
query_openalex_headless(
    query_str,
    include_theses=False
)
```

会排除 thesis/dissertation。

但是 Deep Search 第三阶段：

```python
run_snowball_search(top_seed["doi"], ...)
```

没有：

```python
include_theses
```

参数。

因此可能发生：

```text
Primary Search
排除 thesis
      ↓
Expansion Search
排除 thesis
      ↓
Snowball Search
重新带入 thesis
```

也就是说：

```bash
--no-theses
```

目前不是全流程约束。

---

## 3.2 修改原则

用户级检索边界一旦确定，就必须在所有 discovery path 中一致执行：

```text
keyword query
concept expansion
backward citation chasing
forward citation chasing
external ingestion
dedup
screening
```

其中 citation chasing 不能绕过用户的 document type boundary。

---

## 3.3 推荐代码改法

### Step 1：抽出统一 work-type 判断函数

在：

```text
skills/literature-discovery-acquisition/scripts/agent_search.py
```

新增：

```python
def is_thesis_work(item: dict) -> bool:
    work_type = str(item.get("type", "")).lower().strip()

    if work_type in {"dissertation", "thesis"}:
        return True

    return False
```

不要继续使用：

```python
"degree" in title
```

作为 thesis 判断。

原因：

```text
degree of freedom
degree-day
degree distribution
polynomial degree
```

等正常论文标题会被误伤。

如希望保留 title fallback，可严格限定：

```python
THESIS_TITLE_PATTERNS = [
    r"\bdoctoral thesis\b",
    r"\bphd thesis\b",
    r"\bmaster'?s thesis\b",
    r"\bdoctoral dissertation\b",
]
```

---

### Step 2：修改关键词检索

从：

```python
if not include_theses:
    if work_type in ["dissertation", "thesis"] or "thesis" in title or ...:
        continue
```

改为：

```python
if not include_theses and is_thesis_work(item):
    continue
```

---

### Step 3：修改 Snowball 函数签名

从：

```python
def run_snowball_search(seed_identifier, limit=15):
```

改为：

```python
def run_snowball_search(
    seed_identifier,
    limit=15,
    include_theses=True,
):
```

---

### Step 4：Backward filtering

在 backward references 获取后：

```python
for r_item in ref_data.get("results", []):
    if not include_theses and is_thesis_work(r_item):
        continue

    rec = parse_openalex_item(...)
```

---

### Step 5：Forward filtering

同理：

```python
for f_item in f_data.get("results", []):
    if not include_theses and is_thesis_work(f_item):
        continue

    rec = parse_openalex_item(...)
```

---

### Step 6：Deep Search 传递约束

从：

```python
snowballed = run_snowball_search(
    top_seed["doi"],
    limit=...
)
```

改为：

```python
snowballed = run_snowball_search(
    top_seed["doi"],
    limit=min(10, max(3, limit // 3)),
    include_theses=include_theses,
)
```

---

### Step 7：独立 snowball CLI 也传递

当前：

```bash
python agent_search.py --snowball DOI --no-theses
```

也应有效。

调用：

```python
run_headless_search(
    ...,
    include_theses=include_theses
)
```

最终必须进入：

```python
run_snowball_search(
    snowball_seed,
    limit=limit,
    include_theses=include_theses
)
```

---

## 3.4 新增对抗测试

必须新增：

```python
def test_no_theses_applies_to_backward_snowball():
    ...
```

```python
def test_no_theses_applies_to_forward_snowball():
    ...
```

```python
def test_deep_search_no_theses_does_not_reintroduce_thesis():
    ...
```

再增加误伤测试：

```python
def test_degree_of_freedom_article_is_not_thesis():
    item = {
        "type": "article",
        "display_name": "Degrees of freedom in statistical models"
    }

    assert is_thesis_work(item) is False
```

---

## 3.5 验收标准

```text
[ ] --no-theses 对 primary query 有效
[ ] 对 concept expansion 有效
[ ] 对 backward snowball 有效
[ ] 对 forward snowball 有效
[ ] 单独 --snowball + --no-theses 有效
[ ] “degree of freedom”等普通论文不会误删
```

---

# 四、P0-03：把 JSON Schema 测试改成“真验证”

## 4.1 当前问题

当前测试名虽然叫：

```text
test_discovery_result_validates_schema
```

但核心只是：

```python
for req in schema["required"]:
    self.assertIn(req, sample_payload)
```

这只能检查：

```text
required key 是否存在
```

无法检查：

- nested field type；
- enum；
- `$ref`；
- number/string mismatch；
- invalid record；
- additional property；
- schema version；
- canonical sub-schema。

所以目前还不能称为真正 Schema validation。

---

## 4.2 推荐方案

允许一个 dev-only dependency：

```toml
[project.optional-dependencies]

dev = [
    "pypdf>=3.0.0",
    "jsonschema>=4.0.0"
]
```

这不会破坏：

```text
Zero Mandatory Runtime Dependencies
```

因为：

```text
runtime dependency = 0
dev dependency ≠ runtime dependency
```

---

## 4.3 新建 Schema Test Helper

建议新增：

```text
tests/schema_helpers.py
```

示例：

```python
from pathlib import Path
import json

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


def load_schema(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
```

如果 `$ref` 使用相对路径，推荐使用 registry 正确解析。

更简单的方案也可以：

```python
from jsonschema import Draft202012Validator

validator = Draft202012Validator(schema)
validator.validate(payload)
```

但必须确认：

```text
./literature_record.schema.json
./evidence_record.schema.json
```

能被正确 resolve。

---

## 4.4 Discovery contract test

不要只验证手写 payload。

应该验证：

```text
mock OpenAlex response
      ↓
parse_openalex_item()
      ↓
build/run_headless payload
      ↓
DiscoveryResult schema
      ↓
validate()
```

理想测试：

```python
def test_real_headless_payload_conforms_to_discovery_schema():
    payload = build_headless_payload_from_mock(...)
    validate_discovery(payload)
```

同时增加负向测试：

```python
def test_invalid_discovery_payload_is_rejected():
    payload = {
        "schema_version": "1.1",
        "status": "INVALID_VALUE",
        "search_protocol": {"mode": "deep"},
        "candidates": []
    }

    with pytest.raises(...):
        validator.validate(payload)
```

---

## 4.5 Extraction contract test

同理：

```python
def test_extraction_payload_conforms_to_canonical_schema():
    ...
```

并增加：

```python
def test_invalid_support_type_rejected():
    evidence = {
        ...
        "support_type": "E4"
    }

    # canonical support_type 不允许裸 E4
```

以及：

```python
def test_not_reported_record_validates():
    evidence = {
        "support_type": "NOT_REPORTED",
        "extracted_value": None,
        ...
    }
```

---

## 4.6 建议 CI

当前 stdlib tests 可继续保留。

新增独立 contract job：

```yaml
contract-validation:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"

    - run: pip install -e ".[dev]"

    - run: python -m unittest discover -s tests -v
```

如果想保持现有 stdlib CI：

```text
stdlib job
= 确保零 runtime dependency

contract job
= 安装 dev extra，做严格 schema / PDF 测试
```

这反而更加清晰。

---

## 4.7 验收标准

```text
[ ] jsonschema 真正执行
[ ] $ref 被解析
[ ] 正 payload PASS
[ ] 错 enum FAIL
[ ] 错 type FAIL
[ ] 缺 nested required FAIL
[ ] real agent output 被 schema 验证
[ ] real extraction output 被 schema 验证
```

---

# 五、P1-01：彻底消除 Skill-local 重复 Schema

## 5.1 当前问题

目前已经存在 canonical：

```text
schemas/
├── discovery_result.schema.json
├── literature_record.schema.json
├── extraction_result.schema.json
├── evidence_record.schema.json
├── claim_record.schema.json
└── synthesis_record.schema.json
```

但 Extraction Skill 中仍有：

```text
skills/literature-evidence-extraction/assets/
└── evidence_extraction_schema.json
```

这个文件再次完整定义：

```text
EvidenceRecord
support_type
evidence_strength
status
claim_status
assay_id
context_unit
...
```

风险是：

```text
schemas/evidence_record.schema.json
        ↓
修改

assets/evidence_extraction_schema.json
        ↓
忘记修改
```

最终形成 silent schema fork。

---

## 5.2 设计原则

建议明确：

```text
/schemas/
= executable contracts
= machine validation
= cross-skill handoff

/skills/*/assets/
= display template
= example
= worksheet
= markdown template
= human-readable sample
```

禁止：

```text
Skill-local assets
重新声明 canonical schema
```

---

## 5.3 推荐修改

### 删除

```text
skills/literature-evidence-extraction/assets/evidence_extraction_schema.json
```

如果需要保留“用户可读模板”，改为：

```text
evidence_extraction_template.json
```

但内容不要重新声明 JSON Schema。

例如：

```json
{
  "paper_metadata": {
    "title": "",
    "authors": [],
    "year": null
  },
  "evidence_records": []
}
```

并增加说明：

```text
This is an example/template only.
Canonical validation contract:
schemas/extraction_result.schema.json
```

---

## 5.4 SKILL.md 同步

Extraction Skill 的所有契约描述统一写：

```text
schemas/extraction_result.schema.json
```

其内部 EvidenceRecord：

```text
schemas/evidence_record.schema.json
```

禁止再引用：

```text
assets/evidence_extraction_schema.json
```

---

## 5.5 新增单一真源测试

建议：

```python
def test_no_skill_local_json_schema_contracts():
    forbidden_names = {
        "candidate_literature_schema.json",
        "evidence_extraction_schema.json",
    }

    ...
```

进一步可检查：

```python
for path in Path("skills").rglob("*.schema.json"):
    fail(...)
```

然后允许：

```text
schemas/
```

作为唯一 schema root。

---

## 5.6 验收标准

```text
[ ] canonical schemas 只存在 /schemas
[ ] Skill assets 无重复 JSON Schema
[ ] SKILL.md 不引用 local executable schema
[ ] cross-skill handoff 统一使用 /schemas
```

---

# 六、P1-02：降低 Synthesis Heuristic 的语义权限

## 6.1 当前问题

README 已正确标明：

```text
controversy analyzer = EXPERIMENTAL / HEURISTIC
```

这是正确方向。

但脚本内部仍可能直接输出：

```text
Type B (Methodological Artifact / Tool Artifact)
Confidence: High
```

判断依据只是：

```text
SUPPORT studies
使用方法 A

REFUTE studies
使用方法 B

A 和 B 无交集
```

这最多说明：

```text
disagreement is associated with method
```

不能推出：

```text
method CAUSED disagreement
```

否则会把：

```text
association
```

误写成：

```text
causal diagnosis
```

---

## 6.2 推荐语义分层

将争议诊断拆成：

```text
Observed Pattern
      ↓
Candidate Explanation
      ↓
Adjudication Requirement
```

示例：

```json
{
  "observed_pattern": "support/refute groups use non-overlapping methods",
  "candidate_type": "METHOD_ASSOCIATED_DISAGREEMENT",
  "confidence": "MEDIUM",
  "causal_status": "NOT_ESTABLISHED",
  "requires_review": [
    "measurement equivalence",
    "population comparability",
    "scale comparability",
    "sampling period",
    "model assumptions"
  ]
}
```

---

## 6.3 修改 Method-disagreement 判定

从：

```python
return {
    "type": "Type B (Methodological Artifact / Tool Artifact)",
    "confidence": "High",
}
```

改为：

```python
return {
    "type": "Type B Candidate (Method-associated disagreement)",
    "confidence": "Medium",
    "causal_status": "NOT_ESTABLISHED",
    "reason": (
        "Opposing study groups use non-overlapping methods. "
        "This indicates a method-associated pattern, but does not establish "
        "that methodology caused the disagreement."
    ),
}
```

---

## 6.4 修改 2× 数值差异逻辑

当前：

```text
metric mean difference > 2x
→ Type A Direct Empirical Contradiction
→ High
```

过强。

建议输出：

```text
Candidate Type A — Large metric discrepancy
Confidence: Medium
```

只有满足以下条件才能升级：

```text
same outcome definition
same unit
same denominator
same target population
same spatial scale
same temporal scale
comparable design
```

可设计：

```python
comparability = assess_metric_comparability(claims)

if ratio > 2.0 and comparability == "HIGH":
    ...
else:
    ...
```

在 v0.6.2 不必实现复杂自动 comparator。

最低限度可以直接：

```text
Large metric discrepancy detected.
Direct contradiction not established until comparability is confirmed.
```

---

## 6.5 “No Active Disagreement” 也需要降语气

当前：

```text
Unanimous stance across examined evidence.
```

建议避免让用户误解为“科学界没有争议”。

改为：

```text
No active disagreement detected within the supplied evidence set.
```

关键是增加：

```text
within the supplied evidence set
```

---

## 6.6 Consensus Classification 同样增加证据边界

输出中增加：

```json
{
  "classification_scope": "CURRENT_EVIDENCE_SET_ONLY",
  "external_consensus_claim": false
}
```

这样：

```text
STRONG_CONSENSUS
```

不会被误读为：

```text
整个学界已形成强共识
```

而应解释为：

```text
当前输入证据集中存在强趋同
```

---

## 6.7 测试

新增：

```python
def test_disjoint_methods_do_not_claim_causal_artifact():
    result = diagnose_controversy_type(...)

    assert result["confidence"] != "High"
    assert result["causal_status"] == "NOT_ESTABLISHED"
```

```python
def test_large_metric_difference_requires_comparability():
    ...
```

```python
def test_no_disagreement_is_scoped_to_input_evidence():
    ...
```

---

## 6.8 验收标准

```text
[ ] 方法差异不再直接称 Artifact
[ ] 不再自动 High Confidence
[ ] 2×差异不自动等于 Direct Contradiction
[ ] 所有共识/争议结论绑定 current evidence set
[ ] heuristic 输出明确 requires adjudication
```

---

# 七、P1-03：修复 Synthesis frontmatter 的领域偏向残留

## 7.1 当前问题

`literature-synthesis/SKILL.md` 顶部 description 仍存在类似：

```text
生态/分子生态黄金 Profile
```

这与当前设计原则：

```text
Domain-neutral core
Domain-aware execution
```

不一致。

虽然正文已经改成动态：

```text
shared/domain_lenses/<domain>.md
```

但 Skill metadata / description 仍可能给 Agent 一个默认领域锚点。

---

## 7.2 修改方式

删除：

```text
生态/分子生态黄金 Profile
```

改为：

```text
支持按任务动态加载跨学科 Domain Lens，
不得将任何单一学科 Profile 设为默认执行本体。
```

---

## 7.3 不建议只扩敏感词表

当前 Domain Neutrality Linter 主要依赖：

```text
PCR
microsatellite
patient
perovskite
...
```

无限加关键词不是最稳的方法。

建议再增加一个结构规则：

```python
def check_skill_frontmatter_for_default_domain():
    ...
```

检查：

```text
golden profile
默认生态
默认临床
默认材料
default biomedical
default ecology
...
```

更关键的是逻辑检查：

```text
generic SKILL.md 中不能写：
“默认加载 X 学科 Profile”
```

---

## 7.4 验收标准

```text
[ ] 三个 SKILL frontmatter 无单一领域默认 Profile
[ ] Domain Lens 只能动态加载
[ ] Linter 增加 frontmatter/default-domain gate
```

---

# 八、P1-04：README 与实现进行最终同步

这一项不是算法 bug，但对开源项目可信度很重要。

---

## 8.1 修复自动检索源声明

README 当前表述类似：

```text
全自动检索层集成：
OpenAlex
Crossref
PubMed
```

但当前 `agent_search.py` 的明确 headless implementation 是：

```text
OpenAlex
```

因此建议拆分：

```markdown
### Headless CLI

当前原生自动化实现：
- OpenAlex API
- OpenAlex citation snowballing

### Interactive / Host-Orchestrated Mode

在 Agent Host 具备相应工具能力时，可进一步编排：
- PubMed
- Crossref
- Web search
- commercial database export ingestion
```

不要使用：

```text
ScholarFlow 原生集成 PubMed/Crossref
```

除非代码中真的存在 connector/API implementation。

---

## 8.2 修复 Repository Structure

当前结构描述仍是：

```text
schemas v1.0
```

但：

```python
SCHEMA_VERSION = "1.1"
```

因此改为：

```text
schemas/  # canonical cross-skill contracts v1.1
```

并补充：

```text
discovery_result.schema.json
extraction_result.schema.json
```

完整建议：

```text
schemas/
├── scholarflow_contract.md
├── discovery_result.schema.json
├── literature_record.schema.json
├── extraction_result.schema.json
├── evidence_record.schema.json
├── claim_record.schema.json
└── synthesis_record.schema.json
```

---

## 8.3 修复 benchmark 展示

当前 benchmark 实际已经有四项：

```text
Discovery
Extraction
Claim
Synthesis
```

README 表格也建议补齐 Discovery：

```markdown
| Discovery | Synthetic known-seed recovery | ... |
```

同时明确：

```text
Synthetic Regression Benchmark
```

不要写成：

```text
Scientific Validation
```

建议统一：

```text
Internal Regression Benchmark
```

---

## 8.4 修复“零依赖”表述残留

README 某些比较表可能仍存在：

```text
纯 Python 3 标准库，零外部 Pip 依赖
```

建议全部统一成：

```text
Zero Mandatory Runtime Dependencies
Optional PDF / Dev dependencies available
```

避免和：

```text
pypdf
jsonschema
```

产生表面冲突。

---

## 8.5 验收标准

```text
[ ] Headless capability 与实际实现一致
[ ] Crossref/PubMed 不再被描述为本地已集成，除非真实实现
[ ] schema version = 1.1
[ ] structure tree 包含两个 envelope schemas
[ ] Benchmark 明确 synthetic/internal
[ ] Zero dependencies 改成 Zero Mandatory Runtime Dependencies
```

---

# 九、P2-01：加强 Packaging 测试

## 9.1 当前状态

当前已经有：

```bash
pip install -e .
```

并测试：

```python
import shared.version
import shared.grill_me
import shared.context_resolution
```

这比之前已经强很多。

但 editable install 不能完全证明：

```text
真实 wheel
```

中是否包含：

```text
SKILL.md
schemas/
domain_lenses/
references/
assets/
```

这些非 Python 文件。

---

## 9.2 建议新增 wheel smoke test

CI：

```yaml
- name: Build wheel
  run: |
    pip install build
    python -m build

- name: Install wheel
  run: |
    pip install dist/*.whl

- name: Verify packaged resources
  run: |
    python scripts/verify_package_assets.py
```

---

## 9.3 verify_package_assets.py

检查：

```text
shared/domain_lenses/*.md
skills/*/SKILL.md
schemas/*.json
```

如果设计目标本来不是作为 Python package 分发这些 skill assets，则需要在 README 明确：

```text
pip package = engine code only
git clone = full ScholarFlow skill bundle
```

二选一，不能模糊。

---

# 十、推荐执行顺序

建议不要一次大 commit。

拆成 4 个 PR。

---

## PR 1 — Canonical Discovery Contract

包含：

```text
P0-01
P0-02
```

标题：

```text
fix(discovery): enforce canonical output contract and propagate document-type filters
```

修改：

```text
SKILL.md
agent_search.py
discovery tests
legacy candidate schema
```

---

## PR 2 — Real Schema Validation

包含：

```text
P0-03
P1-01
```

标题：

```text
refactor(schema): enforce canonical contracts with real JSON Schema validation
```

修改：

```text
pyproject.toml
schemas/
tests/
Skill assets
CI
```

---

## PR 3 — Synthesis Heuristic Safety

包含：

```text
P1-02
P1-03
```

标题：

```text
refactor(synthesis): downgrade heuristic diagnostics and remove residual domain anchoring
```

---

## PR 4 — Docs & Packaging Closure

包含：

```text
P1-04
P2-01
```

标题：

```text
docs(packaging): align public capability claims and verify distributable assets
```

---

# 十一、建议新增测试清单

v0.6.2 最少新增以下测试：

```text
1. test_discovery_skill_points_to_canonical_schema
2. test_no_legacy_discovery_schema_as_active_contract
3. test_no_theses_applies_to_backward_snowball
4. test_no_theses_applies_to_forward_snowball
5. test_deep_search_no_theses_does_not_reintroduce_thesis
6. test_degree_of_freedom_article_is_not_thesis
7. test_real_headless_payload_validates_discovery_schema
8. test_invalid_discovery_payload_rejected
9. test_real_extraction_payload_validates_schema
10. test_invalid_support_type_rejected
11. test_no_skill_local_json_schema_contracts
12. test_disjoint_methods_do_not_claim_causal_artifact
13. test_large_metric_difference_requires_comparability
14. test_consensus_is_scoped_to_current_evidence_set
15. test_skill_frontmatter_has_no_default_domain
16. test_built_wheel_contains_required_assets
```

如果全部加入，测试规模预计从：

```text
105
```

提升到：

```text
120+
```

左右。

测试数量不是目标，关键是这些测试都针对：

```text
cross-skill silent failure
```

而不是只检查函数能否运行。

---

# 十二、v0.6.2 Definition of Done

只有以下全部满足，才建议发布 v0.6.2：

## Discovery

```text
[ ] Headless 使用 DiscoveryResult canonical contract
[ ] candidates[] 使用 LiteratureRecord contract
[ ] no-theses 全链路传播
[ ] title heuristic 不误删普通 article
```

## Extraction

```text
[ ] ExtractionResult / EvidenceRecord 为唯一 schema 真源
[ ] Skill-local schema 被删除或降级为 template
```

## Schema

```text
[ ] jsonschema 真验证
[ ] $ref 正常解析
[ ] 正例 PASS
[ ] 负例 FAIL
[ ] real pipeline payload 被验证
```

## Synthesis

```text
[ ] Method difference 只称 candidate association
[ ] 2× metric difference 不自动升级为 contradiction
[ ] consensus scope = current evidence set
[ ] heuristic 不能冒充 causal adjudication
```

## Domain Neutrality

```text
[ ] SKILL metadata 无单一领域默认 Profile
[ ] Domain Lens 只能动态注入
```

## Documentation

```text
[ ] README 与实际 headless source 一致
[ ] schemas 标注 v1.1
[ ] benchmark 明确 synthetic/internal regression
[ ] Zero Mandatory Runtime Dependencies 表述统一
```

## Packaging

```text
[ ] editable install PASS
[ ] wheel build PASS
[ ] wheel install PASS
[ ] required assets 存在
```

---

# 十三、v0.6.2 之后不要继续修什么

完成本轮以后，不建议继续投入大量时间在：

```text
更多规则
更多角色
更多 Grill-Me 维度
更多 heuristic threshold
更多 Domain Lens
```

下一阶段真正应该做的是：

```text
Validation
```

也就是：

```text
v0.7
↓
Real-World Validation
```

建议核心任务：

```text
真实论文
真实跨学科问题
人工金标
盲测
错误分析
外部使用者反馈
```

---

# 十四、建议 v0.7 路线

```text
v0.6.2
Internal Contract Stable
        ↓
v0.7
Real Paper Benchmark
        ↓
v0.8
Cross-Domain Validation
        ↓
v0.9
External User Evaluation
        ↓
v1.0
Stable Research Workflow Contract
```

建议 v0.7 不再以“新增功能数量”为 KPI。

而以：

```text
False Support Rate
NR Accuracy
Evidence Quote Accuracy
Page Accuracy
Search Recall
Cross-domain Robustness
Consensus Calibration
```

作为主要指标。

---

# 十五、最终架构目标

完成 v0.6.2 后，ScholarFlow 应形成：

```text
User / Project Context
        ↓
Context Resolution
        ↓
Adaptive Grill-Me
        ↓
Protocol Snapshot
        ↓
Discovery
        ↓
DiscoveryResult
        ↓
LiteratureRecord[]
        ↓
Extraction
        ↓
ExtractionResult
        ↓
EvidenceRecord[]
        ↓
Synthesis
        ↓
ClaimRecord[]
        ↓
SynthesisRecord
        ↓
Narrative / Controversy Map / Consensus Boundary
```

所有跨 Skill 交接只依赖：

```text
canonical versioned schemas
```

而不依赖：

```text
某个 Skill 自己维护的一套私有字段定义
```

---

# 十六、最终原则

v0.6.2 最重要的不是功能扩张，而是彻底落实以下 8 条：

```text
1. One concept, one canonical contract.
2. User constraints propagate through every execution branch.
3. A schema is only real if it is actually validated.
4. Skill assets are templates, not shadow contracts.
5. Heuristic association is not causal diagnosis.
6. Consensus is always bounded by the evidence corpus examined.
7. Domain specialization must never become domain default.
8. Public claims must never exceed executable implementation.
```

完成这一轮以后，ScholarFlow 的主要风险将从：

```text
内部架构与契约问题
```

转为：

```text
真实科研场景中的外部有效性与泛化能力
```

这正是下一阶段应该解决的问题。

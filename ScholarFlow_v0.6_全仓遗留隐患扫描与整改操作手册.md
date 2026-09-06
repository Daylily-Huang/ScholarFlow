# ScholarFlow v0.6 GitHub 全仓遗留隐患扫描与整改操作手册

> 仓库：`Daylily-Huang/ScholarFlow`  
> 扫描基线：`main` @ `89be357fed8ebd617b78c2306df2c8133f5b932a`  
> 基线版本：`pyproject.toml = 0.6.0`  
> 扫描日期：2026-09-06  
> 本文目的：识别当前仓库中**已实现但未接线、旧协议残留、数据契约分叉、声明与实现不一致、测试盲区和跨学科偏置残留**，并给出可以直接执行的整改步骤。

---

# 0. 扫描结论

当前 ScholarFlow 已经从早期“方法论设计稿”明显进入可运行工程阶段：

- 已有 `shared/core/`
- 已有 `shared/grill_me/`
- 已有 `shared/context_resolution/`
- 已有 9 个跨学科 Domain Lens
- 已有统一 `schemas/`
- 已有 CI
- 已有对抗测试、Context-Aware Grill 测试、Domain Neutrality 测试
- 最新 CI 在 Python 3.9 / 3.11 / 3.13 下通过
- 最新 CI 实际运行 **88 个 unittest，全部通过**

因此目前最大的风险已经不是“缺少架构”，而是：

> **新架构已存在，但旧入口、旧 Schema、旧措辞和旧启发式仍残留在执行链中。**

建议下一版本不要再加新 Feature，而是专门做一次：

```text
Integration Hardening
+
Contract Consolidation
+
Claim Calibration
```

推荐版本名：

```text
v0.6.1 — Integration Hardening
```

---

# 1. 优先级总表

| ID | 严重度 | 问题 | 核心风险 |
|---|---|---|---|
| P0-01 | P0 | Context Resolution 未真正接入三个主 Skill | 新 Context-Aware Grill 可能实际不运行 |
| P0-02 | P0 | Discovery 主 Skill 仍硬编码必须问 Deep/Quick + Thesis | 与 Adaptive Grill 原则直接冲突 |
| P0-03 | P0 | 两套 Domain Lens 目录重复 | 双重真源，未来必然漂移 |
| P0-04 | P0 | README 的 9 个 Domain Lens 名称与真实文件不一致 | 用户/Agent 加载不存在的 Lens |
| P0-05 | P0 | Skill-local Schema 与 global Schema 已分叉 | 跨 Skill 交接可能静默失败 |
| P0-06 | P0 | Headless Search 实际输出不满足其宣称的 Candidate Schema | 契约是假契约 |
| P0-07 | P0 | Extraction SKILL 与 `audit_claims.py` 的职责描述不一致 | Locator 可能被误当事实裁判 |
| P0-08 | P0 | Synthesis 中裸 `E4` 仍可能映射成 EXPERT_OPINION | NR 语义冲突仍未彻底消失 |
| P0-09 | P0 | `evidence_strength` 缺失时默认 MODELED_EMPIRICAL | 未知证据被自动抬高 |
| P0-10 | P0 | 宣称 Python 3.8+，但代码使用 Python 3.9+ 语法 | 3.8 用户可能直接导入失败 |
| P1-01 | P1 | Context Resolver 的附件全文判断过宽 | 普通 DOCX/MD 可能被误判为论文全文 |
| P1-02 | P1 | Conversation Provider 丢失时序 | 旧设置可能压过新设置 |
| P1-03 | P1 | Context Resolver 领域过滤只覆盖少数领域 | 跨学科污染风险仍存在 |
| P1-04 | P1 | timestamp/confidence/volatility 已定义但未参与决策 | 文档承诺与真实 resolver 不一致 |
| P1-05 | P1 | Synthesis 主 Skill 仍以生态/分子生态 Profile 为默认 | 跨学科中立化未真正完成 |
| P1-06 | P1 | Domain Neutrality Linter 不扫描三个 `SKILL.md` | 关键偏置可绕过测试 |
| P1-07 | P1 | Grill Dimensions 的 Recommended 仍大量静态硬编码 | “动态推荐”目前更多是固定默认 |
| P1-08 | P1 | `yes / ok / 确认` 被当作“全部按推荐” | 用户轻微确认可能误授权全部 Critical 决策 |
| P1-09 | P1 | `--no-theses` 不真正改变检索逻辑 | 参数只改 metadata，不改结果 |
| P1-10 | P1 | Deep Search 的“概念扩展/饱和度”仍是轻量启发式 | 容易过度描述为系统深搜 |
| P1-11 | P1 | PRISMA-S 审计字段仍不完整 | applicable=16，但没有逐项 16 项状态 |
| P1-12 | P1 | Benchmark Runner 声称 4 类 Benchmark，实际只跑 3 类 | Discovery benchmark 实际缺失 |
| P1-13 | P1 | Extraction Benchmark 没有真正测试 Extraction | 100% 指标容易误导 |
| P1-14 | P1 | Claim / Synthesis Benchmark 数据集过小 | 只能叫回归测试，不能叫外部验证 |
| P1-15 | P1 | README Validation 数字已过期 | 写 61/61，实际 CI 是 88 tests |
| P1-16 | P1 | README “Zero External Pip Dependencies” 表述过强 | 已存在 `pypdf` optional dependency |
| P1-17 | P1 | PDF 无 parser 时仍退化读取二进制 | Evidence-grade 模式应 fail closed |
| P1-18 | P1 | 多份内部整改文档堆在仓库根目录 | 旧设计会污染用户和 Agent 理解 |
| P1-19 | P1 | 组件版本号漂移 | 0.6.0 / 2.1.0 / v0.5 / benchmark v0.1 混杂 |
| P2-01 | P2 | CI 不测试 package install | repo-root 可跑 ≠ pip 安装后可跑 |
| P2-02 | P2 | 缺少真实 OpenAlex 定期集成测试 | API 变化无法及时发现 |
| P2-03 | P2 | README 硬编码 test count / benchmark 指标 | 每次更新后容易再次过期 |
| P2-04 | P2 | 缺少真正外部 gold-set validation | 无法支持强性能声明 |

---

# 2. P0-01：Context Resolution 已实现，但三个主 Skill 没真正接线

## 已确认现状

仓库已经存在：

```text
shared/context_resolution/
├── context_resolver.py
├── core_protocol.md
├── source_priority.md
├── conflict_resolution.md
├── relevance_filter.md
├── volatility_rules.md
└── provider_contract.md
```

并且 `tests/test_context_aware_grill.py` 已覆盖 9 个场景。

但是三个主入口仍然写的是：

```text
Stage 1:
唯一必须读取 references/stage0_grill_me.md
```

而不是：

```text
Stage 0A Context Resolution
Stage 0B Adaptive Grill
Stage 0C Protocol Snapshot
```

因此当前状态实际上是：

```text
Context Resolver:
代码存在 ✓
测试存在 ✓
README 宣称存在 ✓
主 Skill 强制调用 ✗
```

---

## 风险

真实 Agent 只遵循 `SKILL.md` 时：

1. 不一定加载 Context Resolver；
2. 可能直接进入旧 `stage0_grill_me.md`；
3. 重复问用户已经在对话/项目里回答的问题；
4. README 宣称的 Context-Aware 行为与实际运行不一致。

---

## 修改文件

必须同时修改：

```text
skills/literature-discovery-acquisition/SKILL.md
skills/literature-evidence-extraction/SKILL.md
skills/literature-synthesis/SKILL.md
```

---

## 推荐替换结构

把当前：

```text
阶段 1：启动与前置交互门禁
→ stage0_grill_me.md
```

替换为：

```text
Stage 0A — Context Resolution
Stage 0B — Adaptive Grill-Me
Stage 0C — Protocol Snapshot
Stage 1  — Substantive Execution
```

---

## Stage 0A 必须明确写

```markdown
### Stage 0A — Context Resolution

Before generating any Grill-Me question, the Agent MUST:

1. Parse the current user message.
2. Reuse confirmed decisions from the current conversation.
3. Inspect current task attachments when relevant.
4. Consume upstream ScholarFlow structured outputs when available.
5. Search project files only for unresolved high-impact variables.
6. Produce a Decision State.
7. Pass only unresolved CRITICAL/HIGH_IMPACT dimensions to Grill-Me.

The Agent MUST NOT ask for information already reliably resolved from context.
```

---

## 验收标准

新增测试：

```text
tests/test_skill_entrypoint_contract.py
```

检查三个 `SKILL.md` 必须同时包含：

```text
Stage 0A
Context Resolution
Stage 0B
Adaptive Grill
Stage 0C
Protocol Snapshot
```

同时检查不再出现：

```text
唯一必须读取 stage0_grill_me.md
```

作为整个 Stage 0 的唯一入口。

---

# 3. P0-02：Discovery SKILL 仍硬编码“Q1/Q2 必问”

## 已确认现状

Discovery `SKILL.md` 仍写：

```text
必须向用户发起：
Q1 Deep Search vs Quick Search
Q2 硕博学位论文需求
```

这与现在的设计原则：

```text
预设 Decision Dimensions
不预设固定问题
```

直接冲突。

---

## 修改原则

删除：

```text
Q1 必问
Q2 必问
```

改成：

```text
Only unresolved CRITICAL/HIGH_IMPACT dimensions may enter Grill-Me.
```

`Search Depth`、`Thesis` 是否需要问，应由：

```text
Decision Impact
+
Current Context
+
Research Goal
+
Domain Lens
```

动态决定。

---

## 验收标准

例如输入：

```text
请做 Deep Search，包含中英文硕博论文，2010年至今。
```

不得再问：

```text
Deep or Quick?
Need theses?
Time range?
Language?
```

---

# 4. P0-03：两套 Domain Lens 是重复真源

## 已确认现状

同时存在：

```text
shared/domain_lenses/
```

和：

```text
shared/grill_me/domain_lenses/
```

两边 9 个文件当前 SHA 完全相同。

这说明它们现在是复制品。

---

## 风险

以后修改：

```text
shared/domain_lenses/computer_science.md
```

如果忘记同步另一份：

```text
shared/grill_me/domain_lenses/computer_science.md
```

就会产生：

```text
同一个 Domain
两套规则
```

这是典型：

```text
Duplicate Source of Truth
```

---

## 推荐修复

只保留：

```text
shared/domain_lenses/
```

删除：

```text
shared/grill_me/domain_lenses/
```

Grill-Me 通过相对路径引用：

```text
../domain_lenses/
```

---

## 验收测试

新增：

```python
assert not os.path.exists("shared/grill_me/domain_lenses")
assert os.path.exists("shared/domain_lenses")
```

并在 CI 中做 duplicate SHA / duplicate basename 检查。

---

# 5. P0-04：README 中 Domain Lens 名称与实际文件不一致

## README 当前描述

README 最新架构段列出类似：

```text
generic
biomedical
clinical
ecology
molecular_biology
computer_science
physical_sciences
social_sciences
environmental
```

## 实际目录

```text
generic
biomedical
life_sciences
ecology_environment
computer_science
chemistry_materials
physical_sciences
engineering
social_sciences
```

---

## 风险

用户或 Agent 根据 README 尝试加载：

```text
shared/domain_lenses/clinical.md
```

会找不到文件。

---

## 两种修法

### 推荐 A：README 对齐实际文件

直接改为：

```text
generic
biomedical
life_sciences
ecology_environment
computer_science
chemistry_materials
physical_sciences
engineering
social_sciences
```

### B：真的实现别名

如果一定想使用：

```text
clinical
molecular_biology
environmental
```

则必须建立 alias resolver。

不建议第一版这么做。

---

## 验收

增加一个自动文档测试：

```text
README 中列出的 lens 名称
=
shared/domain_lenses/*.md
```

---

# 6. P0-05：Global Schema 与 Skill-local Schema 已经分叉

## 已确认现状

全局：

```text
schemas/evidence_record.schema.json
```

使用：

```text
evidence_id
record_id
field
claim_status
```

而 Extraction Skill 内部：

```text
skills/literature-evidence-extraction/assets/evidence_extraction_schema.json
```

使用：

```text
field_id
field_name
status
assay_id
paper_metadata
auditor_verdict
```

两者不是同一个 Schema。

---

## 风险

可能出现：

```text
Extraction 输出通过本地 Schema
↓
Synthesis 按 global EvidenceRecord 读取
↓
字段找不到
```

或者需要 Agent 自己猜：

```text
status == claim_status?
field_name == field?
```

这违背你的：

> 跨 Skill 明确契约

原则。

---

## 推荐架构

只允许一个 Canonical Record Schema：

```text
schemas/evidence_record.schema.json
```

Extraction 的完整输出 Envelope 单独叫：

```text
schemas/extraction_result.schema.json
```

结构：

```json
{
  "schema_version": "1.1",
  "paper_metadata": {},
  "extraction_metadata": {},
  "evidence_records": [
    { "$ref": "evidence_record.schema.json" }
  ],
  "auditor_verdict": {}
}
```

---

## 核心原则

```text
EvidenceRecord ≠ ExtractionResult
```

EvidenceRecord 是跨 Skill 原子单位。

ExtractionResult 是一次运行的 Envelope。

---

## 建议删除/改造

```text
skills/literature-evidence-extraction/assets/evidence_extraction_schema.json
```

不要继续作为第二套 EvidenceRecord 定义。

---

# 7. P0-06：Headless Search 输出和宣称的 Candidate Schema 不一致

## 已确认现状

Discovery SKILL 写：

> Headless JSON 必须严格遵循 `assets/candidate_literature_schema.json`

Candidate Schema 要求：

```text
id
title
authors
year
journal
doi
source_databases
evidence_level
screening_status
screening_reason
```

但 `agent_search.py` 产生的单条记录没有稳定填写：

```text
screening_reason
document_type
...
```

同时 CLI 输出本身还是：

```json
{
  "status": "...",
  "search_target": "...",
  "candidates": [...]
}
```

也就是说：

> Schema 描述的是 record，实际输出是 envelope。

---

## 推荐修复

建立两个 Schema：

```text
schemas/literature_record.schema.json
schemas/discovery_result.schema.json
```

`discovery_result.schema.json`：

```json
{
  "type": "object",
  "required": [
    "schema_version",
    "status",
    "search_protocol",
    "candidates"
  ],
  "properties": {
    "candidates": {
      "type": "array",
      "items": {
        "$ref": "./literature_record.schema.json"
      }
    }
  }
}
```

---

## 同时修改 agent_search

不要：

```text
evidence_level = VERIFIED
```

建议改：

```text
metadata_verification_status = VERIFIED_API
screening_status = UNCERTAIN
```

“元数据来自 OpenAlex”不等于：

> 该论文已经成为 VERIFIED scientific evidence。

---

## 新增测试

不要只测：

```text
JSON 能打开
```

要真实验证：

```text
agent_search output
→ discovery_result.schema.json
→ PASS
```

---

# 8. P0-07：Extraction SKILL 与 `audit_claims.py` 已经职责错位

## 已确认现状

`audit_claims.py` 现在已经正确降级为：

```text
Candidate Evidence Locator & Surface-Consistency Checker
```

并明确声明：

```text
NOT a semantic truth verifier
```

它输出：

```text
NO_SURFACE_MATCH
LOCATED_CO_OCCURRING
NUMBER_DISLOCATED
NUMERICAL_MISMATCH
CANDIDATE_LOCATED
```

这是合理的。

但是 Extraction `SKILL.md` 仍然说 Audit Mode：

```text
调用 audit_claims.py
→ 输出 SUPPORTED / UNSUPPORTED / CONTRADICTORY
```

---

## 风险

Agent 可能：

```text
LOCATED_CO_OCCURRING
↓
自动升级
SUPPORTED
```

这是你之前最想避免的错误。

---

## 正确架构

```text
audit_claims.py
        ↓
Candidate Evidence
        ↓
Evidence Auditor
        ↓
Semantic Adjudication
        ↓
SUPPORTED
PARTIALLY_SUPPORTED
UNSUPPORTED
CONTRADICTORY
AMBIGUOUS
OCR_UNCERTAIN
```

---

## 必须修改

```text
skills/literature-evidence-extraction/SKILL.md
skills/literature-evidence-extraction/references/audit_mode_protocol.md
```

明确：

> Deterministic locator verdicts MUST NOT be translated directly into final claim status.

---

# 9. P0-08：裸 `E4` 的歧义仍然存在

## 当前代码

Synthesis：

```python
LEGACY_TIER_MAP = {
    ...
    "E4": "EXPERT_OPINION",
    "E4_NR": "NOT_REPORTED"
}
```

但 Extraction 历史语义中：

```text
E4 = NR / NOT_REPORTED
```

---

## 这意味着

旧数据如果只有：

```json
{
  "evidence_tier": "E4"
}
```

Synthesis 仍可能解释为：

```text
EXPERT_OPINION
```

而不是：

```text
NOT_REPORTED
```

因此最初那个 E1-E4 bug 还没有彻底封死。

---

## 推荐修复

裸：

```text
E4
```

一律禁止自动解释。

改成：

```python
"E4": "AMBIGUOUS_LEGACY_TIER"
```

遇到它：

```text
REJECT / REQUIRE_SCHEMA_VERSION
```

---

## 兼容迁移

如果输入：

```text
artifact_type = extraction
schema_version < 1.0
E4
```

可以明确映射：

```text
NOT_REPORTED
```

如果：

```text
artifact_type = synthesis
```

才按旧 Synthesis 语义处理。

不能仅凭：

```text
"E4"
```

猜。

---

# 10. P0-09：缺失 evidence_strength 时不应该默认 MODELED_EMPIRICAL

当前：

```python
raw_strength = ... or "MODELED_EMPIRICAL"
```

这会导致：

> 没有评级的信息自动获得中高等级证据。

---

## 正确默认

```python
raw_strength = ... or "UNKNOWN"
```

并且：

```text
UNKNOWN
```

最好不要自动参与强共识判断。

---

## 推荐规则

```text
UNKNOWN evidence strength
→ may be displayed
→ must not independently elevate consensus level
```

---

# 11. P0-10：Python 3.8+ 声明与代码语法不兼容

## 当前声明

README：

```text
Python 3.8+
```

`pyproject.toml`：

```toml
requires-python = ">=3.8"
```

但例如：

```python
def get_discovery_dimensions() -> list[GrillDimension]:
```

内建泛型：

```text
list[T]
```

是 Python 3.9+ 语法能力。

当前 CI 也只测：

```text
3.9
3.11
3.13
```

没有 3.8。

---

## 推荐修复

最简单：

```toml
requires-python = ">=3.9"
```

README badge 同步：

```text
Python 3.9+
```

这是比为了兼容 3.8 到处改 typing 更合理的方案。

---

# 12. P1-01：Attachment Provider 把普通文件误判成“全文论文”

当前逻辑大致：

```python
if filename.endswith(".pdf/.txt/.md/.docx/.html")
or len(content) > 50:
    E2 = fulltext_pdf
```

---

## 问题

以下文件也会被误判：

```text
research_protocol.docx
meeting_notes.md
README.md
project_plan.txt
```

结果 Extraction 可能错误跳过：

```text
Full-text Verification Gate
```

---

## 推荐数据模型

不要直接：

```text
fulltext_pdf
```

改成：

```yaml
document_available: true
document_kind:
  PAPER_FULLTEXT
  SUPPLEMENT
  PROTOCOL
  NOTES
  DATA_TABLE
  UNKNOWN
```

只有：

```text
PAPER_FULLTEXT
```

才能满足 Extraction Full-text Gate。

---

## 判定方法

至少联合：

```text
文件名
+
标题/作者/摘要/References 等文献结构特征
+
用户显式说明
```

不能只看扩展名。

---

# 13. P1-02：Conversation Provider 应按“最近决策”解析，而不是全文拼接

当前做法：

```python
full_text = " ".join(all conversation turns)
```

然后 regex。

---

## 风险例子

早期：

```text
只搜英文
```

后面：

```text
改成中英文都要
```

拼接后如果代码先检测 English-only：

旧决定可能获胜。

---

## 推荐逻辑

```text
按 turn 从新到旧扫描
↓
每个 Dimension 找到最近一次明确决定
↓
停止该 Dimension 的继续历史扫描
```

---

## 更好的结构

优先解析历史：

```text
Protocol Snapshot
```

而不是自然语言全文。

新增：

```text
DecisionSnapshotProvider
```

这是最值得加的 provider。

---

# 14. P1-03：Project Search 的领域过滤仍然不是真正全学科

当前 resolver 中的过滤主要识别：

```text
computer science
biomedical
ecology
```

而且真正严格排除主要是：

```text
CS task
vs
ecology doc
```

---

## 缺失

```text
materials
chemistry
physics
engineering
social science
economics
education
...
```

---

## 推荐修复

不要继续扩展巨大 regex。

改为：

```text
Domain Detector
↓
Canonical Domain Tags
↓
Lens-compatible relevance score
```

例如：

```yaml
task_domains:
  - computer_science
  - biomedical

document_domains:
  - ecology_environment

domain_overlap: 0.0
```

才过滤。

---

# 15. P1-04：timestamp / confidence / volatility 目前是“定义了但没真正用”

`ContextFact` 已经有：

```text
timestamp
confidence
volatility
```

这是好设计。

但 resolver 同层冲突主要还是：

```text
distinct values > 1
→ UNRESOLVED_CONFLICT
```

没有真正按：

```text
VOLATILE → newer timestamp wins
```

执行。

---

## 推荐冲突算法

```text
1. Compare source priority
2. If different priority → higher wins
3. If same priority:
   a. VOLATILE + valid timestamps → newest wins
   b. STATIC contradiction → conflict
   c. same timestamp → compare explicitness/confidence
4. still unresolved → Grill
```

---

# 16. P1-05：Synthesis 主 Skill 仍有明显生态/分子生态默认偏向

当前 `literature-synthesis/SKILL.md` 仍含：

```text
生态/分子生态黄金 Profile
```

并且 Deep 分支还规定：

```text
加载 ecology_profile.md
或 molecular_ecology_profile.md
```

Workflow 里还有：

```text
领域 Profile 偏倚过滤 生态/分子生态
```

---

## 必须改为

```text
Detect domain
↓
load shared/domain_lenses/<domain>.md
```

如果跨领域：

```text
primary lens + secondary lens
```

---

## 旧目录处理

```text
skills/literature-synthesis/references/domain_profiles/
```

只作为：

```text
legacy / backward-compatible examples
```

不得再作为主执行入口。

---

# 17. P1-06：Domain Neutrality Linter 有明显扫描盲区

当前 linter 扫：

```text
shared/core
shared/grill_me core
几个 references
```

但不扫最关键的：

```text
skills/*/SKILL.md
skills/*/references/stage0_grill_me.md
README.md
核心 assets/templates
```

因此：

```text
Synthesis SKILL 仍写生态/分子生态
```

测试照样 PASS。

---

## 推荐分两级

### Tier A — 必须学科中立

```text
README architecture sections
3 × SKILL.md
3 × stage0_grill_me.md
shared/core/*
shared/grill_me/*
cross-skill schemas
generic templates
```

### Tier B — 允许领域词

```text
examples/*
shared/domain_lenses/*
legacy profiles/*
```

---

## 新增规则

不能只搜词。

还应检测：

```text
generic execution path
→ 是否直接引用某个单一领域 profile 文件
```

---

# 18. P1-07：Grill Dimensions 目前仍不是完全动态推荐

`dimensions.py` 中大量：

```python
is_recommended=True
```

是静态写死的。

例如 Discovery：

```text
D1 默认系统综述
D2 默认因果机制
D3 默认单一目标实体
...
```

---

## 风险

用户只是：

> “找几篇代表性论文”

系统仍可能推荐：

```text
systematic_survey
```

因为默认 option A 是 Recommended。

---

## 推荐架构

`dimensions.py` 只定义：

```text
Dimension
possible option families
priority
```

不要永久定义：

```text
is_recommended=True
```

推荐结果应由：

```text
Recommendation Engine
=
Goal
+
Context
+
Domain Lens
+
Cost/Rigor Tradeoff
```

动态生成。

---

## 短期修复

至少允许：

```python
recommendation_policy.recommend(
    dimension,
    task_state,
    domain_lens
)
```

覆盖 preset recommendation。

---

# 19. P1-08：`yes / ok / 确认` 不应自动等于“全部按推荐”

当前：

```text
yes
y
ok
确认
同意
proceed
```

全部能触发：

```text
accept all recommended
```

---

## 风险

用户说：

```text
“ok”
```

可能只是表示：

> 看到了。

但系统会把 5 个科研决策全部视为用户授权。

---

## 推荐保留

明确语义：

```text
按推荐
全部按推荐
全选推荐
accept all recommended
```

---

## 建议删除

```text
yes
y
ok
确认
同意
proceed
```

除非：

```text
当前只有一个明确待确认决策
```

---

## 另外

```text
全选A
```

不能等同：

```text
全部按推荐
```

因为 Recommended 不一定是 A。

---

# 20. P1-09：`--no-theses` 目前没有真正过滤论文类型

`agent_search.py` 中：

```text
include_theses
```

目前主要：

- 打日志；
- 写 metadata。

但 OpenAlex query 并没有因为：

```text
--no-theses
```

改变。

---

## 两种修法

### A. 真正实现过滤

根据 OpenAlex work type：

```text
dissertation
thesis
```

执行 include / exclude。

### B. 如果自动源无法可靠控制

输出：

```yaml
thesis_preference:
  requested: exclude
  enforcement: NOT_FULLY_ENFORCED
```

不要写：

```text
theses_included = false
```

让用户误以为已严格过滤。

---

# 21. P1-10：Deep Search 的能力名需要收敛

当前 Deep Search：

1. 主 query；
2. 用 query 第一词 + 最后一词做一个扩展 query；
3. 找最高被引 candidate；
4. 对它 snowball；
5. 计算一次 marginal gain。

这已经比 Quick 强。

但它还不能等同：

```text
真正多轮概念矩阵搜索
真正饱和收敛
```

---

## 建议短期改名

内部：

```text
enhanced_openalex_search
```

用户层仍可叫：

```text
Deep Search
```

但 README 应说明：

> Headless Deep mode currently performs multi-pass OpenAlex expansion and limited citation chasing; full multi-database systematic retrieval remains an agent-orchestrated workflow.

---

## 饱和字段建议改名

当前：

```text
saturation_status
```

建议：

```text
expansion_gain_status
```

直到真的实现：

```text
repeat search rounds
until marginal gain < threshold
for N consecutive rounds
```

---

# 22. P1-11：PRISMA-S 审计结构还不够严谨

当前 payload：

```text
applicable_items = 16
reported_items = 5...
unreported_items = 2...
```

剩余项目状态并不透明。

---

## 推荐数据结构

```json
{
  "prisma_s_audit": {
    "framework": "PRISMA-S-2021",
    "overall_status": "PARTIAL",
    "items": [
      {
        "item": 1,
        "status": "PASS",
        "evidence": "OpenAlex"
      },
      {
        "item": 2,
        "status": "USER_ASSISTED"
      },
      {
        "item": 3,
        "status": "NOT_EVALUATED"
      }
    ]
  }
}
```

状态：

```text
PASS
FAIL
NOT_APPLICABLE
NOT_EVALUATED
USER_ASSISTED
```

---

## 同时修改 docstring

删掉：

```text
PRISMA-S compliant multi-phase execution
```

改：

```text
PRISMA-S-informed logging and audit support
```

---

# 23. P1-12：Benchmark Runner 声称有 Discovery Benchmark，但没有执行

文件注释写：

```text
4 core benchmarks:
1 Discovery
2 Extraction
3 Claim Verification
4 Synthesis
```

但：

```python
results = [
    extraction,
    claim_verification,
    synthesis
]
```

没有：

```text
discovery
```

虽然：

```text
benchmarks/data/discovery_gold_set.json
```

已经存在。

---

## 修复

新增：

```python
evaluate_discovery_benchmark()
```

至少评估：

```text
Recall@K
Precision@K
known-seed recovery
dedup accuracy
citation-chasing gain
```

---

# 24. P1-13：当前 Extraction Benchmark 实际上只是 Fixture Sanity Check

目前逻辑：

```text
expected value 是否出现在字符串中
field name 是否不存在
```

它并没有调用真正的 extraction pipeline。

因此：

```text
Field Precision = 100%
```

不能解释成：

> ScholarFlow 实际抽取准确率 100%。

---

## 当前 Benchmark 应改名

```text
Extraction Fixture Integrity Check
```

---

## 真 Benchmark 应该做

```text
input document
↓
ScholarFlow extraction path
↓
EvidenceRecord output
↓
compare against human gold
```

指标：

```text
Field Precision
Field Recall
Exact Match
Quote Grounding Accuracy
Location Accuracy
NR Accuracy
False Completion Rate
```

---

# 25. P1-14：Claim / Synthesis Benchmark 目前规模太小

最新 CI：

```text
Claim cases = 5
Synthesis topics = 2
```

这对：

```text
回归测试
```

很好。

但对：

```text
scientific validation
```

远远不够。

---

## README 应明确分级

当前属于：

```text
INTERNAL SYNTHETIC REGRESSION
```

而不是：

```text
EXTERNALLY VALIDATED SCIENTIFIC PERFORMANCE
```

---

## 下一阶段目标

### Claim

至少：

```text
100–300 human-annotated claims
```

覆盖：

```text
supported
partial
unsupported
contradictory
ambiguous
referenced-only
wrong-context-number
```

### Synthesis

至少：

```text
30–50 scenarios
```

覆盖所有 consensus classes 和 controversy types。

---

# 26. P1-15：README Validation Status 已过期

README 仍写：

```text
61/61 passed
```

最新 CI：

```text
88 tests passed
```

---

## 不建议继续手工更新数字

改成：

```text
Latest CI status: see GitHub Actions
```

或者自动 badge。

否则：

```text
每新增测试
→ README 又过期
```

---

# 27. P1-16：Zero External Pip Dependencies 应改成“Zero Mandatory Dependencies”

当前：

```text
dependencies = []
```

这是事实。

但 optional：

```toml
[pdf]
pypdf>=3.0.0
```

也是真实存在。

---

## 推荐 README

替换：

```text
Zero External Pip Dependencies
```

为：

```text
Zero Mandatory Third-Party Runtime Dependencies
```

补：

```text
Optional PDF extra:
pip install "scholarflow[pdf]"
```

---

# 28. P1-17：Evidence-grade PDF 模式应该 fail closed

`audit_claims.py` 在没有 pypdf 时会：

```text
plain_text_fallback
```

并尝试把 PDF 当文本打开。

即使标记：

```text
LOW_FALLBACK
```

仍继续执行 locator。

---

## 推荐模式

### Strict / Audit Mode

如果：

```text
PDF
+
no reliable PDF parser
```

则：

```text
STOP
PARSER_REQUIRED
```

### Best-effort Mode

用户显式：

```text
--allow-degraded-pdf
```

才继续。

---

# 29. P1-18：内部整改文档不应继续放仓库根目录

目前根目录存在多份：

```text
ScholarFlow_审查问题与整改方案.md
ScholarFlow_Grill-Me_重构设计方案.md
ScholarFlow_跨学科中立化与去偏整改方案.md
ScholarFlow_Context-Aware_Grill-Me_操作设计文档.md
```

这些对开发过程有价值。

但放根目录会：

- 混淆正式用户文档；
- 旧内容会被搜索到；
- Agent 可能把 superseded 设计当现行协议。

---

## 推荐迁移

```text
docs/
└── rfcs/
    ├── RFC-001-grill-me.md
    ├── RFC-002-domain-neutrality.md
    ├── RFC-003-context-resolution.md
    └── archive/
```

顶部加：

```yaml
status: IMPLEMENTED / PARTIALLY_IMPLEMENTED / SUPERSEDED
target_version: ...
last_updated: ...
```

---

# 30. P1-19：版本号需要统一定义

当前可见：

```text
Package: 0.6.0
agent_search metadata: 2.1.0
Domain linter: v0.5
Benchmark runner: v0.1
```

如果这是组件版本，没问题。

问题是：

> 没有文档说明哪些是 package version，哪些是 component version。

---

## 推荐

建立：

```text
VERSION
```

或：

```python
scholarflow/version.py
```

至少统一：

```text
project_version = 0.6.1
schema_version = 1.0
benchmark_suite_version = 0.1
```

组件不要各自随意写“2.1.0”。

---

# 31. 额外重要问题：Synthesis 的共识算法仍然是启发式评分器

虽然当前代码已经比早期版本好：

- `support_type` 和 `evidence_strength` 分开；
- NR = 0；
- 有 independence / bias / replication modifier；
- 不再声称 Universal Consensus。

但核心仍是：

```text
base weights
× modifiers
→ support/refute ratio
→ threshold classification
```

例如：

```text
support >= 0.80
→ STRONG_CONSENSUS
```

---

## 建议定位

程序输出应叫：

```text
Heuristic Evidence Balance
```

最终：

```text
Consensus Classification
```

必须经过：

```text
Gatekeeper qualitative adjudication
```

---

## 不建议当前就删除算法

它适合作为：

```text
screening / triage
```

但不要作为：

```text
scientific truth engine
```

---

# 32. 争议类型诊断仍有因果过推风险

当前代码类似：

```text
支持论文的方法集合
和
反对论文的方法集合
完全不相交
↓
Type B Methodological Artifact
High confidence
```

但：

> 方法与结论相关

不等于：

> 方法造成了结论差异。

---

## 改成

```text
Candidate Type B:
Method-associated disagreement
```

confidence：

```text
LOW / MEDIUM
```

只有经过具体设计/边界比较后才能升级。

---

## 数值 > 2 倍

同样不能直接：

```text
Type A High Confidence
```

必须先检查：

```text
unit
metric definition
population
scale
normalization
CI
```

---

# 33. `dimensions.py` 中还存在一些跨学科偏向

虽然已经比早期好很多，但仍有：

```text
D2 默认因果机制
D9 “同行评议期刊 = 科研证据金标准”
D12 默认 PubMed / EuropePMC / arXiv/bioRxiv
E1 rationale = 循证医学与生态学
S4 value = assay_level
S6 rationale = Gold Standard
```

---

## 建议

Core Dimension 用更中性术语：

```text
context_unit_level
study_unit_level
```

而不是：

```text
assay_level
```

---

`D12` 数据源推荐应由 Domain Lens 决定：

```text
medicine → PubMed / Europe PMC
computer science → OpenAlex / arXiv / Semantic Scholar
social science → OpenAlex + domain databases
chemistry → Crossref/OpenAlex + domain databases
```

---

# 34. Global Schema 中仍有 `assay_id`，建议进一步中立化

当前：

```text
schemas/evidence_record.schema.json
```

仍有：

```text
assay_id
```

对全学科并不够中立。

---

## 建议 v1.1

使用：

```json
"context_unit": {
  "context_id": "...",
  "context_type": "..."
}
```

Domain Lens 再解释：

```text
ASSAY
COHORT
DATASET
MODEL_VARIANT
SITE
BATCH
TREATMENT_ARM
```

---

# 35. P2-01：CI 应增加“安装后运行”测试

现在 CI：

```text
checkout
setup Python
直接从 repo root 跑 unittest
```

但没有：

```text
pip install -e .
```

因此无法证明：

> pip 安装后的 package 能正常 import。

---

## 加一个 packaging job

```yaml
- run: python -m pip install -U pip
- run: pip install -e .
- run: python -c "import shared.grill_me"
- run: python -c "import shared.context_resolution"
```

更长期建议：

```text
src/scholarflow/
```

作为真正 Python package。

---

# 36. P2-02：增加定期 OpenAlex integration test

不建议 PR CI 每次依赖网络。

但可以：

```yaml
schedule:
  - cron: weekly
```

测试：

```text
known DOI resolve
known title search
OpenAlex JSON fields
snowball endpoint
```

API 结构一旦变化就能发现。

---

# 37. P2-03：README 状态不要再硬编码

建议：

```text
CI badge
benchmark artifact link
release badge
```

替代：

```text
61/61
88/88
```

这种数字。

---

# 38. P2-04：建立 Validation Level 体系

建议项目明确四级：

```text
LEVEL 1 — UNIT_TESTED
LEVEL 2 — SYNTHETIC_REGRESSION_VALIDATED
LEVEL 3 — HUMAN_GOLDSET_VALIDATED
LEVEL 4 — EXTERNAL_CROSS_DOMAIN_VALIDATED
```

当前多数核心模块应标：

```text
LEVEL 1–2
```

不要提前写：

```text
scientifically validated
```

---

# 39. 建议的实际整改顺序

不要同时改 30 个文件。

推荐拆成 5 个 PR。

---

# PR 1 — Stage 0 Wiring Fix

标题：

```text
fix: wire context resolution into all Stage 0 entrypoints
```

修改：

```text
3 × SKILL.md
3 × stage0_grill_me.md
README.md
```

完成：

```text
Stage 0A Context
Stage 0B Grill
Stage 0C Snapshot
```

同时删除 Discovery 固定 Q1/Q2。

---

# PR 2 — Canonical Contracts

标题：

```text
refactor: consolidate cross-skill schemas and legacy evidence semantics
```

完成：

1. Canonical `EvidenceRecord`
2. 新建 `ExtractionResult`
3. 新建 `DiscoveryResult`
4. Headless output schema validation
5. 裸 E4 禁止自动映射
6. UNKNOWN evidence strength 默认

---

# PR 3 — Domain Neutrality Closure

标题：

```text
refactor: complete domain-neutral execution wiring
```

完成：

1. 删除 duplicate domain lenses
2. README Lens 名称对齐
3. Synthesis SKILL 改 shared lens
4. Linter 扩展到 3 个 SKILL
5. `assay_level` → `context_unit_level`
6. Context Resolver 去掉儿童等硬编码领域规则

---

# PR 4 — Validation Honesty

标题：

```text
docs: align validation claims with actual benchmark scope
```

完成：

1. README 61/61 删除
2. Zero Mandatory Dependencies
3. Benchmark 标记 synthetic regression
4. Discovery benchmark 真正接入
5. PRISMA-S itemized audit
6. Deep Search capability 边界说明

---

# PR 5 — Resolver & Runtime Hardening

标题：

```text
fix: harden context resolution, PDF parsing and runtime compatibility
```

完成：

1. Conversation recency
2. Attachment document_kind
3. timestamp/volatility resolution
4. stricter response parser
5. Python >=3.9
6. packaging install test
7. strict PDF parser gate

---

# 40. 每个 PR 的最低验收条件

所有 PR 必须：

```text
python -m unittest discover -s tests -v
python benchmarks/run_benchmarks.py
python scripts/domain_neutrality_linter.py
```

通过。

---

# 41. 建议新增 12 个测试

```text
test_skill_entrypoint_requires_context_resolution
test_discovery_no_fixed_q1_q2
test_single_domain_lens_source_of_truth
test_readme_lens_names_match_files
test_discovery_result_validates_schema
test_extraction_result_validates_schema
test_bare_e4_is_rejected
test_missing_evidence_strength_is_unknown
test_attachment_protocol_is_not_fulltext
test_conversation_latest_decision_wins
test_ok_does_not_accept_all_recommended
test_python_version_contract
```

---

# 42. 建议新增 5 个对抗测试

## A. 旧 E4 数据

```json
{
  "evidence_tier": "E4"
}
```

预期：

```text
AMBIGUOUS_LEGACY_TIER
```

而不是：

```text
EXPERT_OPINION
```

---

## B. 普通项目 Word

```text
project_protocol.docx
```

预期：

```text
document_kind = PROTOCOL
```

不得：

```text
fulltext_pdf
```

---

## C. Conversation 决策覆盖

Turn 1：

```text
English only
```

Turn 8：

```text
改成中英双语
```

预期：

```text
en_and_zh
```

---

## D. “ok”

5 个 Grill Questions 后用户只说：

```text
ok
```

预期：

```text
NOT_FULLY_CONFIRMED
```

而不是：

```text
accept all recommended
```

---

## E. 计算机项目 + 生态历史文件

当前：

```text
Transformer benchmark
```

历史：

```text
PCR / species / habitat
```

预期：

```text
0 irrelevant-domain inheritance
```

---

# 43. README 建议新增一个“能力成熟度”表

| Capability | Current Status |
|---|---|
| OpenAlex metadata retrieval | `IMPLEMENTED / UNIT-TESTED` |
| Citation snowballing | `IMPLEMENTED / UNIT-TESTED` |
| Multi-database autonomous retrieval | `PARTIAL / USER-ASSISTED` |
| Context Resolution | `IMPLEMENTED / INTEGRATION HARDENING` |
| Adaptive Grill-Me | `IMPLEMENTED / UNIT-TESTED` |
| PDF evidence localization | `IMPLEMENTED / OPTIONAL PDF PARSER` |
| Semantic claim verification | `AGENT/HUMAN ADJUDICATION REQUIRED` |
| Consensus classification | `HEURISTIC / EXPERIMENTAL` |
| School discovery | `EXPERIMENTAL` |
| External cross-domain benchmark | `NOT YET VALIDATED` |

这比：

```text
全部支持 / 全部验证
```

更符合 ScholarFlow 自己的证据哲学。

---

# 44. 当前仓库总体成熟度判断

基于本次扫描，可以把当前状态概括为：

```text
Architecture Design        9.2/10
Documentation Structure   8.8/10
Testing Infrastructure    8.3/10
Cross-domain Design       8.2/10
Execution Integration     6.8/10
Schema Consistency        6.5/10
Scientific Validation     4.5/10
```

这里的“Scientific Validation 4.5”不是说算法差，而是：

> **当前公开 benchmark 样本过小，尚不足以证明跨领域真实科研性能。**

---

# 45. 当前最重要的五件事

如果只修五个：

## 1

```text
把 Context Resolution 真正接到三个 SKILL.md 的 Stage 0
```

## 2

```text
统一所有 Schema，禁止 Skill-local 与 global 双轨定义
```

## 3

```text
彻底封死裸 E4 语义歧义 + UNKNOWN 不得默认升格
```

## 4

```text
删除重复 Domain Lens，并完成 Synthesis 主 Skill 去生态默认化
```

## 5

```text
把 Benchmark 从“漂亮的 100%”重新定位为 honest synthetic regression，
然后逐步建设真正 human gold set
```

---

# 46. 最终建议

ScholarFlow 现在不需要继续扩展第 4 个 Skill，也不需要再添加大量新角色。

下一阶段最有价值的目标应是：

```text
Make every existing promise executable,
make every executable behavior contract-valid,
and make every validation claim proportionate to its evidence.
```

中文：

> **让每一条架构承诺真正进入执行链，让每一份执行产物真正符合统一契约，让每一句“已验证”都与实际证据强度相匹配。**

如果完成本文 P0 + P1 项目，ScholarFlow 会从当前：

> “架构非常先进、实现快速增长，但存在集成债务”

进入：

> **“执行入口、证据契约、跨学科机制和验证声明相互一致的稳定科研 Agent Workflow”。**

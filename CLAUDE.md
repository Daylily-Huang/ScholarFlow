# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

ScholarFlow 是面向严谨科研的智能体文献全生命周期工作流套件（Agent Skills Suite），完整覆盖从假说推敲到文献调研的 **4 个核心技能**：

1. `research-idea-debate` — 研究构想与假说推敲（五类苏格拉底视角讨论、单轮单问交互协议、想法成熟度守卫 RAW→TESTABLE、独立反例质询与确定性分歧判定、查证缺口双向交接）
2. `literature-discovery-acquisition` — 文献系统发现、初筛与全文获取（OpenAlex 检索、双向引文滚雪球、商业库题录摄取、双评阅人 κ 一致性）
3. `literature-evidence-extraction` — 证据可信抽取与声明审计（Quote-First 逐字引句、0-10 相关度剪枝、E1-E4 溯源/强度解耦）
4. `literature-synthesis` — 学术争议发掘与跨文献综合（加权证据评价、非多数决共识梯队、Claim ID 门禁）

核心设计：**防幻觉**（结论锚定带页码的原文引句）、**零强制第三方依赖**（全部运行时逻辑基于 Python 3.9+ 标准库，可选 `pip install "scholarflow[pdf]"` / `.[dev]`）。

## 测试与质检命令

```bash
# 全量测试（unittest，零第三方依赖；CI 在 Python 3.9/3.11/3.13 上跑）
python -m unittest discover -s tests -v

# 单个测试文件 / 单个用例
python -m unittest tests.test_quote_audit -v
python -m unittest tests.test_quote_audit.ClassName.test_method -v

# 科研回归基准（注意：Discovery/Extraction 基准是合成夹具自检，不代表在线召回质量）
python benchmarks/run_benchmarks.py

# 跨学科中立性 linter（CI 门禁之一）
python scripts/domain_neutrality_linter.py

# 打包资产校验 / 构建 wheel
python scripts/verify_package_assets.py
python -m build --wheel

# 技能脚本内置自测（CI 单独跑的四条）
python skills/literature-evidence-extraction/scripts/context_expansion.py --test
python skills/literature-discovery-acquisition/scripts/calculate_screening_agreement.py --test
python skills/research-idea-debate/scripts/validate_session.py --self-check
python skills/research-idea-debate/scripts/session_store_cli.py --help
```

严格契约校验需要 jsonschema（CI 的 contract-validation job 在 `pip install -e ".[dev]"` 后运行，并通过 `SCHOLARFLOW_STRICT_CONTRACT_CI=1` 环境变量开启）。本地跑全量测试前建议先 `pip install -e ".[dev]"`，否则 schema 相关测试会跳过。

## 架构大图

**两层分发模型**（README「分发模型契约」一节）：

- **`shared/`** — 可 `pip install scholarflow` 的纯标准库运行时引擎：
  - `context_resolution/` — Stage 0A 五层来源解析（current_user > conversation > current_attachments > upstream_outputs > project_search）
  - `grill_me/` — Stage 0B 自适应追问引擎（只问未决高影响维度，每轮上限 4 题）
  - `execution/` — 统一执行深度与预算总账（profiles/config/context/budget/artifacts + debate_handoff/session_store/subprocess_utils）
  - `domain_lenses/` — 9 大学科透镜（静态 .md，经 importlib.resources 打包）
  - `core/`、`security/`、`validation/`（schema_gate）、`version.py`（版本单点，当前 0.6.6）
- **`skills/`** — 四个 Agent 技能（SKILL.md + scripts/references/role/assets），按 `scripts/install.sh` / `install.ps1` 安装到宿主 Agent

**`schemas/`** — 跨技能数据契约（JSON Schema）：execution_profile、evidence_record、claim_record、discovery_result、extraction_result、synthesis_record、research_debate_* 等。技能间通过 Envelope 契约单向传递，修改任何 schema 必须同步跑 `test_cross_skill_contract.py` / `test_cross_skill_roundtrip_contract.py` / `test_schema_gate.py`。

**两条贯穿全仓的硬门禁**（写代码前必须理解）：

1. **执行深度门禁**：任何实质执行（检索/下载/抽取/讨论）前必须确认执行深度（quick/standard/deep 三档）。`ExecutionProfile` 只是资源上限模板，不等于运行授权——只有经确认的 `RunExecutionConfig`（`runs/<run_id>/execution_profile.json`，写前校验 + 原子替换）才解锁执行；`RunContext` 携带同一份确认配置与预算台账贯穿四个技能，超出上限显式标记为未处理而非静默丢弃。未确认配置一律不得保存为已授权状态。
2. **Stage 0 决策门禁**：0A 上下文解析 → 0B 追问（输出提问清单后必须立即停止回复、静默等待，严禁自问自答）→ 0C 协议快照放行。已知要素自动继承、严禁重复发问。

## 能力状态真相来源

`docs/CAPABILITY_STATUS.md` 是**四个**技能能力的**唯一权威说明**，能力分四级：`CODE_VERIFIED`（有代码+测试，**仅覆盖结构与行为两层，不含科研正确性**）/ `PARTIAL`（部分路径已实现，缺口明确未实现）/ `HOST_EXECUTED`（只有规程和提示词，效果取决于宿主 Agent 遵循度）/ `HUMAN_CONFIRMED`（必须人工裁定）/ `NOT_SUPPORTED`（不交付）。

写代码或修改文档前必读，尤其注意：

- `HOST_EXECUTED` ≠ 已实现。SKILL.md 里 `[PROTOCOL]` 标签描述的是规程性质，不是执行保证。
- 该文档 §6 列出 README/SKILL 中**仍会误导用户的表述**（如「9 类争议」实为 3 类、「四级级联去重」实为两级、Stage 0「自动识别已知信息」实为约 5 类固定正则），与它冲突时以它为准。
- Stage 0 提问上限为每轮 4 题（`MAX_QUESTIONS_PER_ROUND = 4`）。

## 设计文档与变更流程

- `docs/rfcs/` — RFC 归档（RFC-001 ~ RFC-016），README.md 首页有状态表（`IMPLEMENTED` / `PARTIALLY IMPLEMENTED` / `PENDING`）。新功能应先落 RFC 再实现。
- 功能变更通常同时触及：`shared/` 引擎 + `schemas/` 契约 + `skills/*/SKILL.md` 规程 + `tests/` 机械门禁 + `docs/CAPABILITY_STATUS.md` 状态行。只改一处而不联动其余，会被现有契约/文档一致性测试（`test_doc_consistency.py`、`test_contract_closure_v062.py` 等）拦截。
- 测试套件是机械门禁的落地形态：引句回查（quote_audit）、主张-证据对齐（claim_alignment）、Cohen's κ 闭式解、NOT_REPORTED 零权重隔离、跨学科中立性等均有对抗用例（`test_adversarial_gates.py`）。

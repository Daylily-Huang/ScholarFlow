# ScholarFlow 能力状态表 (Capability Status Matrix)

> **目的**：把"文档里写了什么"与"实际由谁保证"分开记录。
> 本表是**四个 Skill** 的能力**唯一权威说明**；当 SKILL.md 的描述与本表冲突时，以本表为准并应提 issue 修正 SKILL.md。

## 状态定义

| 状态 | 含义 | 用户应如何对待 |
|---|---|---|
| `CODE_VERIFIED` | 有实际执行路径，且有行为测试覆盖 | 可直接依赖 |
| `PARTIAL` | 部分路径已实现；列出的缺口明确未实现 | 只依赖说明中已确认的那部分 |
| `DEFERRED` | 已判定应做但**本轮明确暂缓**，当前行为保守（宁可阻断） | 不要按"已完成"使用；需要时先排期 |
| `HOST_EXECUTED` | 只有操作规范与提示词，实际效果取决于宿主 Agent 的遵循程度 | 需抽查产物；不要把规范当成已执行的保证 |
| `HUMAN_CONFIRMED` | 自动判断不足以保证正确，必须由人最终裁定 | 关键结论必须人工复核 |
| `NOT_SUPPORTED` | 明确不交付；调用会得到显式缺口或错误 | 不要期待该能力存在 |

> [!IMPORTANT]
> `HOST_EXECUTED` **不是**"已实现"的同义词。它表示 ScholarFlow 提供了规程，但不保证宿主执行到位，也不保证执行质量。

> **检索式语言（2026-09-13 实测修正）**：`to_executable_query()` 现在按语言分路生成——
> 英文主题只出拉丁词，中文需求句不再混入；实测同一缺口由「直接命中 0 条、退回无关滚雪球」
> 变为「直接命中 8 条」（`sympatric black muntjac Reeve's diet overlap`）。

### `CODE_VERIFIED` 到底验证了什么（审查 F10）

`CODE_VERIFIED` **只覆盖前两层**，不得外推为科研正确性已验证。四层验收分级：

| 层级 | 验证内容 | 本表标注方式 |
|---|---|---|
| **L1 结构** | Schema、路径、字段形状 | 计入 `CODE_VERIFIED` |
| **L2 行为** | 失败门禁、授权绑定、恢复、幂等、引用溯源 | 计入 `CODE_VERIFIED` |
| **L3 科研质量** | 真实论文金标的字段准确率、数值/单位正确率、主张与证据方向准确率 | **未验证**；需要人工复核金标 |
| **L4 工作流** | 同任务、同模型、同预算下的召回、交付质量、时间与 token | **未验证**；需要对照评测 |

> **测试通过 ≠ 科研正确。** 套件全绿只证明 L1/L2。L3/L4 未建设，任何据此得出的
> 准确率或能力排名都缺乏依据。金标须由人工复核并保存判定依据，
> **不得用同一 Agent 生成答案再自评分**。

### 测试到能力的映射（审查 F10）

每项能力应可追溯到实现入口与对应测试；本表在每行"证据"列给出实现位置。
机械门禁与测试锚点：

| 门禁 / 测试 | 覆盖的能力层 |
|---|---|
| `tests/test_research_debate_handoff.py` | 授权指纹绑定、范围失效、引句对齐（L2） |
| `tests/test_four_skill_review_f01_f06.py` | R01–R06 反例回归：语义核验默认未决、数值量纲、可信事件授权、事件先行基底、修复产物契约（L2） |
| `tests/test_third_review_t01_t05.py` | T01–T05 反例与正例：十进制相等、单位倍率/千分比、未知单位阻断、封存原子性与中断识别、零事件检查点重放（L2） |
| `tests/test_research_debate_session_store.py` | 事件日志恢复、快照一致性、外键修复（L2） |
| `tests/test_quote_audit_gate.py` / `test_quote_audit.py` | 引句回查与数值锚定门禁（L2） |
| `tests/test_cross_skill_contract.py` / `test_cross_skill_roundtrip_contract.py` | 跨技能 Envelope 契约（L1） |
| `scripts/domain_neutrality_linter.py` | 核心文件学科中立性（L1） |
| `scripts/verify_package_assets.py` | 打包资产完整性（L1） |

**最后验证记录**：`709 tests OK (skipped=4)`，对应提交见本表末尾脚注；跳过项为
`jsonschema` 严格契约（未装 `[dev]`）与 Windows 侧 bash 不可用项，属**未验证**而非通过。

**已知未覆盖场景（不得据本表外推）**：

- 第四技能的真实宿主端到端流程（缺口确认 → 上游返回 → 支持/反证回流 → 保存 → 恢复）**尚未执行**。
- 隔离安装环境下的复用性验证曾因环境权限跳过，**未补验**；「单技能目录复制即可用」仍不成立。
- 历史已自动标记为 `VERIFIED` 的旧记录**未被重审**，只应作审计器版本标注与重审清单处理。

---

## 1. literature-discovery-acquisition

| 能力 | 状态 | 证据 / 说明 |
|---|---|---|
| OpenAlex 元数据检索 + 游标分页 | `CODE_VERIFIED` | `agent_search.py`；含 `reported_total_hits` / `pages_fetched` / `coverage_status` |
| 双向引用滚雪球 | `CODE_VERIFIED` | `run_snowball_search`（referenced_works + cites） |
| 覆盖度真实性规则（失败≠0 篇、截断≠完全检索） | `CODE_VERIFIED` | `retrieval_coverage.evaluate_coverage_status` |
| Gate A 发现覆盖门禁 | `CODE_VERIFIED` | 各项由台账计算；无法判定时记 `unknown` 而非 PASS |
| 运行级候选总额与真实轮数报告 | `CODE_VERIFIED` | `RunContext` + `configured_limits` / `actual_usage` |
| 商业库题录硬解析（CNKI/WoS/RIS/EndNote/CSV） | `CODE_VERIFIED` | `ingest_external_records.py` |
| 下载输入契约校验（四类结果分派） | `CODE_VERIFIED` | `load_candidate_records`：`OK` / `EMPTY` / `FAILED_UPSTREAM` / `InputContractError` |
| 双评阅人一致性统计（Cohen's κ） | `CODE_VERIFIED` | `calculate_screening_agreement.py`；**κ 是可选增强，PRISMA 2020 Item 8 只要求报告筛选人数与是否独立** |
| 概念矩阵构建（正交桶 + 同义词扩展） | `HOST_EXECUTED` | 脚本侧仅为首尾词启发式；真实扩展式由 Agent 按 `concept_matrix.md` 生成 |
| 期刊分层与投稿建议 | `HOST_EXECUTED` | `journal_mapping.md` 规范 |
| 双盲独立初筛流程本身 | `HOST_EXECUTED` | 代码只在事后统计；"盲"由 Agent 调度保证 |
| 饱和度判定（边际概念收敛） | `HOST_EXECUTED` | 代码只报边际增益；收敛结论由 Agent 判定 |
| 四级级联去重 | `PARTIAL` | 实际为两级（DOI 精确 + 标题精确）；PMID/arXiv/相似度未实现 |
| PRISMA-S 16 项审计 | `PARTIAL` | 结构完整，但部分条目为静态常量，不随执行变化 |
| Stage 8B 浏览器兜底下载 | `NOT_SUPPORTED` | 无实现；仅剩枚举值 |
| 商业库逆向抓取 | `NOT_SUPPORTED` | 明确不做（合规边界） |

---

## 2. literature-evidence-extraction

| 能力 | 状态 | 证据 / 说明 |
|---|---|---|
| 逐字引句回查（EXACT/HYPHEN/FUZZY/NOT_FOUND） | `CODE_VERIFIED` | `quote_audit.py`；**不校验页码**，页码来自 Agent 自报 |
| 数值—引句锚定（含单位与量纲） | `CODE_VERIFIED` | 完整数量解析（符号/数值/指数/单位）后按数值+量纲比较；同量纲按**精确十进制**因子换算（2.5 mL == 2500 µL，1 nL ≠ 2 nL），跨量纲不匹配；`bp/kb/mb` 分列，`%`=1/100、`‰`=1/1000；`%` ↔ 裸比例仅在字段声明 `value_type` 时互认 |
| 未知/复合单位的诚实阻断 | `CODE_VERIFIED` | 单位不在表内（如 `Gy`、`Sv`、`m/s`、`m2`）→ `dimension="unknown"`、保留原文，判 `UNKNOWN_UNIT` 并阻断；源文扫描**保留大小写**（`Gy` 不会被折成 `gy`），抽取值悄悄丢单位也会被 `UNIT_MISMATCH` 挡住；只有字段声明 `value_type=count/dimensionless` 且另一侧确实无量纲时才按数值比较 |
| 数值字面量边界 | `CODE_VERIFIED` | 千分位 `1,000` 与欧洲小数逗号 `2,5` 分别解析；`5%` ↔ `50‰` 在比例字段下等价、`5%` ≠ `5‰`；同量纲跨单位换算仅接受已登记倍率；含义不明确的符号（`mb`）不登记 |
| 数值核验覆盖边界 | `PARTIAL` | **已覆盖**：抽取值带未知/复合单位、源文未知单位（含大小写符号与两字母小写单位）、量纲错配、未锚定、不可解析。**未覆盖**：源文用 3 个以上字母的**生僻小写**单位、而抽取值又恰好丢了单位——这种组合仍可能通过；需要时把该单位登记进 `_UNIT_GROUPS` |
| 数值判定边界 | `CODE_VERIFIED` | 含数字却解析不出数量 → `UNPARSEABLE_VALUE`；数字对但单位/量纲不同 → `UNIT_MISMATCH`；距引句过远 → `NOT_IN_QUOTE_CONTEXT`；四类均计入 `unverified` 并触发硬门禁 |
| 主张—证据对齐硬门禁（A2） | `CODE_VERIFIED` | `claim_alignment.py` 五门禁 + fail-closed |
| AECE 上下文扩展（单句→相邻句→段落→结构化） | `CODE_VERIFIED` | `context_expansion.py`；`SECTION_CONTEXT` / `CONTEXT_UNIT` 两级未产出 |
| 长距离拼接拦截 | `CODE_VERIFIED` | 跨页 / 间隔 >1500 字符 / Intro-Results 混拼 |
| 表格单元格与图注证据提升 | `CODE_VERIFIED` | 原为崩溃路径，已修；保留原始单元格内容，拼接上下文单独标注为解释性 |
| 抽取溯源四级（`support_type`） | `CODE_VERIFIED` | 提升路径按语义推导 EXPLICIT / REFERENCED / DERIVED / NOT_REPORTED，不再硬编码 |
| 结构化定位保留（表号/行头/列头/单位/脚注） | `CODE_VERIFIED` | `location.table_or_figure_id` 等字段随提升保留 |
| 0–10 相关度前置剪枝 | `CODE_VERIFIED` | `audit_claims.py`；空 topic 边界行为见已知限制 |
| 上下文充分性审计（第 16 项） | `CODE_VERIFIED` | `audit_context_sufficiency` |
| 多实验体系隔离 | `HOST_EXECUTED` | 由 Agent 按 `assay_context_isolation.md` 执行 |
| Evidence Auditor 完整清单（16 项） | `PARTIAL` | 仅第 16 项有代码；其余为 Agent 规程 |
| 事实 / 推论物理隔离 | `HOST_EXECUTED` | 依赖 Agent 遵守 `interpretation_boundary.md` |
| OCR 零容忍防护 | `PARTIAL` | 仅覆盖 μL / °C / ± / 引物碱基；非生命学科无防护 |
| 表格/图表的语义理解 | `HUMAN_CONFIRMED` | 代码只定位与结构化，不裁决语义 |
| 扫描件无文本层的光学识别 | `NOT_SUPPORTED` | 无内置 OCR 后端 |
| MD 轨产物生成 | `HOST_EXECUTED` | JSON 与 HTML 有代码，MD 由 Agent 撰写 |

---

## 3. literature-synthesis

| 能力 | 状态 | 证据 / 说明 |
|---|---|---|
| 加权证据评价（directness/independence/risk_of_bias/replication） | `CODE_VERIFIED` | `controversy_analyzer.resolve_evidence_weight` |
| 独立性组权重封顶 + STRONG 需 ≥2 已验证独立组 | `CODE_VERIFIED` | 实测通过 |
| 非篇数多数决 | `CODE_VERIFIED` | 8 篇弱反证不敌 1 篇强实证，实测 |
| 已核验反证的有界加权 | `CODE_VERIFIED` | `controversy_analyzer.apply_verified_challenges()`：`WEAKENS` 0.25 / `REFUTES` 0.5，同来源组封顶 0.5，权重不为负；反证记录**不计入立场权重**（`CHALLENGE_EVIDENCE`），5 条 `REFUTES` 只把支持压到 `INSUFFICIENT_EVIDENCE`，`REFUTE` 权重保持 0；未核验反证零影响。测试 `tests/test_rfc017_challenge_channel.py` |
| 可比性分层（6 维） | `CODE_VERIFIED` | `comparability.py` |
| 层内结论与跨层差异分别披露 | `CODE_VERIFIED` | 头条取全量主张；分层方向分歧显式披露，不再以单层代表整体 |
| Claim ID 可溯源门禁 | `CODE_VERIFIED` | `claim_linter.py` |
| Mermaid 论证拓扑图 | `CODE_VERIFIED` | 有静默截断（支持/反驳各 4 篇、条件 3 篇） |
| canonical SynthesisRecord 输出 | `CODE_VERIFIED` | 通过 schema 校验 |
| 9 类争议分类（Type A–I） | `PARTIAL` | 实现 A/B/D 三类分支；C/E/F/G/H/I 未实现 |
| 6 级共识梯队 | `CODE_VERIFIED` | 层级判定与零权重不入共识均为实测行为 |
| 学派与范式演进图谱 | `PARTIAL` | 确定性分桶 + 时间排序，非无监督聚类 |
| Devil's Advocate 红队质询 | `HOST_EXECUTED` | 仅 role 文档；无代码强制 |
| Gatekeeper 10 项终审 | `HOST_EXECUTED` | 同上 |
| SEARCH GAP / EXTRACTION GAP 回传 | `HOST_EXECUTED` | 有字段与模板，无生成代码 |
| 争议类型归因（"差异由方法造成"） | `HUMAN_CONFIRMED` | 方法差异只能提示相关性，不能证明因果归因 |
| 域中立化的领域规则隔离 | `PARTIAL` | `comparability.py` / `claim_alignment.py` 含硬编码学科规则；linter 尚未扫描 `.py` |
| M1/M2/M4（DocumentBundle / ExtractionProvider / 敏感性分析） | `NOT_SUPPORTED` | RFC-013 设计中，未实现 |
| D1–D5（多源调度 / 查询计划 / 多种子前沿） | `NOT_SUPPORTED` | RFC-013 设计中，未实现（D0 分页已实现） |

---

## 3.5 research-idea-debate（研究构想与假说推敲）

| 能力 | 状态 | 证据 / 说明 |
|---|---|---|
| 五类苏格拉底视角角色与调度阶梯 | `HOST_EXECUTED` | `role/*.md` 规程；P0–P6 由 Agent 按规程执行 |
| 想法成熟度守卫（RAW / DEVELOPING / TESTABLE） | `HOST_EXECUTED` | `references/maturation_and_gates.md` |
| 单轮单问交互协议 | `HOST_EXECUTED` | `references/dialogue_protocol.md` |
| 独立反例质询与确定性分歧判定 | `CODE_VERIFIED` | `shared/execution/debate_handoff.py: `_compare()` / `compare_evidence_links()`；测试 `tests/test_research_debate_handoff.py` |
| **查证缺口授权绑定**（指纹 + 确认事件 + 范围/版本） | `CODE_VERIFIED` | `prepare_dispatch()`；**必须提供可信事件上下文**（`SessionStore`），缺上下文即 `CONFIRMATION_CONTEXT_MISSING`；核验事件类型为用户确认类、`execution_kind=USER`、会话/gap/构想/版本/范围指纹逐项匹配；比对 `approved_idea_version` 与 `idea_version`；阻断 `RUNNING` 在途请求。测试 `tests/test_research_debate_handoff.py`、`tests/test_four_skill_review_f01_f06.py` |
| **缺口派发前门禁** | `CODE_VERIFIED` | 未确认 / 范围变更 / 版本变更 / 未绑定确认事件 / 非用户事件 / 在途执行一律不得派发；`gap._events` 等自述事件不构成授权；覆盖边界：仅校验本会话内绑定，不校验上游文献真实性 |
| 引句对齐入向适配（`to_evidence_link`） | `CODE_VERIFIED` | `to_evidence_link()`；强制要求 `artifact_ref` 溯源；区分 `EXACT` / `FRAGMENT` / 否定句 |
| **命题—引句一致性门槛** | `PARTIAL` | 引句须覆盖命题比对单元 ≥ **0.85** 才升级。实测：逐字同句 1.000/轻微改写 0.975 → `VERIFIED`；**忠实意译 0.709、中文命题+英文证据 0.575/0.512 → `UNRESOLVED`**。即「用自己的措辞陈述命题」不会升级。用法要求命题用证据语言、按原文用词陈述；跨语言须有与原文用词一致的已确认译文。阈值是设计选择（不降低科学准入），已在 `to_evidence_link` 与 `references/evidence_handoff.md` 写明 |
| 语义支持核验 | `CODE_VERIFIED` | **默认 `UNRESOLVED`**：模式规则只用于排除（设问/假说/模拟假设/转引/条件/被反驳），未命中不等于已证实；只有绑定完整的显式语义凭据（`evidence_id` + 命题指纹 + `verifier` + `verification_ref`，且命题版本未过期）才允许 `VERIFIED`。覆盖边界：凭据由核验环节写出，本层不生成语义判断 |
| **反证通道（RFC-017 / F09）** | `CODE_VERIFIED` | 新增独立字段 `challenge_status` / `challenge_scope` / `challenge_strength` / `challenge_basis`，**`alignment` 语义不变**（非 SUPPORT 永远不是 `VERIFIED`）。四项裁定已落代码：①**必须人工复核**（`confirmed_by=user` + 事件可追溯；提供 `SessionStore` 时须在可信日志核验通过）；②**参与综合加权但封顶**（`WEAKENS` 0.25 / `REFUTES` 0.5，同来源组合计 ≤0.5，只扣被挑战主张、**不转移给对立立场** → 反证再多也只能压到证据不足，不会形成反证多数决）；③**强度分级**（`REFUTES` 必须给 `refutation_basis`）；④绑定门槛与 SUPPORT **同级**（溯源/定位/范围/命题指纹）。反例覆盖：支持句冒充反证、无关句、非用户事件、`applied=false`、缺复核、越界枚举。测试 `tests/test_rfc017_challenge_channel.py` |
| **会话事件日志与恢复** | `CODE_VERIFIED` | `shared/execution/session_store.py`；完整追加边界保护（末尾无换行时安全补行分隔）、坏尾部须显式恢复（F03）、快照比较业务投影（F04）；测试 `tests/test_research_debate_session_store.py` |
| 授权事件的真实性边界 | `CODE_VERIFIED` | 用户确认事件必须是已生效事件（`applied=false` → `CONFIRMATION_EVENT_NOT_APPLIED`）；同一 `event_id` 出现多次 → `CONFIRMATION_EVENT_AMBIGUOUS`；事件日志损坏 → `CONFIRMATION_CONTEXT_UNREADABLE`（与"没给上下文"区分） |
| **事件先行可信重放基底** | `PARTIAL` | `seal_checkpoint()`：封存全量状态 + 事件前缀摘要 + `event_count` + `last_event_id`，未封存会话一律报 `SNAPSHOT_BASE_UNVERIFIED`；重放边界以 `event_count` 为准（零事件检查点不会跳过后续事件），并校验前缀摘要/边界一致性。**未完成**：`save_snapshot()` 仍只是调用约定（无法从代码上阻止写入未记录字段），尚无强制事件先行的写入入口 |
| 检查点信任边界与历史导入 | `CODE_VERIFIED` | 检查点自述 `inherited_fields` + `trust_boundary` + `import_mode/reason/source`；已有检查点后引入新的、事件未记录的业务字段必须显式 `import_mode=True` 并给出理由与来源，否则拒绝封存。**不得宣称"全部业务状态由事件证明"** |
| 两文件一致提交与中断识别 | `CODE_VERIFIED` | 封存前完成 revision 校验（失败时快照与检查点均不变）；快照与检查点经 `commit_journal.json` 一致提交，中断留下提交日志 → `consistency_report()` 报 `INCOMPLETE_COMMIT`，`recover_commit()` 完成或回滚；CLI `seal` 支持 `--import-mode/--import-reason/--import-source` |
| **契约校验前置到修复路径** | `CODE_VERIFIED` | `heal_referential_integrity()` 生成的占位立即过 `research_debate_gap.schema.json`；不合规输出转入 `repair_proposals` 而非正式 `gap_requests` |
| **外键修复不得制造授权** | `CODE_VERIFIED` | `heal_referential_integrity()` 只生成 `PENDING` 占位，不伪造 `CONFIRMED`（F06/R06）；占位以 `healed_placeholder=true` 显式标记，Schema 据此放开空关联并强制 `execution_status=NOT_STARTED`；测试 `tests/test_research_debate_session_store.py` |
| 缺口确认 → 上游返回 → 支持/反证分别回流 → 保存 → 恢复 | `HOST_EXECUTED` | 端到端真实宿主流程**尚未执行** |
| 讨论对文献质量的独立判断 | `HUMAN_CONFIRMED` | 不得以讨论中的说服力替代证据核验 |

---

## 4. Stage 0 上下文解析与提问

> 结论先行：**五层来源的管道与冲突检测是 `CODE_VERIFIED`；"自动识别已知信息"这一层是 `HOST_EXECUTED`。**
> 区别很重要——代码只做固定模式匹配，真正的语义理解由宿主 Agent 承担。

| 能力 | 状态 | 证据 / 说明 |
|---|---|---|
| 五层来源 Provider 管道与优先级 | `CODE_VERIFIED` | `current_user`(6) > `conversation`(5) > `current_attachments`(4) > `upstream_outputs`(3) > `project_search`(2) |
| 《现有科研上下文确认简报》生成 | `CODE_VERIFIED` | `render_context_brief_markdown()` |
| 已解析维度不再重复提问 | `CODE_VERIFIED` | 实测：深度/语言/时间/学位论文四类经上下文确认后不再入题 |
| 同级冲突检测与仲裁提示 | `CODE_VERIFIED` | 无时间戳的同层资料矛盾 → `UNRESOLVED_CONFLICT` + 简报显式列出 |
| 上游产物继承 | `CODE_VERIFIED` | 绑定 `run_id`；证据可用但资源授权不转移 |
| **从自由文本自动识别已知信息** | `HOST_EXECUTED` | 代码为**固定关键词正则**，无任何语义理解。实测覆盖见 §4.1；自然语言表述多数不被识别 |
| 从项目文件自动识别已知信息 | `HOST_EXECUTED` | 仅认**带标签键值对**（`目标对象: XXX`）；自由描述不识别 |
| Grill 引擎自动装配上下文解析 | `NOT_SUPPORTED` | `select_questions()` 仅在调用方显式传入 `context_resolver` 时解析；引擎不自行装配 |

### 4.1 固定模式的实测覆盖（这是真实边界）

| 层 | 可自动识别的输入 | 实测结果 |
|---|---|---|
| 当前用户消息 | `这次用深度模式` | `EXECUTION_DEPTH=deep` |
| 当前用户消息 | `仅限英文文献` | `D10=en_only` |
| 当前用户消息 | `不要学位论文` | `D9` |
| 历史对话 | `用标准档` | `EXECUTION_DEPTH=standard` |
| 历史对话 | `要中英文都查` | `D10=en_and_zh` |
| 历史对话 | `2020-2024年的文献` / `2020年至今` | `D8=2020-2024` / `2020-present` |
| 历史对话 | `研究对象是杉木人工林` | **未识别** |
| 项目文件 | `目标对象: 杉木人工林` | `D3=杉木人工林` |
| 项目文件 | `本研究聚焦杉木人工林生物多样性` | **未识别** |

**总计约 5 类模式覆盖约 4 个维度**（`EXECUTION_DEPTH` / `D8` / `D9` / `D10`，加项目文件的 `D3`），
而维度表共有 41 个维度。因此文档中"自动识别多队列/多数据集、已知约束自动确认"的表述
**强于实现**。

**为什么不影响可用性**：宿主 Agent 能直接读懂对话与文件，并通过 `select_questions()`
的 `inferred_values` 入口注入已知值。代码这层只是确定性预检，不是唯一入口。

### 4.2 一处容易误读的实现

`ProjectSearchContextProvider` 会产出 `SAMPLE_SIZE` 事实，但**该键不属于任何技能的维度表**，
`GrillEngine` 从不请求它，因此在正常 Stage 0 流程中不会生效。
它保留是因为被同级冲突检测的测试用作载体（两份项目文件样本量不一致 → `UNRESOLVED_CONFLICT`）。
**不要把它当作"支持样本量抽取"。**

---

## 5. 跨技能与平台

| 能力 | 状态 | 证据 / 说明 |
|---|---|---|
| 统一执行深度三档 | `CODE_VERIFIED` | 预设 ≠ 运行授权；未确认配置不得保存 |
| 运行配置契约与往返一致性 | `CODE_VERIFIED` | `RunExecutionConfig` + schema 校验 + 原子写入 |
| 运行级预算与阶段计划 | `CODE_VERIFIED` | `RunContext`；模型/数据库请求分开计数 |
| Token 计量诚实性 | `CODE_VERIFIED` | 由观测计数推导；部分观测标注为下界 |
| 预算硬上限（抢占式） | `NOT_SUPPORTED` | 请求 `hard` 会显式降级为 `best_effort` 并写入回执 |
| 跨运行资源授权隔离 | `CODE_VERIFIED` | 绑定 `run_id`；证据可用但授权不转移 |
| 阻塞态恢复 | `CODE_VERIFIED` | `resume_input()` / `RunContext.resume()` |
| 一键安装运行时完整性 | `CODE_VERIFIED` | 单一 `shared` 副本 + 隔离解释器验收 |
| 断点续跑（阶段中途精确接续） | `PARTIAL` | 可重建剩余额度，不支持单篇处理中途接续 |
| 宿主图表理解能力 | `HOST_EXECUTED` | 记为能力缺口，不输出"已穷尽审计" |
| 真实论文质量评测（Level 3–4） | `NOT_SUPPORTED` | 尚未建设真实金标测试集 |

---

## 6. 已知会误导用户的表述（应视为缺陷）

以下是文档中**仍然存在**但与本表冲突的表述，按本表为准：

1. README「9 大学术争议分类学体系」——实际实现 3 类（见 §3）。
2. README「四级级联去重」——实际两级（见 §1）。
3. README「Stage 8B 浏览器兜底」——无实现（见 §1）。
4. README/SKILL 中把 `HOST_EXECUTED` 项以 `[DETERMINISTIC]` / `[PROTOCOL]` 标签呈现的部分（如双盲初筛、Devil's Advocate）——标签描述的是**规程性质**，不是执行保证。
5. `benchmarks/` 中 Discovery 与 Extraction 两项为**合成夹具自检**，不代表在线召回或真实抽取质量。
6. SKILL.md 称 Stage 0A「自动识别多队列/多数据集、已知约束自动确认」——实际为约 5 类固定正则、
   覆盖约 4 个维度（见 §4.1），自由文本表述多数不被识别。
7. Stage 0 提问**上限为每轮 4 题**（`MAX_QUESTIONS_PER_ROUND = 4`）。Discovery 有 6 个 CRITICAL
   维度，因此会有 2 个进入第二轮显式确认，而非静默默认。
8. README 第 0 节把 `research-idea-debate` 的「混合 Agent 独立评估」与 `[DETERMINISTIC]` 并列——
   **仅分歧判定**是确定性程序；「独立评估」是 `HOST_EXECUTED` 规程，且同模型两次作答不构成
   独立性（见 §3.5）。
9. 同节「质量审查员恪守 12 项合规硬门禁」为 `role/quality_gatekeeper.md` 的**检查表规程**，
   仓库内无对应代码实现（`grep -r quality_gatekeeper shared/ scripts/` 无结果），属 `HOST_EXECUTED`。
10. 第四技能的「候选研究问题 / 最小验证方案」由宿主按规程产出，属 `HOST_EXECUTED`；
    其端到端真实流程尚未执行，不得呈现为确定性交付。
11. 「单技能目录复制即可用」不成立——技能依赖 `shared/` 共享运行时；复用性验证在隔离安装
    环境**未补验**（见 §5）。
12. 把「词面命中 / 数值在文中出现」当作已证实：`text_match` 只回答字面重合，语义支持另有
    绑定要求；数值必须数值+量纲同时对齐。未提供绑定完整的语义凭据时一律 `UNRESOLVED`。
13. 把「传了 `confirmed_event_id`」当作已获授权：授权要求可信事件上下文 + 用户来源 +
    会话/gap/构想/版本/范围逐项绑定（见 §3.5）；只给字符串 ID 不再放行。
14. 「快照 = 事件重放结果」在未封存检查点时不成立：此时 `consistency_report()` 报
    `SNAPSHOT_BASE_UNVERIFIED`，不得把 `consistent=true` 当作真源一致性证明。

---

## 7. 本表的验证绑定

- **实现提交**：`e8b3d14`（含 RFC-017 反证通道；预算映射 `bc5555f`；F1/F2 `b091516`；T01–T05 主体 `8a267e2`）
- **测试结果**：`Ran 871 tests ... OK`（本机 0 项跳过；跳过 ≠ 通过）
- **报告**：`docs/implementation/ScholarFlow_第三次修改验收修复报告_2026-09-13.md`
  （前两轮：`ScholarFlow_R01-R06第二轮修复报告_2026-09-13.md`、
  `ScholarFlow_四技能审查修复批次报告_2026-09-12.md`，后者已标注"全部验收"表述过度）

> 本表的 `CODE_VERIFIED` 仅覆盖上表 L1/L2 层，且只对该提交有效；实现变更后须重新核对本表。

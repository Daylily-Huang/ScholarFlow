# ScholarFlow 能力状态表 (Capability Status Matrix)

> **目的**：把"文档里写了什么"与"实际由谁保证"分开记录。  
> 本表是三个 Skill 的能力**唯一权威说明**；当 SKILL.md 的描述与本表冲突时，以本表为准并应提 issue 修正 SKILL.md。

## 状态定义

| 状态 | 含义 | 用户应如何对待 |
|---|---|---|
| `CODE_VERIFIED` | 有实际执行路径，且有行为测试覆盖 | 可直接依赖 |
| `HOST_EXECUTED` | 只有操作规范与提示词，实际效果取决于宿主 Agent 的遵循程度 | 需抽查产物；不要把规范当成已执行的保证 |
| `HUMAN_CONFIRMED` | 自动判断不足以保证正确，必须由人最终裁定 | 关键结论必须人工复核 |
| `NOT_SUPPORTED` | 明确不交付；调用会得到显式缺口或错误 | 不要期待该能力存在 |

> [!IMPORTANT]
> `HOST_EXECUTED` **不是**"已实现"的同义词。它表示 ScholarFlow 提供了规程，但不保证宿主执行到位，也不保证执行质量。

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

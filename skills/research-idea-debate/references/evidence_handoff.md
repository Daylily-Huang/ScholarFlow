# 查证交接与证据回流 (Evidence Handoff)

> 加载时机：出现证据缺口、准备调用前三个技能、或证据回流需要判定对齐时读取。

## 一、可推进性原则：什么时候需要文献

只有当前判断**最终必须由外部经验事实决定**时才需要查证；否则留在概念讨论内完成。

| 情形 | 处理 |
|---|---|
| 命题成否取决于领域内已有什么证据、测量口径或既有结论 | 记 `EVIDENCE_NEED`，按下文提出查证 |
| 分歧在于定义选择、价值取舍、逻辑一致性，或可由已知事实直接推演 | **留在概念讨论**，不启动检索；主持人应说明"这一点我们自己能定" |
| 缺口是当前结论的唯一障碍 | `blocking = BLOCKING`，需用户确认后查证 |
| 缺口只影响确定程度或后续方案精细度 | `blocking = RECORDED`，记为待核实，不阻塞讨论 |
| 用户项目内已有可回答该问题的产物 | 优先复用，不为已有材料再发起检索 |

**硬约束**：`approval.status != CONFIRMED` 时，**禁止**调用检索、提取或综合技能。

## 二、六步交接流程

1. **说明缺口**：当前争议是什么 / 准备查什么 / 结果会改变哪个判断。
2. **等待用户确认范围**（`CONFIGURATION` 问句，不与实质问题捆绑）；若缺深度或新增预算，另行单独确认。
3. **优先复用**已有材料，仍须核对证据与当前命题的匹配。
4. **调用上游技能**：`SEARCH_GAP` → `literature-discovery-acquisition`；`EXTRACTION_GAP` → `literature-evidence-extraction`；`SYNTHESIS_REQUEST` → `literature-synthesis`。
   - 只传完成任务所需上下文；**不把整段私有对话写入外部检索式**。
5. **回流校验**：文件可读、schema 版本、记录引用、命题对应关系。结构合法 ≠ 语义证据有效。
   - **命题必须用证据的语言、按原文用词陈述（2026-09-13 实测）**：入向适配要求引句覆盖
     命题比对单元 ≥ **0.85**。实测「逐字同句 1.000 → 升级」「轻微改写 0.975 → 升级」
     「忠实意译 0.709 → 不升级」「中文命题 + 英文证据 0.58/0.51 → 不升级」。
     因此：**不要用自己的措辞去对应引句**；把待证主张写成引句本身或用词一致的命题。
     中文命题 + 英文证据在缺"与原文用词一致的已确认译文"时一律停在 `UNRESOLVED`，
     这是设计选择，不是故障。
   - **入向适配默认未决（R01）**：`to_evidence_link()` 只有在记录携带**绑定完整**的
     `semantic_verification` 凭据（`evidence_id` + 命题指纹 + `verifier` + `verification_ref`，
     且 `idea_version` 未过期）时才把引句升级为 `VERIFIED`；否则一律 `UNRESOLVED`。
     未命中"研究问题/假说/转引/条件/被反驳"等排除规则**不等于**已证实。
   - **数值必须数值 + 量纲同时对齐（R02）**：单位参与比较（`2.5 mL ≠ 2.5 µL`），
     跨量纲不匹配（百分比 ≠ 长度）；`%` 与裸比例只在字段声明 `value_type` 时互认。
6. **说明影响**：支持／削弱／限定／无法回答；更新对应版本，再提下一问。

## 二·补：反证的回流（RFC-017，已实现）

反证用 `relation = "CHALLENGE"` 回流，状态记在**独立字段**上（`alignment` 语义不变，非 SUPPORT
永远不是 `VERIFIED`）：

| 状态 | 何时 | 后果 |
|---|---|---|
| `VERIFIED_CHALLENGE` | 溯源/定位/范围/命题指纹绑定齐全 + `challenge_verification.status=VERIFIED` + **用户人工复核事件可追溯** | 参与综合加权（`WEAKENS` 0.25 / `REFUTES` 0.5，同来源组封顶 0.5，只扣被挑战主张） |
| `PENDING_HUMAN_CONFIRMATION` | 缺人工复核、或无可信存储无法核验确认事件 | 权重影响为 0，等待用户复核 |
| `REJECTED` | 引句实为**支持**命题、与命题无任何共同单元、或确认事件非用户产生 | 不计入任何加权 |
| `UNRESOLVED` | 缺凭据、缺绑定、`challenge_scope`/`strength` 非法、`REFUTES` 未给 `refutation_basis` | 只作背景记录 |

要点：①`REFUTES`（推翻）必须给出 `refutation_basis`；②反证记录**不充当 REFUTE 立场证据**，
再多反证也只能把被挑战主张压到"证据不足"，不会靠计数翻成反证多数；③中文命题 + 英文反证
仍受 0.85 覆盖率门槛限制（见上一条）。

## 三、授权的产生、失效与幂等

- **授权指纹**覆盖四项：`question`（要回答什么）、`scope`（范围与对象）、`target_skill`（交给谁）、`budget_ref`（资源引用）。
- 任一改变 → 旧确认 `INVALIDATED`，须**重新确认**；仅排版或措辞归一化后不变时不失效。
- 相同 `gap_id` + 相同指纹的重试**不得重复派发**；已完成任务（`execution_status = COMPLETE`）直接复用 `result_refs`。
- 用户拒绝查证时 `approval.status = REJECTED`，**缺口保留**在 `open_questions`，可继续讨论不依赖该证据的分支，不因缺证据中止整个会话。
- **恢复会话不视为新授权**：指纹未变则沿用；指纹缺失或不匹配则回到 `WAITING_GAP_CONFIRMATION`。
- **指纹不是授权证明（第二轮核查 R05）**：范围指纹只是任务内容摘要。派发前必须提供
  **可信事件上下文**（`SessionStore`，事件来自会话目录），并逐项核对确认事件：
  事件类型必须是用户确认类（`GAP_CONFIRMED` / `GAP_APPROVED` / `USER_CONFIRMATION`），
  `execution_kind` 必须是 `USER`，且事件的 `session_id` / `gap_id` / `idea_id` /
  `idea_version` / `scope_fingerprint` 必须与当前缺口逐项一致。
  缺上下文 → `CONFIRMATION_CONTEXT_MISSING`；`gap` 自带的 `_events` 等自述内容不予采信。
- **在途幂等**：`execution_status = RUNNING / IN_PROGRESS` 时重复请求返回
  `ALREADY_RUNNING_IN_FLIGHT`（不重复派发）；`COMPLETE` 返回 `ALREADY_COMPLETE_IDEMPOTENT`。

## 四、与上游既有载荷的映射（新增实现，不是既有接口）

上游技能现有的任务包字段为 `gap_type / target_skill / reason / suggested_query / date_range / mode`（抽取任务包为 `target_paper / required_fields`），**没有** `gap_id`、`approval`、`scope_fingerprint`。适配层做单向映射，仅填相关字段：

| GapRequest 字段 | 映射到上游载荷 | 备注 |
|---|---|---|
| `gap_type` | 同名 | `SYNTHESIS_REQUEST` 需映射为综合技能的检索/抽取缺口，或用任务描述直接传入 |
| `target_skill` | 同名 | 由 `gap_type` 决定，用户确认时可见 |
| `question` + `scope` | `suggested_query` / `target_paper` / `required_fields` | 只传完成任务所需上下文，不写会话原文 |
| `decision_impact` | `reason` | 供上游理解用途，不作为其内部判断依据 |
| `idea_version` + `scope_fingerprint` | 不映射 | 仅存于本技能记录，用于幂等与授权失效 |
| `execution_status` | 不映射 | 由本技能按回流结果更新 |

- 保留原始 `GapRequest` 与映射记录，**不反向覆盖**上游原文件。
- 不得把上游文档示例中的 `mode=deep` 当成自动深度选择——它不构成资源授权。

## 四之二、可执行检索式与候选记录（M3 实现细节）

- **`to_executable_query(gap)`**：把缺口转成可直接消费的检索式。只从 `scope.topic` 与 `question` 取词，
  **不把对话原文写进检索式**（第 2 节第 4 步的硬要求）；剥离"是否／哪些／如何"这类疑问句式，
  去重并截断到 `max_terms`。结果放进载荷的 `executable_query` 字段。
- **`candidates_to_records(discovery_result)`**：把上游 Discovery 的 headless 产物转成**候选**记录。
  **一律不带 `verbatim_quote`**——题录与摘要**不是**原文引句；`location` 为 `null`，
  并标记 `candidate_only = true` 与 `checked_scope = "仅题录与摘要（未获取全文）"`。
- **因此**：候选记录经对齐判定必然落在 `UNRESOLVED`。这是**预期行为**，不是缺陷——
  **候选命中 ≠ 证据**。要升级为 `SUPPORT`/`VERIFIED`，必须先把全文交给
  `literature-evidence-extraction` 抽取原文引句，再回流。

闭环实测（真实调用一次上游 headless 检索）：未确认 → `APPROVAL_NOT_CONFIRMED`；确认 → 派发；
上游返回 20 条候选（覆盖度 `PARTIAL`、分页 `TRUNCATED_BY_LIMIT`）→ 转 6 条候选记录（引句全空）
→ 对齐 `verified=0 / unresolved=6` → 抽取回流后才 `verified=1`。

**中文比对口径**：对齐判定用**拉丁词元 + 字符 2-gram** 并用，以**命题侧覆盖率 ≥ 0.85** 为 `OVERLAP` 门槛。
不得改回按空白/`\w+` 分词——中文无空格会把整段汉字切成一个 token，使"引句包含命题"也算不出相似度。

## 五、回流校验与对齐判定（最易出错的一步）

1. **结构与引用**：文件可读；schema 版本与记录 ID 可解析；引用的 `evidence_id` 在目标文件内存在。任一步失败即**拒绝该批导入**，报告具体记录，不静默丢字段。
2. **命题对应**：核对回流证据指向的字段或主张是否就是当前命题所需；不匹配时记为 `CONTEXT` 或退回，**不做近似替代**。
3. **对齐判定（硬规则）**：

   | 规则 | 要求 |
   |---|---|
   | `alignment = VERIFIED` | **仅当**回流记录的 `verbatim_quote`（或等价原文锚点）与 `location` 在**命题本身**层面直接支持该命题 |
   | 共现不算支持 | 实体、变量、关键词、方法名的出现、共现或上下文邻近，一律判 `UNRESOLVED` |
   | `relation` 与判定一致 | `SUPPORT` 支持／`CHALLENGE` 削弱／`BOUNDARY` 限定条件／`CONTEXT` 仅背景 |
   | 禁止越用 | **禁止把 `CONTEXT` 当支持使用**；`CHALLENGE`／`BOUNDARY`／`CONTEXT` 均不得记 `VERIFIED` |
   | 无法回答 | 证据不能回答当前命题时进入 `UNRESOLVED`，不因关键词命中而升级 |
   | 必须留痕 | 每条 evidence_link 必须带 `checked_scope`，以区分"没找到"与"没查" |
   | **跨语言须标注** | 引句与命题**分属不同书写系统**（中文命题 vs 英文引句，或反之）时，覆盖率比对恒为 0，结果必然落在 `KEYWORD_ONLY` —— 这与"查了但文献确实不支持"**在结果上无法区分**。此时必须标 `language_mismatch: true`（`quote_match = LANGUAGE_MISMATCH`），并在汇报里说明这是"**机制上无法判定**"而非"判定为不支持" |

   **跨语言不得自动升级**：`language_mismatch` 是**知情标注**，不改变 `alignment`。合规的升级路径是
   **命题变体**（`ideas[].variants`），三条硬约束缺一不可：

   | 约束 | 检查点 |
   |---|---|
   | 用户确认 | `approval.status = CONFIRMED` **且** `confirmed_by = "user"`。**AI 自我确认无效**——自译自用等于自造一个更容易被命中的命题 |
   | 两条互相印证 | 需**两条**已确认译文，双向覆盖率均 ≥ 0.85。只有一条时无法区分"译得对"与"译得偏" |
   | 跟随命题 | `source_text` 必须等于**当前**命题；命题一改，旧变体自动失效 |

   **判定顺序**（先命中先返回）：①引句命中命题本身 → `VERIFIED`；②命中 ≥ 2 条互相印证的已确认变体 →
   `VERIFIED`（`quote_match = VARIANT_AGREEMENT`，记录实际使用的 `variant_ref`）；③只命中 1 条已确认变体 →
   `PENDING_CONFIRMATION`，**如实报覆盖率并请用户补第二条**；④命中多条但互不印证 → `VARIANT_DISAGREEMENT`，
   **把分歧交回用户裁决译法**；⑤只命中未确认/已失效变体 → `VARIANT_UNCONFIRMED`；⑥都不命中但有同语言变体记录 →
   `PENDING_CONFIRMATION`（这是**待办**，不是"不适用"）；⑦都不命中且无同语言变体 → `NOT_APPLICABLE`。

   **变体不等于新命题**：变体只是同一命题的另一种表述，**不得**新建 `IdeaRecord` 版本、**不得**改变成熟度、
   **不得**写进 `proposition` 字段。它只在证据对齐时充当参照物。
   **禁止**由 AI 自行翻译命题后直接比对；AI 可以**提议**译法，但必须由用户确认才生效。

4. **影响说明**：证据可能支持、削弱、限定或无助于当前命题；说明它改变了哪一项判断（前提状态、区分能力或决定），并更新对应 `IdeaRecord` 版本。
   英文文献支持中文命题时，汇报须同时给出引句原文与其**由你复述**的中文含义，并明确该含义是复述而非引文。
5. **诚实的空结果**：查不到、无法下载、缺全文、OCR 不确定、未报告参数**分别保留各自状态**。
   - 检索失败 ≠ 不存在研究；没有反证 ≠ 证实；`NONE_FOUND` 必须附 `checked_scope`。

## 六、概念讨论与文献讨论的分界示例

- "林下草本更少，是因为光不够，还是凋落物太厚？"——两个机制提案，若用户接受"先都当假说"，可继续概念讨论。
- "这两篇论文结论相反，是因为种子大小不同吗？"——若要判断"是否已有研究支持这一解释"，属外部经验事实，需查证；若只是比较两个解释哪个更可检验，可继续概念讨论。
- "有没有人做过这个？"——需要查证；**未完成查证前，新颖性一律标"待核实"，不得宣称首次发现。**

## 七、记录字段

`GapRequest` 字段与枚举见 [gap_request.schema.json](../../../schemas/research_debate_gap.schema.json)；相关事件类型：`GAP_PROPOSED`、`GAP_CONFIRMED`、`GAP_REJECTED`、`EVIDENCE_IMPORTED`、`CHECKPOINT`。

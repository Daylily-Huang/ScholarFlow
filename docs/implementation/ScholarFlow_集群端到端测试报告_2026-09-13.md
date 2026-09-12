# ScholarFlow 四技能集群端到端测试报告（2026-09-13）

- **触发**：用户要求"最大能力、多 agent 集群、上下文隔离、依次进行、模拟真实任务的高复杂度端到端测试"。
- **方式**：`workflow` 编排 **18 个隔离 agent**（12 个执行/验证/敌意 + 6 个汇总），全部真实素材：
  51 篇真实 PDF（宿主 pypdf 取文）、真实 OpenAlex 网络、真实仓库脚本；agent 之间互不可见。
- **原始产物**：`端到端真实跑/20260913-e2e-cluster/`（各阶段 REPORT.md / findings.json / 日志 / 夹具；
  本目录被 `.gitignore` 忽略，未污染仓库）。
- **去重结果**：115 条原始发现 → **34 条**（P0 6 / P1 22 / P2 5 / P3 1）。

---

## 一、编排结构

| 阶段 | agent | 角色 |
|---|---|---|
| 1 | debate-runner / debate-verifier | 真实会话 + 规格校验；对抗复验（构造能骗过校验器的 session） |
| 2 | discovery-runner / discovery-verifier | 真实检索 + 深度门禁负例；台账对账、去重与 DOI 质疑 |
| 3 | extraction-runner / extraction-verifier / extraction-adversary | 真实 PDF 审计；自选未用过的 PDF 独立复跑；脏输入攻击 |
| 4 | synthesis-runner / synthesis-verifier / synthesis-adversary | 真实证据综合；权重手算对账；伪造 claim/反证滥用 |
| 5 | integration-runner / integration-adversary | 跨技能契约链；并发/授权/环境敌意 |
| 6 | 5 个 harvest + 1 triage | 从落盘报告汇总、去重、按严重度排序 |

---

## 二、已修复（本批，均含回归）

### P0（会产出错误科研结论或静默放行伪造数据）

| # | 缺陷（实测） | 修复 |
|---|---|---|
| P0-1 | `normalize_claim()` 白名单丢弃 `relation/challenge_status/challenge_strength/target_claim_id` → RFC-017 罚则在 `analyze()`/CLI 生产路径**永不生效**，反证行回落为立场证据投票（实测 10 条未核验反证把 REFUTE 从 23.1% 抬到 73.7%） | 归一化保留全部方向/反证/溯源字段；反证记录不计立场权重（按取值判定，避免"键存在即反证"） |
| P0-2 | 数值门禁可被伪造值直通：`1,234` 在 `1,234,567` 内判 ALIGNED；`P<0.05` 与 `>0.05` 同判 ALIGNED；抽取值侧未做 confusable 归一化 | 多组千分位（英/欧两种 locale，单组点分仍按小数）；比较符（`< > ≤ ≥ ± ~`）参与比较；抽取值侧同源归一化 |
| P0-3 | 把整篇论文当 `verbatim_quote` → "数值在引句内"恒真（只在 Table 1 出现的 23.0 判 ALIGNED） | 新增 `MAX_QUOTE_LEN=2000` 与 `QUOTE_TOO_LONG` 判定，计入 `unverified` 并触发硬门禁 |
| P0-4 | 综合侧把「没查」当满权重证据：`support_type="NOT REPORTED"`（带空格）、`claim_status=unchecked/inaccessible/cited_only` 全部按 1.0 进入共识 | 新增 `evidence_states.py` 单一真源：写法归一化后一律零权重，并首次真正读取 `claim_status`；资格检查同源 |
| P0-5 | claim 与证据方向从不校验：加否定词/反义谓词的 claim 与忠实 claim 同样 `SUPPORTED / eligible=True` | `claim_alignment` 新增极性检查（否定奇偶 + 反义类）→ `CONTRADICTORY / REJECT_POLARITY_MISMATCH` |
| P0-6 | 并发写快照把 `session.json` 写坏：固定 `.tmp` 名 + 无锁 check-then-write（实测 3 进程 ×30 轮：20 次异常、90 次写入只剩 50 个版本） | 唯一临时名 + fsync + `O_EXCL` 锁串行化读改写 + 损坏快照抛结构化 `SnapshotCorrupt`；复测 90/90 成功、revision=91、零损坏 |

### P1（门禁/契约失效或误挡合法数据）

| # | 缺陷 | 修复 |
|---|---|---|
| P1-8 | 反证的人工复核事件不绑定被复核证据 → 一个真实事件可给任意论文的反证授权 | 复核事件必须携带并匹配 `payload.evidence_id`，否则 `PENDING`/`REJECTED` |
| P1-11 | DOI 归一化不剥 `https://doi.org/` 前缀 → 同一 DOI 不合并，重复文献获得两份独立证据身份 | 归一化剥离 URL/`doi:` 前缀并解百分号编码 |
| P1-13 | 占位 DOI（`"NR"`）直接当 ID → 29 条候选只产生 28 个唯一 `evidence_id`，关系注入串篇 | 占位符排除并回退 `openalex_id`/标题哈希保底 |
| P1-15 | 两个子任务共用同一 `task_id` 即冒充 2 名评估者 → 单人也能得 `LOW_DIVERGENCE` | 按去重身份计数，重复即 RV16，身份 <2 强制 `NOT_APPLICABLE` |
| P1-16 | 清空 `maturity_history` 即绕过成熟度守卫 MT1 | 证据不足按未满足处理（MT2，失败关闭） |
| P1-17 | 中文 PDF 折行被复制时整段去掉 → 真实引句一律 `NOT_FOUND`（误挡） | 含 CJK 的引句启用空白不敏感匹配（`WHITESPACE_RELAXED`）；拉丁文不放宽以免 "the rapist"/"therapist" 假命中 |
| P1-23 | 派发门禁强制 `gap.session_id`，而 canonical gap schema 未声明该字段 → **合规缺口永远无法派发** | schema 声明并 required；`heal_referential_integrity` 写入 `session_id`；规格夹具同步 |
| P1-29 | 规格校验器对派发必拒状态全绿（GP1 只查非空、GP3 不查事件存在、`approved_idea_version` 不检查、token 禁令只认字面 `max_tokens`） | 新增 GP6（指纹重算）、GP7（版本一致），GP3 核验事件，token 键按语义匹配；**由此发现 canonical 规格夹具的指纹是占位值**（`fp-gap-001-v1`），已重算为真实指纹 |

---

## 三、尚未修复（留档，含证据位置）

**P1（12 条，需契约决策或较大改动）**
- 反证跨技能断链：`to_evidence_link` 不透传 `target_claim_id/paper_id/independence_group_id`；`challenge_verification.status` 与消费侧 `challenge_status` 字段约定不一致且无适配器。
- `research_debate_event.schema.json` 全仓无执行点：伪造确认事件可直接 `append_event` 并让 `prepare_dispatch` 放行（修复需给 append 加 schema 门禁，会波及大量既有夹具，故单列）。
- 入向适配产物不符 `evidence_record.schema.json`（5/5、19/19、23/23 全不合）；`research_debate_session.schema.json` 无 `evidence_links` 定义。
- 执行深度标签与预算解耦：`depth=quick` 可携带 deep 预算并通过校验与 preflight；`selection.confirmed` 不要求 `confirmed_by/confirmed_at`。
- 检索台账跨作用域虚报：3 次查询只落 1 行台账，`reported_total_hits=0` 却判 `coverage=COMPLETE`，`rate=4.1429 > 1`。
- 反证方向判定依赖字符 2-gram 覆盖率：逐字否定句被判"支持"而拒收；方向检查被凭据检查挡住（归因错位）。
- `claimed_scope`/`checked_scope` 在抽取—综合链路无读取点；综合资格门 `evaluate_consensus_eligibility()` 无生产调用点；CLI 接受 `evidence_id` 悬空的伪造 claim 且 `rc=0`。
- 独立组判定可被 NULL 绕过（`independence_status` 缺失/null 都算"已验证"）。
- 畸形输入静默放行：`quote_audit` 入口不校验 envelope（裸 traceback 与静默 exit 0 并存）；`--unverified-policy list/ignore` 会跳过数值核验；`validate_session` 的 schema FAIL 不影响退出码。
- HEADLINE 权重纳入报告自称"已排除出综合"的不可比主张；明细 weight 与头条不一致。

**P2（5 条）**：文档与实现不符合集（README 四级去重/NR 示例/命令不可执行、能力表测试数字自相矛盾、9 类争议实为 3 类且字母不进产物）；契约字段名漂移合集（`selection_source` vs `source`、`evidence_tier` 枚举、`CLAIM-*` 前缀）；统计口径错误合集（`papers_by_stance` 计入零权重、summary 计数与 entries 不符）；写入与路径健壮性合集（`--out` 父目录缺失抛裸异常、超长路径误报、`.tmp`/`commit_journal` 残留）。

**P3 / 环境限制**（非产品缺陷）：子 agent 无人工交互通道（用户轮次只能模拟）；`/mnt/d` 9p 挂载下并发 append 静默丢事件且忽略 `chmod`；纯标准库 PDF 回退在真实语料仅 2/14 篇可提取；未跨 Python 版本、未跑严格契约 CI。

---

## 四、结论

- 集群测试**确实发现了 6 个 P0**：其中 3 个（P0-2/P0-3/P0-5）会直接让伪造或反向证据进入科研结论，2 个（P0-1/P0-4）会让"没查/反证"被误用，1 个（P0-6）会损坏会话真源。全部已修并回归。
- 修复后 `Ran 900 tests ... OK`（新增 `tests/test_cluster_audit_p0_fixes.py` 27 例，含并发写快照的跨进程用例）。
- 剩余 P1/P2 需契约决策（事件 schema 门禁、反证跨技能字段归属、深度-预算绑定、台账口径），已在能力表登记，未在本轮擅自改动公共契约。

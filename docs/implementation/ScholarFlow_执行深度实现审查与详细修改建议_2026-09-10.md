# ScholarFlow 执行深度实现审查与详细修改建议

审查日期：2026-09-10。

审查版本：`2c54c026eec0ad2cfdc05a7b5e190056aff2331f`；对比基线：`78a32604f80a178a3f2bd70b77cf2698a8ff37b8`。本次实现涉及 27 个变更文件，版本常量仍为 0.6.5。

范围：全面检查本次执行深度改动及其相邻的问询、上下文、检索、预算、数据契约、安装、测试路径；不是对历史所有科研算法进行重新认证。结论基于本地源码与离线复现，未核对 GitHub 远端、未做收费模型或真实文献质量评测。

本次只新增审查文档与隔离审查材料，没有修复业务代码。

## 一、结论

**方向正确，基础组件已建立，但当前不能认定“统一执行深度已端到端完成”。**

已经做好的部分：

- 建立 quick／standard／deep 三档配置和公共问询维度。
- 深度问题首轮优先展示，不再轻易被 5 问上限挤掉。
- 补查未展示的关键维度、未答深度时阻止两轮后的默认确认。
- 普通查询缺少深度时返回 INPUT_REQUIRED；显式 quick/deep 冲突会报错。
- 新增标准检索分支，快照标题能区分已确认和待确认。
- 预算预留使用线程锁；完全没有 usage 时能输出 null。

但仍有三类核心缺口：

1. **选择不可靠**：否定、询问、非法值和未验证推断仍可进入确认或执行。
2. **配置没有形成一致的数据契约**：保存结构、Schema、文档示例和上下游字段位置不一致。
3. **运行闭环未接通**：预算、持久化和下游档位策略主要停留在组件或说明层，不能据此保证全流水线资源受控。

建议先修下表的 P1，再补 P2；不需要推倒重做，也不宜继续叠加更多模式。

## 二、验证结果与边界

| 检查 | 实际结果 | 能证明什么 |
|---|---|---|
| `python -B -m unittest discover -s tests` | 290 项通过，测试报告耗时 3.208 秒 | 现有断言没有失败，不等于新需求全部实现 |
| `python -B scripts/verify_package_assets.py` | 通过 | 当前仓库资源存在且当前环境可导入 |
| 独立离线复现脚本 | 复现下文的门禁、配置、预算和检索统计问题 | 确认具体缺陷，不依赖外部论文或模型 |
| 安装到新建隔离目录 | 安装器报告成功 | 文件复制完成 |
| 安装副本 `python -I ... --help` | 成功 | 当前机器已有环境能够补足依赖 |
| 安装副本 `python -I -S ... --help` | `ModuleNotFoundError: No module named 'shared'` | 单靠安装器复制的技能文件不能独立启动该脚本 |
| JSON Schema 验证预设序列化结果 | 失败，缺少 3 个必需字段且有未知字段 | 生产者结构与新增 Schema 不匹配 |

离线复现材料保存在 `.planning/depth-review/repro.py`；安装副本保存在 `.planning/depth-review/install-fixture/`。这些是本地审查证据，未进入业务运行路径；目录可能被 Git 忽略，正式修复时应把对应断言迁入 tests。

复现入口（项目根目录）：

```powershell
python -B .planning/depth-review/repro.py
```

脚本对研究查询使用 Mock，不向外部服务发送研究请求。完整现有测试套件的日志含模拟的 HTTP 错误场景；这些日志不构成真实联网检索验证。

## 三、问题总表

P1：应在把本功能当作可靠默认工作流前修复。P2：需要补齐的正确性、可恢复性或测试问题。优先级按影响评估，不代表已发生用户数据损失。

| 编号 | 优先级 | 问题 | 证据类别 |
|---|---|---|---|
| R01 | P1 | 自然语言把否定、提问、引用当作模式选择 | 已复现 |
| R02 | P1 | Grill 门禁接受非法值、未经确认的 inferred 值 | 已复现 |
| R03 | P1 | Headless 非法模式和未指定深度的 snowball 默认执行标准档 | 已复现 |
| R04 | P1 | 配置序列化、Schema、文档三套结构不一致 | 已复现＋源码核对 |
| R05 | P1 | 预算和运行产物没有接入实际执行；下游缺少可核验调度 | 调用点审查 |
| R06 | P1 | 一键安装产物缺少新增强制依赖，已有环境掩盖问题 | 隔离复现 |
| R07 | P1 | 跨运行继承没有确认／运行绑定，实际上下游字段也不对齐 | 已复现＋源码核对 |
| R08 | P2 | INPUT_REQUIRED 后无法继续提交用户回答 | 已复现 |
| R09 | P2 | 先缺失 usage、后有 usage 时，部分测量被标成完整测量 | 已复现 |
| R10 | P2 | 预算结算不幂等、已超 Token 仍可预留、未完成回执标完成 | 已复现 |
| R11 | P2 | 检索档位参数未完全生效，候选上限和轮数报告不真实 | 已复现＋源码核对 |
| R12 | P2 | 若干“验收测试”只验配置，名称比实际验证范围更强 | 测试源码核对 |

## 四、逐项修改方法

### R01：自然语言意图识别误确认

位置：`shared/context_resolution/context_resolver.py:102`，`extract_execution_depth_from_text()`；历史对话扫描从约第 169 行起。

实际结果：

| 输入 | 当前返回 | 应有行为 |
|---|---|---|
| 不要用深度模式 | deep | 不确认 deep；需要其他明确选择 |
| 深度模式是什么意思 | deep | 回答含义，不确认模式 |
| 论文中写着“采用深度模式” | deep | 视为引用内容，不确认 |
| 先用快速模式，不，改用深度模式 | quick | 识别明确更正为 deep，或返回歧义待确认 |

原因：前缀和后缀均可选；短句直接接受关键词；找到第一个匹配即返回。领域黑名单只挡住了少数词组，没有表达确认意图。历史对话还未按 role 筛选用户决策。

修改步骤：

1. 将“抽取词值”与“认定确认”分开，返回 value、intent、source、scope、ambiguity，而不只返回字符串。
2. 当前用户的肯定执行指令才可自动确认；否定、疑问、条件句、引用文本进入未决或非决策分支。
3. 历史对话只接受用户角色中的有效决策，绑定当前运行；Agent 的推荐文本不是用户选择。
4. 同一句多种模式，处理明确更正；不明确时保留冲突，不使用首个词。
5. 保留领域词排除，但不要继续用不断扩大的黑名单代替意图校验。

验收：上表全部通过；追加 assistant 说“建议深度模式”、用户讨论“是否需要深度模式”、阶段分别选档的用例。

### R02：Grill 门禁只验“存在”，未验合法性与确认来源

位置：`shared/grill_me/response_parser.py:270`、`:342`、`:391`、`:626`。

实际复现：只注册公共深度维度时，回答 `1 zzz` 后状态为 `STAGE0_CONFIRMED`，值为 zzz；headless 传 `EXECUTION_DEPTH=banana` 后状态为 `STAGE0_BYPASSED`。传 `inferred_values={"EXECUTION_DEPTH":"deep"}` 会不提问并直接确认。

原因：非法深度走通用 CUSTOM 分支；关键项检查主要检查标签和键是否非空；`requires_explicit_selection` 没有约束 inferred 来源；headless 也只检查空值。

修改步骤：

1. 深度作为封闭枚举，不允许通用 CUSTOM 回退。非法值返回字段错误并维持未决。
2. 为需明确选择的维度建立共享验证函数，校验枚举、确认状态、来源、运行范围和题目绑定。
3. `select_questions()` 的无问题确认、`submit_response()`、`bypass_headless()` 都调用该函数。
4. 普通 inferred 值可用于推荐，不得直接解锁需明确选择的维度。确为当前用户明确表达时，使用有证据的决策记录，而不是裸字典。
5. 不影响允许自由文本的科研维度；限制只加到封闭选择类型。

验收：zzz、空白、任意数字、未知枚举不解锁；正常三档和中文别名解锁；人工构造 inferred 值不解锁。

### R03：Headless 两个绕过入口

位置：`skills/literature-discovery-acquisition/scripts/agent_search.py:635`、`:678`；`shared/execution/selection.py:56`。

实际复现（查询已被 Mock）：

- `run_headless_search(query="topic", execution_depth="banana")` 返回 0，调用研究分支一次，输出 standard。
- `run_headless_search(snowball_seed="10.0/fake")` 不指定深度也返回 0，调用 snowball 一次，输出 standard。

原因：缺参检查特意排除了 snowball；非法值归一化为 None 后又被默认成 standard。

修改步骤：

1. 区分“参数未提供”和“参数提供但非法”，后者立即报错。
2. 删除无条件 `resolved_depth = STANDARD` 回退。
3. snowball 是检索任务类型，不是免确认入口；所有研究入口统一 preflight。
4. CLI 和可导入 Python 函数都验证参数；不能只依赖 argparse choices。
5. 对错误返回结构化 INPUT_REQUIRED／INVALID_PARAMETER，并保证研究调用次数为 0。

验收矩阵包括：query/snowball × 未提供/非法/合法/新旧参数冲突，以及空白参数、中文别名。全部失败路径用 Mock 断言工具零调用。

### R04：执行配置没有统一的数据契约

位置：`shared/execution/profiles.py:49`、`:56`；`artifacts.py:25`、`:71`；`schemas/execution_profile.schema.json`；`shared/core/cross_skill_contract.md` 第 4 节。

已复现：

- `ExecutionProfile.from_dict(STANDARD_PROFILE.to_dict())` 抛出 `unexpected keyword argument 'execution_depth'`。
- `STANDARD_PROFILE.to_dict()` 缺少 Schema 要求的 run_id、selection_source、budgets，且多个扁平字段被 additionalProperties=false 拒绝。
- `save_run_artifacts()` 接受该对象并将这份不合规结构直接保存；loader 只读 JSON，不验证。
- 契约文档用 execution_depth／selection／budget，而 Schema 用 depth／selection_source／budgets，两者不一致。
- `preflight_check(ExecutionDepth.STANDARD)` 也失败，因为先 str(enum)，得到的不是 standard。

推荐修法：明确区分“档位预设”和“某次已确认运行配置”。

1. 保留 ExecutionProfile 作为不可变预设，修复自身 to_dict/from_dict 对称性。
2. 新增 RunExecutionConfig，包含 schema_version、profile_version、run_id、确认记录、阶段设置、有效预算、能力限制。
3. 选择唯一 canonical 字段命名；Schema、文档、保存器、loader、上下游同时迁移。不要为了让测试通过而关闭未知字段限制。
4. 归一化函数首先判断 ExecutionDepth 实例，直接使用 `.value`。
5. 保存前校验、读取后校验；兼容旧格式必须显式转换，不能把未确认旧配置补成已确认。
6. 使用临时文件与原子替换；运行恢复需要一致版本的文件组合，避免配置已更新、回执仍旧的混合快照。

验收：对象往返相等；预设不能冒充 RunConfig；实际保存文件通过 Schema；契约文档示例通过同一 Schema；非法预算和未知字段拒绝。以上必须测试真实生产者输出，而不是手工拼一份正确 JSON。

### R05：预算、持久化和下游策略尚未接入实际执行

位置：`shared/execution/`，检索入口 `agent_search.py:624`，三个 Skill 的 Stage 0 与执行分支。

源码证据：对 shared、skills、scripts、tests 全局查找 ExecutionBudget、preflight_check、save_run_artifacts、load_run_profile，除定义／导出之外，调用主要在测试中。实际检索函数没有建立或接收预算实例。抽取和综合没有对应新增的运行调度适配器来消费 extraction_unit_limit、devils_advocate_mode 等配置。

因此：已有预算类不等于实际执行会受预算限制；已有 Markdown 批量说明不等于脚本已落实同一总预算。宿主 Agent 可能按提示词执行，但本次无法验证其实际遵循程度。

修改步骤：

1. 引入轻量 RunContext，携带已确认配置、共享预算、阶段计划与产物路径；不要重写底层科研算法。
2. 检索入口接收 RunContext，调用前检查时间、候选处理量；分页、扩展、下载批次之间再次检查。
3. 模型请求与数据库 HTTP 请求分开计数，不能把 OpenAlex 请求记成 model_requests。
4. 抽取、综合分别增加计划适配层，实际消费论文／字段／核验策略；宿主执行时输出可核验的批次清单和完成事件。
5. 三阶段传递同一运行配置和总账；独立进程之间不能假定共享同一个内存对象，需持久化状态或单一协调器。
6. 正常结束、错误、超时都进入统一收尾，保存回执和剩余工作；重启不能重新获得完整额度。
7. usage 不可观测时保持 best_effort；图表工具不可用时记录缺口，不能输出“已穷尽审计”。

验收：用假时钟让运行在第二次查询前耗尽，断言第二次查询不调用且回执 partial；跨阶段恢复后余额不重置；同一输入不同档位产生不同执行计划和调用轨迹。

### R06：安装器复制技能后缺少 shared 运行时

位置：`scripts/install.ps1` 的逐 Skill 复制逻辑；`scripts/install.sh`；`agent_search.py:72` 至 `:84`。

隔离复现：安装到全新目录后，排除 site-packages 执行帮助命令，报 `No module named 'shared'`。安装器只复制 skills 子目录，没有提供 shared。脚本新增了强制导入，仓库 parents[3] 的回退位置在安装布局下也不是原仓库根目录。

边界：README 后部确实介绍了 Python 包与技能套件两层分发；但前面的“一键安装→直接使用”流程没有安装或验证这项运行时依赖。因此问题是该快捷路径不完整，不是声称任何 pip 安装环境都会失败。此次未验证从 wheel 干净安装的完整流程。

修改可选方案：

- 方案 A：明确依赖同版本 Python 引擎，由安装器检查对应解释器、引擎版本和资源位置；缺失时给出安装步骤，不报告全功能安装成功。
- 方案 B：分发可自包含的运行时目录和启动器，固定资源解析根目录，避免把仓库目录层级当作安装目录约定。

不要把 shared 随意复制到所有 Skill 根目录制造多个漂移副本。无论选哪一种，都需同步 shared 规程与 Schema 的查找方式。

验收：全新虚拟环境、仓库外工作目录、没有全局 editable 包，安装后验证帮助命令、缺参门禁、一次 Mock 查询、共享资源加载。打印实际模块路径，确认不是借用了原仓库或旧包。

### R07：跨运行继承既缺少绑定，又没有消费实际检索输出

位置：`shared/context_resolution/context_resolver.py:413`；`shared/execution/preflight.py:22`；`agent_search.py:828` 附近。

已复现：CURRENT_PLUS_UPSTREAM 下提供 `run_id=other-old-run` 和 `execution_depth=deep`，解析器直接继承 deep。它没有当前运行 ID 可供比较，也不验证 selection.status。

另一个集成问题：真实检索输出把配置放在 `search_protocol.depth_profile`，继承器却读取顶层 `execution_profile` 或 `execution_depth`。当前 T11 手工创建了继承器想要的输入，未使用真实 producer 输出，掩盖了这处断点。

修改步骤：

1. 上下游共用 RunConfig 引用或完整 canonical envelope，而不是任意字典中的 depth。
2. preflight 接收完整配置，验证 run_id、确认记录和适用阶段；当前未使用的 run_id 参数必须真正参与检查。
3. 区分“上游文章证据可继续使用”和“上游资源授权适用于当前运行”。前者成立不代表后者成立。
4. 实际检索 producer 到抽取 consumer 做往返契约测试；不要在测试中绕过映射手工构造数据。
5. 阶段覆盖、显式本次选择和有效配置的优先级写成可测试函数。

验收：同运行已确认配置继承；异运行、未确认、缺少运行标识的配置不自动解锁。文献元数据仍可读取，不因拒绝资源继承而丢弃科研证据。

### R08：阻塞状态无法恢复

位置：`shared/grill_me/response_parser.py:540`，允许提交回答的状态列表。

复现：连续两轮不选择后进入 STAGE0_INPUT_REQUIRED，再提交有效回答 `1A`，抛出 `Cannot submit response in state GrillState.STAGE0_INPUT_REQUIRED`。

修改：允许在等待补充状态消费回答，或提供显式 resume_input API；保留已有答案，只重新展示未决项。绑定 question_set_id，避免重排后将旧序号解释成新题目。无需重启整个研究门禁。

验收：两轮未决→暂停→合法补答→确认；暂停期间已回答的研究参数不丢失；旧题集答案不能错配新题集。

### R09：Token 完整性标记取决于返回顺序

位置：`shared/execution/budget.py:195` 至 `:206`。

复现：第一笔 actual_tokens=None，第二笔 actual_tokens=123，回执显示 tokens=123、token_measurement=available、limitations=[]。这是部分观测，却被报告成完整观测。

修改：用已计账请求数、已观测请求数、缺失 usage 数推导状态，而不是仅依赖上一次枚举状态。全部有 usage 才 available；全部没有才 unavailable；其余 partial。实测 Token 合计是观测到的下界，不能冒充整次运行总量。

验收：None→123、123→None、None→0、并发乱序、重试缺失全部测试；只要存在未观测的已执行模型调用，就不能变回 available。

### R10：预算状态、重复结算与完成语义

位置：`shared/execution/budget.py:148`、`:179`、`:226`。

已复现三件事：

1. 同一 reservation 结算两次，123 Token 被记成 246，模型调用被记成两次。
2. Token 上限 1,200，实际已用 1,500 后，默认 `reserve()` 仍成功；零估算跳过 Token 检查。
3. 存在 pending_scope 时，若没有标 EXHAUSTED／PARTIAL，回执仍为 completed。

源码还显示：未知 reservation 也会增加计账；is_success 未参与完成状态判断；settle 后不重新检查额度；已声明的 hard enforcement 没有配套硬上界保障。这些是实现层风险，不代表当前已经发生付费超支。

修改步骤：

1. 预留 ID 建立 pending／settled／released 生命周期；重复相同结算幂等，不同内容重复结算报错；未知 ID 拒绝。
2. 校验额度和用量为合法非负数，实际请求数不能通过负值修改总账。
3. settle 后更新额度状态；reserve 在已耗尽时不派发新研究任务，即使本次估算为零也不能绕过已超出的总额。
4. 调度完成状态与预算状态分开：任务未完成、在途、失败、预算耗尽分别表达；generate_receipt 不能以“没耗尽”推断“已完成”。
5. 收尾预留提供专用消费接口，不与普通研究配额混用；重试仍记账。
6. 当前没有硬上界执行能力时拒绝 hard 或明确降为 best_effort，并在回执解释。
7. 为恢复建立持久事件账本与一致性检查；仅有内存字典和最终 JSON 不足以提供断点续跑。

验收：重复结算不增加总账；超额后的任何新研究预留失败；未完清单非空不能整体 completed；最终一笔结算越界无需等下一次请求才被发现。

### R11：候选上限、真实轮数与策略参数不一致

位置：`agent_search.py:462`、`:529`、`:569`、`:580`；`shared/execution/profiles.py` 的档位参数。

复现：标准档 limit=50，首轮返回 50 个独立记录、扩展返回 16 个，最终得到 66 个候选，超过名为 max_search_candidates 的 50 上限。

复现：以不含空格的“生态学”作为查询，无候选和种子，实际只有一次查询；标准报告 rounds_executed=2，深度报告 3。该 Deep 固定计数是已有逻辑，本次新增 Standard 又复制了相同问题。

源码：Deep 声明 concept_expansion_rounds=2、snowball_rounds=2，但现有 Deep 函数仍是一次简化查询扩展、一次种子追踪；函数不读取这些档位字段。Standard 和 Deep 的差别主要是数量，而非声明的多轮配置都已执行。

修改步骤：

1. 明确 limit 是每查询上限还是运行候选总上限，分别命名；总预算独立累计并扣除已用量。
2. 扩展前计算剩余候选处理额度；多取的已返回数据保留来源和未处理状态，不静默丢失。
3. 根据 profile 的轮数循环执行；尚不支持多轮时将实际策略和文案收缩到真实能力，不能只提高配置数字。
4. 对实际执行事件统计 query_count、expansion_rounds_executed、snowball_rounds_executed；跳过步骤记录原因，不算已执行。
5. 输出 configured_limits 与 actual_usage；标准／深度报告中的差异必须能从事件轨迹重建。

验收：多查询去重后的候选处理量不超总额；中文单查询时不虚报扩展；改变轮数配置确实改变调用轨迹；预算结束与证据饱和分别报告。

### R12：验收名称与测试断言不相符

位置：`tests/test_execution_depth.py:279`、`:290`、`:300`、`:311`、`:335`、`:348`。

| 测试 | 当前实际检查 | 应替换或新增的验证 |
|---|---|---|
| T12 异任务不继承 | CURRENT_ONLY 禁用上游 | 允许上游的正常模式中拒绝错误 run_id |
| T16 升级增量续跑 | 比较两个 preset 的数值 | 先运行 quick，再升级 deep，验证缓存复用与总账连续 |
| T17 图表缺口 | 三档配置字符串 | 模拟工具缺失，验证回执缺口及不出现“已核验” |
| T18 不可比不合并 | devils_advocate_mode 属于枚举 | 传不可比证据，验证三档均拒绝违规聚合 |
| T20 干净安装 | 当前进程 import＋preflight | 仓库外新环境安装与首次调用 |
| persistence | 保存后读取一个字段 | 保存、Schema 校验、读取、恢复执行往返 |

修改：保留这些配置测试，但如实改名；另加真正验收测试。使用负面输入和真实 producer 输出。至少要保证删掉或绕过关键功能时，对应测试会失败，而不是配置还在就全绿。

## 五、建议修复顺序与最小改动范围

### 批次 A：先堵错误执行

修 R01、R02、R03、R08。目标：不误确认、不接受非法值、不绕过、能够补答恢复。只改解析、门禁和入口，不重构科研算法。

### 批次 B：统一配置并接通上下游

修 R04、R07。先确定唯一 RunConfig，再同步 Schema、序列化、文档和 producer/consumer。新增真实跨阶段 roundtrip 测试。

### 批次 C：修预算本体，再接入执行

先修 R09、R10，再修 R05。预算类未修好前不要在所有入口推广使用。最后补 R11，让档位参数落实到真实操作。

### 批次 D：安装与发布验收

修 R06、R12。使用干净环境验收，记录 Python 解释器、模块来源和引擎版本。按项目发布规则更新版本，避免同为 0.6.5 的不同实现让用户误用旧包。

每一批都运行原有 290 项回归和新增针对性测试；允许必要的旧断言调整，但不能通过删掉保护性测试获得全绿。

## 六、交付前必须满足的检查清单

- [ ] 否定／疑问／引用不被记为模式确认。
- [ ] 输入非法值的所有入口不产生研究工具调用。
- [ ] INPUT_REQUIRED 可在原运行补答恢复。
- [ ] canonical 配置保存、校验、加载、上下游往返一致。
- [ ] 有效运行绑定和阶段覆盖得到验证。
- [ ] 预算模块真实接入执行，耗尽后停止新任务并交付 partial。
- [ ] Token 完整性不受调用顺序影响；重复结算不重复收费记账。
- [ ] pending 工作不被整体标为完成。
- [ ] 配置轮数与实际调用一致，候选总上限生效。
- [ ] 安装验收不借用仓库或全局已有包。
- [ ] 测试名称与证据范围一致，真实行为有对应断言。
- [ ] 仍依赖宿主的图表理解、独立复核、Token 计量明确写出限制。

## 七、可交给修改 Agent 的任务说明

> 请以本审查文档和当前源码为依据，先复现 R01–R12，再按 A/B/C/D 四批修复。保留三档配置与已有科研证据底线，不进行无关重构。将每项复现转为真正会失败的回归断言。先统一运行配置和确认记录，再接预算与上下游；不要用字符串存在代替确认，不要用 preset 常量测试代替功能验收。安装测试必须在仓库外干净环境执行。不得因测试全绿宣称科研质量、OCR 或真实 Token 硬上限已验证。完成时逐项给出修复文件、测试证据、仍未实现内容；不触碰用户已有全局 Skill 安装，除非另获授权。

## 八、最终判断

这次实现不是无效工作：公共档位、第一轮优先询问和基本阻塞行为都已经落地。但目前更准确的定位是“**执行深度基础组件与部分检索接入完成，确认、数据契约、预算和部署闭环仍待修复**”。

修完上述问题，才适合把三档作为用户可依赖的稳定功能。届时还需用真实科研任务校准速度、用量与证据质量；代码测试通过不能替代科研能力评测。

---

# 附录 A：整改完成记录（v0.6.6）

**整改基线**：`2c54c02`。**整改后版本**：`0.6.6`。
**验收方式**：`python3 -B .planning/depth-review/verify_r01_r12.py` 对 R01–R12 逐项核验（31 项检查全部 PASS），加上 381 项 unittest 回归。

## A.1 逐项修复对照

| 编号 | 批次 | 修复文件 | 关键变更 |
|---|---|---|---|
| R01 | A | `shared/context_resolution/context_resolver.py` | 抽取与确认分离：新增 `ExecutionDepthIntentResult` / `DepthIntent` 与 `classify_execution_depth_intent()`；否定、疑问、引用、条件句、无更正的多值提及一律不确认；显式更正取最后值；历史对话仅接受 user 角色且经同一意图判定；`extract_execution_depth_from_text()` 退化为"仅返回可确认值"的兼容包装 |
| R02 | A | `shared/grill_me/selection_validation.py`（新增）、`response_parser.py` | 封闭维度共享校验：枚举合法性 + `USER` 来源 + 阶段范围；非法值进入 `INVALID_SELECTION` 并保持未决；inferred/context 值降级为推荐，不解除门禁；`bypass_headless()` 校验枚举而非仅查空；`bypass_headless()` 不再为封闭维度补默认值 |
| R03 | A | `agent_search.py`、`shared/execution/selection.py` | 区分"未提供"与"提供但非法"；删除无条件 `STANDARD` 回退；snowball 与 query 统一 preflight；新增 `_emit_headless_error()` 输出契约化 `INPUT_REQUIRED` / `INVALID_PARAMETER` 且研究调用次数为 0 |
| R04 | B | `shared/execution/config.py`（新增）、`profiles.py`、`preflight.py`、`artifacts.py`、`schemas/execution_profile.schema.json`、`shared/core/cross_skill_contract.md` | 区分 `ExecutionProfile`（不可变预设）与 `RunExecutionConfig`（已确认运行配置）；修 `to_dict/from_dict` 往返对称并拒绝未知/冲突字段；`get_profile()` 支持别名且非法值抛 `ValueError`；`preflight_check()` 直接消费枚举值；Schema 重写为运行配置契约；契约文档示例通过同一 Schema |
| R05 | C | `shared/execution/context.py`（新增） | `RunContext` 携带确认配置 + 共享总账 + 阶段计划 + 产物路径；模型请求与数据库请求分开计数；候选按运行级总额累计；统一收尾（正常/错误/超时）落盘回执与待办；`resume()` 依据台账重建余额，重启不重置额度 |
| R06 | D | `scripts/install.sh`、`scripts/install.ps1`、`agent_search.py` | 安装器在目标根写入**唯一一份** `shared/`（不再每个 skill 各一份），并执行隔离解释器验收，失败则退出码 2 且不报告成功；`agent_search.py` 运行时可同时解析仓库布局与安装布局 |
| R07 | B | `context_resolver.py`、`response_parser.py`、`preflight.py` | 上游继承绑定 `run_id`：不一致、缺失或 `selection.status != confirmed` 一律拒绝并记入 `rejected_inheritance`；新增 `preflight_run_config()` 真正使用 `run_id` 与阶段范围；上游证据（如 `S3`）在授权被拒后仍可用 |
| R08 | A | `response_parser.py` | `STAGE0_INPUT_REQUIRED` 纳入可提交状态并新增 `resume_input()`；保留已答参数，只重展未决项；`question_set_id` 绑定防止旧序号错配新题集 |
| R09 | C | `shared/execution/budget.py` | Token 完整性由"已观测/未观测调用计数"推导，与调用顺序无关；`partial` 回执明确标注 Token 为已观测下界 |
| R10 | C | `shared/execution/budget.py` | 预留生命周期 `pending→settled/released`；重复同值结算幂等、异值或未知 ID 抛 `BudgetError`；超额后任何新预留失败（含零估算）；`settle` 后立即刷新额度状态；存在未完成清单或未结算预留时回执为 `partial`；不支持 `hard` 时显式降级并写入 `limitations`；收尾预留按比例计算而非固定常量 |
| R11 | C | `agent_search.py`、`shared/execution/profiles.py` | `limit` 明确为**每查询上限**，运行级候选总额独立累计；超出总额的记录以 `UNPROCESSED_BEYOND_RUN_CEILING` 保留；`snowball_rounds` / `concept_expansion_rounds` 真实驱动循环；输出 `configured_limits` 与 `actual_usage`，跳过的步骤记录原因且不计入执行轮数；Ledger A 改为 canonical envelope 对象 |
| R12 | D | `tests/test_execution_depth.py`、`tests/test_execution_depth_hardening_r01_r12.py`（新增）、`tests/test_doc_consistency.py` | 仅验配置的 T12/T16/T17/T18/T20/persistence 更名为 `*_config_*`，另建 `TestExecutionDepthBehaviour` 真实验收（升级续跑、工具缺口、不可比不合并、预算耗尽）；新增 R01–R11 的行为回归；文档一致性门禁扩展到 `.py` 源码 |

## A.2 交付前检查清单核对

- [x] 否定／疑问／引用不被记为模式确认 — R01 回归 + 31 项核验
- [x] 输入非法值的所有入口不产生研究工具调用 — R03 用 Mock 断言零调用
- [x] `INPUT_REQUIRED` 可在原运行补答恢复 — R08 `resume_input()`
- [x] canonical 配置保存、校验、加载、上下游往返一致 — R04/R07 roundtrip + Schema 校验
- [x] 有效运行绑定和阶段覆盖得到验证 — `preflight_run_config()` + T12b/T12c
- [x] 预算模块真实接入执行，耗尽后停止新任务并交付 partial — R05 `RunContext`
- [x] Token 完整性不受调用顺序影响；重复结算不重复记账 — R09/R10
- [x] pending 工作不被整体标为完成 — R10 回执语义
- [x] 配置轮数与实际调用一致，候选总上限生效 — R11
- [x] 安装验收不借用仓库或全局已有包 — 隔离目录 + `-I -S` + 模块来源断言
- [x] 测试名称与证据范围一致，真实行为有对应断言 — R12
- [x] 仍依赖宿主的图表理解、独立复核、Token 计量明确写出限制 — `RunContext.plan_for()` 的 `unsupported` 与回执 `limitations`

## A.3 仍未实现 / 明确不声称

以下内容**本次未实现**，不得因测试全绿而声称已验证：

1. **真实科研质量评测**：未做真实论文的抽取/综合质量、召回率或耗时校准；`benchmarks/` 中 Discovery 与 Extraction 两项仍为合成夹具自检。
2. **宿主侧执行遵循度**：图表理解、Devil's Advocate 独立复核、Gatekeeper 终审仍由宿主 Agent 承担，代码只提供计划与缺口标记。
3. **图表/OCR 工具链**：`figure_table_verification`、`ocr_scan_policy` 在无对应宿主工具时记为能力缺口，不会输出"已穷尽审计"。
4. **Token 硬上限**：当前无抢占能力，请求 `hard` 会被降级为 `best_effort` 并写入回执，不代表存在真实硬上界。
5. **RFC-013 的 M1/M2/M4 与 D1–D5**：本次未触及，仍为设计状态（见 `docs/rfcs/README.md` 的 `PARTIALLY IMPLEMENTED` 标注）。
6. **断点续跑**：`resume()` 依据持久化台账重建余额，但尚不支持在阶段中途精确接续未完成的单篇处理。


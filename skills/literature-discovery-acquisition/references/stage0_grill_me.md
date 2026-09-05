# Stage 0: 文献发现与获取自适应决策门禁规程 (Grill-Me Protocol)

> **Status**: Production Standard  
> **Skill**: `literature-discovery-acquisition`  
> **Core Architecture**: Powered by [ScholarFlow Adaptive Research Grill Engine](../../../shared/grill_me/core_protocol.md)  
> **Dimension Reference**: [grill_dimensions.md](./grill_dimensions.md) (D1 ~ D14)

---

## 一、规程目的与核心原则

在学术文献检索中，用户给出的初始 Prompt 往往是宽泛或存在隐性前提的（例如：“帮我搜一下关于CRISPR基因编辑临床试验的论文”）。如果未经澄清直接搜索，将导致严重的检索偏差（如检出大量不可用的综述、遗漏高影响因子成果、检索年份不符需求等）。

**自适应决策门禁的核心目标**：
1. **预设决策维度，动态生成问题**：基于 [grill_dimensions.md](./grill_dimensions.md) 定义的 14 个决策维度（D1-D14），结合任务语境与学科透镜，动态筛选 3~5 个最高影响度的问题发起提问；
2. **每题必带推荐，推荐必给理由**：每个选项题必须包含 `(Recommended)` 选项，附带 1 句话的方法学Rationale与置信度标签（`[高置信度]` / `[中置信度]` / `[需权衡]`）；
3. **严格交互硬门禁 (STOP Rule)**：Agent 在输出 Stage 0 问题后，**必须立即终止当前回复，进入静默等待状态**，严禁在同一回复中自问自答或直接调用检索/下载工具；
4. **低摩擦快捷协议与全量可追溯**：支持用户单指令极速确认（`按推荐`、`1A 2B 3C`），并在通过后生成包含参数来源追溯（`[USER]` / `[INFERRED]` / `[DEFAULTED]` / `[SYSTEM_RULE]`）的协议快照（Protocol Snapshot）。

---

## 二、决策维度与层级映射

系统在启动时评估 14 个维度：

| 层级 | 维度清单 | 处理策略 |
|---|---|---|
| **Tier 1: CRITICAL** | `D1` 研究目标与产出定位<br>`D2` 核心研究问题与因果命题<br>`D3` 目标实体与概念范畴<br>`D4` 纳入标准与边界<br>`D5` 排除标准与禁忌红线 | **首轮必须解决**；未在初始提示中明确者优先列入提问清单；未解决前严禁开工。 |
| **Tier 2: HIGH_IMPACT** | `D6` 概念拓展与近义词策略<br>`D7` 地理与空间范畴<br>`D8` 时间跨度与历史回溯<br>`D9` 文献类型与同行评审门槛 | 显著影响检索召回率与数据量；在不超过 3~5 题预算下按影响力降序填补提问槽位。 |
| **Tier 3: DEFAULTABLE** | `D10` 语言范围 (中英双语)<br>`D11` 种子文献滚雪球起点<br>`D12` 数据库边界 (多源聚合)<br>`D13` 检索深度与饱和度 (2层饱和停止)<br>`D14` 交付物类型 (PRISMA台账+OA全文) | **默认不提问**，自动应用科学透镜默认值，打上 `[DEFAULTED]` 标签写入协议快照供复核。 |

---

## 三、Stage 0 执行三步走流程

### Step 1：任务解析与动态提问生成 (Dynamic Grill-Me Generation)
Agent 接收到用户请求后：
1. 自动提取初始 Prompt 中已明确声明的参数，直接赋予 `[INFERRED]` 标签；
2. 从未决的 `CRITICAL` 维度中提取核心问题，并在 `HIGH_IMPACT` 维度中挑选高影响项，组合生成 **3 ~ 5 个** 聚焦的结构化问题；
3. **Agent 输出问题后立即停止输出（STOP），等待用户回复！**

### Step 2：用户快捷回复与解析 (Response Parsing)
用户可通过以下任意方式快捷回复：
- **全盘采纳**：输入 `按推荐` / `全部按推荐` / `全选A` / `yes` / `ok`，系统将所有提问项解析为 `(Recommended)` 选项，标记为 `[USER]`。
- **代号速选**：输入 `1A 2B 3C` 或 `1.A 2.B 3.C`，按题号精确解析。
- **混合覆盖**：输入 `1按推荐，2选B，3补充：仅检索近三年临床三期试验`，系统解析覆盖项。

### Step 3：协议快照固化与门禁放行 (Protocol Snapshot & Gate Clearance)
确认全部 `CRITICAL` 维度闭环后，系统生成标准的【Stage 0 Protocol Snapshot】：

```markdown
# Stage 0 Protocol Snapshot (Research Gate Confirmed)
- **Skill**: literature-discovery-acquisition
- **Domain Lens**: biomedical / life_sciences / generic
- **Gate Status**: CONFIRMED
- **Interaction Rounds**: 1

| Dimension ID | Dimension Name | Priority | Selected Setting / Boundary | Provenance | Rationale / Notes |
|---|---|---|---|---|---|
| `D1` | 研究目标定位 | `CRITICAL` | 硕博学位论文开题与系统综述调研 | `[USER]` | 遵循高召回与可审计规范 |
| `D2` | 核心科研问题 | `CRITICAL` | 靶向药物耐药性与调控机制 | `[INFERRED]` | 从用户任务提示词直接提炼 |
| `D4` | 纳入标准 | `CRITICAL` | 具备完整实证对照组数据及统计学指标 | `[USER]` | 采纳推荐方案 |
| `D5` | 排除红线 | `CRITICAL` | 排除非同行评议社论、通俗科普与掠夺性期刊 | `[USER]` | 采纳推荐方案 |
| `D8` | 时间跨度 | `HIGH_IMPACT` | 近10年前沿为主 + 经典奠基文献追溯 | `[DEFAULTED]` | 遵循学科领域通用规范 |
| `SYS_RULE` | 方法学守则 | `CRITICAL` | PRISMA-S 标准检索日志与双轨导出 | `[SYSTEM_RULE]` | ScholarFlow 核心质控规范 |

> [!NOTE]
> **门禁状态**: `CONFIRMED`。检索式构建、数据库并发查询与 OA 下载已获授权，即刻进入 Stage 1 执行。
```

快照输出后，工作流正式转入 Stage 1 概念矩阵构建与检索执行。

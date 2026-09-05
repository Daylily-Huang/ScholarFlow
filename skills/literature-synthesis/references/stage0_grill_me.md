# Stage 0: 跨篇文献合成自适应决策门禁规程 (Grill-Me Protocol)

> **Status**: Production Standard  
> **Skill**: `literature-synthesis`  
> **Core Architecture**: Powered by [ScholarFlow Adaptive Research Grill Engine](../../../shared/grill_me/core_protocol.md)  
> **Dimension Reference**: [grill_dimensions.md](./grill_dimensions.md) (S1 ~ S11)

---

## 一、规程目的与核心原则

多文献跨篇综合分析最容易面临三大灾难：
1. **输入来源混乱**：基于不可靠的粗提摘要分析学术争议，直接导致基于模型幻觉构建伪争议；
2. **核心科学问题发散**：缺乏明确聚焦点，输出变成涵盖几十个方向的流水账；
3. **输出期望脱节**：用户仅需快速排查两个结论的冲突点，AI 却消耗大量算力撰写长篇学术流派史。

**自适应合成门禁的核心目标**：
1. **证据输入结构化预检**：优先接入经过 `literature-evidence-extraction` 质控的结构化证据表及伴生 JSON；若仅有无序粗文，给出降级警示；
2. **预设决策维度，动态生成问题**：基于 [grill_dimensions.md](./grill_dimensions.md) 定义的 11 个合成决策维度（S1-S11），动态筛选 3~5 个最高影响度的问题发起提问；
3. **每题必带推荐，推荐必给理由**：每个选项题必须包含 `(Recommended)` 选项，附带 1 句话的方法学依据与置信度标签；
4. **严格交互硬门禁 (STOP Rule)**：Agent 在输出 Stage 0 问题后，**必须立即终止当前回复，进入静默等待状态**，严禁在同一回复中自问自答或直接调用分析工具；
5. **低摩擦快捷协议与全量可追溯**：支持用户单指令极速确认（`按推荐`、`1A 2B 3C`），并在通过后生成包含参数来源追溯（`[USER]` / `[INFERRED]` / `[DEFAULTED]` / `[SYSTEM_RULE]`）的协议快照（Protocol Snapshot）。

---

## 二、决策维度与层级映射

系统在启动时评估 11 个维度：

| 层级 | 维度清单 | 处理策略 |
|---|---|---|
| **Tier 1: CRITICAL** | `S1` 综合目的与产出定位<br>`S2` 核心争鸣命题与待检验假设<br>`S3` 证据库来源与纳入边界<br>`S4` 比较单元与聚合粒度 | **首轮必须解决**；未在初始提示中明确者优先列入提问清单；未解决前严禁开工。 |
| **Tier 2: HIGH_IMPACT** | `S5` 可比性边界与条件控制<br>`S6` 证据质量评级与加权策略<br>`S7` 学派识别与聚类灵敏度 | 显著影响争议判定准确度与学派划分边界；按需放入首轮提问。 |
| **Tier 3: DEFAULTABLE** | `S8` 时间演进与范式转移切片<br>`S9` 强制独立反方挑刺 (Devil's Advocate)<br>`S10` 知识空白上游反馈任务包 (Upstream Gap)<br>`S11` 叙事综述产出深度 (Claims-first) | **默认不提问**，自动应用科学规范默认值，打上 `[DEFAULTED]` 标签写入协议快照供复核。 |

---

## 三、Stage 0 执行三步走流程

### Step 1：证据就绪预检与动态提问生成 (Verification & Dynamic Grill-Me)
Agent 接收到请求后：
1. **证据输入就绪度核查**：确认是否已有证据表或结构化参数；
2. **提取已知要素**：识别任务指定的核心争鸣命题或限定主题；
3. **动态输出 3 ~ 5 个问题**：从未决的 S1、S2、S4、S5、S6、S7 中组织提问；
4. **Agent 输出问题后立即停止输出（STOP），等待用户回复！**

### Step 2：用户快捷回复与解析 (Response Parsing)
用户可通过以下方式快捷回复：
- **全盘采纳**：输入 `按推荐` / `全部按推荐` / `全选A` / `yes` / `ok`，系统将所有提问项解析为推荐选项。
- **代号速选**：输入 `1A 2B 3C` 或 `1.A 2.B 3.C`，按题号精准匹配。
- **混合微调**：输入 `1按推荐，2选A (聚焦效应量方向对立)，3选C`。

### Step 3：协议快照固化与门禁放行 (Protocol Snapshot & Gate Clearance)
确认全部 `CRITICAL` 维度闭环后，系统生成标准的【Stage 0 Protocol Snapshot】：

```markdown
# Stage 0 Protocol Snapshot (Research Gate Confirmed)
- **Skill**: literature-synthesis
- **Domain Lens**: biomedical / life_sciences / generic
- **Gate Status**: CONFIRMED
- **Interaction Rounds**: 1

| Dimension ID | Dimension Name | Priority | Selected Setting / Boundary | Provenance | Rationale / Notes |
|---|---|---|---|---|---|
| `S1` | 综合产出定位 | `CRITICAL` | 全景学术争议诊断与学派演进图谱 | `[USER]` | 揭示前沿学术争鸣与理论分歧 |
| `S2` | 核心争鸣命题 | `CRITICAL` | 因果效应方向分歧 (促进 vs 抑制) | `[USER]` | 聚焦核心矛盾假设 |
| `S3` | 证据输入边界 | `CRITICAL` | 经 Extraction 质控的结构化证据表 | `[INFERRED]` | 输入已具备 E1-E4 证据矩阵 |
| `S4` | 比较聚合粒度 | `CRITICAL` | 细粒度独立实验 / 独立处理组单元 | `[USER]` | 采纳推荐方案消除组间混杂 |
| `S6` | 质量评级加权 | `HIGH_IMPACT` | 多维循证质量加权 (样本量与偏倚风险) | `[DEFAULTED]` | 遵循循证医学与定量综合规范 |
| `SYS_RULE` | 方法学守则 | `CRITICAL` | Claims-first + 强制独立反方挑刺 | `[SYSTEM_RULE]` | ScholarFlow 核心防伪铁律 |

> [!NOTE]
> **门禁状态**: `CONFIRMED`。Step 1 证据单元标准化与争议矩阵构建已获授权，即刻进入执行。
```

快照输出后，正式进入 Step 1 证据处理与争议发掘流水线。

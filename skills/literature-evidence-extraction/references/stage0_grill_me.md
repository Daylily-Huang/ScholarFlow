# Stage 0: 证据抽取自适应决策门禁规程 (Grill-Me Protocol)

> **Status**: Production Standard  
> **Skill**: `literature-evidence-extraction`  
> **Core Architecture**: Powered by [ScholarFlow Adaptive Research Grill Engine](../../../shared/grill_me/core_protocol.md)  
> **Dimension Reference**: [grill_dimensions.md](./grill_dimensions.md) (E1 ~ E9)

---

## 一、规程目的与核心原则

学术论文内容抽取绝不能搞“黑盒盲盒运行”。用户的实际科研需求千差万别：有人需要提取完整的 PCR 体系组分，有人需要提取临床试验效应量，有人需要对既有争议结论进行原子化事实核验。

**自适应抽取门禁的核心目标**：
1. **全文输入有效性前置硬筛**：核验是否真正具备论文全文（PDF 文件、全文文本或本地路径）。若只有摘要（Abstract），坚决拒绝提取实验参数并触发熔断；
2. **预设决策维度，动态生成问题**：基于 [grill_dimensions.md](./grill_dimensions.md) 定义的 9 个抽取决策维度（E1-E9），动态筛选 3~5 个最高影响度的问题提问；
3. **每题必带推荐，推荐必给理由**：每个选项题必须包含 `(Recommended)` 选项，附带 1 句话的方法学依据与置信度标签；
4. **严格交互硬门禁 (STOP Rule)**：Agent 在输出 Stage 0 问题清单后，**必须立即终止当前回复，进入静默等待状态**，严禁在同一回复中自问自答或直接调用抽取工具；
5. **低摩擦快捷协议与全量可追溯**：支持用户单指令极速确认（`按推荐`、`1A 2B 3C`），并在通过后生成包含参数来源追溯（`[USER]` / `[INFERRED]` / `[DEFAULTED]` / `[SYSTEM_RULE]`）的协议快照（Protocol Snapshot）。

---

## 二、决策维度与层级映射

系统在启动时评估 9 个维度：

| 层级 | 维度清单 | 处理策略 |
|---|---|---|
| **Tier 1: CRITICAL** | `E1` 抽取目的与任务类型<br>`E2` 待抽取的文献范围与输入边界<br>`E3` 抽取 Schema 选择与定制<br>`E4` 证据单元切分与多实验隔离粒度 | **首轮必须解决**；未在初始提示中明确者优先列入提问清单；未解决前严禁开工。 |
| **Tier 2: HIGH_IMPACT** | `E5` 推导证据与重计算策略<br>`E6` 计量单位与数值归一化要求 | 显著影响下游定量分析与横向可比性；按需放入首轮提问。 |
| **Tier 3: DEFAULTABLE** | `E7` 表格与附录材料优先挖掘<br>`E8` Quote-before-Extract 物理隔离<br>`E9` 10% 关键高危字段抽检审计 | **默认不提问**，自动应用科学规范默认值，打上 `[DEFAULTED]` 标签写入协议快照供复核。 |

---

## 三、Stage 0 执行三步走流程

### Step 1：全文预检与动态提问生成 (Verification & Dynamic Grill-Me)
Agent 接收到请求后：
1. **输入全文预检**：
   - 若仅有 Abstract：触发熔断，提示用户提供全文，不进入参数提取。
   - 若具备全文：标记 `E2` 为 `[INFERRED: fulltext_pdf]`。
2. **提取已知要素**：识别任务中指定的目标 Schema 或核验目标。
3. **动态输出 3 ~ 5 个问题**：从未决的 E1、E3、E4、E5、E6 中组织提问。
4. **Agent 输出问题后立即停止输出（STOP），等待用户回复！**

### Step 2：用户快捷回复与解析 (Response Parsing)
用户可通过以下方式快捷回复：
- **全盘采纳**：输入 `按推荐` / `全部按推荐` / `全选A` / `yes` / `ok`，系统将所有提问项解析为推荐选项。
- **代号速选**：输入 `1A 2B 3C` 或 `1.A 2.B 3.C`，按题号精准匹配。
- **混合微调**：输入 `1按推荐，2选C (采用生态专属Schema)，3选A`。

### Step 3：协议快照固化与门禁放行 (Protocol Snapshot & Gate Clearance)
确认全部 `CRITICAL` 维度闭环后，系统生成标准的【Stage 0 Protocol Snapshot】：

```markdown
# Stage 0 Protocol Snapshot (Research Gate Confirmed)
- **Skill**: literature-evidence-extraction
- **Domain Lens**: biomedical / life_sciences / generic
- **Gate Status**: CONFIRMED
- **Interaction Rounds**: 1

| Dimension ID | Dimension Name | Priority | Selected Setting / Boundary | Provenance | Rationale / Notes |
|---|---|---|---|---|---|
| `E1` | 抽取任务类型 | `CRITICAL` | 系统综述与定量参数精准提取 | `[USER]` | 遵循高精度可复现规范 |
| `E2` | 文献输入形态 | `CRITICAL` | 全文 PDF 解析文本 (已就绪) | `[INFERRED]` | 输入已验证为完整全文 |
| `E3` | 抽取 Schema | `CRITICAL` | schemas/v1.0/general_empirical.json | `[USER]` | 采纳推荐标准双轨 Schema |
| `E4` | 多实验隔离粒度 | `CRITICAL` | 细粒度独立 Assay 上下文物理隔离 | `[USER]` | 采纳推荐方案防参数混淆 |
| `E5` | 推导重计算策略 | `HIGH_IMPACT` | 允许透明重计算（附带原始值与公式） | `[DEFAULTED]` | 兼顾可用性与可审计性 |
| `SYS_RULE` | 方法学守则 | `CRITICAL` | Quote-before-Extract + E1-E4 分层 | `[SYSTEM_RULE]` | ScholarFlow 核心防伪铁律 |

> [!NOTE]
> **门禁状态**: `CONFIRMED`。Phase A 事实定位与引文抽取已获授权，即刻进入执行。
```

快照输出后，正式进入 Phase A 事实抽取流水线。

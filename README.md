# 🎓 ScholarFlow

<p align="center">
  <b>面向严谨科研的智能体文献全生命周期工作流套件</b><br>
  <i>An evidence-grounded AI research workflow for literature discovery, evidence extraction, and controversy-aware synthesis.</i>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/Python-3.9%2B-brightgreen.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/Dependencies-Zero%20Mandatory%20Pip-orange.svg" alt="Zero Mandatory Dependencies">
  <img src="https://img.shields.io/badge/Workflow-PRISMA--S%20Informed-purple.svg" alt="PRISMA-S Informed">
  <img src="https://img.shields.io/badge/Supported%20Agents-Claude%20Code%20%7C%20Antigravity%20%7C%20Codex-blueviolet.svg" alt="Agent Support">
</p>

---

## 📖 简介 (Introduction)

**ScholarFlow** 是为 AI 编程助手与自主智能体（Claude Code、Google Antigravity、Codex、Cursor 等）量身定制的**全生命周期科研文献调研智能体技能套件（Agent Skills Suite）**。

与常见的“喂一篇 PDF 做泛读总结”的浅层工具不同，ScholarFlow 吸收了 **FutureHouse `PaperQA2`**、**Stanford `STORM`**、**`GPT-Researcher`** 等前沿理念，严格恪守高水平科研出版与学位论文的严谨性标准：

1. **防幻觉设计（Grounding-by-Design）**：核心数据必须锚定带页码的原文逐字引用与上下文协同校验。
2. **拒绝流水账（Controversy-Driven）**：综述绝非“张三做了 A、李四做了 B”，而是以科学冲突、方法论根因与适用边界为主线。
3. **拒绝文献民主投票（Weighted Evidence）**：严禁简单比拼文献篇数多数决，单篇高精度独立复现研究可一票降权粗放旧成果。
4. **全生命周期闭环（Upstream Gap Loop）**：综合分析发现文献断裂或数据模糊时，自动生成结构化任务载荷驱动上游补充检索与精准核验。
5. **轻量与零强制第三方依赖（Zero Mandatory Third-Party Runtime Dependencies）**：所有核心业务逻辑与 CLI 脚本均基于 Python 3 标准库构建，可选依赖（如 `pypdf`）通过 `pip install "scholarflow[pdf]"` 按需启用。

### 🌟 核心设计信条 (Core Epistemic Principles)
- **Principle 1: Domain-neutral core, domain-aware execution (核心学科中立，视角按需注入)**：核心协议与证据纪律保持全学科中立，领域特有概念与风险点通过按需加载的 Domain Lens 动态注入。
- **Principle 2: Examples must not become rules (示例严禁上升为规则)**：核心规范中任何具体学科的案例（如 PCR、临床队列、神经网络）仅作为理解辅助，执行规则严格使用通用抽象本体（Target Entity, Method, Context Unit, Outcome, Boundary）。
- **Principle 3: Domain knowledge may specialize the workflow, but may not override evidence integrity (领域知识可特化流程，不可覆盖证据纪律)**：学科规范只能细化关注维度，严禁放宽或违背原句绑定、未报告不脑补、客观事实物理隔离等通用证据铁律。
- **Principle 4: No single discipline defines the default ontology of ScholarFlow (没有任何单一学科定义 ScholarFlow 的默认本体)**：系统默认不以任何特定学科专家的偏见思考，首先作为中立科研证据系统运行，再动态加载对应学科透镜。

---

## 🏗️ 架构总览 (System Architecture)

ScholarFlow 由三个高度模块化、既可独立运行又可无缝协同的 Agent 技能构成：

```mermaid
graph TD
    User([科研学者 / 课题组 / 论文作者]) -->|输入科学问题或种子DOI| Skill1["<b>1. literature-discovery-acquisition</b><br/>文献系统发现、初筛与全文获取"]
    
    Skill1 -->|OpenAlex 跨库检索<br/>双向引用滚雪球 Snowballing<br/>PRISMA-S 流程审计 / OA PDF 获取| Skill2["<b>2. literature-evidence-extraction</b><br/>证据可信抽取、事实核验与声明审计"]
    
    Skill2 -->|Quote-First 铁律<br/>0-10相关性前置剪枝<br/>E1-E4 证据分层 / 审稿人四象限| Skill3["<b>3. literature-synthesis</b><br/>学术争议发掘、学派谱系与边界共识"]
    
    Skill3 -->|自动生成| Vis["🌐 Mermaid 论证拓扑图<br/>Argument Graph Visualizer"]
    Skill3 -->|驱动产出| Review["📝 争议驱动型叙述性文献综述<br/>Controversy-Driven Narrative Review"]
    
    Skill3 -.->|闭环反馈: 检索空白| GapSearch["SEARCH GAP Payload"] -.->|补充扩展检索| Skill1
    Skill3 -.->|闭环反馈: 数据冲突| GapExtract["EXTRACTION GAP Payload"] -.->|定向深度审计| Skill2

    style Skill1 fill:#e6f4ff,stroke:#1890ff,stroke-width:2px;
    style Skill2 fill:#f6ffed,stroke:#52c41a,stroke-width:2px;
    style Skill3 fill:#fff7e6,stroke:#fa8c16,stroke-width:2px;
    style Vis fill:#f9f0ff,stroke:#722ed1,stroke-width:2px;
    style Review fill:#fff0f6,stroke:#eb2f96,stroke-width:2px;
```

---

## 🛡️ Stage 0 上下文感知科研决策门禁 (Context-Aware Research Gate & Grill Engine)

各技能在消耗实质性算力与调用下游工具前，由统一的 **Context Resolution Layer (`shared/context_resolution/`)** 与 **Adaptive Research Grill Engine (`shared/grill_me/`)** 强制执行前置科研决策门禁（三阶段流水线：Stage 0A → Stage 0B → Stage 0C）：

1. **Stage 0A：科研上下文解析层 (Context Resolution Layer)**：
   - **五层来源递进解析**：按优先级依次提取当前提示词 (`current_user`)、对话历史 (`conversation`)、任务附件 (`current_attachments`)、上游技能产物 (`upstream_outputs`)，仅在必要时针对未决变量按需查询项目资料 (`project_search`)；
   - **正交过滤与已知要素确认**：启用跨学科正交防泄漏过滤，已知约束自动确认为 `RESOLVED`（标记 `[USER]` / `[CONTEXT]` / `[UPSTREAM]` / `[PROJECT]`），呈现《现有科研上下文确认简报》，严禁对已知要素重复发问；
   - **同级冲突检测**：检测到无时间戳的同级资料矛盾时，标记 `UNRESOLVED_CONFLICT` 提交学者仲裁。
2. **Stage 0B：自适应科研决策追问 (Adaptive Research Grill-Me)**：
   - **只问未决高影响变量**：仅针对上下文未覆盖的 `CRITICAL` 与 `HIGH_IMPACT` 维度动态筛选 **3~5 个** 核心追问；
   - **每题必带推荐**：提供带有明确依据的 `(Recommended)` 选项与置信度标签；次要 `DEFAULTABLE` 维度自动应用学科透镜默认值；
   - **严格交互硬门禁 (STOP Rule)**：Agent 输出提问清单后，**必须立即终止当前回复，进入静默等待状态**，严禁自问自答或在同一轮次中偷跑下游工具。
3. **Stage 0C：协议快照生成与执行放行 (Protocol Snapshot & Execution Gate)**：
   - **低摩擦快捷回复**：支持一键全盘采纳（`按推荐` / `全部按推荐`）、紧凑选项（`1A 2B 3C`）与自然语言局部覆盖；
   - **全量来源可信追溯**：确认通过后输出带来源追溯（`[USER]` / `[CONTEXT]` / `[UPSTREAM]` / `[PROJECT]` / `[INFERRED]` / `[DEFAULTED]` / `[SYSTEM_RULE]`）的【Stage 0 Protocol Snapshot】，解锁下游实质执行。
4. **九大学科透镜 (Multi-Domain Lenses)**：
   - 系统支持加载 `shared/domain_lenses/` 下的 9 大规范学科透镜：`generic`（通用实证）、`biomedical`（生物医药 PICO）、`life_sciences`（生命科学与演化）、`ecology_environment`（生态与环境科学）、`computer_science`（计算机与基准复现）、`chemistry_materials`（化学与材料工程）、`physical_sciences`（物理与实验模拟）、`engineering`（工程与技术系统）、`social_sciences`（社会学因果推断）。

---

## 🧩 三大核心技能详解 (Skills Breakdown)

### 1. `literature-discovery-acquisition` (文献系统发现与全文获取)
> **定位**：高召回、可审计的文献检索、商业库人机协同摄取、PRISMA 双盲初筛与开源全文获取管道。

- **自适应决策门禁 `[PROTOCOL + ENGINE]`**：在发起检索前，基于 D1-D14 维度动态收敛研究实体、纳排边界与时间跨度。
- **双层数据源架构 (Data Source Architecture)**：
  - 🌐 **全自动检索层 (AUTOMATED Tier)**：集成 OpenAlex API、Crossref 与 PubMed，支持程序化关键词检索与双向引文滚雪球（Snowballing）；
  - 🔐 **人机协同商业库摄取层 (USER_ASSISTED Tier)**：知网 (CNKI)、万方、Web of Science、Scopus 受校园网 IP 准入与反爬机制保护，ScholarFlow 严格遵守学术安全规范，不采用逆向爬虫；系统自动生成目标库的标准高级布尔检索式（Boolean Syntax），由学者在机构网络下一键导出标准题录（Refworks / RIS / EndNote / CSV），随后由 `ingest_external_records.py` 执行本地批量硬解析与四级去重入库。
- **PRISMA 2020 Item 8 双盲独立初筛 `[PROTOCOL + DETERMINISTIC]`**：
  - 派发双评阅人独立盲审，基于内置工具自动计算 **Cohen's Kappa ($\kappa$)** 与一致率，生成符合发表级规范的 `screening_dual_audit.csv` 与分歧待仲裁队列。
- **双向引用滚雪球 `[DETERMINISTIC]`**：
  - 传入种子文献 DOI，利用 OpenAlex API 自动追溯参考文献（`Backward Snowballing`）并追踪施引文献（`Forward Snowballing`），自动补全学派谱系。
- **PRISMA-S 检索过程可审计清单 `[PROTOCOL]`**：全流程记录概念矩阵（Concept Matrix）、检索饱和度日志（Search Saturation）与去重决策表。
- **双轨运行模式**：
  - **交互工作流**：适合人类学者把关指导；
  - **Headless CLI 模式**：通过 `python scripts/agent_search.py -q "..."` 直接输出契约化 JSON 流。

---

### 2. `literature-evidence-extraction` (证据可信抽取与声明审计)
> **定位**：严格恪守 `Quote → Extract → Verify → Interpret` 铁律的结构化抽取与候选证据定位引擎。

- **0-10 分相关性前置快速剪枝 (Relevance Gatekeeper) `[HEURISTIC]`**：
  - 启发自 `PaperQA2` 评测基准。在进入全篇精读前，自动评估论文与课题契合度（0-10 分）。低于 6 分直接判定为 `PRUNE` 建议跳过，防止上下文污染与算力浪费。
- **顶刊审稿人四象限审计 (Reviewer 4-Quadrant Rubric) `[PROTOCOL]`**：
  - 自动提炼四大必答项：`Q1 科学动机`、`Q2 前人局限`、`Q3 方法创新`、`Q4 实验严谨性与混杂变量`。
- **抽取与综合严格解耦（Support Type vs Evidence Strength） `[DETERMINISTIC]`**：
  - **抽取溯源 (`support_type`)**：`EXPLICIT` (原文原句)、`DERIVED` (公式推导)、`REFERENCED` (前人转引)、`NOT_REPORTED` (全文未提及，入库权重恒为 0.0)；
  - **证据论证强度 (`evidence_strength`)**：`DIRECT_EMPIRICAL` (1.0)、`MODELED_EMPIRICAL` (0.8)、`AUTHOR_INTERPRETATION` (0.4)、`SECONDARY_EVIDENCE` (0.2)、`EXPERT_OPINION` (0.1)。
- **多实验体系隔离 (Assay Isolation) `[PROTOCOL]`**：
  - 自动隔离同篇文献中的不同实验（如：不同退火温度、不同引物组、不同位点），杜绝跨实验混淆。
- **候选证据定位与上下文协同检查 CLI `[DETERMINISTIC + HEURISTIC]`**：
  - `python scripts/audit_claims.py -i paper.pdf -c claims.json` 自动扫描原文，审计 PDF 解析质量，并在局部文本窗口内校验关键词与数值协同共现（Co-location）。

---

### 3. `literature-synthesis` (综合分析、学术争议发掘与学派图谱)
> **定位**：对标 PaperQA2 思路，推行 `Claims-first, narrative-later` 的学术争议诊断与跨篇证据综合专家。

- **9 大学术争议分类学体系 (Type A ~ Type I) `[HEURISTIC]`**：
  - 深入实验设计、采样偏差、探测率假定、等位基因脱落（ADO）、空间自相关与尺度依赖等底层技术根因。
- **多维证据评价与定性共识模型 `[DETERMINISTIC]`**：
  - 综合 `directness`、`independence`、`risk_of_bias` 和 `replication` 四维调整因子计算加权得分；
  - 严禁篇数多数决，将共识划分为 `STRONG_CONSENSUS`、`MODERATE_CONSENSUS`、`CONDITIONAL_CONSENSUS`、`ACTIVE_CONTROVERSY` 和 `INSUFFICIENT_EVIDENCE` 5 级定性梯队，并强制声明**空间、时间、方法与生物学四维硬性适用边界**。
- **红队反方质询（Devil's Advocate） `[LLM-ASSISTED]`**：
  - 专设红队审议角色，挖掘反对文献、离群数据与替代性假设，降低大模型的确认偏误。
- **方法学与范式演进总览 (`school_clustering.py`) `[DETERMINISTIC]`**：
  - 基于上游抽取字段（`paradigm`、`method`、`core_assumption`）执行确定性分桶汇总与年代更迭分析，区分 `ESTABLISHED SCHOOL` 与 `ANALYTICAL GROUPING`。
- **Mermaid 论证拓扑图自动可视化 (Argument Graph) `[DETERMINISTIC]`**：
  - CLI `controversy_analyzer.py` 自动绘制带色彩阵营（支持/反驳/调和边界）的论证网络拓扑图。
- **争议驱动型综述撰写规范 `[PROTOCOL + LLM-ASSISTED]`**：
  - 取缔流水账罗列，推行“核心分歧 → 冲突溯源 → 证据对决 → 边界共识 → 破局机遇”五步法。

---

## 📊 横向对比：ScholarFlow 与开源标杆

| 特性维度 | 传统 Agent / 通用 Prompt | GPT-Researcher | ChatPaper | Stanford STORM | **ScholarFlow (本项目)** |
|:---|:---:|:---:|:---:|:---:|:---:|
| **核心定位** | 泛化问答 / 代码辅写 | 互联网自动化研报生成 | 单篇 PDF 快速泛读总结 | 维基百科式长文条目编纂 | **全生命周期可审计科研调研、争议对决与可溯源综述** |
| **启动交互** | 盲目启动，易发散 | 单一搜索框 | 上传 PDF 直接读 | 多专家虚拟对话 | **Stage 0 Grill-Me 四级交互门禁** |
| **数据源支持** | 依赖通用搜索引擎 | 互联网搜索 API | 仅单篇本地 PDF | 维基式多轮检索 | **自动化开放库 (OpenAlex/PubMed) + 商业库无缝摄取 (CNKI/WoS)** |
| **引文扩展** | 仅依赖关键词搜索 | 搜索引擎扩展 | 无 | 维基式多轮检索 | **双向引用滚雪球 (OpenAlex Snowballing)** |
| **相关度剪枝** | 无剪枝，全量读 | 启发式过滤 | 无 | 大纲树剪枝 | **0–10 分 Relevance Gatekeeper (<6分剪枝)** |
| **抽取铁律** | 易产生浮动幻觉 | 总结文本片段 | 结构化问答 | 文本汇总 | **严格 Quote-First + 页码逐字绑定 + 上下文协同核验** |
| **争议分析** | 简单并列两派 | 文字综合报告 | 篇单维度 | 维基条目式汇总 | **9 类学术争议分类学 + 方法论根因溯源** |
| **共识算法** | 篇数多数决投票 | 频率多数决 | 无 | 综合叙述 | **多维证据评价 (Appraisal) + 定性共识梯队 + 硬性边界** |
| **防确认偏误** | 倾向于顺从与讨好 | 无独立对抗 | 无 | 多视角专家 | **专设 Devil's Advocate (红队反方质询)** |
| **可视化呈现** | 纯文本 | Markdown 表格 | 脑图/思维导图 | 目录大纲树 | **自动化 Mermaid 论证拓扑图 (Argument Graph)** |
| **外部依赖** | 复杂环境配置 | 庞大 Python 库 | 复杂依赖 | 较多依赖 | **纯 Python 3 标准库，零外部 Pip 依赖** |

---

## 🚀 快速开始 (Quick Start)

### 1. 一键安装到您的 Agent 系统

克隆本仓库并执行安装脚本，自动将三大技能安装至全局环境（支持 Claude Code、Antigravity 与通用 Agent）：

#### Windows (PowerShell)
```powershell
git clone https://github.com/Daylily-Huang/ScholarFlow.git
cd ScholarFlow
.\scripts\install.ps1
```

#### Linux / macOS (Bash)
```bash
git clone https://github.com/Daylily-Huang/ScholarFlow.git
cd ScholarFlow
chmod +x ./scripts/install.sh
./scripts/install.sh
```

---

### 2. 在 Agent 中直接唤醒与使用

只要您的 Agent 支持标准 `SKILL.md` 规范，输入如下指令即可直接激活对应能力，ScholarFlow 会根据课题自适应加载对应的学科透镜（Domain Lens）：

#### 💻 计算机科学 / AI (Computer Science Lens)
> *“请使用 `literature-discovery-acquisition` 帮我针对‘大语言模型 KV-Cache 动态剪枝与长文本评测基准’开展系统检索，通过 Stage 0 决策门禁锁定包含开源仓库与消融实验的纳入标准。”*

#### 🩺 生物医药 / 临床医学 (Biomedical Lens)
> *“请调用 `literature-evidence-extraction`，按照 PICO 临床诊断架构抽取这篇乳腺癌 AI 影像筛查文献中的灵敏度、特异性、AUC-ROC 及 95% 置信区间，恪守 Quote-First 铁律。”*

#### 🔋 材料科学 / 化学 (Chemistry & Materials Lens)
> *“请使用 `literature-synthesis` 对比这 6 篇钙钛矿太阳能电池文献，以合成工况（温度/退火气氛）为上下文隔离单元，诊断 2D/3D 钝化层提升湿热稳定性的共识与适用边界。”*

#### 📊 社会与行为科学 (Social Sciences Lens)
> *“请调用 `literature-synthesis`，针对‘混合办公制对知识工作者客观生产率与离职率的因果影响’，排查相关性偏倚与准实验内生性控制，输出加权证据对决与论证拓扑图。”*

#### 🌿 生命科学与生态学 (Life Sciences Lens)
> *“针对这批野生动物非损伤遗传学文献，使用 `literature-evidence-extraction` 严格按独立 Assay 隔离微卫星 PCR 分型体系与线粒体鉴别反应，严防退火温度与组分串染。”*

---

### 3. 三级质检与学术诚信架构 (Multi-Tier Audit Hierarchy)

ScholarFlow 严格拒绝“同一个大模型换角色念台词的伪独立审查”，以学术诚信为底线清晰划分质检层级：
- **Level-1 启发式角色自检 (In-Context Persona Audit)**：在单会话内通过 Quality Gatekeeper / Devil's Advocate 角色扮演打破思维惯性并核验清单。本质属于模型自省（Self-Consistency），不具有统计学外部独立性，签发的 PASS 声明为内部自检放行；
- **Level-2 确定性程序级硬审计 (Deterministic Programmatic Audit)**：由纯 Python 确定性脚本对事实与数据进行程序级验真，杜绝大模型幻觉与偏见：
  - `download_oa_papers.py`：PDF 二进制 `%PDF-` 魔数核验，拦截 403 伪装 HTML；
  - `ingest_external_records.py`：知网/万方/WoS 外部导出题录 Schema 硬解析与四级去重；
  - `calculate_screening_agreement.py`：双评阅人 Cohen's $\kappa$ 数学统计检验与分歧自动剥离；
  - `audit_claims.py`：正文局部上下文协同共现校验与 PDF 文本解析质量审计，辅助定位候选证据并拦截伪匹配；
  - `controversy_analyzer.py`：多维评价因子加权数学验算、定性共识梯队划分与 `NOT_REPORTED` 绝对零权重隔离；
- **Level-3 物理隔离子智能体审计 (Isolated SubAgent Execution)**：在支持多智能体并发调度的平台中，Gatekeeper 与 Screening Reviewers 均通过无共享上下文的独立 SubAgent 会话执行，实现真正的背对背双盲审议。

---

### 4. 独立运行配套 CLI 工具箱

ScholarFlow 配套的 Python 脚本均为纯标准库实现，支持独立作为命令行工具使用：

```bash
# 1. 知网 (CNKI) / 万方 / WoS / Scopus 题录一键极速摄取与去重
python skills/literature-discovery-acquisition/scripts/ingest_external_records.py -i cnki_theses.txt -o candidates.json --source CNKI

# 2. PRISMA 2020 Item 8 双评阅人背对背初筛一致性检验 (计算 Cohen's Kappa 并输出仲裁表)
python skills/literature-discovery-acquisition/scripts/calculate_screening_agreement.py -a rev_a.json -b rev_b.json -o report.md --csv audit.csv

# 3. 基于核心论文 DOI 发起双向引用滚雪球追溯
python skills/literature-discovery-acquisition/scripts/agent_search.py --snowball "10.1016/j.biocon.2020.108581" --limit 20 -o snowball.json

# 4. 对论文执行 0-10 分前置相关性剪枝评估与声明核验
python skills/literature-evidence-extraction/scripts/audit_claims.py -i paper.pdf -r "fecal DNA microsatellite snow leopard" --claim "PID-sibs was 0.0004"

# 5. 运行争议诊断分析并生成 Mermaid 论证拓扑图
python skills/literature-synthesis/scripts/controversy_analyzer.py -i claims.json -f markdown -o controversy_report.md

# 6. 运行学派谱系与范式演进聚类分析
python skills/literature-synthesis/scripts/school_clustering.py -i studies.json -f markdown -o school_report.md
```

---

## 📂 仓库结构 (Repository Structure)

```text
ScholarFlow/
├── schemas/                                   # 统一跨技能数据契约 (v1.0 JSON Schemas)
│   ├── scholarflow_contract.md               # 契约规范、语义解耦与字段映射定义
│   ├── literature_record.schema.json         # 检索输出与题录流标准 Schema
│   ├── evidence_record.schema.json           # 结构化抽取与证据溯源 Schema
│   ├── claim_record.schema.json              # 综述断言与多维证据评价 Schema
│   └── synthesis_record.schema.json          # 争议诊断与共识梯队 Schema
│
├── skills/                                    # 三大核心技能规范与资产
│   ├── literature-discovery-acquisition/      # 文献系统发现与全文获取
│   │   ├── SKILL.md                          # 技能规范入口
│   │   ├── scripts/                          # agent_search.py, download_oa_papers.py,
│   │   │                                     # ingest_external_records.py, calculate_screening_agreement.py
│   │   ├── references/                       # PRISMA-S, Stage 0, 双盲初筛, 商业库摄取, Zotero联动
│   │   └── assets/                           # 检索日志、概念矩阵、CSL-JSON Schema
│   │
│   ├── literature-evidence-extraction/        # 证据可信抽取与声明审计
│   │   ├── SKILL.md                          # 技能规范入口
│   │   ├── scripts/                          # audit_claims.py, pdf_evidence_locator.py
│   │   ├── references/                       # Quote-First 铁律, E1-E4 解耦, 实验隔离
│   │   └── assets/                           # 结构化抽取 Schema, 审稿人四象限模板
│   │
│   └── literature-synthesis/                  # 学术争议发掘、学派谱系与边界共识
│       ├── SKILL.md                          # 技能规范入口
│       ├── role/                             # 总控、争议、学派、红队质询与门禁
│       ├── scripts/                          # controversy_analyzer.py, school_clustering.py
│       ├── references/                       # 9类争议分类学, 5级定性共识与边界, 综述指南
│       └── assets/                           # 争议图谱、论证拓扑图、上游空白请求模板
│
├── benchmarks/                                # 科研性能基准评测集 (ScholarFlow Benchmark v0.1)
│   ├── data/                                 # 发现、抽取、声明核验与争议综合黄金测试集
│   └── run_benchmarks.py                     # 基准测试执行引擎与度量报告生成器
│
├── tests/                                     # 机械门禁、对抗用例与跨技能契约测试套件
│   ├── fixtures/                             # 真实格式题录与数据样本
│   ├── test_claim_linter.py                  # 综述 Claim ID 溯源门禁测试
│   ├── test_quote_audit.py                   # 原文引用机械对齐门禁测试
│   ├── test_screening_agreement.py           # 双评阅人 Cohen's Kappa 数学校验测试
│   ├── test_ingest_external_records.py       # CNKI / RIS / EndNote / CSV 解析测试
│   ├── test_cross_skill_contract.py          # 跨技能单向契约与解耦测试
│   ├── test_adversarial_gates.py             # 多实验串值与低独立性对抗测试
│   └── test_benchmarks.py                    # 基准度量持续集成测试
│
├── scripts/                                   # 一键安装脚本 (install.ps1 / install.sh)
├── pyproject.toml                             # PEP 517/621 标准包配置 (含 [pdf] 可选依赖)
├── .gitignore
├── LICENSE                                    # MIT License
└── README.md                                  # 项目说明文档
```

---

## 🧪 测试与科研基准 (Testing & Benchmarks)

### 1. 自动化单元与契约测试套件

本仓库测试套件仅使用 Python 标准库（`unittest`），零第三方强制依赖：

```bash
# 运行全量单元、契约、跨学科中立性与对抗测试
python -m unittest discover -s tests -v
```

覆盖范围：
- **统计学闭式解**：双评阅人 Cohen's $\kappa$ 数学统计检验（闭式解验证）；
- **外部题录硬解析**：知网 CNKI Refworks、RIS、EndNote `.enw` 与 CSV 四格式解析；
- **机械审计门禁**：引句回查校验门（`quote_audit.py`）与 Claim ID 可溯源门禁（`claim_linter.py`）；
- **数据契约防错**：`schemas/` 校验，确保 `support_type: NOT_REPORTED` 绝对赋予 0.0 权重；
- **上下文决策门禁**：Context-Aware Grill-Me 9 大场景测试，验证上下文自动继承、同级冲突仲裁与正交隔离；
- **跨学科中立性审查**：Domain Neutrality Linter 自动化扫描核心协议与门禁，严禁单一学科偏置；
- **跨平台 CI**：GitHub Actions（`.github/workflows/ci.yml`）自动在 Python 3.9 / 3.11 / 3.13 上运行测试与基准。

### 2. ScholarFlow 评测集与内部回归基准 (v0.1)

运行独立的自动化科研评测基准：

```bash
python benchmarks/run_benchmarks.py
```

| 评测维度 (Benchmark Dimension) | 核心科研质量指标 (Target Metric) | 目标阈值 | 实测表现 (Measured) | 门禁状态 |
|:---|:---|:---:|:---:|:---:|
| **抽取契约基准 (Extraction)** | **NR Accuracy** (敢于报告未提及，严防无中生有) | 100.0% | `100.0%` | **[PASS]** |
| | **Field Precision** (字段级精准抽取率) | ≥ 95.0% | `100.0%` | **[PASS]** |
| **声明核验 (Claim Audit)** | **Accuracy** (局部上下文协同对齐率) | ≥ 90.0% | `100.0%` | **[PASS]** |
| | **False-Support Rate** (错误断言误判支持率，科研最高危指标) | **0.00%** | `0.0%` | **[PASS]** |
| **综合争议 (Synthesis)** | **Consensus Calibration** (共识梯队与边界标定准确率) | 100.0% | `100.0%` | **[PASS]** |

---

## 📊 能力成熟度与验证分级 (Capability Maturity Matrix)

按照 ScholarFlow 证据分级哲学（Level 1 单元测试 → Level 2 合成回归验证 → Level 3 人工金标验证 → Level 4 外部跨学科验证），各核心能力当前成熟度界定如下：

| 核心能力模块 (Capability) | 当前成熟度与验证级别 (Current Status) | 备注说明 |
|:---|:---:|:---|
| OpenAlex 元数据检索与解析 | `LEVEL 1 — UNIT-TESTED` | 标准库 HTTP 请求与 JSON 解析已全面覆盖 |
| 双向引用滚雪球 (Snowballing) | `LEVEL 1 — UNIT-TESTED` | 前向与后向引文追踪算法闭环验证通过 |
| 商业库人机协同导出清洗 | `LEVEL 1 — UNIT-TESTED` | CNKI、RIS、EndNote、CSV 硬解析闭式验证通过 |
| 上下文感知决策门禁 (Context Resolution) | `LEVEL 2 — SYNTHETIC REGRESSION` | 5 层来源递进与 9 大典型上下文场景全覆盖 |
| 自适应动态追问 (Adaptive Grill-Me) | `LEVEL 1 — UNIT-TESTED` | 优先级筛选、预算硬门禁与来源追溯快照全部通过 |
| PDF 局部证据定位 (Evidence Locator) | `LEVEL 1 — OPTIONAL PDF PARSER` | 表层文字与数值协同定位（非语义事实裁决） |
| 语义事实裁决 (Semantic Claim Audit) | `AGENT / HUMAN ADJUDICATION REQUIRED` | 定位器提供候选线索，必须由 Auditor 最终裁定 |
| 证据共识度启发式分级 | `EXPERIMENTAL / HEURISTIC` | 启发式平衡打分，须经质检员定性复核 |
| 学派聚类与争议诊断 | `EXPERIMENTAL / HEURISTIC` | 规则分桶与方法学关联，非无监督图聚类 |
| 外部真实论文跨学科盲测 | `NOT YET VALIDATED (LEVEL 3-4 PLANNED)` | 正在建设大规模真实金标测试集 |

---

## ⚠️ 局限性与已知边界 (Known Limitations)

为确保严谨科研，使用者应当知晓本工具套件的设计边界：
1. **依赖上游 PDF 解析质量**：`audit_claims.py` 基于提取文本进行协同匹配。若文献为老旧扫描版、低分辨率图像或无 OCR 文本层，定位置信度会显著下降（脚本将显式打出 `[WARN] LOW_OCR_SUSPECT` 警告）。
2. **商业数据库访问边界**：知网、万方、Web of Science 等商业数据库受版权保护与反爬限制，ScholarFlow 不提供越权逆向抓取功能，采用“标准布尔表达式生成 + 机构网络导出题录 + 本地批量清洗”的合规人机协同范式。
3. **启发式工具的非因果性**：`controversy_analyzer.py` 的争议分类与 `school_clustering.py` 的范式分桶基于确定性加权与元数据统计，并非无监督网络社区发现（如 Louvain 图聚类）或因果图推断，结果需结合专业领域知识研读。
4. **单模型自检非真正双盲**：在单会话内通过提示词扮演的 Gatekeeper 或 Devil's Advocate 属于模型自我反省机制（Self-Consistency），在统计学上不具备真正多专家双盲审议的独立性。建议重要结论采用 Level-3 物理隔离子智能体调度或人工最终复核。

---

## 🤝 贡献与反馈 (Contributing)

欢迎科研同仁、导师学者以及 AI Agent 开发者提交 Issue 和 Pull Request！
- 贡献新的领域画像文件（如：医学、材料学、计算社会学等）
- 优化数据抽取与清洗算法
- 分享在博士/硕士学位论文开题与写作中的实战经验

---

## 📄 开源许可证 (License)

本项目基于 [MIT License](LICENSE) 开源发布。您可以自由地在学术研究、个人项目或商业应用中使用、修改与集成。


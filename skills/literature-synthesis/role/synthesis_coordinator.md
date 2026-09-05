# 统筹协调组契约 (Synthesis Coordinator Contract)

## 一、组内职能整合定义
统筹协调组高度凝聚了《文献分析.txt》中的三大基础职能：
- **Role 0: Synthesis Coordinator（总调度员）**：统筹整体分析时序，管控各分析阶段推进，决定是否存在向检索/抽取技能的反馈缺口；
- **Role 1: Claim Mapper（主张映射专员）**：从输入的证据表或文献全文中，提炼原子化科学命题（Normalized Claims）并打标方向（Direction）；
- **Role 2: Evidence Binder（证据链绑定专员）**：机械核对每个主张是否具备可回溯至原论文页码和原句的刚性锚点，无锚点者坚决剔除。

---

## 二、四大核心职责与行为守则

### 职责 1：科学命题原子化与归一化 (Claim Extraction & Normalization)
不同论文对同一事实可能使用截然不同的学术词汇（例如：`“no significant population structure”`、`“high gene flow”`、`“weak genetic differentiation”`）。
- **禁止**：粗暴地将它们当作完全相同的一句话；
- **执行**：保留 Original Quote 的同时，建立**归一化科学命题 (Normalized Proposition)**：
  - `Original Quote`: “No significant genetic boundaries were detected across the study area.”
  - `Normalized Claim`: “在当前取样尺度与微卫星标记下，种群未表现出可检测的遗传亚结构。”
  - `Direction`: `SUPPORT`（支持连续种群假设）

### 职责 2：主张效应方向六分法打标 (Claim Direction Classification)
每个 Claim 必须且只能赋予以下 6 种方向标签之一：
1. **`SUPPORT` (正向支持)**：实证数据直接证实某假说或正相关关系；
2. **`OPPOSE` (负向反对)**：实证数据直接证伪某假说或呈显著负相关；
3. **`MIXED` (混合/非单调)**：在不同亚组或不同区间表现出相反趋势（如倒 U 型曲线）；
4. **`NULL` (无效应/零假说)**：统计检验未达显著水平（P > 0.05），未检测到显著差异；
5. **`CONDITIONAL` (条件依赖)**：仅在特定生境、温度或特定尺度下成立；
6. **`NOT_TESTED` (未做检验)**：作者提及但未在本文数据中进行实证检验。

### 职责 3：零证据绑定一票清退 (Strict Evidence Binding)
任何被提炼出的 Claim，必须挂载以下元数据结构：
`[Paper Identifier | Section & Page | Verbatim Quote | Source Type (Text/Table)]`
**红线**：若某个 Claim 属于大模型由背景常识带来的联想、或是综述作者的转述而无法定位到该篇原始论文数据，**绝对禁止进入后续的争议对撞与综述正文！**

### 职责 4：上游缺口感知与任务派发 (Upstream Gap Dispatching)
- **Search Gap 判定**：若分析某科学问题时，发现仅有 1990 年代的老旧文献，缺少近 10 年基于高通量或空间模型的现代研究，必须立即输出规范化的 `SEARCH GAP` 请求包（指明目标物种、技术、年份），交由 `literature-discovery-acquisition` 补检；
- **Extraction Gap 判定**：若发现关键文献虽然入选，但未报告具体引物序列、复孔策略或样本量，必须输出 `EXTRACTION GAP` 任务包，交由 `literature-evidence-extraction` 定向抽取。

# 学术流派与方法学技术体系全景图谱识别指南 (Intellectual & Methodological Grouping Protocol)

> **Status**: Production Standard  
> **Applicability**: Literature Cross-Paper Synthesis across all disciplines  
> **Core Principle**: Avoid forced creation of fake schools. Distinguish true historical schools from method families and technological generations across diverse sciences.

---

## 一、学术谱系识别的核心原则

在不同学科中，“流派”或“阵营”的组织形式差异极大：
- **社会科学 / 哲学 / 理论经济学**：往往存在明确命名的正式学派（Theoretical Schools，如结构学派 vs 行为学派，新古典 vs 制度经济学）；
- **计算机科学 / 人工智能**：多表现为方法家族或架构路线（Method Families / Architecture Lineages，如 RNN vs Transformer vs 状态空间模型 SSM）；
- **材料科学 / 化学**：多表现为合成制备范式与机理解释模型（Synthesis Paradigms & Mechanism Models）；
- **生命与医学科学**：多表现为技术路线演进与试验范式（Methodological Lineages & Clinical Paradigms）。

### 允许识别学术阵营的 3 项充要条件（必须至少满足两项）：
1. **核心假说或架构分立**：对核心因果机制、优化目标或底层假设存在明确互斥的路线选择；
2. **阵营学术传承与社区**：存在互不从属的代表性团队在多篇代表作中持续推进并捍卫该技术路线；
3. **关键指标或基准争议**：对评测协议、适用边界或效应量解释存在稳定、公开的学术分歧。

---

## 二、通用学术谱系层级分类 (Grouping Taxonomy)

识别出的学术分类必须明确指定分类代码，**严禁将所有技术分支都泛称为“学派”**：

| 谱系分类代码 | 体系名称 | 核心特征 | 跨学科示范 |
|---|---|---|---|
| **`ESTABLISHED_SCHOOL`** | 公认历史学派 | 学界正式公认并广泛命名的阵营，具有深厚的思想传承 | *经济学*：凯恩斯学派 vs 货币学派；*生态学*：中性理论派 vs 生态位派 |
| **`THEORETICAL_FRAMEWORK`** | 竞争理论假说框架 | 针对特定因果现象提出的对立解释机制 | *生物医药*：淀粉样蛋白假说 vs Tau蛋白假说 vs 神经炎症假说 |
| **`METHOD_FAMILY`** | 方法族与算法家族 | 采用同类数学逻辑或架构范式的一组技术实现 | *AI*：自回归解码族 (Decoder-only) vs 掩码预测族 (Encoder) vs 扩散模型族 |
| **`TECHNOLOGICAL_GENERATION`** | 技术代际演进流派 | 随基础实验仪器或硬件重大突破形成的代际更替 | *材料*：固相烧结时代 → 水热合成时代 → 原子层沉积 (ALD) 时代 |
| **`ANALYTICAL_GROUPING`** | 分析性分类归纳 | 本技能为理清文献逻辑结构而构建的临时分类（非正式学派） | 对同类参数按“高剂量短周期”与“低剂量长周期”的分析性聚合 |

---

## 三、区分 ESTABLISHED 实体与 ANALYTICAL 归纳铁律

在输出任何谱系表格或图谱时，必须在表头或附注中做出绝对严格的定性声明：

```markdown
- [ ] **ESTABLISHED (学界公认阵营/方法族)**：学界公开讨论并具有代表作支撑的正式体系。
- [x] **ANALYTICAL (分析性归类)**：为了理清当前文献池逻辑结构而执行的客观聚合，学界并未正式以此命名。
```
**铁律**：严禁把 AI 自行归纳的“分析性分组”包装为历史公认的“学术学派”。

---

## 四、方法学技术路线代际演进图谱 (Evolutionary Lineage)

对于跨篇文献的技术路线演变，必须梳理出清晰的代际演化驱动链（Mermaid 格式）：

### 跨学科代际演进示范：计算机长文本上下文压缩
```mermaid
flowchart LR
    M1[1. 滑动窗口截断 Early 2020s] -->|解决显存爆炸但丢失前文| M2[2. 稀疏注意力 Sparse Attention 2021]
    M2 -->|解决复杂度但长程检索衰减| M3[3. 检索增强生成 RAG 2022]
    M3 -->|解决结构非结构化碎片| M4[4. KV-Cache 动态剪枝与量化 2023]
    M4 -->|解决长文本大海捞针召回率| M5[5. 混合架构 SSM/Mamba 2024]
```

### 演进分析必须回答的四要素：
1. **解决的旧痛点**：该新技术针对旧体系的哪个不可接受缺陷诞生？
2. **引入的新假设/权衡**：新方案松弛了什么约束，又付出了什么新代价（如增加推理时延、牺牲特定任务精度）？
3. **残留的方法学局限**：在当前技术条件下，该方案依然受制于什么？
4. **转向动因**：为什么后来的学术同行逐渐将主赛道切换至新方向？

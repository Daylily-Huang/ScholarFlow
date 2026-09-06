# 六级共识度评级体系与通用边界标定规程 (Consensus Levels & Universal Boundaries Protocol)

> **Status**: Production Standard  
> **Applicability**: Literature Cross-Paper Synthesis across all disciplines  
> **Core Axiom**: Scientific consensus is never determined by a democratic vote of paper counts. It is bounded by methodological rigor and explicit operational boundaries.

---

## 一、为什么严禁“论文篇数民主投票”？ (Rejection of Democracy by Paper Count)

在很多劣质综述中，作者经常使用粗糙的“投票统计”：
> “在收集到的 10 篇论文中，7 篇支持结论 A，3 篇反对，因此我们得出结论：A 得到了学术界的广泛证实。”

**这种“论文数量多数决”是极度危险的伪科学**，因为：
1. 这 7 篇论文可能来自同一个团队在同一数据集/试验点上的切片发表；
2. 这 7 篇论文可能采用的是已被淘汰的早期低精度方法或存在严重系统偏倚；
3. 而那 3 篇反面论文，可能是近期由独立高水平团队在控制了核心混杂变量后取得的突破性证据。

**共识评级的核心法则**：
**科学结论不是由人头数决定的，而是由证据权重、方法严密性、独立重复性与明确的适用边界共同决定的。**

---

## 二、六级共识度评级体系 (Consensus Hierarchy)

针对每一个核心科学命题，必须根据多维证据加权评定为以下 6 个等级之一：

| 共识等级代码 | 等级全称 | 判定硬指标 | 典型表述模板 |
|---|---|---|---|
| **`STRONG_CONSENSUS`** | 强共识 | 存在多个互不隶属的独立研究团队，采用不同技术路线（如实验+仿真+理论推导），在异质条件下均取得高度一致结论 | “学界已形成高度共识，多源独立实证证据一致证实……” |
| **`MODERATE_CONSENSUS`** | 中度共识 | 绝大多数高质量研究支持该结论，但存在个别特殊工况或极限边界下的合理例外 | “现有多数高质量证据倾向于支持……，但在特定极端条件下存在例外” |
| **`CONDITIONAL_CONSENSUS`** | 条件共识 / 边界共识 | 该结论**仅在特定严苛前置条件满足时**才成立，脱离该条件则失效 | “在满足 [前置条件X] 的前提下形成一致认知，但在 [工况Y] 下分歧未决” |
| **`ACTIVE_CONTROVERSY`** | 活跃争议 / 正面对抗 | 存在两组或多组高质量的对立文献，各方方法学均相对严谨，直接实证冲突（Type A/B）未解 | “学界当前对该问题存在显著学术争议，主要分歧集中于……” |
| **`EMERGING_VIEW`** | 新兴假说 / 趋势前沿 | 近 3–5 年由新技术/新范式推动的高质量前沿研究开始集中指向新结论，但样本积累尚有限 | “近期前沿研究展现出向……汇聚的新趋势，但尚待更大范围独立验证” |
| **`INSUFFICIENT_EVIDENCE`** | 证据不足 / 孤证存疑 | 全文池中仅有 1–2 篇孤立研究，或样本量极小、方法存在明显系统缺陷 | “现有实证证据严重匮乏，尚不足以对该命题形成确定性科学论断” |

---

## 三、通用多维边界标定体系 (Universal Boundary Model)

任何被评定为 `STRONG`、`MODERATE` 或 `CONDITIONAL` 的共识，**必须在输出时强制绑定适用边界**。根据学科领域按需激活以下通用维度：

```text
┌───────────────────────────────────────────────────────────────┐
│                 Universal Boundary Model                      │
├──────────────────────────┬────────────────────────────────────┤
│ 1. Entity / Population   │ 目标实体、人群或材料体系范围         │
│ 2. Context Boundary      │ 试验工况、环境介质或测试基准         │
│ 3. Methodological        │ 实验设计、技术路线或算法架构限制     │
│ 4. Measurement Boundary  │ 仪器精度极限、指标定义与误差范围     │
│ 5. Temporal Boundary     │ 时间尺度、数据采集窗口或演化阶段     │
│ 6. Geographic / Spatial  │ 空间尺度、地理网格或宏观区域外推限制 │
│ 7. Theoretical Boundary  │ 底层机制假设或理论模型适用域         │
└──────────────────────────┴────────────────────────────────────┘
```

### 跨学科边界标定示范：

#### 示范 A：计算机科学 (AI / 检索增强大模型 RAG)
```markdown
> **共识命题**：密集检索（Dense Retrieval）结合重排序（Reranker）在长文本问答准确率上显著优于稀疏检索 (BM25)
> **共识评级**：`CONDITIONAL_CONSENSUS`
> **适用边界**：
> 1. **Entity / Model 边界**：仅在底层 Embedding 维度 ≥ 768 且针对专业领域微调的模型中成立；
> 2. **Context 边界**：在文档长度在 4k–32k tokens 内成立；当文档超过 128k 时因注意力稀释出现衰减；
> 3. **Measurement 边界**：以 Top-5 Hit Rate 与 Answer Accuracy 评测；纯时延 (Latency) 维度不具备优势。
```

#### 示范 B：生命科学与生态学
```markdown
> **共识命题**：非损伤性遗传标记可用于个体识别与种群密度评估
> **共识评级**：`CONDITIONAL_CONSENSUS`
> **适用边界**：
> 1. **Context / 样本质量边界**：仅在新鲜干燥保存的样本中成立；
> 2. **Methodological 边界**：必须执行严格的独立复孔检验以控制等位基因脱落率 (ADO)；
> 3. **Measurement 边界**：标记多态性累积识别概率必须满足 $PID_{sibs} < 0.01$；
> 4. **Spatial 边界**：适用于有边界的地理样带，不宜随意向无界大尺度空间粗放外推。
```

#### 示范 C：材料与化学 (钙钛矿太阳能电池)
```markdown
> **共识命题**：引入 2D/3D 异质结界面钝化可显著提升钙钛矿电池湿热稳定性
> **共识评级**：`MODERATE_CONSENSUS`
> **适用边界**：
> 1. **Entity 边界**：主要在甲脒基 (FA-based) 铅碘体系中验证充分，对全无机体系适用性尚待评估；
> 2. **Context 边界**：在 85°C / 85% RH 双 85 湿热老化标准测试下成立；
> 3. **Methodological 边界**：要求后处理退火温度严格控制在 100±5°C 以内，防止 2D 相结构热相变降解。
```

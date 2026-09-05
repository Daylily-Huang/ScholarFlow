# 深度检索全流程案例：鹿科动物粪便 DNA 微卫星个体识别 (Deep Search Ecology Case)

本案例完整演示 `literature-discovery-acquisition` Skill 在生态学与保护遗传学复杂课题下的端到端执行全过程。

---

## Stage 0: 问题拆解与前置 Grill-Me 交互

### 1. 用户初始输入
> “我想搜一下国内外利用粪便 DNA 微卫星技术进行黑麂或鹿科动物个体识别和种群数量估算的相关研究论文。”

### 2. Agent 自动初稿推荐呈现
Agent 快速完成语义解构，在对话中主动呈现初稿：
- **研究范围初稿**：
  - 核心问题：非损伤性遗传取样（粪便）+ 微卫星（STR/SSR）进行鹿科个体识别与种群评估；
  - 核心对象：黑麂 (*Muntiacus crinifrons*) 及扩展鹿科物种 (*Cervidae*)；
- **概念矩阵初稿**：拆解为 4 个概念桶（C1 样本类型、C2 分子标记、C3 科学目标、C4 鹿科分类群）；
- **推荐重点期刊初稿**：
  - Tier 1: *Molecular Ecology*, *Conservation Biology*, *Ecology*
  - Tier 3: *Trends in Ecology & Evolution*
  - Tier 4: 《兽类学报》、《生态学报》、《生物多样性》

### 3. Agent 发起 Grill-Me 决策提问
```markdown
基于您的研究课题，为了确保检索既具学术代表性又避免遗漏关键文献，请对以下 3 个关键边界进行决策：

1. 【检索深度与模式】
   - (Recommended) Deep Search：执行多数据库联合检索、多轮词矩阵扩展、种子文献引文双向追踪与饱和度审计
   - Quick Search：仅提取 15–20 篇领域权威顶刊论文快速研读
2. 【文献类型与灰色文献】
   - (Recommended) 包含同行评议研究论文、权威综述与中国硕博士学位论文（CNKI 优秀博硕士论文库常包含大量第一手非损伤标记参数）
   - 仅限同行评议英文期刊论文，排除学位论文与会议报告
3. 【时间跨度与语言】
   - (Recommended) 中英双语全覆盖，时间不设下限（保留 1997 年非损伤微卫星开创奠基文献，重点高亮 2010–2026 近年研究）
   - 仅限 2015 年以后最新发表的英文研究
```

### 4. 用户确认反馈
用户选择全部采用推荐配置（(Recommended)）。

### 5. 锁定检索协议快照
```markdown
> **已锁定检索协议快照**：
> - 课题：利用粪便 DNA 微卫星进行黑麂/鹿科个体识别与种群估算
> - 模式：Deep Search
> - 范围：中英双语 / 期刊论文 + 综述 + 学位论文 / 全时段（包含奠基性工作）
> - 数据源调度：OpenAlex + PubMed + Europe PMC + Web 广域搜索 + CNKI/WoS 人工补检式生成
```

---

## Stage 1: 概念矩阵确立 (Concept Matrix)

| Concept ID | 概念分类 | 核心词 (Core) | 同义词与缩写 (Synonyms) | 拼写变体 (Variants) | 上位/下位词 (Hierarchical) | 受控词 (MeSH/NCBI) | 中文对应词 |
|---|---|---|---|---|---|---|---|
| **C1** | 样本类型 | fecal DNA | scat, pellet, dung | faecal DNA, noninvasive, non-invasive | excrement, environmental DNA | MeSH: Feces | 粪便DNA, 粪便样品, 非损伤性取样 |
| **C2** | 分子标记 | microsatellite | STR, SSR | short tandem repeat | simple sequence repeat, VNTR | MeSH: Microsatellite Repeats | 微卫星, 简单重复序列, 短串联重复 |
| **C3** | 科学目标 | individual identification | genetic tagging, fingerprinting | individual recognition | population estimation, capture-recapture, Capwire | MeSH: DNA Fingerprinting | 个体识别, 遗传标记, 种群数量估算 |
| **C4** | 研究对象 | Muntiacus crinifrons | black muntjac | Muntiacus | Cervidae, deer, cervid, ungulate | NCBI: Muntiacus crinifrons | 黑麂, 麂属, 鹿科, 鹿类, 有蹄类 |

---

## Stage 2: 推荐重点期刊与检索式扩展

### 1. 四层级重点期刊推荐
- **Tier 1 (旗舰/顶刊)**：*Molecular Ecology*, *Conservation Biology*, *PNAS*
- **Tier 2 (核心专业)**：*Journal of Applied Ecology*, *Biological Conservation*, *Heredity*, *Journal of Mammalogy*, *Mammal Research*
- **Tier 3 (权威综述)**：*Trends in Ecology & Evolution*, *Biological Reviews*, *Annual Review of Ecology, Evolution, and Systematics*
- **Tier 4 (中文核心/CSCD)**：高亮《兽类学报》（国内非损伤遗传学核心阵地）、《生态学报》、《生物多样性》

### 2. 数据库来源过滤代码块
```text
SO=("Molecular Ecology" OR "Conservation Biology" OR "Biological Conservation" OR "Journal of Applied Ecology" OR "Heredity" OR "Mammal Research" OR "Trends in Ecology & Evolution")
```

### 3. 多组针对性检索式派生
- **Q01 (高精核心式)**：
  `("fecal DNA" OR "faecal DNA" OR "noninvasive genetic") AND ("microsatellite*" OR "STR") AND ("individual identification" OR "genetic tagging") AND ("Muntiacus crinifrons" OR "black muntjac")`
- **Q02 (高召回鹿科扩展式)**：
  `("fecal" OR "faecal" OR "scat" OR "pellet") AND ("DNA") AND ("microsatellite*" OR "SSR" OR "STR") AND ("individual identification" OR "population estimation") AND ("Cervidae" OR "deer" OR "cervid" OR "muntjac")`
- **Q03 (方法学质控式)**：
  `("fecal DNA" OR "faecal DNA") AND ("microsatellite") AND ("allelic dropout" OR "false allele" OR "multi-tube" OR "genotyping error")`
- **Q04 (中文核心专业检索式)**：
  `(主题 = '粪便DNA' + '非损伤') AND (主题 = '微卫星' + 'STR') AND (主题 = '黑麂' + '麂' + '鹿科')`

---

## Stage 3: 多数据源协同检索

Agent 调用 API 与学术搜索工具并行执行：
1. **OpenAlex REST API**：检索 Q01, Q02，返回记录 184 条；
2. **PubMed / NCBI E-utilities**：检索 Q01, Q02, Q03，返回记录 92 条；
3. **Europe PMC**：检索 Q03（针对微卫星基因分型假等位基因与多次 PCR 质控文献），返回记录 48 条；
4. **Web 学术广域探测**：补充检索近 3 年新发表但尚未被传统索引收录的鹿科案例，返回 32 条；
5. **原始捕获总数**：356 条题录。

---

## Stage 4: 四级渐进式去重流水线

1. **Level 1 (DOI 匹配)**：归一化 DOI 匹配成功并合并 142 条重复记录；
2. **Level 2 (PMID 匹配)**：匹配合并 31 条；
3. **Level 3 (归一化标题精确匹配)**：匹配合并 19 条；
4. **Level 4 (第一作者姓氏 + 出版年 + 标题相似度 > 90%)**：消除 8 条拼写与标点差异导致的隐性重复；
5. **去重后独立候选文献总数**：**156 篇**（每篇完整保留 `source_databases` 来源列表）。

---

## Stage 5: 题录与摘要结构化初筛

对 156 篇文献依据预设标准进行判定：
- **Include (纳入)**：**52 篇**（直接涉及鹿科/黑麂粪便 DNA 微卫星个体识别或种群估算）；
- **Uncertain (待定)**：**14 篇**（如：摘要仅提及“有蹄类非损伤遗传调查”，未明确列举物种；或涉及非微卫星 SNP 方法，但包含种群标记对比，予以保留至全文阶段）；
- **Exclude (排除)**：**90 篇**（主要触发原因：`EXC_TAXON` 非鹿科食肉动物粪便研究、`EXC_METHOD` 纯胃内容物食性分析无遗传标记、`EXC_TOPIC` 纯微卫星位点引物开发无个体识别实证）。

---

## Stage 6: 核心种子文献双向引文追踪

挑选 3 篇里程碑式种子文献 (Seed Papers)：
1. **Seed 1 (国际经典方法)**：*Kohn & Wayne (1997)* Facts from feces revisited. *Trends Ecol Evol*. (奠基性综述)
2. **Seed 2 (质控规范)**：*Taberlet et al. (1996)* Reliable genotyping of samples with very low DNA quantities using PCR. *Nucleic Acids Res*. (多管 PCR 质控开创者)
3. **Seed 3 (黑麂本地实证)**：*Zheng et al. (2012)* Noninvasive genetic estimation of black muntjac population size. *Conservation Genetics*. (本地实证突破)

**追踪结果**：
- **Backward Chasing (反向追溯参考文献)**：捕获 38 篇文献，去重后新增有效纳入 6 篇（大多为早期鹿科微卫星引物跨物种通用性经典论文）；
- **Forward Chasing (正向追踪施引文献)**：捕获引用 Zheng et al. 的后续施引文献 29 篇，经初筛纳入 4 篇（均为近 5 年中国森林有蹄类非损伤微卫星新研究）；
- **重筛入库**：共计 10 篇通过初筛进入有效文献库。

---

## Stage 7: 检索饱和度收敛审计

### 1. 轮次边际贡献表

| 轮次 | 阶段操作与来源 | 检出数 | 去重后新增 | 初筛有效数 (Include+Uncertain) | 边际收益率 | 累计有效文献 |
|:---:|---|:---:|:---:|:---:|:---:|:---:|
| **Round 1** | Q01-Q02 核心词矩阵 API 检索 | 276 | 125 | 45 | 100% (基线) | 45 |
| **Round 2** | Q03-Q04 方法与分类群扩展检索 | 80 | 31 | 21 | 46.7% | 66 |
| **Round 3** | Seed 1-3 参考文献反向追溯 (Backward) | 38 | 12 | 6 | 13.3% | 72 |
| **Round 4** | Seed 1-3 施引文献正向追踪 (Forward) | 29 | 7 | 4 | 8.9% | 76 |
| **Round 5** | 核心作者课题组成果网络拓扑 | 15 | 2 | 1 | 2.2% | 77 |

### 2. 饱和度结论与声明
> **检索收敛声明**：第 5 轮次新增初筛有效文献仅为 1 篇（边际收益率降至 2.2%），引文重叠率达到 86.7%，表明在当前设定的概念矩阵与数据源边界下，**检索已接近边际饱和**。本策略尚不能证明绝对不存在历史或未入库文献的遗漏，已附带商业数据库人工补检式供进一步复核。

---

## 交付产物汇总 (Deliverables)

1. **结构化候选文献表**（导出为 `candidate_literature.csv`，含 77 篇文献完整题录、DOI、证据分级 `VERIFIED` 与初筛状态）；
2. **文献管理软件导入文件**（导出为 `literature_pool.bib`，包含全部 77 篇规范 BibTeX 词条）；
3. **商业数据库人工补检代码块**：
   - **中国知网 (CNKI)**：
     ```text
     (主题='粪便DNA' OR 主题='非损伤取样') AND (主题='微卫星' OR 主题='STR') AND (主题='黑麂' OR 主题='麂属' OR 主题='鹿科')
     ```
   - **Web of Science 核心合集**：
     ```text
     TS=(("fecal DNA" OR "faecal DNA" OR "noninvasive") AND ("microsatellite*" OR "STR") AND ("individual identification" OR "genetic tagging") AND ("Muntiacus" OR "Cervidae" OR "deer"))
     ```
4. **下一步推荐**：
   > “检索阶段已高质量完成。若需获取具体的多管 PCR 反应参数、退火温度、等位基因丢失率（ADO）及引物扩增片段范围，请将下载的全文文献提交给 **literature-extraction** 专用处理模块，禁止在本阶段根据摘要推断实验数值。”

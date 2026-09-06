# Domain Lens: Life Sciences & Ecology (生命科学与生态演化)

> **Lens Code**: `life_sciences`  
> **Applicability**: Ecology, evolutionary biology, zoology, botany, microbiology, conservation genetics

---

## 1. 学科透镜特征

- **研究单元**: 分类单元 (Taxon / Species / Subspecies)、种群 (Population)、分子标记 (Microsatellites / SNPs / Genomes) 或生态位生境；
- **核心风险**: 野外抽样偏倚 (Sampling Bias)、伪重复 (Pseudoreplication)、环境混杂因素、非损伤取样的低浓度降解 DNA 等位基因丢失 (Allelic Dropout)；
- **预印本态度**: bioRxiv 预印本在快速演化领域可作为补充，但必须标注 `[PREPRINT]` 提示。

---

## 2. 默认科学标准与参数配置 (Tier 3 Defaults)

- **核心数据库边界**: PubMed, Web of Science, bioRxiv, GBIF, NCBI GenBank
- **文献类型门槛**: 优先经同行评议的生态与演化学报；重要野外监测调查报告视情况作为灰色文献补充
- **数据提取粒度**: 必须提取物种拉丁名、地理坐标/区域、样本量、抽样周期、分子标记类型与多态性参数（如 $H_e$, $H_o$, PIC）
- **实验隔离**: 严禁将野外调查（In situ field observation）与受控实验室验证（Ex situ lab experiment）混淆提取

---

## 3. 推荐项生成偏好 (Recommendation Tendency)

- **地理与分类范畴**: 明确限定目标物种与地理种群边界，避免跨物种盲目类比 `[高置信度]`；
- **重复判定**: 要求分子实验至少达到多重 PCR 重复检验标准，野外样带具备足够空间独立性 `[高置信度]`；
- **争议合成**: 关注环境梯度（如海拔、纬度、破碎化程度）对生态学结论的调节效应（Moderator Effect）。

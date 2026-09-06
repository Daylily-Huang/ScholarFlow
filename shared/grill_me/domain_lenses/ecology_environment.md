# Domain Lens: Ecology & Environmental Sciences (生态与环境科学)

> **Lens Code**: `ecology_environment`  
> **Applicability**: Ecology, wildlife biology, conservation genetics, biodiversity assessment, environmental science

---

## 1. 学科透镜特征与高危维度

- **核心实体 (Target Entity)**: 物种 (Species)、群落 (Community)、空间种群 (Population)、生态系统 (Ecosystem)；
- **最小上下文隔离单元 (Context Unit)**: 采样样点 (Site / Station)、野外样线 (Transect)、独立生境斑块 (Habitat Patch)、取样季节 (Season)；
- **核心风险与混杂偏倚**:
  - 空间自相关 (Spatial Autocorrelation) 与伪重复 (Pseudoreplication)；
  - 探测概率异质性 (Detection Probability Heterogeneity)；
  - 非损伤性遗存 DNA 的降解偏倚与等位基因脱落 (Allelic Dropout)；
  - 样线/相机陷阱铺设偏差与边缘效应。

---

## 2. 默认科学标准与参数配置

- **数据源边界**: Web of Science, PubMed, bioRxiv, GBIF, IUCN Red List
- **关键提取字段**: 物种学名、空间坐标、样方尺寸/样带长度、探测模型、估算密度 (个/km²)、置信区间
- **可比性边界检查**: 必须核查海拔梯度、植被类型与调查季节，不同季节或破碎化生境下的密度估算严禁直接粗放合并

---

## 3. 证据加权与争议判定偏好

- 优先采纳进行了探测概率校正（如 SECR / Occupancy models）的实证研究；
- 关注环境梯度对物种响应的调节效应（Moderator Effects）。

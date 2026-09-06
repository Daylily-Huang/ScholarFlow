# Domain Lens: Chemistry & Materials Science (化学与材料科学)

> **Lens Code**: `chemistry_materials`  
> **Applicability**: Materials Science, Solid-state Chemistry, Nanotechnology, Energy Materials (Batteries/Solar), Polymer Chemistry

---

## 1. 学科透镜特征与高危维度

- **核心实体 (Target Entity)**: 材料体系 (Material System)、化学计量比 (Stoichiometry)、晶体结构 (Crystal Phase)、活性位点 (Active Site)；
- **最小上下文隔离单元 (Context Unit)**: 制备批次 (Batch)、合成条件 (Temperature/Pressure/Solvent)、退火气氛 (Annealing Atmosphere)、测试工况 (Testing Condition)；
- **核心风险与混杂偏倚**:
  - 批次间合成重现性波动 (Batch-to-batch variation)；
  - 气氛/湿度未受控造成的界面假象 (Artifacts from ambient moisture/air exposure)；
  - 表征分辨率不足导致的相结构误判 (Phase misassignment from low-res XRD)；
  - 循环测试工况不一致（如充放电倍率、温度窗口）。

---

## 2. 默认科学标准与参数配置

- **数据源边界**: ACS, RSC, Elsevier ScienceDirect, Wiley, Springer, arXiv (cond-mat)
- **关键提取字段**: 材料组分/分子式、前驱体、合成温度 (°C)、保持时间 (h)、表征方法 (XRD/TEM/XPS/NMR)、性能指标（如光电转换效率 PCE、比容量 mAh/g、降解半衰期 $T_{80}$）
- **可比性边界检查**: 必须核查测试环境（手套箱惰性气体 vs 空气环境），不同测量工况下的稳定性指标严禁直接粗放并列

---

## 3. 推荐项生成偏好

- 结构判定强制要求至少两种互补表征手段印证；
- 性能指标必须与测试温度、载荷与老化标准并列记录。

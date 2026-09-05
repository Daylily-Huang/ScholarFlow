# Domain Lens: Physical Sciences & Chemistry (物理与化学材料科学)

> **Lens Code**: `physical_sciences`  
> **Applicability**: Physics, Chemistry, Materials Science, Chemical Engineering, Earth Sciences

---

## 1. 学科透镜特征

- **三足鼎立**: 理论推演 (Theoretical Modeling)、精密实验测量 (Experimental Measurement)、数值计算模拟 (Numerical Simulation / DFT / MD)；
- **核心要素**: 材料组分/化学式、制备合成条件 (Temperature, Pressure, Solvent)、表征手段 (XRD, TEM, NMR, XPS)、仪器测量极限与不确定度误差棒 (Error Bars)；
- **核心风险**: 假象信号 (Artifacts)、测量精度标定漂移、DFT 泛函选取偏差。

---

## 2. 默认科学标准与参数配置 (Tier 3 Defaults)

- **核心数据库边界**: APS, ACS, RSC, Elsevier ScienceDirect, arXiv (quant-ph, cond-mat)
- **文献类型门槛**: 同行评审专业期刊（注重支持信息 SI / Supporting Information 完备性）
- **数据提取粒度**: 化学结构/材料代码、反应温度/压力条件、产率/转化率、物理性质数值（带误差 $\pm \sigma$）
- **实验隔离**: 纯理论第一性原理计算与实验实测数据必须严格隔离列出

---

## 3. 推荐项生成偏好 (Recommendation Tendency)

- **表征交叉印证**: 要求材料结构认定必须有两种以上互补表征手段印证 `[高置信度]`；
- **条件边界标定**: 明确标定制备与测试的环境温度/气氛条件，拒绝无环境参数的孤立数值 `[高置信度]`；
- **争议判定**: 关注晶体相变温度或催化活性位点判定中的竞争模型。

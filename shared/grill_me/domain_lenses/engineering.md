# Domain Lens: Engineering & Applied Technologies (工程与应用技术)

> **Lens Code**: `engineering`  
> **Applicability**: Mechanical Engineering, Electrical/Electronic Engineering, Civil/Structural Engineering, Robotics, Control Systems

---

## 1. 学科透镜特征与高危维度

- **核心实体 (Target Entity)**: 工程构件 (Component)、控制系统 (Control System)、结构拓扑 (Structure)、工艺流程 (Process Flow)；
- **最小上下文隔离单元 (Context Unit)**: 实验台架 (Test Bench)、仿真工况 (Simulation Scenario / Load Case)、传感器测点 (Sensor Channel)、原型批次 (Prototype Iteration)；
- **核心风险与混杂偏倚**:
  - 边界条件与环境振动/热漂移噪声 (Thermal drift / Environmental vibration)；
  - 仿真简化假设与物理现实不匹配 (Simulation idealization gap)；
  - 尺度缩放效应 (Scale Effect / Reynolds number mismatch)；
  - 传感器测量带宽与校准漂移。

---

## 2. 默认科学标准与参数配置

- **数据源边界**: IEEE Xplore, ASME, ASCE, AIAA, ScienceDirect, Engineering Village
- **关键提取字段**: 原型规格尺寸、材质参数、载荷条件、工作频率/转速、效率/阻尼比/寿命/误差指标
- **可比性边界检查**: 必须核查工况标准（如 ISO/ASTM 测试规范），不同载荷工况下的评测结果不可直接等同

---

## 3. 推荐项生成偏好

- 仿真结论优先采纳具备实体物理试验台架对照验证的研究；
- 明确区分实验室原型（TRL 3-4）与工程化应用（TRL 6+）。

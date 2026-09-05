# Domain Lens: Computer Science & AI (计算机科学与人工智能)

> **Lens Code**: `computer_science`  
> **Applicability**: Artificial Intelligence, Machine Learning, Systems, Software Engineering, Theory

---

## 1. 学科透镜特征

- **发表文化**: 顶级顶会（Top-tier Conferences，如 NeurIPS, ICML, CVPR, ACL, SOSP, SIGCOMM）长文具备最高权威性；
- **预印本普遍性**: arXiv 预印本占据关键前沿位置，但存在大量未经复现或消融不充分的宣称 (Overclaiming)；
- **核心关注**: 基准数据集 (Benchmark Datasets)、开源代码可复现性 (Code Availability)、硬件算力预算、严密消融实验 (Ablation Studies)。

---

## 2. 默认科学标准与参数配置 (Tier 3 Defaults)

- **核心数据库边界**: arXiv, IEEE Xplore, ACM Digital Library, DBLP, Papers With Code
- **文献类型门槛**: CCF-A/B 顶会长文 + 知名预印本（附带开源官方仓库）；纯理论证明需包含完备附录
- **数据提取粒度**: 模型架构名称、训练集/测试集基准、核心定量指标（Acc, F1, BLEU, Latency, FLOPs）、可比 Baseline 版本
- **争议判定**: 关注在同等算力/同等测试基准下是否存在过拟合、数据泄露（Data Contamination）或微调偏差

---

## 3. 推荐项生成偏好 (Recommendation Tendency)

- **基准可比性**: 强制要求对比项必须基于同一官方测试集与评测脚本 `[高置信度]`；
- **代码开源约束**: 优先提取具备公开复现代码的 SOTA 结论 `[中置信度]`；
- **流派与演进**: 梳理架构变迁脉络（如 RNN -> Transformer -> SSM/Mamba）。

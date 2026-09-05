# Domain Lens: Generic / Cross-Disciplinary (通用与交叉学科)

> **Lens Code**: `generic`  
> **Status**: Production Standard Default

---

## 1. 学科特性与透镜定位

适用于尚未明确指定特定自然科学或人文社科学科归属的综合性文献调研、新兴交叉学科研究或宏观科技情报分析。

---

## 2. 默认科学标准与参数配置 (Tier 3 Defaults)

- **语言范围 (Language Scope)**: 英文 + 中文 (核心国际期刊与权威中文核心)
- **文献类型 (Document Types)**: 同行评审期刊文章 (Peer-reviewed Journal Articles) + 权威学术会议长文 (Conference Full Papers)
- **检索深度 (Search Depth)**: 2 层引用拓扑深搜 (Direct references + 1-hop seed expansion)
- **上下文隔离 (Context Isolation)**: 以文章内的独立研究/实验单元 (Individual Experiment / Study Section) 为隔离边界
- **争议判定灵敏度 (Controversy Sensitivity)**: 严格判定，要求核心结论相反或定量效应量方向互斥

---

## 3. 推荐项生成偏好 (Recommendation Tendency)

- 在证据可信度与覆盖面冲突时，优先推荐**高可信度 (保守防伪)** 策略；
- 默认建议过滤无同行评议的非正式博文、商业白皮书或未经核实的演讲速记；
- 默认开启表格与附录优先挖掘（Table/Supplementary priority）。

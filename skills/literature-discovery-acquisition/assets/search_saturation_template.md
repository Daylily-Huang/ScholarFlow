# 检索饱和度轮次跟踪表模板 (Search Saturation Tracking Template)

## 一、轮次收敛数据表 (Convergence by Rounds)

| 轮次 ID | 阶段操作与数据来源 (Stage & Method) | 原始检索数 (Raw Retrieved) | 四级去重后新增 (New Deduped) | 初筛有效数 (Included + Uncertain) | 有效边际贡献率 (Marginal Yield %) | 累计纳入文献数 (Cumulative Valid) |
|:---:|---|:---:|:---:|:---:|:---:|:---:|
| **Round 1** | 核心与扩展检索式 (Q01–Q02) | [N1] | [D1] | [V1] | 100% (基线) | [V1] |
| **Round 2** | 方法学与分类群扩展检索式 (Q03–Q04) | [N2] | [D2] | [V2] | [V2/V1 * 100]% | [V1 + V2] |
| **Round 3** | 核心种子文献反向引文追溯 (Backward Chasing) | [N3] | [D3] | [V3] | [V3/V1 * 100]% | [V1 + V2 + V3] |
| **Round 4** | 核心种子文献正向施引追踪 (Forward Chasing) | [N4] | [D4] | [V4] | [V4/V1 * 100]% | [V1..+ V4] |
| **Round 5** | 核心作者与高频相似论文网络 (Author/Similar) | [N5] | [D5] | [V5] | [V5/V1 * 100]% | [V1..+ V5] |

---

## 二、收敛判定与停止论据 (Convergence Rationale)

- **最新轮次有效新增量**：`[V_latest]` 篇（是否 $\le 2$ 篇）
- **最新轮次边际收益率**：`[Yield %]`（是否 $< 5\%$）
- **引文网络闭环重叠度**：`[Overlap %]`（引文追踪中已存在文献占比，是否 $> 80\%$）
- **收敛状态结论**：
  > “基于上述量化数据，当前检索路径的边际产出已趋于平缓，检索流程达到收敛饱和条件，可终止自动化扩展。”

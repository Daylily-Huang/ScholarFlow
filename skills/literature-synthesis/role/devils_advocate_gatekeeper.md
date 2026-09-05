# 红队辩驳与终审把关组契约 (Devil's Advocate & Quality Gatekeeper Contract)

## 一、组内职能整合定义
本组是整个综合分析流程中最严酷的“红队防御与质量总检”：
- **Role 8: Devil's Advocate（反方挑刺专员）**：站在主流结论的绝对对立面，专门挑刺、寻找被忽略的负结果反例、抓因果倒置、排查学术重复发表；
- **Role 9: Quality Gatekeeper（终审把关人）**：依据十项硬性科研审查准则，对全部分析产物行使**独立一票否决权**。

---

## 二、Devil's Advocate 必须发起的五大“红队攻击”

在综合结论最终定稿前，反方专员必须在报告中发起五项针对性挑刺：

1. **反例与零假说搜查 (Hunt for Negative / Null Evidence)**：
   - 质问：是否有研究明确未检测出显著效应，却被正文轻描淡写地略过了？
   - 铁律：必须主动向读者呈现那些“未能复现主流结论”的阴性结果。
2. **相关性与因果性伪装审查 (Correlation ≠ Causation Audit)**：
   - 质问：文献中只是观测到“修路与种群数量下降在时间上伴随出现”，报告是否将其擅自升格为“修路直接导致了种群灭绝”？
3. **同质数据集伪独立排查 (Shared-Dataset Pseudoreplication)**：
   - 质问：引用的 5 篇高相关文献，是否实际上源于同一个科研团队在 2012–2014 年间于同一片野外实验林采集的同一批粪便数据？
   - 铁律：若是同一批样本的多次衍生发表，只能记为 1 个独立证据源！
4. **发表偏倚风险提示 (Publication Bias / File-Drawer Risk)**：
   - 质问：当前一致的正效应结论，是否源于学术界倾向于不发表“未发现基因阻隔”的阴性研究？
5. **外推边界攻击 (Over-Generalization Challenge)**：
   - 质问：基于人工湖孤岛碎片化生境得到的结论，凭什么能推广至大陆连续大山系？

---

## 三、终审把关人 10 项形式化审查清单 (10-Point Quality Gate)

最终报告提交前，Gatekeeper 必须逐一机械式核查以下 10 项：

| 审查维度 | 审查标准 | 违规直接判定 |
|---|---|---|
| **1. Evidence Grounding** | 每一个主要结论与归纳，是否能追溯到具体论文原句与页码？ | 无锚点直接删除 |
| **2. Counterevidence Coverage** | 是否公平呈现了反对意见、阴性结果与异常点？ | 遗漏反证驳回重审 |
| **3. Conflict Classification** | 争议是否准确归入了 Type A~I？是否把表面假争议当成学术冲突？ | 归类错误打回更正 |
| **4. Methodological Divergence** | 是否深入排查了样本量、标记、尺度与模型假设等方法学根源？ | 仅列不同而无归因驳回 |
| **5. School Validity** | 是否严禁了虚构学派？是否区分了公认学派与分析分组？ | 虚构学派直接 REJECT |
| **6. Consensus Calibration** | 共识评级是否过高？是否杜绝了“篇数民主投票”？ | 过度宣称共识直接降级 |
| **7. Causality Rigor** | 是否严格区分了观察相关性与因果证明？ | 伪因果强制修正 |
| **8. Generalization Boundary** | 是否为每一个共识明确标记了时空与物种适用边界？ | 泛化结论强制补边界 |
| **9. Search Completeness** | 是否识别出文献断代或方法断层？是否生成了 `SEARCH GAP`？ | 明显缺文献发出警告 |
| **10. Extraction Completeness**| 关键文献是否缺少必要参数？是否生成了 `EXTRACTION GAP`？ | 关键参数缺失发出警告 |

---

## 四、终审决议书签署模板 (Sign-off Template)

```markdown
---
### ⚖️ 综合分析终审质量决议 (Quality Gate Verdict)
- **分析主题**：[Research Question]
- **纳入文献总数**：[N] 篇 (独立数据集 [M] 个)
- **争议识别数**：[X] 项 (Type A: [x1], Type B: [x2], Type I: [x3])
- **共识判定**：[Y] 项 (全部已绑定适用边界条件)
- **红队进攻对抗记录**：[已排除 2 篇共享数据伪重复 / 已驳回 1 项因果倒置推论]
- **上游任务派发**：
  - SEARCH GAP: [已生成 1 项补检请求 / 无]
  - EXTRACTION GAP: [已生成 1 项补抽请求 / 无]
- **十项硬指标审查结论**：10/10 项审查通过
- **终审裁决**：
  - [x] **PASS (放行)**：分析严密，争议深刻，反例充分，共识严谨有边界。
  - [ ] **CONDITIONAL PASS (附带警告放行)**：存在轻微文献断层，需注意时效性。
  - [ ] **REJECT (驳回重修)**：存在伪造学派或文献篇数投票违规。
- **审查员签署**：Quality Gatekeeper & Devil's Advocate
---
```

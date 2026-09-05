# 既有学术结论争议反查审计实战案例 (Audit Mode Verification Case)

## 一、案例背景与送审问题

- **待查论文**：`2015_Chen_Muntjac_Population_Genetics.pdf`
- **引发争议的综述陈述**：
  在某篇 2020 年发表的中文综述论文中，作者引用了陈等（2015）的数据并写道：
  > “陈等 (2015) 利用 12 个微卫星位点对千岛湖黑麂粪便样品进行了个体识别，PCR 体系为 25 μL，未添加任何 BSA 稳定剂，最终成功识别出 42 个人体，种群估算为 65 只。”
- **用户的核查指令**：
  > “请帮我核实这段综述里提到的陈等 (2015) 细节是否属实？特别是 25 μL PCR、未添加 BSA 和 12 个位点，帮我逐一到陈等的 PDF 原文中反查对账！”

---

## 二、Stage 0: 启动 Audit Mode 并原子化拆解主张

针对用户的复合输入，`evidence_auditor` 立即执行**原子化主张拆解 (Atomic Decomposition)**：
- **Claim 1 (位点数量)**：陈等使用了 12 个微卫星位点进行个体识别；
- **Claim 2 (PCR 体系)**：微卫星 PCR 反应体积为 25 μL；
- **Claim 3 (BSA 添加)**：PCR 体系中明确未添加任何 BSA 稳定剂；
- **Claim 4 (个体识别数)**：最终成功识别出 42 个黑麂个体；
- **Claim 5 (种群估算值)**：种群估算为 65 只。

---

## 三、全文反向寻证与对账核查 (Verification Trail)

调用 `scripts/audit_claims.py` 辅助检索，并在全文中深入 Methods 与 Tables 逐字比对：

1. **核查 Claim 1 (12 个位点)**：
   - 检索关键词 `12 microsatellite` / `Table 1`；
   - 发现 Methods 2.3 明确记录：作者实际初筛了 **15 个位点**（`“A panel of 15 microsatellite loci was initially amplified...”`），其中 12 个位点表现为多态性用于个体识别。
   - **裁决**：`PARTIALLY_SUPPORTED`（实为 15 筛 12，综述表述不完整）。

2. **核查 Claim 2 (25 μL PCR)**：
   - 检索 `25 μL` 与 `reaction volume`；
   - 发现：Methods 2.2 中记载物种鉴定的 Cytb PCR 体系为 25 μL；但在 Methods 2.3 中，微卫星分型 PCR 体系明确记录为 **10 μL**（`“Multiplex STR PCR was carried out in a 10 μL volume...”`）。
   - **裁决**：`CONTRADICTORY`（⚠️ **严重事实错误！** 综述作者犯了典型的多实验交叉污染错误，误将物种鉴定的 25 μL 嫁接给微卫星分型）。

3. **核查 Claim 3 (未添加 BSA)**：
   - 全文深度检索 `BSA`, `bovine serum albumin`，无任何文字记录。
   - **裁决**：`UNSUPPORTED`（❌ **查无实据！** 全文根本没有报告 BSA，综述作者擅自将“未报告 (Not Reported)”脑补成了“未添加 (Without BSA)”）。

4. **核查 Claim 4 (识别出 42 个人体)**：
   - 检索 `42 individuals`；
   - 发现：Results 3.2 明确写道：`“After multi-tube consensus matching, 42 distinct individuals were identified from 88 valid fecal genotypes.”`
   - **裁决**：`SUPPORTED`（完全属实吻合）。

5. **核查 Claim 5 (种群估算为 65 只)**：
   - 检索 `65` 与 `Capwire`；
   - 发现：Results 3.4 中，使用 Capwire 软件的 TIRM 模型估算值为 **68 只** (95% CI: 52–89)，而 65 是另一个两阶段模型的点估计。
   - **裁决**：`PARTIALLY_SUPPORTED`（65 只是模型之一，作者推荐的 TIRM 实际为主体 68 只）。

---

## 四、最终交付物：学术反查审计决议书

```markdown
### 📋 陈等 (2015) 综述引用真伪反查审计报告 (Audit Report)

| Claim # | Atomic Claim Statement (综述主张) | Audit Verdict (裁决) | Evidence Level | Verbatim Original Quote (陈等 2015 原文原句) | Source Location | Discrepancy & Verification Notes (对账说明) |
|:---:|---|:---:|:---:|---|---|---|
| **C1** | 使用了 12 个微卫星位点 | **PARTIALLY_SUPPORTED** | E1 | “...initially screened 15 loci; 12 polymorphic loci were selected for final typing...” | Page 3, Section 2.3 | 原文初筛 15 个位点，最终多态入选 12 个，综述略去筛选过程 |
| **C2** | 微卫星PCR体系为 25 μL | **CONTRADICTORY** | E1 | “Multiplex STR PCR was carried out in a 10 μL volume containing...” | Page 4, Section 2.4 | ⚠️ **存在严重事实颠倒！** 原文微卫星实为 10 μL；综述作者错把物种鉴定的 25 μL 混入 |
| **C3** | 未添加任何 BSA 稳定剂 | **UNSUPPORTED** | E4 (NR) | — | Full text scanned | ❌ **查无实据！** 原文通篇未提 BSA，犯了“将未报告当成未使用”的严重推断错误 |
| **C4** | 成功识别出 42 个黑麂个体 | **SUPPORTED** | E1 | “...42 distinct individuals were identified from 88 valid fecal genotypes.” | Page 5, Section 3.2 | 证实完全属实，数据严格对应 |
| **C5** | 种群估算为 65 只 | **PARTIALLY_SUPPORTED** | E1 | “TIRM model estimated N = 68 (95% CI: 52–89), while ECM model yielded N = 65...” | Page 6, Table 4 | 65 仅为次优模型 ECM 估算值，主流 TIRM 实际为 68 只 |

---

### ⚖️ 审计员结论与建议 (Auditor Takeaway)
1. **核实结论**：送审的综述陈述中，仅 1 项（C4）完全客观属实，1 项（C2）存在重大实验参数颠倒错误，1 项（C3）存在无中生有的过度推断，2 项（C1, C5）缺乏精度；
2. **论文撰写纠偏建议**：在您自己的学位论文或学术报告中，引用陈等 (2015) 时必须**修正微卫星 PCR 体系为 10 μL**，种群估算应表述为 `68只 (TIRM)`，切勿直接照抄该错误综述！
```

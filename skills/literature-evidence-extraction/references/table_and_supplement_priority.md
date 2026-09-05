# 表格与补充材料优先挖掘及 OCR 防护规程 (Table Priority & OCR Protocol)

## 一、表格优先原则 (Table-First Principle)

在实验科学与生态学文献中，**正文往往是叙述性的概括，而表格（Tables）和补充材料（Supplementary Material）才是高精度事实的真正汇聚地**。

### 必须优先检索表格与补充材料的核心字段清单：
1. **引物信息**：引物名称 (Locus/Primer)、5'→3' 碱基序列、荧光标记染料 (FAM/HEX/NED/ROX)；
2. **扩增参数**：位点退火温度 ($T_a$)、循环数、Mg2+ 浓度；
3. **等位基因与多态性**：等位基因大小范围 (Allele Size Range)、等位基因数 ($N_a$)、期望杂合度 ($H_E$)、观测杂合度 ($H_O$)、多态信息含量 ($PIC$)；
4. **样本与采样点明细**：每个样带/地点的样本编号、经纬度、提取浓度；
5. **数据库注册号**：GenBank Accession Number、Dryad DOI、PRJNA 编号。

> **铁律**：凡涉及上述 5 类字段，**严禁仅凭正文中的一句话就结案**，必须主动检索全文中的 `Table 1`, `Table 2` 以及 `Supplementary Tables / Appendix`。如果正文叙述与表格冲突，以表格为准或标记 `CONTRADICTORY`。

---

## 二、表格抽取的三大经典暗坑与规避手段

### 陷阱 1：多栏混排与行列错位 (Column Offset)
- **现象**：PDF 转换为文本时，表格中的“正向引物”常与“反向引物”错行，或“荧光染料”串入“退火温度”列。
- **对策**：
  - 抽取专员必须通过表头（Headers）进行严格的网格坐标核对（Row Index × Column Index）；
  - 摘抄 Verbatim Quote 时，必须将整行相关单元格同时提取（如：`Row "STR-04": F: 5'-...-3' | R: 5'-...-3' | Dye: FAM | Ta: 55°C`）。

---

### 陷阱 2：表注与星号标记遗漏 (Table Footnotes)
- **现象**：表格单元格数值旁带有标记（如 `55°C*`），而表注 `* Multiplex PCR annealing temperature was lowered by 2°C` 被模型忽略。
- **对策**：检查表格时，**必须强制阅读表格底部的 Table Footnotes**，表注中的限定条件必须并入 Notes 记录。

---

### 陷阱 3：补充材料（Supplement / Appendix）信息未穿透
- **现象**：正文写 `“Detailed PCR conditions for each locus are given in Table S1”`，模型直接输出 `NR`。
- **对策**：
  - 若用户提供了补充材料，必须穿透至补充材料提取；
  - 若补充材料不可得，必须准确输出：
    - `Value = NR (详见未提供之 Table S1)`
    - `Level = E4 (NR)`
    - `Notes = 正文指引补充材料 Table S1，当前文档包未包含附录文件`。

---

## 三、高危字段 OCR 噪声零容忍防护红线 (Zero-Tolerance OCR Policy)

学术论文（尤其是 2015 年前发表的老文献或扫描版 PDF）普遍存在 OCR 识别噪声。以下 5 类字段被定义为**极度高危字段 (Extreme High-Risk Fields)**：

| 高危字段类型 | 典型 OCR 识别畸变与乱码 | 严厉禁止的行为 (Violations) | 唯一合法合规操作 (Mandatory Actions) |
|---|---|---|---|
| **引物碱基序列** | `AGCTA...` 混入 `1`, `l`, `0`, `O` 或 `?` | ❌ 擅自根据常识修复碱基序列 | 强制标记为 `Status = OCR_UNCERTAIN`，提醒人工复核原版 PDF |
| **微升体积单位** | `μL` 错识别为 `uL`, `?L`, `mL` 或直接丢失 | ❌ 猜想是微升还是毫升 | 原文摘抄 `?L`，标记 `OCR_UNCERTAIN` 并提示单位异常 |
| **退火与变性温度** | `55°C` 错识别为 `550C`, `55·C`, `SS°C` | ❌ 自行替换为 55°C | 标记 `OCR_UNCERTAIN`，在 Notes 中指明字符漂移 |
| **试剂浓度与比例** | `0.2 mg/mL` 误识别为 `0·2` 或小数点丢失为 `2` | ❌ 擅自补充小数点 | 标记 `OCR_UNCERTAIN`，警示可能存在数量级错误 |
| **误差与置信区间** | `±` 符号错识别为 `+`, `-`, `=`, `6` | ❌ 脑补为正负号 | 标记 `OCR_UNCERTAIN`，保留原始识别字符 |

> **红线宣言**：
> **宁可诚实地报告“此处扫描存在杂音需人工核对”，也绝不生成一个看似完美的伪造引物或错误温度！**

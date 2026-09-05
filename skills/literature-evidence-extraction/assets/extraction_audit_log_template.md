# 抽取审计轨迹日志模板 (Extraction Audit Log Template)

## 任务基本信息
- **任务编号 (Task ID)**：`EXT-[YYYYMMDD]-[UUID]`
- **目标文献**：[Paper Basename]
- **执行时间**：[YYYY-MM-DD HH:MM:SS]
- **执行专员**：Extraction Lead
- **建模助手**：Context Modeler
- **质检核验员**：Evidence Auditor

---

## 阶段轨迹流转记录 (Execution Trail)

### 1. Stage 0: 协议基线锁定记录
- [x] 全文有效性核验：PDF 就绪 (通过 `%PDF-` 二进制及可提取文本核验)
- [x] 模式选定：Extract Mode / Audit Mode / Batch-Matrix
- [x] Schema 协商状态：[User-specified / Dynamic-generated]
- [x] Assay 上下文标记：[单 Assay / 多 Assay: Assay-01, Assay-02]

### 2. Phase A: 事实定位与候选提取记录
- 检索关键词列表：`[kw1, kw2, kw3...]`
- 主表定位记录：`[Table 1: primers, Table 2: diversity]`
- 补充材料检索：`[Supplement checked / Not available]`
- 候选提取字段数：`[Total fields count]`

### 3. Phase B: 证据链核验与降级处理记录
- 初始 E1 数量：`[Count]`
- 降级为 E2 (DERIVED) 记录：
  - 字段 `[Field Name]`：原因 `[推导公式补充]`
- 降级为 E3 (REFERENCED) 记录：
  - 字段 `[Field Name]`：原因 `[原文引用外部文献，当前值记为NR]`
- 确认 E4 (NR) 记录：
  - 字段 `[Field Name]`：原因 `[全文扫描无匹配，严禁脑补]`
- 冲突标记 (CONTRADICTORY) 记录：
  - 字段 `[Field Name]`：位置 `[Text Page X vs Table Y]`

### 4. 终审放行签批
- **14 项质检 Checklist 状态**：`14/14 PASS`
- **最终裁决**：`PASS (放行并落盘 JSON)`
- **生成实体文件**：`<Paper_Slug>_evidence.json`

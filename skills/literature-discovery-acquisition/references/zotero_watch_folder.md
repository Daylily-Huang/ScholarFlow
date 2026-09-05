# Zotero 监听目录与 CSL-JSON 文献库生态沉淀指南 (Zotero Watch Folder & CSL-JSON Guide)

## 一、为什么选择 CSL-JSON 与监听目录 (Watch Folder)？

在传统工作流中，研究者需要手动将 PDF 拖入 Zotero，或打开 Zotero 点击“文件 -> 导入”并选择 BibTeX，再手动关联 PDF 附件，流程繁琐且容易丢失元数据。

**双层 CSL-JSON 与 Zotero 监听目录机制**：
- **CSL-JSON (Citation Style Language JSON)** 是 Zotero、Pandoc 与现代文献管理生态的原生标准交换格式，相比 BibTeX 能更精准地表达多作者姓名、学位论文培养单位、DOI 与期刊卷期。
- **Watch Folder（监听目录）**：Zotero 能够实时监控指定本地文件夹，只要下载脚本将 PDF 与元数据写入该目录，Zotero 即可在后台零摩擦秒级自动入库。

---

## 二、双层 CSL-JSON 产物架构规范

在下载流程（Stage 8）中，系统在输出目录（默认 `papers/downloads/`）同时生成两层元数据：

```text
papers/downloads/
├── 2024_Wang_Targeting_KRAS_G12D.pdf          # 经 %PDF- 魔数校验的合法全文
├── 2024_Wang_Targeting_KRAS_G12D.csl.json     # [单篇配对] 该文献独立的 CSL-JSON
├── 2012_Zheng_Estimation_black_muntjac.pdf    # 另一篇已下载全文
├── 2012_Zheng_Estimation_black_muntjac.csl.json# [单篇配对] 独立 CSL-JSON
├── zotero_import.csl.json                     # [总汇文件] 包含全部文献对象的全局 CSL-JSON
└── literature_pool.bib                        # [通用备选] 标准 BibTeX 格式
```

---

## 三、单篇与总汇 CSL-JSON 数据格式规范

每一份 CSL-JSON 对象严格遵循 CSL 1.0.2 规范：

```json
{
  "id": "REC001",
  "type": "article-journal",
  "title": "Targeting KRAS(G12D) with MRTX1133 in pancreatic ductal adenocarcinoma",
  "author": [
    { "family": "Wang", "given": "X." },
    { "family": "Allen", "given": "S." }
  ],
  "issued": {
    "date-parts": [[2024]]
  },
  "container-title": "Cancer Discovery",
  "DOI": "10.1158/2159-8290.CD-22-0415",
  "URL": "https://doi.org/10.1158/2159-8290.CD-22-0415",
  "abstract": "...",
  "keyword": "KRAS G12D, MRTX1133, acquired resistance",
  "file": "2024_Wang_Targeting_KRAS_G12D.pdf"
}
```

*若为学位论文 (Thesis)*：
- `"type": "thesis"`
- `"publisher": "华东师范大学"`（学位授予单位）
- `"genre": "博士学位论文"`（学位级别）

---

## 四、Zotero 自动无感导入配置三步走 (Zotero Setup)

用户仅需在 Zotero 中配置一次，即可享受完全自动化的文献与 PDF 沉淀：

### 方式 1：利用 Zotero 7 原生监听 / 拖拽一键入库 (最推荐)
1. 打开 Zotero 客户端；
2. 直接将 `papers/downloads/zotero_import.csl.json` 拖入 Zotero 窗口的对应分类收藏夹中；
3. Zotero 将瞬间解析所有文献元数据，并根据 `file` 字段自动将同级目录下的对应 PDF 文件挂载为附件。

### 方式 2：配置 Zotero 自动抓取目录 (Zotero Watch Folder / ZotFile)
1. 打开 Zotero 菜单：`编辑` -> `首选项` -> `高级` -> `文件与文件夹`；
2. 在“链接附件的基本目录 (Linked Attachment Base Directory)”中，选择本项目的 `papers/downloads/` 目录；
3. 若安装了自动监控插件（如 ZotFile 或 Zotero Auto-Import），直接将监听源文件夹设置为 `papers/downloads/`，每次运行检索下载后，Zotero 将在后台静默自动收录新入库的 PDF 与 CSL-JSON。

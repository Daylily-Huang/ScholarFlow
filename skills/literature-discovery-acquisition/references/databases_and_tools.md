# Stage 3: 多数据源检索与工具调度规范 (Multi-Source Retrieval & Tool Strategy)

## 一、分层混合检索架构 (Tiered Hybrid Architecture)

为了实现高召回率（Recall）并保证检索过程的完全真实与透明，Skill 采用**三层数据源调度架构**：

```mermaid
flowchart TD
    A[用户确认的检索式集合 Q01-Q06] --> B[第一层：环境学术 API 工具]
    A --> C[第二层：Web 学术广域探测与 URL 抓取]
    A --> D[第三层：商业/受限库人工补检生成]
    
    B --> B1[OpenAlex]
    B --> B2[PubMed / MEDLINE]
    B --> B3[Europe PMC]
    B --> B4[arXiv / bioRxiv]
    
    C --> C1[Google Scholar 检索]
    C --> C2[Semantic Scholar / Crossref]
    C --> C3[出版商官方落地页解析]
    
    D --> D1[Web of Science 核心合集]
    D --> D2[Scopus]
    D --> D3[中国知网 CNKI]
    D --> D4[万方数据 / 学位论文库]
```

---

## 二、学术工具与 API 调度优先级

### 1. 第一层：原生学术 API 工具（自动化高置信度）
当环境中具备对应工具或通用 API 可用时，必须按学科属性优先调度：

| 工具 / API | 覆盖学科与特点 | 优势与返回字段 | 调度建议 |
|---|---|---|---|
| **OpenAlex** | 全学科（2.5 亿+文献，覆盖跨学科、交叉学科） | 返回精准 DOI、Title、Authors、Year、Journal、Abstract (Inverted Index 重建)、Citation Count | **通用首选**，任何学科均应第一批次调用 |
| **PubMed / MEDLINE** | 生命科学、生物医学、动物遗传学 | 官方权威题录、MeSH 词标引精准、PMID 绑定 | **生物与医学首选**，遗传标记与分子生态学必查 |
| **Europe PMC** | 生物学、生物化学、生命科学开放获取 | 涵盖 PubMed 题录 + 欧洲生物学资源，支持全文直接扫描与引文检索 | 配合 PubMed 执行交叉补漏 |
| **bioRxiv / medRxiv** | 生命科学与医学最新预印本 | 获取尚未正式见刊的近 6–12 个月前沿突破 | 适用于探索性前沿主题调研 |
| **Unpaywall** | 全学科（覆盖 2 亿+ DOI 的 OA 状态库） | 返回 `best_oa_location.url_for_pdf` 与各机构知识库绿色 OA 副本（`oa_locations[]`） | **Stage 8 下载必查**；请求须携带 `?email=` 参数；对 OpenAlex 未给出直链的 OA 文献是关键替补 |
| **arXiv** | 计算机、人工智能、定量生物学 (q-bio) | 计算机与物理/数学绝对主力源 | 涉及计算模型、生物信息算法时必查 |

### 2. 第二层：Web 学术广域探测与网页提取
当特定长尾文献或预印本在直接 API 中未命中时，启动网页级学术搜索：
- **Google Scholar / Semantic Scholar 探测**：利用 `search_web` 针对特定复合检索短语进行检索，捕获高引用经典论文；
- **DOI 官方解析与落地页元数据抓取**：通过 `read_url_content` 访问 `https://doi.org/<DOI>` 或出版商官方摘要页，核实准确标题、作者列表与摘要，严格消除幻觉。

### 3. 第三层：商业/受限数据库支持模式与极速摄取 (Three Coverage Modes)
因绝大部分 Agent 环境无法直接绕过商业付费鉴权（Web of Science, Scopus, CNKI, 万方, 维普 VIP, ProQuest），系统正式支持**三种合法可审计的数据源覆盖模式 (Three Coverage Modes)**：

| 模式 | 模式名称 | 执行方式 | 覆盖认定标准 |
|---|---|---|---|
| **Mode A** | `DIRECT_METADATA_SEARCH` | 自动化环境直接访问可用 API 或开放元数据接口执行检索 | 接口返回完整命中且抓取全部题录 |
| **Mode B** | `BROWSER_METADATA_SEARCH` | 浏览器会话处理 JS 动态渲染/Session 登录，读取检索结果列表 | 完整遍历分页至总命中数 |
| **Mode C** | `USER_ASSISTED_EXPORT` | 用户在校园网/机构内执行 ScholarFlow 派生的检索式，导出全部题录文件交由脚本解析 | 导出记录数与检索命中数严格对账一致 |

> [!NOTE]
> **三种模式均属于合格的数据库覆盖路径**。无论哪种模式，只要完整获取了检索式对应的题录，均可在 Ledger A 中标记为 `COMPLETE` 覆盖。

#### 🇨🇳 中文数据库支持画像 (Chinese Database Support Profiles)
1. **中国知网 (CNKI)**：
   - 支持 Refworks 格式题录导入、期刊文献与博硕士学位论文解析；
   - 记录 `reported_total_hits` 并校验分页完整性；
2. **万方数据 (Wanfang)**：
   - 支持 RIS、EndNote 及 CSV 表格题录导入；
   - 保留 `source_databases: ["Wanfang"]` 独立溯源；
3. **维普数据库 (VIP)**：
   - 支持维普自定义字段标签（`【题名】`、`【作者】`、`【机构】`、`【刊名】`、`【年份】`、`【文摘】`、`【关键词】`、`【DOI】`）及标准 Tagged 格式解析；
   - 自动识别期刊论文与博硕士学位论文。

#### 🚀 商业库题录极速摄取流水线 (Ingestion Pipeline)
用户在校园网内检索并批量导出 Refworks/RIS/EndNote/VIP 文件后，调用内置脚本实现免爬虫无缝解析合流：
```bash
# 一键解析并标准化知网/万方/维普/WoS 外部导出文献
python skills/literature-discovery-acquisition/scripts/ingest_external_records.py \
  -i ./user_exports/ \
  -o ./output/external_candidates.json \
  --source auto
```
脚本自动解析题名、作者、年份、摘要、期刊/高校，并执行跨源去重与元数据相互补全（`merge_candidate_records`），保留多库重合证据（`source_databases`），严禁因无全文丢弃题录。


---

## 三、元数据提取字段规范 (Metadata Fields Extraction)

每一篇从 API 或网页检索到的文献，必须以统一数据模型提取并存储以下 14 个核心字段：

```json
{
  "id": "REC001",
  "title": "Normalized Paper Title",
  "authors": ["Author 1", "Author 2"],
  "year": 2024,
  "journal": "Molecular Ecology",
  "doi": "10.1111/mec.12345",
  "pmid": "38123456",
  "url": "https://doi.org/10.1111/mec.12345",
  "abstract": "Full abstract text...",
  "keywords": ["fecal DNA", "microsatellites", "individual identification"],
  "document_type": "Article",
  "source_databases": ["PubMed", "OpenAlex"],
  "query_id": "Q01",
  "metadata_verification_status": "VERIFIED_API"
}
```

- 若缺少 DOI，字段填 `"doi": "NR"`，严禁虚构；
- 若缺少 PMID，字段填 `"pmid": null`；
- 若缺少摘要（如极早期论文），必须标记 `"abstract": "Not available"`。

---

## 四、检索异常与失败降级策略 (Failure Handling & Fallback)

1. **API 超时或频次限制 (Rate Limit / Timeout)**：
   - 自动指数退避重试（1s, 2s, 4s）；
   - 若重试 3 次仍失败，自动降级至 Web 学术搜索或备用镜像，并在检索日志中如实记录降级事件。
2. **检索结果过少 (Zero / Low Hits: < 5 篇)**：
   - 触发『概念放宽机制』：在 Concept Matrix 中启用 Broader Terms（如将种名放宽为属名或科名，将具体试剂放宽为通用方法）；
   - 移除过紧的字段限定（从 `Title-only` 放宽为 `Title/Abstract`）；
   - 检查布尔操作符是否错用了过多的 `AND`，将次要概念由必须限定改为可选项。
3. **检索结果过多 (Information Overload: > 1000 篇)**：
   - **严禁直接暴力截断前 50 条**；
   - 增加必要的方法学或目标变量限定概念（如增加 `AND ("individual identification" OR "genetic tagging")`）；
   - 施加时间窗口限定（如限制近 10 年）或限定同行评议期刊论文类型。

# 全文文献获取台账模板 (Download Ledger Template)

## 一、获取概况统计 (Acquisition Summary)

- **检索课题**：[填写研究主题]
- **初筛合格候选总数**：[N] 篇
- **已成功下载开源全文 (OA / 预印本)**：[N_oa] 篇
- **受限商业数据库付费墙 (Paywalled)**：[N_pay] 篇
- **下载受阻/网络失败**：[N_fail] 篇
- **存储目录**：`papers/downloads/`

---

## 二、详细文献全文获取明细表 (Full-Text Details)

| 记录 ID | 论文标题 (Title) | 第一作者 | 出版年 | 官方 DOI / 标识符 | 获取状态 (Status) | 本地文件名 / 官方访问指引 |
|---|---|---|:---:|---|:---:|---|
| **REC001** | [Paper Title 1] | [Author 1] | [Year] | [10.xxxx/xxxx](https://doi.org/10.xxxx/xxxx) | 🟢 **OA_DOWNLOADED** | `2024_Author_Title_Slug.pdf` |
| **REC002** | [Paper Title 2] | [Author 2] | [Year] | [10.xxxx/xxxx](https://doi.org/10.xxxx/xxxx) | 🟢 **PREPRINT_AVAILABLE** | `2023_Author_Preprint_Slug.pdf` |
| **REC003** | [Paper Title 3] | [Author 3] | [Year] | [10.xxxx/xxxx](https://doi.org/10.xxxx/xxxx) | 🔒 **PAYWALLED** | 商业数据库需订阅，请通过机构/校园网访问 |

---

## 三、商业付费文献 (Paywalled) 人工补全指引

对于上述标记为 🔒 **PAYWALLED** 的文献：
1. 已在表格中提供官方 DOI 超链接，请在已购买数据库授权的机构局域网（校园网/科研所 IP）内点击访问；
2. 若校园网未购买，可复制 DOI 使用中科院文献情报中心、CALIS 或国家科技图书文献中心（NSTL）的馆际互借（Interlibrary Loan）通道；
3. 下载后重命名为规范格式 `<Year>_<FirstAuthor>_<TitleSlug>.pdf` 并放置在 `papers/downloads/` 目录中即可。

# 检索审计日志模板 (Search Audit Log Template)

## 一、检索任务元数据 (Task Metadata)

- **任务名称**：[Task Name]
- **执行时间**：[YYYY-MM-DD HH:mm:ss]
- **执行人 / Agent**：literature-discovery-acquisition Agent
- **检索模式**：[Deep Search / Quick Search]
- **学科领域**：[Discipline]

---

## 二、数据源状态审计 (Data Source Status)

| 数据源名称 (Source) | 访问方式 (API / Web / Manual) | 访问状态 (Success / Rate-Limited / Blocked) | 实际检出文献数 (Hits) | 备注 |
|---|---|---|:---:|---|
| **OpenAlex** | REST API | Success | [Count] | 核心全量题录池 |
| **PubMed** | NCBI E-utilities | Success | [Count] | 医学/遗传学生物权威源 |
| **Europe PMC** | REST API | Success | [Count] | 欧洲生物开放获取库 |
| **arXiv / bioRxiv** | API | Success | [Count] | 预印本补充 |
| **Web / Google Scholar**| Search Web | Success | [Count] | 广域补漏 |
| **CNKI (中国知网)** | Manual Recommended | Blocked / No Direct API | 0 (已提供人工式) | 建议人工登录机构内网补检 |
| **Web of Science** | Manual Recommended | Blocked / No Direct API | 0 (已提供人工式) | 建议人工登录机构内网补检 |

---

## 三、执行检索式记录 (Executed Queries Audit)

| Query ID | 目标数据源 | 执行布尔表达式 (Exact Query String) | 检出数 (Raw Hits) |
|---|---|---|:---:|
| **Q01** | OpenAlex, PubMed | `[Query String 1]` | [Hits 1] |
| **Q02** | OpenAlex, Europe PMC | `[Query String 2]` | [Hits 2] |
| **Q03** | Google Scholar | `[Query String 3]` | [Hits 3] |
| **Q04** | CNKI (人工补检式) | `[Query String 4]` | 待人工回填 |

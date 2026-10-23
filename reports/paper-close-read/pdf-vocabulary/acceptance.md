# 双语 PDF、逐段词汇与白话规范更新验收

日期：2026-10-23。所有 HTML 从 reading-data 经通用构建器生成；未手工补成品。

## 变更

- 首页突出 v1.2.0 独立 Release ZIP；解压复制或包内安装器，不必克隆仓库。
- translations.vocabulary 保存原段实际英文词形和语境中文义，兼容旧资料。10 篇输入共 465 个正文段、1756 项词汇；校验真实出现、重复与字段形状，不冒称自动判断释义正确。
- 专用 A4 中英左右对照 PDF，支持纵横向、白话/逻辑和附录选项，保留原图表、公式、词汇和归属。标准库 CLI 使用隔离 Chrome，先核验排版 DOM，失败保留旧输出。
- 白话首选具体对象按简单规则推演：直觉→关键运作→按需补边界；类比/具体失败场景服务读者卡点，禁止概念解释概念。不把它强制成每段三层、三个动作或固定要点数。跨学科写作示例和内容审读一并更新；Hardy/Carroll 5 个关键段在输入中演示这一写法。
- 修复原图缩放按钮导致导出时丢图、行内 MathML 出现滚动控件的问题。

## 实测

| 范围 | 结果 |
| --- | --- |
| reader 单元回归 | 38 项通过（含词汇真实性、旧输入兼容、转义和失败不覆盖） |
| 技能自检 | 40 项通过 |
| 隔离标准库环境全套 | 1209 项通过，44 项可选依赖测试跳过；CI 严格依赖环境另验 |
| Hardy/Carroll 原交互回归 | 各 40 项，合计 80 项；报告绑定最终 HTML 哈希 |
| 4 篇真实 Chrome 检查 | 词汇、检索后导出全文、打印选项/恢复、旧路线动图、无重复 ID、390px 模拟布局通过 |
| 4 份实际 PDF | Hardy 9 页、Carroll 25 页（含白话逻辑）；Mariana 51 页、Thomsen 41 页（纯对照及词汇）；文字可选择，原图分别保留 1/5 项 |
| 可重建 | 10 篇 generation-manifest 绑定输入、技能树和输出 |

PDF 首页、中间和末页及图表页已渲染目视检查，未见丢字叠字或页面横溢；长段会跨页，重复栏头，按段对照，不声称逐行对齐。交互动图、批注与工具仍在 HTML。390px 为布局模拟，并非真实手机硬件测试。

本机常用 Python 的全套初跑遇到已安装旧版 shared 包、系统编码和并发环境干扰；未据此改无关业务代码。使用独立虚拟环境后全套通过。GitHub CI 再核验干净平台和严格依赖条件，不将本地可选项跳过冒称已验证。

## 复现

```text
python -m unittest discover -s tests -p "test_reader_*.py"
python -m unittest discover -s tests -p test_paper_reader.py
python skills/paper-close-read/scripts/selftest.py --work-dir <任务临时目录>/selftest
python scripts/check_reader_pdf_browser.py examples/paper-close-read/hardy1908 examples/paper-close-read/carroll1895 examples/paper-close-read/mariana examples/paper-close-read/thomsen --work-dir <任务临时目录>/browser --output <验收目录> --browser-executable <Chrome路径>
python skills/paper-close-read/scripts/export_pdf.py examples/paper-close-read/hardy1908/reader.html Hardy1908.pdf --work-dir <任务临时目录>/pdf
```

公式字节重建使用 latex2mathml==3.77.0；浏览器脚本需 Playwright 和已安装 Chrome。实际 PDF 样本在 Release 提供 Hardy/Carroll 两份，教学归属与 CC BY 4.0 随文件保留；安装包代码 MIT，不附论文。以上是功能与编辑检查，不是读者学习效果试验或全学科一次成稿保证。

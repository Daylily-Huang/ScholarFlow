# 单篇论文带读 / Paper close reading

paper-close-read把一篇学术全文变成可离线打开的阅读页。先讲完整主线，再展开困难环节，最后随时对照原文、译文和逐段解释。正文18px、可调字号、默认展开；解释下直接播放演示；支持搜索、阅读位置、选字高亮、笔记、JSON备份和回到顶部。

## 开始

1. 有宿主模型可读取本地文件的Agent环境，安装Python 3.9+。
2. 优先 [下载 Release 独立安装包](https://github.com/Daylily-Huang/ScholarFlow/releases/tag/paper-close-read-v1.3.0)，解压后复制整个 `paper-close-read` 文件夹，无需克隆。也可在解压目录执行 `python install.py --target <宿主skills目录>`。贡献者从仓库单独安装：`python scripts/install_reader.py --target <宿主skills目录>`；或复制完整skills/paper-close-read目录。该技能独立于shared引擎。已有不同版本时安装器会停止，检查后显式--replace才替换此技能。
3. 提供PDF、可靠Markdown或出版商JATS XML，说“用paper-close-read带我读这篇”。可以补充基础和阅读目的，省略时按主题初学研究者带读。
4. 宿主先通读结构、提炼主线和困难点，再写逐段材料与导读，经校验构建后实际打开检查。新稿不使用旧问答清单兜底，不补丁修改成品HTML。

标准库即可执行解析、结构校验和构建。可选：latex2mathml用于公式；pymupdf用于PDF核查；playwright配可用浏览器用于交互验收。提取服务和模型推理不是离线HTML的一部分，技能不会自行发送到某个收费服务。

## 完整流程

- Markdown：`python skills/paper-close-read/scripts/parse_mineru.py <source.md> <fulltext.json> --paper-id <DOI>`。
- JATS：`python skills/paper-close-read/scripts/import_jats.py <article.xml> <reading-data目录>`。导入不产生讲解，图像按import.json明确提供；作者与编辑区分，段落/引用/表格保留；嵌套引文只出现一次、保留后续文字和出处，注释独立成节，资助声明纳入来源。
- 按SKILL.md和references编写translations.json、guide.json，补核实的页码与必要来源说明。完整段落翻译需保留原意和限定，不能把白话摘要当译文。
- 构建：`python skills/paper-close-read/scripts/build_html.py <fulltext.json> <translations.json> <guide.json> <reader.html> --asset-root <reading-data目录> --source <source.md>`。
- 重建示例：`python scripts/rebuild_readers.py examples/paper-close-read/thomsen examples/paper-close-read/wilcox examples/paper-close-read/mariana examples/paper-close-read/menis examples/paper-close-read/austen`。

三分钟入门以180秒内把握整篇为设计目标，采用背景→缺口→问题→方法→结果→结论六步总览；十分钟展开必要的中间推理。入门页短句独立可读，实际理解需按读者基础试读验收。解释与翻译质量取决于宿主模型，应检查真正的困惑是否讲通、要点是否推进。程序发现漏项与断链，不能判定所有学术解释正确。

## 人文社科读法

按文章如何论证选视角，可组合：定量看概念测量与比较设计，质性看处境、原话和主题生成，概念论证看争论对象、概念区别和推论，历史看史料生成与解释，文学看文本细节与视角。概念卡与显式关系图按需使用，不强制把每篇写成实验论文或每段固定两点。

主展示为3篇自然科学（海洋eDNA实证、引物检测方法、心血管综述）与2篇人文社科（历史、文学）。早期定量心理、质性访谈与哲学例子仍作为额外回归材料保留。历史新增事件/记录/解释分层，文学新增信息通道与原句高亮；引文边界、行内强调、注号跳转及外置资助声明经实际材料检查。主展示均由输入构建并在真实浏览器验证；这不等于所有学科、所有新论文的解释质量已获保证。跨学科演示可配置节点与关系，真正不同的机制仍需合适的新场景。

## 笔记与贡献

阅读页双击即可打开，无运行时网络请求。笔记保存在该浏览器；更换设备前导出JSON。论文原文和用户批注不应随错误报告无意上传。报告问题可提供版本、浏览器、文章类型、复现步骤，以及愿意分享的最小片段；不必提供整篇私有论文。

贡献可改阅读设计、场景、提取适配器或修复交互；共性问题改模板，个案内容改reading-data并重建。提交时说明可复现结果及未测试部分。源代码沿用仓库MIT许可；论文、原图和教学改写的归属见示例ATTRIBUTION，论文材料不因代码开源而自动变成MIT。

通过GitHub仓库分发此独立技能，ScholarFlow原有四项科研流程继续按原协议运行。

历史与文学新增完整示例见[示例目录](../examples/paper-close-read/README.md)，本轮检查见[发布检查](../reports/paper-close-read/publication/acceptance.md)。未改原黑麂项目技能及成品。

示例逐字节重建使用latex2mathml==3.77.0处理公式；安装后再运行重建命令。未安装时核心技能会显示公式原LaTeX，但HTML字节与已发布公式版不同。

## 逐段词汇与双语 PDF

逐段词汇保留实际英文词形，配语境中文义；白话采用具体对象推演关键过程，先直觉、后运作、按需补边界，不用概念解释概念。工具栏可导出 A4 双语 PDF，另存时可选择白话、逻辑和附录。直接生成文件、分页检查与数据字段见 [PDF 与词汇规格](../skills/paper-close-read/references/bilingual-pdf-vocabulary.md)。

## 原图与讲解

新版按独立原文图清单核对图号、子图与图片，关键原图放到10分钟对应讲解后，原图和动图分别保留。新完整稿使用严格图核验；旧提取件没有图时需回原文补图，不能仅凭升级自动恢复。见 [原图完整性规范](../skills/paper-close-read/references/original-figures.md)。

有本地原PDF时可准备原页图像，HTML按可靠页码打开真实原页。窗口支持鼠标拖动、大小调整、翻页与缩放；页码未核实的段落只作浏览。设置及体积/许可说明见 [原页窗口](../skills/paper-close-read/references/pdf-page-viewer.md)。

# 五篇真实文献的完整带读：自然科学3篇 + 人文社科2篇

主展示用三篇自然科学与两篇人文社科，呈现同一技能怎样随研究对象和论证方式调整讲解。各篇保留正式出版PDF、原文转录、全部重建输入及许可归属；两篇新增eDNA实例还保留出版商JATS。正式主文完整带读，外部补充文件仅列目录。

| 领域 | 类型 | 阅读页 | 主线与演示 |
|---|---|---|---|
| 自然科学 ① | 海洋生态实证 | [Thomsen等，2012：半升海水，能读出哪些鱼？](thomsen/reader.html) | 取水→过滤与序列鉴定→15种鱼与常规调查比较→衰减与来源解释；取样流程及按原参数重画的衰减演示 |
| 自然科学 ② | 分子检测方法 | [Wilcox等，2013：极少量DNA，怎样认准物种？](wilcox/reader.html) | 灵敏与特异→探针/引物两种设计→稀释与近缘混样→检测验证；探针发光与引物端区别的过程演示 |
| 自然科学 ③ | 环境毒理与心血管综述 | [Mariana与Cairrao，2020：塑化剂与心血管](mariana/reader.html) | 人群关联→动物反应→血管、脂质与细胞损伤→对齐研究条件；钙与舒张、ABCA1外排、氧化应激演示 |
| 人文社科 ① | 历史与社会法律史 | [Menis，2023：杀妻案件中的减责](menis/reader.html) | 案件/教义差距→家庭与名誉规范→多材料解释；史料分层与支持关系图 |
| 人文社科 ② | 文学细读 | [Bystydzieńska，2022：《劝导》中的声音与认识](austen/reader.html) | nobody→缺少归属→旁听与误读→叙述/身体→公开发言；信息通道与真实原句高亮 |

每篇都有六步3分钟入门、六节10分钟讲解、逐段原文/中文/白话/递进逻辑，以及直接放在讲解下的可操作演示、按需概念卡及核心文献推荐。正文和逻辑默认展开，18px可调字号。新增自然科学三篇分别有40、31、50段主要讲解；历史与文学为95、42段正文及实质注释讲解。作者、单位、书目等辅助信息简列。

## 直接看效果

- [海水eDNA六步入门](thomsen/overview-map.png) · [引物与探针讲解下演示](wilcox/walkthrough.png) · [心血管机制演示](mariana/walkthrough.png)
- [自然科学逐段精读](wilcox/close-reading.png) · [历史讲解](menis/walkthrough.png) · [文学讲解](austen/walkthrough.png)
- 各篇保留mobile.png及mobile-overview.png手机实拍。

GitHub的HTML文件页显示源码：点击 **Download raw file**，保存后用浏览器打开。每个reader.html均是独立离线文件，动图、原图和阅读工具已内嵌。

## 重建与复验

在仓库根运行（公式转换版本用于保持示例逐字节一致；核心技能仍可只用标准库）：

```text
python -m pip install latex2mathml==3.77.0
python scripts/rebuild_readers.py examples/paper-close-read/thomsen examples/paper-close-read/wilcox examples/paper-close-read/mariana examples/paper-close-read/menis examples/paper-close-read/austen
python -m unittest discover -s tests -p test_paper_reader.py -v
python skills/paper-close-read/scripts/selftest.py --work-dir <临时目录>/reader-selftest
python scripts/check_readers_browser.py examples/paper-close-read/thomsen examples/paper-close-read/wilcox examples/paper-close-read/mariana examples/paper-close-read/menis examples/paper-close-read/austen --work-dir <临时目录>/browser --output <报告目录> --browser-executable <已安装浏览器路径>
```

浏览器检查默认实际打开窗口，需可选Python Playwright及已安装Chrome；可按需--headless。HTML从保存输入完整构建，不事后手工修补。改讲解回到reading-data，改通用呈现回到skill。重建摘要见各篇generation-manifest.json；本轮实测见[验收记录](../../reports/paper-close-read/natural-showcase/acceptance.md)。功能及内容检查不代替读者学习成效实验。

## 其他论证方式的回归材料

早期的[定量心理研究](kross/reader.html)、[访谈质性研究](mckenna/reader.html)、[哲学规范论证](tavani/reader.html)仍保留，继续用于兼容性回归；它们不计入上述五篇主展示，也不被归为自然科学。其原有来源归属与输入保留。

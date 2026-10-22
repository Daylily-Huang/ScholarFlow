# 五种真实文章的完整带读

这五篇正式全文用于检查同一技能面对不同论证方式的表现。来源均有开放许可声明，具体归属与教学改写见各篇ATTRIBUTION.md；原PDF、出版商JATS、规范转录与全部重建输入均保留。正式主文完整带读，外部补充文件仅保留目录。

| 类型 | 阅读页 | 主线与演示 |
|---|---|---|
| 定量心理/社会研究 | [Kross等，2013：Facebook与幸福感](kross/reader.html) | 同一个人的反复测量、区间使用与前后感受；时间图与推断路径 |
| 访谈质性研究 | [McKenna-Plumley等，2021：封控中的孤独](mckenna/reader.html) | 从具体讲述到主题、接触与选择的缺失；编码阅读重建与选择条件对照 |
| 哲学概念与规范论证 | [Tavani，2018：社交机器人的道德关照](tavani/reader.html) | 概念澄清→行动者/受体→Jonas理由→推论及范围审查；概念对照与论证图 |
| 历史与社会法律史 | [Menis，2023：杀妻案件中的减责](menis/reader.html) | 区分杀情人与杀妻→案件/教义差距→家庭与名誉规范→多材料解释；史料分层与支持关系图 |
| 文学细读 | [Bystydzieńska，2022：《劝导》中的声音与认识](austen/reader.html) | nobody→缺少归属→旁听与误读→叙述/身体→公开发言；信息通道与真实原句高亮 |

每篇都有3分钟入门、六节10分钟讲解、逐段原文/中文/白话/逻辑、两组讲解下可操作的演示、按需概念卡及4项核心推荐。所有正文和逻辑默认展开。前三篇共有156段主文讲解；新增历史、文学共137段正文与实质注释讲解（95/42段）；参与者身份、作者与书目等辅助信息简列。

## 直接看效果

- [定量入门实拍](kross/overview.png) · [质性讲解与演示](mckenna/walkthrough.png) · [哲学讲解与演示](tavani/walkthrough.png)
- 各篇另有close-reading.png和mobile.png，分别是逐段与390px手机视口实拍。

## 重建与复验

在仓库根运行：

```text
python scripts/rebuild_readers.py examples/paper-close-read/kross examples/paper-close-read/mckenna examples/paper-close-read/tavani
python -m unittest discover -s tests -p test_paper_reader.py -v
python skills/paper-close-read/scripts/selftest.py --work-dir <临时目录>/reader-selftest
python scripts/check_readers_browser.py examples/paper-close-read/kross examples/paper-close-read/mckenna examples/paper-close-read/tavani --work-dir <临时目录>/browser --output <报告目录> --browser-executable <已安装浏览器路径>
```

浏览器脚本使用Python Playwright，默认实际打开窗口，可按需--headless。批注测试只在指定临时目录的独立profile中操作。发布前根据当前环境重新检查，不把此处结果当未来浏览器支持保证。

当前检查报告在[验收记录](../../reports/paper-close-read/publication/acceptance.md)。重建需与generation-manifest.json摘要一致；HTML不能事后手工修补。修改讲解回到reading-data，通用交互问题回到skill资源，再重新生成。

历史/文学：保留原论文全部正文、50/6条注释和完整书目；独立引文有边界与出处。新增两篇各50项Chrome检查，原三篇各48项复验，详见[本轮验收](../../reports/paper-close-read/publication/acceptance.md)。跨行内样式高亮与重开恢复另有实测；尚无读者学习成效实验。


最新三分钟入门改为六步研究总览（背景→缺口→核心问题→怎么做→主要结果→结论与意义），五篇正文各约430–460字符。overview-map.png是总览实拍，mobile-overview.png是手机整页实拍；原来的十分钟与逐段资料保留。最新验收见[三分钟总览记录](../../reports/paper-close-read/publication/acceptance.md)。

# 原图完整性及PDF原页窗口：v1.3.0

日期：2026-10-26。HTML 全部从输入和通用渲染器重建，未事后补写。

## 本次范围

- 独立原文图清单：JATS原XML图号、graphics及图像公式，或PDF逐页看图记录；核对整图、子图、图注、来源与图片哈希。新完整稿 `--require-figure-audit`，旧稿缺清单显示待核对。
- 关键原图在10分钟对应讲解段后就地展示：保留原图注，新增“先看哪里／这张图说明什么”，可放大。教学动图不替代结果原图。
- 原PDF文件页快照离线内嵌：可靠页码直接定位，未知只作浏览；窗口支持鼠标拖动标题栏、右下角调整大小、翻页、缩放、最大化还原、键盘操作。原图放大窗复用移动缩放。原页快照不是原生可选字PDF引擎。
- 新独立安装包与中文说明，README优先下载v1.3.0，另提供两份可直接下载的单HTML示例。

## 实际来源核查

Thomsen 2012与Wilcox 2013：各9页原PDF，对照完整页缩略图、图页及原图文件与图注。Thomsen有3幅主文图和2个图像公式；Wilcox有3幅主文图，分别含A–C、A–D、A–B子图。均保留完整原图及原始来源顺序，输入的sections与旧版完全相同。没有编号子图的不强造字母。每篇关键3图均配置导读原位展示。

原PDF/原XML、原图片、source.md及逐段翻译未改写；新增figure_inventory/source_pdf资料记录和guide中的读图安排。原文文字逐页全部校对与原图清点是两回事，既有文字待核状态保留。外部补充文件范围沿用原示例，不宣称已核对全部补充材料。

## 功能验证

- 50项reader回归通过（33项reader_*及原17项），技能40项自检通过。新测遗漏原图/graphic、漏核子图、图像篡改、错误引用/插入点、段内图片误作普通文字、多graphic与替代格式、原页哈希和页码、旧输入兼容。
- 四篇实际Chrome离线浏览：Thomsen、Wilcox、Hardy、Carroll。图片与原资产字节一致，图注、就地插入、放大、原动图及打印恢复通过。前两篇各9个PDF原页，鼠标实际移动/缩放、原页切换与缩放、最大化还原、可靠/未知页码入口、390px模拟布局通过；后两篇无原页数据仍正常使用。
- 实际导出Thomsen、Wilcox双语PDF分别41/40页，保留5/3个图片项（图像公式在内），不重复导读引用图，不将9页原件再附入。PDF图像维度与原资产相同；Chrome重编码图像，未声称PDF图片字节相同。已渲染组合图、柱图及相关图页目视检查，轴、图例和子图完整。
- 既有Hardy/Carroll交互各40项通过。四篇输入通过独立安装的生成器重建；重复安装和相邻技能保留由打包检查验证。
- 全套本地隔离测试中1218项阶段检查通过（44依赖跳过）；加原页后1221项初跑有一项已有Windows并发锁PermissionError，未改无关共享引擎；该41项文件定向重跑通过（2跳过）。远端干净CI的结果在发布记录另存，不能以本地跳过或重跑冒充全平台通过。

浏览器报告与PDF报告绑定最终HTML哈希。390px是模拟布局，未测真实手机硬件、辅助技术或学习效果。独立验收及GitHub精确提交CI另行记录，发布前不得将尚未得到的结果写成已通过。

## 复现

```text
python -m unittest discover -s tests -p "test_reader_*.py"
python -m unittest discover -s tests -p test_paper_reader.py
python skills/paper-close-read/scripts/selftest.py --work-dir <临时目录>/selftest
python scripts/check_reader_pdf_browser.py examples/paper-close-read/thomsen examples/paper-close-read/wilcox examples/paper-close-read/hardy1908 examples/paper-close-read/carroll1895 --work-dir <临时目录>/browser --output <验收目录> --browser-executable <Chrome路径>
python scripts/package_reader.py --output <临时目录>/package --verify
```

公式精确重建使用latex2mathml==3.77.0；准备原页可选PyMuPDF。核心构建保持标准库。源材料与内嵌原页遵循论文原许可，新增教学内容遵循示例许可，skill代码MIT。

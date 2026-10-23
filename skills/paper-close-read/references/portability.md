# 安装与运行

将整个paper-close-read目录复制到宿主的skills目录即可使用，独立于ScholarFlow的shared引擎。可在仓库执行 `python scripts/install_reader.py --target <宿主skills目录>`；只安装此技能，目标已存在时先比较，明确--replace才替换。Python 3.9+；核心构建只用标准库，公式转换可选latex2mathml（缺少时显示原LaTeX），PDF文本/原页核查可用可选pymupdf，浏览器验收可用playwright及已安装Chrome。PDF/OCR和模型撰稿由宿主执行，不自动调用收费服务。

先提供PDF、可靠Markdown或出版商JATS。可直接说“用paper-close-read带我读这篇论文”。模型读取SKILL.md，先提取主线和难点，再写完整逐段解释与guide，最后验证和构建；HTML是产物，不事后补丁。需要重建时保留原文.md、fulltext.json、translations.json、guide.json和图像，在ScholarFlow仓库执行 `python scripts/rebuild_readers.py <阅读目录>`；单独安装时使用本技能的 `python scripts/build_html.py <fulltext.json> <translations.json> <guide.json> <输出.html> --asset-root <reading-data> --source <source.md>`。

生成解释需要模型和来源材料；生成后的单文件HTML不依赖网络。浏览器本地保存笔记，跨设备用JSON导出/导入。材料授权由各来源决定；技能代码的MIT许可不替代论文/图像的许可。示例的引用、翻译和教学改写在各篇ATTRIBUTION.md说明。

## 最小依赖与可重建交付

| 环节 | 依赖 | 是否进入生成后的HTML |
|---|---|---|
| Markdown/JATS解析、校验、构建 | Python3.9+标准库 | 不需要Python运行 |
| LaTeX转MathML | 可选latex2mathml；Python3.9可用3.77.0，按Python版本选择兼容发行版 | 只内嵌生成的MathML |
| PDF提取/原页查看 | 宿主现有工具；PyMuPDF只是可选方案 | 不内嵌工具 |
| 实际浏览器验收 | 可选Playwright与已安装Chrome，或对应Firefox/WebKit引擎 | 不内嵌测试框架 |

PyMuPDF有自己的AGPL/商业许可选项，见[官方许可](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)；它不是核心构建依赖。拟分发或部署第三方组件时分别核对所选版本许可，不能用本技能MIT许可替代。代码与场景采用本仓库许可；论文、第三方图像、字体和宿主服务仍遵循各自来源条件。默认系统字体不打包字体文件。

构建器嵌入generatorVersion（当前本地1.1.0-dev），备份schema2/3保持兼容，不自动清空旧笔记。依赖升级后重建应重新验收公式、图像与笔记定位。在仓库可用`python scripts/freeze_readers.py <阅读目录>`核对最终HTML可按字节重建，并生成输入、技能树和HTML摘要；该记录不替代语义审读。

读者数据格式、隐私、冲突与故障恢复见[阅读记录与维护](reader-operations.md)。生成文件需保留的来源声明与核验范围由实际取得材料决定。不要把未经目标读者测试的“无痛”“三分钟学会”写成产品效果保证。

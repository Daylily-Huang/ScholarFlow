# 安装与运行

将整个paper-close-read目录复制到宿主的skills目录即可使用，独立于ScholarFlow的shared引擎。可在仓库执行 `python scripts/install_reader.py --target <宿主skills目录>`；只安装此技能，目标已存在时先比较，明确--replace才替换。Python 3.9+；核心构建只用标准库，公式转换可选latex2mathml（缺少时显示原LaTeX），PDF文本/原页核查可用可选pymupdf，浏览器验收可用playwright及已安装Chrome。PDF/OCR和模型撰稿由宿主执行，不自动调用收费服务。

先提供PDF、可靠Markdown或出版商JATS。可直接说“用paper-close-read带我读这篇论文”。模型读取SKILL.md，先提取主线和难点，再写完整逐段解释与guide，最后验证和构建；HTML是产物，不事后补丁。需要重建时保留原文.md、fulltext.json、translations.json、guide.json和图像，在ScholarFlow仓库执行 `python scripts/rebuild_readers.py <阅读目录>`；单独安装时使用本技能的 `python scripts/build_html.py <fulltext.json> <translations.json> <guide.json> <输出.html> --asset-root <reading-data> --source <source.md>`。

生成解释需要模型和来源材料；生成后的单文件HTML不依赖网络。浏览器本地保存笔记，跨设备用JSON导出/导入。材料授权由各来源决定；技能代码的MIT许可不替代论文/图像的许可。示例的引用、翻译和教学改写在各篇ATTRIBUTION.md说明。

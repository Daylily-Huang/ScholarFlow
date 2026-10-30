# 文献阅读 skill 1.4.0 安装说明

本说明随v1.4.0源码及构建包提供。本次为源码同步，正式Release下载入口仍以仓库首页和Release列表实际发布版本为准。

这是 paper-close-read 的独立安装包，不需要下载整个 ScholarFlow 仓库。解压和复制技能不需要 Python；运行技能中的解析、校验和构建工具需要 Python 3.9 或更高版本。生成讲解需要你所用 AI 助手的模型和论文材料，阅读生成的 HTML 不需要 Python 或联网。

## 方式一：直接复制

1. 下载 `paper-close-read-v1.4.0.zip`，完整解压。
2. 将里面整个 `paper-close-read` 文件夹复制到你的 AI 助手实际读取的 `skills` 目录。不要只复制 `SKILL.md`；`scripts`、`assets` 和 `references` 都需要保留。
3. 如助手未立即识别新技能，按该助手的方式刷新技能列表或重新开始会话。
4. 提供一篇 PDF、可靠 Markdown 或出版商 JATS，并说：“用 paper-close-read 带我读这篇论文，先讲清整篇主线，难点配动图，再逐段解释。”

包内不含模型、论文全文或 PDF/OCR 服务，也不会自动调用收费服务。

## 方式二：用包内安装器

在解压目录打开终端，将 `<skills目录>` 替换为你所用 AI 助手实际读取的技能目录：

```text
python install.py --target "<skills目录>"
```

安装器只安装 `paper-close-read`，不改相邻技能。已有相同版本可重复执行；发现不同文件时默认拒绝覆盖。确认备份自己修改的技能后，可明确替换：

```text
python install.py --target "<skills目录>" --replace
```

安装器会先复制、校验完整性，再切换目录；失败会尝试保留原安装。重要的自定义技能修改请自行保留副本。

## 更新已有阅读页与笔记

更新 skill 不会自动重写已有 HTML。需要新版功能时，应从保存的阅读资料重新生成，原文和已有 HTML 建议保留。浏览器笔记属于阅读页本地记录；改文件位置、换浏览器或清缓存前，先在阅读工具中导出完整 JSON 备份。这里的安装器不会读写浏览器笔记。

## 可选依赖与核验

核心工具只使用 Python 标准库。公式转 MathML 可选 `latex2mathml`；PDF提取和浏览器验收工具均按需配置，不包含在安装包中。

包内 `manifest.json` 列出每个文件的 SHA256；Release 的 `SHA256SUMS.txt` 可校验 ZIP 和其他附件。Windows 可运行 `Get-FileHash .\paper-close-read-v1.4.0.zip -Algorithm SHA256`，macOS可用 `shasum -a 256`，Linux可用 `sha256sum`。

## 来源与许可

技能代码及场景按包内 `paper-close-read/LICENSE` 的 MIT 许可分发。论文、图片和外部工具的许可各自适用；此包不附大学托管PDF或第三方测试引擎。

## 双语 PDF 与词汇

阅读页逐段列出重点英文词和语境中文释义。点击“导出双语 PDF”，选择纸张方向和是否包含白话、逻辑、附录，在打印窗口选择“另存为 PDF”。也可让助手运行 `paper-close-read/scripts/export_pdf.py reader.html 双语.pdf --work-dir <任务临时目录>`，需本地 Chrome/Chromium/Edge。PDF 为静态排版，交互动图保留在 HTML。新功能须从阅读资料重建旧页才能获得。

## 原图完整性

新版保留论文原图与图注，关键原图在10分钟对应讲解下就地展示。新完整稿需建立独立原文图清单、核对各子图并使用 `--require-figure-audit`；旧稿仍可重建但缺清单时显示待核对。更新不能自动补回原提取阶段已经遗失的图片，需要回到原文取图和核对后重建。

## 原PDF页面查看

用新版重建并准备source_pdf原页图像后，工具栏和对应段落可打开PDF原页窗口。鼠标拖标题栏移动、拖右下角调整大小，支持翻页、缩放与最大化。原页准备脚本使用可选PyMuPDF，核心构建仍是标准库。旧HTML需重建，更新技能不会直接修改旧页。

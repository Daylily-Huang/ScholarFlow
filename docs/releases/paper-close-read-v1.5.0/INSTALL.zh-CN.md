# 文献阅读 skill v1.5.0 安装与升级

[下载 v1.5.0 独立 ZIP](https://github.com/Daylily-Huang/ScholarFlow/releases/download/skills-2026-11-01/paper-close-read-v1.5.0.zip)，完整解压后运行包内 `python install.py --target "<AI助手实际读取的skills目录>"`。旧版或自定义文件有差异时会停止；确认升级后使用 `--replace --backup "<同盘的新备份目录>"`，先保留旧文件。详细步骤及校验方法见[三个Skill统一安装说明](../skills-2026-11-01/README.md)。

也可在源码仓库执行：

```text
python scripts/install_reader.py --target "<AI助手实际读取的skills目录>"
```

已有自定义版本先备份；确认替换此技能后使用--replace。核心构建需要Python3.9+，生成的HTML无需Python或联网。

独立 ZIP 与旧版 v1.3.0 包分开保留，请使用上方 v1.5.0 下载链接；包内安装器和源码安装器的升级参数不同，以对应说明为准。

给助手论文并说“用paper-close-read制作带读页，抓主线，为难点设计并验收直观演示”。对象与关键帧由助手编写；无需使用者开发场景。新完整稿用--require-figure-audit --require-visual-plan构建。

升级skill不会改旧HTML；用原阅读资料重建才能获得新绘制能力。保留旧页，移动文件或更新前导出批注JSON。论文材料与技能代码许可分别适用。

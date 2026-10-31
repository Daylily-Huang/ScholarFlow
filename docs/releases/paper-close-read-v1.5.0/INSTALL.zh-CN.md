# 文献阅读 skill v1.5.0 源码安装

此次只更新源码，正式Release下载仍为v1.3.0；请勿把旧包当作v1.5.0。可从仓库复制完整skills/paper-close-read目录，或在源码仓库执行：

```text
python scripts/install_reader.py --target "<AI助手实际读取的skills目录>"
```

已有自定义版本先备份；确认替换此技能后使用--replace。核心构建需要Python3.9+，生成的HTML无需Python或联网。

如获得维护者构建的v1.5.0独立ZIP，可完整解压、复制paper-close-read目录，或执行包内python install.py --target "<skills目录>"。此说明不表示该ZIP已发布到GitHub Release。

给助手论文并说“用paper-close-read制作带读页，抓主线，为难点设计并验收直观演示”。对象与关键帧由助手编写；无需使用者开发场景。新完整稿用--require-figure-audit --require-visual-plan构建。

升级skill不会改旧HTML；用原阅读资料重建才能获得新绘制能力。保留旧页，移动文件或更新前导出批注JSON。论文材料与技能代码许可分别适用。

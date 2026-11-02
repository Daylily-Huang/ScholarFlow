# 文献阅读 skill v1.6.0 安装与升级

[下载 v1.6.0 独立 ZIP](https://github.com/Daylily-Huang/ScholarFlow/releases/download/paper-close-read-v1.6.0/paper-close-read-v1.6.0.zip)，无需克隆仓库。下载后先按同一Release的SHA256SUMS.txt核对文件，再完整解压。

ZIP完整解压后，在包目录运行：

```text
python install.py --target "<AI助手实际读取的skills目录>"
```

Python3.9+。安装器只处理paper-close-read，不改其他skill；不同版本默认停止。升级前导出浏览器批注；确认后执行 `python install.py --target "<skills目录>" --replace --backup "<同盘且尚不存在的备份目录>"`，旧skill先备份，旧HTML不会自动更新。

提供论文并要求助手按SKILL.md完整制作。构建器命令行默认complete，缺来源审读、原图清点、难点覆盖或六步入门会停止；旧资料重建显式 `--profile legacy`，待补稿显式 `--profile draft`。内容质量仍须对照原文和实际浏览器检查。

保留原来源、fulltext.json、translations.json、guide.json及图像；修订输入或生成器后重建，不手补HTML。只有安装包、manifest及SHA256校验文件一致，才算核实下载文件；校验不证明论文内容解释正确。

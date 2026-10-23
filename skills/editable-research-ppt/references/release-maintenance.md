# 发布与副本同步

维护源为 ScholarFlow 仓库的 `skills/editable-research-ppt/`。安装目录和解压发布目录是分发副本；若在安装目录改进了技能，先备份，再把明确修改的文件合入仓库候选版，保留现有宣传资源，避免三份分别维护。

1. 修改代码、输入约定与测试；运行 `python -I -S -B -m unittest discover -s tests -v`。
2. 新版自适应样板从 `assets/examples/adaptive-{solid,light}.json` 生成，并运行严格审计。Windows PowerPoint 导出后逐页看图；图片与对应 PPTX 一起更新。
3. 在 `assets/template-system.json` 与 README 更新版本。`approved-standard.json` 的历史设计基线日期属于历史事实，不因代码更新而改写；更新当前实现与当前样板哈希，并说明差异。
4. 新建 `references/v<版本>-hashes.json`，包含 `version`、验证日期和 `sha256` 字典。历史快照不应改成当前文件哈希，也不应被当作当前完整性证明；已知错误明确记录勘误。
5. 最后生成 `SHA256SUMS.txt`：对全部包文件按相对路径排序，写 `SHA256  相对路径`；排除该清单自身、`.git`、`__pycache__`、`.pyc`、系统缩略图与 Office 锁文件。生成器模块 `scripts/verify_release.py` 的 `package_files()` 定义范围。清单更新后不再修改文件。
6. 运行 `python -I -S -B scripts/verify_release.py`；它核对文件缺失、额外文件、内容变化、当前版本快照和批准标准中的当前哈希。失败时先调查差异，不以刷新清单代替调查。
7. 独立发布核验通过后，按获准范围同步安装目录、发布目录和 GitHub。同步后再次核验；打包新版本 ZIP，保留旧版本，并验证解压内容与清单一致。

主仓库 CI 入口是 `.github/workflows/research-ppt.yml`；本技能目录中的 `.github/workflows/test.yml` 供独立开源副本使用。两个入口均运行完整测试发现及发布完整性检查。CI 的三系统生成测试不等同于 macOS PowerPoint、WPS 或 LibreOffice 的实际排版验证。

日常使用者升级/回退仅改一个skill目录时，按[本地安装维护](local-installation.md)使用`install_local.py`，保留旧版及本地修改；不要直接用仓库总安装器批量覆盖其他技能。

公开发布前另运行 `python -I -S -B scripts/verify_publication.py`，确认设计契约与隐私扫描通过；检查图片和Office内部元数据。冻结的版式、配色与字号不得在隐私清洗中改变，具体见[通用发布规程](publication-policy.md)。

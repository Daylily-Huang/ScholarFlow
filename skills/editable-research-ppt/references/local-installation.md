# 本地安装、升级与回退

只操作指定的`editable-research-ppt`技能目录，不改其他skill、系统字体、代理或Git。先下载/解压完整的已核验版本；脚本不自动联网拉取。源目录不能位于目标目录内，也不能把整个skills父目录当成目标。

新装：

```console
python scripts/install_local.py --target /assistant/skills/editable-research-ppt --dry-run
python scripts/install_local.py --target /assistant/skills/editable-research-ppt
```

升级（备份目录必须是新目录，且与安装目标在同一文件系统）：

```console
python scripts/install_local.py --target /assistant/skills/editable-research-ppt --replace --backup /assistant/skill-backups/ppt-before-upgrade --dry-run
python scripts/install_local.py --target /assistant/skills/editable-research-ppt --replace --backup /assistant/skill-backups/ppt-before-upgrade
```

命令中的目录按实际环境替换，含空格时加引号。Windows示例目标位于当前账户的 `~/.codex/skills/editable-research-ppt`，备份放在同一文件系统的 `~/.codex/skill-backups/` 内；也可用其他助手的skills路径。不会自动寻找并覆盖多个安装副本。完成后重新开启助手会话，使它重新读取技能。

源包先验完整性，旧版默认也须完整。检测到本地增改时停止，让使用者先合并到新候选；确实要把当前改动完整存入备份后换新版，添加`--allow-local-changes`。此选项保留旧目录所有文件，但**不自动把旧改动合并进新版**；先给出差异清单与备份落点。不要把有意修改的文件重新刷哈希后冒充原始发布包。

更新以重命名保留旧目录，再复制并核验新目录。普通复制失败会恢复旧目录，部分新文件留在备份目录的`failed-install`以便定位，不删除用户文件。首次安装失败可能留`editable-research-ppt.failed-*`。若进程被强制终止或断电，可能留下不完整目标：用备份检查恢复，不宣称跨目录更换是单次原子事务。

干净已核验备份的回退：

```console
python scripts/install_local.py --source /assistant/skill-backups/ppt-before-upgrade/editable-research-ppt --target /assistant/skills/editable-research-ppt --replace --backup /assistant/skill-backups/ppt-before-rollback
```

回退也保留当前版本，且不覆盖已有备份。若旧备份含本地修改、未通过原版清单，先人工核对差异；完整目录仍在备份中，可在保留当前目录后手动恢复或将改动合并进可验候选。安装程序不会执行或隐式信任这些改动。`--dry-run`只检查路径与清单，不会写入，也不证明实际复制权限、磁盘容量或Office显示已通过。

# 三个 Skill 独立安装包（2026-11-01）

[Release 与所有校验文件](https://github.com/Daylily-Huang/ScholarFlow/releases/tag/skills-2026-11-01)

| Skill | ZIP | Python | 包含内容 |
|---|---|---|---|
| 单篇文献带读 1.5.0 | [下载](https://github.com/Daylily-Huang/ScholarFlow/releases/download/skills-2026-11-01/paper-close-read-v1.5.0.zip) | 3.9+ | 原文/译文/白话、原图原页、双语 PDF、通用过程演示与难点覆盖 |
| 可编辑科研 PPT 1.8.0 | [下载](https://github.com/Daylily-Huang/ScholarFlow/releases/download/skills-2026-11-01/editable-research-ppt-v1.8.0.zip) | 3.10+ | 完整模板、示例、字体、图标、脚本和各自许可证 |
| 文献检索与获取 0.6.6 | [下载](https://github.com/Daylily-Huang/ScholarFlow/releases/download/skills-2026-11-01/literature-discovery-acquisition-v0.6.6.zip) | 3.9+ | 检索技能、shared 引擎、schemas、能力说明、免费 OpenAlex Key 接入教程 |

这是安装与分发更新，不变更科研算法；组件版本取自已合入的源码，不将打包日期当作能力升级。

## 新安装

1. 下载所需 ZIP，按同一 Release 的 `SHA256SUMS.txt` 校验文件。Windows 可执行 `Get-FileHash <ZIP路径> -Algorithm SHA256`；Linux 执行 `sha256sum <ZIP路径>`，macOS 执行 `shasum -a 256 <ZIP路径>`，核对对应文件行。
2. 完整解压，在有 `install.py` 的目录打开终端。
3. 确认 AI 助手实际读取的 skills 目录。Codex 通常是用户目录下 `.codex/skills`，Claude Code 通常是 `.claude/skills`，其他宿主以其配置为准。
4. 执行 `python install.py --target "<AI助手实际读取的skills目录>"`；随后重新加载技能或重启助手。

不要只复制检索 Skill 文件夹；它依赖同包的 shared 和 schemas，能力文档位于技能目录内的 docs/。带读和 PPT 独立运行，不要求安装另外两个 Skill。安装器不会设置 API Key、安装字体、查询论文或修改系统设置。

## 从旧版升级

相同内容重复安装会返回 `already-current`。发现旧版或自定义文件有差异时，默认停止。

先查看差异并保存自己的配置，再指定一个同盘、尚不存在且在安装目录外的备份目录：

```text
python install.py --target "<skills目录>" --replace --backup "<同盘的新备份目录>"
```

替换前校验并暂存全部新文件；旧目录保留在备份目录，安装失败时回滚已移动目录。只处理包内清单声明的目录。检索包会更新 shared、schemas，共用这些目录的其他 ScholarFlow 核心 Skill 应保持版本兼容；其他 Skill 文件夹和外部 docs 目录不替换。

升级不自动改写旧 HTML/PPT 或论文、实验数据与批注。带读需要用保留的阅读资料重建旧页面才能获得新绘制功能；移动页面前导出批注 JSON。

## 来源与发布验收

技能源码固定为 `4ef40f3b8c1ee82b43a3a768cb54e6c209fb9e8e`。构建器直接读取 Git 对象，不打包脏工作区、个人 Key、缓存、临时件或历史备份。每个 ZIP 含文件级清单、安装器和中文说明；外部 manifest、release-index 和 SHA256SUMS 可复核。为保持解压后的链接，检索包对随包 Markdown 的部分相对链接重新定位，清单明确记录变更文件；科研代码不改写。

发布流程先校验三个解压安装结果、幂等安装和无关技能保留，再运行带读自检、PPT 生成/审计、检索安装后的离线诊断与版本入口。PR 不发布；主分支发布还须同一提交的完整 CI 成功。附件先上传草稿并核对 GitHub 服务端 SHA256，再公开。已有正式 Release 附件不删除、不覆盖。

未安装或使用真实 OpenAlex Key 进行线上认证；免费 Key 的注册与配置由使用者按随包教程完成。字体、图标、论文材料等不统一改为 MIT，保留相应原始许可。

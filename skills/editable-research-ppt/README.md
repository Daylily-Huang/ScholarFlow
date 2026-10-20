# 可编辑科研 PPT · 便携开源版 v1.3.0

三种汇报场景、六套配色、两种填充风格、二十种版式及多种变体。支持**根据使用者提供的资料实时自适应（`visual_mode: adaptive`）**：自动移除生硬默认位图与卡片内冗余大图标，实时匹配极简学科线框图标或嵌入原图，原生表格自适应列宽与统一字号，并配备强制性的字体、字号与位置对齐核验。

![学术分享样板](examples/previews/academic/slide-01.png)

**代码与文档采用 MIT；随包字体遵循各自 OFL-1.1 许可证。**

## v1.3 原图证据与六种新布局

新增论文导读、大图讲解、全貌与局部、地图采样、实验时间轴、文献矩阵；左右交换、整图展示等作为变体，不另计版式。固定可编辑图号、来源、放大框、编号与章节导航。

**原图是硬指标：有相关论文图表时，必须从 PDF 直接裁出完整图表嵌入；默认不重绘、不重组。** 正式输入必须声明 `materials.papers`；缺少相关原图、原文或核对记录时阻止生成。原图内部属于图片，不承诺逐项可编辑。详见 [原图与版式规则](references/evidence-and-composition.md)。

[六页新版样板](examples/evidence-layouts.pptx) · [六页版式变体](examples/evidence-variants.pptx) · [样板预览](examples/evidence-index.html)

## v1.2.1 可靠性修复

严格审计遇到警告即失败，覆盖图表字体/字号、表格实际容量与对象边界；PowerPoint 渲染发现质量问题也返回失败。配图改为明确的命名插槽，封面摘要超量或过长时提示调整，不静默丢字。字号配置现在直接作用于生成结果，浅底与实底自适应表格统一为表头 21px / 数据 20px，图表标注不低于 17px。

[查看新版 28 页自适应样板](examples/index.html#adaptive-solid) · [实底 PPTX](examples/adaptive-solid.pptx) · [浅底 PPTX](examples/adaptive-light.pptx) · [四页宣传样板](examples/promo/)

自动检查不能代替逐页看图；文字、框图、表格和数据图保持原生可编辑，插入的 PNG 仍是独立图片。配图支持范围与容量限制见[输入约定](references/input-and-templates.md)，更新与同步见[发布维护](references/release-maintenance.md)。

制作时优先使用与论点相关、清晰可读的论文原图或用户实验结果，保持原色、比例及必要标注，并记录图号与资料来源；密集图拆页或局部放大，仅在用户明确要求后另做重绘并保留原图对照。完整规则见 [SKILL.md](SKILL.md) 的“真实资料原图优先原则”。

## v1.2 实时资料自适应与去 AI 味更新

针对真实文献汇报与科研进展场景（`demo: false` 默认启用 `adaptive` 模式）：

1. **拒绝模板硬塞与生硬“人机感”图标**：
   - 自动移除模板默认的森林/鸟类生态位图，清理卡片正文区占宽 35%–60% 的重复装饰大图标（`L1/L2/L6/L8/L12/L13/L14`），将完整卡片宽度（`344–816px`）归还给自然学术正文、原生表格与数据图。
   - 标题栏与流程节点采用极简线框矢量图标（`dna`, `pcr`, `table`, `chart`, `filter`, `warning`, `check`, `location`, `layers`, `workflow`, `document`, `compass`, `search`, `none`），可根据每张卡片的内容实时匹配并同页去重。
   - 单图版式 `L2/L5/L7/L8/L14` 可通过 `"image": "path/to/fig.png"` 按原图真实宽高比嵌入实验图或序列截图；`L9` 使用命名 `images` 插槽（见输入约定）。无外部配图时，`L5`（封面）、`L7`（章节页）、`L9`（对照页）、`L14`（讨论页）自动构建 **100% 原生可编辑的摘要卡、动态章节路线图（支持 `active: 0..3`）、对照卡与讨论焦点卡**。
2. **原生表格与散点图自适应**：
   - `L4` 表格自动按列内容视觉长度分配列宽、统一所有数据单元格字号为 `20px`（表头 `21px`），并清除模板残留 `#AF3D3D` 红底色块，防止数值区间（如 `193–202`）折行撑破表格。
   - `L10` 散点图默认不强加回归趋势线（需拟合线时设 `trendline: true`）。
3. **强制后置检查（字体、字号、位置对齐）**：
   - `scripts/audit.py --strict` 与 `scripts/render_powerpoint.ps1` 自动核验字体白名单、单页字号层级、表格数据格字号统一性、CJK 文本/表格折行溢出、表格纵向撑高碰撞及图文边界重叠。

## 三分钟开始

需要 Python 3.10 或更新版本。生成部分只使用 Python 标准库，无需 pip、Node、API 密钥或私有运行时。在解压后的本目录运行：

```console
python scripts/check_environment.py
python scripts/install_fonts.py
python scripts/generate.py --input assets/examples/adaptive-solid.json --output my-talk.pptx
python scripts/audit.py my-talk.pptx --strict
```

字体安装脚本仅向**当前用户**字体目录写入随包 Noto 字体；安装后重启 PowerPoint/WPS。若不想运行脚本，也可以手动安装 `fonts/` 中四个 OTF 文件。`--font-profile office` 可改用微软雅黑/宋体。

## 作为 Agent Skill 使用

把**整个目录**放进所用助手的技能目录，保留 `SKILL.md`、`scripts/`、`assets/`、`references/` 和 `fonts/` 的相对关系（例如 `~/.codex/skills/editable-research-ppt/` 或 `~/.agents/skills/editable-research-ppt/`）。

告诉助手：

> 用 editable-research-ppt 做科研汇报。先问我的场景，再问主配色，最后问填充风格；根据我提供的材料实时组织内容与图表，保留可编辑原生对象，完成后检查字体、字号和位置对齐。

## 可选范围

| 场景 | 内容侧重 |
| --- | --- |
| 学术分享 (`academic`) | 研究问题、实验与方法设计、核心数据证据、方法适用边界与讨论 |
| 课程作业 (`coursework`) | 任务要求、概念与方法、比较推导、回答与反思 |
| 实验进展 (`progress`) | 本期目标、完成状态、初步结果、问题诊断与下一步 |

| 配色 | 主色 | 配色 | 主色 |
| --- | --- | --- | --- |
| P1 蓝白朱红 | `#1359A0` | P4 酒红灰蓝 | `#8F2445` |
| P2 松绿米白 | `#136742` | P5 靛紫芥黄 | `#4D319F` |
| P3 石墨青金 | `#07556B` | P6 湖蓝珊瑚 | `#087F9A` |

## 开发与测试

```console
python -I -S -B -m unittest discover -s tests -v
python -I -S -B scripts/verify_release.py
```

25 项测试覆盖原有生成能力及负向案例：六色×双填充×十四版式、自适应表格容量、图表字体、命名配图、双色调继承、摘要不截断、配置生效和发布文件完整性。旧版示例保留用于兼容性对照；当前严格标准以新版自适应样板为准。

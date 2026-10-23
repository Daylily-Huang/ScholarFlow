# 数据与模板约定

## 填充风格与自适应资料模式（v1.2）

新建汇报按 **场景 → 配色 → 填充风格** 依次询问，收到上一步答案后再进入下一步；已明确的不重复问。输入顶层写 `fill_style: "light"` 或 `"solid"`。十套配色全部支持两种风格。

- `visual_mode`：
  - 当 `demo: false` 时，默认 `visual_mode: "adaptive"`（或 `"clean"`）：
    1. **自动移除无关默认插画与卡片内冗余大图标**：不再强塞模板自带的森林/鸟类位图，也不在卡片正文区放置 `72px–100px` 的重复大图标，释放完整卡片宽度（`344–816px`）给正文、表格与数据图。
    2. **实时学科线框图标与按页原图嵌入**：标题栏与流程节点使用极简线框矢量图标（支持 `dna`, `pcr`, `table`, `chart`, `filter`, `warning`, `check`, `location`, `layers`, `workflow`, `document`, `compass`, `search`, `none`，或由生成器根据该卡文本自动匹配并同页去重）；单页可通过 `"image": "path/to/fig.png"` 按真实宽高比无损嵌入用户材料原图（不强制套双色调滤镜）。
    3. **无外部配图时自动生成原生可编辑卡片**：`L5`（封面核心速览卡，支持 `highlights`）、`L7`（章节路线图卡，支持 `active: 0..3` 动态高亮）、`L9`（机制/状态对照卡）、`L14`（讨论焦点与下一步卡，支持 `anchor_details`）。
       - `L5.highlights`：长度 1–4 的数组，每项 `{"label","value","detail"}`，渲染为封面右侧「核心信息速览」卡；显式空数组、超过四项或文字超容量均报错。省略时使用最多四个目录章节或内容页完整标题，不截断长标题、数值、来源，也不承诺覆盖全部正文。
       - `L12.items[*]` 可另加 `problem_label` / `response_label`，替换该卡「问题」「应对」两个固定小标题（如改为「现象」「处理」）。
    4. **原生表格自适应归一化**：`L4` 表格自动按列内容视觉长度分配列宽、统一所有数据行字号为 `20px`（表头 `21px`），并清除模板残留 `#AF3D3D` 警示色块。
  - 当 `demo: true` 时，默认 `visual_mode: "legacy"`，保持历史示例逐字节兼容。

## 从示例修改

先按每页论点和证据规划；从 `assets/examples/academic.json`、`coursework.json` 或 `progress.json` 参考字段，不照搬整套页序。`all-layouts.json` 保留历史十四种结构；`compact-approved.json` 提供 L21–L23 的六个已批准紧凑变体。

顶层字段：`scenario` = `academic|coursework|progress`；`palette` = `P1`…`P10`；`demo` 为布尔值；`slides` 为 1–150 页列表。正式内容设 `demo: false`，并提供 `footer`。每页提供 `sources`，每张图提供 `source`，写入备注以供追溯。

每页 `layout` 选择 `L1`…`L23`。L15–L20、变体、`figures`、标注组件与正式输入必须提供的 `materials.papers` 详见 [原图与版式规则](evidence-and-composition.md)。可按材料逻辑自由组合、复制或重排页面，不必硬凑 14 页。

### 写作与表达规范（去除 AI 味与过度防御）

- **标题自然直接**：不要全篇机械使用 `四字词｜后半句` 公式；直接用自然学术短句概括当页核心问题、方法或证据。
- **正文完整可读**：`adaptive` 模式下卡片宽度充裕，请写完整、自然的学术分句，避免生硬的“四字口号堆砌”。
- **不过度防御**：专注呈现研究问题、方法、数据与实质结论，不要用多页篇幅反复说教“读法建议 / 本文没有做什么 / 免责声明”。

## 图表

- `line` / `bar`：`categories` 和各系列 `values` 等长。
- `scatter`：每系列提供 `xValues`、`values`。`adaptive` 模式下默认移除模板内置线性回归趋势线；若需要显示趋势线，在图表对象中显式设置 `"trendline": true`。
- `interval`：`lower` 和 `upper` 对应第一系列的上下界，长度与类别一致。
- `box`：各组输入原始 `values`，使用线性插值 Q1 / 中位数 / Q3，须线为最小值和最大值。
- `effects`：`labels` 为固定行数，`values` 为效应点，`errors[0].lower/upper` 为区间端点。
- 轴的 `xMin/xMax/yMin/yMax` 不得裁切数据或区间；`xMajor/yMajor` 必须大于 0。

## 文字、图标及插画

- `emphasis` 使用本主题强调色突出文本中的匹配词（每页最多 4 处）。
- 每页可加 `labels` 字典替换版式固定栏目标签，例如 `"labels": {"样地 × 工作环节": "位点 × 核心参数"}`。
- `icon` 字段在 `adaptive` 模式下支持任意学科图标名（`dna`, `pcr`, `table`, `chart`, `filter`, `warning`, `check`, `location`, `layers`, `workflow`, `document`, `compass`, `search`, `none`）；即使保留旧名，生成器也会结合卡片文本实时匹配最贴切的极简线框图标并避免同页重复。
- 单页配图：仅 `L2/L5/L7/L8/L14` 可设置 `"image": "images/figure1.png"`（PNG，路径相对于输入 JSON），等价于 `"images": {"main": "images/figure1.png"}`。保留原图宽高比，是否加双色调由 `duotone` 控制。
- `duotone`：页面级或文档级布尔值，控制插画是否套主题双色调。`adaptive` 模式默认 `false`（保留原图色彩），`legacy` 默认 `true`。
- 字号来源：权威值在 `assets/template-system.json` 的 `solid_typography`（内容页标题 42px、正文 21–25px、辅助与图表标注 ≥17px、页脚 14px、左右边距 32px），由 `scripts/fill_styles.py` 实现。L21–L23 使用单独的 `compact_typography`：标题36px、正文20–21px，几何与字号以批准原生模板为准，详见[紧凑版式](compact-layouts.md)。同文件的 `sizes` / `spacing` 为历史记录字段，脚本不读取。

### 配图插槽（v1.2.1）

| 版式 | 可用插槽 |
| --- | --- |
| L2、L5、L7、L8、L14 | `main` |
| L9 | `left_before`、`left_after`、`right_before`、`right_after_1`、`right_after_2`、`right_after_3`、`right_after_4` |
| L1、L3、L4、L6、L10、L11、L12、L13 | 无；选有配图区的版式或另拆一页 |

例如 L9 使用 `"images": {"left_before": "images/before.png", "left_after": "images/after.png"}`。每张图片只替换指定插槽；自适应模式移除本页未指定的默认位图。L9 不接受含义不明的单个 `image`，`image` 与 `images` 不能同时使用，未知插槽直接报错。图片内部内容属于位图，不能作为原生文字或数据编辑。

文档级 `duotone` 会传递到自定义图片，页面级显式值可覆盖；所有十套配色均遵循同一规则。科研实测图片通常保持 `duotone: false`。

### 使用真实论文或实验原图

原图是硬性验收项：提供的论文有相关图表，正式成稿必须直接裁取完整原图嵌入；即使有源数据也不默认重绘或重组。缺少原文或裁图无法核对时不通过。密集内容拆页或局部放大，保留坐标、单位、图例及解释所需上下文。真实图片通常显式设置页面 `duotone: false`，防止文档主题设置改变数据色彩。

在可见正文/现有标签中写简短图注；`sources` 写详细追溯记录，例如“main：某作者（年份），论文题目，图2，DOI；仅裁去外围空白”。自己的结果写真实文件名、分析版本或日期。`sources` 写入备注；`figures.caption/source` 为新图像版式自动创建可编辑图注，其余页可使用 `components`。图片槽位置、PNG 格式限制和图片内部不可编辑的边界仍按上表执行。

### 表格容量

自适应表格需至少一行表头及一行数据，所有行列数一致且非空。表头 21px、数据 20px 的最小行高与文本列宽要能装入 `table_regions` 指定区域；长文本、太多行列或单元格内换行会报错。生成器不截断、缩字号或自动分页；应由助手组织拆页，或用户在 PPT 中手动调整。

## 强制检查（字体、字号、位置对齐）

生成后必须运行：

```console
python scripts/audit.py OUTPUT.pptx --strict
```

确认退出码 0、`ok: true` 且 `warning_count: 0`，并在 PowerPoint 中导出预览图逐页目视复核。严格模式将全部警告视为失败，包括图表字体与字号。字体配置可显式传 `--font-profile portable|office`，默认自动识别；这检查文件声明，不代表目标电脑一定安装了字体。

PowerPoint 渲染报告必须 `quality_ok: true`；打开失败、文字溢出、表格碰撞、字体问题或请求的编辑探针失败均返回非零退出码。静态检查和实机规则都是有边界的检查，不能代替看图。历史 legacy 示例可能不满足新版严格标准；优先使用 `adaptive-solid.json` / `adaptive-light.json`。

## 外部素材与动画后处理

联网素材与解释性动画使用独立清单/配置，不扩展本文件的静态输入schema。可选Windows PowerPoint处理、离线HTML及媒体核验见 [媒体规则](media-and-animation.md)。原图优先、字体字号、图片比例与图注规则继续适用。

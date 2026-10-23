# 离线素材库与原生形状

辅助图优先使用已从网上取得并保留许可的素材。先读用户原资料，论文图表、真实照片、点位图与实验结果仍优先；再查询随包素材库。相关素材不足时继续联网搜索，记录查询、选用ID及未采用候选的具体原因，不能未搜索就直接使用自画或生成图。缓存中的在线原件已经满足“优先网上素材”，不必重复下载同一文件。

## 查询与选择

离线预览为 `assets/media-library/gallery.html`。机器目录为 `catalog.json`，按类别、风格、关键词、来源与原生编辑状态选择，优先同页同系列。`themes.json` 中生态监测研究主题是可选内容索引，不改变通用模板的默认学科。

```console
python scripts/assets.py search 相机 --theme camera-monitoring --native-only
python scripts/assets.py search --theme habitat-sampling
python scripts/assets.py search --theme molecular-workflow
python scripts/assets.py search --theme identity-qc
```

生态监测主题包括相机与活动记录、森林生境与采样、非损伤采样与分子实验、微卫星分型与个体识别质控。通用鹿图标只标“鹿类示意”，不得当作特定物种外形鉴定图。真实物种照片、实际采样地点和原始峰图由使用者提供，不把私人资料固定到公开素材包。

## 插入原生形状

普通 `generate.py` 仍按既有模板生成静态PPT；完成正文与证据图安排后，可运行以下独立后处理，不把这些配置字段混入模板JSON：

```console
python scripts/assets.py insert --source examples/assets/ecology-showcase-base.pptx --config examples/assets/ecology-showcase.json --output my-assets.pptx --report my-assets-insertion.json
```

配置采用画布坐标，默认1280×720，必须与实际PPT比例一致。`box` 为 `[左,上,宽,高]`，按原始比例居中容纳；可用 `target` 替换一个已预留的普通形状插槽，二者不混用。优先替换预留位置，避免后加素材遮住文字、数据图或原图。

```json
{"canvas":[1280,720],"placements":[
  {"slide":1,"asset":"noto/emoji_u1f333","box":[80,200,180,180],"name":"forest"},
  {"slide":2,"asset":"lucide/camera","target":"camera-slot","name":"camera","color":"173D67"}
]}
```

默认保留原始颜色，只有普通说明图标在需要时显式指定单色 `color`。线宽随插入尺寸等比例换算，保持SVG轮廓比例。结果为 `p:grpSp` 原生组合及 `p:sp` 子形状，可在PowerPoint选择组内对象、改色、移动、取消组合及调整节点；复杂曲线通常仍是一个自由曲线对象，不保证自动拆成有科学语义的部件。来源、许可及修改记录保留在组合的替代文字和已有备注中。

脚本只用Python标准库，不联网、不自动启动Office，不覆盖源稿或已有输出。未知ID、越界、缺失插槽、哈希异常、没有合格缓存的SVG在写入前报错，不自动改成图片后声称可编辑。

## 编辑验收边界

逐项状态以 `catalog.json` 的 `native` 为准。有缓存且 `edit_probe: passed` 才属于本批已测原生素材；`source_only` 保留SVG原件，需转成清晰PNG后按普通配图流程插入，不宣称内部可编辑。原件不得为了通过转换被擅自删掉渐变、裁切、滤镜或文字。

本批对照浏览器SVG与PowerPoint实际渲染，并检查组内改色、子对象移动、组合移动/缩放保存重开。自动图像筛选是失真预警，不等于逐项人工目检；重点样板另作目检。证据见 [素材验收](asset-validation-v1.7.1.json)。未验证WPS、macOS、网页版Office；不能把Windows验收外推为跨软件一致。

若后续添加新SVG，维护者可在独立构建环境安装 `svgelements==1.9.6`，运行 `compile_svg_asset.py`。此依赖只用于编译，不是使用现有库的依赖。编译成功仍是候选，须另做显示与编辑验证；遇到复杂裁切、渐变、滤镜、偶奇填充等不支持特性就保留原件后备，不绕过检查。

## 源项目与许可

图标与配色不承载研究结论。第三方素材各自遵循 ISC、MIT、CC0、CC BY 或 Apache 2.0，具体作者、固定来源、许可全文和SHA256均随包；本项目MIT不覆盖它们。带CC BY的插图在页面邻近图注中署名，不能只靠备注满足全部署名需求。

`export_project.py` 仅重建静态模板稿，不会自动重放素材后处理。交付带素材的源项目时，另附选用的原始SVG、对应缓存、许可、placements配置与插入脚本，并在静态重建后再次执行插入；要交付完整skill时直接使用本版完整ZIP。不要声称只交旧的静态源项目就能复现新增素材。

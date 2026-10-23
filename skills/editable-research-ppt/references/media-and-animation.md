# 联网素材与解释性动画

制作涉及图标、辅助插图、动画或交互演示时读取。本规则不改变论文原图硬指标。

## 素材选择与编辑边界

1. 先查用户资料的原图，再用 `scripts/assets.py search` 查询随包在线素材缓存，记录选用ID；相关素材不足再联网找。查询、插入和生态监测可选主题见 [离线素材库](asset-library.md)。缓存中的在线来源不是自绘素材，不必重复下载；未匹配到时不能跳过联网检索而直接用自绘图。美化素材优先级：**网上可编辑矢量 → 网上高清图片 → 自行绘制或 AI 生成**。相关性、准确性、清晰度与可用许可先于装饰；不为遵循优先级使用不相关素材。找不到适用素材或无法联网时说明原因，再选后备方式。
2. 优先同一素材库/同一视觉系列，匹配线条、比例和精细程度。科学图表不随主题重新配色；普通图标允许协调主题色。图标服务于识别与解释，不能挤占证据图和正文。
3. SVG是优先来源格式，不是逐项可编辑的证明。能可靠转换的转为PowerPoint原生形状/组合，核对轮廓、颜色、透明度及裁切，再测试组内改色、移动、保存重开。复杂或转换失真的矢量保留独立图片；PNG/JPG仅承诺移动、裁剪、缩放和替换。
4. 保留原始素材、源网址、作者、许可URL、必要署名、下载文件SHA256和修改说明。页面按许可署名；开源分发须确认再分发条件，并在第三方声明中列出。代码的MIT许可不覆盖第三方素材。来源或许可不清楚的素材不进入公开发布包。
5. 网络插图只能辅助解释，不能替代资料中已有的完整论文图表，也不能冒充实测结果。完整论文图仍按 [原图规则](evidence-and-composition.md) 裁取、核对、直接嵌入。

## 按讲解需要选择动画

- 机制链、反馈、时序、扩散或参数变化等静态图难以解释时，考虑动画。每段说明“改变什么、影响哪个过程、看什么结果”；没有解释收益就保留静态图，不要求每页或每份汇报必须有动画。
- 简单分支、顺序和强调优先**原生形状＋PowerPoint动画**，保留文字、图形和时间线编辑。默认由点击推进，讲解者可控制节奏。
- 复杂连续运动可用**SVG/HTML源码制作 → 浏览器实际播放检查 → 渲染MP4 → 内嵌PPT**；同时交付源SVG/HTML和静态关键帧。视频区域内部不能在PPT逐项编辑，需改源文件再渲染；页面标题、解释和标注保持原生文本。
- 普通SVG插入不是网页动画运行环境，不能承诺保留SMIL/CSS/JavaScript动画。HTML交互可作为离线附件，支持暂停、回退、重播及必要的参数控制；HTML元素不自动变成PPT形状。需要在PPT内运行HTML时另做内容加载项兼容性验证，默认不依赖加载项或外部服务。
- 展示机制与实测证据分开。示意的尺寸、速度、粒子数量和循环不是研究数值或生理时间；讲解步骤不是实验发生顺序。不要以运动暗示未经支持的因果关系，原证据图保持静态完整，新增解释层另做。

## 实现入口与实际能力

`generate.py`仍是仅依赖Python标准库的**静态PPTX生成器**，普通图片输入仍为PNG；它不会联网搜索、自动转换任意SVG或执行网页动画。联网检索/转换/HTML制作由使用技能的Agent调用实际可用工具完成，并如实报告没有的能力。不要把下面的后处理字段塞入原JSON模板输入。

Windows桌面PowerPoint可用时，在已有PPT上调用可选后处理工具：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/add_media.ps1 -Source talk.pptx -Config effects.json -Output talk-animated.pptx
```

配置路径相对于配置文件目录，坐标以PPT实际point为单位（不能直接套用1280px坐标）。源稿和输出必须不同，输出已存在则失败；不覆盖用户原稿。先检查对象名称，优先按名称定位，避免按易变的对象顺序猜测。

```json
{
  "steps": [
    {"slide": 1, "shapes": ["process-node", "process-caption"], "name": "step-one", "duration": 0.65}
  ],
  "videos": [
    {"slide": 2, "path": "media/demo.mp4", "name": "concept-demo", "box": [24, 110, 540, 304], "autoplay": true, "loop": false}
  ]
}
```

`steps`按数组顺序添加点击淡入，可包含一组对象；已有动画的页面拒绝新增步骤，避免悄悄破坏时间线。视频完整嵌入而非路径链接。该工具不生成动画视频、不安装PowerPoint、不改变全局Office设置。缺Windows/PowerPoint时保留静态PPT并交付HTML/视频附件，标明未在PPT内验证。

## 溯源记录与交付检查

为本次使用的外部素材和动画建立 `media-manifest.json`，路径相对于清单。通用示例见 [媒体示例](../examples/media/README.md)。每项声明 `id`、`path`、`sha256`、`origin`（online/original/user）、`role`（illustration/concept_animation/evidence）、`representation`（image/native_shapes/video）、`editable`（native/source/replace_only）、`changes`、`placements`（从1开始的页号）。在线项另需作者、HTTP(S)来源URL、许可及许可URL；动画项另需 `source_path`、`source_sha256`、`static_fallback`、`fallback_sha256`、`explanation`、`schematic`。SVG/HTML源文件和静态后备也要随包可访问。

```console
python scripts/audit_media.py --manifest media-manifest.json --pptx talk-animated.pptx
```

核验器检查记录和文件哈希、路径范围、动画源/静态后备、声明页是否含相同视频字节以及是否存在外链视频。它**不证明**网页许可真实有效、SVG几何转换正确、视频一定能解码、图形与论文结论一致或所有素材均已登记；这些仍需人工核对。

交付顺序：原图证据核对 → 静态字体/字号/边距/碰撞检查 → 实际放映（点击顺序、暂停/重播、媒体播放）→ 改字/改动画设置并保存重开 → 离线/路径搬迁检查。视频要查实际渲染的不同时间点，不能把静态截图当播放证据；HTML要在浏览器操作控件，并检查资源不依赖临时目录。保留静态备用图，导出PDF后仍可理解。只声明实际测试过的软件/平台。

## 参考资料

- [Microsoft：SVG编辑与转形状](https://support.microsoft.com/en-us/office/graphics-visuals/edit-svg-images-in-microsoft-365)
- [Microsoft：原生对象动画](https://support.microsoft.com/en-us/powerpoint/training/animate-text-or-objects)
- [Microsoft：内嵌视频](https://support.microsoft.com/en-us/powerpoint/insert-and-play-a-video-file-from-your-computer)
- [Microsoft：HTML内容加载项](https://learn.microsoft.com/en-us/office/dev/add-ins/powerpoint/powerpoint-add-ins)

维护者可在有PowerPoint的Windows上运行 `tests/test_media_powerpoint.ps1 -WorkDir <新的临时目录>`，验证不覆盖、异常输入、点击序列和保存重开；导出视频仍需抽帧目检。此测试不进入无Office的便携CI。

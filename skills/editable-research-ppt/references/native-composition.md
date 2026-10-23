# 内容驱动的原生排版变体

当完整论文需要推导链、宽幅原图和不等宽文字区，L15–L18的预设槽位不足时，使用`composition`；普通内容优先用现有版式。它是原生排版变体，不另算一套模板，不把整页渲染图塞进PPT。可运行示例见[输入](../assets/examples/native-composition.json)。

## 输入与编辑边界

页面使用`layout: L15|L16|L17|L18`、`visual_mode: adaptive`，`composition`为1–500个节点的有序数组，按顺序叠放。全部坐标为1280×720画布上的像素，`box: [x,y,w,h]`必须有限、正宽高且不越界。保持32px左右留白、42px主标题、21–25px正文、≥17px辅助文字；校验接受13–80px是技术边界，不是缩字排版许可。

| kind | 必要字段 | 可选字段 |
| --- | --- | --- |
| text | `text`, `box` | `name`, `size`（默认22）, `color`, `bold`, `align`（l/ctr/r） |
| shape | `box` | `name`, `fill`, `stroke`, `prst`（默认rect） |
| image | `figure_index`, `box` | `name`, `slot` |

颜色可写六位RGB（不含#）、null，或`primary/secondary/accent/paper/tint`主题令牌。主题令牌跟随所选配色；指定RGB保留其含义。原图像素永不随主题变色。shape支持rect、roundRect、ellipse、rightArrow、downArrow、upArrow、chevron、triangle、diamond、hexagon、parallelogram。当前不提供此模式的原生图表、表格、富文本或任意SVG路径节点；需要这些对象时使用原有相应版式，不以散点假装数据图。

页面`title`必须作为一个完整原生text节点显示。此模式自行排布标题、图注、页脚与导航，不自动补模板横幅，`title_translation`也应由独立text节点承载；不要同时依赖自动标题字段。

图片引用同页`figures`中的索引，保留原始比例、字节与颜色，每幅图都必须实际出现。对应`caption`、`source`各须有内容完全一致的原生text节点，位置由作者紧邻图边安排。完整论文原图的材料清单、PDF页、裁图记录和哈希硬指标照常执行；不能用局部图或重新绘制的图片替代。此模式暂不支持局部放大插槽，放大需求改用标准L17或另加一页完整大图。

旧私有实验字段`experiment_scene`不再静默忽略：先人工核对其节点符合本规范，再明确迁移为`composition`。生成后仍运行严格审计、实际渲染与编辑重开；坐标合法不代表视觉、科研内容或图片清晰度通过。

[可编辑PPT样页](../examples/native-composition.pptx) · [实际PowerPoint预览](../examples/previews/native-composition/slide-01.png)。使用合成测试资料，不是真实研究。

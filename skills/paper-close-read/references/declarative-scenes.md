# 通用演示：先设计解释，再选择绘制方式

使用者只需要给文献与阅读目标。题材匹配、演示设计、实现和验收由执行者完成。既有scene是可复用例子，不是支持学科的白名单；不能答复“新主题需要用户开发场景”。

## 先把难点与表达对应

在guide.visual_plan填写主要理解卡点。每项含：
- id：本篇唯一；question：实际卡点；refs：原文块ID。
- mode：motion / figure / static / text；reason：为何采用这种表达；observe：读者应看见什么关系或变化。
- motion项另有mechanism：既有motion-ID；kind：mechanism或argument。场景在mechanisms中定义，并在对应walkthrough.motions就地插入。

例如：

```json
[{"id":"vp-change","question":"为什么移动同一个对象会改变观察结果？","refs":["原文ID"],"mode":"motion","kind":"mechanism","mechanism":"motion-change","reason":"需要比较同一对象在两个位置下的结果","observe":"只变位置，其他条件保持；观察结果随之变化"}]
```

按难点选择表达，不设固定动画数；静态对照清楚就不强动画。同一动图在正文/导读两处出现只算一个解释。计划没有覆盖主要难点，或把几个不同过程都塞进一个概括框图，要回到本篇重新设计。校验仅验证声明与映射，完整性由内容审读判断。

## scene: process：不改代码即可编排新过程

900×440坐标画布。visual包含description（对象含义、变化条件、教学数值与原文结果关系）与elements。每个元素：id、type、meaning、props；需要变化时加frames。

- type：circle / rect / line / polyline / text。
- props：circle用x/y/r；rect用x/y/w/h；line用x/y/x2/y2；polyline用points坐标数组；text用x/y/text。
- 可选fill/stroke（六位十六进制颜色或none）、opacity（0–1）、line_width（0–20）、font_size（10–48）、align（left/center/right）。text可用换行，需检查可读性。
- frames：按at从小到大排列，at在0–1之间、不重复；其余键覆盖props。数值与同长度points在关键帧间线性插值；文字和颜色到达关键帧时切换。需要停顿则在不同时间写入相同值，再移动到下一状态。
- 整体播放器仍提供播放/暂停、步骤、拖动、速度。画面关键时点应与stages分段相配；不要一边说第三步、一边还展示第一步。

```json
{"id":"motion-change","scene":"process","anchor":"原文ID","refs":["原文ID"],"title":"对象穿过边界时，记录怎样变","question":"为什么存在却没有记录？","stages":["蓝点在可记录区内","对象移向边界","对象来到记录区外"],"note":"位置和区域是教学示意，不是论文实测轨迹。","visual":{"description":"边框是记录区；蓝点为同一对象；只改变对象位置。","elements":[{"id":"region","type":"rect","meaning":"可记录范围","props":{"x":60,"y":90,"w":360,"h":270,"fill":"#edf3ed","stroke":"#52836b"}},{"id":"object","type":"circle","meaning":"随时间移动的同一对象","props":{"x":150,"y":220,"r":12,"fill":"#568ba1","stroke":"none"},"frames":[{"at":0.33,"x":150},{"at":0.66,"x":420},{"at":1,"x":620}]},{"id":"key","type":"text","meaning":"对象与记录的区别","props":{"x":470,"y":110,"text":"存在和被记录是两件事","font_size":20,"fill":"#454039"}}]}}
```

这些形状可组成流程中的样品/人/群体、空间移动、遮挡与覆盖、响应曲线、累计量条、状态开关、情景地图和信息流。曲线points及数值标签由作者基于论文或明确教学设定提供；本引擎不会自动拟合模型或验证数值。没有任意JS、eval、HTML、联网素材或表达式执行口。文本需要解释清楚，画面也要真正呈现变化，不能用此场景包装一串淡入文字。

复杂过程可以组合多个演示，各自只讲一个需要理解的关系。确需特殊图形时由执行者扩展通用绘制并验证；这属于制作流程，不是使用者安装或阅读前的开发工作。

## 验收要查解释是否成立

用--require-visual-plan构建新完整稿。然后对照论文与主线逐项审读计划，在实际浏览器查看首中末帧、全部条件、暂停/步骤/拖动；检查图文同步、箭头、变量方向、单位、基准与证据强度。过程示意、数据曲线重画、情景投影分别标清。内容问题修JSON，共性问题修通用绘制后重建，不补最终HTML。允许无动图的文章，但须有与内容相符的表达选择，不能靠固定配额或自动计数过关。

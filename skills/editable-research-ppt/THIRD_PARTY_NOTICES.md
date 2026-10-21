# 来源与许可说明

## 本项目

代码、字段配置、文档及由本项目制作的模板结构按根目录 MIT LICENSE 提供，版权行使用 `editable-research-ppt contributors`。MIT 允许使用、修改和商业再分发，须保留许可与版权声明；不构成商标或他人权利授权。

## 字体

随包的 Noto Sans CJK SC 和 Noto Serif CJK SC（Regular / Bold）来自 [notofonts/noto-cjk](https://github.com/notofonts/noto-cjk)，按 SIL Open Font License 1.1 分发，**不改为 MIT**。字体未修改。完整许可证在 `fonts/NotoSans-LICENSE.txt` 和 `fonts/NotoSerif-LICENSE.txt`，含上游版权信息。精确下载地址、固定提交及 SHA-256 在 `fonts/sources.json`。

随包不含微软雅黑、宋体或其他商业字体。字体文件不是 PPT 内嵌字体；接收方需自行安装。

## 插画与设计参考

`assets/templates/library.pptx` 中两份独立位图为本项目制作流程中 AI 生成的生态插画（山林景观、森林斑块），用于演示模板；重复图片引用会复用同一媒体对象。不是实验照片、遥感影像或研究证据。允许随模板使用与替换；不对 AI 图像的独占权或各地区可版权性作保证。

设计曾参考用户提供的科研汇报截图，以及 Slidesgo、SlideModel、PresentationGO、iSlide 的通用版式分类；本包仅分发本项目重建的形状结构与生成素材，不分发这些网站的模板文件或截图，也不表示获得其背书。用户日后加入的论文图片、机构标识、照片及数据，其权限需按实际来源处理。

## 运行依赖

静态生成与Python检查脚本仅使用 Python 标准库；不随包复制 Python 本身。Windows PowerPoint 是可选的本地预览、编辑验证和动画/媒体后处理工具，须使用者自行取得。未分发原制作工具的私有运行时或其库代码。

## v1.3 合成测试资料

assets/examples/figures/synthetic-study.pdf 及其 PNG 裁图为本项目生成的合成测试资料，采用本项目 MIT 许可；不是真实发表论文，不包含第三方论文图片。PDF 裁图工具可选使用 PyMuPDF，该依赖未随本包分发，遵循其自身许可证。

## v1.4 动画样板

`examples/media/` 的几何SVG、视频、静态帧、HTML、PPT结构及配置为本项目原创合成教学素材，采用本项目MIT许可；不是论文原图或实测数据。未把此前私人文献样稿或第三方医学插图加入开源包。用户联网取得的素材须另行记录来源、许可、修改和必要署名，不能自动套用本项目MIT。可选脚本 `add_media.ps1` 依赖用户已安装的Windows桌面PowerPoint，不分发Office软件。

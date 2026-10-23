# 可搬迁源项目

需要在另一台电脑重新生成PPT时使用；仅给收件人编辑现成PPT，直接交付PPTX即可。制作前把选用的PNG和PDF收集到一个源目录内，并核对论文原图清单。不要把无素材的JSON称为完整源项目。

```console
python scripts/export_project.py --input /project/input.json --output-directory /handoff/new-source-project
python /handoff/new-source-project/rebuild.py --output /handoff/rebuilt.pptx
```

输入相对路径默认以JSON所在目录为准，需要时指定`--base-directory`。只复制明确引用的论文PDF、普通PNG、figures和illustrations，不复制整个原素材文件夹；路径必须位于所选源目录内部。输出目录必须不存在。脚本把已知路径字段转为相对路径，并附本次最小生成运行时、许可证与哈希清单；不会扫描或改写正文、备注中的文字。

重建需要Python≥3.10，静态生成只用标准库，不依赖另一台电脑已安装的skill。使用冻结运行时可避免以后skill升级改变这份项目的布局；编辑维护时仍以源输入为入口，PPT里手改的内容不会自动写回。默认全部文件先验哈希；有意改过`input.json`后使用`--allow-input-edits`，素材与程序仍须匹配原快照。输出必须为新文件，避免覆盖收件人的手改稿。

项目清单记录字体配置，但不打包字体；收件人需另装对应字体，再在目标软件看图、编辑保存重开。可以重建不证明跨平台显示或动画一致。当前源项目只覆盖静态生成，不包含另行添加的动画、视频及SVG/HTML后处理；这些按媒体交付流程另附。

此工具用于本地源项目移交，**包括选用的PDF原文**。论文、未发表结果、备注和图片可能不适合公开；源项目不会自动上传，也不提供再分发许可或隐私合规结论。对外公开前单独确认。普通展示交付包`prepare_handoff.py`仍默认不复制原论文。

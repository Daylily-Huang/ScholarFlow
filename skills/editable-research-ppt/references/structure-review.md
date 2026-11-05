# 逐页结构与交付检查（v1.9）

正式输入每页填写 `task` 和 `structure`。`task` 说明听众要从本页理解什么，`structure` 取以下一种：`cover` 封面、`agenda` 目录、`section` 章节、`closing` 结束、`image_led` 大图、`comparison` 对照、`process` 流程、`cards` 卡片、`data` 表格或数据、`chart` 图表、`statement` 文字论点。缺失或只填写部分页会阻止正式生成。旧输入可用 `--draft` 生成待审稿。`structure_check: advisory` 只供无内容计划的合成演示，正式输入使用即报错。

## 版式与节奏

L5/L6/L7/L14 固定对应封面、目录、章节和结束页。L19 是时间线，L20 是数据矩阵。L21 两个变体声明 `chart`，L22 三个变体声明 `data`，L23 声明 `process`。L15–L18 及支持 `original_figure` 的旧版式可用原图结构，详见 [输入约定](input-and-templates.md)。不确定时先跑输入预检。

连续三页或以上相同结构会被拦截。生成前按声明检查，生成后再独立按 PPT 展示顺序和实际页面对象检查。更换模板编号、调换标签或改色都不会改变实测分类。只有能对应到成品中已生成的导航页才不计入正文连排。实测识别关注大图面积、原生表／图表、成组对象、流程连接和对齐的单元格。混合布局的主结构属于几何估计，需看实际缩略图确认。

大图声明至少有一张覆盖画布 25% 的可见图片。图表声明需要可见原生图表。数据页可用原生表／图表或对齐的形状矩阵，包括 L20 合法的表头加一行数据。流程声明须有可见的流程连接或时间泳道。对照与卡片是混合结构，检查所需的图片或文本分组；实测分类单独计算连排，不以这些兼容条件取代实测。

## 合理连排

确需连排时，在该组至少一页的 `rhythm_exception` 写明原因。生成结果会标记 `review_required`。复核者看实际缩略图并确认每个报告中的连排区间后，提交独立的 JSON，再用 `prepare_handoff.py --rhythm-review REVIEW.json`。输入格式如下，字段值以实际报告为准。

```json
{
  "pptx_sha256": "最终 PPTX 的实际 SHA256",
  "reviewer": "实际复核者",
  "note": "看过哪些页以及允许连排的依据",
  "accepted_runs": [
    {"start": 4, "end": 6, "structure": "chart", "reason": "同一实验的三个时间点共用坐标尺度"}
  ]
}
```

`accepted_runs` 必须覆盖 `structure_audit.py --pptx OUTPUT.pptx` 中列出的所有区间，顺序、结构和理由须与报告一致。理由字段只允许进入复核。脚本能验证复核记录与成品绑定，复核者是否看图及判断是否合理仍由执行者负责。

## 正式交付与改稿

生成器先验声明，再对将保存的 PPTX 内容实测。拒绝时不覆盖已有文件。正式交付会重新检查报告和全部 `ppt/` 部件指纹，过期报告会被拒绝。`structure-validation.json` 并列保存逐页计划、成品结构、连排与复核结果。待审包也会实测当前文件并注明状态。

手改或旧稿按 [内容复核](content-review.md) 为实际 PPT 更新内容计划与哈希。先用 `structure_audit.py --input UPDATED.json --pptx EDITED.pptx` 查看当前几何结果，再用 `prepare_handoff.py --content-input UPDATED.json` 重新核验两道检查。若实测有连排，仍需同文件对应的 `--rhythm-review`。这个过程读取现有 PPTX，适用于保留 PowerPoint 手改内容。内容准确性、原图来源与实机视觉继续按各自的流程核验。

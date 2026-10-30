# 原图不能丢：从原文清单到讲解与 PDF

## 先盘点原文，而不是只数提取后的图片

在阅读资料中独立建立原文图清单。PDF **逐页看**，列主文 Fig.1、Fig.2……及 A/B/C 等子图、图注、实际文件页、图像公式；注意图与图注跨页、组合图、嵌在段落里的小图、附录图。出版商 JATS 可独立枚举 `<fig>`、图像公式及其 graphics，作为漏图检查来源。不要把 PDF 内嵌图像对象数当图数：一幅结果图可能由多个对象组成，矢量图也可能没有位图对象。

默认完整稿保留所提供正文的全部原图；外部补充材料另列范围，实际拿到并核对后才称覆盖。论文确实无图也记录无图及检查范围，不凭提取结果是零张就认定原文无图。

可以先生成待核清单：

```text
python scripts/figure_inventory.py fulltext.json original.xml figure-inventory-draft.json --kind jats
python scripts/figure_inventory.py fulltext.json original.pdf figure-inventory-draft.json --kind pdf
```

草稿不覆盖已有清单或原件。JATS 自动列原文图/图像公式并尝试匹配图片，**不自动勾选核验**；PDF 草稿只绑定原文件，页数与图清单由实际阅读填写，不伪装成自动识图。完成后把记录放入 `fulltext.figure_inventory`。原提取文本、图像及原件只读，修订保留记录。

## 数据契约

```json
{
  "source": {"kind":"pdf", "file":"original.pdf", "sha256":"原文件64位小写SHA256", "page_count":6},
  "status":"pending",
  "review_note":"实际核对范围、方式；完成后才写 verified",
  "checked_pages":[1,2],
  "figures":[{
    "id":"fig1", "label":"Figure 1", "kind":"figure", "pages":[2],
    "panels":["A","B"], "checked_panels":["A"],
    "blocks":["对应的原图来源块ID"],
    "caption_checked":false, "verified":false,
    "verification_note":"具体看了什么；缺什么",
    "key_result":true
  }],
  "asset_sha256":{"原图来源块ID":"该图片文件的SHA256"}
}
```

- `source.kind` 可为 `jats`，此时无需 PDF 页数字段；图 `id` 使用 XML 的 fig/公式 ID，无 ID 时沿草稿生成的稳定序号。JATS 版清单仍需核对整图、图注和子图。原 PDF 也核对过时可加 `pdf_review:{file,sha256,page_count,checked_pages}`，与实际页码及核对记录一起保存。清单完成不意味着正文文字已全部核对。
- 一幅组合图用一张完整图片时 `blocks` 只有一个，但仍列全部子图；分成多个原始 graphic 时映射所有图片，不能只保留第一幅。没有字母编号的原图 `panels:[]`，不编造 A/B。`kind:equation` 表示图像公式；它不必强插入结果讲解。
- `verified` 只在实际看过整图、图注、坐标、单位、图例和误差表示后设置；记录子图核对及图片哈希。`status:verified` 要求清单全部完成、覆盖所有来源图片块；PDF 还要求所有页完成检查。
- `key_result:true` 是本篇主线依赖的关键原图，必须在10分钟对应讲解中就地展示。其他原图仍在逐段精读的原位置保留，不因未选入导读而删除。

构建器会检查清单覆盖、未知/重复映射、未核子图、JATS 原文图号和 graphic 数量、来源与图片哈希，以及关键图是否配置就地展示。它不能仅凭这些声明判断裁切是否完整、图片是否清楚、人工记录是否真实；这些仍要看原页。SVG/其他暂不支持的图片格式需从来源获得合适的清晰栅格版并记转换，不得静默略过。

## 与讲解一起看

在 `guide.story.walkthrough[].figures` 配置：

```json
[{"ref":"原图来源块ID", "after":0,
  "focus":"先看哪个轴、哪一组、哪个子图或哪条曲线",
  "explanation":"具体对照得到什么，这一步如何支持或限定本节判断"}]
```

`after` 是该节 `paragraphs` 从0开始的索引；图直接放在那段讲解后。把原图 ID 也放入该节 `refs`。模板复用**同一图片文件**，保留完整英文图注，图下中文带读与原图注明确分开，并可原地放大、返回逐段位置。不要只写“见图2”要求跳转，也不要用教学动画替代实验结果图。动图负责解释过程，原图负责呈现论文证据；二者可相邻。

逐段精读保持原图、图注与前后文的源顺序，稳定 ID 不变；可先展示完整图，再另加子图细看，不能裁掉误差棒、图例或“效果不显著”的子图。历史、文学原文有手稿、版画或材料照片时同样保留，讲读按材料性质写，不强行解释为实验结果。

## 完整稿与验收

新完整稿使用：

```text
python scripts/validate_content.py fulltext.json translations.json guide.json --source source.md --asset-root reading-data --require-figure-audit
python scripts/build_html.py fulltext.json translations.json guide.json reader.html --source source.md --asset-root reading-data --require-figure-audit
```

旧资料仍兼容重建，但无清单时页末只显示“原图完整性待核对”，不声称已证实原图齐全；`--allow-incomplete` 不能绕过严格图核验。独立来源文件需保留于资料根目录内以复核哈希，不因此授权对外分发原 PDF。缺材料时保留实际缺项和范围，不能将状态改成 verified 来消除错误。

最后实际打开浏览器，按清单逐图检查逐段页与导读：图片能加载、放大看清子图、原图字节与清单一致、图注完整、上下文位置正确、讲解确实说明该图。导出 PDF 后再次核对全部原图/图像公式数和图注，渲染看组合图是否整幅保留，不能只数 HTML 的 img 标签便结束。PDF 导出正文原图，不重复复制导读里的同图。复现检查随 `scripts/check_reader_pdf_browser.py` 进入 CI，视觉与释义核对保留人工/模型实际审读记录。


分离图注：Markdown提取将图片与英文图注分为两个来源块时，可在图片的 `source.caption_ref` 填入实际图注段落ID。保留两块raw、ID与源顺序；逐段原图链接至原位图注，10分钟导读复用该段完整英文图注。未知、空或非段落引用阻断构建。

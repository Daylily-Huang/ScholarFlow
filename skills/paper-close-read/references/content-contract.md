# 内容与输入契约（schema v2）

解析器输出 `fulltext.json` 的 `sections[].items[]`：`t/id/raw/source`；p 另有 en，eq 另有 latex，figure 有 src/caption。raw 是不可改的提取文本；每个来源含 file、line_start/end（闭区间、从 1 开始）、pdf_page、printed_page、status。PDF 字形修正留独立 corrections，不能回写 raw。编号来自内容指纹和重复次数，同段未变时不会因别段插入而重编号。

修改提取文本后须重新解析和核对；不要手工改 SHA 来绕过核验。标题层级保留，HTML 采用顺序小节导航；复杂排版/列表/图注仍需人工对照。

## translations.json

JSON 数组，每个段落 `p` 必须有且仅有一个记录；此外允许为核心独立公式 `eq` 和主要结果表 `table` 添加可选解释记录（仅填 `id`、必填 `note`，按需填 `keys`/`trap`/`terms`，无需填 `zh` 与 `vocabulary`），用于就地渲染「公式白话拆解」与「读表抓手」。缺失必填段落、重复 ID 或未知 ID 默认失败：

```json
[
  {
    "id": "从解析结果复制",
    "role": "body",
    "zh": "逐句对应译文；保留限定、否定、单位与不确定性",
    "note": "把读者会卡住的具体问题讲通；长度随内容需要",
    "keys": ["提取实际推理关系；条数随内容需要"],
    "trap": "具体易错点；没有则空字符串",
    "terms": [{"en": "原文术语", "zh": "全文统一译名"}],
    "vocabulary": [{"en": "段内实际出现的词或连续词组", "zh": "此处语境的中文释义"}]
  }
]
```

所有文本字段是**纯文本**，行内公式可用 $...$；不写 HTML 标签。正文不存在的补充背景标「补充解释」，不能伪装成翻译。

## guide.json（新稿默认叙事版）

以下是字段说明示例，文字和 refs 必须替换为本篇内容。先写论证，再装入结构。

```json
{
  "scope": "本次材料与核验范围",
  "story": {
    "overview": {
      "title": "本篇具体要解决的问题",
      "lead": "直接回答问题，并点明核心解法",
      "format": "research-map",
      "research_map": [
        {"step":"background", "text":"具体背景", "refs":["来源块ID"]},
        {"step":"gap", "text":"已有研究/解释做到什么，还缺什么", "refs":["来源块ID"]},
        {"step":"question", "text":"本文明确要回答什么", "refs":["来源块ID"]},
        {"step":"method", "text":"什么对象/材料，怎样操作、比较或论证", "refs":["来源块ID"]},
        {"step":"findings", "text":"主要发现；理论/历史/文学可用title调整读者标签", "refs":["来源块ID"]},
        {"step":"conclusion", "text":"发现如何回答问题，带来何种理解", "refs":["来源块ID"]}
      ],
      "takeaway": "读完应理解的关系及其适用条件",
      "refs": ["真实来源块ID"]
    },
    "walkthrough": [{
      "title": "这一环节解决什么问题",
      "bridge": "上一环节留下的具体疑问",
      "paragraphs": ["用对象、操作、比较和现象讲清过程，补上必要中间步骤"],
      "connection": "这一步获得了什么，为什么下一步还必要；末节回答开头问题",
      "refs": ["真实来源块ID"],
      "motions": []
    }]
  },
  "mechanisms": [],
  "further_reading": []
}
```

新稿必须提供 story，不再填旧式问答清单凑导读。overview 和 walkthrough 均需原文 refs。新入门页用format=research-map，research_map恰好包含上述六个step且顺序固定；每步有非空text和有效refs，可选title替换面向读者的标题（如“材料发现”“论证所得”），不改变step含义。无需再填overview.paragraphs/chain；walkthrough.paragraphs仍为非空文本数组。metrics 可选，label/value/meaning 都是字符串。motions 中每项为 {"id":"motion-场景ID"}；同一章节不重复插入同一场景，不同章节可以复用。table 可选，head/rows 单元格为字符串，列数一致。

旧稿仅在明确 `"format":"legacy"` 时允许没有 story；旧字段为 question、answer、why、claims、limits，自测 checks 可选。这是旧文件重建入口，不用于新文献。claims/checks 若提供仍校验 refs；旧 animations 帧清单只由兼容版渲染，新叙事版使用 mechanisms + walkthrough.motions。不要填写一个当前路线不会显示的字段就宣称功能已交付。

需要直观展示抽象概念或作用过程时，先规划重难点，再添加`mechanisms`，格式见[动图规划](mechanism-design.md)。机制动图的`anchor`确定正文插入位置，`refs`绑定对应原文，`stages`提供与画面同步的逐步解释；不是用任意文字套一个无关场景。


role 默认 body。body 提供非空 note 和 keys，长短与条数由实际解释需要决定。校验非空只用于发现漏项，不评价教学质量。metadata、reference、supporting、label 用于元信息、书目、支持材料目录和纯编号标签，简列原文/译文及定位，不生成空白话/逻辑区；不可把困难正文标成辅助信息来绕过要求。全部原始块仍参与覆盖校验。

## 核心文献推荐：guide.further_reading

数组顺序即建议阅读顺序；每项含 citation（核实后的作者、年份、题名、期刊）、role（与本文关系）、priority（先读/按问题选读）、reason（具体推荐理由）、focus（重点读什么）、url（核实后的 HTTPS 期刊/DOI/机构/PubMed 入口）、refs（本文书目或相关论述的已有块 ID）。构建器生成独立章节与导航，卡片展开。空数组兼容旧稿；新阅读页默认填写，有明确不推荐原因时不凑数。推荐与原文书目分开保存；书目题名差异、核验来源和范围另存阅读资料。

## 叙事导读：guide.story

overview新稿包含title、lead、format=research-map、research_map六步、takeaway、refs，并可按需提供 2–4 项 `metrics`（`label`/`value`/`meaning`，渲染在六步卡下方作为“原始观测 / 旧方法基准 / 本文结果”直观对比卡）。旧叙事版保留paragraphs/chain兼容入口，新六步总览不重复渲染旧paragraphs/chain长文。walkthrough 为按推理顺序排列的章节数组，每项 title、bridge（承接问题）、paragraphs、connection（通往下一步）、refs，可选 motions（id/label，指向既有机制）、table（head/rows）。章节不是论文目录的缩写；正文必须解释步骤之间的必要关系。数值卡统一交代对象和分母，综述可用机制卡。3分钟显示一页入门；10分钟在同一主线上展开章节，导读目录随路线切换。

10分钟导读的 motions 字段指向既有场景配置，但渲染为章节内播放器，而非跳转链接。实例ID采用 guide-motion-章节号-原场景ID，防止同页多处演示重名；场景来源、分步说明与正文一致，播放状态分别管理。验收须在导读内操作所有实例，确认没有切换至逐段精读，切路线后隐藏实例暂停。


## 阅读呈现与原始来源分开

sections[].name/level/items的原始内容和顺序继续校验。可额外填写display_name（中文阅读标题），kind取body、metadata或appendix；构建时正文先显示，辅助章节置后，原ID不变，空章节不占目录，推荐位于辅助章节之前。不得把正文标成附录以逃避讲解。

表格 source.facsimile 可提供 asset-root 内的原页裁切图片路径，用于原表转录排版有问题时并排核查；不可替换原表数据。caption仍按原文翻译解释。

段落 source.corrections 为可选数组，每项含old/new/pdf_page/reason。仅在source.status=verified且已看原页时使用；old须在当前显示文本中唯一精确匹配，逐项依序应用。原始raw与SHA始终保留，不能用此字段更改作者真实说法或解决论文内部矛盾。完整修订记录随阅读资料交付。若修改已有文字，批注可能待重定位，不能强行贴回。

## 可选跨学科字段（保持schema v2旧稿兼容）

`reading_profile`记录article_type（如quantitative/qualitative/conceptual/normative/historical/interpretive，可组合）、reader和purpose，用于撰稿，不向读者塞实现标签。`concepts`为概念卡数组：id以concept-开头且唯一；term、meaning、distinction、example均为非空文本，refs指向原文，anchor可指定全文插入处，默认第一条refs。walkthrough章节用concepts:["concept-id"]引用，图文原地呈现；示例在example中明确是原文还是教学例子。它们只在有助理解时增加，不每段强制配卡。

三类新增scene用visual配置：argument_map和evidence_coding含nodes与edges。节点为id、label、lines（1–3行，每行至多20字符）、stage（从0起的讲解阶段，必须有序且在stages范围内）；2–6个节点。编码演示恰好三个节点，对应材料、关注/编码和主题；关系边为from、to、relation，relation可为supports、rebuts、defines、precedes、compares、causes、interprets，箭头与真实论证一致。argument_map以3列至多2行排列，配置时避免交叉难读。

repeated_measures的visual需before、interval、after、meaning，均为文本，用于表示起始状态、区间记录、终点及比较含义；只演示测量顺序，不默认生成伪数据。通用场景只负责显现关系，不证明哲学论证有效，也不自动复现作者真实编码。阶段顺序与内容需实际看首中末帧。

front.language可为zh；中文原文标签使用“原文”，中文解释保持原义，不构造假英文。

attribution为可选对象，citation/url/license/changes均非空；在来源说明内保留作者、正式入口、原许可与教学改写说明，便于单文件离线传播时保留归属。编码演示三节点依次用interprets连接材料、关注与主题；因果或反驳关系需选择argument_map等合适场景。

## 原文的安全行内结构与注释

JATS导入器可写入source.inline_runs：顺序数组，每项text为文字，styles仅em/strong/sup/sub，可选target为现有原文块ID。全部text连接必须逐字等于raw.strip()；构建器拒绝未知链接和其他标签，不接受任意HTML。source.context=quote标明独立引文，quote_attribution保存其出处；footnote_label保留注号。引文不重复并入父段，后续文字仍独立保留。脚注跳转只指向原文，不把引注格式当成作者身份判断。

含inline_runs时不能叠加display corrections，否则样式偏移会失配。若需修正显示，先依据已核对来源重新生成一致的run结构；原raw与来源仍保留。不得为通过校验而改作者的真实论述。

新的人文场景visual：
- source_timeline：layers恰好三项，各含label/date/detail。detail至多36字符。三层可区分事件、记录、研究解释，图形间距不是精确时间尺度；不能以连接暗示未经证实的影响或因果。
- communication：nodes恰好三个{id,label}，label至多12字符。steps与stages等长；每步message/interpretation至多35字符，channels为{from,to,mode}，mode限speaks/overhears/letter。节点可在step.labels用既有ID覆盖显示名，以便切场景时明确谈话者；不要靠图外脚注才能知道此时是谁。
- text_focus：quote为至多160字符的真实短引句，须逐字存在于refs至少一个来源块，attribution说明说话者或引文出处。focuses与stages等长，每项text必须是quote连续片段，meaning至多45字符。高亮说明措辞如何支持解读，不冒充原作者强调。

六步数据只校验完整性、顺序与来源。是否讲清具体背景、真实缺口、方法怎样回应问题、发现怎样支撑结论，以及读者能否三分钟内理解，仍需内容审读。title/lead/六步/takeaway应形成一个短而完整的研究总览，不能每格写泛用句。

自然科学实测扩展：edna_capture展示颗粒随水流集中至滤膜，再经提取、扩增与参考库判读；qpcr_probe展示引物延伸及探针切开后的荧光；primer_specificity对比非目标在探针区或引物区受到区别时的扩增过程，均为固定原理示意，需核对是否符合本篇。edna_decay按visual的maximum、days、threshold（正有限数）及两条curves（label、initial、rate）画N(t)=initial×exp(−rate×t)；maximum覆盖起点与阈值。必须交代单位、参数来源及条件，曲线是模型重画，不冒充新增实测点。

词汇选择与双语 PDF 导出见 [专用规格](bilingual-pdf-vocabulary.md)。旧稿可不含 vocabulary；新英文正文按实际需要编写，不设固定条数。

## 原图清单与导读原图

`fulltext.figure_inventory` 保存独立原文图清单与子图核验；`story.walkthrough[].figures` 指定原图来源块、插入段落索引和中文读图解释。字段及严格构建流程见 [原图完整性规范](original-figures.md)。原文图不属于教学 mechanisms，不能相互替代。

`fulltext.source_pdf` 可绑定原PDF文件、哈希与逐页图像，段落使用已核实 `source.pdf_page` 关联；字段和可拖动缩放窗口见 [原页窗口](pdf-page-viewer.md)。


分离图注：Markdown提取将图片与英文图注分为两个来源块时，可在图片的 `source.caption_ref` 填入实际图注段落ID。保留两块raw、ID与源顺序；逐段原图链接至原位图注，10分钟导读复用该段完整英文图注。未知、空或非段落引用阻断构建。

## 重难点覆盖与题材无关绘制

新稿填写 `visual_plan`，格式与 `scene:process` 对象/关键帧见[声明式演示](declarative-scenes.md)。新完整稿CLI添加 `--require-visual-plan`；Python build/validate可用同名布尔参数。旧输入仍能重建。严格检查验证来源/场景/十分钟插入映射，拒绝把argument_map标为机制，不能代替内容覆盖、箭头语义、数值口径和画面同步的实际审读。

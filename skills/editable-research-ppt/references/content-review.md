# 通用内容计划与证据检查（v1.8）

这套规则适用于各学科、三种场景，以及论文、用户数据、概念讲解和推导。没有固定章节数、固定阅读顺序、每页字数或统一统计阈值。示例不构成特定研究领域的默认结论。

## 先理解，再排版

1. 阅读用户实际材料，列清核心问题、必要概念、研究/分析设计、主要发现或推导、结论适用条件；按本次任务确定哪些必讲、哪些可省略并记录原因。概念型课程没有实测结果时，不虚构实验；没有报告的信息如实写未报告/待核实。
2. 区分各项调查、实验或分析的对象、样本单位、比较基准及时间范围。结果不能借用另一研究的样本量、随访期或方法。把研究设计与观察结果分开，不能把结果硬排成预设实验流程。
3. 建立“结论—原文位置/原始结果—证据性质—必要条件—PPT落点”的内容计划，再按受众安排讲解依赖。允许同页解释、先给概览后展开、有理由的结论先行；不机械照搬摘要顺序或模板示例顺序。
4. 先核对内容，再选择版式。方法与主要结果应能相互对应，必要适用条件有落点，不重复几页相同结论填满槽位。重复提示供判断，不能为消除提示而删掉关键解释。

## 机器能检查什么

`scripts/content_audit.py`只使用Python标准库。它检查记录完整性、源文件哈希、UTF-8摘录中的引文、可见文字绑定、声明的数据口径、必讲主题覆盖和讲解依赖。不调用模型、不联网、不读取PDF语义，**不能证明引用支持结论、分类正确或全文重点已经穷尽**。

执行AI/人工须对照原文完成实际核验，再填写review；禁止先批量填verified再补材料。单凭摘要、文件哈希、勾选字段或本脚本绿灯都不代表科学核验完成。来源摘录也可能抽错，必须核对它与原PDF/数据的对应关系。

关系分类是声明式检查：非显著性不是等效证明，相关关系不是因果证明；不自动使用某个p值阈值。定量值必须保留单位、对象、比较基准和时间范围。值转换、合并分析或再计算须记录单独的可核对推导，不能悄悄换口径。

## 输入格式

正式输入 `demo: false` 必须有 `content_plan`。完整可运行的合成版式示例见 `assets/examples/native-composition.json`；它不是真实科研结果。字段如下：

```json
{
  "content_plan": {
    "version": 1,
    "sources": [{"id":"s1","path":"materials/extract.txt","sha256":"64位真实哈希"}],
    "evidence": [{
      "id":"e1","source_id":"s1","locator":"PDF第3页，结果第2段",
      "quote":"从已核对的UTF-8摘录逐字引用",
      "kind":"observation","relation":"descriptive","context":"study-a",
      "status":"verified"
    }],
    "claims": [{
      "id":"c1","text":"页面字段中的完整原句","kind":"observation",
      "context":"study-a","evidence_ids":["e1"],
      "targets":[{"slide":1,"field":"sections.0.body"}],"depends_on":[]
    }],
    "coverage": [{"id":"result","topic":"本任务的主要发现","required":true,"claim_ids":["c1"]}],
    "pages": [{"slide":1,"role":"content","message":"本页要讲清的问题或发现"}],
    "review": {
      "status":"verified","scope":"all_visible_substantive_content",
      "reviewer":"实际核对者/执行AI标识","note":"实际核对范围、条件及未报告项处理",
      "slides_sha256":"完成实际核对后的slides摘要"
    }
  }
}
```

- `sources`：本地UTF-8文本/表格摘录及SHA256；论文摘录、数据导出建议附`origin: {path,sha256}`绑定原PDF/工作簿。脚本核对文件字节和摘录引文，不把页码文本当成已自动定位到PDF。输入路径相对于制作JSON。
- `evidence.kind`：`observation`实测、`background`背景/定义、`inference`解释、`projection`预测、`derivation`推导。`status`可为`verified`、`unverified`、`not_reported`；未核实/未报告不能支撑肯定性结论，但可作为明确问题呈现。`context`是本任务内自定的调查/实验/分析ID，不含领域预设。
- `claims.kind`同上，另有`question`。解释和预测须提供`qualifier`，且该限定词/归属语必须实际出现在`text`中；例如“可能”“作者提出”“under this scenario”，不强制统一措辞。问题须在页面上有问号或真实的待验证措辞，不能仅把类型字段改成question。
- `relation`可为`descriptive|association|causal|not_different|equivalent`；因果和等效结论须有相应性质的证据。正确分类与统计解释仍需人/AI核验。
- 关键数值在`evidence.facts`记录`{value,unit,population,comparison,timeframe}`；`claims.facts`为该结构加`evidence_id`的数组。脚本比对完整口径、有限数值及引文/可见句中的值；缺失条件可写`not_reported`，不能替换为另一研究的数据。没有数字的概念或定性材料无需虚构facts。脚本不保证发现所有未声明的数值，实际核对必须覆盖全页实质内容。
- `targets`采用1起始页码及可见字段路径。标题、正文、表格单元格、紧凑版`texts`或`composition.0.text`均可；备注和来源字段不能冒充可见结论。至少覆盖每张正文/讨论页的关键内容，以及封面实质性highlights；其余实质文字同样属于review核验范围，不能利用只声明一个无关标题逃避检查。
- `coverage`按材料与任务定义核心主题；必讲项必须有claim落点。可选主题未讲时填写`omission_reason`。没有统一“必须有实验/假说”的章节表，也没有脚本声称已自动发现所有应讲主题。
- `pages`覆盖所有页面，角色`cover|navigation|content|discussion`，记录核心信息。封面/导航不能被用于豁免正文。重复讲述是表达检查，不强制每页结论或版式不同。
- `depends_on`引用需要先解释的claim；同页可解释，后页解释须在`forward_reference_reason`记录有意先概览的原因，产生待核对提示；依赖不存在或循环则报错。该字段描述讲解依赖，不是研究机制中的反馈环。
- `review.slides_sha256`由`content_audit.slides_digest(document)`计算。必须在实际核对后更新；不能自动刷新它来掩盖内容改变。review是核对声明，不是数字签名或独立验收证明。

## 正式稿、待审稿与手工编辑

```console
python scripts/content_audit.py --input INPUT.json
python scripts/preflight.py --input INPUT.json
python scripts/generate.py --input INPUT.json --output OUTPUT.pptx
python scripts/audit.py OUTPUT.pptx --strict
```

正式生成缺少计划或检查失败会在写入之前停止；不会覆盖原稿。临时排版/迁移旧JSON可显式加`generate.py --draft`，原图、数值图表和排版原有检查照常运行。它在PPT包中记录draft，不转成正式内容通过；不在页面上增加破坏模板的装饰或水印。`demo: true`仅用于如实标注的合成样板，不能用来绕过真实研究核验。

生成器将不含私有引文/路径的内容检查摘要及内容指纹写入PPT。凭据保守绑定实际页序、整页对象、关联关系、备注、图表、工作簿和媒体；调页、替换内容会令它失效，位置/样式修改或Office重存也可能令它失效。失效不一定说明科学内容改变，但不得静默继承旧凭据；按下文保留手改稿、核对实际变更并重新绑定，不用模板覆盖用户编辑。

```console
python scripts/prepare_handoff.py --pptx OUTPUT.pptx --output-directory DELIVERY --preview-directory PREVIEW
```

正式交付默认要求有效内容凭据；没有凭据的旧稿或样板可用`--draft`交付，使用说明和manifest明确标待审。PowerPoint渲染/目检和原图硬门槛仍单独执行，内容检查不能替代它们。

已有PPT手改后不要用模板覆盖。同步制作JSON与实际关键结论，实际审阅修改后的整份PPT，在`review.pptx_sha256`记录其SHA256，再运行：

```console
python scripts/content_audit.py --input UPDATED.json --pptx EDITED.pptx
python scripts/prepare_handoff.py --pptx EDITED.pptx --content-input UPDATED.json --output-directory DELIVERY
```

工具核对内容计划、PPT字节哈希、实际页序与关键结论可见性；其余手改实质内容仍须review声明者逐项核对。不会改写用户PPT，也不把人工声明包装成自动语义证明。

源项目导出会携带仅被引用的摘录及原始证据文件，并冻结内容检查运行时；与PDF一样可能含私密内容，只供明确授权的本地移交，不能自动公开。源输入编辑后，即使允许重建，也须更新实际核对记录；否则仅能显式`--draft`重建。十配色、两填充、23类版式及字体/比例/原图/素材规则均不变。

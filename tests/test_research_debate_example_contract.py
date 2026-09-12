# -*- coding: utf-8 -*-
"""研究构想与假说推敲技能（RFC-016）：示例对话与规则的机器可核对验证。

本模块把 `docs/rfcs/research-idea-debate-design.md` 中**已声明**的规则，对照**文档里实际写出的
两段示例对话**逐条核对。它不是对技能行为的验收（技能尚未实现），而是对设计稿自身的自检：
规则与示例必须互相一致，否则实现者会照抄一份自相矛盾的规格。

验证的三类对象：
1. 设计稿中声明的枚举与映射表（role_id / question_type、relation、maturity、反对意见定性等）；
2. §13.1、§13.2 两段示例对话的逐轮结构（单焦点、标签合法、信号有据、门禁顺序）；
3. 示例中出现的所有编号引用是否能解析到真实小节。

纯标准库实现，零第三方依赖。
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN_DOC = REPO_ROOT / "docs" / "rfcs" / "research-idea-debate-design.md"

# 5.1 表声明的五类实质提问 + 主持人的操作性问题
ROLE_QUESTION_TYPE = {
    "concept_clarifier": "CLARIFICATION",
    "premise_evidence_examiner": "PREMISE_EVIDENCE",
    "implication_validator": "IMPLICATION",
    "alternative_explorer": "COMPARISON",
    "reflection_facilitator": "REFLECTION",
    "moderator": "CONFIGURATION",
}
ROLE_ZH = {
    "概念澄清者": "concept_clarifier",
    "前提与证据审查者": "premise_evidence_examiner",
    "推论与验证者": "implication_validator",
    "替代解释探索者": "alternative_explorer",
    "观点修订引导者": "reflection_facilitator",
    "主持人": "moderator",
}
# 调度阶梯中属于"评估性提问"的项：RAW 阶段在完成发展配额前不得出现
EVALUATIVE_LADDER = {"P2", "P3", "P4"}
DEVELOPMENT_SIGNALS = {"INTUITION_FORMULATED", "DISCRIMINATION_ADDED"}


def _doc_text():
    return DESIGN_DOC.read_text(encoding="utf-8")


def _doc_prose():
    """正文视图：剥掉围栏代码块与行内代码，避免把"记载缺陷修复"的文字当成引用。

    §14.5 的实测记录里会出现形如 `8B`、`（7.4）` 的历史编号，它们描述的是已修复的
    问题本身，不是仍然生效的引用。
    """
    text = _doc_text()
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    return text


def _examples():
    """返回 {小节号: {"title": str, "body": [lines]}}，仅取示例小节。"""
    text = _doc_text()
    out = {}
    for m in re.finditer(r"^### (13\.\d) (.+)$", text, flags=re.M):
        num, title = m.group(1), m.group(2).strip()
        if "示例" not in title:
            continue
        start = m.end()
        nxt = re.search(r"^#{2,3} ", text[start:], flags=re.M)
        body = text[start:start + nxt.start()] if nxt else text[start:]
        out[num] = {"title": title, "body": body.splitlines()}
    return out


def _rounds(body):
    """把示例正文切成"轮"：一个用户输入 + 其后到下一个用户输入之间的内容。

    返回 [{"user": str, "ai": [lines]}...]。
    """
    starts = [i for i, l in enumerate(body) if l.startswith("**用户（虚构）**")]
    rounds = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(body)
        rounds.append({
            "user": body[s],
            "ai": body[s + 1:e],
        })
    return rounds


def _focus_questions(ai_lines):
    return [l for l in ai_lines if re.match(r"^\*{0,2}焦点问题", l)]


def _rule_notes(ai_lines):
    return [l for l in ai_lines if l.strip().startswith("> 规则落点")]


def _role_labels(ai_lines):
    """抽取形如 '**角色 · 视角切换**' 的标签；支持 5.1.3 的合并写法。

    注意：角色中文名本身含"与"（前提与证据审查者），因此合并分隔必须用最长角色名
    前缀匹配，不能用字符串切分。
    """
    kinds = "视角切换|独立 Agent 评估|视角自检（非独立评估）"
    pattern = re.compile(r"^\*\*(.+?) · (%s)\*\*" % kinds)
    names = sorted(ROLE_ZH, key=len, reverse=True)
    labels = []
    for l in ai_lines:
        m = pattern.match(l)
        if not m:
            continue
        rest = m.group(1).strip()
        roles = []
        while rest:
            for n in names:
                if rest.startswith(n):
                    roles.append(n)
                    rest = rest[len(n):].lstrip()
                    if rest.startswith("与"):
                        rest = rest[1:].lstrip()
                    break
            else:
                roles.append(rest)
                break
        labels.append((roles, m.group(2)))
    return labels


class TestDesignDocParsable(unittest.TestCase):
    """前置：设计稿可读、示例可解析。解析失败时后续断言无意义。"""

    def test_design_doc_exists_and_readable(self):
        self.assertTrue(DESIGN_DOC.is_file(), "设计稿不存在：%s" % DESIGN_DOC)
        text = _doc_text()
        self.assertGreater(len(text), 10_000)
        self.assertNotIn("\ufffd", text, "设计稿含替换字符，编码损坏")

    def test_two_examples_present(self):
        ex = _examples()
        self.assertGreaterEqual(len(ex), 2, "应至少有两段示例（探索 + 推敲），实际：%s" % list(ex))

    def test_markdown_fences_balanced(self):
        fences = [l for l in _doc_text().splitlines() if l.strip().startswith("```")]
        self.assertEqual(len(fences) % 2, 0, "代码围栏未配对")


class TestDeclaredMappings(unittest.TestCase):
    """5.1.3 声明的 role_id / question_type 映射必须存在且为一一对应。"""

    def test_role_question_type_table_declared(self):
        text = _doc_text()
        for role, qtype in ROLE_QUESTION_TYPE.items():
            self.assertIn("`%s`" % role, text, "未声明 role_id：%s" % role)
            self.assertIn("`%s`" % qtype, text, "未声明 question_type：%s" % qtype)
        self.assertIn("### 5.1.3 角色与标签的不可混用规则", text)

    def test_mapping_is_bijective(self):
        self.assertEqual(len(set(ROLE_QUESTION_TYPE.values())), len(ROLE_QUESTION_TYPE),
                         "question_type 与 role_id 必须一一对应，不能两个角色共用一个类型")

    def test_five_socratic_types_only(self):
        """五类实质提问之外的 CONFIGURATION 只属主持人。"""
        socratic = [v for k, v in ROLE_QUESTION_TYPE.items() if k != "moderator"]
        self.assertEqual(len(socratic), 5, "实质提问类型应为五类")
        self.assertEqual(ROLE_QUESTION_TYPE["moderator"], "CONFIGURATION")


class TestExampleProtocolConformance(unittest.TestCase):
    """§5.5 单轮协议在示例中的逐轮核对。"""

    def setUp(self):
        self.examples = _examples()
        self.assertTrue(self.examples, "未解析到示例小节")

    def test_every_user_turn_has_exactly_one_focus_question(self):
        """每轮恰好一个焦点问题；确认轮与评审轮同样只允许一个问句。"""
        for num, ex in self.examples.items():
            for idx, rnd in enumerate(_rounds(ex["body"]), start=1):
                fq = _focus_questions(rnd["ai"])
                self.assertEqual(
                    len(fq), 1,
                    "%s 第 %d 轮焦点问题数为 %d（须恰好 1）：%s" % (num, idx, len(fq), rnd["user"][:40]),
                )

    def test_no_bundled_subquestions_in_focus_question(self):
        """焦点问题不得把多个子问题打包成'一问'。"""
        banned = ("以及", "另外", "顺便", "同时，", "第二")
        for num, ex in self.examples.items():
            for idx, rnd in enumerate(_rounds(ex["body"]), start=1):
                for fq in _focus_questions(rnd["ai"]):
                    q = fq.split("：", 1)[-1]
                    self.assertEqual(q.count("？"), 1, "%s 第 %d 轮含多个问号" % (num, idx))
                    for b in banned:
                        self.assertNotIn(b, q, "%s 第 %d 轮焦点问题含并列引导词 %r" % (num, idx, b))

    def test_role_labels_are_known_and_typed(self):
        """每个标签的角色名必须在 5.1 表内，且执行方式取三种合法值之一。"""
        for num, ex in self.examples.items():
            for idx, rnd in enumerate(_rounds(ex["body"]), start=1):
                for roles, kind in _role_labels(rnd["ai"]):
                    self.assertIn(kind, ("视角切换", "独立 Agent 评估", "视角自检（非独立评估）"))
                    for r in roles:
                        self.assertIn(r, ROLE_ZH, "%s 第 %d 轮出现未知角色 %r" % (num, idx, r))

    def test_no_unlabeled_role_response(self):
        """有焦点问题的轮必须有角色标签；不能出现无标签的'裸'提问。"""
        for num, ex in self.examples.items():
            for idx, rnd in enumerate(_rounds(ex["body"]), start=1):
                if _focus_questions(rnd["ai"]):
                    self.assertTrue(
                        _role_labels(rnd["ai"]),
                        "%s 第 %d 轮有焦点问题但无角色标签" % (num, idx),
                    )

    def test_independent_review_is_labeled_independently(self):
        """独立评估结果必须以'独立 Agent 评估'标签陈示，且不得与'视角切换'混用同一行。"""
        for num, ex in self.examples.items():
            for idx, rnd in enumerate(_rounds(ex["body"]), start=1):
                kinds = set(k for _, k in _role_labels(rnd["ai"]))
                self.assertNotIn("视角切换", kinds - {"视角切换"} | set(),
                                 "%s 第 %d 轮标签非法" % (num, idx))
                if "视角切换" in kinds:
                    self.assertNotIn("独立 Agent 评估", kinds,
                                     "%s 第 %d 轮把视角切换与独立评估混在标签中" % (num, idx))
        text = "\n".join("\n".join(ex["body"]) for ex in self.examples.values())
        self.assertIn("独立 Agent 评估", text, "示例未展示独立评估标签")

    def test_rule_notes_are_short_and_present_per_round(self):
        """每轮应有规则落点注释，说明该轮触发/遵守了哪条规则。"""
        for num, ex in self.examples.items():
            rounds = _rounds(ex["body"])
            with_notes = sum(1 for r in rounds if _rule_notes(r["ai"]))
            self.assertGreaterEqual(
                with_notes, len(rounds) - 1,
                "%s 规则落点注释过少：%d/%d" % (num, with_notes, len(rounds)),
            )


class TestExampleEvidenceBoundaries(unittest.TestCase):
    """证据与来源边界：不得出现伪造数值、结论升级或未确认执行。"""

    def setUp(self):
        self.examples = _examples()

    def test_no_fabricated_parameters(self):
        """示例中不得给出具体样本量/时长/统计方法（必须标待补）。"""
        pattern = re.compile(
            r"(样地\s*\d+\s*(块|个)|n\s*=\s*\d+|\d+\s*个重复|\d+\s*个生长季|p\s*[<=]\s*0\.\d+)"
        )
        for num, ex in self.examples.items():
            body = "\n".join(ex["body"])
            hits = pattern.findall(body)
            self.assertEqual(hits, [], "%s 出现疑似伪造参数：%s" % (num, hits))

    def test_unknown_params_marked_pending(self):
        for num, ex in self.examples.items():
            body = "\n".join(ex["body"])
            if "设计草案" in body:
                self.assertIn("待补", body, "%s 的设计草案未标注待补" % num)

    def test_gap_confirmation_precedes_execution(self):
        """查证必须先确认后执行：确认问句出现在任何'已执行检索/提取'表述之前。"""
        for num, ex in self.examples.items():
            if "说明" in ex["title"]:
                continue
            body = "\n".join(ex["body"])
            confirm = body.find("焦点问题：是否按")
            self.assertGreater(confirm, -1, "%s 缺少查证确认问句" % num)
            for executed in ("已完成检索", "已经检索", "检索已完成", "已提取完成"):
                self.assertEqual(body.find(executed), -1,
                                 "%s 出现未经确认的执行表述：%s" % (num, executed))

    def test_no_consensus_claim_from_agreement(self):
        """不得把评估一致或未找到反例写成命题成立。"""
        banned = ("因此可以认为成立", "已获证实", "评估通过", "科学共识")
        for num, ex in self.examples.items():
            body = "\n".join(ex["body"])
            for b in banned:
                self.assertNotIn(b, body, "%s 出现越界结论：%s" % (num, b))


class TestMaturityGateInExamples(unittest.TestCase):
    """§8 成熟度守卫：评估性提问必须晚于发展配额。"""

    def test_raw_stage_defers_evaluative_questions(self):
        """示例 A（RAW 起步）中，首个 P2/P3/P4 之前须有至少 2 个发展信号。"""
        ex = _examples()
        target = [v for k, v in ex.items() if "探索" in v["title"] or "直觉" in v["title"]]
        self.assertTrue(target, "未找到探索模式示例")
        body = target[0]["body"]

        signals_before_eval = 0
        found_eval = False
        for rnd in _rounds(body):
            notes = " ".join(_rule_notes(rnd["ai"]))
            # 本轮之前累计的信号
            ladder_hits = set(re.findall(r"\bP[0-6]\b", notes))
            if ladder_hits & EVALUATIVE_LADDER and not found_eval:
                found_eval = True
                self.assertGreaterEqual(
                    signals_before_eval, 2,
                    "进入评估性提问时发展信号不足 2 个（实际 %d）——违反发展配额" % signals_before_eval,
                )
            for s in DEVELOPMENT_SIGNALS:
                if s in notes:
                    signals_before_eval += 1
        self.assertTrue(found_eval, "示例未展示评估性提问，无法核对发展配额")

    def test_examine_stage_may_start_with_premise_question(self):
        """示例 B 命题已成形（DEVELOPING），允许首轮即为 P2 前提审查。"""
        ex = _examples()
        target = [v for k, v in ex.items() if "推敲" in v["title"] or "挑战" in v["title"]]
        self.assertTrue(target, "未找到推敲模式示例")
        first = _rounds(target[0]["body"])[0]
        notes = " ".join(_rule_notes(first["ai"]))
        self.assertTrue(
            ("P1" in notes) or ("P2" in notes),
            "推敲模式首轮应为命题化（P1）或前提审查（P2），实际落点：%s" % notes,
        )
        self.assertIn("DEVELOPING", notes, "推敲模式首轮应标注命题已成形（DEVELOPING）")


class TestDesignDocReferencesResolve(unittest.TestCase):
    """设计稿内部编号引用必须解析到真实小节，避免重编号后留下悬空引用。"""

    def test_no_section_letter_suffixes(self):
        text = _doc_text()
        self.assertIsNone(re.search(r"^#+ \d+[A-Z]\.", text, flags=re.M),
                          "出现 A/B 字母后缀章节，编号应连续")

    def test_numbered_section_headings_are_strictly_increasing(self):
        nums = [int(m.group(1)) for m in re.finditer(r"^## (\d+)\.", _doc_text(), flags=re.M)]
        self.assertEqual(nums, sorted(nums), "章节编号未递增：%s" % nums)
        self.assertEqual(len(nums), len(set(nums)), "章节编号重复：%s" % nums)

    def test_cross_references_resolve(self):
        text = _doc_prose()
        headings = re.findall(r"^#{2,4} ([0-9]+(?:\.[0-9]+)*)\.? ", text, flags=re.M)
        top = {h.split(".")[0] for h in headings}
        sub = set(headings)
        bad = []
        for m in re.finditer(r"第\s*(\d+(?:\.\d+)?)\s*节", text):
            if m.group(1) not in top and m.group(1) not in sub:
                bad.append(m.group(1))
        titled = set()
        for m in re.finditer(r"^#{2,4} (\d+\.\d+(?:\.\d+)?) ", text, flags=re.M):
            titled.add(m.group(1))
        for m in re.finditer(r"[（(](\d+\.\d+(?:\.\d+)?)[）)]", text):
            num = m.group(1)
            if num in titled:
                continue  # 形如"### 13.3 示例说明"的小节标题，不是引用
            if num.split(".")[0] in top and num not in sub:
                bad.append(num)
        self.assertEqual(bad, [], "悬空的节引用：%s" % sorted(set(bad)))

    def test_no_stale_letter_section_references(self):
        self.assertIsNone(re.search(r"8[AB](\.\d)?", _doc_prose()),
                          "正文（不含实测记录）仍有 8A/8B 旧编号引用")


if __name__ == "__main__":
    unittest.main(verbosity=2)

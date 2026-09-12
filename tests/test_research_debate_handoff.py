# -*- coding: utf-8 -*-
"""M3：research-idea-debate ↔ 上游技能交接的行为测试。

逐条针对真实故障设计：

- **先确认后执行**：`approval.status != CONFIRMED` 时不得派发；
- **指纹绑定**：`question/scope/target_skill/budget_ref` 任一改变 → 旧确认失效，必须重新确认；
- **幂等**：同一 gap 加同一指纹重试不得重复派发已完成任务；
- **旧载荷映射**：不得假设上游有 `gap_id`/`approval`/指纹字段，映射是单向的；
- **对齐硬规则**：只有"命题层面直接支持"才能 `VERIFIED`；关键词共现一律 `UNRESOLVED`；
  `CONTEXT`/`BOUNDARY`/`CHALLENGE` 不得记 `VERIFIED`；
- **拒绝不阻塞**：拒绝查证后缺口保留、可继续讨论；
- 与仓库既有 `quote_audit.py` 的引句归一化口径一致。
"""

import sys
import unittest

import helpers  # noqa: F401

import tempfile

from shared.execution import (  # noqa: E402
    TARGET_SKILLS, scope_fingerprint, to_upstream_payload, prepare_dispatch,
    to_evidence_link, ingest_returns, normalize_quote_text,
    to_executable_query, candidates_to_records,
    detect_language_mismatch, align_against_proposition, variant_fingerprint,
)
from shared.execution.session_store import SessionStore  # noqa: E402
from helpers import semantic_verification  # noqa: E402

REPO_ROOT = helpers.REPO_ROOT


def _gap(**over):
    g = {
        "schema_version": "0.1",
        "gap_id": "GAP-001",
        "session_id": "S1",
        "idea_id": "I1",
        "idea_version": 1,
        "gap_type": "SEARCH_GAP",
        "target_skill": "literature-discovery-acquisition",
        "question": "移除凋落物与土壤扰动对林下草本物种数的相对影响",
        "reason": "当前争议是地表层限制是否主导",
        "decision_impact": "决定主张重心是否从光限制转到地表层限制",
        "blocking": "BLOCKING",
        "scope": {"topic": "litter removal vs soil disturbance", "time_range": "2020-2026"},
        "approval": {"status": "PENDING", "confirmed_event_id": None, "scope_fingerprint": None},
        "execution_status": "NOT_STARTED",
        "result_refs": [],
    }
    g.update(over)
    if g["approval"].get("scope_fingerprint") is None:
        g["approval"]["scope_fingerprint"] = scope_fingerprint(g)
    return g


def _confirm(g, event_id="EV-GAP-1"):
    g = dict(g)
    g["approval"] = dict(g["approval"], status="CONFIRMED", confirmed_event_id=event_id,
                         approved_idea_version=g.get("idea_version"))
    return g


def _store_for(gap, event_id="EV-GAP-1", **payload_over):
    """建一个真实 SessionStore，内含该缺口的用户 GAP_CONFIRMED 事件。

    R05 之后授权核验要求可信事件上下文：只有范围指纹不算授权证明。
    """
    folder = tempfile.mkdtemp(prefix="sf-handoff-")
    store = SessionStore(folder)
    payload = {
        "gap_id": gap.get("gap_id"),
        "idea_id": gap.get("idea_id"),
        "idea_version": gap.get("idea_version"),
        "scope_fingerprint": scope_fingerprint(gap),
        "confirmed_by": "user",
    }
    payload.update(payload_over)
    event = {
        "schema_version": "0.1", "event_id": event_id,
        "session_id": gap.get("session_id"), "seq": 1,
        "type": "GAP_CONFIRMED", "actor": "user", "execution_kind": "USER",
        "payload": payload, "created_at": "2026-09-13T00:00:00Z",
    }
    event.update({k: v for k, v in payload_over.items() if k.startswith("_event_")})
    store.append_event(event)
    return store


class TestFingerprint(unittest.TestCase):
    def test_fingerprint_is_stable_for_same_material(self):
        self.assertEqual(scope_fingerprint(_gap()), scope_fingerprint(_gap()))

    def test_typographic_differences_do_not_change_fingerprint(self):
        a = _gap()
        b = _gap(question="移除凋落物与土壤扰动对林下草本物种数的相对影响  ")  # 尾随空格
        self.assertEqual(scope_fingerprint(a), scope_fingerprint(b),
                         "仅排版差异不应使确认失效")

    def test_each_of_four_fields_changes_fingerprint(self):
        base = scope_fingerprint(_gap())
        variants = {
            "question": _gap(question="另一问法"),
            "scope": _gap(scope={"topic": "another topic"}),
            "target_skill": dict(_gap(), target_skill="literature-synthesis"),
            "budget_ref": _gap(approval={"status": "PENDING", "confirmed_event_id": None,
                                          "scope_fingerprint": None, "budget_ref": "run-2"}),
        }
        for field, g in variants.items():
            g = dict(g)
            g["approval"] = dict(g["approval"])
            g["approval"]["scope_fingerprint"] = None
            g["approval"]["scope_fingerprint"] = scope_fingerprint(g)
            self.assertNotEqual(base, scope_fingerprint(g),
                                "%s 改变后指纹必须变化" % field)


class TestDispatchGate(unittest.TestCase):
    def test_pending_approval_cannot_dispatch(self):
        r = prepare_dispatch(_gap())
        self.assertFalse(r["dispatchable"])
        self.assertEqual(r["reason"], "APPROVAL_NOT_CONFIRMED")
        self.assertTrue(r["must_reconfirm"])

    def test_confirmed_approval_dispatches_with_mapped_payload(self):
        g = _confirm(_gap())
        r = prepare_dispatch(g, session_store=_store_for(g))
        self.assertTrue(r["dispatchable"], r)
        payload = r["payload"]
        self.assertEqual(payload["gap_type"], "SEARCH_GAP")
        self.assertEqual(payload["target_skill"], "literature-discovery-acquisition")
        self.assertEqual(payload["reason"], "决定主张重心是否从光限制转到地表层限制")
        self.assertEqual(payload["date_range"], "2020-2026")
        # 单向映射：不得把本技能的内部字段塞给上游
        for forbidden in ("gap_id", "approval", "scope_fingerprint", "idea_version"):
            self.assertNotIn(forbidden, payload,
                             "上游载荷不应包含本技能内部字段 %s" % forbidden)

    def test_scope_change_invalidates_approval(self):
        g = _confirm(_gap())
        g["scope"] = {"topic": "widened topic"}   # 范围变了，指纹随之改变
        r = prepare_dispatch(g)
        self.assertFalse(r["dispatchable"])
        self.assertEqual(r["reason"], "SCOPE_CHANGED_APPROVAL_STALE")
        self.assertTrue(r["must_reconfirm"])

    def test_explicit_scope_changed_flag_also_blocks(self):
        g = _confirm(_gap())
        g["scope_changed"] = True
        r = prepare_dispatch(g)
        self.assertFalse(r["dispatchable"])
        self.assertEqual(r["reason"], "SCOPE_CHANGED_APPROVAL_STALE")

    def test_completed_task_is_idempotent_not_redispatched(self):
        g = _confirm(_gap())
        g["execution_status"] = "COMPLETE"
        r = prepare_dispatch(g)
        self.assertFalse(r["dispatchable"])
        self.assertTrue(r["idempotent_replay"])
        self.assertFalse(r["must_reconfirm"])

    def test_rejected_gap_keeps_question_and_blocks_dispatch(self):
        g = _gap(approval={"status": "REJECTED", "confirmed_event_id": None,
                            "scope_fingerprint": None})
        r = prepare_dispatch(g)
        self.assertFalse(r["dispatchable"])
        self.assertTrue(g["question"], "拒绝后原问题必须保留")


class TestUpstreamPayloadShapes(unittest.TestCase):
    def test_extraction_gap_payload(self):
        g = _confirm(_gap(gap_type="EXTRACTION_GAP",
                          target_skill="literature-evidence-extraction",
                          scope={"target_papers": ["2018_Author_A.pdf", "2019_Author_B.pdf"],
                                 "required_fields": ["渗透势设定", "萌发观察终点"]}))
        payload = to_upstream_payload(g)
        self.assertEqual(payload["target_paper"], "2018_Author_A.pdf")
        self.assertEqual(payload["additional_target_papers"], ["2019_Author_B.pdf"])
        self.assertEqual(payload["required_fields"], ["渗透势设定", "萌发观察终点"])

    def test_synthesis_request_payload(self):
        g = _confirm(_gap(gap_type="SYNTHESIS_REQUEST",
                          target_skill="literature-synthesis",
                          scope={"evidence_refs": ["EV-1", "EV-2"], "target_claim": "光限制主导"}))
        payload = to_upstream_payload(g)
        self.assertEqual(payload["evidence_refs"], ["EV-1", "EV-2"])
        self.assertEqual(payload["target_claim"], "光限制主导")

    def test_unknown_gap_type_is_rejected_loudly(self):
        with self.assertRaises(ValueError):
            to_upstream_payload(_gap(gap_type="MADE_UP_GAP"))

    def test_target_skills_cover_three_skills_only(self):
        self.assertEqual(len(TARGET_SKILLS), 3)
        for skill in TARGET_SKILLS.values():
            self.assertTrue((REPO_ROOT / "skills" / skill / "SKILL.md").is_file(),
                            "目标技能不存在：%s" % skill)


class TestEvidenceAlignmentHardRules(unittest.TestCase):
    PROP = "在批内比较中，根际土与非根际土的 amoA 丰度差异方向与 nifH 一致"

    def _rec(self, **over):
        r = {"evidence_id": "EV-1", "artifact_ref": "paper.json",
             "verbatim_quote": "", "location": {"page": 4, "section": "Results"},
             "checked_scope": "该文 Results 与 Methods"}
        r.update(over)
        # R01 之后 VERIFIED 需要绑定完整的语义核验凭据；本类测的是命题对齐，
        # 因此默认给"正例"配一份合规凭据，需要验证语义门槛时再显式覆盖。
        r.setdefault("semantic_verification",
                     semantic_verification(r["evidence_id"], self.PROP))
        return r

    def test_support_with_supported_quote_is_verified(self):
        link = to_evidence_link(
            self._rec(verbatim_quote="根际土与非根际土的 amoA 丰度差异方向与 nifH 一致，"
                                     "在批内配对比较中成立。"),
            self.PROP, relation="SUPPORT")
        self.assertEqual(link["alignment"], "VERIFIED", link)
        self.assertIn(link["quote_match"], ("EXACT", "OVERLAP"))

    def test_keyword_cooccurrence_is_not_upgraded(self):
        """实体/关键词出现 ≠ 命题获支持。"""
        link = to_evidence_link(
            self._rec(verbatim_quote="amoA 与 nifH 基因的丰度在土壤样品中均被检出，"
                                     "根际土样品占全部样品的半数。"),
            self.PROP, relation="SUPPORT")
        self.assertEqual(link["alignment"], "UNRESOLVED", link)
        self.assertIn("QUOTE_DOES_NOT_SUPPORT_PROPOSITION", link["problems"])

    def test_context_never_verified(self):
        link = to_evidence_link(
            self._rec(verbatim_quote="根际土与非根际土的 amoA 丰度差异方向与 nifH 一致，"
                                     "在批内配对比较中成立。"),
            self.PROP, relation="CONTEXT")
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertIn("不得升级为支持", link["reason"])

    def test_boundary_and_challenge_never_verified(self):
        for rel in ("BOUNDARY", "CHALLENGE"):
            link = to_evidence_link(
                self._rec(verbatim_quote="根际土与非根际土的 amoA 丰度差异方向与 nifH 一致，"
                                         "在批内配对比较中成立。"),
                self.PROP, relation=rel)
            self.assertEqual(link["alignment"], "UNRESOLVED", "%s 不应 VERIFIED" % rel)

    def test_missing_quote_or_location_stays_unresolved(self):
        no_quote = to_evidence_link(self._rec(), self.PROP, relation="SUPPORT")
        self.assertEqual(no_quote["alignment"], "UNRESOLVED")
        self.assertIn("MISSING_VERBATIM_QUOTE", no_quote["problems"])
        # 显式去掉定位才测"缺定位"；_rec 默认带 location
        no_loc = to_evidence_link(self._rec(verbatim_quote="x", location=None), self.PROP,
                                  relation="SUPPORT")
        self.assertIn("MISSING_LOCATION", no_loc["problems"])
        self.assertEqual(no_loc["alignment"], "UNRESOLVED")

    def test_checked_scope_surfaces_in_link(self):
        link = to_evidence_link(self._rec(verbatim_quote="无关内容"), self.PROP)
        self.assertEqual(link["checked_scope"], "该文 Results 与 Methods")

    def test_illegal_relation_rejected(self):
        with self.assertRaises(ValueError):
            to_evidence_link(self._rec(), self.PROP, relation="SUPPORTS")


class TestIngestReturns(unittest.TestCase):
    PROP = "在批内比较中，根际土与非根际土的 amoA 丰度差异方向与 nifH 一致"

    def test_empty_return_keeps_gap_open_and_says_so(self):
        out = ingest_returns([], self.PROP)
        self.assertEqual(out["counts"]["total"], 0)
        self.assertIn("检索失败不等于不存在研究", out["note"])

    def test_mixed_batch_reports_impact_by_relation(self):
        records = [
            {"evidence_id": "EV-A", "location": {"page": 1},
             "verbatim_quote": "在批内配对比较中，根际土与非根际土的 amoA 丰度差异方向与 nifH 一致。",
             "checked_scope": "Results",
             "semantic_verification": semantic_verification(
                 "EV-A", "在批内比较中，根际土与非根际土的 amoA 丰度差异方向与 nifH 一致")},
            {"evidence_id": "EV-B", "location": {"page": 2},
             "verbatim_quote": "amoA 与 nifH 丰度均被检出。", "checked_scope": "Results"},
            {"evidence_id": "EV-C", "location": {"page": 3},
             "verbatim_quote": "该结论仅适用于水稻季样品。", "checked_scope": "Discussion"},
        ]
        out = ingest_returns(records, self.PROP,
                             relations={"EV-A": "SUPPORT", "EV-B": "SUPPORT",
                                        "EV-C": "BOUNDARY"},
                             artifact_ref="upstream.json")
        self.assertEqual(out["counts"]["total"], 3)
        self.assertEqual(out["impact"]["supports"], ["EV-A"])
        self.assertEqual(out["impact"]["boundaries"], ["EV-C"])
        self.assertIn("EV-B", out["impact"]["unresolved"])
        for link in out["evidence_links"]:
            self.assertEqual(link["artifact_ref"], "upstream.json")

    def test_no_verified_means_no_status_upgrade(self):
        out = ingest_returns([{"evidence_id": "EV-X", "location": {"page": 1},
                                "verbatim_quote": "无关句子", "checked_scope": "s"}],
                             self.PROP, relations={"EV-X": "SUPPORT"})
        self.assertEqual(out["counts"]["verified"], 0)
        self.assertIn("不因本批而升级", out["note"])


class TestQuoteNormalisationParity(unittest.TestCase):
    """引句口径必须与仓库既有 quote_audit.py 一致，否则两个技能会给出不同判断。"""

    def test_parity_with_quote_audit(self):
        audit_path = REPO_ROOT / "skills" / "literature-evidence-extraction" / "scripts"
        sys.path.insert(0, str(audit_path))
        try:
            import quote_audit  # type: ignore
        except Exception as exc:  # noqa: BLE001
            self.skipTest("quote_audit 不可导入：%s" % exc)
        samples = [
            "PCR was performed in a total volume of  20 μL.",
            "step- wise annealing",
            "“Root\n\nbiomass”  increased",
            "ＡＢＣ１２３",
        ]
        for s in samples:
            self.assertEqual(normalize_quote_text(s), quote_audit.normalize_text(s),
                             "归一化结果与 quote_audit 不一致：%r" % s)


class TestChineseComparabilityRegression(unittest.TestCase):
    """中文比对回归：早期实现用词元切分，中文整段会被切成一个 token，
    导致"引句包含命题"这种最直接的支持关系也算不出相似度（假阴性）。
    这里把四种典型情形固化为回归基线。"""

    PROP = "城市公园不同植被配置下土壤细菌群落的相对组成存在系统差异"

    def _link(self, quote):
        return to_evidence_link(
            {"evidence_id": "E", "artifact_ref": "paper.json", "location": {"page": 1},
             "verbatim_quote": quote, "checked_scope": "s",
             "semantic_verification": semantic_verification("E", self.PROP)},
            self.PROP, relation="SUPPORT")

    def test_supporting_quote_with_extra_context_is_verified(self):
        l = self._link("不同植被配置下土壤细菌群落的相对组成存在系统差异，混植样点与草坪样点显著分离。")
        self.assertEqual(l["alignment"], "VERIFIED", l)

    def test_verbatim_proposition_is_exact(self):
        l = self._link(self.PROP)
        self.assertEqual(l["alignment"], "VERIFIED")
        self.assertEqual(l["quote_match"], "EXACT")

    def test_keyword_salad_is_not_upgraded(self):
        l = self._link("土壤细菌群落在城市绿地中广泛分布，植被配置是常见的研究对象。")
        self.assertEqual(l["alignment"], "UNRESOLVED", l)
        self.assertEqual(l["quote_match"], "KEYWORD_ONLY")

    def test_unrelated_paragraph_is_not_upgraded(self):
        l = self._link("本研究采用双因素方差分析比较三种配置的土壤理化性质。")
        self.assertEqual(l["alignment"], "UNRESOLVED", l)

    def test_latin_text_still_works(self):
        prop = "BioBERT-Large achieved a Macro-F1 score of 0.842"
        quote = "BioBERT-Large achieved a Macro-F1 score of 0.842 on the test split."
        l = to_evidence_link(
            {"evidence_id": "E", "artifact_ref": "paper.json", "location": {"page": 5},
             "verbatim_quote": quote, "checked_scope": "Table 3",
             "semantic_verification": semantic_verification("E", prop)},
            prop, relation="SUPPORT")
        self.assertEqual(l["alignment"], "VERIFIED", l)


class TestCrossLanguageDetection(unittest.TestCase):
    """跨语言盲区回归（2026 真实闭环暴露）。

    真实闭环里，英文文献的关键引句与中文命题的 2-gram 交集恒为空，覆盖率恒为 0，
    结果被记成 `KEYWORD_ONLY` —— 与「查了但文献确实不支持」**完全无法区分**。
    而「英文文献支持中文命题」正是本技能的常态。

    修法是**知情标注**而非放宽阈值：
      - `language_mismatch = True` 标出「机制上无法判定」；
      - `alignment` 仍为 `UNRESOLVED`（跨语言不得升级为支持）。
    """

    PROP = "城市公园不同植被配置下土壤细菌群落的相对组成存在系统差异"
    EN_QUOTE = ("there is less conclusive evidence that microbial community composition "
                "influences the broad processes of decomposition and organic matter turnover in soil")

    def test_mismatch_detected_for_cjk_prop_vs_latin_quote(self):
        self.assertTrue(detect_language_mismatch(self.EN_QUOTE, self.PROP))

    def test_mismatch_detected_in_both_directions(self):
        self.assertTrue(detect_language_mismatch(self.PROP, self.EN_QUOTE))

    def test_same_language_is_not_flagged(self):
        self.assertFalse(detect_language_mismatch(self.PROP, "不同植被配置下的相对组成差异"))
        self.assertFalse(detect_language_mismatch(
            "the relative composition differs", "the relative composition differs systematically"))

    def test_mixed_script_is_not_flagged(self):
        """中英混排（如英文引句带中文括注）不算跨语言，避免误标。"""
        self.assertFalse(detect_language_mismatch(self.EN_QUOTE + "（微生物群落）", self.PROP))

    def test_empty_input_is_not_flagged(self):
        self.assertFalse(detect_language_mismatch("", self.PROP))
        self.assertFalse(detect_language_mismatch(self.EN_QUOTE, ""))

    def test_mismatch_is_labelled_but_never_upgraded(self):
        l = to_evidence_link(
            {"evidence_id": "E", "artifact_ref": "paper.json", "location": {"page": 1},
             "verbatim_quote": self.EN_QUOTE, "checked_scope": "全文 11 页"},
            self.PROP, relation="SUPPORT")
        self.assertEqual(l["alignment"], "UNRESOLVED")
        self.assertEqual(l["quote_match"], "LANGUAGE_MISMATCH")
        self.assertTrue(l["language_mismatch"])
        self.assertIn("LANGUAGE_MISMATCH", l["problems"])
        self.assertIn("无法判定", l["reason"])

    def test_same_language_failure_still_reads_as_keyword_only(self):
        """跨语言标注不得吞掉真实的"不支持"判定：同语言失败仍应是 KEYWORD_ONLY。"""
        l = to_evidence_link(
            {"evidence_id": "E", "location": {"page": 1},
             "verbatim_quote": "本研究测量了土壤 pH 与有机质含量。", "checked_scope": "全文"},
            self.PROP, relation="SUPPORT")
        self.assertEqual(l["alignment"], "UNRESOLVED")
        self.assertEqual(l["quote_match"], "KEYWORD_ONLY")
        self.assertFalse(l["language_mismatch"])

    def test_ingest_returns_propagates_the_flag(self):
        out = ingest_returns(
            [{"evidence_id": "E1", "verbatim_quote": self.EN_QUOTE, "location": {"page": 1},
              "checked_scope": "全文"}],
            self.PROP, {"E1": "SUPPORT"})
        link = out["evidence_links"][0]
        self.assertTrue(link["language_mismatch"])
        self.assertEqual(link["alignment"], "UNRESOLVED")
        self.assertEqual(out["counts"]["verified"], 0)


class TestPropositionVariants(unittest.TestCase):
    """跨语言升级路径：命题的多语言变体必须经用户确认才可比对。

    设计取舍（为什么不是"只要有译文就升级"）：
      - 译文是 AI 产出的**主张**，不是命题本身；若可直接升级，
        等于让 AI 自造一个更容易被文献命中的命题来"证明"原命题；
      - 因此要求 `approval.status == CONFIRMED` **且** `confirmed_by == "user"`；
      - 且要求**两条**已确认译文互相印证（双向覆盖率 ≥ 0.85），
        以拦住"把一种误译当成证据"；
      - 只命中一条已确认译文时**不升级**，如实标 `PENDING_CONFIRMATION`。
    """

    PROP = "城市公园不同植被配置下，土壤细菌群落的相对组成存在系统差异（主口径为各分类单元的相对比例）。"
    EN_QUOTE = ("Across vegetation configurations in urban parks, the relative composition "
                "of soil bacterial communities differs systematically, measured primarily "
                "as the relative proportion of each taxon.")
    EN_A = ("The relative composition of soil bacterial communities differs systematically "
            "across vegetation configurations in urban parks (primary measure: the relative "
            "proportion of each taxon).")
    EN_B = ("In urban parks, the relative composition of soil bacterial communities differs "
            "systematically across vegetation configurations, with the relative proportion of "
            "each taxon as the primary measure.")
    EN_OTHER = "Tree age drives soil pH in temperate forests."

    def _variant(self, ref, text, status="CONFIRMED", by="user", source=None):
        src = source if source is not None else self.PROP
        return {"variant_ref": ref, "lang": "en", "text": text, "source_text": src,
                "proposed_by": "ai",
                "approval": {"status": status, "confirmed_by": by,
                             "scope_fingerprint": variant_fingerprint({"source_text": src})}}

    def _link(self, variants, quote=None):
        return to_evidence_link(
            {"evidence_id": "E", "artifact_ref": "paper.json", "location": {"page": 3},
             "verbatim_quote": quote or self.EN_QUOTE, "checked_scope": "全文 11 页",
             "semantic_verification": semantic_verification("E", self.PROP)},
            self.PROP, relation="SUPPORT", variants=variants)

    def test_without_variants_cross_language_stays_unresolved(self):
        l = self._link(None)
        self.assertEqual(l["alignment"], "UNRESOLVED")
        self.assertEqual(l["variant_status"], "NOT_APPLICABLE")

    def test_single_user_confirmed_variant_is_pending_not_verified(self):
        """只有一条译文时不得升级：缺第二条独立翻译互相印证。"""
        l = self._link([self._variant("V-1", self.EN_A)])
        self.assertEqual(l["alignment"], "UNRESOLVED")
        self.assertEqual(l["quote_match"], "VARIANT_NEEDS_SECOND_OPINION")
        self.assertEqual(l["variant_status"], "PENDING_CONFIRMATION")
        self.assertEqual(l["variant_ref"], "V-1")
        self.assertIn("第二条", l["reason"])

    def test_ai_self_confirmed_variant_never_upgrades(self):
        """`confirmed_by="ai"` 不算确认，即使标了 CONFIRMED。"""
        vs = [self._variant("V-AI", self.EN_A, by="ai"),
              self._variant("V-AI2", self.EN_B, by="ai")]
        l = self._link(vs)
        self.assertEqual(l["alignment"], "UNRESOLVED")
        self.assertEqual(l["quote_match"], "VARIANT_UNCONFIRMED")

    def test_two_user_confirmed_agreeing_variants_upgrade(self):
        """两条已确认且互相印证的译文 → 可升级，并记录实际使用的变体。"""
        l = self._link([self._variant("V-1", self.EN_A),
                        self._variant("V-2", self.EN_B)])
        self.assertEqual(l["alignment"], "VERIFIED", l)
        self.assertEqual(l["quote_match"], "VARIANT_AGREEMENT")
        self.assertEqual(l["variant_status"], "ALIGNED")
        # 标注的是**覆盖率最高**的那条（确定性规则：先按命中顺序扫描，再取最大值）
        self.assertIn(l["variant_ref"], ("V-1", "V-2"))
        self.assertFalse(l["language_mismatch"])
        self.assertIn("互相印证", l["reason"])

    def test_confirmed_but_disagreeing_variants_do_not_upgrade(self):
        """两条已确认译文互相不印证 → 译法本身有分歧，交由用户裁决，不升级。

        注意这里 `quote_match` 是 `VARIANT_NEEDS_SECOND_OPINION` 而不是
        `VARIANT_DISAGREEMENT`：引句本身（含 "relative composition" 等）
        与无关命题的覆盖率只有 0.55，够不上命中，所以命中的只有 1 条。
        两者都落在 `PENDING_CONFIRMATION`，结论一致。
        """
        l = self._link([self._variant("V-1", self.EN_A),
                        self._variant("V-3", self.EN_OTHER)])
        self.assertEqual(l["alignment"], "UNRESOLVED")
        self.assertEqual(l["variant_status"], "PENDING_CONFIRMATION")
        self.assertIn(l["quote_match"], ("VARIANT_DISAGREEMENT", "VARIANT_NEEDS_SECOND_OPINION"))

    def test_two_hitting_but_mutually_unconfirming_variants_stay_pending(self):
        """两条译法都"命中"引句、却互不印证时，判 `VARIANT_DISAGREEMENT`，不得升级。

        这正是本机制的要点：引句对**两条译法各自**都够像，说明分歧出在译法本身，
        而不是出在引句；此时必须交回用户裁决，不能挑一条有利的译法来升级。
        """
        loose = ("Soil bacterial community composition in urban parks differs systematically "
                 "across vegetation configurations.")
        vs = [self._variant("V-1", self.EN_A), self._variant("V-2", loose)]
        r = align_against_proposition(self.EN_QUOTE, self.PROP, vs)
        self.assertFalse(r["supported"])
        self.assertEqual(r["how"], "VARIANT_DISAGREEMENT")
        self.assertEqual(r["variant_status"], "PENDING_CONFIRMATION")
        l = self._link(vs)
        self.assertEqual(l["alignment"], "UNRESOLVED")

    def test_pending_variant_never_upgrades(self):
        l = self._link([self._variant("V-1", self.EN_A, status="PENDING", by=None)])
        self.assertEqual(l["alignment"], "UNRESOLVED")
        self.assertEqual(l["variant_status"], "PENDING_CONFIRMATION")

    def test_rejected_variant_never_upgrades(self):
        vs = [self._variant("V-1", self.EN_A, status="REJECTED", by=None),
              self._variant("V-2", self.EN_B, status="REJECTED", by=None)]
        self.assertEqual(self._link(vs)["alignment"], "UNRESOLVED")

    def test_variant_of_a_different_proposition_is_stale(self):
        """命题已改 → 旧变体指纹不符 → 自动失效，不得用于升级。"""
        old = self.PROP + "（修订）"
        vs = [self._variant("V-1", self.EN_A, source=old),
              self._variant("V-2", self.EN_B, source=old)]
        l = self._link(vs)
        self.assertEqual(l["alignment"], "UNRESOLVED")
        self.assertEqual(l["quote_match"], "VARIANT_UNCONFIRMED")

    def test_non_support_relation_is_not_upgraded_by_variants(self):
        vs = [self._variant("V-1", self.EN_A), self._variant("V-2", self.EN_B)]
        l = to_evidence_link(
            {"evidence_id": "E", "location": {"page": 3},
             "verbatim_quote": self.EN_QUOTE, "checked_scope": "全文"},
            self.PROP, relation="CONTEXT", variants=vs)
        self.assertEqual(l["alignment"], "UNRESOLVED")
        self.assertIn("relation=CONTEXT", l["reason"])

    def test_same_language_proposition_still_wins_over_variants(self):
        """引句直接命中命题时按命题判定，不因存在变体而改口径。"""
        vs = [self._variant("V-1", self.EN_A), self._variant("V-2", self.EN_B)]
        l = self._link(vs, quote="研究确认：" + self.PROP)
        self.assertEqual(l["alignment"], "VERIFIED")
        self.assertEqual(l["quote_match"], "EXACT")
        self.assertIsNone(l["variant_ref"])

    def test_ingest_returns_reports_pending_variant_confirmation(self):
        out = ingest_returns(
            [{"evidence_id": "E1", "verbatim_quote": self.EN_QUOTE,
              "location": {"page": 3}, "checked_scope": "全文"}],
            self.PROP, {"E1": "SUPPORT"},
            variants=[self._variant("V-1", self.EN_A)])
        self.assertEqual(out["counts"]["verified"], 0)
        self.assertEqual(out["counts"]["pending_variant_confirmation"], 1)
        self.assertEqual(out["impact"]["pending_variants"], ["E1"])
        self.assertIn("译法待确认", out["note"])

    def test_variant_fingerprint_tracks_source_text(self):
        a = variant_fingerprint({"source_text": self.PROP})
        b = variant_fingerprint({"source_text": self.PROP + "。"})
        c = variant_fingerprint({"source_text": self.PROP})
        self.assertEqual(a, c)
        self.assertNotEqual(a, b)

    def test_align_helper_is_usable_standalone(self):
        """对齐核心可独立调用（宿主需要在写库前预览判定）。"""
        r = align_against_proposition(self.EN_QUOTE, self.PROP,
                                      [self._variant("V-1", self.EN_A),
                                       self._variant("V-2", self.EN_B)])
        self.assertTrue(r["supported"])
        self.assertEqual(r["variant_status"], "ALIGNED")
        self.assertIn(r["variant_ref"], ("V-1", "V-2"))


class TestExecutableQuery(unittest.TestCase):
    """缺口 → 可执行检索式；只从缺口取词，不把对话原文写进检索式。"""

    def test_query_built_from_gap_scope_and_question(self):
        q = to_executable_query({"scope": {"topic": "urban green space soil bacteria"},
                                  "question": "植被配置是否影响群落组成"})
        self.assertIn("urban", q)
        self.assertIn("植被配置", q)

    def test_duplicates_and_function_words_removed_but_content_kept(self):
        q = to_executable_query({"scope": {"topic": "土壤 细菌 土壤"},
                                  "question": "细菌 的 差异 是否存在"})
        tokens = q.split()
        self.assertEqual(len(tokens), len(set(tokens)), "重复词未去重：%s" % q)
        self.assertNotIn("的", tokens, "虚词未过滤：%s" % q)
        self.assertNotIn("是否", tokens, "疑问句式未剥离：%s" % q)
        # 名词性实词必须保留——它们是检索的核心
        for keep in ("土壤", "细菌", "差异"):
            self.assertIn(keep, tokens, "名词性实词被误删：%s" % q)
        # 已知取舍：剥离"是否存在"这类疑问句式会连带去掉"存在"。
        # 该动词检索价值低，故接受；但断言在此显式记录，避免以后被当成 bug 反复"修"。
        self.assertNotIn("存在", tokens, "疑问句式剥离的已知副作用发生了变化，请复核")

    def test_term_cap_respected(self):
        q = to_executable_query({"scope": {"topic": " ".join("t%d" % i for i in range(40))},
                                  "question": ""}, max_terms=5)
        self.assertEqual(len(q.split()), 5)

    def test_conversation_text_is_not_injected(self):
        """检索式只能来自缺口字段——传入的对话原文式描述不参与构造。"""
        gap = {"scope": {"topic": "alpha"}, "question": "beta"}
        q = to_executable_query(gap)
        self.assertNotIn("用户说", q)
        self.assertNotIn("我导说", q)


class TestCandidateConversion(unittest.TestCase):
    """上游产物 → 候选记录：**候选命中 ≠ 证据**。"""

    PROP = "城市公园不同植被配置下土壤细菌群落的相对组成存在系统差异"

    def _discovery(self, n=3):
        return {"status": "SUCCESS",
                "candidates": [{"doi": "10.1/x%d" % i, "title": "T%d" % i,
                                 "abstract": "关于群落组成的研究摘要 %d" % i} for i in range(n)]}

    def test_candidates_carry_no_verbatim_quote(self):
        recs = candidates_to_records(self._discovery())
        self.assertEqual(len(recs), 3)
        for r in recs:
            self.assertEqual(r["verbatim_quote"], "",
                             "题录与摘要不得冒充原文引句")
            self.assertIsNone(r["location"])
            self.assertTrue(r["candidate_only"])

    def test_respects_max_records(self):
        self.assertEqual(len(candidates_to_records(self._discovery(5), max_records=2)), 2)

    def test_candidates_never_upgrade_to_verified(self):
        """核心断言：候选命中绝不能被升级为支持。"""
        recs = candidates_to_records(self._discovery(4))
        out = ingest_returns(recs, self.PROP, artifact_ref="discovery_result.json")
        self.assertEqual(out["counts"]["verified"], 0)
        self.assertEqual(out["counts"]["unresolved"], 4)
        self.assertIn("不因本批而升级", out["note"])

    def test_extraction_return_can_upgrade_only_with_quote(self):
        """只有带回原文引句的抽取产物才可能升级。"""
        rec = {"evidence_id": "EV-1", "artifact_ref": "extraction_result.json",
               "verbatim_quote": "不同植被配置下土壤细菌群落的相对组成存在系统差异，混植样点与草坪样点显著分离。",
               "location": {"page": 6, "section": "Results"}, "checked_scope": "Results",
               "semantic_verification": semantic_verification("EV-1", self.PROP)}
        out = ingest_returns([rec], self.PROP, relations={"EV-1": "SUPPORT"})
        self.assertEqual(out["counts"]["verified"], 1)

    def test_empty_discovery_result_is_handled(self):
        self.assertEqual(candidates_to_records({}), [])
        out = ingest_returns([], self.PROP)
        self.assertIn("检索失败不等于不存在研究", out["note"])


class TestFullHandoffClosure(unittest.TestCase):
    """端到端：未确认 → 拒绝；确认 → 派发 → 候选 → 不升级 → 抽取后才升级。"""

    PROP = "城市公园不同植被配置下土壤细菌群落的相对组成存在系统差异"

    def test_closure(self):
        gap = {"gap_id": "G-1", "session_id": "S-CLOSURE", "idea_id": "I-CLOSURE",
               "idea_version": 2, "gap_type": "SEARCH_GAP",
               "target_skill": "literature-discovery-acquisition",
               "question": "植被配置是否影响群落组成", "decision_impact": "决定能否独立归因",
               "scope": {"topic": "urban green space soil bacteria"}, "blocking": "BLOCKING",
               "approval": {"status": "PENDING", "confirmed_event_id": None,
                             "scope_fingerprint": None},
               "execution_status": "NOT_STARTED"}
        gap["approval"]["scope_fingerprint"] = scope_fingerprint(gap)
        self.assertFalse(prepare_dispatch(gap)["dispatchable"])

        gap["approval"].update(status="CONFIRMED", confirmed_event_id="EV-1",
                               approved_idea_version=2)
        disp = prepare_dispatch(gap, session_store=_store_for(gap, event_id="EV-1"))
        self.assertTrue(disp["dispatchable"])
        self.assertIn("executable_query", disp["payload"])

        recs = candidates_to_records({"candidates": [
            {"doi": "10.1/a", "title": "A", "abstract": "abs"}]})
        out1 = ingest_returns(recs, self.PROP)
        self.assertEqual(out1["counts"]["verified"], 0)

        recs2 = [{"evidence_id": "EV-X", "artifact_ref": "paper.json",
                  "verbatim_quote": "不同植被配置下土壤细菌群落的相对组成存在系统差异。",
                  "location": {"page": 1}, "checked_scope": "s",
                  "semantic_verification": semantic_verification("EV-X", self.PROP)}]
        out2 = ingest_returns(recs2, self.PROP, relations={"EV-X": "SUPPORT"})
        self.assertEqual(out2["counts"]["verified"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

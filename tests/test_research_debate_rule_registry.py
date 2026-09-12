# -*- coding: utf-8 -*-
"""RFC-016 规格检查器的元测试：规则号必须可溯源、实跑记录必须被正确判定。

本模块防两类退化：
  1. **凭空规则**：检查器里出现设计稿没有依据的规则号；
  2. **永久通过**：检查器对一份含已知违规的真实实跑记录给出"无违规"。

实跑记录来自 `.planning/research-idea-debate/live-run/`（多 Agent 真实对话，内容为虚构演示素材）。
该目录被 `.gitignore` 忽略，因此记录以本模块内的镜像常量为准，并在设计稿 §14.7 摘录。
"""

import io
import re
import unittest
from pathlib import Path

import helpers  # noqa: F401

import spec_check_debate as sc

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_CHECKER = REPO_ROOT / "tests" / "spec_check_debate.py"
DESIGN_DOC = REPO_ROOT / "docs" / "rfcs" / "research-idea-debate-design.md"
LIVE_SESSION = REPO_ROOT / ".planning" / "research-idea-debate" / "live-run" / "session.json"


def _checker_rule_ids():
    """收集校验器用到的全部规则号。

    技能校验器统一使用 `rep.add("RULE", ...)` 登记（早期规格检查器用 `_v(out, "RULE", ...)`），
    两种写法都要覆盖，否则会把新加的规则误判为"索引里的幽灵规则"。
    """
    src = SPEC_CHECKER.read_text(encoding="utf-8")
    ids = set(re.findall(r'rep\.add\("([A-Z0-9-]+)"', src))
    ids |= set(re.findall(r'_v\(out,\s*"([A-Z0-9-]+)"', src))
    # 枚举类规则用 _enum(rep, value, allowed, "RULE", where, field) 登记
    ids |= set(re.findall(r'"([A-Z][A-Z0-9-]+)",\s*where', src))
    ids |= set(re.findall(r'_enum\(rep,[^)]*?"([A-Z][A-Z0-9-]+)"', src))
    return sorted(ids)


def _indexed_rule_ids():
    doc = DESIGN_DOC.read_text(encoding="utf-8")
    if "### 14.8 检查器规则索引" not in doc:
        return []
    heading = "### 14.8 检查器规则索引"
    start = doc.index(heading)
    body = start + len(heading)
    nxt = re.search(r"^#{2,3} ", doc[body:], flags=re.M)
    seg = doc[start:body + nxt.start()] if nxt else doc[start:]
    return re.findall(r"^\| `([A-Z0-9-]+)` \|", seg, flags=re.M)


class TestRuleTraceability(unittest.TestCase):
    """每条检查器规则都必须能对到设计稿的依据。"""

    def test_rule_index_exists(self):
        self.assertTrue(_indexed_rule_ids(), "设计稿缺少 §14.8 检查器规则索引")

    def test_every_checker_rule_is_indexed(self):
        missing = [r for r in _checker_rule_ids() if r not in _indexed_rule_ids()]
        self.assertEqual(missing, [], "检查器规则未登记依据（凭空规则）：%s" % missing)

    def test_index_has_no_phantom_rules(self):
        extra = [r for r in _indexed_rule_ids() if r not in _checker_rule_ids()]
        self.assertEqual(extra, [], "索引里存在检查器没有的规则号：%s" % extra)

    def test_rule_count_is_stable(self):
        self.assertGreaterEqual(len(_checker_rule_ids()), 50,
                                "规则数异常减少，可能被误删")


class TestLiveSessionAdjudication(unittest.TestCase):
    """实跑记录的判定必须稳定：该报的报，不该报的不报。"""

    def setUp(self):
        if not LIVE_SESSION.is_file():
            self.skipTest("实跑记录不存在（.planning 被忽略或未生成）")
        import json
        self.session = json.loads(LIVE_SESSION.read_text(encoding="utf-8"))

    def test_live_session_violations_are_stable(self):
        """实跑记录的判定必须稳定。

        RD1 是当场暴露的真实违规（R3 焦点问题含并列引导词）；
        RV15 是后来新增的分歧判定规则**事后检出**的同类问题——
        该会话的 review_batches 里只有 `premise_overlap`（字面重合）而无反例类型标签，
        正是 §7.3 修法所禁止的判定方式。两条都应保留，作为回归基线。
        """
        v = sc.check_all(self.session)
        rules = sorted({x.rule for x in v})
        self.assertEqual(rules, ["RD1", "RV15"],
                         "实跑记录的判定发生变化：%s\n%s" % (rules, sc.format_violations(v)))
        self.assertEqual(sorted(x.where for x in v), ["R3", "batch RB-01"])

    def test_live_session_records_the_violation_and_round(self):
        """真实违规的形态：1 个问号 + 「以及」并列三个子问 —— 仅数问号不足以发现。"""
        r3 = next(r for r in self.session["rounds"] if r["round"] == 3)
        self.assertEqual(r3.get("spec_violation"), "RD1")
        self.assertEqual(r3["question"].count("？") + r3["question"].count("?"), 1)
        self.assertIn("以及", r3["question"])

    def test_live_session_never_reached_p3(self):
        """实跑中全程未出现 P3 —— 收尾前检查规则的现实依据。"""
        triggers = {r.get("trigger") for r in self.session["rounds"]}
        self.assertNotIn("P3", triggers)
        self.assertTrue(self.session["summary"].get("proposition_left_developing"))
        self.assertEqual(self.session["summary"].get("proposition_maturity_at_close"), "DEVELOPING")

    def test_live_session_divergence_is_high_and_deterministic(self):
        b = self.session["review_batches"][0]
        self.assertEqual(b["disagreement_signal"], "HIGH_DIVERGENCE")
        self.assertEqual(b["computed_by"], "deterministic_program")
        self.assertNotEqual(b["verdicts"]["T1"], b["verdicts"]["T2"])
        self.assertLess(b["premise_overlap_ratio"], 0.5)

    def test_live_session_external_opinion_not_user_decision(self):
        for d in self.session["ideas"][0]["decisions"]:
            self.assertTrue(d["user_confirmation"], "存在未经用户确认的决定：%s" % d["id"])
            self.assertNotEqual(d["author"], "EXTERNAL_OPINION")
        ext = self.session["external_inputs"]
        self.assertTrue(len(ext) >= 2, "导师两次意见都应登记为外部意见")
        for e in ext:
            self.assertTrue(e["not_user_decision"])

    def test_live_session_keeps_boundary_decision_with_user(self):
        """用户要求"先看改写文本再定"——不得提前标为已决定。"""
        d3 = next(d for d in self.session["ideas"][0]["decisions"] if d["id"] == "D3")
        self.assertEqual(d3["action"], "DEFER_REVISION")
        self.assertEqual(d3["author"], "USER")


class TestST7Rule(unittest.TestCase):
    """ST7：收尾时未进入 P3 却声称已形成验证方案。"""

    def _base(self):
        return {
            "schema_version": "0.1", "session_id": "S", "run_id": "R", "mode": "explore",
            "state": "CHECKPOINT", "original_prompt": "p", "current_question": "q",
            "stop_reason": "CHECKPOINT_REACHED",
            "execution": {"depth": "standard", "selection_status": "confirmed",
                          "budget": {"max_rounds": 4, "max_review_batches": 1,
                                     "max_subtasks_per_batch": 2, "max_active_seconds": 100,
                                     "max_events": 10},
                          "usage": {"rounds_used": 1, "tokens_observed": None,
                                    "tokens_metering": "UNAVAILABLE"}},
            "ideas": [{"idea_id": "I", "maturation": "DEVELOPING", "versions": [
                {"version": 1, "parent_version": None, "proposition": "x", "origin": "USER",
                 "epistemic_status": "HYPOTHESIS", "disposition": "ACTIVE",
                 "revision_reason": "r"}],
                "maturity_history": [{"from": "RAW", "to": "DEVELOPING", "round": 1}],
                "decisions": []}],
            "rounds": [{"round": 1, "kind": "SUBSTANTIVE", "idea_id": "I", "target_version": 1,
                        "role": "concept_clarifier", "question_type": "CLARIFICATION",
                        "trigger": "P1", "intent": "i", "question": "一个问题？",
                        "user_answer": "a", "signals": ["INTUITION_FORMULATED"]}],
            "open_questions": [], "stopped_questions": [], "gap_requests": [],
            "summary": {},
        }

    def test_flags_validation_plan_claim_without_p3(self):
        s = self._base()
        s["summary"]["claims_validation_plan"] = True
        rules = {v.rule for v in sc.check_all(s)}
        self.assertIn("ST7", rules)

    def test_passes_when_plan_claim_is_retracted(self):
        s = self._base()
        s["summary"]["proposition_left_developing"] = True
        rules = {v.rule for v in sc.check_all(s)}
        self.assertNotIn("ST7", rules)


if __name__ == "__main__":
    unittest.main(verbosity=2)

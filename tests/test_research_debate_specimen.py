# -*- coding: utf-8 -*-
"""RFC-016 规格检查器的故障注入测试（负控）。

一个"永远通过"的检查器毫无价值。本模块对复杂规格样本注入 20 处已知违规，
逐一断言检查器能报出**预期规则号**；并以未注入的原始样本作为正控（必须 0 违规）。

样本：`tests/fixtures/specimen_session_debate.json`（虚构演示场景，非真实研究证据）。
"""

import copy
import json
import unittest
from pathlib import Path

import helpers  # noqa: F401  （保持与仓库其余测试一致的导入习惯）

import spec_check_debate as sc

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "specimen_session_debate.json"


def _load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _round(session, number):
    return next(r for r in session["rounds"] if r["round"] == number)


def _rules(violations):
    return {v.rule for v in violations}


class TestSpecimenBaseline(unittest.TestCase):
    """正控：未注入的样本必须完全合规，否则检查器不可信。"""

    def test_specimen_has_no_violation(self):
        violations = sc.check_all(_load())
        self.assertEqual(violations, [], "样本自身存在违规：\n%s" % sc.format_violations(violations))

    def test_specimen_is_complex_enough(self):
        s = _load()
        kinds = {r["kind"] for r in s["rounds"]}
        for required in ("SUBSTANTIVE", "CONFIGURATION", "EXTERNAL_INPUT", "REVIEW_SUBMISSION", "CHECKPOINT"):
            self.assertIn(required, kinds, "样本缺少轮次类型：%s" % required)
        self.assertGreaterEqual(len(s["gap_requests"]), 4)
        self.assertGreaterEqual(len(s["review_batches"]), 2)
        self.assertGreaterEqual(len(s["ideas"][0]["versions"]), 3)


class TestFaultInjection(unittest.TestCase):
    """负控：每处注入都必须被对应规则抓到。"""

    def _inject(self, mutate, expected_rules):
        s = _load()
        mutate(s)
        violations = sc.check_all(s)
        got = _rules(violations)
        for rule in expected_rules:
            self.assertIn(rule, got,
                          "注入未被 %s 捕获；实际报出：%s" % (rule, sorted(got) or "无"))

    # ---- 单轮协议 ----
    def test_catch_two_questions_in_one_round(self):
        def mutate(s):
            _round(s, 5)["question"] = "存活率会下降吗？高生长也会下降吗？"
        self._inject(mutate, {"RD1"})

    def test_catch_bundled_subquestion(self):
        def mutate(s):
            _round(s, 7)["question"] = "有没有对应关系，以及有没有做过定标？"
        self._inject(mutate, {"RD1"})

    def test_catch_role_question_type_mismatch(self):
        def mutate(s):
            _round(s, 5)["question_type"] = "COMPARISON"
        self._inject(mutate, {"RD4"})

    def test_catch_configuration_by_non_moderator(self):
        def mutate(s):
            _round(s, 11)["role"] = "concept_clarifier"
            _round(s, 11)["question_type"] = "CONFIGURATION"
        self._inject(mutate, {"RD4", "RD7"})

    def test_catch_missing_user_answer(self):
        def mutate(s):
            _round(s, 9)["user_answer"] = ""
        self._inject(mutate, {"RD2"})

    def test_catch_unknown_progress_signal(self):
        def mutate(s):
            _round(s, 9)["signals"] = ["FELT_GOOD"]
        self._inject(mutate, {"RD9"})

    def test_catch_stale_target_version(self):
        def mutate(s):
            _round(s, 16)["target_version"] = 99
        self._inject(mutate, {"RD5"})

    # ---- 成熟度与维度独立 ----
    def test_catch_deferral_written_as_evidence_denial(self):
        def mutate(s):
            s["ideas"][0]["versions"][2]["disposition"] = "DEFERRED"
            s["ideas"][0]["versions"][2]["epistemic_status"] = "EVIDENCE_CHALLENGED"
        self._inject(mutate, {"ID-INDEP"})

    def test_catch_value_tradeoff_without_user(self):
        def mutate(s):
            s["ideas"][0]["versions"][2]["assumptions"] = [{
                "text": "应优先保护补植带", "type": "VALUE",
                "verification_status": "UNVERIFIED", "source_refs": [],
            }]
        self._inject(mutate, {"ID-VALUE"})

    def test_catch_maturity_history_inconsistent(self):
        def mutate(s):
            s["ideas"][0]["maturity_history"] = [{"from": "RAW", "to": "TESTABLE", "round": 1}]
        self._inject(mutate, {"ID-MAT"})

    def test_catch_missing_checked_scope(self):
        def mutate(s):
            del s["ideas"][0]["evidence_links"][0]["checked_scope"]
        self._inject(mutate, {"EV2"})

    # ---- 证据对齐 ----
    def test_catch_context_evidence_upgraded_to_support(self):
        def mutate(s):
            s["ideas"][0]["evidence_links"][0]["alignment"] = "VERIFIED"
        self._inject(mutate, {"EV1"})

    # ---- 决定记录 ----
    def test_catch_external_opinion_as_decision_author(self):
        def mutate(s):
            for d in s["ideas"][0]["decisions"]:
                if d["id"] == "D5":
                    d["author"] = "EXTERNAL_OPINION"
        self._inject(mutate, {"DC1"})

    def test_catch_ai_suggestion_without_confirmation(self):
        def mutate(s):
            for d in s["ideas"][0]["decisions"]:
                if d["id"] == "D2":
                    d["user_confirmation"] = False
        self._inject(mutate, {"DC3"})

    # ---- 查证 ----
    def test_catch_execution_before_confirmation(self):
        def mutate(s):
            for g in s["gap_requests"]:
                if g["gap_id"] == "GAP-003":
                    g["execution_status"] = "RUNNING"
        self._inject(mutate, {"GP2"})

    def test_catch_confirmed_without_fingerprint(self):
        def mutate(s):
            for g in s["gap_requests"]:
                if g["gap_id"] == "GAP-001":
                    g["approval"]["scope_fingerprint"] = ""
        self._inject(mutate, {"GP1"})

    def test_catch_scope_change_without_invalidation(self):
        def mutate(s):
            for g in s["gap_requests"]:
                if g["gap_id"] == "GAP-001":
                    g["scope_changed"] = True
        self._inject(mutate, {"GP4"})

    # ---- 独立评估 ----
    def test_catch_high_divergence_resolved_by_vote(self):
        def mutate(s):
            s["review_batches"][0]["resolution"] = "VOTE"
        self._inject(mutate, {"RV12"})

    def test_catch_missing_evaluators_not_voted_low(self):
        def mutate(s):
            s["review_batches"][0]["subtasks"][1]["status"] = "FAILED"
            s["review_batches"][0]["disagreement_signal"] = "LOW_DIVERGENCE"
        self._inject(mutate, {"RV9", "RV14"})

    def test_catch_degraded_batch_masquerading_as_independent(self):
        def mutate(s):
            b = s["review_batches"][1]
            b["execution_kind"] = "INDEPENDENT_AGENT"
            b["disagreement_signal"] = "LOW_DIVERGENCE"
        self._inject(mutate, {"RV11", "RV10"})

    def test_catch_review_input_leaks_other_evaluators(self):
        def mutate(s):
            s["review_requests"][0]["excluded"] = ["用户偏好表述"]
        self._inject(mutate, {"RV1"})

    def test_catch_disagreement_not_computed_deterministically(self):
        def mutate(s):
            s["review_batches"][0]["computed_by"] = "gpt-4o"
        self._inject(mutate, {"RV8"})

    def test_catch_same_lens_twice_in_batch(self):
        def mutate(s):
            s["review_batches"][0]["subtasks"][1]["lens"] = "premise_evidence_examiner"
        self._inject(mutate, {"RV5"})

    # ---- 停止与未决 ----
    def test_catch_checkpoint_claiming_resolution(self):
        def mutate(s):
            _round(s, 23)["question"] = "卡点已经解决，要生成小结吗？"
        self._inject(mutate, {"ST3"})

    def test_catch_missing_stop_reason(self):
        def mutate(s):
            s.pop("stop_reason")
        self._inject(mutate, {"ST1"})

    def test_catch_rejected_gap_without_open_question(self):
        def mutate(s):
            s["open_questions"] = []
        self._inject(mutate, {"ST4"})

    def test_catch_stopped_question_without_known_info(self):
        def mutate(s):
            s["stopped_questions"][0]["known"] = ""
        self._inject(mutate, {"ST5"})

    def test_catch_stopping_rule_mislabel(self):
        def mutate(s):
            s["stopped_questions"][0]["stop_rule"] = "S9"
        self._inject(mutate, {"ST5"})

    def test_catch_budget_exhaustion_unrecorded(self):
        def mutate(s):
            s.pop("budget_exhausted_at_round")
        self._inject(mutate, {"ST6"})

    def test_catch_session_ends_without_reason(self):
        def mutate(s):
            s["state"] = "DISCUSSING"
        self._inject(mutate, {"ST2"})

    # ---- 预算 ----
    def test_catch_token_used_as_hard_cap(self):
        def mutate(s):
            s["execution"]["budget"]["max_tokens"] = 30000
        self._inject(mutate, {"BU1"})

    def test_catch_raw_proposition_verdict(self):
        def mutate(s):
            s["ideas"][0]["maturation"] = "RAW"
            _round(s, 1)["verdict_on_proposition"] = "CHALLENGED"
        self._inject(mutate, {"RD8b"})

    def test_catch_first_prediction_before_quota(self):
        def mutate(s):
            # 把命题本身的可观察预测要求提前到第 1 轮：此时尚无任何发展信号
            _round(s, 1)["trigger"] = "P3"
            _round(s, 1)["signals"] = []
        self._inject(mutate, {"MT1"})


class TestNewRuleBehaviour(unittest.TestCase):
    """RD10（同轮角色名 ≤2）与 RV15（分歧判定不得用字面重合）的行为性负控。

    只断言"规则号出现在文档索引里"是不够的——必须证明规则**真的会触发**。
    """

    def _load(self):
        return _load()

    def test_rd10_fires_on_three_role_names(self):
        s = _load()
        _round(s, 1)["labels_text"] = "主持人 与 概念澄清者 与 替代解释探索者 同轮"
        rules = _rules(sc.check_all(s))
        self.assertIn("RD10", rules)

    def test_rd10_silent_on_two_role_names(self):
        """合并标签（两个角色）是允许的，不得误报。"""
        s = _load()
        _round(s, 1)["labels_text"] = "概念澄清者 与 前提与证据审查者 · 独立 Agent 评估"
        self.assertNotIn("RD10", _rules(sc.check_all(s)))

    def test_rv15_fires_when_divergence_lacks_counterexample_types(self):
        s = _load()
        s["review_batches"][0].pop("counterexample_types", None)
        self.assertIn("RV15", _rules(sc.check_all(s)))

    def test_rv15_fires_on_high_with_identical_types_and_verdicts(self):
        s = _load()
        b = s["review_batches"][0]
        b["disagreement_signal"] = "HIGH_DIVERGENCE"
        b["counterexample_types"] = {"T1": "MEASUREMENT_ARTIFACT", "T2": "MEASUREMENT_ARTIFACT"}
        for sub in b["subtasks"]:
            sub["verdict"] = "BOUNDED"
        self.assertIn("RV15", _rules(sc.check_all(s)))

    def test_rv15_fires_on_undeclared_counterexample_type(self):
        s = _load()
        s["review_batches"][0]["counterexample_types"] = {"T1": "MADE_UP", "T2": "CONFOUNDING"}
        self.assertIn("RV15", _rules(sc.check_all(s)))

    def test_rv15_silent_when_no_divergence_was_assessed(self):
        """NOT_APPLICABLE（评估者不足 2 个）本无分歧可标，不得因缺标签报错。"""
        s = _load()
        b = s["review_batches"][1]
        self.assertEqual(b["disagreement_signal"], "NOT_APPLICABLE")
        self.assertNotIn("RV15", _rules(sc.check_all(s)))


if __name__ == "__main__":
    unittest.main(verbosity=2)

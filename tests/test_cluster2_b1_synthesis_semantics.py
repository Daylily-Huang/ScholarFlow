# -*- coding: utf-8 -*-
"""B1 批次（synthesis 语义 + 资格族）回归——20260913-e2e-cluster2 第二轮集群测试修复。

覆盖决议表行 H-05 / H-06 / H-50 / H-52 / H-54 / H-49 / H-91 / H-53 / H-07 止血 / 设施-1，
夹具移植自 04-synthesis 三个 agent 的实测产物：

- verifier/attacks/a1_zero_weight_variants.py 的 15 个 BYPASS 写法变体（SYN-V-01）；
- adversary/fixtures/f01*（句号逃逸翻转）、f02*（stance 拼写静默）、f03*（独立性负向
  比较）、f04b/c/d/h（反证武器化）、f05c/e（REJECTED 吞掉真实异议）、f07（appraisal
  拼写逃逸）；
- adversary/REPORT.md §H.D/E 的 map_evidence_to_claim / 主宾互换实测；
- verifier REPORT §4.4 的 15/38 audit-gate 不合格场景（13 NEUTRAL + 2 REFERENCED_ONLY）。

不变量：合法输入 byte-identical；枚举语义类 fail-closed 一律「标志 + 排除 + 计数」，
不 raise；normalize_claim 只增键不删键。
"""

import json
import os
import sys
import unittest

import helpers  # noqa: F401

REPO_ROOT = helpers.REPO_ROOT
sys.path.insert(0, os.path.join(REPO_ROOT, "skills", "literature-synthesis", "scripts"))

import controversy_analyzer as ca  # noqa: E402
from controversy_analyzer import (  # noqa: E402
    analyze,
    challenge_penalty,
    compute_topic_consensus,
    format_markdown_report,
    format_summary_report,
    normalize_claim,
    resolve_evidence_weight,
    to_canonical_synthesis_records,
)
from evidence_states import (  # noqa: E402
    UNPARSEABLE_CLASS,
    classify_non_evidence,
    normalize_state_token,
)
from evidence_to_claim import (  # noqa: E402
    claim_consensus_issues,
    check_target_proposition_compatibility,
    evaluate_consensus_eligibility,
    map_evidence_to_claim,
)

TOPIC = "Snow leopard density in Sanjiangyuan"


def _claim(cid, pid, stance, **over):
    """adversary/fixtures 基础行形状（f02a/f04a 族）。"""
    base = {
        "claim_id": cid,
        "topic": TOPIC,
        "paper_id": pid,
        "year": 2020,
        "claim": "%s density measured by camera trap" % pid,
        "stance": stance,
        "method": "camera trap grid",
        "metric_value": 1.1,
        "evidence_strength": "DIRECT_EMPIRICAL",
    }
    base.update(over)
    return base


def _runner_row(cid, pid, stance, group, status="VERIFIED", **over):
    """runner/claims/claims_two_topic.json 的真实 ClaimRecord 形状（s1_build_claims 产物）。"""
    row = {
        "schema_version": "1.0",
        "claim_id": cid,
        "topic": TOPIC,
        "paper_id": pid,
        "year": 2026,
        "claim": "%s 主张" % pid,
        "stance": stance,
        "stance_mapping_status": "AGENT_MAPPED",
        "evidence_ids": ["EV-%s" % cid],
        "method": "transect survey",
        "evidence_strength": "DIRECT_EMPIRICAL",
        "evidence_tier": "E1",
        "support_type": "EXPLICIT",
        "independence_group_id": group,
        "independence_status": status,
        "claim_status_upstream": "SUPPORTED",
    }
    row.update(over)
    return row


class TestH05NonEvidenceVariants(unittest.TestCase):
    """H-05：归一化表驱动全覆盖；15 个实测逃逸变体全部零权重；空值 UNPARSEABLE。"""

    def test_fifteen_bypass_variants_now_zero_weight(self):
        """verifier a1 实测的 15 个 BYPASS 变体（SYN-V-01），表驱动断言全零权。"""
        variants = [
            "N/R", "NR.", "N.R.", "NOT.REPORTED", "not.reported",
            "un-checked", "", None, "NONE", "null", "NOT_AVAILABLE",
            "N/A", "N.A.", "not reported.", "NOT REPORTED.",
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                weight, kind, _ = resolve_evidence_weight(
                    _claim("C", "P", "SUPPORT", support_type=variant))
                self.assertEqual(weight, 0.0, variant)
                self.assertNotEqual(kind, "DIRECT_EMPIRICAL", variant)

    def test_punctuation_and_case_variants_share_the_same_token(self):
        """标点逃逸与规范写法必须折叠到同一 token / 同一语义类。"""
        for variant in ("Not reported.", "not reported!", "NOT.REPORTED",
                        "not_reported", "NOT-REPORTED", "  NOT  REPORTED  "):
            self.assertEqual(classify_non_evidence({"support_type": variant}),
                             "NOT_REPORTED", variant)
            self.assertEqual(normalize_state_token(variant), "NOT_REPORTED")

    def test_empty_and_punctuation_only_become_unparseable(self):
        for variant in ("", "   ", "…", "---", "?", None):
            self.assertEqual(classify_non_evidence({"support_type": variant}),
                             UNPARSEABLE_CLASS, repr(variant))

    def test_unparseable_is_excluded_and_counted_not_silent(self):
        claims = [_claim("C1", "P1", "SUPPORT", support_type="…"),
                  _claim("C2", "P2", "SUPPORT")]
        res = compute_topic_consensus(claims)
        self.assertEqual(res["consensus_eligible_claims"], 1)
        self.assertEqual(res["excluded_from_consensus"].get(UNPARSEABLE_CLASS), 1)

    def test_referenced_only_maps_to_cited_only_zero_weight(self):
        """SYN-R-01：二级转引（REFERENCED_ONLY）与 CITED_ONLY 同层零权。"""
        weight, kind, _ = resolve_evidence_weight(
            _claim("C", "P", "SUPPORT", support_type="REFERENCED_ONLY"))
        self.assertEqual(weight, 0.0)
        self.assertEqual(kind, "CITED_ONLY")
        # 变体写法同样命中
        self.assertEqual(classify_non_evidence({"support_type": "referenced only"}),
                         "CITED_ONLY")

    def test_first_round_seven_spellings_stay_blocked(self):
        for label, cls in (("NOT_REPORTED", "NOT_REPORTED"), ("NOT REPORTED", "NOT_REPORTED"),
                           ("NR", "NOT_REPORTED"), ("unchecked", "UNCHECKED"),
                           ("UNCHECKED", "UNCHECKED"), ("inaccessible", "INACCESSIBLE"),
                           ("cited_only", "CITED_ONLY")):
            weight, kind, _ = resolve_evidence_weight(
                _claim("C", "P", "SUPPORT", support_type=label))
            self.assertEqual(weight, 0.0, label)
            self.assertEqual(kind, cls, label)

    def test_field_absence_is_not_a_declaration(self):
        """support_type 缺失 = 未声明，权重交 evidence_strength（合法 CLI 主张形状）。"""
        self.assertIsNone(classify_non_evidence(
            _claim("C", "P", "SUPPORT")))
        weight, kind, _ = resolve_evidence_weight(_claim("C", "P", "SUPPORT"))
        self.assertEqual(weight, 1.0)
        self.assertEqual(kind, "DIRECT_EMPIRICAL")

    def test_flagship_period_escape_no_longer_flips_level(self):
        """adversary f01d/f01e 最小翻转夹具：句号写法与空格写法同层，均不得入共识。"""
        baseline = [_claim("CLM-001", "Liu2020", "SUPPORT",
                           support_type="NOT REPORTED", independence_group_id="G1"),
                    _claim("CLM-002", "Wang2021", "SUPPORT",
                           support_type="NOT REPORTED", independence_group_id="G2")]
        escaped = [_claim("CLM-001", "Liu2020", "SUPPORT",
                          support_type="Not reported.", independence_group_id="G1"),
                   _claim("CLM-002", "Wang2021", "SUPPORT",
                          support_type="Not reported.", independence_group_id="G2")]
        for claims in (baseline, escaped):
            res = compute_topic_consensus(claims)
            self.assertEqual(res["consensus_classification"], "INSUFFICIENT_EVIDENCE")
            self.assertEqual(res["excluded_from_consensus"].get("NOT_REPORTED"), 2)


class TestH06InvalidStance(unittest.TestCase):
    """H-06：词表外 stance 不再静默归 NEUTRAL 入分母——标志 + 排除 + 原值进产物。"""

    def _baseline(self):
        return [_claim("CLM-001", "Liu2020", "SUPPORT"),
                _claim("CLM-002", "Wang2021", "SUPPORT"),
                _claim("CLM-003", "Li2019", "REFUTE")]

    def test_out_of_vocabulary_stances_leave_the_denominator(self):
        """adversary f02b 族：REFUTES/REFUTED/数字/空值三类夹具出分母且计数。"""
        for bad in ("REFUTES", "REFUTED", "OPPOSED", 7, "", None):
            with self.subTest(stance=bad):
                claims = self._baseline() + [_claim("CLM-004", "Chen2022", bad)]
                res = compute_topic_consensus(claims)
                self.assertEqual(res["excluded_from_consensus"].get("INVALID_STANCE"), 1)
                self.assertNotIn("INVALID_STANCE", (res["stance_weights"]))
                # 分母只含合法三方向：2 SUPPORT + 1 REFUTE
                self.assertAlmostEqual(res["stance_weights"]["SUPPORT"], 2.0, places=2)
                self.assertAlmostEqual(res["stance_weights"]["REFUTE"], 1.0, places=2)

    def test_stance_original_reaches_artifacts(self):
        claims = self._baseline() + [_claim("CLM-004", "Chen2022", "REFUTED")]
        res = compute_topic_consensus(claims)
        records = res["invalid_stance_records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["claim_id"], "CLM-004")
        self.assertEqual(records[0]["stance_original"], "REFUTED")
        summary = format_summary_report({TOPIC: res})
        self.assertIn("InvalidStance: CLM-004 (stance_original=REFUTED)", summary)
        headline = analyze(claims)[TOPIC]
        markdown = format_markdown_report({TOPIC: headline})
        self.assertIn("stance_original=`REFUTED`", markdown)
        self.assertIn("排除与拒绝计数", markdown)

    def test_legal_four_values_and_contract_vocabulary_unchanged(self):
        """合法四值 + 契约六值映射 byte-identical：立场/原值/映射标记全不变。"""
        for raw, mapped, original in (("SUPPORT", "SUPPORT", "SUPPORT"),
                                      ("REFUTE", "REFUTE", "REFUTE"),
                                      ("CONDITIONAL", "CONDITIONAL", "CONDITIONAL"),
                                      ("NEUTRAL", "NEUTRAL", "NEUTRAL"),
                                      ("OPPOSE", "REFUTE", "OPPOSE"),
                                      ("MIXED", "NEUTRAL", "MIXED")):
            n = normalize_claim(_claim("C", "P", raw))
            self.assertEqual(n["stance"], mapped)
            self.assertEqual(n["stance_original"], original)
            self.assertFalse(n["invalid_stance"])
            self.assertEqual(n["stance_was_mapped"], mapped != original)

    def test_does_not_raise(self):
        for bad in ("REFUTED", 7, None, "", {"a": 1}):
            analyze(self._baseline() + [_claim("CLM-004", "Chen2022", bad)])


class TestH50IndependenceWhitelist(unittest.TestCase):
    """H-50：独立组判定改正向白名单——仅 VERIFIED（含写法变体）算已验证独立。"""

    def _pair(self, status_a="VERIFIED", status_b="VERIFIED", **over_a):
        return [_claim("CLM-001", "Liu2020", "SUPPORT",
                       independence_group_id="G1", independence_status=status_a, **over_a),
                _claim("CLM-002", "Wang2021", "SUPPORT",
                       independence_group_id="G2", independence_status=status_b)]

    def test_unverified_and_missing_cannot_reach_level_1(self):
        """adversary f03a/f03c：UNVERIFIED / 缺失 → Level 2（MODERATE），不得 Level 1。"""
        for status_a in ("UNVERIFIED", None, "unknown", " UNKNOWN ", "ASSUMED",
                         "SELF_CITATION"):
            with self.subTest(status=status_a):
                claims = self._pair(status_a=status_a, status_b=None)
                res = compute_topic_consensus(claims)
                self.assertNotEqual(res["consensus_classification"], "STRONG_CONSENSUS",
                                    status_a)
                self.assertEqual(res["consensus_level"].split(" ")[0], "Level", status_a)

    def test_verified_still_reaches_level_1(self):
        res = compute_topic_consensus(self._pair())
        self.assertEqual(res["consensus_classification"], "STRONG_CONSENSUS")

    def test_lowercase_variant_of_verified_counts(self):
        res = compute_topic_consensus(self._pair(status_a="verified"))
        self.assertEqual(res["consensus_classification"], "STRONG_CONSENSUS")


class TestH52ChallengeStatusGate(unittest.TestCase):
    """H-52：反证分流只认 relation=CHALLENGE（或真实反证状态等价路径）。"""

    def _baseline(self):
        return [_claim("CLM-001", "Liu2020", "SUPPORT", independence_group_id="Liu2020"),
                _claim("CLM-002", "Wang2021", "SUPPORT", independence_group_id="Wang2021"),
                _claim("CLM-003", "Wu2023", "SUPPORT", independence_group_id="Wu2023"),
                _claim("CLM-004", "Li2019", "REFUTE", independence_group_id="Li2019")]

    def test_rejected_challenge_status_returns_to_voting(self):
        """adversary f05d→f05e：REJECTED 反证不再吞掉真实异议，75% 不翻 100%。"""
        baseline = compute_topic_consensus(self._baseline())
        self.assertEqual(baseline["consensus_classification"], "MODERATE_CONSENSUS")
        self.assertAlmostEqual(baseline["stance_percentages"]["SUPPORT"], 75.0, places=1)

        suppressed = [_claim("CLM-004", "Li2019", "REFUTE",
                             independence_group_id="Li2019",
                             challenge_status="REJECTED",
                             target_claim_id="CLM-001")]
        res = compute_topic_consensus(self._baseline() + suppressed)
        self.assertEqual(res["consensus_classification"], "MODERATE_CONSENSUS")
        self.assertAlmostEqual(res["stance_percentages"]["SUPPORT"], 75.0, places=1)
        self.assertAlmostEqual(res["stance_weights"]["REFUTE"], 1.0, places=2)
        self.assertNotIn("CHALLENGE_EVIDENCE", res["excluded_from_consensus"])

    def test_arbitrary_truthy_status_also_returns_to_voting(self):
        """adversary f05c：challenge_status="X" 任意非空值同样不再逐出投票。"""
        rows = [_claim("CLM-004", "Li2019", "REFUTE",
                       independence_group_id="Li2019",
                       challenge_status="X", target_claim_id="CLM-001")]
        res = compute_topic_consensus(self._baseline() + rows)
        self.assertAlmostEqual(res["stance_weights"]["REFUTE"], 1.0, places=2)

    def test_relation_challenge_still_diverted_even_if_rejected(self):
        """relation=CHALLENGE 的行仍进反证分流（REJECTED 状态不再施加罚则）。"""
        challenge = dict(_claim("CH-1", "GhostA", "REFUTE",
                                independence_group_id="GA"),
                         relation="CHALLENGE", challenge_status="REJECTED",
                         challenge_strength="REFUTES", target_claim_id="CLM-001")
        res = compute_topic_consensus(self._baseline() + [challenge])
        self.assertEqual(res["excluded_from_consensus"].get("CHALLENGE_EVIDENCE"), 1)
        self.assertEqual(res["challenge_adjustment"]["applied"], False)

    def test_genuine_status_without_relation_is_still_a_challenge(self):
        """等价判定路径：缺 relation 但状态为真实反证状态的行仍不分流为立场投票。"""
        challenge = dict(_claim("CH-1", "GhostA", "REFUTE",
                                independence_group_id="GA"),
                         challenge_status="VERIFIED_CHALLENGE",
                         challenge_strength="REFUTES", target_claim_id="CLM-001")
        res = compute_topic_consensus(self._baseline() + [challenge])
        self.assertEqual(res["excluded_from_consensus"].get("CHALLENGE_EVIDENCE"), 1)


class TestH07ChallengeChannelStembleed(unittest.TestCase):
    """H-07 止血：scope 枚举校验（GALAXY 截获）、凭据矛盾不罚、factors 披露三量。"""

    def _baseline(self):
        return [_claim("CLM-001", "Liu2020", "SUPPORT", independence_group_id="Liu2020"),
                _claim("CLM-002", "Wang2021", "SUPPORT", independence_group_id="Wang2021"),
                _claim("CLM-003", "Li2019", "REFUTE", independence_group_id="Li2019")]

    @staticmethod
    def _challenge(cid, pid, target, group, scope, **over):
        row = dict(_claim(cid, pid, "REFUTE", independence_group_id=group),
                   relation="CHALLENGE", challenge_status="VERIFIED_CHALLENGE",
                   challenge_strength="REFUTES", target_claim_id=target,
                   challenge_scope=scope, challenge_basis="irrelevant lorem ipsum")
        row.update(over)
        return row

    def test_galaxy_scope_is_intercepted_baseline_not_zeroed(self):
        """adversary f04h：4 条 scope=GALAXY 伪造反证 → 惩罚归零，66.7% 基线不降级。"""
        claims = self._baseline() + [
            self._challenge("CH-1", "GhostA", "CLM-001", "A", "GALAXY"),
            self._challenge("CH-2", "GhostB", "CLM-001", "B", "GALAXY"),
            self._challenge("CH-3", "GhostC", "CLM-002", "C", "GALAXY"),
            self._challenge("CH-4", "GhostD", "CLM-002", "D", "GALAXY"),
        ]
        res = compute_topic_consensus(claims)
        self.assertAlmostEqual(res["stance_percentages"]["SUPPORT"], 66.7, places=1)
        self.assertNotEqual(res["consensus_classification"], "INSUFFICIENT_EVIDENCE")
        rejected = res["challenge_adjustment"]["scope_rejected_challenges"]
        self.assertEqual(len(rejected), 4)
        self.assertEqual({r["scope"] for r in rejected}, {"GALAXY"})
        self.assertFalse(res["challenge_adjustment"]["applied"])

    def test_contradictory_verification_no_penalty(self):
        """adversary f04c：challenge_verification=UNVERIFIED 与顶层 VERIFIED_CHALLENGE
        矛盾 → 不罚 + 告警披露。"""
        claims = self._baseline() + [
            self._challenge("CH-1", "GhostA", "CLM-001", "A", "MAGNITUDE",
                            challenge_verification={"status": "UNVERIFIED"}),
            self._challenge("CH-2", "GhostB", "CLM-002", "B", "MAGNITUDE",
                            challenge_verification={"status": "REJECTED"}),
        ]
        res = compute_topic_consensus(claims)
        self.assertAlmostEqual(res["stance_percentages"]["SUPPORT"], 66.7, places=1)
        conflicts = res["challenge_adjustment"]["verification_conflict_challenges"]
        self.assertEqual(len(conflicts), 2)
        self.assertEqual({c["verification_status"] for c in conflicts},
                         {"UNVERIFIED", "REJECTED"})
        self.assertFalse(res["challenge_adjustment"]["applied"])

    def test_out_of_enum_scope_is_intercepted(self):
        """adversary f04d：scope=ENTIRE_TOPIC_AND_BEYOND（上游枚举外）→ 不罚。"""
        claims = self._baseline() + [
            self._challenge("CH-1", "GhostA", "CLM-001", "A", "ENTIRE_TOPIC_AND_BEYOND"),
        ]
        res = compute_topic_consensus(claims)
        self.assertAlmostEqual(res["stance_weights"]["SUPPORT"], 2.0, places=2)
        self.assertEqual(len(res["challenge_adjustment"]["scope_rejected_challenges"]), 1)

    def test_declared_legal_scope_still_penalizes(self):
        """adversary f04b：合法 scope（MAGNITUDE）的自声明反证照旧有界生效（RFC-017）。"""
        claims = self._baseline() + [
            self._challenge("CH-1", "GhostReview2024", "CLM-001", None, "MAGNITUDE"),
            self._challenge("CH-2", "GhostReview2024", "CLM-002", None, "MAGNITUDE"),
        ]
        res = compute_topic_consensus(claims)
        # 同组 REFUTES×2（组 raw 1.00 → capped 0.50），两条被挑战支持主张各被扣 0.25×2：
        # 2.0 → 1.0（adversary 实测 "支持权重 2.0→1.0"）
        self.assertAlmostEqual(res["stance_weights"]["SUPPORT"], 1.0, places=2)
        self.assertTrue(res["challenge_adjustment"]["applied"])
        self.assertEqual(res["challenge_adjustment"]["factors"].count(
            "challenge(GhostReview2024:-0.50)"), 2)

    def test_missing_scope_keeps_legacy_semantics(self):
        """既有合法链路（无 scope 字段，tests/test_rfc017）不受止血影响。"""
        penalty, _ = challenge_penalty([
            {"challenge_status": "VERIFIED_CHALLENGE", "challenge_strength": "REFUTES",
             "independence_group_id": "G1"}])
        self.assertEqual(penalty, 0.5)

    def test_factors_disclose_raw_capped_and_applied(self):
        """罚前 / 封顶后 / 罚后三量全部可见（同组 5×REFUTES：2.50 → 0.50）。"""
        many = [self._challenge("CH-%d" % i, "Ghost%d" % i, "CLM-001", "GCAP",
                                "MECHANISM") for i in range(5)]
        penalty, factors = challenge_penalty(many)
        self.assertEqual(penalty, 0.5)
        self.assertIn("challenge_group_raw(GCAP: 2.50)", factors)
        self.assertIn("challenge_group_capped(GCAP: 2.50->0.50)", factors)
        self.assertIn("challenge(GCAP:-0.50)", factors)


class TestH53WordBagPropositionSwap(unittest.TestCase):
    """H-53：词袋相等但语序不等（主宾互换）→ UNRESOLVED；原语序仍 VERIFIED。"""

    def test_subject_object_swap_is_unresolved(self):
        """adversary REPORT §H.E 两个实测载荷。"""
        for src, tgt in (("Soil nitrogen increases plant growth",
                          "Plant growth increases soil nitrogen"),
                         ("N addition decreases soil pH",
                          "Soil pH decreases N addition")):
            status, _ = check_target_proposition_compatibility(src, tgt)
            self.assertEqual(status, "UNRESOLVED", src)

    def test_original_order_stays_verified_paired(self):
        for text in ("Soil nitrogen increases plant growth",
                     "N addition decreases soil pH"):
            status, _ = check_target_proposition_compatibility(text, text)
            self.assertEqual(status, "VERIFIED_SAME_PROPOSITION", text)

    def test_synonym_rewording_still_verified(self):
        status, _ = check_target_proposition_compatibility(
            "Soil nitrogen increases plant growth",
            "Soil nitrogen stimulates plant growth")
        self.assertEqual(status, "VERIFIED_SAME_PROPOSITION")

    def test_swapped_claim_is_rejected_by_eligibility(self):
        """与 H-49 联动：UNRESOLVED 映射的主张不得入共识。"""
        evidence = {"evidence_id": "EV-53", "record_id": "REC-53",
                    "claim_status": "SUPPORTED",
                    "source_target_claim": "Soil nitrogen increases plant growth",
                    "evidence_strength": "DIRECT_EMPIRICAL"}
        claim = map_evidence_to_claim(
            evidence,
            {"topic": "T", "target_claim": "Plant growth increases soil nitrogen"})
        self.assertEqual(claim["stance"], "NEUTRAL")
        self.assertEqual(claim["stance_mapping_status"], "UNRESOLVED")
        eligible, issues = evaluate_consensus_eligibility(claim)
        self.assertFalse(eligible)
        self.assertIn("UNRESOLVED", issues)


class TestH49EligibilityWiring(unittest.TestCase):
    """H-49/H-91：资格门禁接入生产路径；UNRESOLVED/缺 claim_status 拒绝；NEUTRAL 出分母。"""

    def test_missing_claim_status_no_longer_defaults_supported(self):
        """adversary §H.D：缺 claim_status 不得默认 SUPPORTED、不得盖 E1 章直通。"""
        evidence = {"evidence_id": "EV-1", "record_id": "R1",
                    "evidence_strength": "DIRECT_EMPIRICAL",
                    "independence_group_id": "G1"}
        claim = map_evidence_to_claim(evidence, {"topic": "T", "target_claim": "t claim"})
        self.assertEqual(claim["stance"], "NEUTRAL")
        eligible, issues = evaluate_consensus_eligibility(claim)
        self.assertFalse(eligible)
        self.assertTrue(any("NEUTRAL" in i for i in issues))

    def test_unresolved_mapping_rejected_without_audited_index(self):
        claim = {"claim_id": "CLM-U", "topic": "T", "paper_id": "P", "claim": "c",
                 "stance": "SUPPORT", "evidence_strength": "DIRECT_EMPIRICAL",
                 "stance_mapping_status": "UNRESOLVED"}
        eligible, issues = evaluate_consensus_eligibility(claim)
        self.assertFalse(eligible)
        self.assertIn("UNRESOLVED", issues)
        self.assertIn("UNRESOLVED", claim_consensus_issues(claim))

    def test_unresolved_mapping_exempt_only_when_fully_audited(self):
        """豁免仅限 AUDITED_CANONICAL 下证据索引逐条核验通过（tests/test_g 契约）。"""
        claim = {"claim_id": "CLM-U", "topic": "T", "paper_id": "P", "claim": "c",
                 "stance": "SUPPORT", "evidence_strength": "DIRECT_EMPIRICAL",
                 "evidence_ids": ["EV-OK"], "stance_mapping_status": "UNRESOLVED"}
        ev = {"evidence_id": "EV-OK", "claim_status": "SUPPORTED",
              "support_type": "EXPLICIT", "evidence_strength": "DIRECT_EMPIRICAL"}
        eligible, _ = evaluate_consensus_eligibility(claim, {"EV-OK": ev})
        self.assertTrue(eligible)

    def test_declared_non_bearing_claim_status_rejected(self):
        claim = {"claim_id": "CLM-CS", "topic": "T", "paper_id": "P", "claim": "c",
                 "stance": "SUPPORT", "evidence_strength": "DIRECT_EMPIRICAL",
                 "claim_status": "UNSUPPORTED"}
        self.assertIn("CLAIM_STATUS_UNSUPPORTED", claim_consensus_issues(claim))
        claims = [_claim("C1", "P1", "SUPPORT"),
                  dict(claim, topic=TOPIC)]
        res = compute_topic_consensus(claims)
        self.assertEqual(res["excluded_from_consensus"].get("CLAIM_STATUS_UNSUPPORTED"), 1)

    def test_neutral_leaves_denominator(self):
        """H-91：NEUTRAL 行出分母（1 S + 1 R + 2 NEUTRAL → 支持比 50% 而非 25%）。"""
        claims = [_claim("C1", "P1", "SUPPORT"),
                  _claim("C2", "P2", "REFUTE"),
                  _claim("C3", "P3", "NEUTRAL"),
                  _claim("C4", "P4", "NEUTRAL")]
        res = compute_topic_consensus(claims)
        self.assertEqual(res["excluded_from_consensus"].get("NEUTRAL"), 2)
        self.assertAlmostEqual(res["stance_percentages"]["SUPPORT"], 50.0, places=1)
        self.assertAlmostEqual(res["stance_percentages"]["REFUTE"], 50.0, places=1)

    def test_runner_15_of_38_scenario_excluded_non_empty(self):
        """verifier REPORT §4.4：15/38 audit 不合格行（13 NEUTRAL + 2 REFERENCED_ONLY）
        此前 engine-eligible 无痕；接入后 excluded_from_consensus 必须非空且逐行可数。"""
        claims = []
        # 2 条合格 SUPPORT（真实独立组）
        claims.append(_runner_row("CLM-OK-1", "P-OK1", "SUPPORT", "G-OK1"))
        claims.append(_runner_row("CLM-OK-2", "P-OK2", "SUPPORT", "G-OK2"))
        # 1 条合格 REFUTE
        claims.append(_runner_row("CLM-OK-3", "P-OK3", "REFUTE", "G-OK3"))
        # 1 条 UNRESOLVED 映射（层内另册）
        claims.append(_runner_row("CLM-UR", "P-UR", "SUPPORT", "G-UR",
                                  stance_mapping_status="UNRESOLVED"))
        # 13 条 NEUTRAL 背景行（runner 真实分布：21 NEUTRAL 中 13 条非 NR）
        for i in range(13):
            claims.append(_runner_row("CLM-N-%02d" % i, "P-N%02d" % i, "NEUTRAL",
                                      "G-N%02d" % i))
        # 2 条 REFERENCED_ONLY（层A core 曾依赖的二级转引 SUPPORT 行）
        claims.append(_runner_row("CLM-RO-1", "P-RO1", "SUPPORT", "G-RO1",
                                  claim_status_upstream="REFERENCED_ONLY"))
        claims.append(_runner_row("CLM-RO-2", "P-RO2", "SUPPORT", "G-RO2",
                                  claim_status_upstream="REFERENCED_ONLY"))
        res = compute_topic_consensus(claims)
        excluded = res["excluded_from_consensus"]
        self.assertTrue(excluded)
        self.assertEqual(excluded.get("NEUTRAL"), 13)
        self.assertEqual(excluded.get("CLAIM_STATUS_REFERENCED_ONLY"), 2)
        self.assertEqual(excluded.get("UNRESOLVED"), 1)
        self.assertEqual(res["consensus_eligible_claims"], 3)

    def test_referenced_only_support_rows_do_not_inflate_strong(self):
        """层A 降级语义：REFERENCED_ONLY 的 SUPPORT 权重不得进层内支持权重。"""
        with_ref = [_runner_row("CLM-RO-1", "P-RO1", "SUPPORT", "G-RO1",
                                claim_status_upstream="REFERENCED_ONLY"),
                    _runner_row("CLM-RO-2", "P-RO2", "SUPPORT", "G-RO2",
                                claim_status_upstream="REFERENCED_ONLY")]
        res = compute_topic_consensus(with_ref)
        self.assertEqual(res["stance_weights"].get("SUPPORT", 0.0), 0.0)
        self.assertEqual(res["consensus_classification"], "INSUFFICIENT_EVIDENCE")


class TestH54AppraisalEvasion(unittest.TestCase):
    """H-54：appraisal 拼写逃逸——HIGH_RISK/VERY_LOW 受罚且有专属标记。"""

    def test_evasive_spellings_are_penalized_and_marked(self):
        """adversary f07：EvasiveHighRisk / EvasiveVeryLow 与诚实声明同权。"""
        honest = resolve_evidence_weight(
            _claim("C", "HonestHigh", "SUPPORT",
                   appraisal={"risk_of_bias": "HIGH"}))
        evasive_high = resolve_evidence_weight(
            _claim("C", "EvasiveHighRisk", "SUPPORT",
                   appraisal={"risk_of_bias": "HIGH_RISK"}))
        evasive_low = resolve_evidence_weight(
            _claim("C", "EvasiveVeryLow", "SUPPORT",
                   appraisal={"directness": "VERY_LOW"}))
        self.assertEqual(honest[0], 0.6)
        self.assertEqual(evasive_high[0], 0.6)
        self.assertEqual(evasive_low[0], 0.6)
        self.assertIn("appraisal_nonstandard(risk_of_bias=HIGH_RISK->HIGH)", evasive_high[2])
        self.assertIn("bias_high(-0.3)", evasive_high[2])
        self.assertIn("appraisal_nonstandard(directness=VERY_LOW->LOW)", evasive_low[2])
        self.assertIn("indirect(-0.2)", evasive_low[2])

    def test_out_of_vocabulary_value_is_flagged(self):
        weight, _, factors = resolve_evidence_weight(
            _claim("C", "P", "SUPPORT", appraisal={"risk_of_bias": "SUPER_HIGH"}))
        self.assertIn("appraisal_invalid(risk_of_bias=SUPER_HIGH)", factors)
        self.assertIn("appraisal_incomplete", factors)

    def test_weight_factors_reach_normalized_claim(self):
        n = normalize_claim(_claim("C", "P", "SUPPORT",
                                   appraisal={"risk_of_bias": "HIGH_RISK"}))
        self.assertIn("appraisal_nonstandard(risk_of_bias=HIGH_RISK->HIGH)",
                      n["weight_factors"])


class TestFacility1SummaryCounts(unittest.TestCase):
    """设施-1 最低版：UNRESOLVED / UNPARSEABLE / INVALID_STANCE 等每次拒绝可读数。"""

    def test_summary_and_markdown_expose_counts(self):
        claims = [
            _claim("C1", "P1", "SUPPORT"),
            _claim("C2", "P2", "SUPPORT", support_type="NOT REPORTED"),
            _claim("C3", "P3", "REFUTED"),
            _claim("C4", "P4", "SUPPORT", support_type=""),
            dict(_claim("C5", "P5", "SUPPORT"), stance_mapping_status="UNRESOLVED"),
        ]
        res = compute_topic_consensus(claims)
        excluded = res["excluded_from_consensus"]
        self.assertEqual(excluded.get("NOT_REPORTED"), 1)
        self.assertEqual(excluded.get("INVALID_STANCE"), 1)
        self.assertEqual(excluded.get(UNPARSEABLE_CLASS), 1)
        self.assertEqual(excluded.get("UNRESOLVED"), 1)

        summary = format_summary_report({TOPIC: res})
        self.assertIn("Excluded: INVALID_STANCE=1, NOT_REPORTED=1, UNPARSEABLE=1, UNRESOLVED=1",
                      summary)
        markdown = format_markdown_report({TOPIC: analyze(claims)[TOPIC]})
        self.assertIn("暂无专用裁决队列", markdown)
        for key in ("NOT_REPORTED", "INVALID_STANCE", "UNPARSEABLE", "UNRESOLVED"):
            self.assertIn("`%s`" % key, markdown)

    def test_clean_input_renders_no_exclusion_section(self):
        claims = [_claim("C1", "P1", "SUPPORT"),
                  _claim("C2", "P2", "REFUTE")]
        res = compute_topic_consensus(claims)
        summary = format_summary_report({TOPIC: res})
        self.assertNotIn("Excluded:", summary)
        markdown = format_markdown_report({TOPIC: analyze(claims)[TOPIC]})
        self.assertNotIn("排除与拒绝计数", markdown)

    def test_canonical_records_shape_unchanged(self):
        """合法输入的 canonical 记录键集不变（byte-identical 契约的形状面）。"""
        results = analyze([_claim("C1", "P1", "SUPPORT"),
                           _claim("C2", "P2", "REFUTE")])
        records = to_canonical_synthesis_records(results)
        self.assertEqual(len(records), 1)
        self.assertEqual(set(records[0].keys()),
                         {"schema_version", "topic", "total_claims",
                          "consensus_classification", "heuristic_balance_score",
                          "controversy_diagnosis"})
        payload = json.dumps(records, ensure_ascii=False, sort_keys=True)
        self.assertIn("ACTIVE_CONTROVERSY", payload)


class TestP1SelfDeclaredNonEvidenceCannotDisableTheGate(unittest.TestCase):
    """P1（2026-09-15 集群审查）：自声明的空值不得成为门禁关停开关。

    旧 `resolve_non_evidence_class` 只要 `"non_evidence_class" in record` 就无条件返回
    其值，而 `load_input_data()` 接受宿主 Agent 任意构造的 claim 对象——给一条
    `support_type="NOT REPORTED"` 的记录加 `"non_evidence_class": null` 即可跳过全部
    状态字段分类，该记录改由 `evidence_strength` 计权。实测伪造后 weight=1.0、
    consensus_eligible=True、excluded_from_consensus 为空，3 条即产出
    Level 1「Strong Prevailing Consensus - Replicated Evidence」。
    这正是本套件威胁模型要防的「把自声明字段当授权依据」。
    """

    BASE = {"topic": "forged gate", "support_type": "NOT REPORTED",
            "evidence_strength": "DIRECT_EMPIRICAL"}

    def test_falsy_self_declaration_cannot_disable_classification(self):
        for extra in ({}, {"non_evidence_class": None}, {"non_evidence_class": ""}):
            with self.subTest(extra=extra):
                n = ca.normalize_claim(dict(self.BASE, **extra))
                self.assertEqual(n["weight"], 0.0,
                                 "非证据记录必须零权（自声明空值不得放行）")
                self.assertFalse(n["consensus_eligible"])

    def test_explicit_null_support_type_is_still_unparseable(self):
        """治源不得削弱 H-05：宿主显式给 null 仍须 fail-closed。"""
        n = ca.normalize_claim({"topic": "t", "support_type": None,
                                "evidence_strength": "DIRECT_EMPIRICAL"})
        self.assertEqual(n["weight"], 0.0)
        self.assertFalse(n["consensus_eligible"])

    def test_normalization_is_idempotent(self):
        """归一化产物再归一化结果必须一致（短路移除的前提）。"""
        n1 = ca.normalize_claim(dict(self.BASE))
        n2 = ca.normalize_claim(n1)
        self.assertEqual(n1["weight"], n2["weight"])
        self.assertEqual(n1["consensus_eligible"], n2["consensus_eligible"])
        self.assertFalse(n1["consensus_eligible"])

    def test_ordinary_evidence_record_keeps_full_weight(self):
        """反向：正常证据记录不得被误判出局。"""
        n = ca.normalize_claim({"topic": "t", "support_type": "EXPLICIT",
                                "evidence_strength": "DIRECT_EMPIRICAL",
                                "stance": "SUPPORT", "claim_status": "SUPPORTED"})
        self.assertGreater(n["weight"], 0.0)


if __name__ == "__main__":
    unittest.main()

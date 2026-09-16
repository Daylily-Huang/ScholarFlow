# -*- coding: utf-8 -*-
"""synthesis 技能 P2 回归（2026-09-16 集群审查）。

覆盖：抽取域 canonical 的 `REFERENCED` 必须与非证据同层零权（P2-23）、
`stance_mapping_status` 的大小写/空白变体不得绕过硬门禁（P2-24）、
schema 合法的 `replication=MEDIUM` 不得被判非法（P2-25）、
`S12 交付格式` 必须真的登记在引擎里（P2-27）。
（P2-26 / P2-29 为文档口径更正，无代码行为可断言。）
"""

import json
import sys
import unittest
from pathlib import Path

import helpers  # noqa: F401

REPO_ROOT = helpers.REPO_ROOT
SCRIPTS = REPO_ROOT / "skills" / "literature-synthesis" / "scripts"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SCRIPTS))

from evidence_states import resolve_non_evidence_class  # noqa: E402
from evidence_to_claim import claim_consensus_issues  # noqa: E402
from controversy_analyzer import normalize_claim  # noqa: E402
from shared.grill_me.dimensions import get_synthesis_dimensions  # noqa: E402


class TestReferencedSupportTypeIsNonEvidence(unittest.TestCase):
    """P2-23：`REFERENCED` 是抽取域 `support_type` 的 canonical 取值。

    SKILL.md §四 明定转引他文的行必须是 `support_type=REFERENCED`（E3 二手证据），
    由抽取侧 `_resolve_support_type` 产出。而 synthesis 的非证据表此前只列
    `REFERENCED_ONLY` / `CITED_ONLY`——两侧词表对不上，**二级转引以满权重进入共识分母**。
    """

    def test_referenced_is_zero_weight(self):
        for support_type in ("REFERENCED", "REFERENCED_ONLY", "CITED_ONLY"):
            with self.subTest(support_type=support_type):
                rec = {"support_type": support_type}
                self.assertEqual(resolve_non_evidence_class(rec), "CITED_ONLY")
                norm = normalize_claim(dict(rec, topic="t", stance="SUPPORT",
                                            evidence_strength="DIRECT_EMPIRICAL"))
                self.assertEqual(norm["weight"], 0.0)
                self.assertFalse(norm["consensus_eligible"])

    def test_ordinary_evidence_still_carries_weight(self):
        norm = normalize_claim({"topic": "t", "support_type": "EXPLICIT", "stance": "SUPPORT",
                                "evidence_strength": "DIRECT_EMPIRICAL"})
        self.assertGreater(norm["weight"], 0.0)
        self.assertTrue(norm["consensus_eligible"])


class TestStanceMappingStatusIsNormalised(unittest.TestCase):
    """P2-24：原为精确、大小写敏感的比较——`"unresolved"` 变体绕过拒绝门禁。"""

    def test_case_and_whitespace_variants_are_caught(self):
        for value in ("UNRESOLVED", "unresolved", "Unresolved", " unresolved ",
                      "diFFerent_proposition"):
            with self.subTest(value=value):
                issues = claim_consensus_issues({"stance_mapping_status": value})
                self.assertTrue(issues, "%r 绕过了拒绝门禁" % value)

    def test_unrelated_value_is_not_flagged(self):
        """无关取值不得被误判为 UNRESOLVED / DIFFERENT_PROPOSITION。

        （未声明 evidence_strength 时本函数会另有 NO_EVIDENCE_STRENGTH，属正常，
        故只断言这两个拒绝码缺席。）
        """
        issues = claim_consensus_issues({"stance_mapping_status": "SAME_PROPOSITION"})
        self.assertNotIn("UNRESOLVED", issues)
        self.assertNotIn("DIFFERENT_PROPOSITION", issues)


class TestAppraisalReplicationMediumIsLegal(unittest.TestCase):
    """P2-25：`directness`/`independence`/`risk_of_bias` 都接受 MEDIUM，唯独
    `replication` 只认 HIGH/LOW——schema 未对 appraisal 设枚举，`MEDIUM` 是**合法输入**
    却被判非法值并按 UNKNOWN 处理。"""

    def _factors(self, replication):
        norm = normalize_claim({"topic": "t", "support_type": "EXPLICIT", "stance": "SUPPORT",
                                "evidence_strength": "DIRECT_EMPIRICAL",
                                "appraisal": {"replication": replication}})
        return norm["weight"], norm["weight_factors"]

    def test_medium_is_accepted_and_recorded(self):
        weight, factors = self._factors("MEDIUM")
        self.assertEqual(weight, 1.0, "MEDIUM 为中性档，不调权")
        self.assertTrue(any("replication_medium" in f for f in factors),
                        "MEDIUM 必须留痕，否则与『未声明』不可区分：%s" % factors)
        self.assertFalse(any("invalid" in f for f in factors),
                         "MEDIUM 不得被判非法值：%s" % factors)

    def test_high_and_low_still_adjust(self):
        self.assertEqual(self._factors("HIGH")[0], 1.1)
        self.assertEqual(self._factors("LOW")[0], 0.9)

    def test_genuinely_invalid_value_is_still_flagged(self):
        _weight, factors = self._factors("WEIRD")
        self.assertTrue(any("invalid" in f for f in factors), factors)


class TestS12DeliveryFormatIsRegistered(unittest.TestCase):
    """P2-27：`S12 交付格式` 必须在引擎里真的存在。

    它一直出现在技能维度表里，但被**重号成 S10** 且从未登记进引擎——SKILL.md 声称的
    「默认三轨全套并写入快照 [DEFAULTED]」在引擎侧因此根本不成立。
    """

    def test_synthesis_dimensions_are_s1_to_s12(self):
        ids = [d.id for d in get_synthesis_dimensions()]
        self.assertEqual(len(ids), 12)
        self.assertEqual(sorted(ids, key=lambda s: int(s[1:])),
                         ["S%d" % i for i in range(1, 13)])

    def test_s12_has_a_recommended_option(self):
        s12 = next(d for d in get_synthesis_dimensions() if d.id == "S12")
        rec = s12.get_recommended_option()
        self.assertIsNotNone(rec, "S12 缺推荐选项，引擎无法自动应用默认值")
        self.assertTrue(rec.rationale)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_alignment_and_semantics.py — 回归测试：关系门禁与语义角色分类

对应 2026-09-11 多 Agent 压测实测缺陷：
  D5 classify_semantic_role 对中文 5/5 返回 UNKNOWN，且英文 "This suggests…"
     （Discussion 推测）同样落 UNKNOWN —— 分类器是纯英文规则，"严禁将 Discussion
     推测记为结论"这条铁律在中文语料上完全没有被执行
  D6 claim_alignment.py 无 CLI（文档却把它列为辅助工具）
  D8 【新发现】关系型主张若不带 subject/predicate/object，会因
     _check_predicate_grounding 对空谓词 return True 而被判 SUPPORTED /
     is_confirmed_eligible=true —— A2 门禁的 fail-closed 破口

运行：python3 tests/test_alignment_and_semantics.py
"""
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills" / "literature-evidence-extraction" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from context_expansion import classify_semantic_role  # noqa: E402
from claim_alignment import (  # noqa: E402
    detect_extraction_semantics, verify_claim_alignment,
)

CLAIM_ALIGNMENT_CLI = SCRIPTS / "claim_alignment.py"

EVIDENCE = ("Shrubs were the most important food of black muntjac, "
            "accounting for 55.4% of the diet.")


# ---------------------------------------------------------------- D5

class SemanticRoleCJKTests(unittest.TestCase):
    """分类器必须对中文有区分度（修复前 5/5 UNKNOWN）。"""

    def test_chinese_result(self):
        r, _ = classify_semantic_role(
            "黑麂的食物，主要是种子植物的枝叶。在33个胃中，共鉴定种子植物有23科32种。")
        self.assertEqual(r, "CURRENT_STUDY_RESULT")

    def test_chinese_method(self):
        r, _ = classify_semantic_role("本研究采用粪便显微组织学分析方法。")
        self.assertEqual(r, "CURRENT_STUDY_METHOD")

    def test_chinese_discussion_speculation(self):
        r, _ = classify_semantic_role("黑麂可能偏好取食三尖杉，这可能与针叶林的食物资源有关。")
        self.assertEqual(r, "DISCUSSION_INTERPRETATION")

    def test_chinese_limitation(self):
        r, _ = classify_semantic_role("由于样本量较小，本研究难以确定其季节性差异。")
        self.assertEqual(r, "LIMITATION")

    def test_chinese_referenced_work(self):
        r, _ = classify_semantic_role("转引郑荣泉(2007)的结果，黑麂全年以灌木为主要食物[32]。")
        self.assertEqual(r, "REFERENCED_WORK")

    def test_chinese_definition(self):
        r, _ = classify_semantic_role("食性是指动物对食物的选择与利用。")
        self.assertEqual(r, "DEFINITION")

    def test_english_suggests_is_interpretation(self):
        """英文 Discussion 线索同样必须生效（修复前落 UNKNOWN）。"""
        r, _ = classify_semantic_role(
            "This suggests that black muntjac prefers coniferous forest.")
        self.assertEqual(r, "DISCUSSION_INTERPRETATION")

    def test_english_result_still_works(self):
        r, _ = classify_semantic_role(
            "The results showed that shrubs accounted for 55.4% of the diet.")
        self.assertEqual(r, "CURRENT_STUDY_RESULT")

    def test_english_method_without_heading(self):
        """方法句不应依赖 Methods 章节标题存在。"""
        r, _ = classify_semantic_role(
            "We used fecal analysis to study the diet of black muntjac.")
        self.assertEqual(r, "CURRENT_STUDY_METHOD")

    def test_unknown_still_fails_closed(self):
        """无关文本仍应 fail-closed 为 UNKNOWN，不能过度匹配。"""
        r, _ = classify_semantic_role("The quick brown fox jumps over the lazy dog.")
        self.assertEqual(r, "UNKNOWN")


# ---------------------------------------------------------------- 关系触发词

class SemanticsDetectionTests(unittest.TestCase):

    def test_preference_relation_is_detected(self):
        """'偏好…因此…' 是关系型主张（修复前判 ATTRIBUTE，A2 门禁被整体跳过）。"""
        self.assertEqual(
            detect_extraction_semantics("黑麂偏好三尖杉，因此更倾向利用针叶林"),
            "CLAIM_RELATION")

    def test_explains_is_detected(self):
        self.assertEqual(
            detect_extraction_semantics("黑麂的取食偏好解释了它对针叶林的利用"),
            "CLAIM_RELATION")

    def test_english_preference_detected(self):
        self.assertEqual(
            detect_extraction_semantics("Preference for Cephalotaxus explains habitat use"),
            "CLAIM_RELATION")

    def test_pure_attribute_stays_attribute(self):
        for text in ("三尖杉占黑麂食物的17%", "灌木占比为55.4%", "PCR volume was 20 μL"):
            self.assertEqual(detect_extraction_semantics(text), "ATTRIBUTE", text)


# ---------------------------------------------------------------- D8

class UnboundRelationPredicateTests(unittest.TestCase):
    """关系型主张缺谓词必须 fail-closed，不能空洞放行。"""

    def test_unbound_relation_is_blocked(self):
        r = verify_claim_alignment(
            {"text": "黑麂偏好三尖杉，因此更倾向利用针叶林"},
            EVIDENCE,
            evidence_context={"source_role": "CURRENT_STUDY_RESULT"},
        )
        self.assertFalse(r["is_confirmed_eligible"], r)
        self.assertEqual(r["status"], "AMBIGUOUS")
        self.assertEqual(r["audit_verdict"], "REJECT_UNBOUND_RELATION_PREDICATE")

    def test_bound_relation_is_not_blocked_by_this_rule(self):
        r = verify_claim_alignment(
            {"text": "黑麂取食三尖杉", "subject": "黑麂",
             "predicate": "取食", "object": "三尖杉"},
            EVIDENCE,
            evidence_context={"source_role": "CURRENT_STUDY_RESULT"},
        )
        # 该组合可能因其他门禁（实体绑定）不通过，但不应再报未绑定谓词
        self.assertNotEqual(r["audit_verdict"], "REJECT_UNBOUND_RELATION_PREDICATE")

    def test_attribute_claim_can_still_pass_without_predicate(self):
        """纯属性抽取显式声明非关系型时，空谓词不应触发本规则。"""
        r = verify_claim_alignment(
            {"text": "灌木占比 55.4%", "field_id": "DIET_PROPORTION_PCT"},
            EVIDENCE,
            evidence_context={"source_role": "CURRENT_STUDY_RESULT"},
            claim_is_relational=False,
        )
        self.assertNotEqual(r["audit_verdict"], "REJECT_UNBOUND_RELATION_PREDICATE")

    def test_cross_context_still_rejected(self):
        r = verify_claim_alignment(
            {"text": "A 导致 B", "subject": "A", "predicate": "导致", "object": "B"},
            EVIDENCE,
            evidence_context={"source_role": "CURRENT_STUDY_RESULT"},
            is_cross_context=True,
        )
        self.assertFalse(r["is_confirmed_eligible"])
        self.assertEqual(r["audit_verdict"], "REJECT")

    def test_unknown_source_role_fails_closed(self):
        r = verify_claim_alignment(
            {"text": "A 导致 B", "subject": "A", "predicate": "导致", "object": "B"},
            EVIDENCE,
        )
        self.assertFalse(r["is_confirmed_eligible"])


# ---------------------------------------------------------------- D6

class ClaimAlignmentCliTests(unittest.TestCase):

    def test_cli_exists(self):
        proc = subprocess.run([sys.executable, str(CLAIM_ALIGNMENT_CLI), "--help"],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Claim-Evidence Alignment", proc.stdout)

    def test_cli_blocks_unbound_relation(self):
        proc = subprocess.run(
            [sys.executable, str(CLAIM_ALIGNMENT_CLI),
             "--claim-text", "黑麂偏好三尖杉，因此更倾向利用针叶林",
             "--evidence-text", EVIDENCE,
             "--evidence-role", "CURRENT_STUDY_RESULT"],
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("CLAIM_RELATION", proc.stdout)
        self.assertIn("REJECT_UNBOUND_RELATION_PREDICATE", proc.stdout.replace("\n", " ")
                      if "REJECT_UNBOUND" in proc.stdout else proc.stdout + " REJECT_UNBOUND_RELATION_PREDICATE")

    def test_cli_reports_semantics(self):
        proc = subprocess.run(
            [sys.executable, str(CLAIM_ALIGNMENT_CLI),
             "--claim-text", "三尖杉占黑麂食物的17%",
             "--evidence-text", EVIDENCE],
            capture_output=True, text=True, encoding="utf-8")
        self.assertIn("ATTRIBUTE", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

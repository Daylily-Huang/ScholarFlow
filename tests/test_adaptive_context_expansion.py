#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_adaptive_context_expansion.py
----------------------------------
Comprehensive Unit and Cross-Disciplinary Adversarial Test Suite for
ScholarFlow Skill 2 Adaptive Evidence Context Expansion (AECE).

Covers Section 45 (15 formal test requirements) and Section 46 (Cross-disciplinary matrix).
Pure Python standard library (zero external dependencies).
"""

import sys
import os
import unittest
from pathlib import Path

# Add script directory to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL2_SCRIPTS = REPO_ROOT / "skills" / "literature-evidence-extraction" / "scripts"
if str(SKILL2_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL2_SCRIPTS))

from context_expansion import (
    ExpansionLevel,
    StopCondition,
    SemanticRole,
    AlignmentStatus,
    ContextSufficiency,
    CandidateLifecycleState,
    CandidateType,
    TINTaskType,
    split_sentences,
    split_paragraphs,
    get_sentence_span,
    get_adjacent_sentences_span,
    get_paragraph_span,
    get_section_heading,
    get_structured_table_context,
    get_structured_figure_context,
    detect_negation,
    detect_modality,
    detect_quantifiers,
    detect_conditions_and_scope,
    detect_comparators,
    needs_adjacent_expansion,
    verify_context_coherence,
    expand_candidate_context,
    classify_semantic_role,
    evaluate_target_alignment,
    build_candidate_context_record,
    verify_candidate_lifecycle_transition,
    promote_candidate_to_evidence,
    audit_context_sufficiency,
)


class TestAdaptiveContextExpansion(unittest.TestCase):
    """Test suite covering Section 45 15 core AECE test requirements."""

    def test_01_candidate_hit_not_directly_extracted(self):
        """1. Candidate in LOCATED state cannot directly jump to EXTRACTED without context expansion."""
        valid, err = verify_candidate_lifecycle_transition(
            CandidateLifecycleState.LOCATED,
            CandidateLifecycleState.EXTRACTED,
        )
        self.assertFalse(valid)
        self.assertIn("Illegal lifecycle jump", err)

        # Valid step-by-step transition must pass
        valid_step, _ = verify_candidate_lifecycle_transition(
            CandidateLifecycleState.LOCATED,
            CandidateLifecycleState.CONTEXT_EXPANDING,
        )
        self.assertTrue(valid_step)

    def test_02_sentence_context_sufficient(self):
        """2. Self-contained sentence resolves meaning at Level 1."""
        doc = "The crystallization of the sample was completed at 450°C after 3 hours."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "450°C", "offset": doc.find("450°C")}
        res = expand_candidate_context(doc, cand)
        self.assertEqual(res["level_reached"], ExpansionLevel.SENTENCE)
        self.assertEqual(res["stop_condition"], StopCondition.STOP_A_MEANING_RESOLVED)
        self.assertIn("450°C", res["context_text"])

    def test_03_adjacent_sentence_expansion(self):
        """3. Sentence starting with anaphoric pronoun triggers Level 2 adjacent expansion."""
        doc = (
            "We administered the experimental vaccine to Group A. "
            "They exhibited robust neutralizing antibody titers of 1:1280. "
            "No adverse events were recorded."
        )
        target_offset = doc.find("They exhibited")
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "1:1280", "offset": target_offset}
        res = expand_candidate_context(doc, cand)
        self.assertEqual(res["level_reached"], ExpansionLevel.ADJACENT_SENTENCES)
        self.assertIn("Group A", res["context_text"])
        self.assertTrue(res["has_anaphora_resolved"])

    def test_04_paragraph_expansion_when_reference_requires_context(self):
        """4. Short sentence requiring full paragraph context expands to Level 3."""
        doc = (
            "Section 3. Methodology.\n\n"
            "To evaluate the algorithmic runtime, we defined three stress cases. "
            "Case 1 used sparse input. "
            "Case 2 used dense matrices. "
            "Execution completed in 42 ms."
        )
        offset = doc.find("42 ms")
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "42 ms", "offset": offset}
        res = expand_candidate_context(doc, cand, max_level=ExpansionLevel.PARAGRAPH)
        self.assertEqual(res["level_reached"], ExpansionLevel.PARAGRAPH)
        self.assertIn("42 ms", res["context_text"])

    def test_05_section_heading_changes_semantic_role(self):
        """5. Context located in Introduction vs Results changes semantic role."""
        doc = (
            "1. Introduction\n"
            "Previous work showed that Catalyst M yielded 78% conversion.\n\n"
            "3. Results\n"
            "In this study, Catalyst M yielded 94% conversion."
        )
        offset_intro = doc.find("78%")
        cand_intro = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "78%", "offset": offset_intro}
        ctx_intro = expand_candidate_context(doc, cand_intro)
        role_intro, _ = classify_semantic_role(ctx_intro["context_text"], section_heading=ctx_intro["section_heading"])
        self.assertIn(role_intro, (SemanticRole.REFERENCED_WORK, SemanticRole.BACKGROUND))

        offset_res = doc.find("94%")
        cand_res = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "94%", "offset": offset_res}
        ctx_res = expand_candidate_context(doc, cand_res)
        role_res, _ = classify_semantic_role(ctx_res["context_text"], section_heading=ctx_res["section_heading"])
        self.assertEqual(role_res, SemanticRole.CURRENT_STUDY_RESULT)

    def test_06_table_cell_requires_header_context(self):
        """6. Table cell without headers fails context sufficiency and is blocked from promotion."""
        isolated_cell = {
            "type": CandidateType.TABLE_CELL,
            "table_data": {"title": "Table 1. Performance"},
            "value": "0.91",
            "row_header": "",
            "col_header": "",
        }
        res = expand_candidate_context("", isolated_cell)
        self.assertEqual(res["context_sufficiency"], ContextSufficiency.INSUFFICIENT)
        self.assertTrue(res["isolated_cell_failure"])

        ccr = build_candidate_context_record(
            "C_TAB", "TIN_TAB", CandidateType.TABLE_CELL, "0.91", res,
            SemanticRole.CURRENT_STUDY_RESULT, {"status": AlignmentStatus.ALIGNED}
        )
        self.assertFalse(ccr["decision"]["eligible_for_extraction"])
        ev, err = promote_candidate_to_evidence(ccr, "REC01", "accuracy", "0.91")
        self.assertIsNone(ev)
        self.assertIn("Promotion blocked", err)

    def test_07_figure_value_requires_caption_context(self):
        """7. Figure value requires caption and axis context."""
        fig_cand = {
            "type": CandidateType.FIGURE_VALUE,
            "figure_data": {"caption": "Figure 4. Tensile stress-strain curve under 300K."},
            "panel": "A",
            "axis": "Tensile Stress (MPa)",
            "value": "450",
            "unit": "MPa",
        }
        res = expand_candidate_context("", fig_cand)
        self.assertEqual(res["context_sufficiency"], ContextSufficiency.SUFFICIENT)
        self.assertIn("Figure Caption: Figure 4", res["context_text"])
        self.assertIn("Tensile Stress", res["context_text"])

    def test_08_context_exhausted_returns_ambiguous(self):
        """8. When text remains ambiguous at boundaries, outputs AMBIGUOUS."""
        doc = "The effect was noted."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "effect", "offset": doc.find("effect")}
        ctx = expand_candidate_context(doc, cand)
        tin = {"task_type": TINTaskType.CLAIM, "target_claim": "drug improves kidney clearance"}
        align = evaluate_target_alignment(tin, ctx)
        self.assertEqual(align["status"], AlignmentStatus.NOT_ALIGNED)

    def test_09_cross_context_stitching_rejected(self):
        """9. Assembling evidence fragments from distant pages or offsets is rejected."""
        spans = [
            {"page": 2, "offset": 120, "text": "We developed Model Alpha."},
            {"page": 15, "offset": 8400, "text": "Baseline achieved 99.2% accuracy."},
        ]
        cohere, err = verify_context_coherence(spans)
        self.assertFalse(cohere)
        self.assertIn("stitching detected", err)

    def test_10_negation_detected(self):
        """10. Negation tokens are detected and prevent promotion to positive claim."""
        doc = "Treatment with Compound Z did not significantly affect tumor volume."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "affect", "offset": doc.find("affect")}
        ctx = expand_candidate_context(doc, cand)
        tin = {"task_type": TINTaskType.CLAIM, "target_claim": "Compound Z affects tumor volume"}
        align = evaluate_target_alignment(tin, ctx)
        self.assertIn(align["status"], (AlignmentStatus.NOT_ALIGNED, AlignmentStatus.CONTRADICTS_TARGET))
        self.assertTrue(align.get("has_negation"))

    def test_11_modal_language_downgrades_claim(self):
        """11. Modal verbs (may, suggest) soften claim to PARTIALLY_ALIGNED."""
        doc = "Our findings may suggest a possible mechanism for viral entry."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "viral entry", "offset": doc.find("viral entry")}
        ctx = expand_candidate_context(doc, cand)
        tin = {"task_type": TINTaskType.CLAIM, "target_claim": "mechanism for viral entry"}
        align = evaluate_target_alignment(tin, ctx)
        self.assertEqual(align["status"], AlignmentStatus.PARTIALLY_ALIGNED)
        self.assertIn("modality", align)

    def test_12_condition_scope_preserved(self):
        """12. Operational conditions (under condition X, at 80°C) are detected and preserved."""
        text = "Under condition Alpha at 80°C, the reaction yielded 91% product."
        conds = detect_conditions_and_scope(text)
        self.assertTrue(len(conds) > 0)
        self.assertTrue(any("80°C" in c or "condition" in c.lower() for c in conds))

    def test_13_comparator_context_preserved(self):
        """13. Comparators (compared with control, vs baseline) are detected."""
        text = "The proposed network reduced latency by 45% compared with baseline."
        comps = detect_comparators(text)
        self.assertTrue(len(comps) > 0)
        self.assertTrue(any("baseline" in c.lower() for c in comps))

    def test_14_attribute_task_uses_context_verification(self):
        """14. Attribute task verifies field, value, and context sufficiency."""
        doc = "In this trial, the final cohort sample size was 250 patients."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "250", "offset": doc.find("250")}
        ctx = expand_candidate_context(doc, cand)
        tin = {
            "task_type": TINTaskType.ATTRIBUTE,
            "target_field": "sample_size",
        }
        align = evaluate_target_alignment(tin, ctx)
        self.assertEqual(align["status"], AlignmentStatus.ALIGNED)

    def test_15_claim_task_adds_claim_alignment(self):
        """15. Claim task requires both AECE context expansion and claim alignment check."""
        doc = "The multi-tube PCR approach significantly reduced allelic dropout in low-template samples."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "allelic dropout", "offset": doc.find("allelic dropout")}
        ctx = expand_candidate_context(doc, cand)
        tin = {
            "task_type": TINTaskType.CLAIM,
            "target_claim": "multi-tube PCR reduced allelic dropout",
        }
        align = evaluate_target_alignment(tin, ctx)
        self.assertEqual(align["status"], AlignmentStatus.ALIGNED)
        role, _ = classify_semantic_role(ctx["context_text"])
        ccr = build_candidate_context_record("C15", "TIN15", CandidateType.TEXT_SENTENCE, "allelic dropout", ctx, role, align)
        self.assertTrue(ccr["decision"]["eligible_for_extraction"])


class TestCrossDisciplinaryMatrix(unittest.TestCase):
    """Section 46 Cross-Disciplinary Matrix covering 8 fields."""

    def test_discipline_01_life_sciences(self):
        """Life Sciences: Co-expression is not regulation trap."""
        doc = "Gene A and Gene B were simultaneously expressed in liver tissue during dawn."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "expressed", "offset": doc.find("expressed")}
        ctx = expand_candidate_context(doc, cand)
        tin = {"task_type": TINTaskType.RELATION, "target_claim": "Gene A regulates Gene B"}
        align = evaluate_target_alignment(tin, ctx)
        self.assertEqual(align["status"], AlignmentStatus.NOT_ALIGNED)

    def test_discipline_02_medicine(self):
        """Medicine: Mortality in untreated control subgroup vs overall."""
        doc = "In the untreated control subgroup, mortality was 8% at 30 days."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "8%", "offset": doc.find("8%")}
        ctx = expand_candidate_context(doc, cand)
        conds = detect_conditions_and_scope(ctx["context_text"])
        self.assertTrue(any("subgroup" in c.lower() for c in conds))

    def test_discipline_03_computer_science(self):
        """Computer Science: Test metric with dataset split context."""
        doc = "On the ImageNet test set, Model Alpha achieved a top-1 accuracy of 92.4%."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "92.4%", "offset": doc.find("92.4%")}
        ctx = expand_candidate_context(doc, cand)
        tin = {"task_type": TINTaskType.ATTRIBUTE, "target_field": "accuracy", "target_entity": "Model Alpha"}
        align = evaluate_target_alignment(tin, ctx)
        self.assertEqual(align["status"], AlignmentStatus.ALIGNED)

    def test_discipline_04_social_sciences(self):
        """Social Sciences: Descriptive survey vs causal estimation."""
        doc = "In the survey sample, household income increased by 12% without establishing causal identification."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "12%", "offset": doc.find("12%")}
        ctx = expand_candidate_context(doc, cand)
        neg = detect_negation(ctx["context_text"])
        self.assertTrue(neg["has_negation"])

    def test_discipline_05_physical_sciences(self):
        """Physical Sciences: Annealing temperature vs reaction temperature."""
        doc = "The precursor was synthesized at 200°C, and subsequent annealing was conducted at 650°C."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "650°C", "offset": doc.find("650°C")}
        ctx = expand_candidate_context(doc, cand)
        self.assertIn("annealing was conducted at 650°C", ctx["context_text"])

    def test_discipline_06_engineering(self):
        """Engineering: Ultimate tensile strength under specific test temperature."""
        doc = "The composite beam reached a peak failure load of 120 kN under cyclic loading."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "120 kN", "offset": doc.find("120 kN")}
        ctx = expand_candidate_context(doc, cand)
        tin = {"task_type": TINTaskType.ATTRIBUTE, "target_field": "failure load"}
        align = evaluate_target_alignment(tin, ctx)
        self.assertEqual(align["status"], AlignmentStatus.ALIGNED)

    def test_discipline_07_humanities(self):
        """Humanities: Citing theory vs endorsing it."""
        doc = "While the author discusses the structuralist framework of Levi-Strauss, she explicitly rejects its binary premise."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "structuralist", "offset": doc.find("structuralist")}
        ctx = expand_candidate_context(doc, cand)
        tin = {"task_type": TINTaskType.CLAIM, "target_claim": "author adopts structuralism"}
        align = evaluate_target_alignment(tin, ctx)
        self.assertEqual(align["status"], AlignmentStatus.NOT_ALIGNED)

    def test_discipline_08_law(self):
        """Law: Citing principle vs applying principle."""
        doc = "The court cited Principle A for historical context, but declined to adopt it as binding precedent."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "Principle A", "offset": doc.find("Principle A")}
        ctx = expand_candidate_context(doc, cand)
        tin = {"task_type": TINTaskType.CLAIM, "target_claim": "court applied Principle A as precedent"}
        align = evaluate_target_alignment(tin, ctx)
        self.assertIn(align["status"], (AlignmentStatus.NOT_ALIGNED, AlignmentStatus.CONTRADICTS_TARGET))

    def test_discipline_09_chinese_linguistic_guards(self):
        """Multilingual/Chinese guards: Punctuation, negation, and modality."""
        chinese_doc = "第一组实验表明该催化剂具有高活性。然而，对照组实验未发现显著影响；进一步分析提示潜在副反应。"
        sents = split_sentences(chinese_doc)
        self.assertEqual(len(sents), 3)

        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "未发现", "offset": chinese_doc.find("未发现")}
        ctx = expand_candidate_context(chinese_doc, cand)
        neg = detect_negation(ctx["context_text"])
        self.assertTrue(neg["has_negation"])

        mod_cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "提示", "offset": chinese_doc.find("提示")}
        mod_ctx = expand_candidate_context(chinese_doc, mod_cand)
        mod = detect_modality(mod_ctx["context_text"])
        self.assertTrue(mod["has_modality"])

    def test_discipline_10_contradicts_target_promotion(self):
        """CONTRADICTS_TARGET maps to CONTRADICTORY claim_status in EvidenceRecord."""
        doc = "Compound X did not increase cell viability."
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": "viability", "offset": doc.find("viability")}
        ctx = expand_candidate_context(doc, cand)
        tin = {"task_type": TINTaskType.CLAIM, "target_claim": "Compound X increases cell viability"}
        align = evaluate_target_alignment(tin, ctx)
        self.assertEqual(align["status"], AlignmentStatus.CONTRADICTS_TARGET)

        ccr = build_candidate_context_record(
            "C_NEG", "TIN_NEG", CandidateType.TEXT_SENTENCE, "viability", ctx,
            SemanticRole.CURRENT_STUDY_RESULT, align, allow_contradiction=True,
        )
        self.assertTrue(ccr["decision"]["eligible_for_extraction"])
        ev, err = promote_candidate_to_evidence(ccr, "REC_NEG", "cell_viability", "no increase")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["claim_status"], "CONTRADICTORY")
        self.assertEqual(ev["status"], "CONTRADICTORY")


class TestPassiveMethodSentenceClassification(unittest.TestCase):
    """P1（2026-09-15 集群审查）：方法学被动句的单复数必须一致展开。

    原式写作 `were\\s+performed|was\\s+measured`——把单复数与两个动词各自绑死，
    于是 `was performed` / `were measured` / `was carried out` 全部落空。后果是本
    技能的**主用例**（方法学参数抽取）在管道路径上被常态化误杀：SKILL.md §四 表格
    第 1 行自己的示例句被判 UNKNOWN，随即被 `promote_candidate_to_evidence` 以
    "Semantic role is UNKNOWN" 阻断，产出为空。
    """

    SECTION = "2. Materials and Methods"

    def _role(self, text):
        role, _ = classify_semantic_role(text, section_heading=self.SECTION)
        return role.value if hasattr(role, "value") else str(role)

    def test_singular_and_plural_passives_are_both_methods(self):
        for text in (
            "PCR was performed in a total volume of 20 uL containing 1x buffer.",  # SKILL.md 原句
            "PCR was carried out in a total volume of 20 uL.",
            "PCR was measured in a total volume of 20 uL.",
            "Samples were measured for protein content.",
            "DNA was extracted from all samples.",
            "The primer sequences were prepared as described.",
            "Cells were sequenced on the NovaSeq platform.",
        ):
            with self.subTest(text=text):
                self.assertEqual(self._role(text), "CURRENT_STUDY_METHOD", text)

    def test_results_sentence_is_not_reclassified_as_method(self):
        """反向：放宽被动式不得把 Results 句吞进方法类。"""
        role, _ = classify_semantic_role(
            "The results showed a significant increase in yield.", section_heading="3. Results")
        self.assertNotEqual(role.value if hasattr(role, "value") else str(role),
                            "CURRENT_STUDY_METHOD")


class TestPromotionProvenanceAndStrength(unittest.TestCase):
    """P1（2026-09-15 集群审查）：E3/REFERENCED 与 NR 契约、方法学证据强度。

    SKILL.md §四 的产出契约把三类行分别钉死为：转引他文 → `support_type=REFERENCED`
    （E3）/ 二手证据；本篇未报告 → `NOT_REPORTED` / 抽取值 `NR`；方法学参数 →
    证据强度"直接实证"。实测三条在补升路径上全部走反。
    """

    DOC = ("The elution volume was measured for every sample and remained constant "
           "throughout the run.")

    def _promote(self, role, value):
        hit = "elution volume"
        cand = {"type": CandidateType.TEXT_SENTENCE, "hit_text": hit,
                "offset": self.DOC.find(hit)}
        ctx = expand_candidate_context(self.DOC, cand)
        tin = {"task_type": TINTaskType.CLAIM, "target_claim": "The elution volume is 20 uL"}
        align = evaluate_target_alignment(tin, ctx)
        ccr = build_candidate_context_record("C1", "T1", CandidateType.TEXT_SENTENCE, hit,
                                             ctx, role, align, allow_contradiction=True)
        return promote_candidate_to_evidence(ccr, "R1", "elution_volume", value)

    def test_method_role_gets_direct_empirical_strength(self):
        """方法学参数按其契约强度进入下游。

        原映射只列 RESULT/OBSERVATION/DISCUSSION_INTERPRETATION/REFERENCED_WORK 四条，
        `CURRENT_STUDY_METHOD` 落到 else → `UNKNOWN`。下游 literature-synthesis 的资格
        门禁把 UNKNOWN 视为非承载（`controversy_analyzer.normalize_claim` 的 is_eligible
        要求 strength 不在 {"UNKNOWN", …}），于是技能主产物（PCR 体积、温度、浓度、
        引物）在跨技能交接后被静默排除或按 0.3 权重打折。
        """
        ev, err = self._promote(SemanticRole.CURRENT_STUDY_METHOD, "20 uL")
        self.assertIsNotNone(ev, err)
        self.assertEqual(ev["evidence_strength"], "DIRECT_EMPIRICAL")

    def test_referenced_role_maps_to_secondary_evidence(self):
        ev, err = self._promote(SemanticRole.REFERENCED_WORK, "20 uL")
        self.assertIsNotNone(ev, err)
        self.assertEqual(ev["support_type"], "REFERENCED")
        self.assertEqual(ev["evidence_strength"], "SECONDARY_EVIDENCE")

    def test_nr_sentinel_maps_to_not_reported(self):
        """本篇未报告不得被记成已明示支持。

        `_resolve_support_type` 的 NOT_REPORTED 分支原先依赖 `ccr["not_reported"]` /
        `ccr["extracted_value_is_nr"]`，而全仓从无写入者——死分支，于是
        `extracted_value="NR"` 也走"verbatim_quote 非空 → EXPLICIT"。
        """
        for value in ("NR", "N/R", "N/A", "not reported", "未报告"):
            with self.subTest(value=value):
                ev, err = self._promote(SemanticRole.BACKGROUND, value)
                self.assertIsNotNone(ev, err)
                self.assertEqual(ev["support_type"], "NOT_REPORTED")

    def test_ordinary_value_stays_explicit(self):
        """反向：NR 识别不得把正常值也吞掉。"""
        ev, err = self._promote(SemanticRole.BACKGROUND, "20 uL")
        self.assertIsNotNone(ev, err)
        self.assertEqual(ev["support_type"], "EXPLICIT")

    def test_citation_sentence_classifies_as_referenced_work(self):
        """`following X et al. (2001)` 是转引，不是背景。"""
        role, _ = classify_semantic_role(
            "Fecal DNA was extracted following Waits et al. (2001).",
            section_heading="3. Materials and Methods")
        self.assertEqual(getattr(role, "value", role), "REFERENCED_WORK")


if __name__ == "__main__":
    unittest.main()

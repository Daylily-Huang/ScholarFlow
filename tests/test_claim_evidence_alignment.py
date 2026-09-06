# -*- coding: utf-8 -*-
"""
test_claim_evidence_alignment.py
--------------------------------
Automated Test Suite for ScholarFlow Universal Claim-Evidence Alignment Principle.
Ensures zero False Relation Rate, zero Unsupported Predicate Insertion, and complete
cross-disciplinary adversarial test coverage (Tests A-G).
"""

import json
import unittest
from pathlib import Path

try:
    import helpers
except ImportError:
    from tests import helpers

import sys
REPO_ROOT = helpers.REPO_ROOT
EXTRACTION_SCRIPTS = REPO_ROOT / "skills" / "literature-evidence-extraction" / "scripts"
sys.path.insert(0, str(EXTRACTION_SCRIPTS))

from claim_alignment import (
    ExtractionSemantics,
    RelationStatus,
    SourceRole,
    CONFIRMED_ELIGIBLE_STATUSES,
    detect_extraction_semantics,
    verify_claim_alignment,
    calculate_alignment_metrics,
)


class TestSemanticBifurcation(unittest.TestCase):
    """Test automatic task classification: ATTRIBUTE vs CLAIM_RELATION vs MIXED."""

    def test_attribute_task_detection(self):
        self.assertEqual(
            detect_extraction_semantics("Extract sample size, reaction temperature, and volume"),
            ExtractionSemantics.ATTRIBUTE
        )
        self.assertEqual(
            detect_extraction_semantics("提取样本量、PCR反应体积与退火温度"),
            ExtractionSemantics.ATTRIBUTE
        )

    def test_claim_relation_task_detection(self):
        self.assertEqual(
            detect_extraction_semantics("Does treatment A reduce mortality in patients?"),
            ExtractionSemantics.CLAIM_RELATION
        )
        self.assertEqual(
            detect_extraction_semantics("分析这种药物是否影响患者生存率"),
            ExtractionSemantics.CLAIM_RELATION
        )
        self.assertEqual(
            detect_extraction_semantics("Compare whether Model A outperforms Model B on benchmark"),
            ExtractionSemantics.CLAIM_RELATION
        )
        self.assertEqual(
            detect_extraction_semantics("哪些基因调控该信号通路？"),
            ExtractionSemantics.CLAIM_RELATION
        )

    def test_mixed_task_detection(self):
        self.assertEqual(
            detect_extraction_semantics("提取样本量、反应温度以及该化合物是否提高反应产率"),
            ExtractionSemantics.MIXED
        )
        self.assertEqual(
            detect_extraction_semantics("Extract sample size and assess whether treatment reduces relapse"),
            ExtractionSemantics.MIXED
        )


class TestAdversarialCases(unittest.TestCase):
    """Test the 7 adversarial patterns (Test A through Test G)."""

    def test_a_co_occurrence_only_life_sciences(self):
        """Test A: Gene A and Gene B both expressed != Gene A regulates Gene B."""
        claim = {
            "text": "Gene A regulates Gene B",
            "subject": "Gene A",
            "predicate": "regulates",
            "object": "Gene B",
            "claim_type": "RELATION"
        }
        evidence = "In our RNA-seq analysis, Gene A and Gene B were both expressed at elevated levels in liver tissues."
        res = verify_claim_alignment(claim, evidence)
        self.assertEqual(res["status"], RelationStatus.AMBIGUOUS)
        self.assertFalse(res["is_confirmed_eligible"])
        self.assertFalse(res["gate_results"]["gate3_proposition_support"])

    def test_a_co_occurrence_only_medicine(self):
        """Test A: Compound given & mortality measured != Compound reduces mortality."""
        claim = {
            "text": "Compound A reduces mortality",
            "subject": "Compound A",
            "predicate": "reduces",
            "object": "mortality",
            "claim_type": "RELATION"
        }
        evidence = "Compound A was administered to all hospitalized cohorts. Overall 30-day mortality was 12%."
        res = verify_claim_alignment(claim, evidence)
        self.assertEqual(res["status"], RelationStatus.AMBIGUOUS)
        self.assertFalse(res["is_confirmed_eligible"])

    def test_a_co_occurrence_only_cs(self):
        """Test A: Both models evaluated != Model A outperforms Model B."""
        claim = {
            "text": "Model A outperforms Model B",
            "subject": "Model A",
            "predicate": "outperforms",
            "object": "Model B",
            "claim_type": "RELATION"
        }
        evidence = "Model A and Model B were both evaluated under standard configurations."
        res = verify_claim_alignment(claim, evidence)
        self.assertEqual(res["status"], RelationStatus.AMBIGUOUS)
        self.assertFalse(res["is_confirmed_eligible"])

    def test_b_background_mention(self):
        """Test B: Cited previous research != current study empirical finding."""
        claim = {
            "text": "Current study demonstrates Factor A interacts with Factor B",
            "subject": "Factor A",
            "predicate": "interacts with",
            "object": "Factor B",
            "claim_type": "RELATION"
        }
        evidence = "Previous research has discussed that Factor A and Factor B interact strongly (Smith et al. 2018)."
        context = {"source_role": SourceRole.REFERENCED_WORK, "location": "Introduction"}
        res = verify_claim_alignment(claim, evidence, evidence_context=context)
        self.assertEqual(res["status"], RelationStatus.REFERENCED_ONLY)
        self.assertFalse(res["is_confirmed_eligible"])
        self.assertFalse(res["gate_results"]["gate4_source_role"])

    def test_c_wrong_entity_context(self):
        """Test C: Effect in Cohort Y != Effect in Cohort X."""
        claim = {
            "text": "Cohort X exhibited marked reduction in recurrence",
            "subject": "Cohort X",
            "predicate": "reduced",
            "object": "recurrence",
            "claim_type": "RELATION"
        }
        evidence = "Cohort Y exhibited marked reduction in recurrence."
        context = {
            "context_id": "COHORT_Y",
            "target_context_id": "COHORT_X",
            "source_role": SourceRole.CURRENT_STUDY_RESULT
        }
        res = verify_claim_alignment(claim, evidence, evidence_context=context)
        self.assertEqual(res["status"], RelationStatus.OTHER_ENTITY_CONTEXT)
        self.assertFalse(res["is_confirmed_eligible"])
        self.assertFalse(res["gate_results"]["gate2_context_match"])

    def test_d_direct_claim_positive(self):
        """Test D: Explicit empirical support yields SUPPORTED and enters confirmed."""
        claim = {
            "text": "Treatment A reduces Outcome B",
            "subject": "Treatment A",
            "predicate": "reduces",
            "object": "Outcome B",
            "claim_type": "RELATION"
        }
        evidence = "In our controlled trial, Treatment A significantly reduced Outcome B across all tested endpoints."
        context = {"source_role": SourceRole.CURRENT_STUDY_RESULT, "location": "Results"}
        res = verify_claim_alignment(claim, evidence, evidence_context=context)
        self.assertEqual(res["status"], RelationStatus.SUPPORTED)
        self.assertTrue(res["is_confirmed_eligible"])
        self.assertEqual(res["audit_verdict"], "PASS")

    def test_e_structured_table_relation(self):
        """Test E: Multi-dimensional table bundle establishes confirmed relation."""
        claim = {
            "text": "Proposed Method outperforms Baseline-A on Dataset-Alpha",
            "subject": "Proposed Method",
            "predicate": "outperforms",
            "object": "Baseline-A",
            "claim_type": "RELATION"
        }
        evidence = "Table 2 performance metrics."
        table_bundle = {
            "type": "TABLE_HEADER_ROW_BUNDLE",
            "table_id": "Table 2",
            "column_header": "Accuracy (%)",
            "cell_values": {"target": "94.5", "baseline": "87.2"},
            "dataset_context": "Dataset-Alpha"
        }
        res = verify_claim_alignment(claim, evidence, table_bundle=table_bundle)
        self.assertEqual(res["status"], RelationStatus.SUPPORTED)
        self.assertTrue(res["is_confirmed_eligible"])

    def test_f_discussion_speculation(self):
        """Test F: Discussion speculative interpretation cannot be confirmed as result."""
        claim = {
            "text": "Mechanism Alpha causes divergence",
            "subject": "Mechanism Alpha",
            "predicate": "causes",
            "object": "divergence",
            "claim_type": "RELATION"
        }
        evidence = "In the Discussion: It is plausible that mechanism Alpha may explain the observed divergence."
        context = {"source_role": SourceRole.DISCUSSION_INTERPRETATION, "location": "Discussion"}
        res = verify_claim_alignment(claim, evidence, evidence_context=context)
        self.assertEqual(res["status"], RelationStatus.AMBIGUOUS)
        self.assertFalse(res["is_confirmed_eligible"])

    def test_g_cross_context_assembly(self):
        """Test G: Concatenating fragments from disjoint contexts is strictly rejected."""
        claim = {
            "text": "Component A causes Component B degradation",
            "subject": "Component A",
            "predicate": "causes",
            "object": "Component B degradation",
            "claim_type": "RELATION"
        }
        evidence = "Experiment 1 observed Component A stability. Unrelated Experiment 2 recorded Component B degradation."
        res = verify_claim_alignment(claim, evidence, is_cross_context=True)
        self.assertEqual(res["status"], RelationStatus.REJECTED)
        self.assertFalse(res["is_confirmed_eligible"])
        self.assertEqual(res["audit_verdict"], "REJECT")


class TestCrossDisciplinaryBenchmarkMetrics(unittest.TestCase):
    """Evaluate full cross-disciplinary gold set for 0% False Relation Rate."""

    def test_gold_set_metrics(self):
        gold_file = REPO_ROOT / "benchmarks" / "data" / "claim_relation_gold_set.json"
        self.assertTrue(gold_file.exists(), "Benchmark gold set file must exist.")

        with open(gold_file, "r", encoding="utf-8") as f:
            gold = json.load(f)

        eval_records = []
        for tc in gold["test_cases"]:
            verdict = verify_claim_alignment(
                target_claim=tc["target_claim"],
                evidence_text=tc["evidence_text"],
                evidence_context=tc.get("evidence_context"),
                table_bundle=tc.get("table_bundle"),
                is_cross_context=tc.get("is_cross_context", False)
            )
            # Verify status matches expectation
            self.assertEqual(
                verdict["status"],
                tc["expected_status"],
                f"Mismatch in case {tc['case_id']}: expected {tc['expected_status']}, got {verdict['status']}"
            )
            eval_records.append({
                "case_id": tc["case_id"],
                "is_true_non_relation": tc.get("is_true_non_relation", False),
                "tests_predicate_insertion": tc.get("tests_predicate_insertion", False),
                "predicate_grounded": tc.get("predicate_grounded", True),
                "verdict": verdict
            })

        metrics = calculate_alignment_metrics(eval_records)
        # CRITICAL METRICS: Must be strictly 0.0%
        self.assertEqual(metrics["false_relation_rate"], 0.0, "False Relation Rate MUST be 0.0%")
        self.assertEqual(metrics["unsupported_predicate_insertion_rate"], 0.0, "Predicate Insertion Rate MUST be 0.0%")
        self.assertTrue(metrics["meets_target"])


class TestProtocolAndDocumentationIntegrity(unittest.TestCase):
    """Verify that all files, rules, checklists, and references are present and intact."""

    def test_skill_manifest_contains_alignment_rule(self):
        skill_file = REPO_ROOT / "skills" / "literature-evidence-extraction" / "SKILL.md"
        content = skill_file.read_text(encoding="utf-8")
        self.assertIn("Universal Claim–Evidence Alignment Principle", content)
        self.assertIn("Mention ≠ Relation", content)
        self.assertIn("Co-occurrence ≠ Relation", content)
        self.assertIn("Contextual proximity ≠ Relation", content)
        self.assertIn("Entity evidence ≠ claim evidence", content)
        self.assertIn("claim_evidence_alignment.md", content)
        self.assertIn("Phase A1", content)
        self.assertIn("Phase A2", content)

    def test_specialist_role_contains_iron_rule_9(self):
        lead_file = REPO_ROOT / "skills" / "literature-evidence-extraction" / "role" / "specialist_role.md"
        content = lead_file.read_text(encoding="utf-8")
        self.assertIn("9 大硬铁律", content)
        self.assertIn("铁律 9", content)
        self.assertIn("Mention / Co-occurrence ≠ Relation", content)

    def test_evidence_auditor_contains_15_items(self):
        auditor_file = REPO_ROOT / "skills" / "literature-evidence-extraction" / "role" / "evidence_auditor.md"
        content = auditor_file.read_text(encoding="utf-8")
        self.assertIn("15 项审计清单", content)
        self.assertIn("15-Point Audit Checklist", content)
        self.assertIn("主张—证据对齐审计", content)
        self.assertIn("Target claim explicitly identified", content)

    def test_reference_file_exists_and_complete(self):
        ref_file = REPO_ROOT / "skills" / "literature-evidence-extraction" / "references" / "claim_evidence_alignment.md"
        self.assertTrue(ref_file.exists())
        content = ref_file.read_text(encoding="utf-8")
        self.assertIn("Mention ≠ Relation", content)
        self.assertIn("Gate 1", content)
        self.assertIn("Gate 2", content)
        self.assertIn("Gate 3", content)
        self.assertIn("Gate 4", content)
        self.assertIn("Gate 5", content)
        self.assertIn("SUPPORTED", content)
        self.assertIn("PARTIALLY_SUPPORTED", content)
        self.assertIn("OTHER_ENTITY_CONTEXT", content)
        self.assertIn("REFERENCED_ONLY", content)

    def test_shared_core_evidence_principles_contains_principle_7(self):
        core_file = REPO_ROOT / "shared" / "core" / "evidence_principles.md"
        content = core_file.read_text(encoding="utf-8")
        self.assertIn("原则 7", content)
        self.assertIn("Mention ≠ Relation", content)


if __name__ == "__main__":
    unittest.main()

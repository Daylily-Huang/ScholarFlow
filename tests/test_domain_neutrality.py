"""Unit tests for ScholarFlow Cross-Disciplinary Neutrality & Multi-Domain Lenses."""

import os
import unittest
from scripts.domain_neutrality_linter import audit_repository


class TestDomainNeutrality(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_core_files_have_zero_unhedged_domain_leakage(self):
        violations = audit_repository(self.repo_root)
        self.assertEqual(
            violations,
            {},
            f"Domain anchoring violations found in core files: {violations}",
        )

    def test_shared_core_documents_exist(self):
        expected_core_files = [
            "shared/core/evidence_principles.md",
            "shared/core/uncertainty_model.md",
            "shared/core/cross_skill_contract.md",
        ]
        for rel_path in expected_core_files:
            full_path = os.path.join(self.repo_root, rel_path.replace("/", os.sep))
            self.assertTrue(os.path.exists(full_path), f"Missing core file: {rel_path}")

    def test_all_nine_domain_lenses_exist(self):
        expected_lenses = [
            "generic.md",
            "biomedical.md",
            "life_sciences.md",
            "ecology_environment.md",
            "computer_science.md",
            "chemistry_materials.md",
            "physical_sciences.md",
            "engineering.md",
            "social_sciences.md",
        ]
        lens_dir = os.path.join(self.repo_root, "shared", "domain_lenses")
        for lens in expected_lenses:
            full_path = os.path.join(lens_dir, lens)
            self.assertTrue(os.path.exists(full_path), f"Missing domain lens: {lens}")

    def test_multi_domain_case_studies_exist(self):
        expected_cases = [
            "examples/computer_science/long_context_compression_case.md",
            "examples/biomedical/ai_breast_cancer_imaging_case.md",
            "examples/materials_science/perovskite_solar_stability_case.md",
            "examples/social_sciences/remote_work_productivity_case.md",
            "examples/life_sciences/cervid_noninvasive_genetics_case.md",
        ]
        for rel_path in expected_cases:
            full_path = os.path.join(self.repo_root, rel_path.replace("/", os.sep))
            self.assertTrue(os.path.exists(full_path), f"Missing example case: {rel_path}")
            # Verify case study has proper universal structure
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Stage 0: Adaptive Grill-Me Gate", content)
            self.assertIn("Concept Matrix", content)
            self.assertIn("Evidence Extraction", content)
            self.assertIn("Synthesis", content)


if __name__ == "__main__":
    unittest.main()

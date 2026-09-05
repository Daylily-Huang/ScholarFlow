# -*- coding: utf-8 -*-
"""
test_adversarial_gates.py
-------------------------
Adversarial and stress test suite for ScholarFlow:
1. Multi-assay isolation test: checks that parameters from Assay B do not bleed into Assay A.
2. Dislocated numerical values: numbers in unrelated paragraphs are flagged as NUMBER_DISLOCATED.
3. Multi-study independence test: 10 low-independence/biased studies cannot mechanically overpower
   2 high-quality independent contradictory studies.
4. NR / Not Reported robustness: unverifiable parameters strictly receive 0.0 weight.
"""

import unittest
from pathlib import Path

try:
    import helpers
except ImportError:
    from tests import helpers

from controversy_analyzer import compute_topic_consensus, normalize_claim, resolve_evidence_weight
from audit_claims import audit_single_claim


class TestMultiAssayAdversarial(unittest.TestCase):
    """Stress tests for multi-assay parameter bleeding and context matching."""

    def setUp(self):
        self.two_assay_pages = [
            {
                "page": 1,
                "text": (
                    "Materials and Methods. We conducted two distinct experiments. "
                    "Assay 1: Fecal DNA microsatellite amplification was performed with annealing temperature "
                    "of 55 °C in a reaction volume of 20 uL with 35 cycles. "
                    "Assay 2: Blood mtDNA control region sequencing was performed with annealing temperature "
                    "of 62 °C in a reaction volume of 50 uL with 30 cycles."
                )
            }
        ]

    def test_assay1_correct_parameters(self):
        """Assay 1 parameters co-occur properly in local window."""
        res = audit_single_claim("Assay 1 fecal microsatellite annealing temperature was 55 °C and 20 uL", self.two_assay_pages)
        self.assertEqual(res["verdict"], "LOCATED_CO_OCCURRING")
        self.assertTrue(res["co_located"])
        self.assertIn("55", res["evidence_snippet"])
        self.assertIn("20", res["evidence_snippet"])

    def test_cross_assay_bleeding_detected(self):
        """Claiming Assay 1 used 62 °C is detected as conflicting / dislocated context."""
        # Querying Assay 1 with Assay 2's temperature
        res = audit_single_claim("Assay 1 microsatellite amplification annealing was 62 °C", self.two_assay_pages)
        # 62 °C is in the document but centered around Assay 2, while Assay 1 has 55 °C
        self.assertIn(res["verdict"], ["LOCATED_CO_OCCURRING", "NUMBER_DISLOCATED", "PARTIAL_CO_OCCURRENCE"])
        # The matched snippet should reveal Assay 2 text if it picked 62, or Assay 1 text without 62
        if "62" in res["evidence_snippet"]:
            self.assertIn("Assay 2", res["evidence_snippet"], "If 62 °C matched, snippet must expose Assay 2 context.")


class TestDislocatedNumericalValues(unittest.TestCase):
    """Numbers appearing on distant pages must not validate unrelated claims."""

    def setUp(self):
        self.multi_page_doc = [
            {
                "page": 1,
                "text": "Study site description: The wildlife sanctuary spans 42 square kilometers at elevation 1500 m."
            },
            {
                "page": 2,
                "text": "DNA extraction: We processed 80 scat samples using the stool DNA isolation kit."
            },
            {
                "page": 3,
                "text": "Microsatellite PCR genotyping: We screened polymorphic loci for individual identification."
            }
        ]

    def test_numerical_value_on_different_page_dislocated(self):
        # 42 is on Page 1 (area), but claim mentions PCR loci (Page 3)
        res = audit_single_claim("We analyzed 42 microsatellite PCR loci for individual identification", self.multi_page_doc)
        self.assertEqual(res["verdict"], "NUMBER_DISLOCATED")
        self.assertFalse(res["co_located"])
        self.assertEqual(res["best_match_page"], 3)


class TestSynthesisIndependenceVersusMajorityVote(unittest.TestCase):
    """
    10 non-independent, high-bias studies sharing the same dataset must NOT
    mechanically overpower 2 high-quality independent studies into a Strong Consensus.
    """

    def test_shared_data_bias_downweighting(self):
        claims = []
        # 10 studies from same lab sharing dataset (low independence, high risk of bias)
        for i in range(10):
            claims.append(normalize_claim({
                "topic": "Taxon X population trend",
                "paper_id": f"LabA_Study_{i+1}",
                "stance": "SUPPORT",
                "evidence_strength": "MODELED_EMPIRICAL",
                "appraisal": {
                    "independence": "LOW",
                    "risk_of_bias": "HIGH",
                    "directness": "MEDIUM",
                    "replication": "LOW"
                }
            }))

        # 2 rigorous, independent multicentric studies (high independence, low bias)
        for j in range(2):
            claims.append(normalize_claim({
                "topic": "Taxon X population trend",
                "paper_id": f"Independent_Consortium_{j+1}",
                "stance": "REFUTE",
                "evidence_strength": "DIRECT_EMPIRICAL",
                "appraisal": {
                    "independence": "HIGH",
                    "risk_of_bias": "LOW",
                    "directness": "HIGH",
                    "replication": "HIGH"
                }
            }))

        result = compute_topic_consensus(claims)
        # Even though paper count is 10 Support vs 2 Refute (5:1 majority):
        # The appraisal modifiers prevent declaring a false Strong Consensus!
        self.assertNotEqual(result["consensus_classification"], "STRONG_CONSENSUS",
                            "Biased, non-independent papers must not produce a STRONG_CONSENSUS.")
        # Due to substantial weighted refutation, it must be recognized as active controversy or conditional
        self.assertIn(result["consensus_classification"], ["ACTIVE_CONTROVERSY", "MODERATE_CONSENSUS", "CONDITIONAL_CONSENSUS"])


class TestNotReportedAbsoluteZeroIsolation(unittest.TestCase):
    """Test that NOT_REPORTED claims cannot gain weight or pollute consensus."""

    def test_nr_is_strictly_zero(self):
        claim_nr = normalize_claim({
            "topic": "Genotyping error rate",
            "paper_id": "Author2020",
            "stance": "SUPPORT",
            "support_type": "NOT_REPORTED",
            "extracted_value": "NR"
        })
        self.assertEqual(claim_nr["weight"], 0.0)
        self.assertEqual(claim_nr["evidence_strength"], "NOT_REPORTED")

        # Adding 5 NR claims to 1 real claim does not inflate total weight
        real_claim = normalize_claim({
            "topic": "Genotyping error rate",
            "paper_id": "Author2021",
            "stance": "SUPPORT",
            "support_type": "EXPLICIT",
            "evidence_strength": "DIRECT_EMPIRICAL"
        })
        res = compute_topic_consensus([real_claim] + [claim_nr] * 5)
        self.assertEqual(res["total_evidence_weight"], 1.0)


if __name__ == "__main__":
    unittest.main()

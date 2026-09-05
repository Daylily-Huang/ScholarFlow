# -*- coding: utf-8 -*-
"""Tests for quote_audit.py (mechanical verbatim-quote back-verification)."""
import unittest

import helpers  # noqa: F401

import quote_audit as qa  # type: ignore

SOURCE_TEXT = """
Fecal samples were collected from the Taohongling Nature Reserve.
PCR was performed in a total volume of 20 μL containing 1× buffer.
The annealing temperature was set at 55°C. Amplification used a
step- wise protocol described previously. All samples were stored
at minus 20 degrees until DNA extraction. Microsatellite loci were
amplified using fluorescently labeled primers and genotyped on an
automated sequencer under previously documented laboratory conditions
with published protocols.
"""


def _rec(fid, quote, level="E1_EXPLICIT", name="PCR volume"):
    return {"field_id": fid, "field_name": name, "evidence_level": level,
            "verbatim_quote": quote, "status": "SUPPORTED"}


def _evidence(records):
    return {"paper_metadata": {"title": "T"}, "evidence_records": records}


class TestAuditEvidence(unittest.TestCase):
    def test_exact_and_whitespace_mangled_quotes(self):
        ev = _evidence([
            _rec("F1", "PCR was performed in a total volume of 20 μL containing 1× buffer."),
            # line break + extra spaces inside the quote must normalize away
            _rec("F2", "PCR was performed in a total\n   volume of 20 μL containing 1× buffer."),
        ])
        rep = qa.audit_evidence(ev, SOURCE_TEXT)
        self.assertFalse(rep["summary"]["gate_failed"])
        self.assertEqual(rep["summary"]["exact_match"], 2)

    def test_hyphenated_line_break_join(self):
        ev = _evidence([_rec("F1", "used a stepwise protocol described previously")])
        rep = qa.audit_evidence(ev, SOURCE_TEXT)
        types = {e["match_type"] for e in rep["entries"]}
        self.assertIn("HYPHEN_JOIN", types)
        self.assertFalse(rep["summary"]["gate_failed"])

    def test_confusable_characters_normalized(self):
        # quote uses ASCII apostrophe, source uses curly one; and case differs
        src = 'The samples were \u201cair-dried\u201d before milling.'
        ev = _evidence([_rec("F1", 'The samples were "air-dried" before milling.')])
        rep = qa.audit_evidence(ev, src)
        self.assertEqual(rep["summary"]["exact_match"], 1)
        self.assertFalse(rep["summary"]["gate_failed"])

    def test_absent_quote_fails_gate(self):
        ev = _evidence([_rec("F1", "Total genomic DNA was extracted using the Qiamp kit.")])
        rep = qa.audit_evidence(ev, SOURCE_TEXT)
        self.assertEqual(rep["summary"]["not_found"], 1)
        self.assertTrue(rep["summary"]["gate_failed"])

    def test_empty_quote_is_skipped_not_failed(self):
        ev = _evidence([_rec("F1", "", level="E4_NR")])
        rep = qa.audit_evidence(ev, SOURCE_TEXT)
        self.assertEqual(rep["summary"]["skipped_no_quote"], 1)
        self.assertFalse(rep["summary"]["gate_failed"])

    def test_too_short_quote_flagged(self):
        ev = _evidence([_rec("F1", "55°C")])
        rep = qa.audit_evidence(ev, SOURCE_TEXT)
        self.assertEqual(rep["summary"]["too_short"], 1)
        self.assertFalse(rep["summary"]["gate_failed"])

    def test_fuzzy_match_for_single_word_drift(self):
        # 22-token needle identical to the source sentence except one word
        # ("described" vs "documented") -> unique containment 21/22 = 0.955 >= 0.95
        ev = _evidence([_rec("F1",
            "Microsatellite loci were amplified using fluorescently labeled primers "
            "and genotyped on an automated sequencer under previously described "
            "laboratory conditions with published protocols.")])
        rep = qa.audit_evidence(ev, SOURCE_TEXT)
        self.assertEqual(rep["summary"]["fuzzy_match"], 1)
        self.assertFalse(rep["summary"]["gate_failed"])

    def test_below_fuzzy_threshold_is_not_found(self):
        # 13-token needle with one word different -> 12/13 = 0.923 < 0.95
        # too short to trust as extraction noise -> genuine NOT_FOUND
        ev = _evidence([_rec("F1", "PCR was performed in a total volume of 20 μL containing 1× buffering.")])
        rep = qa.audit_evidence(ev, SOURCE_TEXT)
        self.assertTrue(rep["summary"]["gate_failed"])

    def test_strict_mode_fails_on_fuzzy(self):
        ev = _evidence([_rec("F1",
            "Microsatellite loci were amplified using fluorescently labeled primers "
            "and genotyped on an automated sequencer under previously described "
            "laboratory conditions with published protocols.")])
        rep = qa.audit_evidence(ev, SOURCE_TEXT)
        self.assertFalse(rep["summary"]["gate_failed"])
        self.assertTrue(qa.gate_failed(rep, strict=True))


class TestCliGate(unittest.TestCase):
    def test_gate_exit_codes(self):
        # Gate contract: 0 clean, 1 failed — enforced via report["summary"]["gate_failed"]
        ok = qa.audit_evidence(_evidence([_rec("F1", "the annealing temperature was set at 55°C")]),
                               SOURCE_TEXT)
        bad = qa.audit_evidence(_evidence([_rec("F1", "this sentence appears nowhere in the source at all")]),
                                SOURCE_TEXT)
        self.assertFalse(ok["summary"]["gate_failed"])
        self.assertTrue(bad["summary"]["gate_failed"])


if __name__ == "__main__":
    unittest.main()

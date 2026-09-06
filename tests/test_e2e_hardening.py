# -*- coding: utf-8 -*-
"""Regression tests born from the 2026-09-06 end-to-end trial:

1. agent_search.parse_openalex_item must survive OpenAlex entries with
   explicitly-null nested fields ("primary_location": null) and a single
   malformed entry must never abort the whole result batch.
2. download_oa_papers.run_pipeline must classify every Include/Uncertain
   input record into the ledger (stage8_oa_download.md §五 three-status
   taxonomy), fail with exit code 2 on coverage gaps, and label blocked
   open-access papers OA_BOT_BLOCKED instead of a misleading PAYWALLED.
"""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import helpers  # noqa: F401

import agent_search as ags  # type: ignore
import download_oa_papers as dop  # type: ignore


def _work(**overrides):
    item = {
        "id": "https://openalex.org/W1", "display_name": "A Paper",
        "doi": "https://doi.org/10.1000/x", "publication_year": 2024,
        "type": "article", "cited_by_count": 3,
        "authorships": [{"author": {"display_name": "Auth Or"}}],
        "primary_location": {"source": {"display_name": "J"}}, 
        "best_oa_location": None, "open_access": {"is_oa": False, "oa_status": "closed"},
        "abstract_inverted_index": None, "referenced_works": [],
    }
    item.update(overrides)
    return item


class TestParseDefense(unittest.TestCase):
    """agent_search.parse_openalex_item 对畸形条目的防御。"""

    def test_null_primary_location_does_not_crash(self):
        rec = ags.parse_openalex_item(_work(primary_location=None))
        self.assertEqual(rec["journal"], "Academic Source")

    def test_null_authorships_and_oa_location(self):
        rec = ags.parse_openalex_item(_work(authorships=None, best_oa_location=None,
                                            open_access=None, abstract_inverted_index=None))
        self.assertEqual(rec["authors"], [])
        self.assertIsNone(rec["pdf_url"])
        self.assertFalse(rec["is_oa"])

    def test_non_dict_item_raises_valueerror(self):
        with self.assertRaises(ValueError):
            ags.parse_openalex_item(None)

    def test_single_malformed_item_does_not_abort_batch(self):
        payload = {"results": [_work(), None, "not-a-dict", _work(display_name="Second")]}
        orig = ags.urllib.request.urlopen

        class R:
            status = 200
            def read(self):
                return json.dumps(payload).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        ags.urllib.request.urlopen = lambda req, timeout=20: R()
        try:
            recs, err = ags.query_openalex_headless("q", limit=10)
        finally:
            ags.urllib.request.urlopen = orig
        self.assertIsNone(err)
        self.assertEqual(len(recs), 2, "malformed entries skipped, good ones kept")


class TestLedgerCoverage(unittest.TestCase):
    """download_oa_papers 台账三级分类与覆盖度自检（§五验收标准）。"""

    def _run(self, records, max_downloads=None, fail_download=False):
        td = tempfile.TemporaryDirectory()
        inp = Path(td.name) / "in.json"
        inp.write_text(json.dumps({"records": records}, ensure_ascii=False), encoding="utf-8")
        ret = (False, "HTTP Error 403: Forbidden") if fail_download else (True, "Success")
        with patch.object(dop, "query_openalex_oa", return_value=(None, "closed")),              patch.object(dop, "download_file", return_value=ret):
            rc = dop.run_pipeline(str(inp), str(Path(td.name) / "out"), max_downloads=max_downloads)
        ledger = json.loads((Path(td.name) / "out" / "download_ledger.json").read_text(encoding="utf-8"))
        td.cleanup()
        return rc, ledger

    def _rec(self, rid, with_url=True, oa="gold", status="Include"):
        return {"id": rid, "title": f"Paper {rid}", "authors": ["A"], "year": 2024,
                "doi": ("NR" if not with_url else "10.1000/x"), "screening_status": status,
                **({"pdf_url": f"https://example.org/{rid}.pdf", "oa_status": oa} if with_url else {})}

    def test_records_without_link_enter_ledger_as_paywalled(self):
        rc, ledger = self._run([self._rec("T1", with_url=False)])
        self.assertEqual(rc, 0)
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["status"], "PAYWALLED")

    def test_coverage_check_passes_when_all_classified(self):
        rc, ledger = self._run([self._rec("T1", with_url=False),
                                self._rec("T2", oa="closed")])
        self.assertEqual(rc, 0)
        self.assertEqual(len(ledger), 2)

    def test_truncation_fails_coverage_check(self):
        rc, ledger = self._run([self._rec("T1"), self._rec("T2"), self._rec("T3")],
                               max_downloads=1)
        self.assertEqual(len(ledger), 1, "max_downloads truncates the batch")
        self.assertEqual(rc, 2, "coverage guard must FAIL (exit 2) on truncated ledger")

    def test_blocked_open_access_labeled_oa_bot_blocked(self):
        rc, ledger = self._run([self._rec("T1", oa="gold")], fail_download=True)
        self.assertEqual(ledger[0]["status"], "OA_BOT_BLOCKED",
                         "gold-OA blocked by bots must NOT be mislabeled PAYWALLED")
        self.assertIn("免费", ledger[0]["note"])
        self.assertEqual(rc, 0)

    def test_closed_paywall_not_mislabeled_bot_blocked(self):
        rc, ledger = self._run([self._rec("T1", with_url=False, oa="closed")])
        self.assertEqual(ledger[0]["status"], "PAYWALLED")

    def test_exclude_records_never_download_nor_enter_ledger(self):
        rc, ledger = self._run([self._rec("T1", status="Exclude")])
        self.assertEqual(len(ledger), 0)
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()

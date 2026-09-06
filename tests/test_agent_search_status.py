# -*- coding: utf-8 -*-
"""Regression tests for agent_search.py network-contract fixes.

Root cause (found in end-to-end trial, 2026-09-06):
1. A custom UA suffix "(Headless Agent Search Pipeline)" triggered instant
   HTTP 429 from OpenAlex, while a browser-shaped UA passed (verified live:
   browser UA -> 200, agent UA -> 429, mailto irrelevant).
2. A failed query was reported as "status": "SUCCESS" with 0 records —
   downstream consumers would misread it as "no literature exists".
"""
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

import helpers  # noqa: F401  (sys.path bootstrap)

import agent_search as ags  # type: ignore


def _openalex_payload(n=2):
    works = []
    for i in range(n):
        works.append({
            "id": f"https://openalex.org/W{i}", "display_name": f"Paper {i}",
            "doi": f"https://doi.org/10.1000/p{i}", "publication_year": 2024,
            "type": "article", "cited_by_count": i,
            "authorships": [{"author": {"display_name": f"Author {i}"}}],
            "primary_location": {"source": {"display_name": "Journal of Tests"}},
            "best_oa_location": None, "referenced_works": [],
        })
    return {"results": works}


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._data = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestNetworkContract(unittest.TestCase):
    """The request profile itself must survive OpenAlex bot throttling."""

    def setUp(self):
        self._orig_urlopen = ags.urllib.request.urlopen

    def tearDown(self):
        ags.urllib.request.urlopen = self._orig_urlopen

    def test_request_carries_mailto_and_browser_shaped_ua(self):
        captured = {}

        def fake_urlopen(req, timeout=20):
            captured["url"] = req.full_url
            captured["ua"] = req.headers.get("User-agent", "")
            return _FakeResponse(_openalex_payload(1))

        ags.urllib.request.urlopen = fake_urlopen
        recs, err = ags.query_openalex_headless("battery degradation", limit=5)
        self.assertIsNone(err)
        self.assertEqual(len(recs), 1)
        self.assertIn("mailto=", captured["url"], "OpenAlex politeness pool requires mailto")
        self.assertNotIn("Pipeline", captured["ua"],
                         "agent-style UA suffix caused instant HTTP 429 in live trial")
        self.assertTrue(captured["ua"].startswith("Mozilla/5.0"))

    def test_http_429_surfaces_as_error_not_silent_empty(self):
        def fake_urlopen(req, timeout=20):
            raise HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b""))

        ags.urllib.request.urlopen = fake_urlopen
        recs, err = ags.query_openalex_headless("anything", limit=5)
        self.assertEqual(recs, [])
        self.assertIsNotNone(err)
        self.assertIn("429", err)


class TestStatusSemantics(unittest.TestCase):
    """Output contract: FAILED must be distinguishable from an honest empty result."""

    def _run(self, candidates, error, mode="quick"):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "result.json"
            orig_q, orig_s, orig_d = (ags.query_openalex_headless,
                                      ags.run_snowball_search, ags.run_deep_search)
            ags.query_openalex_headless = lambda *a, **k: (candidates, error)
            ags.run_snowball_search = lambda *a, **k: (candidates, [error] if error else [])
            ags.run_deep_search = lambda *a, **k: (candidates, {"mode": mode, "errors": [error] if error else []})
            try:
                rc = ags.run_headless_search(query="topic x", mode=mode, output_file=str(out))
                payload = json.loads(out.read_text(encoding="utf-8"))
            finally:
                ags.query_openalex_headless, ags.run_snowball_search, ags.run_deep_search = orig_q, orig_s, orig_d
        return rc, payload

    def _one_record(self):
        return ags.parse_openalex_item(_openalex_payload(1)["results"][0])

    def test_failed_query_is_failed_not_empty_success(self):
        rc, p = self._run([], "HTTP Error 429: Too Many Requests")
        self.assertEqual(p["status"], "FAILED")
        self.assertIn("429", p["errors"][0])
        self.assertEqual(rc, 1)

    def test_clean_success(self):
        rc, p = self._run([self._one_record()], None)
        self.assertEqual(p["status"], "SUCCESS")
        self.assertEqual(p["errors"], [])
        self.assertEqual(rc, 0)

    def test_partial_success_is_flagged(self):
        rc, p = self._run([self._one_record()], "HTTP Error 429")
        self.assertEqual(p["status"], "SUCCESS_WITH_ERRORS")
        self.assertEqual(rc, 0)

    def test_deep_mode_failure_propagates(self):
        rc, p = self._run([], "HTTP Error 429: Too Many Requests", mode="deep")
        self.assertEqual(p["status"], "FAILED")
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()

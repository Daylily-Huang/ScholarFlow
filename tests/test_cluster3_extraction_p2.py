# -*- coding: utf-8 -*-
"""extraction 技能 P2 回归（2026-09-16 集群审查）。

覆盖：证据侧无方向词不得当成方向一致（P2-17）、指标方向词表冲突不得猜（P2-18）、
不可读 PDF 必须以非零退出码与产物标记暴露（P2-19）、上下文单元锚定不得是死检查
（P2-21）、「showed X, suggesting Y」不得记成结果（P2-22）。

（P2-20 的修复即 `tests/test_schema_gate.py::test_builder_validates_by_default`
本身：它原带 `hasattr` 守卫而永久空操作，现已改为显式断言。）
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import helpers  # noqa: F401

REPO_ROOT = helpers.REPO_ROOT
SCRIPTS = REPO_ROOT / "skills" / "literature-evidence-extraction" / "scripts"
LOCATOR = SCRIPTS / "pdf_evidence_locator.py"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SCRIPTS))

from shared.text.polarity import check_polarity  # noqa: E402
import claim_alignment as cal  # noqa: E402
from context_expansion import (  # noqa: E402
    audit_context_sufficiency, classify_semantic_role,
)


class TestEvidenceSideWithoutDirectionIsNotAgreement(unittest.TestCase):
    """P2-17：主张有方向、证据侧一个方向词都没有 ⇒ 不可比，不是"方向一致"。

    旧实现在证据侧无方向词时静默 `continue`，循环走完返回 None 被当作一致——
    词表外的反向结论（attenuated / blunted）因此被确认为 SUPPORTED。
    """

    CLAIM = "biomass increases with nitrogen"

    def _verdict(self, evidence):
        return (check_polarity(self.CLAIM, evidence) or {}).get("verdict")

    def test_lexicon_external_antonyms_are_unresolved(self):
        for ev in ("biomass was attenuated by nitrogen",
                   "biomass was blunted by nitrogen"):
            with self.subTest(evidence=ev):
                self.assertEqual(self._verdict(ev), "UNRESOLVED")

    def test_evidence_without_any_direction_word_is_unresolved(self):
        self.assertEqual(self._verdict("samples were collected in June"), "UNRESOLVED")

    def test_in_lexicon_opposite_still_contradictory(self):
        """反向的**已收录**词仍应判矛盾，不得被 fail-closed 吞掉。"""
        self.assertEqual(self._verdict("biomass decreased with nitrogen"), "CONTRADICTORY")

    def test_same_direction_still_agrees(self):
        self.assertIsNone(self._verdict("biomass increased with nitrogen"))


class TestMetricDirectionDoesNotGuess(unittest.TestCase):
    """P2-18：指标名同时命中两侧词表时不得猜方向。

    `yield loss` / `germination failure` / `biomass loss` 都同时含 HIGHER 侧词根与
    LOWER 侧词根；原实现先判 HIGHER，于是把它们判成 HIGHER_IS_BETTER，
    **反向结论被确认为 SUPPORTED**。
    """

    def test_conflicting_metric_names_are_unresolved(self):
        for metric in ("yield loss", "germination failure", "biomass loss"):
            with self.subTest(metric=metric):
                self.assertTrue(cal._metric_matches(metric, cal.HIGHER_IS_BETTER_METRICS))
                self.assertTrue(cal._metric_matches(metric, cal.LOWER_IS_BETTER_METRICS))

    def test_unambiguous_metrics_still_resolve(self):
        self.assertTrue(cal._metric_matches("biomass", cal.HIGHER_IS_BETTER_METRICS))
        self.assertFalse(cal._metric_matches("biomass", cal.LOWER_IS_BETTER_METRICS))
        self.assertTrue(cal._metric_matches("error rate", cal.LOWER_IS_BETTER_METRICS))

    def test_matching_is_word_bounded(self):
        """原实现是裸子串匹配：`mae` 会命中 `maize`、`cost` 会命中 `costal`。"""
        self.assertFalse(cal._metric_matches("maize yield", cal.LOWER_IS_BETTER_METRICS))
        self.assertFalse(cal._metric_matches("costal survey", cal.LOWER_IS_BETTER_METRICS))


class TestPdfTextUnavailableIsLoud(unittest.TestCase):
    """P2-19：文本抽取失败必须同时体现在**退出码**与**机器可读产物**里。

    原实现只把 TEXT_UNAVAILABLE 写进 stderr 与内存中的 pages[0].warnings——
    产物 JSON 里一个字都没有，调用方拿到的结果与"正常检索但没命中"完全同形。
    """

    def _run(self, target, out_json):
        return subprocess.run([sys.executable, str(LOCATOR), "-i", str(target),
                               "-q", "biomass", "-o", str(out_json)],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", cwd=str(REPO_ROOT))

    def test_scanned_pdf_fails_loudly(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "scan.pdf"
            pdf.write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
            out = Path(td) / "out.json"
            proc = self._run(pdf, out)
            self.assertNotEqual(proc.returncode, 0, "文本不可用却退出 0")
            self.assertIn("TEXT_UNAVAILABLE", proc.stderr)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("text_extraction", payload,
                          "产物必须携带抽取健康度，否则与'没命中'同形")
            self.assertTrue(payload["text_extraction"]["text_unavailable"])

    def test_plain_text_still_succeeds(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            txt = Path(td) / "plain.txt"
            txt.write_text("The biomass increased with nitrogen addition.\n", encoding="utf-8")
            out = Path(td) / "out.json"
            proc = self._run(txt, out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(payload["text_extraction"]["text_unavailable"])


class TestContextUnitAnchoringIsNotDead(unittest.TestCase):
    """P2-21：8 点清单第 6 条原为硬编码 True 的死检查。"""

    def _audit(self, record, ctx=None):
        return audit_context_sufficiency(record, ctx, "doc text")

    def test_unanchored_record_is_flagged(self):
        res = self._audit({"verbatim_quote": "Biomass increased with nitrogen.",
                           "claim_status": "SUPPORTED"})
        self.assertFalse(res["checks"]["context_unit_anchored"],
                         "无上下文单元绑定的记录不得判为已锚定")
        self.assertTrue(any("Context unit" in f for f in res["failures"]))

    def test_bound_record_passes(self):
        res = self._audit({"verbatim_quote": "Biomass increased with nitrogen.",
                           "claim_status": "SUPPORTED",
                           "context_unit": "ASSAY-STR-01"})
        self.assertTrue(res["checks"]["context_unit_anchored"])


class TestInterpretiveTailIsNotAnEmpiricalResult(unittest.TestCase):
    """P2-22：`, suggesting X` / `, indicating X` 不得记成结果。

    原 `en_speculation` 各支一律要求 `suggesting that`，于是 SKILL.md 点名的那个
    句式（逗号 + 分词、**无 that**）完全漏网。
    """

    def _role(self, text, section="3. Results"):
        role, _ = classify_semantic_role(text, section_heading=section)
        return getattr(role, "value", role)

    def test_trailing_interpretive_clause_is_downgraded(self):
        for text in ("The results showed that biomass increased, suggesting a fertilization effect.",
                     "The treatment showed a significant increase, suggesting a dose effect.",
                     "Biomass increased with nitrogen, indicating a fertilization effect."):
            with self.subTest(text=text[:40]):
                self.assertEqual(self._role(text), "DISCUSSION_INTERPRETATION")

    def test_plain_result_sentence_is_untouched(self):
        self.assertEqual(self._role("Biomass increased significantly with nitrogen addition."),
                         "CURRENT_STUDY_RESULT")


if __name__ == "__main__":
    unittest.main()

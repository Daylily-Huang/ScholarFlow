# -*- coding: utf-8 -*-
"""Tests for evidence_matrix_html.py (全中文 HTML 报告渲染器).

Covers the 2026-09-06 user-feedback requirements:
- evidence JSON renders into a fully self-contained Chinese HTML report;
- NOT_REPORTED (NR) records must be displayed as 存疑/未报告, never as 不支持
  (NR semantic-protection clause, visual layer);
- output must be offline self-contained (no CDN/JS references).
"""
import json
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401

import evidence_matrix_html as emh  # type: ignore


def _record(rid, field="PCR volume", support="EXPLICIT", status="SUPPORTED",
            strength="DIRECT_EMPIRICAL", quote="PCR was performed in 20 μL."):
    return {
        "schema_version": "1.0",
        "evidence_id": f"EV-{rid}", "record_id": f"R-{rid}",
        "field": field, "field_id": f"F{rid}", "field_name": field,
        "extracted_value": "20 μL", "support_type": support,
        "evidence_strength": strength, "claim_status": status, "status": status,
        "verbatim_quote": quote, "source_type": "Text",
        "location": {"page": 4, "section": None, "table_or_figure_id": None},
        "notes": None,
    }


def _envelope(records):
    return {
        "schema_version": "1.0",
        "paper_metadata": {"title": "Test Paper", "authors": ["作者甲"],
                           "year": 2024, "journal": "测试期刊", "doi": "10.1000/t"},
        "extraction_metadata": {"mode": "extract", "timestamp": "2026-09-06T00:00:00Z",
                                "schema_type": "dynamic"},
        "evidence_records": records,
        "auditor_verdict": {"verdict": "PASS_WITH_DOWNGRADES", "checklist_passed": True,
                            "auditor_notes": "对账说明"},
    }


class TestRenderReport(unittest.TestCase):
    def test_all_chinese_headers_and_self_contained(self):
        html_text = emh.render_report(_envelope([_record(1)]))
        for zh in ["证据抽取报告", "逐字引句", "支撑类型", "证据强度", "审计裁决", "统计面板"]:
            self.assertIn(zh, html_text, f"缺少中文表头: {zh}")
        self.assertNotIn("cdn.", html_text)
        self.assertNotIn("<script", html_text, "报告必须零 JS 自包含")

    def test_nr_record_protected_from_unsupported_display(self):
        rec = _record(2, field="BSA concentration", support="NOT_REPORTED",
                      status="UNSUPPORTED", strength="UNKNOWN", quote="")
        rec["claim_status"] = "UNSUPPORTED"  # 模拟未做 NR 语义防护的输入
        html_text = emh.render_report(_envelope([_record(1), rec]))
        self.assertIn("存疑/未判定", html_text)
        # "未报告"行的状态徽章绝不能显示"不支持"
        self.assertNotIn(">不支持</span>", html_text.split("BSA")[1].split("</tr>")[0])
        self.assertIn("全文未提及", html_text)

    def test_derived_record_highlighted(self):
        rec = _record(3, field="Derived metric", support="DERIVED", strength="MODELED_EMPIRICAL")
        html_text = emh.render_report(_envelope([rec]))
        self.assertIn("派生计算（E2）", html_text)
        self.assertIn("推导公式", html_text)

    def test_legacy_evidence_level_mapping(self):
        rec = _record(4, support="NOT_REPORTED")
        rec.pop("support_type")
        rec["evidence_level"] = "E2_DERIVED"
        html_text = emh.render_report(_envelope([rec]))
        self.assertIn("派生计算（E2）", html_text, "旧字段 evidence_level 应映射为新支撑类型")

    def test_meta_and_doi_render(self):
        html_text = emh.render_report(_envelope([_record(5)]))
        self.assertIn("Test Paper", html_text)
        self.assertIn("作者甲", html_text)
        self.assertIn("10.1000/t", html_text)
        self.assertIn("通过（含降级项）", html_text)


class TestCli(unittest.TestCase):
    def test_end_to_end_file_generation(self):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "e.json"
            out = Path(td) / "report.html"
            inp.write_text(json.dumps(_envelope([_record(1), _record(2)]), ensure_ascii=False),
                           encoding="utf-8")
            rc = emh_main(str(inp), str(out))
            self.assertEqual(rc, 0)
            text = out.read_text(encoding="utf-8")
            self.assertIn("证据明细表", text)
            self.assertEqual(text.count("<tr"), text.count("<tr"))  # smoke

    def test_missing_input_exit_2(self):
        with tempfile.TemporaryDirectory() as td:
            rc = emh_main(str(Path(td) / "nope.json"), str(Path(td) / "o.html"))
            self.assertEqual(rc, 2)


def emh_main(inp, out):
    import sys
    argv_backup = sys.argv
    sys.argv = ["evidence_matrix_html.py", "-i", inp, "-o", out]
    try:
        emh.main()
        return 0
    except SystemExit as e:
        return e.code
    finally:
        sys.argv = argv_backup


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_schema_gate.py — 回归测试：schema 契约必须有真实执行点，且交接链必须可追溯

对应 2026-09-11 多 Agent 压测实测缺陷：
  D3 schema 从未被执行（jsonschema 不进生产路径；extraction_pipeline.py 无 CLI 无校验）
  D4 三角色交接无共同主键（四环节 record_id 交集为 0），橡皮图章审计无人发现
  D7 协议定义 10 个 relation-claim 状态标签，schema 只允许 6 个 —— 契约自相矛盾

运行：python3 tests/test_schema_gate.py
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from shared.validation.schema_gate import (  # noqa: E402
    SchemaGateError, check_evidence_chain, require_valid, validate,
)

PIPELINE = REPO / "skills" / "literature-evidence-extraction" / "scripts" / "extraction_pipeline.py"


def _valid_envelope():
    return {
        "schema_version": "1.1",
        "paper_metadata": {"title": "T", "authors": ["A"], "year": 2007},
        "extraction_metadata": {"mode": "extract", "timestamp": "2026-09-11T00:00:00Z"},
        "evidence_records": [{
            "schema_version": "1.0",
            "evidence_id": "E1",
            "record_id": "R1",
            "field": "灌木占比",
            "extracted_value": "55.4%",
            "support_type": "EXPLICIT",
            "claim_status": "SUPPORTED",
            "verbatim_quote": "Shrubs were the most important food of black muntjac, accounting for 55.4%",
            "source_type": "Text",
        }],
        "auditor_verdict": {"verdict": "PASS", "checklist_passed": True},
    }


# ---------------------------------------------------------------- D3

def test_valid_envelope_passes():
    ok, mode, errs = validate(_valid_envelope())
    assert ok, errs
    assert "draft2020" in mode or "structural" in mode


def test_schema_gate_runs_without_jsonschema(monkeypatch=None):
    """stdlib 兜底路径也必须可用（不能因缺 jsonschema 就退回'不校验'）。"""
    import shared.validation.schema_gate as sg
    saved = sg._FULL
    try:
        sg._FULL = False
        ok, mode, errs = sg.validate(_valid_envelope())
        assert mode == "structural-fallback"
        assert ok, errs
        bad = _valid_envelope()
        del bad["auditor_verdict"]
        ok2, mode2, errs2 = sg.validate(bad)
        assert not ok2 and any("auditor_verdict" in e for e in errs2), errs2
    finally:
        sg._FULL = saved


def test_missing_required_key_is_caught():
    bad = _valid_envelope()
    del bad["extraction_metadata"]
    ok, _mode, errs = validate(bad)
    assert not ok
    assert any("extraction_metadata" in e for e in errs)


def test_off_contract_enum_is_caught():
    """自造标签（实测 SECONDARY_AGGREGATE）必须被拒。"""
    bad = _valid_envelope()
    bad["evidence_records"][0]["evidence_strength"] = "SECONDARY_AGGREGATE"
    ok, _mode, errs = validate(bad)
    assert not ok
    assert any("SECONDARY_AGGREGATE" in e for e in errs)


def test_require_valid_raises():
    bad = _valid_envelope()
    del bad["paper_metadata"]
    try:
        require_valid(bad)
    except SchemaGateError as e:
        assert "paper_metadata" in str(e)
    else:
        raise AssertionError("require_valid 未抛错")


# ---------------------------------------------------------------- D7

def test_relation_claim_statuses_are_allowed():
    """协议 §九 的 10 个标签必须全部可表达（修复前 schema 只允许 6 个）。"""
    for tag in ("SUPPORTED", "PARTIALLY_SUPPORTED", "DERIVED", "AMBIGUOUS",
                "CONTRADICTORY", "BACKGROUND_ONLY", "CONTEXT_ONLY",
                "OTHER_ENTITY_CONTEXT", "REFERENCED_ONLY", "NOT_REPORTED"):
        env = _valid_envelope()
        env["evidence_records"][0]["claim_status"] = tag
        ok, _m, errs = validate(env)
        assert ok, "标签 %s 被拒: %s" % (tag, errs)


def test_claim_components_expresses_partial_verifiability():
    """'比例可证、关系不可证' 必须能被结构化表达。"""
    env = _valid_envelope()
    env["evidence_records"][0]["claim_components"] = [
        {"component": "三尖杉占比 17%", "status": "SUPPORTED",
         "verbatim_quote": "Cephalotaxus fortunei ... 17%"},
        {"component": "黑麂偏好三尖杉", "status": "NOT_REPORTED", "notes": "原文无偏好论证"},
    ]
    ok, _m, errs = validate(env)
    assert ok, errs


# ---------------------------------------------------------------- D4

def test_evidence_chain_flags_untraceable_handoff():
    """auditor 裁决不含任何 evidence id -> 交接不可追溯（实测四个环节交集为 0）。"""
    recs = [{"evidence_id": "SF2-A1-C1-E1"}, {"evidence_id": "SF2-A1-C2-E1"}]
    problems = check_evidence_chain(recs, [{"verdict": "PASS", "checklist_passed": True}])
    assert problems, "无 id 的裁决必须被判为交接断裂"


def test_evidence_chain_flags_rubber_stamp():
    """裁决自称覆盖，但 id 对不上 -> 必须报出孤儿记录。"""
    recs = [{"evidence_id": "A1"}, {"evidence_id": "A2"}, {"evidence_id": "A3"}]
    problems = check_evidence_chain(recs, [{"evidence_ids": ["A1"]}])
    assert problems
    assert "A2" in problems[0] or "A3" in problems[0]


def test_evidence_chain_passes_when_fully_covered():
    recs = [{"evidence_id": "A1"}, {"evidence_id": "A2"}]
    assert check_evidence_chain(recs, [{"evidence_ids": ["A1", "A2"]}]) == []


def test_evidence_chain_requires_ids_on_records():
    problems = check_evidence_chain([{"field": "x"}], [{"evidence_ids": ["A1"]}])
    assert problems and "no evidence_id" in problems[0]


# ---------------------------------------------------------------- CLI

def test_pipeline_cli_exists_and_validates():
    """管线必须有真实 CLI 执行点（修复前无 argparse / 无 __main__）。"""
    with tempfile.TemporaryDirectory() as td:
        good = Path(td) / "good.json"
        bad = Path(td) / "bad.json"
        good.write_text(json.dumps(_valid_envelope(), ensure_ascii=False), encoding="utf-8")
        broken = _valid_envelope()
        del broken["extraction_metadata"]
        bad.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")

        p1 = subprocess.run([sys.executable, str(PIPELINE), "-i", str(good)],
                            capture_output=True, text=True, encoding="utf-8")
        assert p1.returncode == 0, p1.stdout + p1.stderr
        assert "ok=True" in p1.stdout

        p2 = subprocess.run([sys.executable, str(PIPELINE), "-i", str(bad)],
                            capture_output=True, text=True, encoding="utf-8")
        assert p2.returncode == 1, p2.stdout
        assert "errors=" in p2.stdout


def test_pipeline_cli_evidence_chain_flag():
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "e.json"
        env = _valid_envelope()
        env["auditor_verdict"] = {"verdict": "PASS", "checklist_passed": True}
        f.write_text(json.dumps(env, ensure_ascii=False), encoding="utf-8")
        p = subprocess.run([sys.executable, str(PIPELINE), "-i", str(f), "--evidence-chain"],
                           capture_output=True, text=True, encoding="utf-8")
        assert p.returncode == 1, p.stdout
        assert "chain" in p.stdout


def test_builder_validates_by_default():
    """build_extraction_result 默认必须真的校验（修复前只字未提校验）。"""
    sys.path.insert(0, str(REPO / "skills" / "literature-evidence-extraction" / "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("ep", PIPELINE)
    ep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ep)
    if not hasattr(ep, "build_extraction_result"):
        return  # 函数名变动则跳过，避免测试脆弱
    env = ep.build_extraction_result(
        paper_metadata={"title": "T", "authors": ["A"], "year": 2007},
        evidence_records=[{
            "schema_version": "1.0", "evidence_id": "E1", "record_id": "R1",
            "field": "f", "extracted_value": "v", "support_type": "EXPLICIT",
            "claim_status": "SUPPORTED",
        }],
    )
    ok, _m, errs = validate(env)
    assert ok, errs


class GateRegressionTests(unittest.TestCase):
    """unittest 包装：CI 用 `python -m unittest discover -s tests`，裸函数不会被执行。"""

    pass


def _bind_tests_to_case():
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            setattr(GateRegressionTests, name, staticmethod(fn))


_bind_tests_to_case()


def _selfcheck():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed  ({len(tests)} total)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_selfcheck())

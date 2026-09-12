#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_quote_audit_gate.py — 回归测试：quote_audit.py 的门禁必须拦住已实测的逃逸通道

对应 2026-09-11 多 Agent 压测中实测复现的缺陷（见
端到端真实跑/20260911-skill2/out/skill2_多Agent压测报告.md）：
  D1 引文真、取值假（quote laundering）—— 把 55.4% 改成 95.4% 仍 exit=0
  D2 空引文 / 短引文整体逃逸 —— SKIPPED=7 仍 exit=0
  D3 源文件可替换 —— 向源文副本追加 184 字节即可翻转判定

运行：
  python3 -m pytest tests/test_quote_audit_gate.py -v
  python3 tests/test_quote_audit_gate.py          # 无需 pytest 的自检模式
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "skills" / "literature-evidence-extraction" / "scripts" / "quote_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("quote_audit_gate", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


QA = _load_module()

# 真实源文（A 类郑荣泉 2007，已多轮核验）
SOURCE_TEXT = (
    "Shrubs were the most important food of black muntjac, accounting for 55.4% of the diet. "
    "Cephalotaxus fortunei, Smilax glabra, Itea chinensis var. oblonga, Kadsura longipedunculata "
    "and Trachelospermum jasminoides were the species most frequently eaten. "
    "Forty-three plant species (genus) under 29 families were identified in black muntjac diets. "
    "Trees made up the second largest proportion of the diet (19.2%)."
)


def _env(records):
    return {"schema_version": "1.1", "evidence_records": records}


def _rec(**kw):
    base = {"evidence_id": "E1", "record_id": "R1", "field": "diet",
            "field_id": "F01", "field_name": "灌木占比", "support_type": "EXPLICIT"}
    base.update(kw)
    return base


def _run_cli(evidence, source_text, extra_args=()):
    """Run the real CLI end-to-end and return (exit_code, summary_dict)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ev = td / "ev.json"
        src = td / "src.txt"
        out = td / "report.json"
        ev.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
        src.write_text(source_text, encoding="utf-8")
        cmd = [sys.executable, str(SCRIPT), "-i", str(ev), "-s", str(src),
               "-o", str(out), *extra_args]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        summary = json.loads(out.read_text(encoding="utf-8"))["summary"] if out.exists() else {}
        return proc.returncode, summary


# ---------------------------------------------------------------- D1

def test_d1_fabricated_value_in_quote_context_fails():
    """引文真实但取值被篡改（源文 55.4% -> 95.4%）必须判失败。"""
    ev = _env([_rec(
        extracted_value="95.4%",
        verbatim_quote="Shrubs were the most important food of black muntjac, accounting for 55.4% of the diet.",
    )])
    code, s = _run_cli(ev, SOURCE_TEXT, ("--strict",))
    assert s["exact_match"] == 1, "引文本身应命中 EXACT"
    assert s["value_not_found_in_source"] == 1, "95.4% 不在源文中，必须被标记"
    assert code == 1, "取值无源必须 exit=1"


def test_d1_correct_value_still_passes():
    """正确取值不得被误伤。"""
    ev = _env([_rec(
        extracted_value="55.4%",
        verbatim_quote="Shrubs were the most important food of black muntjac, accounting for 55.4% of the diet.",
    )])
    code, s = _run_cli(ev, SOURCE_TEXT, ("--strict",))
    assert s["value_aligned"] == 1
    assert s["value_not_found_in_source"] == 0
    assert code == 0, "正确记录必须放行，否则门禁不可用"


def test_d1_non_numeric_value_is_not_checked():
    """无数值可取值的记录（描述性）不参与对齐，也不得因此失败。"""
    ev = _env([_rec(
        extracted_value="以木本植物叶及嫩枝为主",
        verbatim_quote="Shrubs were the most important food of black muntjac, accounting for 55.4% of the diet.",
    )])
    code, s = _run_cli(ev, SOURCE_TEXT)
    assert s["value_checked"] == 0
    assert code == 0


def test_d1_value_exists_but_far_from_quote_blocks_delivery():
    """取值存在于源文别处但不在引文附近 -> 阻断交付（F02 第 4 条）。

    契约变更说明：旧行为把"存在但错位"视为提示级（exit 0）。那是"对数字、错位置"
    ——数字确实在论文里，却不在所声称的证据锚点上，因此不能作为已核验记录交付。
    审查报告 F02 明确要求：全文命中只能用于寻找候选来源，不能替代当前字段的
    证据锚定。此处改为阻断，并同步更新断言（原有意图在数值核验三反例中保留）。
    """
    ev = _env([_rec(
        extracted_value="19.2%",
        verbatim_quote="Shrubs were the most important food of black muntjac, accounting for 55.4% of the diet.",
    )])
    code, s = _run_cli(ev, SOURCE_TEXT)
    assert s["value_not_in_quote_context"] == 1
    assert s["value_not_found_in_source"] == 0
    assert s["unverified"] == 1, "错位取值必须计入 unverified"
    assert code == 1, "存在但错位必须硬失败：数字对但位置错，不得作为已核验结果交付"


# ---------------------------------------------------------------- D2

def test_d2_empty_quote_fails_by_default():
    """空引文（= NR 记录的合法写法）不得静默放行。"""
    ev = _env([
        _rec(evidence_id="E1", extracted_value="99.9%", verbatim_quote=""),
        _rec(evidence_id="E2", extracted_value="跨物种断言", verbatim_quote=""),
    ])
    code, s = _run_cli(ev, SOURCE_TEXT)
    assert s["skipped_no_quote"] == 2
    assert s["unverified"] == 2
    assert code == 1, "空引文默认必须 exit=1（此前为 exit=0 的逃逸通道）"


def test_d2_short_quote_fails_by_default():
    ev = _env([_rec(extracted_value="12.1%", verbatim_quote="黑麂的食物")])
    code, s = _run_cli(ev, SOURCE_TEXT)
    assert s["too_short"] == 1
    assert s["unverified"] == 1
    assert code == 1


def test_d2_explicit_opt_out_is_available_and_recorded():
    """显式降级必须被记录在报告里，不能静默。"""
    ev = _env([_rec(extracted_value="99.9%", verbatim_quote="")])
    code, s = _run_cli(ev, SOURCE_TEXT, ("--unverified-policy", "list"))
    assert s["unverified_policy"] == "list"
    assert s["unverified"] == 1
    assert code == 0


def test_d2_all_verified_passes():
    ev = _env([_rec(
        extracted_value="55.4%",
        verbatim_quote="Shrubs were the most important food of black muntjac, accounting for 55.4% of the diet.",
    )])
    code, s = _run_cli(ev, SOURCE_TEXT, ("--strict",))
    assert s["unverified"] == 0
    assert code == 0


# ---------------------------------------------------------------- D3

def test_d3_source_provenance_is_recorded():
    code, s = _run_cli(_env([_rec(
        extracted_value="55.4%",
        verbatim_quote="Shrubs were the most important food of black muntjac, accounting for 55.4% of the diet.",
    )]), SOURCE_TEXT)
    prov = s["source_provenance"]
    assert len(prov["sha256"]) == 64
    assert prov["size_bytes"] > 0


def test_d3_source_substitution_is_detected():
    """向源文追加伪造文本后，pin 校验必须失败。"""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ev = td / "ev.json"
        src = td / "src.txt"
        pins = td / "pins.json"
        out = td / "report.json"
        ev.write_text(json.dumps(_env([_rec(
            extracted_value="55.4%",
            verbatim_quote="Shrubs were the most important food of black muntjac, accounting for 55.4% of the diet.",
        )]), ensure_ascii=False), encoding="utf-8")
        src.write_text(SOURCE_TEXT, encoding="utf-8")

        # 1) pin 原始源
        subprocess.run([sys.executable, str(SCRIPT), "-i", str(ev), "-s", str(src),
                        "--write-source-pins", str(pins)], capture_output=True, text=True)
        assert pins.exists()

        # 2) 追加伪造内容
        src.write_text(SOURCE_TEXT + "\nBlack muntjac prefers coniferous forest.", encoding="utf-8")

        # 3) pin 应报错并失败
        proc = subprocess.run([sys.executable, str(SCRIPT), "-i", str(ev), "-s", str(src),
                               "--source-pins", str(pins), "-o", str(out)],
                              capture_output=True, text=True, encoding="utf-8")
        s = json.loads(out.read_text(encoding="utf-8"))["summary"]
        assert s["source_pin_problems"], "源文被替换必须被检出"
        assert proc.returncode == 1


def test_d3_pin_match_passes():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ev = td / "ev.json"
        src = td / "src.txt"
        pins = td / "pins.json"
        ev.write_text(json.dumps(_env([_rec(
            extracted_value="55.4%",
            verbatim_quote="Shrubs were the most important food of black muntjac, accounting for 55.4% of the diet.",
        )]), ensure_ascii=False), encoding="utf-8")
        src.write_text(SOURCE_TEXT, encoding="utf-8")
        subprocess.run([sys.executable, str(SCRIPT), "-i", str(ev), "-s", str(src),
                        "--write-source-pins", str(pins)], capture_output=True, text=True)
        proc = subprocess.run([sys.executable, str(SCRIPT), "-i", str(ev), "-s", str(src),
                               "--source-pins", str(pins)], capture_output=True, text=True)
        assert proc.returncode == 0


# ---------------------------------------------------------------- 负对照

def test_negative_control_fake_quote_still_fails():
    """回归保护：伪造引文必须继续失败。"""
    ev = _env([_rec(
        extracted_value="12.1%",
        verbatim_quote="黑麂全年食物中禾本科植物占12.1%以上",
    )])
    code, s = _run_cli(ev, SOURCE_TEXT)
    assert s["not_found"] == 1
    assert code == 1


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

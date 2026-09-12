# -*- coding: utf-8 -*-
"""2026-09-13 多 agent 集群端到端测试发现的 6 个 P0 缺陷的回归。

每个 P0 都是"会产出错误科研结论或静默放行伪造数据"级别，来自真实素材实测：

- P0-1 反证字段在综合生产路径被 `normalize_claim()` 抹掉，反证当普通立场证据投票；
- P0-2 数值门禁被伪造值直通（千分位截断 / 比较符被丢 / 抽取值侧未做全角归一化）；
- P0-3 整篇文档当引句使"数值在引句内"恒真；
- P0-4 综合侧把「没查」当满权重证据（unchecked / inaccessible / cited_only / "NOT REPORTED"）；
- P0-5 claim 与证据的方向从不校验（加否定词的反向 claim 与忠实 claim 同样 PASS）；
- P0-6 并发写快照把 session.json 写坏（固定 .tmp 名 + 无锁 check-then-write）。
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

import helpers  # noqa: F401

from shared.execution import SessionStore, SnapshotCorrupt  # noqa: E402

REPO_ROOT = helpers.REPO_ROOT
sys.path.insert(0, os.path.join(REPO_ROOT, "skills", "literature-synthesis", "scripts"))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills", "literature-evidence-extraction", "scripts"))

import controversy_analyzer as ca  # noqa: E402
import claim_alignment as cal  # noqa: E402


def _quote_audit():
    path = os.path.join(REPO_ROOT, "skills", "literature-evidence-extraction",
                        "scripts", "quote_audit.py")
    spec = importlib.util.spec_from_file_location("sf_quote_audit_p0", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


qa = _quote_audit()


class TestP0NonEvidenceSemantics(unittest.TestCase):
    """P0-4：没查 ≠ 有证据；写法差异不得绕过零权重隔离。"""

    def test_all_non_evidence_spellings_get_zero_weight(self):
        for label in ("NOT_REPORTED", "NOT REPORTED", "NR", "unchecked", "UNCHECKED",
                      "inaccessible", "cited_only"):
            weight, kind, _ = ca.resolve_evidence_weight(
                {"support_type": label, "evidence_strength": "DIRECT_EMPIRICAL"})
            self.assertEqual(weight, 0.0, "%s -> %s" % (label, weight))
            self.assertNotEqual(kind, "DIRECT_EMPIRICAL", label)

    def test_claim_status_is_consumed(self):
        """旧实现完全不读 claim_status，于是 unchecked 被当成满权重证据。"""
        for label in ("unchecked", "inaccessible", "cited_only", "NOT_REPORTED"):
            weight, kind, _ = ca.resolve_evidence_weight(
                {"claim_status": label, "evidence_strength": "DIRECT_EMPIRICAL"})
            self.assertEqual(weight, 0.0, label)

    def test_non_evidence_claims_do_not_enter_consensus(self):
        claims = [
            {"claim_id": "C1", "paper_id": "P1", "independence_group_id": "G1",
             "stance": "SUPPORT", "evidence_strength": "DIRECT_EMPIRICAL",
             "support_type": "unchecked"},
            {"claim_id": "C2", "paper_id": "P2", "independence_group_id": "G2",
             "stance": "SUPPORT", "evidence_strength": "DIRECT_EMPIRICAL",
             "support_type": "EXPLICIT"},
        ]
        result = ca.compute_topic_consensus(claims)
        self.assertEqual(result["stance_weights"]["SUPPORT"], 1.0)
        self.assertEqual(result["excluded_from_consensus"].get("UNCHECKED"), 1)

    def test_real_evidence_is_not_harmed(self):
        weight, _, _ = ca.resolve_evidence_weight(
            {"support_type": "EXPLICIT", "evidence_strength": "DIRECT_EMPIRICAL"})
        self.assertEqual(weight, 1.0)


class TestP0ChallengeFieldsSurviveProductionPath(unittest.TestCase):
    """P0-1：normalize_claim 必须保留反证字段，否则 RFC-017 罚则在生产路径永不生效。"""

    def test_normalize_claim_preserves_challenge_fields(self):
        normalized = ca.normalize_claim({
            "claim_id": "CH1", "relation": "CHALLENGE",
            "challenge_status": "VERIFIED_CHALLENGE", "challenge_strength": "REFUTES",
            "target_claim_id": "C2", "stance": "REFUTE",
            "evidence_strength": "DIRECT_EMPIRICAL", "verbatim_quote": "q",
            "artifact_ref": "a.pdf", "independence_group_id": "G9"})
        self.assertEqual(normalized["relation"], "CHALLENGE")
        self.assertEqual(normalized["challenge_status"], "VERIFIED_CHALLENGE")
        self.assertEqual(normalized["target_claim_id"], "C2")
        self.assertEqual(normalized["independence_group_id"], "G9")
        self.assertFalse(normalized["consensus_eligible"],
                         "反证记录不得作为立场证据合格")

    def test_analyze_applies_challenge_adjustment(self):
        claims = [
            {"claim_id": "C1", "paper_id": "P1", "independence_group_id": "G1",
             "stance": "SUPPORT", "claim": "c1", "evidence_strength": "DIRECT_EMPIRICAL",
             "support_type": "EXPLICIT"},
            {"claim_id": "C2", "paper_id": "P2", "independence_group_id": "G2",
             "stance": "SUPPORT", "claim": "c2", "evidence_strength": "DIRECT_EMPIRICAL",
             "support_type": "EXPLICIT"},
            {"claim_id": "CH1", "paper_id": "P3", "independence_group_id": "G3",
             "stance": "REFUTE", "claim": "ch", "relation": "CHALLENGE",
             "challenge_status": "VERIFIED_CHALLENGE", "challenge_strength": "WEAKENS",
             "target_claim_id": "C2", "evidence_strength": "DIRECT_EMPIRICAL",
             "support_type": "EXPLICIT"},
        ]
        payload = json.dumps(ca.analyze(claims), ensure_ascii=False)
        self.assertIn("challenge_adjustment", payload)
        self.assertIn("challenge(G3:-0.25)", payload)

    def test_pending_challenge_neither_votes_nor_penalizes(self):
        claims = [
            {"claim_id": "C1", "paper_id": "P1", "independence_group_id": "G1",
             "stance": "SUPPORT", "evidence_strength": "DIRECT_EMPIRICAL",
             "support_type": "EXPLICIT"},
            {"claim_id": "CH1", "paper_id": "P2", "independence_group_id": "G2",
             "stance": "REFUTE", "relation": "CHALLENGE",
             "challenge_status": "PENDING_HUMAN_CONFIRMATION", "challenge_strength": "REFUTES",
             "target_claim_id": "C1", "evidence_strength": "DIRECT_EMPIRICAL",
             "support_type": "EXPLICIT"},
        ]
        result = ca.compute_topic_consensus(claims)
        self.assertEqual(result["stance_weights"]["REFUTE"], 0.0)
        self.assertEqual(result["stance_weights"]["SUPPORT"], 1.0)


class TestP0ClaimPolarity(unittest.TestCase):
    """P0-5：谓词字符串出现 ≠ 主张方向成立。"""

    QUOTE = ("Shrubs were the most important food of black muntjac, "
             "accounting for 55.4% of the diet.")
    CTX = {"source_role": "CURRENT_STUDY_RESULT", "location": "Results"}
    BASE = {"claim_id": "CLM-1", "subject": "black muntjac", "metric": "diet composition",
            "predicate": "most important food", "object": "shrubs"}

    def _verify(self, text):
        return cal.verify_claim_alignment(dict(self.BASE, text=text), self.QUOTE, self.CTX)

    def test_faithful_claim_passes(self):
        result = self._verify("Shrubs are the most important food of black muntjac.")
        self.assertEqual(result["status"], "SUPPORTED")
        self.assertTrue(result["is_confirmed_eligible"])

    def test_negated_claim_is_rejected(self):
        result = self._verify("Shrubs are NOT the most important food of black muntjac.")
        self.assertEqual(result["status"], "CONTRADICTORY")
        self.assertFalse(result["is_confirmed_eligible"])
        self.assertEqual(result["audit_verdict"], "REJECT_POLARITY_MISMATCH")

    def test_antonym_claim_is_rejected(self):
        result = self._verify("Shrubs are the least important food of black muntjac.")
        self.assertEqual(result["audit_verdict"], "REJECT_POLARITY_MISMATCH")

    def test_absence_claim_is_rejected(self):
        result = self._verify("Shrubs are rarely eaten by black muntjac.")
        self.assertEqual(result["audit_verdict"], "REJECT_POLARITY_MISMATCH")


class TestP0NumericGate(unittest.TestCase):
    """P0-2：数值门禁不得被伪造值直通。"""

    def _verdict(self, source, value):
        report = qa.audit_evidence(
            {"evidence_records": [{"verbatim_quote": source, "extracted_value": value}]}, source)
        entry = report["entries"][0]
        return (entry.get("value_alignment") or {}).get("verdict"), qa.gate_failed(report, strict=True)

    def test_thousands_truncation_is_blocked(self):
        verdict, failed = self._verdict(
            "The sample yielded 1,234,567 reads in total.", "1,234")
        self.assertTrue(failed, verdict)

    def test_correct_thousands_passes(self):
        verdict, failed = self._verdict(
            "The sample yielded 1,234,567 reads in total.", "1,234,567")
        self.assertFalse(failed, verdict)

    def test_european_thousands_pass(self):
        verdict, failed = self._verdict(
            "The sample yielded 1.234.567 reads in total.", "1234567")
        self.assertFalse(failed, verdict)

    def test_decimal_with_three_digits_is_not_thousands(self):
        """`0.005` 是小数，不得被当成千位读成 5。"""
        self.assertEqual([str(q["value"]) for q in qa.extract_quantities("0.005")], ["0.005"])

    def test_comparator_must_match(self):
        verdict, failed = self._verdict(
            "The effect was P < 0.05 in the tested group.", ">0.05")
        self.assertTrue(failed, verdict)
        verdict, failed = self._verdict(
            "The effect was P < 0.05 in the tested group.", "P < 0.05")
        self.assertFalse(failed, verdict)

    def test_uncertainty_marker_must_match(self):
        verdict, failed = self._verdict("The value was 0.3 in the sample.", "±0.3")
        self.assertTrue(failed, verdict)

    def test_full_width_value_is_normalized(self):
        verdict, failed = self._verdict(
            "本研究中含量为 ５５．４％ ，属于主要食物类别之一。", "５５．４％")
        self.assertFalse(failed, verdict)


class TestP0QuoteLengthCap(unittest.TestCase):
    """P0-3：整篇文档当引句 → 数值锚定恒真。"""

    def test_over_long_quote_is_blocked(self):
        doc = ("Title. Methods. " + "filler. " * 400 +
               "Table 1. Survival was 23.0 mg in the treated group.")
        report = qa.audit_evidence(
            {"evidence_records": [{"verbatim_quote": doc, "extracted_value": "23.0 mg"}]}, doc)
        entry = report["entries"][0]
        self.assertEqual((entry.get("value_alignment") or {}).get("verdict"), "QUOTE_TOO_LONG")
        self.assertTrue(qa.gate_failed(report, strict=True))
        self.assertEqual(report["summary"]["quote_too_long"], 1)

    def test_normal_quote_still_passes(self):
        quote = "Survival was 23.0 mg in the treated group."
        report = qa.audit_evidence(
            {"evidence_records": [{"verbatim_quote": quote, "extracted_value": "23.0 mg"}]}, quote)
        self.assertFalse(qa.gate_failed(report, strict=True))


class TestP0ConcurrentSnapshotWrites(unittest.TestCase):
    """P0-6：并发写快照不得损坏 session.json 或静默丢版本。"""

    def test_concurrent_writers_do_not_corrupt_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="sf-p0-conc-") as folder:
            store = SessionStore(folder)
            store.save_snapshot({"state": "INIT", "last_applied_event_id": None}, 0)
            script = textwrap.dedent('''
                import sys
                sys.path.insert(0, %r)
                from shared.execution import SessionStore
                st = SessionStore(%r)
                ok = 0
                for i in range(10):
                    for _ in range(5):
                        cur = st.load_snapshot()
                        cur["state"] = "W-%%s-%%d" %% (sys.argv[1], i)
                        try:
                            st.save_snapshot(cur, expected_revision=cur["revision"])
                            ok += 1
                            break
                        except Exception:
                            pass
                print(ok)
            ''') % (str(REPO_ROOT), folder)
            script_path = os.path.join(folder, "writer.py")
            with open(script_path, "w", encoding="utf-8") as fh:
                fh.write(script)
            procs = [subprocess.Popen([sys.executable, script_path, tag],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for tag in ("A", "B")]
            written = 0
            errors = ""
            for proc in procs:
                out, err = proc.communicate()
                written += int((out.strip() or "0").split()[-1])
                errors += err
            self.assertNotIn("JSONDecodeError", errors)
            self.assertNotIn("FileNotFoundError", errors)
            with open(os.path.join(folder, "session.json"), encoding="utf-8") as fh:
                data = json.load(fh)          # 必须仍是合法 JSON
            self.assertEqual(data["revision"], written + 1)
            self.assertFalse([f for f in os.listdir(folder) if f.endswith(".tmp")])
            self.assertFalse([f for f in os.listdir(folder) if f.endswith(".lock")])

    def test_corrupt_snapshot_raises_structured_error(self):
        with tempfile.TemporaryDirectory(prefix="sf-p0-corrupt-") as folder:
            store = SessionStore(folder)
            with open(store.session_path, "w", encoding="utf-8") as fh:
                fh.write('{"a": 1}\n{"b": 2}\n')
            with self.assertRaises(SnapshotCorrupt) as ctx:
                store.load_snapshot()
            self.assertEqual(ctx.exception.details.get("reason"), "SNAPSHOT_CORRUPT")


if __name__ == "__main__":
    unittest.main()

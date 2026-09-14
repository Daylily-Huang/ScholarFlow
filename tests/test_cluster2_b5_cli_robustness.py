# -*- coding: utf-8 -*-
"""集群第二轮 B5 批次回归测试：校验器与 CLI 健壮性族。

修复项（决议表 H-11/79/12/17-validate_session 侧/38/39/40）：
  - H-11 成熟度门禁缺口：maturity_history 段间连续、轮次绑定、时间戳单调不减；
    跳跃/倒填/游离轮次负例被拒（debate-verifier M4/M1a 实测夹具移植）。
  - H-79 rounds[].kind 枚举校验（枚举对齐 session schema 既有取值，schema 零改动）。
  - H-12 GP6 指纹重算依赖导入失败必须显式报告（FAILED_IMPORT 计入退出码），
    干净部署（`python -S`）下不再静默失效（debate-verifier V1 实测场景移植）。
  - H-17 JSON Schema 校验 FAIL → 退出码非零 + 结构化明细。
  - H-38 audit_claims 数值改为完整 token 匹配："45" 不再命中 "145"/"456"/"0.45"。
  - H-39 SKIPPED_UNPARSEABLE 计入退出码（rc≠0，或显式 --allow-skipped）。
  - H-40 源不可读（损坏 PDF/零页/无文本层）→ 结构化 SOURCE_UNREADABLE exit 2，
    零页 PDF 不得误判为"伪造/未命中"类失败（extraction-adversary EXT-B-03 场景移植）。
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  （仓库测试统一导入习惯：注入技能脚本路径）

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "skills" / "research-idea-debate" / "scripts" / "validate_session.py"
SPECIMEN = REPO_ROOT / "tests" / "fixtures" / "specimen_session_debate.json"
AUDIT_CLAIMS = REPO_ROOT / "skills" / "literature-evidence-extraction" / "scripts" / "audit_claims.py"

from audit_claims import audit_single_claim  # noqa: E402  (helpers 已注入脚本路径)

try:
    import pypdf  # noqa: F401
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


def _validator_env(clean_deployment=False):
    """干净部署模拟：去掉 PYTHONPATH 并用 -S 跳过 site-packages（editable 安装的
    .pth 会把仓库根塞回 sys.path，实测只有 -S 能复现干净部署——见 verifier V1）。"""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    if not clean_deployment:
        env["PYTHONPATH"] = str(REPO_ROOT)
    return env


def _run_validator(path, clean_deployment=False, extra_args=()):
    cmd = [sys.executable]
    if clean_deployment:
        cmd.append("-S")
    cmd.extend([str(VALIDATOR), str(path), "--json"])
    cmd.extend(extra_args)
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          env=_validator_env(clean_deployment), cwd=str(REPO_ROOT))
    return proc.returncode, proc.stdout, proc.stderr


def _run_audit(source_path, *extra_args):
    proc = subprocess.run([sys.executable, str(AUDIT_CLAIMS), "-i", str(source_path)]
                          + [str(a) for a in extra_args],
                          capture_output=True, text=True, cwd=str(REPO_ROOT))
    return proc.returncode, proc.stdout, proc.stderr


class ValidatorFixtureCase(unittest.TestCase):
    """公共夹具：移植 debate-verifier attack_2 的 base_session 形状。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cluster2-b5-"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def base_session(self, state="DISCUSSING"):
        return {
            "schema_version": "0.1", "session_id": "SESS-B5", "run_id": "RUN-B5",
            "mode": "explore", "state": state,
            "original_prompt": "我想研究道路密度对獾活动的影响",
            "current_question": "道路密度是否显著改变獾的夜间活动范围？",
            "execution": {"depth": "standard", "selection_status": "confirmed",
                          "budget": {"max_rounds": 8, "max_review_batches": 2,
                                     "max_subtasks_per_batch": 2, "max_active_seconds": 1800,
                                     "max_events": 400},
                          "usage": {"rounds_used": 1, "tokens_observed": None,
                                    "tokens_metering": "UNAVAILABLE"}},
            "rounds": [{"round": 1, "kind": "CONFIGURATION", "role": "moderator",
                        "question_type": "CONFIGURATION", "trigger": "P1",
                        "question": "继续讨论道路密度这个变量吗？",
                        "user_answer": "（模拟用户）继续", "intent": "推进", "signals": []}],
            "ideas": [{"idea_id": "IDEA-1", "maturation": "TESTABLE",
                       "maturity_history": [
                           {"from": "RAW", "to": "DEVELOPING", "round": 1,
                            "at": "2026-09-13T09:00:00Z"},
                           {"from": "DEVELOPING", "to": "TESTABLE", "round": 1,
                            "at": "2026-09-13T09:05:00Z"},
                       ],
                       "versions": [{"version": 1, "proposition": "道路密度升高会降低獾的夜间活动范围",
                                     "origin": "USER_INTUITION", "epistemic_status": "INTUITION",
                                     "disposition": "ACTIVE", "revision_reason": "初始版本"}],
                       "evidence_links": [], "decisions": []}],
            "gap_requests": [], "review_batches": [], "review_requests": [], "decisions": [],
        }

    def write_and_run(self, session, name="fixture.json", **run_kwargs):
        path = self.tmp / name
        path.write_text(json.dumps(session, ensure_ascii=False), encoding="utf-8")
        rc, out, err = _run_validator(path, **run_kwargs)
        data = json.loads(out) if out.strip() else {}
        return rc, data

    def rule_set(self, data):
        return sorted({v["rule"] for v in data.get("violations", [])})


class TestMaturityHistoryHardening(ValidatorFixtureCase):
    """H-11：段间连续 / 轮次绑定 / 时间戳单调，负例被拒并计入违规。"""

    def test_positive_control_bound_continuous_monotonic_passes(self):
        """合法历史（绑定真实轮次、段间连续、时间戳单调不减）必须零违规。"""
        rc, data = self.write_and_run(self.base_session())
        self.assertEqual(rc, 0, data.get("violations"))
        self.assertEqual(data["violations"], [])

    def test_segment_discontinuity_rejected(self):
        """M4 实测：每段各自合法但段间断开（from≠上一段 to）必须被拒。"""
        s = self.base_session()
        s["ideas"][0]["maturity_history"] = [
            {"from": "RAW", "to": "DEVELOPING", "round": 1},
            {"from": "RAW", "to": "DEVELOPING", "round": 1},
            {"from": "DEVELOPING", "to": "TESTABLE", "round": 1},
        ]
        rc, data = self.write_and_run(s)
        self.assertEqual(rc, 1)
        self.assertIn("ID-MAT", self.rule_set(data))
        messages = " ".join(v["message"] for v in data["violations"])
        self.assertIn("段间不连续", messages)

    def test_maturity_jump_still_rejected(self):
        """跳级 RAW→TESTABLE 依旧被拒（既有 ID-MAT 行为不回退）。"""
        s = self.base_session()
        s["ideas"][0]["maturity_history"] = [{"from": "RAW", "to": "TESTABLE", "round": 1}]
        rc, data = self.write_and_run(s)
        self.assertEqual(rc, 1)
        self.assertIn("ID-MAT", self.rule_set(data))

    def test_backdated_timestamp_rejected(self):
        """M4 实测：时间戳倒填（10:00→08:00→07:00）必须被拒。"""
        s = self.base_session()
        s["ideas"][0]["maturity_history"] = [
            {"from": "RAW", "to": "DEVELOPING", "round": 1, "at": "2026-09-13T10:00:00Z"},
            {"from": "DEVELOPING", "to": "TESTABLE", "round": 1, "at": "2026-09-13T08:00:00Z"},
        ]
        rc, data = self.write_and_run(s)
        self.assertEqual(rc, 1)
        messages = " ".join(v["message"] for v in data["violations"])
        self.assertIn("时间戳倒填", messages)

    def test_unparseable_timestamp_rejected(self):
        """时间戳存在但不可解析 → 失败关闭，不得当作可证明单调。"""
        s = self.base_session()
        s["ideas"][0]["maturity_history"][0]["at"] = "昨天上午"
        rc, data = self.write_and_run(s)
        self.assertEqual(rc, 1)
        messages = " ".join(v["message"] for v in data["violations"])
        self.assertIn("无法解析", messages)

    def test_partial_timestamp_rejected(self):
        """部分段带时间戳、部分缺失 → 无法证明单调，整条拒绝。"""
        s = self.base_session()
        del s["ideas"][0]["maturity_history"][1]["at"]
        rc, data = self.write_and_run(s)
        self.assertEqual(rc, 1)
        messages = " ".join(v["message"] for v in data["violations"])
        self.assertIn("缺少时间戳", messages)

    def test_floating_round_reference_rejected(self):
        """游离轮次：绑定 round=99（会话内无此轮）必须被拒。"""
        s = self.base_session()
        s["ideas"][0]["maturity_history"][1]["round"] = 99
        rc, data = self.write_and_run(s)
        self.assertEqual(rc, 1)
        messages = " ".join(v["message"] for v in data["violations"])
        self.assertIn("游离轮次", messages)

    def test_unbound_maturity_change_rejected(self):
        """未绑定轮次（round 缺失）的成熟度变更必须被拒——否则清空 round 即绕过门禁。"""
        s = self.base_session()
        for h in s["ideas"][0]["maturity_history"]:
            h.pop("round", None)
        rc, data = self.write_and_run(s)
        self.assertEqual(rc, 1)
        messages = " ".join(v["message"] for v in data["violations"])
        self.assertIn("未绑定轮次", messages)

    def test_verifier_m4_fixture_now_rejected(self):
        """移植 debate-verifier m4.json 原样夹具：修复前 0 违规，修复后必须 rc=1。"""
        src = (REPO_ROOT / "端到端真实跑" / "20260913-e2e-cluster2" / "01-debate"
               / "verifier" / "fixtures" / "sessions" / "m4.json")
        if not src.is_file():
            self.skipTest("verifier 夹具不存在")
        rc, out, _ = _run_validator(src)
        data = json.loads(out)
        self.assertEqual(rc, 1)
        self.assertIn("ID-MAT", self.rule_set(data))


class TestRoundKindEnum(ValidatorFixtureCase):
    """H-79：rounds[].kind 枚举校验（枚举清单对齐 session schema，schema 零改动）。"""

    def test_kind_outside_enum_rejected(self):
        s = self.base_session()
        s["rounds"][0]["kind"] = "MAGIC_ROUND"
        rc, data = self.write_and_run(s)
        self.assertEqual(rc, 1)
        self.assertIn("RD11", self.rule_set(data))

    def test_all_schema_kinds_accepted(self):
        """schema 枚举全集必须全部合法（逐个替换后仍零违规）。"""
        substantive = {"SUBSTANTIVE", "EXTERNAL_INPUT", "REVIEW_SUBMISSION"}
        for kind in ("SUBSTANTIVE", "EXTERNAL_INPUT", "CONFIGURATION",
                     "REVIEW_SUBMISSION", "CHECKPOINT"):
            s = self.base_session()
            s["rounds"][0]["kind"] = kind
            if kind in substantive:
                # RD6：实质轮必须绑定 idea_id——否则测的是 RD6 不是 kind 枚举。
                s["rounds"][0]["idea_id"] = "IDEA-1"
                s["rounds"][0]["target_version"] = 1
            rc, data = self.write_and_run(s, name="kind-%s.json" % kind)
            self.assertEqual(rc, 0, "kind=%s 被误拒：%s" % (kind, data.get("violations")))

    def test_legitimate_specimen_session_still_passes(self):
        """合法完整样本（含全部五种 kind）零违规——新增枚举不误伤既有夹具。"""
        if not SPECIMEN.is_file():
            self.skipTest("规格样本不存在")
        rc, out, _ = _run_validator(SPECIMEN)
        self.assertEqual(rc, 0, out)


class TestGP6ImportFailureReporting(ValidatorFixtureCase):
    """H-12：GP6 指纹重算依赖导入失败必须显式报告（FAILED_IMPORT 计入退出码）。"""

    def gap_session(self):
        s = self.base_session()
        s["gap_requests"] = [{
            "schema_version": "0.1", "gap_id": "GAP-B5", "idea_id": "IDEA-1",
            "idea_version": 1, "session_id": "SESS-B5", "gap_type": "SEARCH_GAP",
            "target_skill": "literature-discovery-acquisition",
            "question": "道路密度对獾夜间活动范围的影响有哪些研究？",
            "reason": "命题缺乏实证支撑", "decision_impact": "决定 P1 可信度",
            "blocking": "BLOCKING", "scope": {"topic": "道路密度 獾 夜间活动范围"},
            "approval": {"status": "CONFIRMED", "scope_fingerprint": "fp-0000000000000000",
                         "confirmed_event_id": "evt-b5", "approved_idea_version": 1},
            "execution_status": "WAITING_RESULT",
        }]
        return s

    def test_engine_available_flags_scope_mismatch(self):
        """引擎可用（PYTHONPATH 指向仓库根）时维持 GP6 指纹不符判定。"""
        rc, data = self.write_and_run(self.gap_session())
        self.assertEqual(rc, 1)
        self.assertEqual(data["gp6"]["status"], "OK")
        messages = " ".join(v["message"] for v in data["violations"])
        self.assertIn("范围已变更", messages)

    def test_clean_deployment_reports_failed_import_and_nonzero_exit(self):
        """V1 实测场景：干净部署（python -S）下 GP6 曾静默失效（exit=0）——
        修复后必须显式 FAILED_IMPORT、计入违规、退出码非零。"""
        rc, data = self.write_and_run(self.gap_session(), clean_deployment=True)
        self.assertEqual(rc, 1)
        self.assertEqual(data["gp6"]["status"], "FAILED_IMPORT")
        self.assertIn("shared", data["gp6"]["error"] or "")
        self.assertIn("GP6", self.rule_set(data))
        messages = " ".join(v["message"] for v in data["violations"])
        self.assertIn("FAILED_IMPORT", messages)

    def test_clean_deployment_without_gaps_still_passes(self):
        """无缺口会话在干净部署下不受牵连（GP6 状态 NOT_RUN，零违规 rc=0）。"""
        rc, data = self.write_and_run(self.base_session(), clean_deployment=True)
        self.assertEqual(rc, 0, data.get("violations"))
        self.assertEqual(data["gp6"]["status"], "NOT_RUN")


class TestSchemaFailExitCode(ValidatorFixtureCase):
    """H-17：schema 校验 FAIL → 退出码 1 + 结构化 FAIL 明细。"""

    def test_schema_fail_alone_drives_nonzero_exit(self):
        """移植 verifier v2 夹具：budget 附加未知键，结构检查全过但 schema FAIL。"""
        s = self.base_session()
        s["execution"]["budget"]["max_unlisted_thing"] = 3
        rc, data = self.write_and_run(s)
        self.assertEqual(data["json_schema"]["status"], "FAIL")
        self.assertEqual(rc, 1, "schema FAIL 必须计入退出码")
        self.assertEqual(data["violations"], [], "结构检查应全过——由 schema 单独驱动 rc")

    def test_schema_fail_details_are_structured(self):
        s = self.base_session()
        s["execution"]["budget"]["max_unlisted_thing"] = 3
        rc, data = self.write_and_run(s)
        errors = data["json_schema"]["errors"]
        self.assertTrue(errors, "FAIL 必须携带结构化明细")
        self.assertIn("message", errors[0])
        self.assertIn("path", errors[0])
        self.assertIn("budget", "/".join([errors[0]["path"]]) + " " + errors[0]["message"])

    def test_schema_pass_keeps_zero_exit(self):
        rc, data = self.write_and_run(self.base_session())
        self.assertEqual(data["json_schema"]["status"], "PASS")
        self.assertEqual(rc, 0)


class TestAuditClaimsFullTokenNumbers(unittest.TestCase):
    """H-38：数值命中必须是完整 token——"45" 不得命中 "145"/"456"/"0.45"/"45.2"/"1945"。"""

    def _doc(self, text):
        return [{"page": 1, "text": text}]

    def test_forged_45_not_located_in_embedded_digits(self):
        doc = self._doc("Site logistics: transect 145 and batch 456; ratio 0.45 "
                        "(median 45.2); field season 1945. No PCR volumes here.")
        res = audit_single_claim("PCR reaction volume was 45 uL in all reactions", doc)
        self.assertNotEqual(res["verdict"], "LOCATED_CO_OCCURRING",
                            "嵌入数字不得冒充完整 token 命中")
        self.assertEqual(res["verdict"], "NUMERICAL_MISMATCH")
        self.assertFalse(res["co_located"])

    def test_real_45_still_located(self):
        doc = self._doc("The PCR reaction volume was 45 uL in all reactions.")
        res = audit_single_claim("PCR reaction volume was 45 uL", doc)
        self.assertEqual(res["verdict"], "LOCATED_CO_OCCURRING")
        self.assertTrue(res["co_located"])

    def test_85_not_found_inside_1985(self):
        doc = self._doc("PCR was first described in 1985 and widely adopted.")
        res = audit_single_claim("PCR reaction volume was 85 uL", doc)
        self.assertEqual(res["verdict"], "NUMERICAL_MISMATCH")

    def test_20_not_found_inside_120(self):
        doc = self._doc("Total volume was 120 uL.")
        res = audit_single_claim("PCR volume was 20 uL", doc)
        self.assertEqual(res["verdict"], "NUMERICAL_MISMATCH")

    def test_window_boundary_partial_token_not_counted(self):
        """窗口边缘被截断的 token 不得冒充共现命中（数字锚定在整页文本上判定）。"""
        text = "x" * 240 + " 1450 uL of buffer was prepared " + "y" * 240
        doc = self._doc(text)
        res = audit_single_claim("Assay volume was 450 uL", doc)
        self.assertNotEqual(res["verdict"], "LOCATED_CO_OCCURRING")

    def test_two_page_colocation_semantics_unchanged(self):
        """既有正控不回退：同页关键词+数值共现 → LOCATED_CO_OCCURRING；异页 → NUMBER_DISLOCATED。"""
        pages = [{"page": 1, "text": "We deployed 24 camera traps in the reserve."},
                 {"page": 2, "text": "PCR amplification was conducted in a total volume of 20 uL with 35 cycles."}]
        res = audit_single_claim("PCR volume was 20 uL", pages)
        self.assertEqual(res["verdict"], "LOCATED_CO_OCCURRING")
        self.assertEqual(res["best_match_page"], 2)
        res2 = audit_single_claim("PCR reactions had 24 replicates", pages)
        self.assertEqual(res2["verdict"], "NUMBER_DISLOCATED")


class TestAuditClaimsSkippedExitCode(unittest.TestCase):
    """H-39：SKIPPED_UNPARSEABLE 计入退出码语义（rc≠0 或显式 --allow-skipped）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cluster2-b5-ac-"))
        self.source = self.tmp / "paper.txt"
        self.source.write_text("The PCR reaction volume was 20 uL in all reactions. "
                               "We deployed 24 camera traps.", encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _claims_file(self, payload, name="claims.json"):
        path = self.tmp / name
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_clean_claims_file_passes(self):
        rc, out, err = _run_audit(self.source, "-c", self._claims_file(
            [{"claim": "PCR volume was 20 uL"}]))
        self.assertEqual(rc, 0, err)
        self.assertNotIn("SKIPPED_UNPARSEABLE", out)

    def test_unparseable_items_fail_closed(self):
        """字段名漂移 / 非字符串 / 空声明 → 计数、留痕、rc=1，不得静默丢弃冒充全绿。"""
        rc, out, err = _run_audit(self.source, "-c", self._claims_file([
            {"claim": "PCR volume was 20 uL"},
            {"claim_id": "C2", "statement": "字段名漂移"},
            42,
            {"claim": ""},
        ]))
        self.assertEqual(rc, 1, err)
        self.assertIn("SKIPPED_UNPARSEABLE", out)
        self.assertIn("3 claim(s) were SKIPPED_UNPARSEABLE", err)
        self.assertIn("字段名漂移", out)  # 每次拒绝可读：原因写入报告

    def test_allow_skipped_makes_partial_audit_explicit(self):
        rc, out, err = _run_audit(self.source, "-c", self._claims_file([
            {"claim": "PCR volume was 20 uL"},
            {"claim_id": "C2", "statement": "字段名漂移"},
        ]), "--allow-skipped")
        self.assertEqual(rc, 0, err)
        self.assertIn("SKIPPED_UNPARSEABLE", out)

    def test_top_level_object_is_not_silently_ignored(self):
        rc, out, err = _run_audit(self.source, "-c", self._claims_file(
            {"claims": [{"claim": "x"}]}))
        self.assertEqual(rc, 1, "顶层非数组必须计为不可解析跳过项")

    def test_malformed_json_is_structured_hard_fail(self):
        rc, out, err = _run_audit(self.source, "-c", self._claims_file("{not json"))
        self.assertEqual(rc, 1)
        payload = json.loads(err.strip().splitlines()[-1])
        self.assertEqual(payload["error"], "CLAIMS_FILE_UNPARSEABLE")
        self.assertNotIn("Traceback", err)

    def test_missing_claims_file_is_structured(self):
        rc, out, err = _run_audit(self.source, "-c", self.tmp / "nope.json")
        self.assertEqual(rc, 1)
        self.assertIn("CLAIMS_FILE_NOT_FOUND", err)


class TestAuditClaimsSourceUnreadable(unittest.TestCase):
    """H-40：源不可读 → 结构化 SOURCE_UNREADABLE exit 2；零页 PDF 不得进入"伪造/未命中"判定。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cluster2-b5-pdf-"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pdf(self, name, writer):
        path = self.tmp / name
        with open(path, "wb") as fh:
            writer(fh)
        return path

    def _assert_structured_exit2(self, rc, err, code):
        self.assertEqual(rc, 2, err)
        payload = json.loads(err.strip().splitlines()[-1])
        self.assertEqual(payload["error"], code)
        self.assertIn("detail", payload)

    def test_zero_page_pdf_is_source_unreadable(self):
        """EXT-B-03 实测场景：零页 PDF 旧实现落入纯文本回退、二进制噪声被判 [HIGH] 质量、
        claim 得到"未命中"类结论——修复后必须 SOURCE_UNREADABLE rc=2。"""
        if not HAS_PYPDF:
            self.skipTest("环境无 pypdf")
        def build(fh):
            pypdf.PdfWriter().write(fh)
        rc, out, err = _run_audit(self._pdf("zero.pdf", build), "--claim", "PCR volume was 20 uL")
        self._assert_structured_exit2(rc, err, "SOURCE_UNREADABLE")
        self.assertIn("zero pages", err)
        self.assertNotIn("NO_SURFACE_MATCH", out or "")

    def test_no_text_layer_pdf_is_source_unreadable(self):
        """无文本层（扫描/纯图页）不得让 claim 落入"伪造/未命中"类结论。"""
        if not HAS_PYPDF:
            self.skipTest("环境无 pypdf")
        def build(fh):
            w = pypdf.PdfWriter()
            w.add_blank_page(width=612, height=792)
            w.write(fh)
        rc, out, err = _run_audit(self._pdf("blank.pdf", build), "--claim", "PCR volume was 20 uL")
        self._assert_structured_exit2(rc, err, "SOURCE_UNREADABLE")
        self.assertIn("no extractable text layer", err)

    def test_corrupted_pdf_is_source_unreadable(self):
        if not HAS_PYPDF:
            self.skipTest("环境无 pypdf")
        def build(fh):
            fh.write(b"%PDF-1.7 this is not really a pdf at all ...")
        rc, out, err = _run_audit(self._pdf("corrupt.pdf", build), "--claim", "PCR volume was 20 uL")
        self._assert_structured_exit2(rc, err, "SOURCE_UNREADABLE")

    def test_missing_input_is_structured_exit2(self):
        rc, out, err = _run_audit(self.tmp / "no-such-file.txt", "--claim", "x")
        self.assertEqual(rc, 2)
        payload = json.loads(err.strip().splitlines()[-1])
        self.assertEqual(payload["error"], "INPUT_NOT_FOUND")

    def test_plain_text_source_still_audits(self):
        """正控：普通文本源不受影响。"""
        src = self.tmp / "paper.txt"
        src.write_text("The PCR reaction volume was 20 uL in all reactions.", encoding="utf-8")
        rc, out, err = _run_audit(src, "--claim", "PCR volume was 20 uL")
        self.assertEqual(rc, 0, err)
        self.assertIn("LOCATED_CO_OCCURRING", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)

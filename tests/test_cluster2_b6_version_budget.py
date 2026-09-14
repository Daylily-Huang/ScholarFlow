# -*- coding: utf-8 -*-
"""Cluster-2 round-2, batch B6 regression tests (version visibility + budget construction).

Fixes under test (panel consensus CONSENSUS.md, 决议表 H-19 最小半边 + H-36 最小集):
- H-19  RunContext re-instantiation must never reset the budget: constructing
        over a run bundle that already carries a usage ledger force-replays it
        (usage counted in, ``run_resumed`` event persisted) and a terminated
        bundle (COMPLETED / EXHAUSTED / ABORTED receipt) refuses new usage
        write-backs with a structured error. Fresh empty directories keep the
        byte-identical previous behaviour; ``resume()`` semantics unchanged.
- H-36  Deployment-drift visibility: ``shared/build_stamp.py`` (embedded build
        provenance constants, honest ``+dev`` fallback), ``--version`` on all
        four skill CLIs (prints ``scholarflow <version> (build <hash> <ts>)``,
        exit 0), and ``verify_package_assets.py --install-dir`` md5 drift
        check that only warns (exit 0) per the panel decision.

Defect provenance: INT-R-02 / DIS-R-03 (quota reset) and EXT-R-13 (deployment
drift) in 端到端真实跑/20260913-e2e-cluster2/.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (sys.path bootstrap)

REPO_ROOT = Path(__file__).resolve().parents[1]

AGENT_SEARCH = REPO_ROOT / "skills" / "literature-discovery-acquisition" / "scripts" / "agent_search.py"
QUOTE_AUDIT = REPO_ROOT / "skills" / "literature-evidence-extraction" / "scripts" / "quote_audit.py"
CONTROVERSY = REPO_ROOT / "skills" / "literature-synthesis" / "scripts" / "controversy_analyzer.py"
SESSION_CLI = REPO_ROOT / "skills" / "research-idea-debate" / "scripts" / "session_store_cli.py"
VERIFY_ASSETS = REPO_ROOT / "scripts" / "verify_package_assets.py"

STAMP_LINE_RE = re.compile(
    r"^scholarflow (?P<version>\d+\.\d+\.\d+) \(build (?P<commit>[0-9a-f]{12}) "
    r"(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\)$"
)


def _read_ledger(run_dir) -> list:
    path = Path(run_dir) / "usage_ledger.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# H-19: RunContext forced ledger replay on construction
# ---------------------------------------------------------------------------
class TestH19ForcedReplayOnConstruction(unittest.TestCase):
    def _make_run_dir(self, td, consumed=15):
        from shared.execution import RunContext, StageKind

        ctx = RunContext.create("quick", run_dir=td, stages=["discovery"])
        ctx.config.save(td)
        ctx.begin_stage(StageKind.DISCOVERY)
        ctx.consume_candidates(consumed)
        # Deliberately NOT finalized: the bundle has a live (non-terminal) ledger.
        return ctx

    def test_construction_over_existing_ledger_force_replays(self):
        """INT-R-02: a bare (non-resume) construction must not start from zero."""
        from shared.execution import RunContext, RunExecutionConfig

        with tempfile.TemporaryDirectory() as td:
            self._make_run_dir(td, consumed=15)
            ctx = RunContext(RunExecutionConfig.load(td), run_dir=td)

            self.assertTrue(ctx.resumed, "construction over a ledger must be marked resumed")
            self.assertIsNone(ctx.terminal_reason)
            self.assertEqual(ctx.candidates_processed, 15, "usage must be replayed, not reset")
            self.assertEqual(ctx.remaining_candidates, 5)

    def test_forced_replay_persists_a_resumed_event(self):
        from shared.execution import RunContext, RunExecutionConfig

        with tempfile.TemporaryDirectory() as td:
            self._make_run_dir(td, consumed=15)
            before = _read_ledger(td)
            self.assertFalse(any(e.get("event") == "run_resumed" for e in before))

            RunContext(RunExecutionConfig.load(td), run_dir=td)
            after = _read_ledger(td)
            resumed_events = [e for e in after if e.get("event") == "run_resumed"]
            self.assertEqual(
                len(resumed_events), 1, "exactly one run_resumed event must be persisted"
            )
            self.assertEqual(after[-1]["event"], "run_resumed")

    def test_replayed_budget_still_enforces_the_run_level_ceiling(self):
        """DIS-R-03: candidate ceiling 137>100 must stay impossible."""
        from shared.execution import RunContext, RunExecutionConfig

        with tempfile.TemporaryDirectory() as td:
            self._make_run_dir(td, consumed=15)
            ctx = RunContext(RunExecutionConfig.load(td), run_dir=td)
            granted = ctx.consume_candidates(30)
            self.assertEqual(granted, 5, "replayed consumption must keep bounding new grants")
            self.assertEqual(ctx.candidates_processed, 20)
            replayed = RunContext(RunExecutionConfig.load(td), run_dir=td)
            self.assertEqual(replayed.candidates_processed, 20)


# ---------------------------------------------------------------------------
# H-19: resume semantics unchanged (one run_resumed, correct replay)
# ---------------------------------------------------------------------------
class TestH19ResumeSemanticsConsistent(unittest.TestCase):
    def test_resume_replays_and_records_exactly_one_resumed_event(self):
        from shared.execution import RunContext

        with tempfile.TemporaryDirectory() as td:
            ctx = RunContext.create("quick", run_dir=td, stages=["discovery"])
            ctx.consume_candidates(15)
            ctx.finalize()
            resumed = RunContext.resume(td)
            self.assertTrue(resumed.resumed)
            self.assertEqual(resumed.candidates_processed, 15)
            self.assertEqual(resumed.remaining_candidates, 5)
            resumed_events = [
                e for e in _read_ledger(td) if e.get("event") == "run_resumed"
            ]
            self.assertEqual(len(resumed_events), 1, "resume must not duplicate run_resumed")

    def test_resume_of_a_bundle_without_ledger_still_records_the_event(self):
        from shared.execution import RunContext, RunExecutionConfig

        with tempfile.TemporaryDirectory() as td:
            RunExecutionConfig.confirmed("quick", run_id="run-leadless").save(td)
            resumed = RunContext.resume(td)
            self.assertTrue(resumed.resumed)
            events = _read_ledger(td)
            self.assertEqual([e["event"] for e in events], ["run_resumed"])


# ---------------------------------------------------------------------------
# H-19: terminated run bundles refuse new usage write-backs
# ---------------------------------------------------------------------------
class TestH19TerminatedRunRefusesWrites(unittest.TestCase):
    def _finalize_completed(self, td):
        from shared.execution import RunContext

        ctx = RunContext.create("quick", run_dir=td, stages=["discovery"])
        ctx.consume_candidates(15)
        ctx.finalize()  # no pending work -> status "completed"
        return ctx

    def test_completed_run_refuses_model_requests(self):
        from shared.execution import RunContext, RunExecutionConfig
        from shared.execution.context import RunTerminatedError

        with tempfile.TemporaryDirectory() as td:
            self._finalize_completed(td)
            ctx = RunContext(RunExecutionConfig.load(td), run_dir=td)
            self.assertEqual(ctx.terminal_reason, "COMPLETED")
            with self.assertRaises(RunTerminatedError) as caught:
                ctx.begin_model_request()
            payload = caught.exception.to_dict()
            self.assertEqual(payload["error_code"], "RUN_TERMINATED")
            self.assertEqual(payload["terminal_status"], "COMPLETED")
            self.assertEqual(payload["run_id"], ctx.config.run_id)

    def test_completed_run_refuses_database_and_candidate_writes(self):
        from shared.execution import RunContext, RunExecutionConfig
        from shared.execution.context import RunTerminatedError

        with tempfile.TemporaryDirectory() as td:
            self._finalize_completed(td)
            ctx = RunContext(RunExecutionConfig.load(td), run_dir=td)
            with self.assertRaises(RunTerminatedError):
                ctx.count_database_request(2)
            with self.assertRaises(RunTerminatedError):
                ctx.consume_candidates(1)
            self.assertEqual(ctx.database_requests, 0)
            self.assertEqual(ctx.candidates_processed, 15, "refused writes must not mutate usage")

    def test_exhausted_partial_receipt_is_terminal(self):
        """INT-R-02 T3c/T4: exhausted+finalized bundles must not accept usage."""
        from shared.execution import BudgetLimitError, RunContext
        from shared.execution.context import RunTerminatedError

        with tempfile.TemporaryDirectory() as td:
            ctx = RunContext.create("quick", run_dir=td)
            ctx.budget.requests_bucket.limit = 2
            ctx.budget.requests_bucket.closing_reserve = 1
            first = ctx.begin_model_request()
            ctx.end_model_request(first, actual_tokens=10)
            with self.assertRaises(BudgetLimitError):
                ctx.begin_model_request()
            receipt = ctx.finalize()
            self.assertEqual(receipt.status, "partial")
            self.assertEqual(receipt.stop_reason, "request_limit")

            resumed = RunContext.resume(td)
            self.assertEqual(resumed.terminal_reason, "EXHAUSTED")
            with self.assertRaises(RunTerminatedError) as caught:
                resumed.begin_model_request()
            self.assertEqual(caught.exception.terminal_status, "EXHAUSTED")

    def test_failed_receipt_is_aborted_and_terminal(self):
        from shared.execution import RunContext
        from shared.execution.context import RunTerminatedError, terminal_reason_from_receipt

        self.assertEqual(terminal_reason_from_receipt({"status": "failed"}), "ABORTED")
        with tempfile.TemporaryDirectory() as td:
            ctx = RunContext.create("quick", run_dir=td, stages=["discovery"])
            ctx.finalize(status="failed", error="boom")
            ctx2 = RunContext.create("quick", run_id=ctx.config.run_id, run_dir=td)
            self.assertEqual(ctx2.terminal_reason, "ABORTED")
            with self.assertRaises(RunTerminatedError):
                ctx2.consume_candidates(1)

    def test_partial_run_with_pending_work_stays_writable(self):
        """The resumable state (partial, no exhaustion) must keep accepting usage."""
        from shared.execution import RunContext, RunExecutionConfig

        with tempfile.TemporaryDirectory() as td:
            ctx = RunContext.create("quick", run_dir=td, stages=["discovery"])
            ctx.defer_stage_work("discovery", ["paper-7"])
            ctx.finalize(stop_reason="host_tool_unavailable")
            resumed = RunContext.resume(td)
            self.assertIsNone(resumed.terminal_reason, "pending-work runs stay resumable")
            granted = resumed.consume_candidates(5)
            self.assertEqual(granted, 5)
            self.assertEqual(resumed.database_requests, 0)
            resumed.count_database_request(3)
            self.assertEqual(resumed.database_requests, 3)

    def test_finalize_marks_the_same_instance_terminal(self):
        from shared.execution import RunContext
        from shared.execution.context import RunTerminatedError

        with tempfile.TemporaryDirectory() as td:
            ctx = RunContext.create("quick", run_dir=td, stages=["discovery"])
            ctx.consume_candidates(5)
            ctx.finalize()  # completed
            with self.assertRaises(RunTerminatedError):
                ctx.consume_candidates(1)


# ---------------------------------------------------------------------------
# H-19: unreadable / foreign ledgers fail explicitly (no silent fresh budget)
# ---------------------------------------------------------------------------
class TestH19LedgerReplayFailureIsExplicit(unittest.TestCase):
    def _config(self, run_id="run-A"):
        from shared.execution import RunExecutionConfig

        return RunExecutionConfig.confirmed("quick", run_id=run_id)

    def test_malformed_ledger_line_raises_structured_error(self):
        from shared.execution import RunContext
        from shared.execution.context import LedgerReplayError

        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "usage_ledger.jsonl"
            ledger.write_text(
                json.dumps({"run_id": "run-A", "event": "model_request", "count": 1}) + "\n"
                + "not-json-at-all\n",
                encoding="utf-8",
            )
            with self.assertRaises(LedgerReplayError) as caught:
                RunContext(self._config(), run_dir=td)
            payload = caught.exception.to_dict()
            self.assertEqual(payload["error_code"], "LEDGER_REPLAY_FAILED")
            self.assertEqual(payload["line_no"], 2)
            self.assertTrue(payload["ledger_path"].endswith("usage_ledger.jsonl"))

    def test_non_integer_usage_value_raises_structured_error(self):
        from shared.execution import RunContext
        from shared.execution.context import LedgerReplayError

        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "usage_ledger.jsonl"
            ledger.write_text(
                json.dumps({"run_id": "run-A", "event": "candidates_consumed",
                            "granted": "fifteen"}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(LedgerReplayError):
                RunContext(self._config(), run_dir=td)

    def test_foreign_run_ledger_is_refused(self):
        from shared.execution import RunContext
        from shared.execution.context import LedgerReplayError

        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "usage_ledger.jsonl"
            ledger.write_text(
                json.dumps({"run_id": "run-X", "event": "model_request", "count": 1}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(LedgerReplayError) as caught:
                RunContext(self._config(run_id="run-B"), run_dir=td)
            self.assertEqual(caught.exception.error_code, "LEDGER_RUN_ID_MISMATCH")

    def test_foreign_lifecycle_events_are_tolerated_but_not_applied(self):
        """Shared-dir timelines of other runs must not fail nor pollute quotas."""
        from shared.execution import RunContext

        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "usage_ledger.jsonl"
            ledger.write_text(
                json.dumps({"run_id": "run-X", "event": "stage_plan",
                            "stage": "discovery", "settings": {}}) + "\n"
                + json.dumps({"run_id": "run-X", "event": "pending_work",
                              "item": "discovery:paper-9"}) + "\n",
                encoding="utf-8",
            )
            ctx = RunContext(self._config(run_id="run-B"), run_dir=td)
            self.assertEqual(ctx.candidates_processed, 0, "foreign usage must not be imported")
            self.assertEqual(ctx.budget.pending_scope, [], "foreign work must not be applied")
            # The context stays fully usable for its own run.
            self.assertEqual(ctx.consume_candidates(5), 5)


# ---------------------------------------------------------------------------
# H-19 hard gate: fresh empty directories behave byte-identically
# ---------------------------------------------------------------------------
class TestH19FreshDirectoryBehaviourUnchanged(unittest.TestCase):
    def test_fresh_construction_creates_no_files_and_no_resumed_event(self):
        from shared.execution import RunContext

        with tempfile.TemporaryDirectory() as td:
            ctx = RunContext.create("quick", run_dir=td, stages=["discovery"])
            self.assertEqual(os.listdir(td), [], "fresh construction must not touch the directory")
            self.assertFalse(ctx.resumed)
            self.assertIsNone(ctx.terminal_reason)
            self.assertFalse(any(e.get("event") == "run_resumed" for e in ctx.events))

    def test_fresh_run_ledger_sequence_is_unchanged(self):
        from shared.execution import RunContext, StageKind

        with tempfile.TemporaryDirectory() as td:
            ctx = RunContext.create("quick", run_dir=td, stages=["discovery"])
            ctx.begin_stage(StageKind.DISCOVERY)
            ctx.consume_candidates(12)
            ctx.complete_stage(StageKind.DISCOVERY, ["quick-batch"])
            receipt = ctx.finalize()
            self.assertEqual(receipt.status, "completed")
            kinds = [e["event"] for e in _read_ledger(td)]
            self.assertEqual(
                kinds,
                ["stage_plan", "stage_started", "candidates_consumed", "stage_completed",
                 "run_finalized"],
            )
            self.assertEqual(receipt.usage["model_requests"], 0)

    def test_fresh_context_without_run_dir_is_unaffected(self):
        from shared.execution import RunContext

        ctx = RunContext.create("standard")
        ctx.count_database_request(4)
        self.assertEqual(ctx.database_requests, 4)
        self.assertEqual(ctx.budget.requests_bucket.used, 0)
        self.assertFalse(ctx.resumed)


# ---------------------------------------------------------------------------
# H-36: build stamp module
# ---------------------------------------------------------------------------
class TestH36BuildStamp(unittest.TestCase):
    def test_module_is_importable_and_stamp_is_embedded(self):
        import shared.build_stamp as bs
        import shared.version

        self.assertTrue(bs.is_stamp_available(), "the shipped module must carry a real stamp")
        self.assertEqual(bs.STAMP_VERSION, shared.version.PROJECT_VERSION)
        self.assertRegex(bs.BUILD_COMMIT, r"^[0-9a-f]{40}$")
        self.assertRegex(bs.BUILD_TIMESTAMP, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_format_matches_the_cli_contract(self):
        import shared.build_stamp as bs

        line = bs.format_version_line()
        match = STAMP_LINE_RE.match(line)
        self.assertIsNotNone(line, msg=line)
        self.assertIsNotNone(match, "format must be 'scholarflow <version> (build <hash> <ts>)'")
        self.assertEqual(match.group("version"), bs.STAMP_VERSION)
        self.assertEqual(match.group("commit"), bs.BUILD_COMMIT[:12])

    def test_get_build_stamp_shape(self):
        import shared.build_stamp as bs

        stamp = bs.get_build_stamp()
        self.assertEqual(
            sorted(stamp.keys()), ["commit", "commit_short", "source", "timestamp", "version"]
        )
        self.assertEqual(stamp["source"], "embedded")
        self.assertEqual(stamp["commit_short"], stamp["commit"][:12])

    def test_dev_fallback_when_unstamped(self):
        import shared.build_stamp as bs

        original = bs.BUILD_COMMIT
        try:
            bs.BUILD_COMMIT = "dev"
            self.assertFalse(bs.is_stamp_available())
            self.assertEqual(bs.format_version_line(), "scholarflow %s+dev" % bs.STAMP_VERSION)
            self.assertEqual(bs.get_build_stamp()["source"], "dev")
            bs.BUILD_COMMIT = ""
            self.assertEqual(bs.format_version_line(), "scholarflow %s+dev" % bs.STAMP_VERSION)
        finally:
            bs.BUILD_COMMIT = original


# ---------------------------------------------------------------------------
# H-36: --version on the four skill CLIs (subprocess probes, no PYTHONPATH help)
# ---------------------------------------------------------------------------
class TestH36CliVersionFlags(unittest.TestCase):
    def _run_version(self, script: Path):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)  # exercise the CLI's own engine bootstrap
        return subprocess.run(
            [sys.executable, str(script), "--version"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), env=env,
        )

    def _assert_stamp(self, proc):
        self.assertEqual(proc.returncode, 0, proc.stderr)
        line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        match = STAMP_LINE_RE.match(line)
        self.assertIsNotNone(match, "unexpected --version output: %r" % proc.stdout)
        self.assertEqual(match.group("ts"), _stamp_timestamp())

    def test_agent_search_version(self):
        self._assert_stamp(self._run_version(AGENT_SEARCH))

    def test_quote_audit_version(self):
        self._assert_stamp(self._run_version(QUOTE_AUDIT))

    def test_controversy_analyzer_version(self):
        self._assert_stamp(self._run_version(CONTROVERSY))

    def test_session_store_cli_version(self):
        self._assert_stamp(self._run_version(SESSION_CLI))

    def test_version_flag_beats_required_arguments(self):
        """--version must answer even though the CLIs have required arguments."""
        proc = self._run_version(QUOTE_AUDIT)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("(build ", proc.stdout)


def _stamp_timestamp():
    import shared.build_stamp as bs

    return bs.BUILD_TIMESTAMP


# ---------------------------------------------------------------------------
# H-36: verify_package_assets --install-dir (warn-only drift check)
# ---------------------------------------------------------------------------
class TestH36VerifyPackageAssetsInstallDir(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(VERIFY_ASSETS), *args],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )

    def test_normal_path_still_passes(self):
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("[PASS] All engine assets and skill manifests verified successfully!", proc.stdout)
        self.assertIn("Build stamp (H-36): scholarflow ", proc.stdout)

    def test_install_dir_drift_warns_but_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            install = Path(td) / "skills"
            install.mkdir()
            skill = REPO_ROOT / "skills" / "literature-synthesis"
            target = install / "literature-synthesis"
            target.mkdir()
            for item in skill.rglob("*"):
                if item.is_file() and "__pycache__" not in item.parts:
                    rel = item.relative_to(skill)
                    dest = target / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(item.read_bytes())
            # Drift one file beyond repair.
            drifted = target / "scripts" / "controversy_analyzer.py"
            drifted.write_text(drifted.read_text(encoding="utf-8") + "\n# drifted\n", encoding="utf-8")

            proc = self._run("--install-dir", td)  # parent layout: <dest>/skills
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("[SAME] literature-synthesis/SKILL.md", proc.stdout)
            self.assertIn("DIFFER literature-synthesis/scripts/controversy_analyzer.py", proc.stdout)
            self.assertIn("[WARNING]", proc.stdout)
            self.assertIn("reinstall skills/", proc.stdout)
            self.assertNotIn("[FAIL]", proc.stdout)

    def test_install_dir_missing_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "does-not-exist"
            proc = self._run("--install-dir", str(missing))
            self.assertEqual(proc.returncode, 2)
            self.assertIn("does not exist", proc.stdout)


if __name__ == "__main__":
    unittest.main()

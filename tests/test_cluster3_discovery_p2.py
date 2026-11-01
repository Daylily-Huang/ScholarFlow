# -*- coding: utf-8 -*-
"""discovery 技能 P2 回归（2026-09-15/16 集群审查）。

覆盖四条：未初筛记录不得进入 Stage 8（P2-11）、canonical `record_id` 身份口径
（P2-12/15）、κ 的同源检测与最小样本量（P2-10）、PRISMA-S 审计清单对齐（P2-14）。
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401

REPO_ROOT = helpers.REPO_ROOT
SCRIPTS = REPO_ROOT / "skills" / "literature-discovery-acquisition" / "scripts"
DOWNLOAD = SCRIPTS / "download_oa_papers.py"
KAPPA = SCRIPTS / "calculate_screening_agreement.py"
AGENT_SEARCH = SCRIPTS / "agent_search.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestScreeningStatusMustBeDeclared(unittest.TestCase):
    """P2-11：缺失 `screening_status` 不得默认成 "Include"。

    原实现 `rec.get("screening_status", "Include")` 会把**从未初筛**的记录带进
    Stage 8 下载与《全文获取台账》——"没筛过"与"筛成纳入"是两件事。
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load(DOWNLOAD, "dl_oa_p2")

    def test_declared_unscreened_is_none(self):
        self.assertIsNone(self.mod.screening_status_of({"title": "x"}))
        self.assertIsNone(self.mod.screening_status_of({"screening_status": "  "}))
        self.assertEqual(self.mod.screening_status_of({"screening_status": "Include"}), "Include")

    def test_unscreened_record_is_not_downloaded(self):
        with tempfile.TemporaryDirectory() as td:
            ip = Path(td) / "in.json"
            ip.write_text(json.dumps([{"record_id": "R1", "title": "T",
                                       "doi": "10.1/x"}], ensure_ascii=False),
                          encoding="utf-8")
            out = Path(td) / "out"
            proc = subprocess.run([sys.executable, str(DOWNLOAD), "-i", str(ip), "-o", str(out)],
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", cwd=str(REPO_ROOT))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("未声明初筛裁决", proc.stdout,
                          "未初筛记录必须被显式披露，而不是静默当成 Include")
            ledger = (out / "download_ledger.md")
            self.assertTrue(ledger.is_file())
            self.assertNotIn("R1", ledger.read_text(encoding="utf-8"),
                             "未初筛记录不得进入全文获取台账")


class TestCanonicalRecordIdentity(unittest.TestCase):
    """P2-12/15：身份键必须认 canonical `record_id`。

    本模块原先只认 `id`，而 `ingest_external_records.py` 只产出 `record_id`——
    ingest→下载这条正常链路上覆盖率门禁**恒报失败 rc=2**，且台账丢失与候选底册的
    身份关联。
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load(DOWNLOAD, "dl_oa_p2b")

    def test_record_key_prefers_canonical(self):
        self.assertEqual(self.mod.record_key({"record_id": "R1"}), "R1")
        self.assertEqual(self.mod.record_key({"id": "R2"}), "R2")
        self.assertIsNone(self.mod.record_key({"title": "only title"}))

    def test_ingest_shaped_input_passes_the_coverage_gate(self):
        with tempfile.TemporaryDirectory() as td:
            ip = Path(td) / "in.json"
            ip.write_text(json.dumps(
                [{"record_id": "R1", "title": "T", "doi": "10.1/x",
                  "screening_status": "Include"}], ensure_ascii=False), encoding="utf-8")
            out = Path(td) / "out"
            proc = subprocess.run([sys.executable, str(DOWNLOAD), "-i", str(ip), "-o", str(out)],
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", cwd=str(REPO_ROOT))
            self.assertEqual(proc.returncode, 0,
                             "canonical record_id 输入不得被判覆盖率失败：%s" % proc.stdout)
            self.assertIn("coverage check PASSED", proc.stdout)


class TestKappaSourceIndependenceAndSampleSize(unittest.TestCase):
    """P2-10：同源检测不得只看字节；κ 不得在小样本上被当成顶级一致性证据。"""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load(KAPPA, "csa_p2")

    def _run(self, a_records, b_records):
        with tempfile.TemporaryDirectory() as td:
            pa, pb = Path(td) / "a.json", Path(td) / "b.json"
            pa.write_text(json.dumps(a_records, ensure_ascii=False), encoding="utf-8")
            pb.write_text(json.dumps(b_records, ensure_ascii=False), encoding="utf-8")
            return subprocess.run([sys.executable, str(KAPPA), "-a", str(pa), "-b", str(pb)],
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", cwd=str(REPO_ROOT))

    def test_reformatted_same_source_is_still_rejected(self):
        """同源洗白只需改一个空格即可绕过字节指纹——内容级指纹必须照拦。"""
        recs = [{"record_id": "R%d" % i, "title": "T%d" % i,
                 "screening_status": "Include"} for i in range(6)]
        reformatted = [dict(reversed(list(r.items()))) for r in recs]
        proc = self._run(recs, reformatted)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("IDENTICAL_SOURCES", proc.stderr)

    def test_small_sample_is_flagged_underpowered(self):
        """3 条共同记录时 κ 方差极大，"自选子集"极易刷出 1.000。"""
        a = [{"record_id": "R0", "screening_status": "Include"},
             {"record_id": "R1", "screening_status": "Exclude"},
             {"record_id": "R2", "screening_status": "Include"}]
        b = [{"record_id": "R0", "screening_status": "Include"},
             {"record_id": "R1", "screening_status": "Exclude"},
             {"record_id": "R2", "screening_status": "Uncertain"}]
        proc = self._run(a, b)
        self.assertIn("sample too small", proc.stderr)
        self.assertEqual(self.mod.MIN_COMMON_RECORDS, 5)

    def test_adequate_sample_is_not_flagged(self):
        a = [{"record_id": "R%d" % i,
              "screening_status": ("Include" if i % 2 else "Exclude")} for i in range(6)]
        b = [{"record_id": "R%d" % i,
              "screening_status": ("Exclude" if i % 3 else "Include")} for i in range(6)]
        proc = self._run(a, b)
        self.assertNotIn("sample too small", proc.stderr)


class TestPrismaSAuditMatchesTheChecklist(unittest.TestCase):
    """P2-14：headless 产物的 16 项必须是 PRISMA-S，而不是 PRISMA 2020 主清单条目。

    原清单有 10 项与技能自带的 `references/prisma_s_checklist.md` 对不上，其中 4 项
    （全文筛选标准 / 研究选择流程 / 数据收集流程 / 偏倚风险评估）属 PRISMA 2020
    主清单，不属 PRISMA-S 的检索报告范围；第 9/10 项还被对调。
    """

    #: 与 `references/prisma_s_checklist.md` Item 1–16 逐一对应的关键词
    CHECKLIST_KEYWORDS = (
        "数据库名称", "多数据库", "注册库", "网络与搜索引擎", "引文双向追踪", "限定条件",
        "检索过滤式", "前人检索", "全量检索式", "同行评议", "命中数", "去重",
        "更新频次", "执行日期", "纳入排除", "流转账本",
    )

    #: 属于 PRISMA 2020 主清单、不得出现在 PRISMA-S 审计里的条目
    PRISMA_2020_ONLY = ("risk of bias", "Data collection", "Study selection",
                        "Full-text screening")

    @classmethod
    def setUpClass(cls):
        cls.audit = _load(AGENT_SEARCH, "as_p2").build_prisma_s_audit("standard")

    def test_has_sixteen_items(self):
        self.assertEqual(len(self.audit["items"]), 16)
        self.assertEqual(self.audit["framework"], "PRISMA-S-2021")

    def test_items_align_with_the_shipped_checklist(self):
        for item, keyword in zip(self.audit["items"], self.CHECKLIST_KEYWORDS):
            with self.subTest(item=item["item"]):
                self.assertIn(keyword, item["name"],
                              "Item %d 与 prisma_s_checklist.md 不对应" % item["item"])

    def test_no_prisma_2020_main_list_items(self):
        for bad in self.PRISMA_2020_ONLY:
            self.assertNotIn(bad, json.dumps(self.audit, ensure_ascii=False),
                             "PRISMA 2020 主清单条目混入 PRISMA-S 审计：%s" % bad)


if __name__ == "__main__":
    unittest.main()

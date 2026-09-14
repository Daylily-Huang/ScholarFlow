# -*- coding: utf-8 -*-
"""部署层运行时完整性回归测试（2026-09-15）。

背景：`scripts/install.sh` 报 `[SUCCESS]`，但装出去的树里三个脚本
（`claim_alignment.py` / `extraction_pipeline.py` / `context_expansion.py`）
解析不到引擎——它们硬编码 `parents[3]`，只在仓库布局成立。后果是极性门禁
静默降级（实测 `REVERSAL_MARKERS` 31→0、`NEGATION_MARKERS` 56→27，
`_HAS_SHARED_POLARITY` True→False），而安装器**只验收 `agent_search.py`**
（唯一带双布局定位器的脚本），因此验收恒 PASS。

本测试不依赖 bash，Windows 与 Linux 都能跑（既有的
`TestR06InstalledRuntime` 在 Windows 上整类跳过，所以这条缺陷从未被机械拦截）。

机械门禁要点：断言在**无 site-packages**（`-I -S`）下装出去的树解析到
**它自己那份**引擎，且极性门禁与仓库布局逐值一致。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from . import helpers
except ImportError:  # pragma: no cover - direct execution
    import helpers  # type: ignore

REPO_ROOT = helpers.REPO_ROOT
SKILLS = ("literature-discovery-acquisition", "literature-evidence-extraction",
          "literature-synthesis", "research-idea-debate")

#: 真正驱动门禁的入口：导入 `shared` 或同技能兄弟模块。
#: 与 `scripts/install.sh` 的 VERIFY_ENTRIES / `scripts/install.ps1` 的
#: $verifyEntries 保持一致。
GATE_ENTRIES = (
    "literature-discovery-acquisition/scripts/agent_search.py",
    "literature-evidence-extraction/scripts/extraction_pipeline.py",
    "literature-evidence-extraction/scripts/claim_alignment.py",
    "literature-evidence-extraction/scripts/quote_audit.py",
    "literature-synthesis/scripts/controversy_analyzer.py",
    "literature-synthesis/scripts/evidence_to_claim.py",
    "research-idea-debate/scripts/session_store_cli.py",
)

#: 在两种布局下都必须解析到引擎的脚本（本缺陷的受害面）。
ENGINE_DEPENDENT = (
    "literature-evidence-extraction/scripts/claim_alignment.py",
    "literature-evidence-extraction/scripts/extraction_pipeline.py",
    "literature-evidence-extraction/scripts/context_expansion.py",
)

_ENGINE_PROBE = r"""
import json, os, runpy, sys
target, expected, modname = sys.argv[1], os.path.realpath(sys.argv[2]), sys.argv[3]
# 以模块名（而非 __main__）执行：只跑模块级引导与导入，不触发 argparse 退出，
# 并且 run_path 会把结果 globals 直接返回（__main__ 在返回后会被还原，取不到）。
namespace, run_error = {}, None
try:
    namespace = runpy.run_path(target, run_name=modname)
except SystemExit:
    pass
except Exception as exc:
    run_error = "%s: %s" % (type(exc).__name__, exc)
engine = sys.modules.get("shared")
result = {
    "engine": None if engine is None else os.path.realpath(os.path.dirname(engine.__file__)),
    "expected": expected,
    "run_error": run_error,
}
if not namespace:
    namespace = getattr(sys.modules.get(modname), "__dict__", {})
result["has_shared_polarity"] = namespace.get("_HAS_SHARED_POLARITY")
result["reversal_markers"] = len(namespace.get("REVERSAL_MARKERS") or [])
result["negation_markers"] = len(namespace.get("NEGATION_MARKERS") or [])
print(json.dumps(result))
"""


def _build_installed_tree(dest: Path) -> None:
    """复刻安装器的落盘布局：`<dest>/<skill>/` + `<dest>/shared` + `<dest>/schemas`。"""
    for skill in SKILLS:
        shutil.copytree(REPO_ROOT / "skills" / skill, dest / skill,
                        ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO_ROOT / "shared", dest / "shared",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO_ROOT / "schemas", dest / "schemas",
                    ignore=shutil.ignore_patterns("__pycache__"))


def _probe(entry: Path, dest: Path, modname: str):
    """在隔离解释器里跑入口脚本，回读引擎解析结果与门禁标志。"""
    proc = subprocess.run(
        [sys.executable, "-I", "-S", "-c", _ENGINE_PROBE,
         str(entry), str(dest / "shared"), modname],
        cwd=str(entry.parent), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )
    payload = None
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except ValueError:
                continue
    return proc, payload


class TestInstalledRuntimeIntegrity(unittest.TestCase):
    """装出去的树必须自带可用引擎——不依赖 site-packages，也不回落到仓库。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="sf_install_integrity_")
        cls.dest = Path(cls._tmp.name) / "dest"
        cls.dest.mkdir(parents=True)
        _build_installed_tree(cls.dest)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_gate_entry_points_run_without_site_packages(self):
        """每个门禁入口在 `-I -S` 下都必须能起来（缺引擎或兄弟模块即失败）。"""
        failures = []
        for rel in GATE_ENTRIES:
            entry = self.dest / rel
            self.assertTrue(entry.is_file(), "安装树缺少入口：%s" % rel)
            proc = subprocess.run(
                [sys.executable, "-I", "-S", entry.name, "--help"],
                cwd=str(entry.parent), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=180,
            )
            if proc.returncode != 0:
                tail = [l for l in (proc.stderr or "").strip().splitlines() if l.strip()]
                failures.append("%s rc=%d %s" % (rel, proc.returncode,
                                                 tail[-1][:120] if tail else ""))
        self.assertEqual(failures, [], "装出去的入口无法运行：\n" + "\n".join(failures))

    def test_installed_tree_resolves_its_own_engine(self):
        """引擎必须来自安装树本身——不得回落到仓库副本或 site-packages。"""
        for rel in ENGINE_DEPENDENT:
            entry = self.dest / rel
            module = Path(rel).stem
            with self.subTest(entry=rel):
                proc, payload = _probe(entry, self.dest, module)
                self.assertIsNotNone(payload, "探针无输出：%s / %s"
                                     % (proc.stdout, proc.stderr))
                self.assertIsNone(payload.get("run_error"), payload)
                self.assertIsNotNone(
                    payload["engine"],
                    "装出去的 %s 没有解析到引擎（门禁将静默降级）" % rel)
                self.assertEqual(
                    os.path.normcase(payload["engine"]),
                    os.path.normcase(payload["expected"]),
                    "引擎解析到了安装树之外：%s" % payload["engine"])

    def test_polarity_gate_is_not_degraded_in_the_installed_layout(self):
        """安装布局下的极性门禁必须与仓库布局逐值一致。

        这是本缺陷的核心断言：旧引导块下 `_HAS_SHARED_POLARITY` 为 False、
        词表长度退化为 0/27，而脚本仍然 `rc=0`——只测退出码抓不到。
        """
        sys.path.insert(0, str(REPO_ROOT / "skills" / "literature-evidence-extraction" / "scripts"))
        try:
            import claim_alignment as repo_claim_alignment  # noqa: WPS433
        finally:
            sys.path.pop(0)

        expected = {
            "has_shared_polarity": getattr(repo_claim_alignment, "_HAS_SHARED_POLARITY", None),
            "reversal_markers": len(getattr(repo_claim_alignment, "REVERSAL_MARKERS", []) or []),
            "negation_markers": len(getattr(repo_claim_alignment, "NEGATION_MARKERS", []) or []),
        }
        self.assertTrue(expected["has_shared_polarity"],
                        "仓库布局下共享极性模块就未生效，测试前提不成立")

        entry = self.dest / "literature-evidence-extraction" / "scripts" / "claim_alignment.py"
        _proc, payload = _probe(entry, self.dest, "claim_alignment")
        self.assertIsNotNone(payload)
        for key, want in expected.items():
            self.assertEqual(
                payload.get(key), want,
                "安装布局下极性门禁降级：%s 期望 %r，实得 %r" % (key, want, payload.get(key)))


class TestInstallerScriptsStayHonest(unittest.TestCase):
    """安装器自身不得回退成「只验收一个入口」或「漏装 schemas」。"""

    def _read(self, rel):
        return (REPO_ROOT / rel).read_text(encoding="utf-8")

    def test_posix_installer_copies_schemas(self):
        body = self._read("scripts/install.sh")
        self.assertIn("schemas", body)
        self.assertRegex(body, r'cp -r "\$SCHEMAS_SRC"')

    def test_windows_installer_copies_schemas(self):
        """H-36 回归：POSIX 安装器复制 schemas，Windows 安装器曾经整段缺失。"""
        body = self._read("scripts/install.ps1")
        self.assertIn("schemas", body.lower(),
                      "install.ps1 未复制 schemas/，Windows 侧 schema gate 不可达")
        self.assertRegex(body, r'Join-Path \$RepoRoot "schemas"')

    def test_installers_verify_more_than_the_single_self_locating_entry(self):
        """验收面必须覆盖门禁入口，而不是只有自带定位器的 agent_search.py。

        旧版 `install.sh` 只探测 `agent_search.py`——那个脚本有自己的双布局
        定位器，所以验收**结构上不可能失败**。此测试锁住覆盖面。
        """
        for rel, token in (("scripts/install.sh", "VERIFY_ENTRIES"),
                           ("scripts/install.ps1", "$verifyEntries")):
            with self.subTest(installer=rel):
                body = self._read(rel)
                self.assertIn(token, body, "%s 缺少验收入口清单" % rel)
                for entry in GATE_ENTRIES:
                    name = entry.split("/")[-1]
                    self.assertIn(name, body,
                                  "%s 的验收清单漏了门禁入口 %s" % (rel, name))


if __name__ == "__main__":
    unittest.main()

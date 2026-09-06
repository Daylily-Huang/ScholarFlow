# -*- coding: utf-8 -*-
"""Doc-consistency guards: turn three rectification-manual acceptance criteria
into permanent CI assertions (v0.6 manual P0-04 / P0-05 / P1-18)."""
import glob
import os
import unittest
from pathlib import Path

import helpers  # noqa: F401

REPO_ROOT = helpers.REPO_ROOT


class TestLensEnumeration(unittest.TestCase):
    """P0-04: README 的 lens 名称清单必须与 shared/domain_lenses/*.md 一致。"""

    def test_every_lens_file_is_mentioned_in_readme(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        lens_dir = REPO_ROOT / "shared" / "domain_lenses"
        lens_names = sorted(p.stem for p in lens_dir.glob("*.md"))
        self.assertGreaterEqual(len(lens_names), 9, "expected at least 9 domain lenses")
        for name in lens_names:
            self.assertIn(f"`{name}`", readme,
                          f"lens '{name}' exists as a file but is missing from README")

    def test_no_phantom_lens_paths_in_readme(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        lens_dir = REPO_ROOT / "shared" / "domain_lenses"
        lens_names = {p.stem for p in lens_dir.glob("*.md")}
        for m in __import__("re").finditer(r"domain_lenses/([a-z_]+)\.md", readme):
            self.assertIn(m.group(1), lens_names,
                          f"README references non-existent lens file '{m.group(1)}.md'")


class TestNoDanglingSchemaRefs(unittest.TestCase):
    """P0-05: skills 与 schemas 内禁止引用不存在的 schema 路径（如 schemas/v1.0/）。"""

    def test_no_v1_point_zero_refs(self):
        offenders = []
        for base in ["skills", "schemas", "shared"]:
            for fp in Path(REPO_ROOT, base).rglob("*.md"):
                text = fp.read_text(encoding="utf-8", errors="replace")
                if "schemas/v1.0/" in text:
                    offenders.append(str(fp.relative_to(REPO_ROOT)))
        self.assertEqual(offenders, [], "dangling schemas/v1.0/ references in: %s" % offenders)

    def test_referenced_schema_files_exist(self):
        for fp in Path(REPO_ROOT, "skills").rglob("*.md"):
            text = fp.read_text(encoding="utf-8", errors="replace")
            for m in __import__("re").finditer(r"`?(schemas/[A-Za-z0-9_.]+\.json)`?", text):
                target = REPO_ROOT / m.group(1)
                self.assertTrue(target.exists(),
                                "%s references missing schema %s" % (fp.relative_to(REPO_ROOT), m.group(1)))


class TestRootDirectoryHygiene(unittest.TestCase):
    """P1-18: 内部整改手册/方案不得留在仓库根目录（归档于 docs/rfcs/archive/）。"""

    def test_no_internal_manuals_in_root(self):
        root = Path(REPO_ROOT)
        offenders = [p.name for p in root.glob("*.md")
                     if any(k in p.name for k in ("方案", "手册", "审查", "整改"))]
        self.assertEqual(offenders, [],
                         "internal manuals must live in docs/rfcs/archive/, found in root: %s" % offenders)

    def test_archive_copies_are_single_source(self):
        archive = REPO_ROOT / "docs" / "rfcs" / "archive"
        names = [p.name for p in archive.glob("*.md")]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()

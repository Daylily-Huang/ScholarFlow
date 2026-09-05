# -*- coding: utf-8 -*-
"""Bootstrap sys.path so test modules can import skill scripts directly."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

for _p in [
    REPO_ROOT / "skills" / "literature-discovery-acquisition" / "scripts",
    REPO_ROOT / "skills" / "literature-evidence-extraction" / "scripts",
    REPO_ROOT / "skills" / "literature-synthesis" / "scripts",
]:
    sys.path.insert(0, str(_p))

FIXTURES = REPO_ROOT / "tests" / "fixtures"

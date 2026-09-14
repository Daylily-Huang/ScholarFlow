#!/usr/bin/env python3
"""ScholarFlow Package Assets & Distribution Verifier (P2-01).

Verifies that essential engine packages, domain lenses, canonical schemas,
and skill manifests are present and intact across development and installed environments.

H-36 (panel decision B6): ``--install-dir <dir>`` md5-compares the installed
skill copies against the repo originals. Drift is reported as WARNING lines
and the run still exits 0 -- the verifier informs, it does not gate. A missing
``--install-dir`` path is a usage error (exit 2), because then no comparison
happened at all and a clean exit would misreport "checked, all fine".
"""

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

REQUIRED_LENSES = [
    "biomedical.md",
    "chemistry_materials.md",
    "computer_science.md",
    "ecology_environment.md",
    "engineering.md",
    "generic.md",
    "life_sciences.md",
    "physical_sciences.md",
    "social_sciences.md",
]

REQUIRED_SCHEMAS = [
    "discovery_result.schema.json",
    "retrieval_coverage_ledger.schema.json",
    "literature_record.schema.json",
    "extraction_result.schema.json",
    "evidence_record.schema.json",
    "candidate_context_record.schema.json",
    "claim_record.schema.json",
    "comparison_record.schema.json",
    "claim_evidence_matrix.schema.json",
    "synthesis_record.schema.json",
    "execution_profile.schema.json",
    "research_debate_session.schema.json",
    "research_debate_event.schema.json",
    "research_debate_gap.schema.json",
]

REQUIRED_SKILLS = [
    "literature-discovery-acquisition/SKILL.md",
    "literature-evidence-extraction/SKILL.md",
    "literature-synthesis/SKILL.md",
    "research-idea-debate/SKILL.md",
]


def verify_installed_wheel() -> bool:
    """Verifies that in an installed environment (outside repo), engine modules and resources load."""
    try:
        import shared
        import shared.version
        import shared.build_stamp  # H-36: the build stamp ships inside shared*
        import shared.grill_me
        import shared.context_resolution
        import shared.execution
        from importlib.resources import files

        lens = files("shared").joinpath("domain_lenses/generic.md")
        if not lens.is_file():
            print("[FAIL] generic.md not accessible via importlib.resources")
            return False
        print(f"[PASS] Installed wheel engine verified (version: {shared.version.__version__})")
        return True
    except Exception as e:
        print(f"[FAIL] Installed wheel verification failed: {e}")
        return False


def verify_repo_assets(repo_root: Path) -> bool:
    print("==================================================")
    print("  ScholarFlow Package Assets Verification (v0.6.6)")
    print("==================================================")

    
    missing = []
    
    # Ensure repo_root is in sys.path for importing shared package
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # 1. Check Python package importability
    try:
        import shared
        import shared.version
        import shared.build_stamp  # H-36: the build stamp ships inside shared*
        import shared.context_resolution
        import shared.grill_me
        import shared.execution
        print(f"[PASS] Python engine packages importable (version: {shared.version.__version__})")
        print(f"[PASS] Build stamp (H-36): {shared.build_stamp.format_version_line()}")
    except Exception as e:
        print(f"[FAIL] Engine import failed: {e}")
        missing.append(f"Engine import error: {e}")

    # 2. Check canonical domain lenses
    lens_dir = repo_root / "shared" / "domain_lenses"
    for lens in REQUIRED_LENSES:
        lp = lens_dir / lens
        if not lp.exists():
            missing.append(f"Missing domain lens: {lens}")
        else:
            print(f"[PASS] Domain lens: {lens}")

    # 3. Check canonical schemas
    schema_dir = repo_root / "schemas"
    for schema in REQUIRED_SCHEMAS:
        sp = schema_dir / schema
        if not sp.exists():
            missing.append(f"Missing schema: {schema}")
        else:
            print(f"[PASS] Canonical schema: {schema}")

    # 4. Check skill manifests
    skill_dir = repo_root / "skills"
    for skill_rel in REQUIRED_SKILLS:
        skp = skill_dir / skill_rel
        if not skp.exists():
            missing.append(f"Missing skill manifest: {skill_rel}")
        else:
            print(f"[PASS] Skill manifest: {skill_rel}")

    if missing:
        print(f"\n[FAIL] Asset verification failed with {len(missing)} missing items:")
        for m in missing:
            print(f"  - {m}")
        return False

    print("\n[PASS] All engine assets and skill manifests verified successfully!")
    return True


def _md5_of(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_installed_skills_root(install_dir: Path) -> Path:
    """Locate the skills root inside an installed tree (H-36).

    Accepts either the skills root itself (``<dest>/skills``-style layouts such
    as ``.agents\\skills``) or a parent that contains a ``skills/`` directory.
    """
    for candidate in (install_dir, install_dir / "skills"):
        if candidate.is_dir() and any(
            (candidate / rel.split("/")[0]).exists() for rel in REQUIRED_SKILLS
        ):
            return candidate
    return install_dir


def compare_install_dir(repo_root: Path, install_dir: Path) -> bool:
    """H-36: md5-compare installed skill copies against the repo originals.

    Drift (DIFFER / MISSING) is printed as a WARNING list and the run stays
    green (exit 0) -- panel decision: only warn, never fail. ``True`` is
    returned only for a real comparison run; ``False`` signals the usage error
    (install dir absent), which the caller maps to exit 2.
    """
    repo_skills = repo_root / "skills"
    print("\n--------------------------------------------------")
    print("  Installed-copy drift check (H-36): %s" % install_dir)
    print("--------------------------------------------------")
    if not install_dir.is_dir():
        print("[ERROR] --install-dir does not exist or is not a directory: %s" % install_dir)
        return False
    skills_root = _resolve_installed_skills_root(install_dir)
    warnings = []
    checked = 0
    for path in sorted(repo_skills.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rel = path.relative_to(repo_skills)
        checked += 1
        counterpart = skills_root / rel
        if not counterpart.exists():
            warnings.append("MISSING in install dir: %s" % rel.as_posix())
            continue
        repo_md5 = _md5_of(path)
        inst_md5 = _md5_of(counterpart)
        if repo_md5 == inst_md5:
            print("[SAME] %s" % rel.as_posix())
        else:
            warnings.append(
                "DIFFER %s (repo md5=%s, install md5=%s)" % (rel.as_posix(), repo_md5, inst_md5)
            )
    for item in warnings:
        print("[WARNING] %s" % item)
    if warnings:
        print(
            "\n[WARNING] Installed copy drifted from the repo in %d of %d files; "
            "reinstall skills/ (and shared/) before trusting local gates (H-36 / EXT-R-13)."
            % (len(warnings), checked)
        )
    else:
        print("\n[PASS] Installed copy matches the repo (%d files compared)." % checked)
    return True


def verify_build_stamp_reachability(repo_root: Path) -> bool:
    """Check the embedded BUILD_COMMIT still names a commit git can read.

    H-36 embedded the build stamp so ``--version`` makes deployment drift
    visible. A rebase or squash silently breaks that: the stamp keeps printing
    a hash that no longer resolves (measured 2026-09-15 -- ``cb343aa...`` was
    readable by neither ``git cat-file`` nor ``git merge-base``), so the
    provenance claim quietly becomes false. Warn rather than fail, matching the
    existing install-drift convention: provenance rot is not a runtime fault,
    but it must not be silent. Fix with ``python scripts/stamp_build.py``.
    """
    try:
        import shared.build_stamp as stamp
    except Exception as exc:  # pragma: no cover - import guarded by caller
        print("[WARNING] build stamp unavailable: %s" % exc)
        return True
    commit = (getattr(stamp, "BUILD_COMMIT", "") or "").strip()
    if not commit:
        print("[WARNING] build stamp carries no commit (source checkout, not a stamped build)")
        return True
    try:
        proc = subprocess.run(
            ["git", "cat-file", "-e", commit + "^{commit}"],
            cwd=str(repo_root), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except OSError as exc:
        print("[WARNING] cannot reach git to check the build stamp: %s" % exc)
        return True
    if proc.returncode != 0:
        print("[WARNING] BUILD_COMMIT %s is not reachable from this repository; "
              "`--version` on the four skill CLIs now prints a hash that proves nothing. "
              "Fix: python scripts/stamp_build.py" % commit[:12])
    else:
        print("[PASS] Build stamp commit is reachable (%s)" % commit[:12])
    return True


def main():
    parser = argparse.ArgumentParser(
        description="ScholarFlow package assets & distribution verifier "
                    "(add --install-dir to md5-compare an installed skill copy)"
    )
    parser.add_argument(
        "--install-dir",
        metavar="DIR",
        default=None,
        help="Installed tree to md5-compare against the repo skill files "
             "(e.g. C:\\Users\\<user>\\.agents\\skills). Drift only warns; exit stays 0.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from shared.build_stamp import format_version_line
        print("ScholarFlow build stamp (H-36): %s" % format_version_line())
    except Exception as exc:  # version visibility must never break verification
        print("ScholarFlow build stamp (H-36): unavailable (%s)" % exc)

    success = verify_repo_assets(repo_root)
    verify_build_stamp_reachability(repo_root)
    if args.install_dir and not compare_install_dir(repo_root, Path(args.install_dir)):
        sys.exit(2)  # usage error: nothing was compared (H-36 contract)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()



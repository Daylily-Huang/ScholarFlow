#!/usr/bin/env python3
"""ScholarFlow Package Assets & Distribution Verifier (P2-01).

Verifies that essential engine packages, domain lenses, canonical schemas,
and skill manifests are present and intact across development and installed environments.
"""

import os
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
    "literature_record.schema.json",
    "extraction_result.schema.json",
    "evidence_record.schema.json",
    "claim_record.schema.json",
    "synthesis_record.schema.json",
]

REQUIRED_SKILLS = [
    "literature-discovery-acquisition/SKILL.md",
    "literature-evidence-extraction/SKILL.md",
    "literature-synthesis/SKILL.md",
]


def verify_installed_wheel() -> bool:
    """Verifies that in an installed environment (outside repo), engine modules and resources load."""
    try:
        import shared
        import shared.version
        import shared.grill_me
        import shared.context_resolution
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
    print("  ScholarFlow Package Assets Verification (v0.6.3)")
    print("==================================================")
    
    missing = []
    
    # Ensure repo_root is in sys.path for importing shared package
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # 1. Check Python package importability
    try:
        import shared
        import shared.version
        import shared.context_resolution
        import shared.grill_me
        print(f"[PASS] Python engine packages importable (version: {shared.version.__version__})")
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


def main():
    repo_root = Path(__file__).resolve().parent.parent
    success = verify_repo_assets(repo_root)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()



#!/usr/bin/env python3
"""ScholarFlow Domain Neutrality Linter.

Audits core protocol and contract files to prevent domain anchoring bias.
Ensures that domain-specific terms (e.g. PCR, microsatellite, cohort, patient)
only appear inside explicitly marked example blocks or domain lenses,
and never as universal hard execution rules in core framework files.

Pure Python standard library (zero external dependencies).
"""

import argparse
import os
import re
import sys
from typing import Dict, List, Tuple

# Domain-specific terms that must not define core universal execution logic
DOMAIN_TERMS = [
    r"\bPCR\b",
    r"\bmicrosatellite\b",
    r"\bSTR\b",
    r"\bCytb\b",
    r"\bPID-sibs\b",
    r"\bpatient\b",
    r"\bradiologist\b",
    r"\bmammography\b",
    r"\bcalcination\b",
    r"\bperovskite\b",
]

# Core files that must remain strictly domain-neutral
CORE_PATHS = [
    "shared/core/evidence_principles.md",
    "shared/core/uncertainty_model.md",
    "shared/core/cross_skill_contract.md",
    "shared/grill_me/core_protocol.md",
    "shared/grill_me/state_model.md",
    "shared/grill_me/decision_priority.md",
    "skills/literature-evidence-extraction/references/assay_context_isolation.md",
    "skills/literature-synthesis/references/consensus_levels_and_boundaries.md",
    "skills/literature-synthesis/references/school_and_paradigm_mapping.md",
    "skills/literature-discovery-acquisition/SKILL.md",
    "skills/literature-evidence-extraction/SKILL.md",
    "skills/literature-synthesis/SKILL.md",
    "README.md",
]


def check_file_domain_neutrality(filepath: str) -> List[Tuple[int, str, str]]:
    """Scan a file for unhedged domain-specific terms outside example blocks.

    Returns:
        List of (line_num, term, line_content) violations.
    """
    if not os.path.exists(filepath):
        return []

    violations = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    in_example_context = False
    in_code_block = False

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        # Track example or illustrative headers
        if re.search(r"(示例|示范|example|跨学科|跨领域|mapping|对照|映射|为例|举例)", stripped, re.IGNORECASE):
            in_example_context = True

        # End of example block when returning to high-level numbered section
        if re.match(r"^#{1,3}\s+[一二三四五六七八九十0-9]+[、\.]", stripped):
            if not re.search(r"(示例|示范|example|映射|为例)", stripped, re.IGNORECASE):
                in_example_context = False

        # Table rows, list bullets, or blockquote prompts demonstrating cross-disciplinary mapping are allowed
        is_mapping_line = bool(
            in_code_block
            or stripped.startswith(">")
            or re.search(r"(生命科学|生物医药|计算机|材料|化学|社会科学|典型混淆|跨学科|为例|lens)", stripped, re.IGNORECASE)
            or stripped.startswith("|")
            or re.match(r"^-\s+\*(生命科学|生物医药|计算机|材料|社会科学|医学)\*", stripped)
        )

        for term_pat in DOMAIN_TERMS:
            m = re.search(term_pat, line, re.IGNORECASE)
            if m:
                matched_term = m.group(0)
                # If it's not inside an explicit example section or mapping table
                if not in_example_context and not is_mapping_line:
                    # Check if line explicitly flags itself as an example
                    if not re.search(r"(如|例|例如|e\.g\.|example|示)", line, re.IGNORECASE):
                        violations.append((idx, matched_term, stripped))

    return violations


DEFAULT_DOMAIN_PATTERNS = [
    r"golden\s+profile",
    r"黄金\s*profile",
    r"默认生态",
    r"默认临床",
    r"默认材料",
    r"默认医学",
    r"default\s+biomedical",
    r"default\s+ecology",
    r"default\s+clinical",
]


def check_skill_frontmatter_for_default_domain(filepath: str) -> List[Tuple[int, str, str]]:
    """Ensure SKILL.md frontmatter/description does not hardcode a single domain as default."""
    if not os.path.exists(filepath):
        return []

    violations = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    in_frontmatter = False
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if idx == 1 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter and stripped == "---":
            in_frontmatter = False
            break
        if in_frontmatter:
            for pat in DEFAULT_DOMAIN_PATTERNS:
                m = re.search(pat, line, re.IGNORECASE)
                if m:
                    violations.append((idx, m.group(0), stripped))
    return violations


def audit_repository(repo_root: str) -> Dict[str, List[Tuple[int, str, str]]]:
    results = {}
    for rel_path in CORE_PATHS:
        full_path = os.path.join(repo_root, rel_path.replace("/", os.sep))
        v = check_file_domain_neutrality(full_path)
        if rel_path.endswith("SKILL.md"):
            v.extend(check_skill_frontmatter_for_default_domain(full_path))
        if v:
            results[rel_path] = v
    return results


def main():
    parser = argparse.ArgumentParser(description="ScholarFlow Domain Neutrality Linter")
    parser.add_argument("--repo-root", default=".", help="Root directory of ScholarFlow repository")
    args = parser.parse_args()

    results = audit_repository(args.repo_root)

    print("==================================================")
    print("  ScholarFlow Domain Neutrality Linter (v0.5)")
    print("==================================================")

    if not results:
        print("[PASS] All core protocol and contract files are strictly domain-neutral!")
        sys.exit(0)
    else:
        print("[FAIL] Domain anchoring leakage detected in core execution files:")
        for file_path, viols in results.items():
            print(f"\n[FILE] {file_path}")
            for line_no, term, content in viols:
                print(f"  Line {line_no}: Found '{term}' -> '{content[:70]}'")
        sys.exit(1)


if __name__ == "__main__":
    main()

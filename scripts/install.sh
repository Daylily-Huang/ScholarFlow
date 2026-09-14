#!/usr/bin/env bash
# ScholarFlow One-Click Skill Installer for Linux / macOS
#
# Installs the three skills *and* the shared Python engine that the skill
# scripts import. The engine is copied exactly once per destination root
# (as `<dest>/shared`, beside the skill directories), so an installed skill
# tree can run outside the repository without accumulating drifting duplicate
# copies (R06).
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SKILLS_SRC="$REPO_ROOT/skills"
SHARED_SRC="$REPO_ROOT/shared"
SCHEMAS_SRC="$REPO_ROOT/schemas"

if [ ! -d "$SKILLS_SRC" ]; then
    echo "[-] skills directory not found: $SKILLS_SRC"
    exit 1
fi

if [ ! -f "$SHARED_SRC/__init__.py" ]; then
    echo "[-] shared engine package not found: $SHARED_SRC"
    echo "    The skill scripts import 'shared.*'; install from a full checkout."
    exit 1
fi

if [ -n "$SCHOLARFLOW_SKILLS_DEST" ]; then
    DESTINATIONS=("$SCHOLARFLOW_SKILLS_DEST")
else
    DESTINATIONS=("$HOME/.agents/skills" "$HOME/.claude/skills")
fi

echo "=========================================="
echo "  ScholarFlow Skills Installer"
echo "=========================================="

for dest in "${DESTINATIONS[@]}"; do
    echo "[*] Target directory: $dest"
    mkdir -p "$dest"
    for skill_dir in "$SKILLS_SRC"/*/; do
        skill_name="$(basename "$skill_dir")"
        echo "  -> Installing $skill_name..."
        rm -rf "$dest/$skill_name"
        cp -r "$skill_dir" "$dest/$skill_name"
        find "$dest/$skill_name" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
    done

    # A single vendored engine copy per destination root: <dest>/shared
    echo "  -> Installing shared Python engine (single copy)..."
    rm -rf "$dest/shared"
    cp -r "$SHARED_SRC" "$dest/shared"
    find "$dest/shared" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

    # Canonical schemas live at the repository root; skill scripts resolve them
    # relative to the installed tree, so they must ship alongside `shared`.
    if [ -d "$SCHEMAS_SRC" ]; then
        echo "  -> Installing canonical schemas (single copy)..."
        rm -rf "$dest/schemas"
        cp -r "$SCHEMAS_SRC" "$dest/schemas"
        find "$dest/schemas" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
    else
        echo "  [!] schemas directory not found: $SCHEMAS_SRC"
    fi
done

# Post-install verification: every entry point that drives a gate must resolve
# its runtime from an isolated interpreter with no site-packages, otherwise the
# install must not be reported as a complete success.
#
# Scope (2026-09-15 部署层修复): this loop used to probe agent_search.py only.
# That script carries its own layout-tolerant locator, so the check could not
# fail even when every other script had silently lost the engine -- the
# acceptance gate was structurally unfalsifiable. The list below covers the
# entries that import `shared` or a sibling module; the engine-identity probe
# additionally rejects a `shared` that resolves OUTSIDE the install root (e.g.
# a stale `pip install -e .` pointing at a repository checkout).
echo ""
echo "[*] Verifying installed runtime (isolated interpreter, no site-packages)..."
VERIFY_FAILED=0
VERIFY_ENTRIES=(
    "literature-discovery-acquisition/scripts/agent_search.py"
    "literature-evidence-extraction/scripts/extraction_pipeline.py"
    "literature-evidence-extraction/scripts/claim_alignment.py"
    "literature-evidence-extraction/scripts/quote_audit.py"
    "literature-synthesis/scripts/controversy_analyzer.py"
    "literature-synthesis/scripts/evidence_to_claim.py"
    "research-idea-debate/scripts/session_store_cli.py"
)
# Runs the target the way a host agent would, then asserts the engine it
# actually imported lives under the expected install root.
ENGINE_PROBE='
import runpy, sys, os
target, expected = sys.argv[1], os.path.realpath(sys.argv[2])
sys.argv = [target, "--help"]
try:
    runpy.run_path(target, run_name="__main__")
except SystemExit:
    pass
except Exception as exc:
    sys.stderr.write("running %s raised %s: %s\n" % (target, type(exc).__name__, exc))
module = sys.modules.get("shared")
if module is None:
    sys.stderr.write("the engine was never imported\n")
    raise SystemExit(3)
found = os.path.realpath(os.path.dirname(module.__file__))
if found != expected:
    sys.stderr.write("engine resolved to %s, expected %s\n" % (found, expected))
    raise SystemExit(4)
'
for dest in "${DESTINATIONS[@]}"; do
    for rel in "${VERIFY_ENTRIES[@]}"; do
        ENTRY="$dest/$rel"
        if [ ! -f "$ENTRY" ]; then
            echo "  [FAIL] $rel is missing from $dest"
            VERIFY_FAILED=1
            continue
        fi
        if ! (cd "$(dirname "$ENTRY")" && python3 -I -S "$(basename "$ENTRY")" --help >/dev/null 2>&1); then
            echo "  [FAIL] $rel cannot resolve its runtime"
            VERIFY_FAILED=1
            continue
        fi
        echo "  [PASS] $rel"
    done
    if ! python3 -I -S -c "$ENGINE_PROBE" \
            "$dest/literature-evidence-extraction/scripts/claim_alignment.py" \
            "$dest/shared" >/dev/null 2>&1; then
        echo "  [FAIL] the installed tree does not resolve $dest/shared"
        VERIFY_FAILED=1
    fi
done

if [ "$VERIFY_FAILED" -ne 0 ]; then
    echo ""
    echo "[-] Installation copied files but the runtime could not be verified."
    echo "    Re-run from a full checkout, or install the engine with: pip install scholarflow"
    exit 2
fi

echo ""
echo "[SUCCESS] ScholarFlow skills installed successfully!"
echo "Engine and schema location(s):"
for dest in "${DESTINATIONS[@]}"; do
    echo "  - $dest/shared"
    echo "  - $dest/schemas"
done
echo "Available skills:"
for skill_dir in "$SKILLS_SRC"/*/; do
    echo "  - $(basename "$skill_dir")"
done

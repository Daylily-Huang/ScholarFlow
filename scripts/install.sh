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
done

# Post-install verification: the engine must resolve from an isolated
# interpreter with no site-packages, otherwise the install must not be
# reported as a complete success.
echo ""
echo "[*] Verifying installed runtime (isolated interpreter, no site-packages)..."
VERIFY_FAILED=0
for dest in "${DESTINATIONS[@]}"; do
    ENTRY="$dest/literature-discovery-acquisition/scripts/agent_search.py"
    if [ ! -f "$ENTRY" ]; then
        continue
    fi
    if (cd "$(dirname "$ENTRY")" && python3 -I -S "$(basename "$ENTRY")" --help >/dev/null 2>&1); then
        echo "  [PASS] $ENTRY resolves the shared engine"
    else
        echo "  [FAIL] $ENTRY cannot resolve the shared engine"
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
echo "Engine location(s):"
for dest in "${DESTINATIONS[@]}"; do
    echo "  - $dest/shared"
done
echo "Available skills:"
for skill_dir in "$SKILLS_SRC"/*/; do
    echo "  - $(basename "$skill_dir")"
done

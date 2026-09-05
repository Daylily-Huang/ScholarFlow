#!/usr/bin/env bash
# ScholarFlow One-Click Skill Installer for Linux / macOS
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SKILLS_SRC="$REPO_ROOT/skills"

if [ ! -d "$SKILLS_SRC" ]; then
    echo "[-] skills directory not found: $SKILLS_SRC"
    exit 1
fi

DEST_AGENTS="$HOME/.agents/skills"
DEST_CLAUDE="$HOME/.claude/skills"

echo "=========================================="
echo "  ScholarFlow Skills Installer"
echo "=========================================="

for dest in "$DEST_AGENTS" "$DEST_CLAUDE"; do
    echo "[*] Target directory: $dest"
    mkdir -p "$dest"
    for skill_dir in "$SKILLS_SRC"/*/; do
        skill_name="$(basename "$skill_dir")"
        echo "  -> Installing $skill_name..."
        rm -rf "$dest/$skill_name"
        cp -r "$skill_dir" "$dest/$skill_name"
    done
done

echo ""
echo "[SUCCESS] ScholarFlow skills installed successfully!"
echo "Available skills:"
for skill_dir in "$SKILLS_SRC"/*/; do
    echo "  - $(basename "$skill_dir")"
done

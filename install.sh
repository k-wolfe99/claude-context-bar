#!/bin/sh
set -e

SCRIPT_SRC="$(cd "$(dirname "$0")" && pwd)/claude-context-bar.py"
SCRIPT_DST="$HOME/.claude/claude-context-bar.py"
SETTINGS="$HOME/.claude/settings.json"

# Copy script
mkdir -p "$HOME/.claude"
cp "$SCRIPT_SRC" "$SCRIPT_DST"
chmod +x "$SCRIPT_DST"
echo "✓ Installed $SCRIPT_DST"

# Patch settings.json
python3 - "$SETTINGS" "$SCRIPT_DST" <<'PYEOF'
import sys, json, os

settings_path, script_path = sys.argv[1], sys.argv[2]

if os.path.exists(settings_path):
    with open(settings_path) as f:
        settings = json.load(f)
else:
    settings = {}

settings["statusLine"] = {
    "type": "command",
    "command": f"python3 {script_path}"
}

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")

print(f"✓ Updated {settings_path}")
PYEOF

echo ""
echo "Done. Restart Claude Code to activate the context bar."

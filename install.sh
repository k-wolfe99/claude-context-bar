#!/bin/sh
set -e

SCRIPT_SRC="$(cd "$(dirname "$0")" && pwd)/claude-context-bar.py"
SCRIPT_DST="$HOME/.claude/claude-context-bar.py"
SETTINGS="$HOME/.claude/settings.json"

usage() {
    cat <<EOF
Usage: ./install.sh [--force]

Installs or updates the context bar. Safe to re-run: an update replaces the
script and leaves settings.json untouched.

  --force   Repoint statusLine at this script even if it currently points
            somewhere else.

Tunables are read from the environment, so updating never clobbers them:
  CCBAR_TTL_SECONDS   prompt cache TTL in seconds (default 300)
  CCBAR_BAR_WIDTH     progress bar width in cells (default 24)
EOF
}

FORCE=0
case "${1:-}" in
    --force) FORCE=1 ;;
    -h|--help) usage; exit 0 ;;
    "") ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 64 ;;
esac

mkdir -p "$HOME/.claude"
cp "$SCRIPT_SRC" "$SCRIPT_DST"
chmod +x "$SCRIPT_DST"
echo "✓ Installed $SCRIPT_DST"

# settings.json is the user's file and may hold hooks, permissions and MCP
# servers. Touch it only when it actually needs changing, and never leave a
# failure here half-applied — the script above is already in place and valid.
set +e
python3 - "$SETTINGS" "$SCRIPT_DST" "$FORCE" <<'PYEOF'
import sys, json, os

settings_path, script_path, force = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
wanted = f"python3 {script_path}"

if os.path.exists(settings_path):
    try:
        with open(settings_path) as f:
            settings = json.load(f)
    except (OSError, ValueError) as e:
        print(f"! Could not read {settings_path}: {e}")
        print("  The script is installed; settings.json was left alone.")
        print("  Add this yourself:")
        print(f'    "statusLine": {{"type": "command", "command": "{wanted}"}}')
        sys.exit(2)
else:
    settings = {}

existing = settings.get("statusLine")
current = existing.get("command") if isinstance(existing, dict) else None

if current and script_path in current:
    print(f"✓ {settings_path} already points here — no changes needed")
    print("")
    print("Done. The new version is live on the next status line repaint;")
    print("no restart required.")
    sys.exit(0)

if current and not force:
    print(f"! statusLine already points somewhere else:")
    print(f"    {current}")
    print("  Leaving it alone. Re-run with --force to repoint it here, or")
    print(f"  update that file/command yourself to use {script_path}.")
    sys.exit(3)

settings["statusLine"] = {"type": "command", "command": wanted}
try:
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
except OSError as e:
    print(f"! Could not write {settings_path}: {e}")
    sys.exit(2)

print(f"✓ Updated {settings_path}")
print("")
print("Done. Restart Claude Code to activate the context bar.")
PYEOF
status=$?
set -e

exit $status

#!/bin/sh
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_SRC="$HERE/claude-context-bar.py"
SCRIPT_DST="$HOME/.claude/claude-context-bar.py"
ROWS_SRC="$HERE/claude-agent-rows.py"
ROWS_DST="$HOME/.claude/claude-agent-rows.py"
SETTINGS="$HOME/.claude/settings.json"

usage() {
    cat <<EOF
Usage: ./install.sh [--force]

Installs or updates the context bar and the subagent rows. Safe to re-run: an
update replaces the scripts and leaves settings.json untouched.

  --force   Repoint statusLine and subagentStatusLine at these scripts even if
            they currently point somewhere else.

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
for pair in "$SCRIPT_SRC:$SCRIPT_DST" "$ROWS_SRC:$ROWS_DST"; do
    cp "${pair%%:*}" "${pair#*:}"
    chmod +x "${pair#*:}"
    echo "✓ Installed ${pair#*:}"
done

# settings.json is the user's file and may hold hooks, permissions and MCP
# servers. Touch it only when it actually needs changing, and never leave a
# failure here half-applied — the script above is already in place and valid.
set +e
python3 - "$SETTINGS" "$SCRIPT_DST" "$ROWS_DST" "$FORCE" <<'PYEOF'
import sys, json, os

settings_path, force = sys.argv[1], sys.argv[4] == "1"
wanted = {"statusLine": sys.argv[2], "subagentStatusLine": sys.argv[3]}

if os.path.exists(settings_path):
    try:
        with open(settings_path) as f:
            settings = json.load(f)
    except (OSError, ValueError) as e:
        print(f"! Could not read {settings_path}: {e}")
        print("  The script is installed; settings.json was left alone.")
        print("  Add this yourself:")
        for key, path in wanted.items():
            print(f'    "{key}": {{"type": "command", "command": "python3 {path}"}}')
        sys.exit(2)
else:
    settings = {}

changed, skipped = [], []
for key, script_path in wanted.items():
    existing = settings.get(key)
    current = existing.get("command") if isinstance(existing, dict) else None
    if current and script_path in current:
        print(f"✓ {key} already points here")
        continue
    if current and not force:
        print(f"! {key} already points somewhere else:")
        print(f"    {current}")
        print("  Leaving it alone. Re-run with --force to repoint it here, or")
        print(f"  update that file/command yourself to use {script_path}.")
        skipped.append(key)
        continue
    settings[key] = {"type": "command", "command": f"python3 {script_path}"}
    changed.append(key)

if changed:
    try:
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
    except OSError as e:
        print(f"! Could not write {settings_path}: {e}")
        sys.exit(2)
    print(f"✓ Updated {', '.join(changed)} in {settings_path}")

print("")
if skipped:
    sys.exit(3)
if changed:
    print("Done. Restart Claude Code to activate the changes.")
else:
    print("Done. The new version is live on the next repaint; no restart required.")
PYEOF
status=$?
set -e

exit $status

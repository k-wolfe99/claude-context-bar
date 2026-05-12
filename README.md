# Claude Code Context Bar

A persistent status bar for [Claude Code](https://claude.ai/code) that shows the current model and a color-coded context window progress bar.

```
Sonnet 4.6  [████████░░░░░░░░░░░░░░░░░░░░░░]  44.8k / 200k (22.0%)
```

The bar transitions through 8 color stops as your context fills up:

| Range   | Color         |
|---------|---------------|
| 0–15%   | Bright green  |
| 15–28%  | Lime          |
| 28–42%  | Yellow-green  |
| 42–55%  | Yellow        |
| 55–65%  | Gold          |
| 65–75%  | Orange        |
| 75–87%  | Orange-red    |
| 87–100% | Red           |

## Requirements

- [Claude Code](https://claude.ai/code) v1.0.71 or later
- Python 3 (pre-installed on macOS)

## Installation

```sh
git clone https://github.com/k-wolfe99/claude-context-bar.git
cd claude-context-bar
chmod +x install.sh
./install.sh
```

Then restart Claude Code.

## Manual installation

1. Copy `claude-context-bar.py` to `~/.claude/`
2. Add to `~/.claude/settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "python3 /YOUR_HOME/.claude/claude-context-bar.py"
}
```

3. Restart Claude Code.

## How it works

Claude Code runs the status line command after each response, passing a JSON payload via stdin that includes model info, token counts (including cached tokens), and context window size. The script sums `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` to get the true in-context token count.

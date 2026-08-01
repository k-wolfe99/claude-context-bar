# Claude Code Context Bar

A persistent status bar for [Claude Code](https://claude.ai/code) that shows the current model, a color-coded context window progress bar, and when your prompt cache lapses.

```
Sonnet 4.6  [██████░░░░░░░░░░░░░░░░░░]  44.8k / 200k (22.0%)  ⏱ til 1:24pm $0.013→$0.168
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

## Cache expiry

Anthropic's prompt cache has a 5-minute TTL. Send your next message inside that window and the conversation is billed at the cheap cache-read rate (0.1× input); let it lapse and the cache must be written again at 1.25× input — a **12.5× difference** on the same tokens.

The `⏱` segment shows the wall-clock time your cache lapses, followed by both prices: green is what the next request costs if you beat that time, red is what it costs if you don't.

```
⏱ til 1:24pm $0.013→$0.168
        │        │       └── cache write, if you miss it
        │        └────────── cache read, if you make it
        └─────────────────── compare against your own clock
```

The expiry pushes outward as you work — every turn *and every tool call* is an API request that renews the TTL.

### Why a time and not a countdown

The first version of this showed `⏱ 4:12` ticking down to `0:00`, color-coded green to red. It could not work, and the reason is worth recording so nobody rebuilds it.

Claude Code runs the status line command on **conversation events, not on a timer**. Measured on an idle session: the transcript aged smoothly from 1.4s to 93.6s while the status line was invoked **zero times** in that 98-second window. Worse, every repaint that *does* happen occurs moments after a transcript write — so `remaining` is always ~300 when anyone asks. A countdown is therefore pinned at `5:00` forever, and a gradient keyed to it is pinned at green.

An absolute time has none of that fragility: the string stays true no matter how stale it is, because you do the comparison. The colors moved onto the two prices, where they mean something at paint time.

A real ticking countdown is possible, but only outside Claude Code — a daemon painting into a tmux status line or terminal title, updating every second on its own clock.

### Caveats

- **The clock starts from the transcript file's mtime**, which tracks the last request. Cache reads renew the TTL just as writes do, so this is the right thing to measure. The tradeoff is that any local write to the transcript also looks like a renewal.
- **The whole context is treated as cacheable.** Only the prefix up to the last cache breakpoint is actually written, so the write figure is a slight over-estimate.
- **Fast mode isn't priced.** The status line payload doesn't expose it, so Opus 5 fast mode shows the standard rate.

Prices come from the model in the payload:

| Model | Input $/MTok | Cache read (0.1×) | Cache write (1.25×) |
|---|---|---|---|
| Fable 5 / Mythos 5 | 10.00 | 1.00 | 12.50 |
| Opus 5 / 4.8 / 4.7 / 4.6 / 4.5 | 5.00 | 0.50 | 6.25 |
| Sonnet 5 | 3.00 (2.00 intro through 2026-08-31) | 0.30 (0.20) | 3.75 (2.50) |
| Sonnet 4.6 / 4.5 | 3.00 | 0.30 | 3.75 |
| Haiku 4.5 | 1.00 | 0.10 | 1.25 |

An unrecognized model still gets an expiry time, just without prices. If you cache with `{"ttl": "1h"}`, change `TTL_SECONDS` at the top of the script.

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

## Tests

```sh
python3 test_context_bar.py
```

Stdlib only — pipes synthetic payloads through the script and pins the cache clock by setting the mtime of a temporary transcript file. Times are asserted against locally-constructed epochs, so the suite is timezone-proof.

## How it works

Claude Code runs the status line command on conversation events, passing a JSON payload via stdin that includes model info, token counts (including cached tokens), the context window size, and the path to the session transcript. The script sums `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` to get the true in-context token count, and stats the transcript to find when the cache lapses.

If the transcript path is missing or unreadable, the cache segment is omitted and the bar renders exactly as it did before — the cache readout can't take the context bar down with it.

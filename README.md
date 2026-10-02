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

## Live countdown mod

`mod/` holds the same bar as a Claude Code mod (a plugin of function hooks), drawn under the prompt where the status line was, above Claude Code's own hint line. A mod has a clock of its own, so it can do what the status line [can't](#why-a-time-and-not-a-countdown): count the cache down in real time.

```
Opus 5.5  [██████░░░░░░░░░░░░░░░░░░]  256.9k / 1M (26.0%)  ⏱ 58:59  $0.051→$2.056
```

- **The countdown ticks every second**, green to red, with no conversation activity needed. At zero it reads `⏱ lapsed` and shows only the write price, the one the next request will pay.
- **The clock starts when each main-thread request is sent**, taken from the request itself rather than the transcript's mtime. Tool-call requests renew it. Subagent requests don't, since they cache their own prefix.
- **On `/resume`** the bar comes back within a second with the resumed conversation's context and the time since its last response. You can see how much is sitting in cache before you send anything. If it has been idle past the TTL, it reads `⏱ lapsed` with the cost of writing it to the cache again. Both come from the last main-thread response in the transcript, not the file's mtime, because resuming appends bookkeeping rows that would make a cold cache look fresh. Only the last 4 MB of the transcript is read (with `tail`), because a long session's transcript outgrows the 4 MiB limit on a mod's file reads. Where a mod can't run commands, such as the desktop app, the whole file is read, which works until the transcript passes that limit. After that the bar shows the window with `⏱ --:--`.
- **On `/compact`**, and on auto-compaction, the bar redraws as soon as the compaction finishes. It shows the compacted size as an estimate, `~45.3k`, with `⏱ compacted` and the write price, because nothing of the summary is cached yet. The estimate is the summary's own token count plus the system prompt, tools and memory as `/context` counts them. Claude Code's local counts run high, so expect it to be off by a few thousand tokens. The next request replaces it with the real figure and starts the countdown. A `/resume` onto a conversation whose last entry is a compaction shows the same.
- **On `/clear`** the bar hides until the new conversation's first request, since nothing is cached yet.
- **Until the first request after a load** the bar shows `⏱ --:--`, because when the cache was last renewed isn't known yet.

The mods API is early access. This was built and tested on Claude Code 2.1.287.

### Loading it

For one session: `claude --plugin-dir /path/to/claude-context-bar/mod`.

For every session, add the folder to the `env` block of your user `settings.json`:

```json
"env": {
  "CLAUDE_CODE_PLUGIN_DIRS": "/path/to/claude-context-bar/mod"
}
```

If the bar never appears, mods may be switched off in that install. They are early access, behind a rollout flag that stays off when Claude Code can't fetch flags: on a third-party API provider, or with telemetry turned off. `claude --debug` then logs `hooks modules are not turned on for installed plugins`. Turn them on in the same `env` block:

```json
"CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1"
```

Then remove `statusLine` from the same file if you no longer want the Python bar alongside it. Keep `subagentStatusLine`: a mod can't draw the agent panel rows, so [`claude-agent-rows.py`](#subagent-rows) still handles those.

### Options

| Option | Default | Meaning |
|---|---|---|
| `cacheTtl` | `1h` | `5m` or `1h`. Claude Code caches for 1 hour on a Claude subscription and 5 minutes on an API key, unless its `promptCacheTtl` setting says otherwise. Also sets the write price: 2× input for 1h, 1.25× for 5m. |
| `placement` | `below` | `below` draws under the prompt, in the status line's old spot. `above` draws a band over the prompt instead. |
| `barWidth` | `24` | Progress bar width in cells. |

Change them in `/config`, or set them under `pluginConfigs` in `settings.json`:

```json
"pluginConfigs": {
  "context-bar": { "options": { "cacheTtl": "5m" } }
}
```

### Prices

`mod/hooks/format.ts` has its own copy of `PRICES`, because a mod can't import the Python script. `check_pricing.py` checks only the Python table, so `test_mod_prices.py` fails whenever the two copies differ. Update both together.

## Subagent rows

The main status line always describes the main session, even while you view a subagent. So `claude-agent-rows.py` adds each running subagent's model to its row in the agent panel, beside the timer and token count:

```
○ general-purpose  Committing porSpan clamp fix             Opus 5.5 · 2m 7s · ↓ 110.9k tokens
```

It is wired up as `subagentStatusLine`. The name comes from the `.meta.json` file Claude Code writes beside each subagent transcript. Finished agents, and any row the script can't read, keep Claude Code's default rendering.

## Cache expiry

Anthropic's prompt cache has a 5-minute TTL. Send your next message inside that window and the conversation is billed at the cheap cache-read rate (0.1× input on most models); let it lapse and the cache must be written again at 1.25× input — a **12.5× difference** on the same tokens, and 25–50× on Opus 5.5 and Fable 5.1, whose cache reads are cheaper still.

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

Prices come from the model in the payload, per the [Anthropic pricing page](https://platform.claude.com/docs/en/about-claude/pricing):

| Model | Input $/MTok | Cache read | Cache write, 5m (1.25×) | Cache write, 1h (2×) |
|---|---|---|---|---|
| Fable 5.1 / Mythos 5.1 | 10.00 | 0.25 (0.025×) | 12.50 | 20.00 |
| Fable 5 / Mythos 5 | 10.00 | 1.00 (0.1×) | 12.50 | 20.00 |
| Opus 5.5 | 4.00 | 0.20 (0.05×) | 5.00 | 8.00 |
| Opus 5 / 4.8 / 4.7 / 4.6 / 4.5 | 5.00 | 0.50 (0.1×) | 6.25 | 10.00 |
| Sonnet 5 | 2.00 | 0.20 (0.1×) | 2.50 | 4.00 |
| Sonnet 4.6 / 4.5 | 3.00 | 0.30 (0.1×) | 3.75 | 6.00 |
| Haiku 4.5 | 1.00 | 0.10 (0.1×) | 1.25 | 2.00 |

The write column follows `CCBAR_TTL_SECONDS`: 1.25× at the default 5-minute TTL, 2× when it is set above 300.

An unrecognized model still gets an expiry time, just without prices.

### Keeping prices current

`check_pricing.py` compares `PRICES` in the script against the live pricing page and lists every figure that differs, including any current model the script has no entry for:

```sh
python3 check_pricing.py
```

It exits 0 when in sync, 1 on drift, and 2 if the page can't be fetched or its layout isn't recognised. A weekly GitHub Actions job (`.github/workflows/pricing-check.yml`) runs it and opens an issue labelled `pricing-drift` when prices change, then closes it once a later run is clean. It only reports; updating the table stays a manual edit.

## Configuration

Tunables are read from the environment, not edited into the script — so updating, which copies the script over the top of itself, can't silently clobber them.

| Variable | Default | Meaning |
|---|---|---|
| `CCBAR_TTL_SECONDS` | `300` | Prompt cache TTL. Set to `3600` if you cache with `{"ttl": "1h"}`; this also switches the write price to the 1-hour rate (2×). |
| `CCBAR_BAR_WIDTH` | `24` | Progress bar width in cells. |

Set them inline in `settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "CCBAR_TTL_SECONDS=3600 python3 /YOUR_HOME/.claude/claude-context-bar.py"
}
```

Anything unparseable or out of range quietly falls back to the default — a status line should never crash or print a diagnostic into your bar.

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

## Updating

```sh
cd claude-context-bar && git pull && ./install.sh
```

Safe to re-run. If `settings.json` already points at the installed script the installer leaves it completely alone, and **no restart is needed** — Claude Code re-runs the status line command on every repaint, so the new version appears immediately.

If your `statusLine` points somewhere else (a renamed script, or a wrapper of your own), the installer says so and changes nothing rather than hijacking it. Pass `--force` to repoint it.

Exit codes: `0` installed or updated, `2` couldn't read or write `settings.json` (the script itself is still installed), `3` left an existing `statusLine` or `subagentStatusLine` alone.

## Manual installation

1. Copy `claude-context-bar.py` and `claude-agent-rows.py` to `~/.claude/`
2. Add to `~/.claude/settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "python3 /YOUR_HOME/.claude/claude-context-bar.py"
},
"subagentStatusLine": {
  "type": "command",
  "command": "python3 /YOUR_HOME/.claude/claude-agent-rows.py"
}
```

3. Restart Claude Code.

## Tests

```sh
python3 test_context_bar.py
python3 test_check_pricing.py
python3 test_agent_rows.py
python3 test_mod_prices.py
claude plugin test mod
```

Stdlib only — pipes synthetic payloads through the script and pins the cache clock by setting the mtime of a temporary transcript file. Times are asserted against locally-constructed epochs, so the suite is timezone-proof.

The mod's tests run inside Claude Code's own plugin test kit on a mocked clock. They cover the drawn line, the countdown ticking with no events, the lapsed state, subagent requests leaving the clock alone, both TTLs, `/resume`, `/clear`, `/compact`, and the model's response passing through unchanged. `claude plugin validate mod` checks the manifest and what the module hooks. After the mod has loaded once, `tsc -p mod` type-checks it against the types the engine lays in `mod/.claude-plugin/types/` (gitignored).

## How it works

Claude Code runs the status line command on conversation events, passing a JSON payload via stdin that includes model info, token counts (including cached tokens), the context window size, and the path to the session transcript. The script sums `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` to get the true in-context token count, and stats the transcript to find when the cache lapses.

If the transcript path is missing or unreadable, the cache segment is omitted and the bar renders exactly as it did before — the cache readout can't take the context bar down with it.

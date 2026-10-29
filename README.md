# Claude Code Context Bar

A bar for [Claude Code](https://claude.ai/code) that shows the current model, how full the context window is, and how long until your prompt cache lapses, with what the next request costs either way.

```
Opus 5.5  [██████░░░░░░░░░░░░░░░░░░]  256.9k / 1M (26.0%)  ⏱ 58:59  $0.051→$2.056
```

It comes in two forms:

| | Mod (`mod/`) | Status line (`claude-context-bar.py`) |
|---|---|---|
| Cache readout | A live countdown, ticking every second | The time the cache lapses, `⏱ til 1:24pm` |
| Needs | Claude Code with mods (early access) | Any Claude Code from v1.0.71, and Python 3 |

The status line can't count down because Claude Code only reruns it on conversation events, never on a timer. Use the mod if your Claude Code supports mods, and the status line otherwise.

## What it shows

- **Model**, then a **progress bar** of the context window that shifts from green to red as it fills:

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

- **Tokens in context** against the window size.
- **`⏱`**, the prompt cache, followed by two prices. Green is what the next request costs while the cache is warm (a cache read). Red is what it costs once the cache has lapsed and must be written again. Once it lapses, only the red price is shown.

The gap between the two prices is why the timer matters. A cache write costs 1.25× the input rate on a 5-minute cache and 2× on a 1-hour cache, while a read costs 0.1× on most models and less on some (0.05× on Opus 5.5, 0.025× on Fable 5.1). Letting a large context lapse costs 12.5× to 80× more than sending in time. Every request renews the cache, including each tool call.

## Mod

### Install

Clone the repo, then add its `mod/` folder to the `env` block of your user `settings.json` (`~/.claude/settings.json`):

```json
"env": {
  "CLAUDE_CODE_PLUGIN_DIRS": "/path/to/claude-context-bar/mod"
}
```

On Windows, give the full path. Backslashes must be doubled in JSON, or use forward slashes, which Windows also accepts:

```json
"env": {
  "CLAUDE_CODE_PLUGIN_DIRS": "C:\\Users\\you\\claude-context-bar\\mod"
}
```

If `settings.json` already has an `env` block, add the key to it rather than a second `env`; JSON keeps only one of them.

New sessions load it. To try it in one session only, run `claude --plugin-dir /path/to/claude-context-bar/mod` instead. To confirm it loaded, run `claude --debug` and look for `hooks module context-bar@inline loaded` in the log under `~/.claude/debug/`.

Mods are early access, behind a rollout flag. If the bar never appears, Claude Code may not be able to fetch that flag. This happens on a third-party API provider or with telemetry turned off, and `claude --debug` then logs `hooks modules are not turned on for installed plugins`. Turn mods on in the same `env` block:

```json
"CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1"
```

If you used this repo's status line before, remove `statusLine` from `settings.json` so the two don't draw side by side. The same goes for any other status line that shows the model or context usage: the mod already does. A status line that shows something else, such as the working directory, can stay; it draws on its own row. Keep `subagentStatusLine`; the mod can't draw the [subagent rows](#subagent-rows).

To update, `git pull`. New sessions load the new version.

Tested on Claude Code 2.1.284 and 2.1.287, and loads on Windows 11 with 2.1.287. Windows has no `tail` on its PATH, so there the mod reads the whole transcript, and on resume a transcript over about 4 MB shows `⏱ --:--` until the next request.

### Options

| Option | Default | Meaning |
|---|---|---|
| `cacheTtl` | `1h` | `5m` or `1h`, matching how long Claude Code caches for you: 1 hour on a Claude subscription, 5 minutes on an API key, unless Claude Code's `promptCacheTtl` setting says otherwise. It also sets the write price: 2× input for `1h`, 1.25× for `5m`. |
| `placement` | `below` | `below` draws under the prompt, above the hint line. `above` draws over the prompt. |
| `barWidth` | `24` | Progress bar width in cells. |

Change them in `/config`, or under `pluginConfigs` in `settings.json`:

```json
"pluginConfigs": {
  "context-bar": { "options": { "cacheTtl": "5m" } }
}
```

### What the countdown shows

- **After each request** it starts again from the full TTL, counted from when the request was sent. Subagent requests don't reset it, because they don't keep the main conversation's cache warm.
- **At zero** it reads `⏱ lapsed`.
- **When you resume a conversation** (`claude -c`, `--resume` or `/resume`), the bar comes back with the conversation's size and how much time its cache has left, read from the transcript. You can see whether it is still cached before you send anything.
- **After `/compact` or auto-compaction**, it shows `~` before the new size, an estimate, and `⏱ compacted` with the write price, since the summary isn't cached yet. The next request replaces both with the real figures.
- **After `/clear`** the bar is hidden until the new conversation's first request.
- **`⏱ --:--`** means the bar has a size but no time, because it couldn't read the transcript. This can happen in the desktop app with a very long session, over about 4 MB of transcript. The next request fixes it.

## Status line

### Install

```sh
git clone https://github.com/k-wolfe99/claude-context-bar.git
cd claude-context-bar
./install.sh
```

Then restart Claude Code. `install.sh` copies `claude-context-bar.py` and `claude-agent-rows.py` to `~/.claude/` and points `statusLine` and `subagentStatusLine` at them.

To update, run `git pull && ./install.sh`. No restart is needed, because Claude Code reruns the script on every repaint.

If `statusLine` or `subagentStatusLine` already points at a different command, the installer leaves it alone and says so. `--force` repoints it. Exit codes: `0` installed or updated, `2` couldn't read or write `settings.json` (the scripts are still copied), `3` left an existing entry alone.

To install by hand, copy the two scripts to `~/.claude/` and add:

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

### Configuration

Set these in the environment, for example inline in the `statusLine` command:

| Variable | Default | Meaning |
|---|---|---|
| `CCBAR_TTL_SECONDS` | `300` | Prompt cache TTL in seconds. Use `3600` for a 1-hour cache; this also switches the write price to 2×. |
| `CCBAR_BAR_WIDTH` | `24` | Progress bar width in cells. |

```json
"statusLine": {
  "type": "command",
  "command": "CCBAR_TTL_SECONDS=3600 python3 /YOUR_HOME/.claude/claude-context-bar.py"
}
```

An invalid value falls back to the default.

### How it times the cache

The cache is timed from the transcript file's last modification, which tracks the last request. Anything else that writes to the transcript also looks like a renewal. If the transcript can't be read, the `⏱` segment is left out and the rest of the bar still draws.

## Subagent rows

The main bar always describes the main session, even while you view a subagent. `claude-agent-rows.py`, set as `subagentStatusLine`, adds each running subagent's model to its row in the agent panel:

```
○ general-purpose  Committing porSpan clamp fix             Opus 5.5 · 2m 7s · ↓ 110.9k tokens
```

Finished agents, and any row it can't read, keep Claude Code's default rendering. It works alongside either form of the bar.

## Prices

| Model | Input $/MTok | Cache read | Cache write, 5m (1.25×) | Cache write, 1h (2×) |
|---|---|---|---|---|
| Fable 5.1 / Mythos 5.1 | 10.00 | 0.25 (0.025×) | 12.50 | 20.00 |
| Fable 5 / Mythos 5 | 10.00 | 1.00 (0.1×) | 12.50 | 20.00 |
| Opus 5.5 | 4.00 | 0.20 (0.05×) | 5.00 | 8.00 |
| Opus 5 / 4.8 / 4.7 / 4.6 / 4.5 | 5.00 | 0.50 (0.1×) | 6.25 | 10.00 |
| Sonnet 5 | 2.00 | 0.20 (0.1×) | 2.50 | 4.00 |
| Sonnet 4.6 / 4.5 | 3.00 | 0.30 (0.1×) | 3.75 | 6.00 |
| Haiku 4.5 | 1.00 | 0.10 (0.1×) | 1.25 | 2.00 |

From the [Anthropic pricing page](https://platform.claude.com/docs/en/about-claude/pricing). An unrecognized model gets the timer without prices.

Two things make the prices approximate:

- **The whole context is priced as cacheable.** Only the part up to the last cache breakpoint is actually written, so the write price runs slightly high.
- **Fast mode isn't priced.** It shows the standard rate.

### Keeping prices current

```sh
python3 check_pricing.py
```

This compares the table in `claude-context-bar.py` against the live pricing page and lists every figure that differs, including current models with no entry. It exits `0` when in sync, `1` on drift, and `2` if the page can't be fetched or read. A weekly GitHub Actions job runs it and opens a `pricing-drift` issue when prices change, closing it once they match again.

The mod keeps its own copy of the table in `mod/hooks/format.ts`. Update both together; `test_mod_prices.py` fails when they differ.

## Development

```sh
python3 test_context_bar.py
python3 test_check_pricing.py
python3 test_agent_rows.py
python3 test_mod_prices.py
claude plugin test mod
claude plugin validate mod
```

The Python tests use only the standard library. The mod's tests run in Claude Code's plugin test kit on a mocked clock. Once the mod has loaded, Claude Code writes its API types to `mod/.claude-plugin/types/` (gitignored), and `npx -p typescript tsc -p mod` type-checks it.

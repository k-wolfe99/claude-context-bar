#!/usr/bin/env python3
"""
Claude Code context bar — displays a color-coded progress bar showing
model name, token usage, and context window percentage in the status line,
plus the wall-clock time the prompt cache lapses and what the next request
costs on either side of that moment.
"""
import sys, json, os, time

data = json.load(sys.stdin)
model = (data.get("model") or {})
model_name = model.get("display_name") or model.get("id") or "Unknown"

ctx = (data.get("context_window") or {})
total = ctx.get("context_window_size") or 0
used_pct_raw = ctx.get("used_percentage")
usage = ctx.get("current_usage") or {}
input_tokens = (
    (usage.get("input_tokens") or 0) +
    (usage.get("cache_read_input_tokens") or 0) +
    (usage.get("cache_creation_input_tokens") or 0)
) or None

def env_int(name, default, minimum=1):
    """Read a positive int from the environment, falling back on anything odd.

    Tunables live in the environment rather than in this file so that
    reinstalling over the top of it cannot silently clobber them. A status
    line must never crash or print a diagnostic into the bar, so an
    unparseable or out-of-range value quietly takes the default.
    """
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


BAR_WIDTH = env_int("CCBAR_BAR_WIDTH", 24)

# Prompt cache TTL. Set CCBAR_TTL_SECONDS=3600 if you cache with {"ttl": "1h"}.
TTL_SECONDS = env_int("CCBAR_TTL_SECONDS", 300)

# Cache writes bill at 1.25x the input rate for the 5-minute TTL, 2x for 1-hour.
CACHE_WRITE_MULT = 2.0 if TTL_SECONDS > 300 else 1.25

# (substrings, input $/MTok, cache-read multiplier). First match wins, so a
# point release sits above its base model: "opus 5" would also match Opus 5.5.
# Source: https://platform.claude.com/docs/en/about-claude/pricing
PRICES = [
    (("fable-5-1", "fable 5.1", "mythos-5-1", "mythos 5.1"), 10.00, 0.025),
    (("fable", "mythos"),                                    10.00, 0.1),
    (("opus-5-5", "opus 5.5"),                                4.00, 0.05),
    (("opus",),                                               5.00, 0.1),
    (("sonnet-5", "sonnet 5"),                                2.00, 0.1),
    (("sonnet",),                                             3.00, 0.1),
    (("haiku",),                                              1.00, 0.1),
]

ESC = "\033"

DIM = 245    # expiry time — deliberately unhighlighted, it's a reference point
GREEN = 82   # cache-read price
RED = 196    # cache-write price

# 8-stop gradient: bright green → lime → yellow-green → yellow → gold → orange → orange-red → red
stops = [
    (15,  82),
    (28, 118),
    (42, 154),
    (55, 226),
    (65, 220),
    (75, 214),
    (87, 208),
    (101, 196),
]

def fmt(n):
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{int(v)}M" if v == int(v) else f"{v:.1f}M"
    elif n >= 1_000:
        v = n / 1_000
        return f"{int(v)}k" if v == int(v) else f"{v:.1f}k"
    return str(n)

def price(model):
    """(input $/MTok, cache-read multiplier), or None if the model is unrecognized."""
    ident = " ".join(v for v in (model.get("id"), model.get("display_name")) if v).lower()
    for needles, rate, read_mult in PRICES:
        if any(n in ident for n in needles):
            return rate, read_mult
    return None

def cache_expiry(transcript_path):
    """Epoch seconds at which the prompt cache lapses, or None if unknowable.

    The transcript is appended on every request — including each tool call —
    so its mtime tracks the last thing that renewed the cache. A cache read
    renews the TTL just as a write does, so this is the right clock.
    """
    if not transcript_path:
        return None
    try:
        return os.path.getmtime(transcript_path) + TTL_SECONDS
    except OSError:
        return None

def fmt_time(epoch):
    """'1:20pm' — 12-hour, no leading zero, no space before the meridiem."""
    t = time.localtime(epoch)
    hour = t.tm_hour % 12 or 12
    return f"{hour}:{t.tm_min:02d}{'am' if t.tm_hour < 12 else 'pm'}"

def cache_segment(expiry, tokens):
    """'⏱ til 1:20pm  $0.022→$0.280' — when the cache lapses, and the price
    on either side of that moment.

    The status line only repaints on conversation events, never on a timer, so
    a live countdown would sit frozen at whatever it read when the line was
    last drawn. An absolute time stays true however stale the string gets —
    you compare it against your own clock.
    """
    text = f"{ESC}[38;5;{DIM}m⏱ til {fmt_time(expiry)}{ESC}[0m"

    rates = price(model)
    if rates is not None and tokens:
        rate, read_mult = rates
        base = tokens / 1_000_000 * rate
        text += (f"  {ESC}[38;5;{GREEN}m${base * read_mult:.3f}{ESC}[0m"
                 f"{ESC}[38;5;{DIM}m→{ESC}[0m"
                 f"{ESC}[38;5;{RED}m${base * CACHE_WRITE_MULT:.3f}{ESC}[0m")

    return f"  {text}"

if input_tokens is not None and total > 0:
    pct = used_pct_raw if used_pct_raw is not None else (input_tokens / total) * 100
    filled = min(BAR_WIDTH, round((pct / 100) * BAR_WIDTH))
    empty = BAR_WIDTH - filled

    filled_bar = "█" * filled
    empty_bar  = "░" * empty

    color = next(c for threshold, c in stops if pct < threshold)

    bar = f"{ESC}[38;5;{color}m{filled_bar}{ESC}[38;5;238m{empty_bar}{ESC}[0m"

    expiry = cache_expiry(data.get("transcript_path"))
    cache = cache_segment(expiry, input_tokens) if expiry is not None else ""

    print(f"{model_name}  [{bar}]  {fmt(input_tokens)} / {fmt(total)} ({pct:.1f}%){cache}", end="")
else:
    print(f"{model_name} | Context: no data yet", end="")

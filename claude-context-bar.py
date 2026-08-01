#!/usr/bin/env python3
"""
Claude Code context bar — displays a color-coded progress bar showing
model name, token usage, and context window percentage in the status line,
plus the wall-clock time the prompt cache lapses and what the next request
costs on either side of that moment.
"""
import sys, json, os, time
from datetime import date

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

BAR_WIDTH = 24

# Prompt cache TTL. Bump to 3600 if you cache with {"ttl": "1h"}.
TTL_SECONDS = 300

# Cache reads bill at 0.1x the input rate; 5-minute cache writes at 1.25x.
CACHE_READ_MULT = 0.1
CACHE_WRITE_MULT = 1.25

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

def input_rate(model):
    """Input price in $/million tokens, or None if the model is unrecognized."""
    ident = " ".join(v for v in (model.get("id"), model.get("display_name")) if v).lower()
    if "fable" in ident or "mythos" in ident:
        return 10.00
    if "opus" in ident:
        return 5.00
    if "sonnet" in ident:
        # Sonnet 5 carries introductory input pricing through 2026-08-31.
        if ("sonnet-5" in ident or "sonnet 5" in ident) and date.today() <= date(2026, 8, 31):
            return 2.00
        return 3.00
    if "haiku" in ident:
        return 1.00
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

    rate = input_rate(model)
    if rate is not None and tokens:
        base = tokens / 1_000_000 * rate
        text += (f"  {ESC}[38;5;{GREEN}m${base * CACHE_READ_MULT:.3f}{ESC}[0m"
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

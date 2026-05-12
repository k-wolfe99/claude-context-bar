#!/usr/bin/env python3
"""
Claude Code context bar — displays a color-coded progress bar showing
model name, token usage, and context window percentage in the status line.
"""
import sys, json

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

BAR_WIDTH = 30

def fmt(n):
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{int(v)}M" if v == int(v) else f"{v:.1f}M"
    elif n >= 1_000:
        v = n / 1_000
        return f"{int(v)}k" if v == int(v) else f"{v:.1f}k"
    return str(n)

if input_tokens is not None and total > 0:
    pct = used_pct_raw if used_pct_raw is not None else (input_tokens / total) * 100
    filled = min(BAR_WIDTH, round((pct / 100) * BAR_WIDTH))
    empty = BAR_WIDTH - filled

    filled_bar = "█" * filled
    empty_bar  = "░" * empty

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
    color = next(c for threshold, c in stops if pct < threshold)

    ESC = "\033"
    bar = f"{ESC}[38;5;{color}m{filled_bar}{ESC}[38;5;238m{empty_bar}{ESC}[0m"
    print(f"{model_name}  [{bar}]  {fmt(input_tokens)} / {fmt(total)} ({pct:.1f}%)", end="")
else:
    print(f"{model_name} | Context: no data yet", end="")

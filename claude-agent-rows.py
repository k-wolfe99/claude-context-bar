#!/usr/bin/env python3
"""
Subagent rows for Claude Code's agent panel: the default row with the model
added beside the timer and token count.

    general-purpose  Committing porSpan clamp fix   Opus 5.5 · 2m 7s · ↓ 110.9k tokens

Configured as subagentStatusLine. Claude Code passes every visible row as one
JSON object on stdin; this prints one {"id", "content"} line per row it
redraws. Only running agents with a resolved model are redrawn, since a
finished row has no end time to stop the timer at. Everything else, and any
error, falls back to Claude Code's own rendering.
"""
import json, os, re, sys, time

SEP = " · "


def model_name(model_id):
    """claude-opus-5-5[1m] -> Opus 5.5, claude-haiku-4-5-20251001 -> Haiku 4.5."""
    ident = re.sub(r"\[.*?\]$", "", model_id).removeprefix("claude-")
    parts = [p for p in ident.split("-") if not re.fullmatch(r"\d{8}", p)]
    words = [p for p in parts if not p.isdigit()]
    version = ".".join(p for p in parts if p.isdigit())
    if not words:
        return model_id
    return " ".join(w.capitalize() for w in words) + (f" {version}" if version else "")


def elapsed(start_ms, now=None):
    secs = max(0, int((now if now is not None else time.time()) - start_ms / 1000))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def tokens(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def agent_type(transcript_path, session_id, task_id):
    """The agent's type (general-purpose, Explore, ...) from the metadata file
    Claude Code writes beside each subagent transcript."""
    base = os.path.dirname(transcript_path)
    meta = os.path.join(base, session_id, "subagents", f"agent-{task_id}.meta.json")
    try:
        with open(meta) as f:
            return json.load(f).get("agentType")
    except (OSError, ValueError):
        return None


def row(name, text, stats, width):
    """name, text and right-aligned stats in width columns, shortening text
    first and dropping it if even a stub won't fit."""
    left = f"{name}  " if name else ""
    room = width - len(left) - len(stats) - 2
    if text and room >= 4:
        if len(text) > room:
            text = text[:room - 1].rstrip() + "…"
        left += text
    elif name:
        left = name
    return left + " " * max(2, width - len(left) - len(stats)) + stats


def render(payload, now=None):
    width = payload.get("columns") or 80
    lines = []
    for task in payload.get("tasks", []):
        if task.get("status") != "running" or not task.get("model"):
            continue
        name = agent_type(payload.get("transcript_path", ""), payload.get("session_id", ""), task["id"])
        stats = SEP.join([
            model_name(task["model"]),
            elapsed(task.get("startTime", 0), now),
            f"↓ {tokens(task.get('tokenCount', 0))} tokens",
        ])
        text = task.get("label") or task.get("description") or ""
        lines.append(json.dumps({"id": task["id"],
                                 "content": row(name or task.get("type", ""), text, stats, width)},
                                ensure_ascii=False))
    return lines


if __name__ == "__main__":
    try:
        out = render(json.load(sys.stdin))
    except Exception:
        out = []  # never break the panel: no output keeps the default rows
    print("\n".join(out))

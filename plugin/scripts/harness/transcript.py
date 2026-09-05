"""Transcript JSONL reader (UNVERIFIED-BY-DOCS format, see research/FINDINGS.md D5).

Observed on Claude Code 2.1.261 [E1]:
  {"type":"user","message":{"role":"user","content":"..."|[{"type":"text"|"tool_result",...}]}, ...}
  {"type":"assistant","message":{"model":"...","content":[{"type":"text"|"tool_use"|"thinking",...}]}, ...}

Everything here is best-effort: unknown shapes are skipped, never raised.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_entries(path: str | None, max_bytes: int = 8_000_000) -> list[dict[str, Any]]:
    if not path:
        return []
    try:
        p = Path(path)
        if not p.is_file():
            return []
        size = p.stat().st_size
        with p.open("rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                fh.readline()  # drop partial line
            raw = fh.read().decode("utf-8", errors="replace")
        out = []
        for line in raw.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("type") in ("user", "assistant"):
                out.append(obj)
        return out
    except Exception:
        return []


def _content(entry: dict[str, Any]) -> list[dict[str, Any]]:
    msg = entry.get("message") or {}
    c = msg.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    if isinstance(c, list):
        return [b for b in c if isinstance(b, dict)]
    return []


HOOK_FEEDBACK_PREFIXES = ("Stop hook feedback", "[harness completion gate")


def is_human_turn(entry: dict[str, Any]) -> bool:
    """A user entry that starts a new prompt. Tool results are not; neither is the Stop-hook feedback Claude Code
    inserts as a user entry when this gate blocks ("Stop hook feedback: [harness completion gate 1/2] …"): the
    retry belongs to the same prompt, so evidence gathered before the block still counts (seen live: a format-only
    block was followed by "no evidence in this turn" because the restated message had no new tool calls)."""
    if entry.get("type") != "user":
        return False
    blocks = _content(entry)
    if not blocks:
        return False
    if any(b.get("type") == "tool_result" for b in blocks):
        return False
    text = "".join(str(b.get("text", "")) for b in blocks if b.get("type") == "text").lstrip()
    if text.startswith(HOOK_FEEDBACK_PREFIXES):
        return False
    return True


def current_turn(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Entries after the last human prompt (the work done for the current request)."""
    idx = -1
    for i, e in enumerate(entries):
        if is_human_turn(e):
            idx = i
    return entries[idx + 1:] if idx >= 0 else entries


def tool_calls(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pair tool_use blocks with their tool_result text."""
    results: dict[str, str] = {}
    for e in entries:
        if e.get("type") != "user":
            continue
        for b in _content(e):
            if b.get("type") == "tool_result":
                rid = b.get("tool_use_id")
                content = b.get("content")
                if isinstance(content, list):
                    text = "\n".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
                else:
                    text = str(content or "")
                if rid:
                    results[rid] = text
    calls = []
    for e in entries:
        if e.get("type") != "assistant":
            continue
        for b in _content(e):
            if b.get("type") == "tool_use":
                calls.append({
                    "id": b.get("id"),
                    "name": b.get("name") or "",
                    "input": b.get("input") if isinstance(b.get("input"), dict) else {},
                    "result": results.get(b.get("id"), ""),
                })
    return calls


def last_assistant_text(entries: list[dict[str, Any]]) -> str:
    for e in reversed(entries):
        if e.get("type") == "assistant":
            texts = [b.get("text", "") for b in _content(e) if b.get("type") == "text"]
            if texts:
                return "\n".join(texts)
    return ""

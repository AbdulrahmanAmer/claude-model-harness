"""Model detection, ranked by documented reliability (research/FINDINGS.md §1).

Order:
  1. hook stdin `model`         (SessionStart; documented, optional)              [src: S20]
  2. hook stdin `to_model`      (PostModelSwitch; documented)                     [src: S20]
  3. harness cache              (written by 1/2 or by the optional statusline
                                 wrapper that receives `model.id`)                 [src: S22]
  4. transcript JSONL           newest `type:"assistant"` line, `message.model`.
                                UNVERIFIED: file format is not documented [S34];
                                observed on Claude Code 2.1.261 [E1]; may lag [S20]
  5. ANTHROPIC_MODEL env / settings `model`  ONLY when it is a full model ID.
                                Aliases (opus, fable, sonnet) resolve server-side [S28]
                                and the env var does not follow `/model` [S20].
  6. unknown                    -> generic profile. Never guess.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from . import config

FULL_ID = re.compile(r"^(anthropic\.|us\.|eu\.|global\.)?claude-[a-z]+-\d")

# Official IDs: S17 (models overview), S18 (deprecations), S6/S41 (Fable/Mythos), S2 (Opus IDs)
PROFILE_RULES: list[tuple[str, str, str]] = [
    # (regex on model id, profile, display name)
    (r"claude-fable-5-1", "fable-5", "Claude Fable 5.1"),
    (r"claude-mythos-5-1", "fable-5", "Claude Mythos 5.1"),
    (r"claude-fable-5(?!-)", "fable-5", "Claude Fable 5"),
    (r"claude-mythos-5(?!-)", "fable-5", "Claude Mythos 5"),
    (r"claude-mythos-preview", "fable-5", "Claude Mythos Preview"),
    (r"claude-opus-5(?!-)", "opus-5", "Claude Opus 5"),
    (r"claude-opus-4-8", "opus-4x", "Claude Opus 4.8"),
    (r"claude-opus-4-7", "opus-4x", "Claude Opus 4.7"),
    (r"claude-opus-4-6", "opus-4x", "Claude Opus 4.6"),
    (r"claude-opus-4-5", "opus-4x", "Claude Opus 4.5"),
    (r"claude-opus-4-1", "opus-4x", "Claude Opus 4.1"),
    (r"claude-opus-4(?!-)", "opus-4x", "Claude Opus 4"),
    # Tiers added 2026-09-05 from research/MODEL_MATRIX.md: S45–S47 (Sonnet 5), S48/S49/S56/S57 (Sonnet 4.x),
    # S17/S50/S51/S58 (Haiku 4.5). Older Sonnet/Haiku IDs (retired, S18) fall through to `generic`.
    (r"claude-sonnet-5(?!-)", "sonnet-5", "Claude Sonnet 5"),
    (r"claude-sonnet-4-6", "sonnet-4x", "Claude Sonnet 4.6"),
    (r"claude-sonnet-4-5", "sonnet-4x", "Claude Sonnet 4.5"),
    (r"claude-haiku-4-5", "haiku", "Claude Haiku 4.5"),
]

# Every profile file the plugin ships (plugin/profiles/<tier>.md). Order = capability tier, high to low.
TIERS: tuple[str, ...] = ("fable-5", "opus-5", "opus-4x", "sonnet-5", "sonnet-4x", "haiku", "generic")


def profile_for(model_id: str | None) -> tuple[str, str]:
    """Return (profile, display_name). Unknown/None -> ('generic', 'unknown')."""
    if not model_id:
        return "generic", "unknown"
    mid = model_id.strip().lower()
    for pat, prof, name in PROFILE_RULES:
        if re.search(pat, mid):
            return prof, name
    if mid.startswith(("claude-", "anthropic.claude-")):
        return "generic", model_id
    return "generic", "unknown"


def _read_cache() -> dict[str, Any]:
    try:
        p = config.model_cache_path()
        if p.is_file():
            d = json.loads(p.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
    except Exception as e:
        config.log("model_cache_read_error", error=repr(e))
    return {}


def invalidate_cache(session_id: str | None = None) -> None:
    """Drop the cached model when a session is resumed or forked without a `model` field: the session may
    have been restored or relaunched on a different model [S20], so nothing cached before is trustworthy."""
    try:
        p = config.model_cache_path()
        if p.is_file():
            p.unlink()
            config.log("model_cache_invalidated", session=session_id)
    except Exception as e:
        config.log("model_cache_invalidate_error", error=repr(e))


def write_cache(model_id: str, source: str, session_id: str | None = None) -> None:
    try:
        p = config.model_cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "model_id": model_id, "source": source, "session_id": session_id,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }), encoding="utf-8")
    except Exception as e:
        config.log("model_cache_write_error", error=repr(e))


def model_from_transcript(path: str | os.PathLike | None, max_bytes: int = 2_000_000) -> str | None:
    """UNVERIFIED-BY-DOCS: reads `message.model` from the newest assistant line [E1]."""
    if not path:
        return None
    try:
        p = Path(path)
        if not p.is_file():
            return None
        size = p.stat().st_size
        with p.open("rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
            data = fh.read().decode("utf-8", errors="replace")
        for line in reversed(data.splitlines()):
            if '"assistant"' not in line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") == "assistant":
                m = (obj.get("message") or {}).get("model")
                if isinstance(m, str) and m:
                    return m
    except Exception as e:
        config.log("transcript_read_error", error=repr(e))
    return None


def _settings_model() -> str | None:
    """`model` key from project/user settings.json [S27]. Only used if it is a full ID."""
    for p in (
        config.project_dir() / ".claude" / "settings.local.json",
        config.project_dir() / ".claude" / "settings.json",
        config._home() / "settings.json",
    ):
        try:
            if p.is_file():
                m = json.loads(p.read_text(encoding="utf-8")).get("model")
                if isinstance(m, str) and m:
                    return m
        except Exception:
            continue
    return None


def detect(hook_input: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return {model_id, display_name, profile, source, confidence}. Never raises."""
    hook_input = hook_input or {}
    try:
        session_id = hook_input.get("session_id")
        candidates: list[tuple[str | None, str, str]] = []  # (id, source, confidence)

        m = hook_input.get("model")
        if isinstance(m, str) and m:
            candidates.append((m, "hook:SessionStart.model", "high"))
        m = hook_input.get("to_model")
        if isinstance(m, str) and m:
            candidates.append((m, "hook:PostModelSwitch.to_model", "high"))

        cache = _read_cache()
        tm = model_from_transcript(hook_input.get("transcript_path"))
        if cache.get("model_id") and tm and tm != cache["model_id"]:
            # The transcript shows a response from a model the cache does not know about: the session was resumed
            # or relaunched on another model without a hook event (e.g. `claude --resume … --model X`, which carries
            # no `model` field [S20]). The newer evidence wins; the stale cache is dropped.
            config.log("cache_stale", cached=cache["model_id"], transcript=tm, session=session_id)
            cache = {}
        if cache.get("model_id"):
            same = (not session_id) or cache.get("session_id") in (None, session_id)
            candidates.append((cache["model_id"], f"cache:{cache.get('source','?')}",
                               "high" if same else "medium"))

        if tm:
            candidates.append((tm, "transcript:message.model (UNVERIFIED-BY-DOCS)", "medium"))

        env = os.environ.get("ANTHROPIC_MODEL")
        if env and FULL_ID.match(env):
            candidates.append((env, "env:ANTHROPIC_MODEL (does not follow /model)", "low"))
        sm = _settings_model()
        if sm and FULL_ID.match(sm):
            candidates.append((sm, "settings:model (intent, not resolved)", "low"))

        for mid, source, conf in candidates:
            if mid:
                prof, name = profile_for(mid)
                if source.startswith("hook:"):
                    write_cache(mid, source, session_id)
                return {"model_id": mid, "display_name": name, "profile": prof,
                        "source": source, "confidence": conf}
        return {"model_id": None, "display_name": "unknown", "profile": "generic",
                "source": "none", "confidence": "none"}
    except Exception as e:
        config.log("detect_error", error=repr(e))
        return {"model_id": None, "display_name": "unknown", "profile": "generic",
                "source": "error", "confidence": "none"}

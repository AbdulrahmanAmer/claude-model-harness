"""Chunk mode: a task split into small, scoped, individually-gated units of work.

State file: <project>/.claude/harness/chunks.json  (created only by the /chunk skill on request)
{
  "task": "...",
  "active": 2,                       # id of the chunk being worked, or null
  "chunks": [
    {"id": 1, "goal": "...", "kind": "mechanical|feature|refactor|debug|research",
     "paths": ["src/auth/**", "tests/test_auth.py"],      # scope lock globs (PreToolUse)
     "acceptance": ["pytest tests/test_auth.py -q"],       # commands that must run and pass
     "effort": "low|medium|high|xhigh",                    # recommendation, see recommend_effort
     "status": "pending|active|done|blocked", "evidence": "..."}
  ]
}

Effort recommendation (cited; per running model — research/MODEL_MATRIX.md):
  * plan the whole task once at the default `high` — Opus 5 "performs best when given the complete
    task specification up front" [src: S1]; default effort is `high` on every model that supports it [src: S14, S28]
  * which levels exist per model in Claude Code [src: S28]: Fable/Mythos 5.x, Opus 5, Sonnet 5, Opus 4.8, Opus 4.7 →
    low..max; Opus 4.6 and Sonnet 4.6 → low, medium, high, max (no xhigh; xhigh runs as high); Haiku 4.5, Sonnet 4.5,
    Opus 4.5 → not listed, "do not support effort" (Haiku 4.5 / Sonnet 4.5 have no effort parameter at all [src: S17, S47])
  * tier sweet spots: Opus 5 "use low and medium liberally … wherever your evals show quality holds", xhigh for
    demanding coding [src: S14]; Opus 4.7/4.8 "Start with xhigh for coding and agentic use cases", medium "the drop-in for
    the average workflow", "step down to medium or low only when you've measured" [src: S14]; Opus 4.6 no xhigh, "Use
    effort as a fallback" against over-exploration [src: S14, S8]; Sonnet 5 default high, xhigh for the hardest coding,
    medium ≈ Sonnet 4.6 at high, low for short scoped tasks [src: S45, S14]; Sonnet 4.6 "Medium effort (recommended
    default)" for agentic coding [src: S14]; Fable 5.1 start at high, "step down to medium or low where your evals show
    quality holds", at low it searches less [src: S4, S14]
  * never disable thinking to save cost; "thinking enabled at `low` effort performs better than thinking disabled at
    similar cost" [src: S1]
  * community: medium reported better-scoped work on Opus 5 (6 independent reports) — research/COMMUNITY.md
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any

from . import config

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


def chunks_path(project: Path | None = None) -> Path:
    return (project or config.project_dir()) / ".claude" / "harness" / "chunks.json"


def load(project: Path | None = None) -> dict[str, Any] | None:
    try:
        p = chunks_path(project)
        if p.is_file():
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("chunks"), list):
                return d
    except Exception as e:
        config.log("chunks_read_error", error=repr(e))
    return None


def save(data: dict[str, Any], project: Path | None = None) -> None:
    try:
        p = chunks_path(project)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        config.log("chunks_write_error", error=repr(e))


def active_chunk(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data or data.get("active") is None:
        return None
    for c in data.get("chunks", []):
        if c.get("id") == data.get("active"):
            return c
    return None


# Effort levels Claude Code offers per model [src: S28] (the API table is in S14; api/ wrappers encode that one).
EFFORT_SUPPORT_CC: list[tuple[str, tuple[str, ...]]] = [
    (r"claude-(fable|mythos)-", EFFORT_LEVELS),
    (r"claude-opus-5(?!-)|claude-sonnet-5(?!-)|claude-opus-4-[78]", EFFORT_LEVELS),
    (r"claude-opus-4-6|claude-sonnet-4-6", ("low", "medium", "high", "max")),
    (r"claude-haiku-|claude-sonnet-4-5|claude-opus-4-5|claude-opus-4-1|claude-opus-4(?!-)|claude-sonnet-4(?!-)|claude-3", ()),
]


def supported_efforts(model_id: str | None) -> tuple[str, ...] | None:
    """Levels the model accepts in Claude Code [S28]; () = no effort parameter; None = model unknown."""
    if not model_id:
        return None
    m = model_id.lower()
    for rx, levels in EFFORT_SUPPORT_CC:
        if re.search(rx, m):
            return levels
    return None


def _tier(model_id: str | None) -> str:
    from . import detect_model
    return detect_model.profile_for(model_id)[0] if model_id else "generic"


def recommend_effort(kind: str, n_paths: int, has_acceptance: bool, model_id: str | None = None) -> tuple[str | None, str]:
    """Return (effort or None, one-line reason with citation) for the running model.
    None means the model has no effort parameter (Haiku 4.5, Sonnet 4.5) or none in Claude Code (Opus 4.5) [S17, S28, S47]."""
    kind = (kind or "feature").lower()
    small = n_paths <= 2 and has_acceptance
    routine = kind in ("feature", "mechanical") and n_paths <= 6
    hard = kind in ("debug", "research", "refactor") or n_paths > 6
    levels = supported_efforts(model_id)
    if levels == ():
        return None, f"effort is not supported on {model_id} (no effort parameter in Claude Code) [S17, S28, S47]"
    tier = _tier(model_id)
    mid = (model_id or "").lower()
    if tier == "opus-5":
        if kind == "mechanical" and small:
            eff, why = "low", "single-file/mechanical change with an acceptance test; Opus 5: use low and medium liberally wherever quality holds [S14]"
        elif routine:
            eff, why = "medium", "routine scoped chunk; Opus 5: use low and medium liberally [S14]; community: better-scoped work (COMMUNITY.md)"
        else:
            eff, why = "high", "investigation / multi-file change; keep the default high, step up to xhigh only for demanding coding [S14]"
    elif tier == "fable-5":
        if kind == "mechanical" and small:
            eff, why = "medium", "small mechanical chunk; Fable 5.1 at medium roughly matches Fable 5 at lower cost — step down where quality holds [S4]"
        elif hard and n_paths > 6:
            eff, why = "xhigh", "large multi-file chunk; xhigh for the most capability-sensitive agentic and coding work [S14]"
        else:
            eff, why = "high", "start at the default high on Fable [S4, S14]; at low it calls search/retrieval tools less [S4]"
    elif tier == "sonnet-5":
        if kind == "mechanical" and small:
            eff, why = "medium", "small mechanical chunk; Sonnet 5 at medium ≈ Sonnet 4.6 at high, a cost-saving step-down [S45, S14]"
        elif hard:
            eff, why = "xhigh", "hardest coding/agentic work: raise effort to xhigh rather than prompting around shallow reasoning [S45]"
        else:
            eff, why = "high", "the Sonnet 5 default; balances token usage and intelligence for most use cases [S45]"
    elif tier == "opus-4x":
        if "opus-4-6" in mid:
            if hard:
                eff, why = "high", "Opus 4.6 has no xhigh; high is its top routine level [S14, S28]"
            else:
                eff, why = "medium", "Opus 4.6 does more upfront exploration at higher effort; use effort as a fallback against over-exploration [S8]"
        else:
            if kind == "mechanical" and small:
                eff, why = "medium", "small mechanical chunk; on Opus 4.7/4.8 medium is 'the drop-in for the average workflow' — step down only where you've measured quality holds [S14]"
            elif hard:
                eff, why = "xhigh", "Opus 4.7/4.8: 'Start with xhigh for coding and agentic use cases' [S14]"
            else:
                eff, why = "high", "Opus 4.7/4.8: high is the minimum for intelligence-sensitive work; xhigh for coding when the chunk is demanding [S14]"
    elif tier == "sonnet-4x":
        if hard:
            eff, why = "high", "Sonnet 4.6: high 'for complex reasoning and tasks where quality matters more than speed or cost' (no xhigh) [S14]"
        else:
            eff, why = "medium", "Sonnet 4.6: 'Medium effort (recommended default) … suitable for agentic coding, tool-heavy workflows' [S14]"
    else:
        eff, why = "high", "model unknown or not in the matrix; high is the API and Claude Code default on every model that supports effort [S14, S28]"
    if levels and eff not in levels:
        eff = max((l for l in levels if EFFORT_LEVELS.index(l) <= EFFORT_LEVELS.index(eff)), key=EFFORT_LEVELS.index, default=levels[0])
        why += f"; clamped to {eff}, the highest level this model supports at or below the recommendation [S28]"
    return eff, why


def effort_line(model_id: str | None, effort: str | None, reason: str = "") -> str:
    """The one line the /chunk skill repeats to the user."""
    if effort is None:
        return f"effort: not supported on {model_id or 'this model'} [S17, S28] — nothing to set"
    return f"recommended effort: {effort} ({reason}) -> run: /effort {effort}"


def path_in_scope(file_path: str, globs: list[str], project: Path | None = None) -> bool:
    if not globs:
        return True
    try:
        proj = (project or config.project_dir()).resolve()
        fp = Path(file_path)
        if not fp.is_absolute():
            fp = proj / fp
        try:
            rel = fp.resolve().relative_to(proj).as_posix()
        except ValueError:
            return False  # outside the project entirely
        for g in globs:
            g = g.strip().lstrip("./")
            if fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel, g.rstrip("/") + "/*") \
               or rel == g or rel.startswith(g.rstrip("*").rstrip("/") + "/"):
                return True
            if "**" in g:
                # fnmatch has no '**'; approximate by prefix match on the part before '**'
                prefix = g.split("**", 1)[0]
                if rel.startswith(prefix):
                    return True
        return False
    except Exception:
        return True  # fail open


def new_plan(task: str, chunks: list[dict[str, Any]], model_id: str | None = None) -> dict[str, Any]:
    out = []
    for i, c in enumerate(chunks, 1):
        kind = c.get("kind", "feature")
        paths = list(c.get("paths") or [])
        acc = list(c.get("acceptance") or [])
        eff, why = recommend_effort(kind, len(paths), bool(acc), model_id)
        out.append({
            "id": i, "goal": c.get("goal", ""), "kind": kind, "paths": paths,
            "acceptance": acc, "effort": c.get("effort") or eff, "effort_reason": why,
            "status": "pending", "evidence": "",
        })
    return {"task": task, "model_id": model_id, "active": None, "chunks": out}

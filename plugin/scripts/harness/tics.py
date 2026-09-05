"""Writing-tics detector. Deterministic regex; three evidence tiers.

Tier "official"   — words Anthropic's own claude.ai system prompt tells the model to avoid [src: S13]
Tier "mannered"   — the "mannered prose" anti-pattern defined in the Fable 5.1 guide [src: S4]
Tier "community"  — community-collected Opus 5 tics (research/COMMUNITY.md, C2–C5, C13). NOT official.

Usage: find_tics(text) -> list of {tier, phrase, line, snippet}
"""
from __future__ import annotations

import re
from typing import Any

TICS: list[tuple[str, str, str]] = [
    # (tier, label, regex)
    ("official", "genuinely", r"\bgenuinely\b"),
    ("official", "honestly", r"\bhonestly\b"),
    ("official", "straightforward", r"\bstraightforward\b"),
    ("mannered", "earns its keep", r"\bearns? (its|their) keep\b"),
    ("mannered", "dial worth turning", r"\bdial worth turning\b"),
    ("mannered", "wearing X's clothing", r"\bwearing [\w' ]{1,30}clothing\b"),
    ("community", "load-bearing", r"\bload[- ]bearing\b"),
    ("community", "it's worth noting", r"\b(it'?s|it is) worth (noting|naming|knowing|stating|saying|calling out)\b"),
    ("community", "worth stating plainly", r"\bworth stating plainly\b"),
    ("community", "it's not X, it's Y", r"\b(it'?s|this is|that'?s) not (just |only |about )?[^.\n]{2,60}[,;—–-]\s*(it'?s|it is|this is|that'?s)\b"),
    ("community", "the key insight", r"\bthe key insight\b"),
    ("community", "seam(s)", r"\b(the|a|that|this|clean|natural) seams?\b"),
    ("community", "carry the argument", r"\bcarr(y|ies) the (argument|weight)\b"),
    ("community", "full stop", r"\bfull stop\b"),
    ("community", "stacked hedge", r"\b(perhaps|maybe|possibly|arguably|somewhat)\b[^.\n]{0,40}\b(perhaps|maybe|possibly|arguably|somewhat|might|could)\b"),
    ("community", "delve", r"\bdelve[sd]?\b"),
    ("community", "tapestry", r"\btapestry\b"),
    ("community", "I'll be honest", r"\b(i'?ll|let me) be (honest|frank|direct)\b"),
    ("community", "you're right", r"\byou'?re (absolutely |completely |totally )?right\b"),
]

_COMPILED = [(tier, label, re.compile(rx, re.IGNORECASE)) for tier, label, rx in TICS]


def find_tics(text: str, tiers: tuple[str, ...] = ("official", "mannered", "community")) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    if not text:
        return hits
    try:
        for lineno, line in enumerate(text.splitlines(), 1):
            for tier, label, rx in _COMPILED:
                if tier not in tiers:
                    continue
                for m in rx.finditer(line):
                    s = max(0, m.start() - 30)
                    hits.append({"tier": tier, "phrase": label, "line": lineno,
                                 "snippet": line[s:m.end() + 30].strip()})
    except Exception:
        return hits
    return hits


def summarize(hits: list[dict[str, Any]], limit: int = 6) -> str:
    if not hits:
        return ""
    parts = []
    for h in hits[:limit]:
        parts.append(f"{h['phrase']} (line {h['line']}, {h['tier']})")
    more = f" +{len(hits) - limit} more" if len(hits) > limit else ""
    return "; ".join(parts) + more

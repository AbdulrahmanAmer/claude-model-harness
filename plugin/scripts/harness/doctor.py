"""harness doctor — config linter for Claude Code instruction files and settings, tier-aware.

Scans (all optional; missing files are skipped):
  ~/.claude/CLAUDE.md, ~/.claude/rules/**/*.md, ~/.claude/skills/*/SKILL.md, ~/.claude/settings.json
  <project>/CLAUDE.md, .claude/CLAUDE.md, CLAUDE.local.md, .claude/rules/**/*.md, .claude/skills/*/SKILL.md,
  .claude/settings.json, .claude/settings.local.json                                   [src: S27, S31, S32]

Every finding carries: file, line, rule id, severity, why (with [S#] citation), suggested edit. Severity depends
on the harness tier of the detected model (research/MODEL_MATRIX.md): the same "double-check your answer" line
is an error on Opus 5 (over-verification [S1]) and informational on Sonnet/Haiku/Opus 4.x, where Anthropic's
cross-model guidance recommends an explicit self-check [S8]. `explain(rule)` prints the cited reasoning per tier.
`apply()` only ever runs after a diff has been produced; the CLI enforces `--apply`; only error/warning findings
are edited. Never rewrites settings.json (report-only there): a wrong edit could break the session.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from . import config

SEV_ORDER = {"error": 0, "warning": 1, "info": 2}
TIERS = ("fable-5", "opus-5", "opus-4x", "sonnet-5", "sonnet-4x", "haiku", "generic")


@dataclass
class Finding:
    rule: str
    severity: str
    file: str
    line: int | None
    text: str
    why: str
    fix: str
    action: str = "none"          # none | delete-line | append-block
    payload: str = ""             # for append-block

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pick(table: dict[str, str] | str, tier: str) -> str:
    """Per-tier text lookup: exact tier, then "*"."""
    if isinstance(table, str):
        return table
    return table.get(tier, table.get("*", ""))


# ------------------------------------------------------------------ line rules
# Each rule: regex over instruction lines, per-tier severity, per-tier cited reasoning, fix, apply action.
# Severity legend: error = documented harm on this tier; warning = documented harm on a sibling version or
# generation, or a documented cost; info = harmless or recommended here, reported so mixed-model teams see it.
LINE_RULES: list[dict[str, Any]] = [
    {
        "rule": "R1-verification-instruction",
        "rx": re.compile(r"(double[- ]?check|re-?verify|re-?check|verif(y|ication) (step|pass|your work|the (result|output|answer))|final verification|use a subagent to (verify|review|double)|self-?check|check your work|before (you )?(finish|respond|answer)[^.\n]*verif)", re.I),
        "sev": {"opus-5": "error", "fable-5": "info", "opus-4x": "info", "sonnet-5": "info", "sonnet-4x": "info", "haiku": "info", "generic": "warning"},
        "why": {
            "opus-5": "Opus 5 verifies its own work; explicit verification/re-check instructions cause over-verification and add cost without improving results [S1, S2, S3, S8].",
            "fable-5": "Not harmful: the Fable 5 guide recommends making self-verification explicit on long runs (fresh-context verifier subagents) [S5]; the cross-model self-check default applies [S8]. Reported so it is removed if the team also runs Opus 5.",
            "generic": "Model unknown; if it is Opus 5 this line causes over-verification [S1, S8]. State the model (status line / /status) and re-run.",
            "*": "Recommended on this model: \"Ask Claude to self-check … This catches errors reliably, especially for coding and math. Claude Opus 5 is the exception\" [S8]. Reported (info) so a mixed-model team knows it must go for Opus 5.",
        },
        "fix": {"opus-5": "Delete the line (Opus 5). Keep it in a per-model file if the team is mixed-model [S8].", "*": "Keep. Delete only if this instruction file is also loaded by Opus 5 sessions [S1]."},
        # auto-edit only where the harm is documented for the running model; on `generic` it is reported, never removed
        "action": {"opus-5": "delete-line", "*": "none"},
    },
    {
        "rule": "R2-thoroughness-cruft",
        "rx": re.compile(r"(\bbe (extremely |very )?thorough\b|\bif in doubt,? (use|call|run)\b|\bCRITICAL:? you MUST\b|\balways (use|call) the \w+ tool\b|\bthink step[- ]by[- ]step\b|\bthink (hard|harder|carefully|deeply)\b)", re.I),
        "sev": {"opus-5": "warning", "fable-5": "warning", "opus-4x": "warning", "sonnet-5": "info", "sonnet-4x": "warning", "haiku": "info", "generic": "info"},
        "why": {
            "opus-5": "Anti-laziness / over-prompting written for older models over-triggers on 4.6+ [S8]; Opus 5 already expands scope and self-verifies [S1].",
            "fable-5": "Skills and prompts written for prior models are often too prescriptive for Fable 5 and can degrade output quality [S5].",
            "opus-4x": "Opus 4.5/4.6 are more responsive to the system prompt; prompts written to stop under-triggering now over-trigger — \"dial back any aggressive language\" [S8]. (On 4.7/4.8 at low effort the documented remedy for shallow reasoning is a targeted \"Think carefully\" line, so judge by context [S14].)",
            "sonnet-5": "No over-triggering statement for Sonnet 5; at low effort Anthropic recommends the targeted line \"This task involves multistep reasoning. Think carefully through the problem before responding.\" [S45].",
            "sonnet-4x": "\"Claude 4.6 models are more proactive and may overtrigger on instructions that were needed for previous models\" — tune anti-laziness prompting [S8].",
            "haiku": "No official statement for Haiku 4.5 on under- or over-triggering; the over-triggering note names Opus 4.5/4.6 and the 4.6 generation [S8]. Reported for information only.",
            "*": "Anti-laziness prompting over-triggers on the 4.6 generation and later [S8]; model unknown.",
        },
        "fix": {"*": "Remove or soften to a plain instruction ('Use this tool when ...') [S8]."},
        "action": "delete-line",
    },
    {
        "rule": "R3-no-thinking-rule",
        "rx": re.compile(r"\b(do not|don'?t|never) (think|reason|use thinking|show (your )?(thinking|reasoning))\b", re.I),
        "sev": {"opus-5": "error", "fable-5": "info", "opus-4x": "warning", "sonnet-5": "info", "sonnet-4x": "info", "haiku": "info", "generic": "warning"},
        "why": {
            "opus-5": "A rule telling the model not to think/reason increases internal-tag and tool-call-as-text leakage on Opus 5 [S1, S16].",
            "fable-5": "Thinking is always on and cannot be disabled on Fable/Mythos [S6, S16]; the rule is dead weight.",
            "opus-4x": "With thinking off, Opus 4.5 is particularly sensitive to the word \"think\" [S8]; adaptive thinking is the recommended mode for agentic work on 4.6+ [S8].",
            "sonnet-5": "Thinking triggering is steerable by prompt on Sonnet 5 (\"When in doubt, respond directly\") [S45]; a blanket ban is unnecessary and `thinking: disabled` makes the model less likely to use tools [S45].",
            "*": "Thinking is off by default on this model [S16]; the rule is a no-op. Prefer adaptive/extended thinking where the guide recommends it [S8, S51].",
        },
        "fix": {"*": "Delete the line. Control cost with a lower effort level instead [S1, S14]."},
        "action": "delete-line",
    },
    {
        "rule": "R4-forced-status-scaffolding",
        "rx": re.compile(r"(after every \d+ (tool calls?|steps?)|every \d+ (tool calls?|steps?),? (summari[sz]e|report)|summari[sz]e (your )?progress (after|every))", re.I),
        "sev": {"opus-5": "warning", "fable-5": "info", "opus-4x": "warning", "sonnet-5": "warning", "sonnet-4x": "info", "haiku": "info", "generic": "info"},
        "why": {
            "opus-5": "Opus 4.7/4.8/5 give regular progress updates on their own; forced interim-status scaffolding should be removed [S2, S9].",
            "fable-5": "Fable 5.1 writes fewer user-facing updates by default and Anthropic says to ask for them explicitly [S4]; a cadence line is not harmful here.",
            "opus-4x": "Opus 4.7/4.8 provide regular, higher-quality updates; \"If you've added scaffolding to force interim status messages … try removing it\" [S2, S9].",
            "sonnet-5": "Sonnet 5 provides regular updates; \"If you've added scaffolding to force interim status messages … try removing it\" [S45].",
            "*": "No official statement for this model; the removal advice is documented for Opus 4.7/4.8/5 and Sonnet 5 only [S2, S9, S45]. Reported for information.",
        },
        "fix": {"*": "Delete; describe the desired cadence in one sentence instead [S1, S45]."},
        "action": "delete-line",
    },
    {
        "rule": "R5-word-cap",
        "rx": re.compile(r"\b(under|max(imum)?|no more than|at most|limit(ed)? to|fewer than|less than) \d{2,4} words\b", re.I),
        "sev": {t: "info" for t in TIERS},
        "why": {"*": "Community reports word ceilings decay over a session while ordering rules ('lead with the outcome') hold (COMMUNITY.md §2, C13/C14). Official guidance is a short conciseness instruction plus an end-of-prompt reminder [S1]."},
        "fix": {"*": "Replace with: 'Lead with the outcome in one sentence; supporting detail after.' and keep the harness Stop gate on."},
        "action": "none",
    },
    {
        "rule": "R6-fable-anti-formatting",
        "rx": re.compile(r"\b(no|never use|don'?t use|avoid) (bullets?|bullet points|headers?|headings|bold|markdown)\b", re.I),
        "sev": {"fable-5": "warning", "opus-5": "info", "opus-4x": "info", "sonnet-5": "info", "sonnet-4x": "info", "haiku": "info", "generic": "info"},
        "why": {"fable-5": "Fable 5.1 already uses less formatting; anti-formatting rules written for earlier models suppress structure the content needs [S4, S8].",
                "*": "Harmless here; Anthropic's cross-model guidance even offers a minimize-markdown block [S8]. Remove it only when the file is also loaded by Fable 5.1 [S4]."},
        "fix": {"fable-5": "Remove when running Fable 5.1, or replace with a rule that says when formatting is appropriate [S4].", "*": "Keep."},
        "action": "delete-line",
    },
    {
        "rule": "R7-fable-hold-findings",
        "rx": re.compile(r"(hold (all )?(findings|updates)|no progress updates|do not (narrate|give updates)|only report at the end)", re.I),
        "sev": {"fable-5": "warning", "opus-5": "info", "opus-4x": "info", "sonnet-5": "info", "sonnet-4x": "info", "haiku": "info", "generic": "info"},
        "why": {"fable-5": "Fable 5.1 writes fewer user-facing updates by default; remove lines that suppress narration before adding anything [S4].",
                "opus-5": "Opus 5 narrates progress more than prior models [S1, S3]; a line limiting narration is a legitimate length control here, but it silences Fable 5.1 [S4].",
                "*": "Harmless on this model; it silences Fable 5.1 if the file is shared [S4]."},
        "fix": {"fable-5": "Delete; ask for brief updates explicitly instead [S4].", "*": "Keep unless the file is shared with Fable 5.1 sessions."},
        "action": "delete-line",
    },
]

CONCISE_RX = re.compile(r"(concise|brief|short (answers|responses|replies)|lead with the outcome|keep (responses|answers|output) (focused|short))", re.I)
SCOPE_RX = re.compile(r"(deliver what was asked|scope intended|only (make )?changes (that are )?(directly )?requested|don'?t add features|avoid over-?engineering|stop short of actions)", re.I)

CONCISE_BLOCK = (
    "\n<!-- added by claude-model-harness doctor [S1] -->\n"
    "Keep responses focused, brief, and concise. Keep disclaimers and caveats short, and spend most of the response on the main answer. "
    "When you finish a task, lead with the outcome: the first sentence answers \"what happened\", supporting detail after.\n"
)
CONCISE_BLOCK_4X = (
    "\n<!-- added by claude-model-harness doctor [S9, S45] -->\n"
    "Provide concise, focused responses. Skip non-essential context, and keep examples minimal.\n"
)
SCOPE_BLOCK = (
    "\n<!-- added by claude-model-harness doctor [S1] -->\n"
    "Deliver what was asked, at the scope intended. Make routine judgment calls yourself, and check in only when different readings of the request "
    "would lead to materially different work. If the request seems mistaken or a better approach exists, say so in a sentence and continue with the task "
    "as asked rather than quietly narrowing, widening, or transforming it. Finish the whole task, and stop short of actions that are clearly beyond what was asked.\n"
)
SCOPE_BLOCK_4X = (
    "\n<!-- added by claude-model-harness doctor [S8] -->\n"
    "Avoid over-engineering. Only make changes that are directly requested or clearly necessary. Don't add features, refactor code, or make \"improvements\" beyond what was asked.\n"
)
REMINDER_BLOCK = "\n<tone_preference>\nKeep outputs reasonably concise.\n</tone_preference>\n"

# Non-line rules, documented for `explain` (their logic lives in scan_settings / scan_missing / scan_duplicates).
OTHER_RULES: dict[str, dict[str, Any]] = {
    "R8-long-prompt-no-reminder": {"what": "CLAUDE.md of >= 80 lines with no conciseness line in its last 12 lines",
        "sev": {"opus-5": "warning", "*": "info"},
        "why": {"opus-5": "In a long system prompt, pair the conciseness instruction with a short reminder near the end [S1].", "*": "The end-of-prompt reminder is documented for Opus 5 [S1]; informational elsewhere."}},
    "R9-duplicate-instruction": {"what": "the same instruction line in two files", "sev": {"*": "warning"},
        "why": {"*": "Duplicates add tokens and, when they diverge, cause deliberation (community, COMMUNITY.md)."}},
    "R10-settings-unparseable": {"what": "settings.json is not valid JSON", "sev": {"*": "error"}, "why": {"*": "Claude Code will reject it [S27]."}},
    "R11-thinking-disabled": {"what": "env.MAX_THINKING_TOKENS=0 or CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING in settings",
        "sev": {"opus-5": "warning (error with effort xhigh/max)", "fable-5": "info", "opus-4x": "info", "sonnet-5": "warning", "sonnet-4x": "info", "haiku": "info", "generic": "warning"},
        "why": {"opus-5": "Thinking disabled on Opus 5: tool calls can be emitted as plain text and internal XML tags can leak [S1, S15, S16]; with effort xhigh/max every request returns HTTP 400 [S2, S14].",
                "fable-5": "MAX_THINKING_TOKENS=0 has no effect on Fable 5 / 5.1 (thinking is always on) [S28, S6].",
                "opus-4x": "Thinking is off by default on Opus 4.6–4.8 [S16], so this only restates the default; adaptive thinking is recommended for agentic work [S8].",
                "sonnet-5": "\"With thinking disabled, the model is less likely to reach for tools or consider searching\" [S45]; prefer thinking on at a lower effort [S8].",
                "sonnet-4x": "Thinking is off by default on Sonnet 4.6 / 4.5 [S16]; restates the default.",
                "haiku": "Thinking is off by default on Haiku 4.5 [S16]; Anthropic suggests enabling extended thinking for significant gains on coding and reasoning [S51].",
                "*": "Model unknown; on Opus 5 this causes tool-call leakage [S1, S16]."}},
    "R12-effort-invalid": {"what": "CLAUDE_CODE_EFFORT_LEVEL not in low/medium/high/xhigh/max", "sev": {"*": "warning"}, "why": {"*": "Valid levels are low, medium, high, xhigh, max [S28]."}},
    "R13-effort-high-routine": {"what": "CLAUDE_CODE_EFFORT_LEVEL=xhigh|max on Opus 5", "sev": {"opus-5": "info", "*": "none"},
        "why": {"opus-5": "xhigh/max is for demanding coding; 'use low and medium liberally … wherever quality holds' [S14]. Community: medium reported better-scoped work (COMMUNITY.md §2).",
                "*": "Not raised: xhigh is the recommended start for Opus 4.7/4.8 coding [S14] and for the hardest Sonnet 5 tasks [S45]."}},
    "R14-no-subagent-cap": {"what": "no CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS / _SPAWN_DEPTH in settings env",
        "sev": {"opus-5": "info", "opus-4x": "info (Opus 4.6 only)", "*": "none"},
        "why": {"opus-5": "Opus 5 delegates to subagents more readily; deterministic caps need Claude Code >= 2.1.217 [S1].",
                "opus-4x": "Opus 4.6 has a strong predilection for subagents [S8]; Opus 4.7/4.8 spawn fewer by default [S2, S9], so it is raised only for 4.6.",
                "*": "No over-delegation statement for this model."}},
    "R15-missing-conciseness": {"what": "no conciseness instruction in any scanned file",
        "sev": {"opus-5": "warning", "opus-4x": "info", "sonnet-5": "info", "*": "none"},
        "why": {"opus-5": "Opus 5 default responses run longer and effort does not shorten them; 'To control response length, prompt for it explicitly' [S1, S2].",
                "opus-4x": "Opus 4.7/4.8 calibrate length to the task; add the concise line only if your product needs it [S9].",
                "sonnet-5": "Sonnet 5 calibrates length to the task; add the concise line only if your product needs it [S45].",
                "*": "No length statement for this model."}},
    "R16-missing-scope": {"what": "no scope-constraint instruction in any scanned file",
        "sev": {"opus-5": "info", "fable-5": "info", "opus-4x": "info", "*": "none"},
        "why": {"opus-5": "Opus 5 can expand task scope; 'For narrow tasks, constrain scope explicitly' [S1].",
                "fable-5": "Fable 5.1 delivers what's asked for and sometimes more; an explicit 'keep changes to what the task asks for' instruction drops unrequested additions with no measurable change in task success [S4].",
                "opus-4x": "Opus 4.5/4.6 tend to over-engineer (extra files, abstractions) [S8].",
                "*": "Sonnet 5 does not infer requests you didn't make [S45]; no statement for the others."}},
    "R17-effort-unsupported": {"what": "CLAUDE_CODE_EFFORT_LEVEL set to a level the detected model does not support",
        "sev": {"*": "info"},
        "why": {"*": "Claude Code falls back to the highest supported level at or below the one you set (xhigh runs as high on Opus 4.6 / Sonnet 4.6); Haiku 4.5, Sonnet 4.5 and Opus 4.5 are not listed, so effort has no effect [S28]."}},
}

NEGATION = re.compile(r"\b(do not|don'?t|never|no need to|without|not required|avoid|instead of|rather than|no additional|none should)\b", re.I)


def _negated(line: str, pos: int) -> bool:
    """True when the matched phrase is itself negated ('do not ... double-check'), e.g. the official
    Opus 5 subagent prompt [S1]. Such lines are not verification instructions."""
    return bool(NEGATION.search(line[max(0, pos - 80):pos]))


def instruction_files(project: Path, home: Path) -> list[Path]:
    cands: list[Path] = [
        home / "CLAUDE.md", project / "CLAUDE.md", project / ".claude" / "CLAUDE.md", project / "CLAUDE.local.md",
    ]
    for base in (home / "rules", project / ".claude" / "rules"):
        if base.is_dir():
            cands += sorted(base.rglob("*.md"))
    for base in (home / "skills", project / ".claude" / "skills"):
        if base.is_dir():
            cands += sorted(base.glob("*/SKILL.md"))
    seen, out = set(), []
    for p in cands:
        try:
            rp = p.resolve()
        except Exception:
            continue
        if rp in seen or not p.is_file():
            continue
        seen.add(rp)
        out.append(p)
    return out


def settings_files(project: Path, home: Path) -> list[Path]:
    return [p for p in (home / "settings.json", project / ".claude" / "settings.json",
                        project / ".claude" / "settings.local.json") if p.is_file()]


def _sev(rule: dict[str, Any], profile: str) -> str:
    return rule["sev"].get(profile, rule["sev"].get("generic", "info"))


def _tier(profile: str | None) -> str:
    return profile if profile in TIERS else "generic"


def scan_file(p: Path, profile: str, min_lines_for_reminder: int = 80) -> list[Finding]:
    tier = _tier(profile)
    out: list[Finding] = []
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        config.log("doctor_read_error", path=str(p), error=repr(e))
        return out
    lines = text.splitlines()
    in_code = False
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or line.lstrip().startswith("<!--"):
            continue
        for r in LINE_RULES:
            m = r["rx"].search(line)
            if m and not _negated(line, m.start()):
                out.append(Finding(r["rule"], _sev(r, tier), str(p), i, line.strip()[:160],
                                   _pick(r["why"], tier), _pick(r["fix"], tier), _pick(r["action"], tier)))
    # R8 long prompt without end-of-prompt reminder (main CLAUDE.md files only)
    if p.name in ("CLAUDE.md", "CLAUDE.local.md") and len(lines) >= min_lines_for_reminder:
        tail = "\n".join(lines[-12:])
        if not CONCISE_RX.search(tail):
            meta = OTHER_RULES["R8-long-prompt-no-reminder"]
            out.append(Finding("R8-long-prompt-no-reminder", "warning" if tier == "opus-5" else "info", str(p), len(lines),
                               f"{len(lines)} lines, no conciseness reminder in the last 12 lines",
                               _pick(meta["why"], tier), "Append a <tone_preference> reminder block [S1].", "append-block", REMINDER_BLOCK))
    return out


def scan_duplicates(files: list[Path]) -> list[Finding]:
    seen: dict[str, tuple[str, int]] = {}
    out: list[Finding] = []
    for p in files:
        try:
            in_code = False
            in_front = False
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if i == 1 and line.strip() == "---":          # YAML frontmatter (SKILL.md, rules with `paths:`) [S31, S32]
                    in_front = True
                    continue
                if in_front:
                    if line.strip() == "---":
                        in_front = False
                    continue
                if line.strip().startswith("```"):
                    in_code = not in_code
                    continue
                norm = re.sub(r"\s+", " ", line.strip().lower())
                if in_code or len(norm) < 25 or norm.endswith(":") or norm.startswith(("#", "-", "*", "```", "<", "|", "echo ", "$", "export ", "if ", "fi", "}")) or "{" in norm:
                    continue
                key = norm.rstrip(".")
                if key in seen and (seen[key][0], seen[key][1]) != (str(p), i):
                    out.append(Finding("R9-duplicate-instruction", "warning", str(p), i, line.strip()[:160],
                                       f"Same instruction also in {seen[key][0]}:{seen[key][1]}. Duplicates add tokens and, when they diverge, cause deliberation (community: 'conflicting rules cause excessive deliberation', COMMUNITY.md).",
                                       "Keep one copy.", "delete-line"))
                else:
                    seen.setdefault(key, (str(p), i))
        except Exception:
            continue
    return out


def _supported_efforts_cc(model_id: str | None) -> tuple[str, ...] | None:
    """Effort levels Claude Code offers for a model id [S28]; None when the model is unknown."""
    if not model_id:
        return None
    m = model_id.lower()
    if re.search(r"claude-(fable|mythos)-|claude-opus-5(?!-)|claude-sonnet-5(?!-)|claude-opus-4-[78]", m):
        return ("low", "medium", "high", "xhigh", "max")
    if re.search(r"claude-opus-4-6|claude-sonnet-4-6", m):
        return ("low", "medium", "high", "max")
    if re.search(r"claude-haiku-|claude-sonnet-4-5|claude-opus-4-5|claude-opus-4-1|claude-opus-4(?!-)|claude-sonnet-4(?!-)", m):
        return ()
    return None


def scan_settings(files: list[Path], profile: str, model_id: str | None = None) -> list[Finding]:
    tier = _tier(profile)
    out: list[Finding] = []
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            out.append(Finding("R10-settings-unparseable", "error", str(p), None, "", f"settings.json is not valid JSON ({e}); Claude Code will reject it [S27].", "Fix the JSON.", "none"))
            continue
        env = data.get("env") if isinstance(data.get("env"), dict) else {}
        mtt = str(env.get("MAX_THINKING_TOKENS", "")).strip()
        effort = str(env.get("CLAUDE_CODE_EFFORT_LEVEL", "")).strip().lower()
        thinking_off = mtt == "0" or str(env.get("CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING", "")).lower() in ("1", "true")
        if thinking_off:
            meta = OTHER_RULES["R11-thinking-disabled"]
            why = _pick(meta["why"], tier)
            if tier == "opus-5":
                sev = "error" if effort in ("xhigh", "max") else "warning"
                why = ("Thinking disabled on Opus 5: tool calls can be emitted as plain text and internal XML tags can leak [S1, S15, S16]"
                       + ("; combined with effort xhigh/max every request returns HTTP 400 [S2, S14]." if effort in ("xhigh", "max") else
                          ". Keep thinking on and lower effort instead — 'thinking enabled at low effort performs better than thinking disabled at similar cost' [S1]."))
                fix = "Remove MAX_THINKING_TOKENS=0 / CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING; set CLAUDE_CODE_EFFORT_LEVEL=medium or low [S28]."
            elif tier in ("sonnet-5", "generic"):
                sev, fix = "warning", "Remove the setting; keep thinking on and lower effort instead [S8, S45]."
            elif tier == "fable-5":
                sev, fix = "info", "Remove the dead setting."
            elif tier == "haiku":
                sev, fix = "info", "Consider enabling extended thinking for coding and reasoning tasks [S51]."
            else:
                sev, fix = "info", "Optional: enable adaptive thinking for agentic work [S8]."
            out.append(Finding("R11-thinking-disabled", sev, str(p), None, f"env.MAX_THINKING_TOKENS={mtt or 'n/a'}", why, fix, "none"))
        if effort and effort not in ("low", "medium", "high", "xhigh", "max"):
            out.append(Finding("R12-effort-invalid", "warning", str(p), None, f"CLAUDE_CODE_EFFORT_LEVEL={effort}", "Valid levels are low, medium, high, xhigh, max [S28].", "Fix the value.", "none"))
        if tier == "opus-5" and effort in ("xhigh", "max"):
            out.append(Finding("R13-effort-high-routine", "info", str(p), None, f"CLAUDE_CODE_EFFORT_LEVEL={effort}", _pick(OTHER_RULES["R13-effort-high-routine"]["why"], tier), "Consider medium for routine chunks; see /chunk.", "none"))
        if effort in ("low", "medium", "high", "xhigh", "max"):
            allowed = _supported_efforts_cc(model_id)
            if allowed is not None and effort not in allowed:
                what = (f"{model_id} does not support the effort parameter in Claude Code; the setting has no effect [S28]." if not allowed
                        else f"{model_id} supports {', '.join(allowed)}; Claude Code runs '{effort}' as the highest supported level at or below it [S28].")
                out.append(Finding("R17-effort-unsupported", "info", str(p), None, f"CLAUDE_CODE_EFFORT_LEVEL={effort}", what, "Remove the setting or pick a supported level [S28].", "none"))
        no_cap = "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS" not in env and "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH" not in env
        if no_cap and tier == "opus-5":
            out.append(Finding("R14-no-subagent-cap", "info", str(p), None, "", "Opus 5 delegates to subagents more readily; deterministic caps are CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH / CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS (Claude Code >= 2.1.217) [S1].", "Add to settings env, e.g. \"CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS\": \"2\".", "none"))
        elif no_cap and tier == "opus-4x" and model_id and "opus-4-6" in model_id.lower():
            out.append(Finding("R14-no-subagent-cap", "info", str(p), None, "", "Opus 4.6 has a strong predilection for subagents and may spawn them where a direct approach would suffice [S8].", "Add a cap to settings env, e.g. \"CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS\": \"2\" [S1].", "none"))
    return out


def scan_missing(files: list[Path], profile: str, project: Path) -> list[Finding]:
    tier = _tier(profile)
    out: list[Finding] = []
    blob = ""
    for p in files:
        try:
            blob += p.read_text(encoding="utf-8", errors="replace") + "\n"
        except Exception:
            pass
    target = next((p for p in (project / "CLAUDE.md", project / ".claude" / "CLAUDE.md") if p.is_file()), project / "CLAUDE.md")
    if not CONCISE_RX.search(blob):
        if tier == "opus-5":
            out.append(Finding("R15-missing-conciseness", "warning", str(target), None, "", _pick(OTHER_RULES["R15-missing-conciseness"]["why"], tier), "Append the official conciseness instruction [S1].", "append-block", CONCISE_BLOCK))
        elif tier in ("opus-4x", "sonnet-5"):
            out.append(Finding("R15-missing-conciseness", "info", str(target), None, "", _pick(OTHER_RULES["R15-missing-conciseness"]["why"], tier), "Optional: append the official concise line [S9, S45].", "append-block", CONCISE_BLOCK_4X))
    if not SCOPE_RX.search(blob):
        if tier == "opus-5":
            out.append(Finding("R16-missing-scope", "info", str(target), None, "", _pick(OTHER_RULES["R16-missing-scope"]["why"], tier), "Append the official scope instruction [S1].", "append-block", SCOPE_BLOCK))
        elif tier == "fable-5":
            out.append(Finding("R16-missing-scope", "info", str(target), None, "", _pick(OTHER_RULES["R16-missing-scope"]["why"], tier), "Append the 'Keep changes and tests to what the task asks for' instruction [S4] (the harness profile already injects it).", "none"))
        elif tier == "opus-4x":
            out.append(Finding("R16-missing-scope", "info", str(target), None, "", _pick(OTHER_RULES["R16-missing-scope"]["why"], tier), "Optional: append the official over-engineering block [S8].", "append-block", SCOPE_BLOCK_4X))
    return out


def run(project: Path | None = None, home: Path | None = None, profile: str = "generic", model_id: str | None = None) -> list[Finding]:
    project = project or config.project_dir()
    home = home or config._home()
    files = instruction_files(project, home)
    findings: list[Finding] = []
    for p in files:
        findings += scan_file(p, profile)
    findings += scan_duplicates(files)
    findings += scan_settings(settings_files(project, home), profile, model_id)
    findings += scan_missing(files, profile, project)
    findings.sort(key=lambda f: (SEV_ORDER.get(f.severity, 9), f.file, f.line or 0))
    return findings


# ------------------------------------------------------------------ explain
def rule_ids() -> list[str]:
    return [r["rule"] for r in LINE_RULES] + list(OTHER_RULES)


def explain(rule: str) -> str:
    """Cited reasoning for one rule, per tier. Accepts 'R1' or the full id."""
    key = rule.strip()
    match = next((r for r in rule_ids() if r == key or r.split("-", 1)[0].lower() == key.lower()), None)
    if not match:
        return f"unknown rule '{rule}'. Rules: " + ", ".join(rule_ids())
    lines = [f"{match}"]
    line_rule = next((r for r in LINE_RULES if r["rule"] == match), None)
    if line_rule:
        lines.append(f"  matches (regex, case-insensitive): {line_rule['rx'].pattern}")
        lines.append("  apply: only error/warning findings whose action is delete-line are edited; info is never edited")
        for t in TIERS:
            lines.append(f"  {t:9} {_sev(line_rule, t):8} {_pick(line_rule['why'], t)}")
            lines.append(f"  {'':9} {'fix:':8} {_pick(line_rule['fix'], t)}  [apply: {_pick(line_rule['action'], t)}]")
    else:
        meta = OTHER_RULES[match]
        lines.append(f"  checks: {meta['what']}")
        for t in TIERS:
            lines.append(f"  {t:9} {_pick(meta['sev'], t):8} {_pick(meta['why'], t)}")
    lines.append("  sources: [S#] -> research/SOURCES.md; tier facts -> research/MODEL_MATRIX.md")
    return "\n".join(lines)


# ------------------------------------------------------------------ apply
def _read_raw(p: Path) -> str:
    # newline="" keeps CRLF/LF exactly as on disk so apply() never rewrites a user's line endings
    with p.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        return fh.read()


def planned_edits(findings: list[Finding], mode: str = "delete") -> dict[str, tuple[str, str]]:
    """Return {file: (before, after)} for line-level and append-block findings. mode: delete|move.
    Only error/warning findings are edited; info findings are reported, never changed."""
    edits: dict[str, tuple[str, str]] = {}
    by_file: dict[str, list[Finding]] = {}
    for f in findings:
        if f.action in ("delete-line", "append-block") and f.severity in ("error", "warning"):
            by_file.setdefault(f.file, []).append(f)
    for file, fs in by_file.items():
        p = Path(file)
        try:
            before = _read_raw(p) if p.is_file() else ""
        except Exception:
            continue
        nl = "\r\n" if "\r\n" in before else "\n"
        lines = before.splitlines(keepends=True)
        removed: list[str] = []
        drop = {f.line for f in fs if f.action == "delete-line" and f.line}
        new_lines = []
        for i, l in enumerate(lines, 1):
            if i in drop:
                removed.append(l.rstrip("\r\n"))
            else:
                new_lines.append(l)
        after = "".join(new_lines)
        for f in fs:
            if f.action == "append-block" and f.payload and f.payload.strip() not in after:
                after = after.rstrip("\r\n") + nl + f.payload.replace("\n", nl)
        if mode == "move" and removed:
            keep = Path(config.project_dir()) / ".claude" / "harness" / "removed-instructions.md"
            cur = _read_raw(keep) if keep.is_file() else ""
            edits[str(keep)] = (cur, (cur or "# Lines removed by harness doctor (not loaded by Claude Code)\n") + f"\n## from {file}\n" + "\n".join(removed) + "\n")
        if after != before:
            edits[file] = (before, after)
    return edits


def unified_diff(edits: dict[str, tuple[str, str]]) -> str:
    out = []
    for file, (before, after) in edits.items():
        out.append("".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile=file, tofile=file + " (proposed)")))
    return "\n".join(o for o in out if o)


def apply(edits: dict[str, tuple[str, str]]) -> list[str]:
    written = []
    for file, (before, after) in edits.items():
        p = Path(file)
        try:
            if p.is_file():
                cur = _read_raw(p)
                if cur != before:
                    config.log("doctor_apply_skipped_changed", file=file)
                    continue
                bak = p.with_suffix(p.suffix + ".harness.bak")
                with bak.open("w", encoding="utf-8", newline="") as fh:
                    fh.write(before)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("w", encoding="utf-8", newline="") as fh:
                fh.write(after)
            written.append(file)
        except Exception as e:
            config.log("doctor_apply_error", file=file, error=repr(e))
    return written


def render(findings: list[Finding], profile: str, model_line: str = "") -> str:
    lines = [f"harness doctor — profile: {profile}" + (f" — {model_line}" if model_line else "")]
    if not findings:
        lines.append("No findings.")
        return "\n".join(lines)
    counts = {s: sum(1 for f in findings if f.severity == s) for s in ("error", "warning", "info")}
    lines.append(f"{counts['error']} error(s), {counts['warning']} warning(s), {counts['info']} info")
    for f in findings:
        loc = f"{f.file}:{f.line}" if f.line else f.file
        lines.append(f"\n[{f.severity.upper()}] {f.rule}  {loc}")
        if f.text:
            lines.append(f"  > {f.text}")
        lines.append(f"  why: {f.why}")
        lines.append(f"  fix: {f.fix}")
    lines.append("\n(`doctor --explain <rule>` prints the per-tier reasoning with sources.)")
    return "\n".join(lines)

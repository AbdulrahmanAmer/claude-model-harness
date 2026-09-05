"""Completion gate for the Stop hook.

Input : Stop hook stdin JSON — `session_id`, `prompt_id`, `transcript_path`, `stop_hook_active`,
        `last_assistant_message`, `effort.level` (all documented) [src: S20, S21, S37]
Output: {"decision": "block", "reason": "..."} (top-level; documented) [src: S21]
        or {} / {"systemMessage": "..."} to allow.

Rules (all deterministic — community evidence says only mechanical gates hold, COMMUNITY.md §2):
  G1 phantom tool call : tool-call-shaped text in the assistant message           -> block
  G2 completion claim without evidence: "done/fixed/tests pass" but no test/build/lint
     tool call with observed output, nor a diff/status, in this turn              -> block
  G3 weak/rigged evidence only (`|| true`, `-k`, "0 tests", checkout main ...)     -> block once
  G4 acceptance failed in output (N failed / FAIL) but message claims success      -> block
  G5 completion format missing (outcome · ≤3 bullets · verification · blockers)  -> block
  G6 chunk mode: claim of done for the active chunk needs its acceptance command   -> block
  G7 grounding (per-tier, `gate.grounding`): a factual claim about an existing project file that no
     Read/Grep/Glob/Edit/Write/Bash call touched this turn -> block once: "read the file, then answer"
     ("Never speculate about code you have not opened" [src: S8]; off on opus-5 / fable-5 [src: S1, S28])
  Cap: at most `gate.max_blocks_per_prompt` (default 2) blocks per prompt; then allow with a
       visible warning. `stop_hook_active` true + cap reached -> always allow. Claude Code's own
       hard cap is 8 consecutive blocks [src: S21].
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from . import chunks as chunkmod
from . import config, tics, transcript

# sentence splitter and file-reference finder for G7
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
FILE_REF = re.compile(r"`?(?P<path>(?:[\w][\w.-]*[\\/])*[\w][\w.-]*\.(?P<ext>[A-Za-z0-9]{1,6}))(?::\d+)?`?")
READ_TOOLS = ("Read", "Grep", "Glob", "Edit", "MultiEdit", "Write", "NotebookEdit")


def _touched_files(calls: list[dict[str, Any]]) -> tuple[set[str], str]:
    """Basenames of files any tool call touched this turn, plus the concatenated Bash command text."""
    names: set[str] = set()
    bash_text: list[str] = []
    for c in calls:
        name = c.get("name", "")
        inp = c.get("input") or {}
        if name in READ_TOOLS:
            for key in ("file_path", "path", "pattern", "notebook_path"):
                v = inp.get(key)
                if isinstance(v, str) and v:
                    names.add(os.path.basename(v.replace("\\", "/")).lower())
        elif name == "Bash":
            bash_text.append(str(inp.get("command", "")))
    return names, "\n".join(bash_text).lower()


def check_grounding(text: str, calls: list[dict[str, Any]], cfg: dict[str, Any], project: Path | None = None) -> list[str]:
    """G7. Returns descriptions of ungrounded claims: sentences that (a) name an existing project file,
    (b) contain a claim verb, and (c) have no tool call touching that file in this turn."""
    if cfg.get("gate.grounding", "off") != "block" or not text:
        return []
    try:
        proj = (project or config.project_dir()).resolve()
        exts = {e.lower() for e in cfg.get("gate.grounding_extensions", [])}
        claim_pats = _compile(cfg.get("gate.grounding_claim_patterns", []))
        touched, bash_text = _touched_files(calls)
        out: list[str] = []
        seen: set[str] = set()
        for sent in SENTENCE_SPLIT.split(text):
            if not sent.strip() or not _any(claim_pats, sent):
                continue
            for m in FILE_REF.finditer(sent):
                path, ext = m.group("path"), m.group("ext").lower()
                if ext not in exts:
                    continue
                base = os.path.basename(path.replace("\\", "/")).lower()
                if base in seen or base in touched or base in bash_text:
                    continue
                cand = Path(path)
                exists = (cand.is_absolute() and cand.is_file()) or (proj / path).is_file() or any(True for _ in proj.rglob(base)) if len(base) > 3 else False
                if not exists:
                    continue
                seen.add(base)
                out.append(f"'{sent.strip()[:140]}' (about {path})")
        return out
    except Exception as e:  # fail open
        config.log("grounding_error", error=repr(e))
        return []

FAIL_TOKENS = re.compile(r"\b([1-9]\d*) (failed|errors?|failures?)\b|\bFAILED\b|\bBUILD FAILED\b|\bTraceback \(most recent call last\)", re.I)
BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+\S")
VERIFICATION_LINE = re.compile(r"^\s*(?:\*\*|__)?\s*verification\s*(?:result)?\s*(?:\*\*|__)?\s*[:·—–-]", re.I | re.M)
BLOCKERS_LINE = re.compile(r"^\s*(?:\*\*|__)?\s*blockers?\s*(?:\*\*|__)?\s*[:·—–-]", re.I | re.M)

FORMAT_HELP = ("Restate your final message in this format only: "
               "1) one-sentence outcome; 2) up to 3 bullets of changes; "
               "3) a line starting 'Verification:' naming the exact command you ran and its observed result; "
               "4) a line starting 'Blockers:' (write 'none' if none).")


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    out = []
    for p in patterns:
        try:
            out.append(re.compile(p, re.I | re.M))
        except re.error:
            config.log("bad_pattern", pattern=p)
    return out


def _any(pats: list[re.Pattern[str]], text: str) -> str | None:
    for p in pats:
        m = p.search(text or "")
        if m:
            return m.group(0)
    return None


def classify_evidence(calls: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    ev_cmd = _compile(cfg["gate.evidence_commands"])
    res_pat = _compile(cfg["gate.result_patterns"])
    weak_pat = _compile(cfg["gate.weak_evidence_patterns"])
    strong: list[str] = []
    weak: list[str] = []
    failed: list[str] = []
    edits = 0
    for c in calls:
        name = c.get("name", "")
        inp = c.get("input") or {}
        if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            edits += 1
            continue
        if name != "Bash":
            continue
        cmd = str(inp.get("command", ""))
        if not _any(ev_cmd, cmd):
            continue
        result = c.get("result") or ""
        weak_hit = _any(weak_pat, cmd) or _any(weak_pat, result)
        has_result = bool(_any(res_pat, result))
        if FAIL_TOKENS.search(result):
            failed.append(cmd[:120])
            continue
        if weak_hit:
            weak.append(f"{cmd[:80]}  [{weak_hit}]")
        elif has_result:
            strong.append(cmd[:120])
        else:
            weak.append(f"{cmd[:80]}  [no observable result in output]")
    return {"strong": strong, "weak": weak, "failed": failed, "edits": edits}


def check_format(text: str, cfg: dict[str, Any]) -> list[str]:
    problems = []
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return ["empty message"]
    bullets = sum(1 for l in lines if BULLET.match(l))
    if bullets > int(cfg["gate.max_bullets"]):
        problems.append(f"{bullets} bullets (max {cfg['gate.max_bullets']})")
    if not VERIFICATION_LINE.search(text):
        problems.append("no 'Verification:' line")
    if not BLOCKERS_LINE.search(text):
        problems.append("no 'Blockers:' line")
    return problems


def evaluate(hook_input: dict[str, Any], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure decision function. Returns the JSON object to print (may be {}).
    When `cfg` is not given, the tier is detected from the hook input (SessionStart cache, transcript, ...)
    and its TIER_DEFAULTS are applied [research/MODEL_MATRIX.md]."""
    if cfg is None:
        from . import detect_model
        cfg = config.load_config(detect_model.detect(hook_input)["profile"])
    if not cfg.get("gate.enabled", True):
        return {}
    session_id = str(hook_input.get("session_id") or "unknown")
    prompt_id = str(hook_input.get("prompt_id") or "no-prompt-id")
    state = config.load_state(session_id)
    attempts = state.get("gate_attempts", {})
    n = int(attempts.get(prompt_id, 0))
    cap = int(cfg["gate.max_blocks_per_prompt"])

    text = hook_input.get("last_assistant_message")
    entries = transcript.read_entries(hook_input.get("transcript_path"))
    turn = transcript.current_turn(entries)
    if not isinstance(text, str) or not text.strip():
        text = transcript.last_assistant_text(turn)  # fallback: may lag [S20]
    text = text or ""

    reasons: list[str] = []
    warnings: list[str] = []

    # G1 phantom tool calls
    phantom = _any(_compile(cfg["gate.phantom_patterns"]), text)
    if phantom:
        reasons.append(f"Your message contains tool-call-shaped text ({phantom.strip()[:40]}...) but no tool was actually "
                       "invoked. That call never ran. Issue it as a real tool call now, then report the observed result.")

    # completion claim?
    claim = _any(_compile(cfg["gate.completion_patterns"]), text)
    calls = transcript.tool_calls(turn)
    ev = classify_evidence(calls, cfg)
    active = chunkmod.active_chunk(chunkmod.load())

    if claim:
        # G4 evidence shows failure
        if ev["failed"] and not ev["strong"]:
            reasons.append("You claim completion but the last verification output shows failures "
                           f"({ev['failed'][0]}). Report the failure under 'Blockers:' instead of claiming done, or fix it and re-run.")
        # G2 no evidence
        elif not ev["strong"] and not ev["weak"]:
            hint = ("You edited files but ran no test/build/lint/diff command in this turn."
                    if ev["edits"] else "No test, build, lint, or diff command ran in this turn.")
            reasons.append(f"You state '{claim.strip()}' but there is no evidence in this session. {hint} "
                           "Run the relevant test/build/lint command (or `git diff --stat`) as a real tool call and quote its "
                           "observed result under 'Verification:'. If you cannot verify, say so plainly under 'Blockers:' and do not claim completion.")
        # G3 weak only
        elif not ev["strong"] and ev["weak"] and n < 1:
            reasons.append("The only verification evidence looks narrowed or unfalsifiable: " + "; ".join(ev["weak"][:2]) +
                           ". Run the full check without `|| true`, filters, or branch switching, or state under 'Blockers:' why the full check cannot run.")
        # G6 chunk acceptance
        if active and cfg.get("chunk.require_acceptance", True):
            acc = [a for a in active.get("acceptance", []) if a]
            ran = [c for c in calls if c.get("name") == "Bash" and any(a.split()[0] in str((c.get("input") or {}).get("command", "")) and a in str((c.get("input") or {}).get("command", "")) for a in acc)]
            if acc and not ran:
                reasons.append(f"Chunk {active.get('id')} is active; its acceptance command(s) {acc} did not run this turn. "
                               "Run them as real tool calls and quote the result, or report 'Blockers:'.")
            elif ran and any(FAIL_TOKENS.search(c.get("result") or "") for c in ran):
                reasons.append(f"Chunk {active.get('id')} acceptance ran but shows failures. Do not claim the chunk done; report under 'Blockers:'.")
        # G5 format
        if cfg.get("gate.require_format", True) and not reasons:
            probs = check_format(text, cfg)
            if probs:
                reasons.append("Completion format missing: " + ", ".join(probs) + ". " + FORMAT_HELP)

    # G7 grounding (independent of a completion claim; once per prompt; per-tier default)
    if not reasons and n < 1:
        ungrounded = check_grounding(text, calls, cfg)
        if ungrounded:
            reasons.append("You make a claim about a file you did not open in this turn: " + "; ".join(ungrounded[:2]) +
                           ". Read the file (Read/Grep) as a real tool call, then answer; if you cannot, say 'could not verify' "
                           "instead of stating it. (Never speculate about code you have not opened.)")

    # tics on the final message
    mode = cfg.get("tics.stop_mode", "warn")
    if mode in ("warn", "block"):
        hits = tics.find_tics(text)
        if hits:
            summary = tics.summarize(hits)
            if mode == "block" and len(hits) >= int(cfg["tics.max_hits_before_block"]) and not reasons:
                reasons.append(f"Rewrite without these phrases and state the claims directly: {summary}.")
            else:
                warnings.append(f"harness: writing tics in final message — {summary}")

    # effort mismatch (chunk mode): info only; skipped when the chunk has no effort (model without the parameter [S28])
    if active and isinstance(hook_input.get("effort"), dict):
        lvl = hook_input["effort"].get("level")
        if lvl and active.get("effort") and lvl != active.get("effort"):
            warnings.append(f"harness: chunk {active.get('id')} recommends effort '{active.get('effort')}', current is '{lvl}' (set with /effort)")

    decision: dict[str, Any] = {}
    if reasons:
        if n >= cap or (hook_input.get("stop_hook_active") and n >= cap):
            warnings.insert(0, f"harness: completion gate allowed after {n} block(s) — unresolved: " + " | ".join(r[:90] for r in reasons))
            config.log("gate_allow_after_cap", session=session_id, prompt=prompt_id, attempts=n, reasons=reasons)
        else:
            attempts[prompt_id] = n + 1
            state["gate_attempts"] = attempts
            config.save_state(session_id, state)
            decision = {"decision": "block", "reason": f"[harness completion gate {n + 1}/{cap}] " + " ".join(reasons)}
            config.log("gate_block", session=session_id, prompt=prompt_id, attempt=n + 1, reasons=reasons,
                       evidence=ev, claim=claim, profile=cfg.get("harness.profile"))
    else:
        if claim and active and ev["strong"]:
            # mark chunk done (locking): evidence recorded
            try:
                data = chunkmod.load()
                for c in data.get("chunks", []):
                    if c.get("id") == active.get("id"):
                        c["status"] = "done"
                        c["evidence"] = ev["strong"][0]
                data["active"] = None
                chunkmod.save(data)
                warnings.append(f"harness: chunk {active.get('id')} marked done with evidence: {ev['strong'][0][:80]}")
            except Exception as e:
                config.log("chunk_mark_error", error=repr(e))
        config.log("gate_allow", session=session_id, prompt=prompt_id, claim=claim, evidence=ev, profile=cfg.get("harness.profile"))

    if warnings and not decision:
        # `systemMessage` is documented in the hook JSON output table [S20 (summarizer pass), S37 types]
        decision["systemMessage"] = "\n".join(warnings)
    return decision

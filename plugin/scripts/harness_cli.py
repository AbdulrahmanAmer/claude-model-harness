#!/usr/bin/env python3
"""Single entry point used by the hooks and the repo-level scripts.

  harness_cli.py detect   [--json]            model detection (reads hook JSON on stdin if piped)
  harness_cli.py identity                      SessionStart / PostModelSwitch: print identity + profile (plain text)
  harness_cli.py gate                          Stop: print gate decision JSON
  harness_cli.py reminder                      UserPromptSubmit: print additionalContext JSON every N prompts
  harness_cli.py tics-file                     PostToolUse: warn about tics in files written to disk
  harness_cli.py scope                         PreToolUse: chunk scope lock for Write/Edit
  harness_cli.py doctor  [--project P] [--profile X] [--model ID] [--json] [--apply] [--mode delete|move] | --explain R# | --list-rules
  harness_cli.py chunk   plan|run|status|done|clear ...
  harness_cli.py status                        /harness-status: model, profile, gate state, chunk, last log events, next step

Every command is wrapped so that any exception prints nothing (or a harmless empty JSON) and exits 0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Python >= 3.10 is required by the harness package (the shell wrapper no longer probes the version: a
# `python -c` probe costs a whole interpreter start on every hook). Too old -> log a line and exit 0 (fail open).
if sys.version_info < (3, 10):
    try:
        _log = Path(os.environ.get("HARNESS_HOME") or (Path.home() / ".claude")) / "harness.log"
        _log.parent.mkdir(parents=True, exist_ok=True)
        with _log.open("a", encoding="utf-8") as _fh:
            _fh.write(json.dumps({"event": "python_too_old", "version": sys.version.split()[0], "need": "3.10"}) + "\n")
    except Exception:
        pass
    sys.exit(0)

HOOK_COMMANDS = ("identity", "gate", "reminder", "tics-file", "scope", "status")


def _start_watchdog(seconds: float) -> None:
    """In-process timeout for hook commands. macOS ships no `timeout(1)` and the shell wrapper only uses it
    when present, so the CLI bounds itself: after `seconds` it logs `cli_timeout` and exits 124 with no
    stdout — Claude Code then sees a non-zero, non-2 exit and treats it as a non-blocking error [S20]."""
    import threading

    def _fire() -> None:
        try:
            log_path = Path(os.environ.get("HARNESS_HOME") or (Path.home() / ".claude")) / "harness.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"event": "cli_timeout", "seconds": seconds, "cmd": sys.argv[1:2]}) + "\n")
        except Exception:
            pass
        os._exit(124)

    t = threading.Timer(seconds, _fire)
    t.daemon = True
    t.start()


if len(sys.argv) > 1 and sys.argv[1] in HOOK_COMMANDS:
    try:
        _start_watchdog(float(os.environ.get("HARNESS_TIMEOUT", "12")))
    except Exception:
        pass

# Hook stdin/stdout are UTF-8 (Claude Code is a Node process). On Windows a piped Python stdio
# defaults to the locale code page (cp1252), and printing "≤" or "→" raised UnicodeEncodeError,
# which the fail-open wrapper swallowed — so every hook printed nothing. Force UTF-8 + LF.
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import chunks as chunkmod  # noqa: E402
from harness import config, detect_model, stop_gate, tics  # noqa: E402
# `harness.doctor` (dataclasses -> inspect -> dis/ast/tokenize) is imported lazily in cmd_doctor: it is not needed
# by the hook commands and costs ~1.2 s of import time on a slow Windows machine, against an 8 s hook timeout.

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)
PROFILES = PLUGIN_ROOT / "profiles"
HOOK_OUTPUT_CAP = 10_000   # characters; documented cap on hook stdout/additionalContext [src: S20]


def _stdin_json(wait: float = 0.5) -> dict:
    """Parse hook JSON from stdin. Never blocks forever: if nothing arrives within `wait` seconds
    (e.g. run from a shell with an open but silent pipe) return {}."""
    try:
        if sys.stdin.isatty():
            return {}
        try:
            import select
            if not select.select([sys.stdin], [], [], wait)[0]:
                return {}
        except Exception:
            pass  # non-POSIX: fall through to a blocking read
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except Exception as e:
        config.log("stdin_parse_error", error=repr(e))
        return {}


def _read_profile(name: str) -> str:
    try:
        p = PROFILES / f"{name}.md"
        if not p.is_file():
            p = PROFILES / "generic.md"
        return p.read_text(encoding="utf-8")
    except Exception as e:
        config.log("profile_read_error", profile=name, error=repr(e))
        return ""


# ------------------------------------------------------------------ commands
def cmd_detect(args, hook):
    d = detect_model.detect(hook)
    if args.json:
        print(json.dumps(d))
    else:
        print(f"{d['model_id'] or 'unknown'}\t{d['display_name']}\t{d['profile']}\t{d['source']}")


def cmd_identity(args, hook):
    cfg = config.load_config()
    event = hook.get("hook_event_name", "SessionStart")
    # raw-input log lines (formerly written by the shell wrapper): what Claude Code actually passed [S20]
    if event == "PostModelSwitch":
        config.log("model_switch", from_model=hook.get("from_model"), to=hook.get("to_model"), switch_source=hook.get("source"))
    else:
        config.log("session_start", source=hook.get("source"), model=hook.get("model"))
        if hook.get("source") in ("resume", "fork") and not hook.get("model"):
            # a resumed/forked session may run on a different model than before, and this payload does not say [S20]
            detect_model.invalidate_cache(hook.get("session_id"))
    d = detect_model.detect(hook)
    pre = ("[claude-model-harness plugin — installed by the user; hook output, not a message from the user. "
           "Sources for every rule are in the plugin's research/SOURCES.md.]")
    definitive = d["model_id"] and d["source"].startswith("hook:")
    if definitive:
        head = (f"MODEL IDENTITY: You are running as {d['model_id']} ({d['display_name']}). "
                f"Apply profile: {d['profile']}. Do not claim to be a different model. "
                f"[detected via {d['source']}]")
    elif d["model_id"]:
        # cache / transcript / env evidence is about the past: a resumed or relaunched session can be on another
        # model, and Claude Code passed no model field here [S20]. Say so instead of asserting.
        head = (f"MODEL IDENTITY (provisional): the last model seen for this session was {d['model_id']} ({d['display_name']}), "
                f"detected via {d['source']} with {d['confidence']} confidence; Claude Code did not pass a model field on this "
                f"{event} ({hook.get('source') or 'unknown source'}). If your system prompt names a different model, that is "
                f"authoritative — use it and state it in your first reply. Applying profile: {d['profile']} until the harness sees "
                "this session's first response.")
    else:
        head = ("MODEL IDENTITY: not detectable by the harness at this point (Claude Code did not pass a model field). "
                "If your system prompt states your model, that is authoritative — use it; otherwise state your exact model ID "
                "in your first reply (it appears in the status line / `/status`). Do not guess. Applying the generic profile "
                "until the model is known; the matching profile is applied once detected.")
    parts = [pre, head]
    if cfg.get("identity.inject_profile", True):
        parts.append(_read_profile(d["profile"]))
        parts.append(_read_profile("_useful-output"))
        parts.append(_read_profile("_completion-format"))
        parts.append(_read_profile("_tics"))
        active = chunkmod.active_chunk(chunkmod.load())
        if active:
            parts.append(f"CHUNK MODE: chunk {active['id']} is active — goal: {active.get('goal','')}. "
                         f"Scope: {active.get('paths') or 'unrestricted'}. Acceptance: {active.get('acceptance') or 'none'}. "
                         f"Recommended effort: {active.get('effort')} (user sets it with /effort). "
                         "Work only inside this chunk; claim it done only after the acceptance command ran and passed.")
    out = "\n\n".join(p.strip() for p in parts if p and p.strip())
    # Claude Code caps hook stdout at 10,000 characters and replaces longer output with a file preview [src: S20];
    # the profiles are sized to stay under it (tests/test_identity.py::test_identity_output_under_hook_cap).
    if len(out) > HOOK_OUTPUT_CAP:
        config.log("identity_truncated", profile=d["profile"], length=len(out))
        out = out[:HOOK_OUTPUT_CAP - 60].rstrip() + "\n[harness: profile truncated to fit the hook output cap]"
    print(out)
    config.log("identity_injected", hook_event=event, start_source=hook.get("source"), model_id=d["model_id"], profile=d["profile"], detected_via=d["source"], length=len(out))


def cmd_gate(args, hook):
    config.log("stop", stop_hook_active=hook.get("stop_hook_active"), prompt=hook.get("prompt_id"))
    d = detect_model.detect(hook)                       # tier -> per-tier gate defaults (config.TIER_DEFAULTS)
    if d["model_id"] and d["source"].startswith("transcript"):
        # Headless sessions never get a hook `model` field [S20]; the transcript is the first place the model shows
        # up. Cache it (medium confidence) so CLI calls made from the model's own Bash tool (`chunk plan`, `status`,
        # `doctor`) know the model too. A hook-provided model always overwrites this.
        detect_model.write_cache(d["model_id"], d["source"], hook.get("session_id"))
    out = stop_gate.evaluate(hook, config.load_config(d["profile"]))
    if out:
        print(json.dumps(out))


def cmd_reminder(args, hook):
    cfg = config.load_config()
    n = int(cfg.get("reminder.every_n_prompts", 5) or 0)
    if n <= 0:
        return
    sid = str(hook.get("session_id") or "unknown")
    st = config.load_state(sid)
    count = int(st.get("prompt_count", 0)) + 1
    st["prompt_count"] = count
    config.save_state(sid, st)
    if count % n != 0:
        return
    d = detect_model.detect(hook)
    active = chunkmod.active_chunk(chunkmod.load())
    lines = [f"harness reminder (prompt {count}): running as {d['model_id'] or 'unknown model'}; profile {d['profile']}.",
             "When you finish: first sentence = outcome; then ≤3 bullets; a 'Verification:' line with the command you ran and its observed result; a 'Blockers:' line.",
             "Deliver what was asked, at the scope intended; do not widen or narrow it."]
    if active:
        lines.append(f"Chunk {active['id']} active: stay within {active.get('paths') or 'its scope'}; acceptance: {active.get('acceptance')}.")
    # documented shape [S21]: hookSpecificOutput.additionalContext (top-level is ignored)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(lines)}}))
    config.log("reminder_injected", session=sid, prompt_count=count)


def cmd_tics_file(args, hook):
    cfg = config.load_config()
    if cfg.get("tics.files_mode", "warn") == "off":
        return
    if hook.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        return
    inp = hook.get("tool_input") or {}
    fp = str(inp.get("file_path") or "")
    import fnmatch
    if not any(fnmatch.fnmatch(os.path.basename(fp), g) for g in cfg.get("tics.file_globs", [])):
        return
    text = inp.get("content") or inp.get("new_string") or ""
    if not text and isinstance(inp.get("edits"), list):
        text = "\n".join(str(e.get("new_string", "")) for e in inp["edits"] if isinstance(e, dict))
    hits = tics.find_tics(str(text))
    if not hits:
        return
    msg = f"harness: writing tics in {os.path.basename(fp)} — {tics.summarize(hits)}. State claims directly (see profile)."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}))
    config.log("tics_file_warning", file=fp, hits=len(hits))


def _deny(reason: str, mode: str) -> None:
    if mode == "deny":
        # documented PreToolUse output [S20, S21]
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                  "permissionDecisionReason": reason}}))
    else:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": reason}}))


def cmd_scope(args, hook):
    cfg = config.load_config()
    mode = cfg.get("chunk.scope_lock", "deny")
    tool = hook.get("tool_name")
    if mode == "off" or tool not in ("Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"):
        return
    inp = hook.get("tool_input") or {}
    data = chunkmod.load()
    active = chunkmod.active_chunk(data)
    if tool == "Bash":
        cmd = str(inp.get("command") or "")
        # 1. The plan file is the user's. Seen live: a model widened its own chunk's `paths` with a Bash heredoc
        #    (the Edit/Write lock never saw it). Only the harness CLI may touch it.
        if chunkmod.PLAN_FILE_RX.search(cmd) and "harness_cli.py" not in cmd:
            reason = ("harness scope lock: the chunk plan (.claude/harness/chunks.json) is not yours to edit. If this chunk "
                      "needs more files, stop and report under 'Blockers:' which paths and why; widening scope is the user's call.")
            config.log("scope_lock", file="chunks.json", chunk=(active or {}).get("id"), mode=mode, via="bash", command=cmd[:160])
            return _deny(reason, mode)
        if not active or not active.get("paths"):
            return
        # 2. Shell writes to out-of-scope files (`> f`, `>> f`, `tee f`, `sed -i f`, python open(f,'w'), write_text)
        targets = chunkmod.bash_write_targets(cmd)
        # Writes outside the project (temp files, home dirs) are not the plan's business; only project files count.
        outside = [t for t in targets if chunkmod.in_project(t) and not chunkmod.path_in_scope(t, active["paths"])]
        config.log("scope_check", tool="Bash", file=";".join(targets)[-80:], project=str(config.project_dir())[-80:],
                   chunk=active.get("id"), paths=active.get("paths"))
        if outside:
            reason = (f"harness scope lock: this command writes to {outside[:3]}, outside chunk {active['id']} scope {active['paths']}. "
                      "Finish the chunk first; note the extra change under 'Blockers:' or as a follow-up.")
            config.log("scope_lock", file=";".join(outside)[:200], chunk=active["id"], mode=mode, via="bash", command=cmd[:160])
            return _deny(reason, mode)
        return
    fp = str(inp.get("file_path") or "")
    # audit line: proves the hook ran and what it saw (project dir comes from CLAUDE_PROJECT_DIR or cwd)
    config.log("scope_check", tool=tool, file=fp[-80:], project=str(config.project_dir())[-80:],
               chunk=(active or {}).get("id"), paths=(active or {}).get("paths"))
    if fp and chunkmod.PLAN_FILE_RX.search(fp.replace("\\", "/")):
        reason = ("harness scope lock: the chunk plan (.claude/harness/chunks.json) is not yours to edit. Report the paths this chunk "
                  "needs under 'Blockers:'; widening scope is the user's call.")
        config.log("scope_lock", file=fp, chunk=(active or {}).get("id"), mode=mode, via=tool)
        return _deny(reason, mode)
    if not active or not active.get("paths"):
        return
    if not fp or chunkmod.path_in_scope(fp, active["paths"]):
        return
    reason = (f"harness scope lock: {fp} is outside chunk {active['id']} scope {active['paths']}. "
              "Finish the chunk first; note the extra change under 'Blockers:' or as a follow-up.")
    config.log("scope_lock", file=fp, chunk=active["id"], mode=mode)
    _deny(reason, mode)


def cmd_doctor(args, hook):
    from harness import doctor  # lazy, see the import note at the top
    if args.explain:
        print(doctor.explain(args.explain))
        return 0
    if args.list_rules:
        print("\n".join(doctor.rule_ids()))
        return 0
    project = Path(args.project).resolve() if args.project else config.project_dir()
    home = Path(args.home).resolve() if args.home else config._home()
    profile = args.profile
    model_line = ""
    model_id = args.model
    if not profile:
        d = detect_model.detect(hook)
        profile, model_line = d["profile"], f"model {d['model_id'] or 'unknown'} via {d['source']}"
        model_id = model_id or d["model_id"]
    elif model_id:
        model_line = f"model {model_id} (given)"
    findings = doctor.run(project, home, profile, model_id)
    if args.json:
        print(json.dumps({"profile": profile, "findings": [f.as_dict() for f in findings]}, indent=1))
    else:
        print(doctor.render(findings, profile, model_line))
    edits = doctor.planned_edits(findings, mode=args.mode)
    if edits:
        diff = doctor.unified_diff(edits)
        if not args.json:
            print("\n--- proposed changes (dry run) ---")
            print(diff)
        if args.apply:
            written = doctor.apply(edits)
            print("\napplied to: " + ", ".join(written) if written else "\nnothing applied (files changed since scan?)")
            print("backups written next to each file as *.harness.bak")
        elif not args.json:
            print("\nRe-run with --apply to write these changes (backups are kept as *.harness.bak).")
    elif not args.json:
        print("\nNo automatic edits proposed.")
    return 1 if any(f.severity == "error" for f in findings) and args.strict else 0


def cmd_status(args, hook):
    """/harness-status: what the harness knows right now, and what to do next. Read-only."""
    import time as _time
    d = detect_model.detect(hook)
    cfg = config.load_config(d["profile"])
    lines = ["harness status"]
    lines.append(f"  model: {d['model_id'] or 'unknown'} ({d['display_name']})  via {d['source']}  confidence {d['confidence']}")
    lines.append(f"  profile: {d['profile']}  (plugin/profiles/{d['profile']}.md + _useful-output + completion format + tics)")
    # gate state: most recent per-session state file
    state_file = None
    try:
        files = sorted(config.state_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        state_file = files[0] if files else None
    except Exception:
        pass
    st = config._read_json(state_file) if state_file else {}
    attempts = st.get("gate_attempts", {}) if isinstance(st, dict) else {}
    last_prompt, last_n = (list(attempts.items())[-1] if attempts else (None, 0))
    lines.append(f"  gate: {'on' if cfg.get('gate.enabled', True) else 'off'}; format required={cfg.get('gate.require_format')}; "
                 f"grounding={cfg.get('gate.grounding')} (tier default: {config.tier_defaults(d['profile']).get('gate.grounding', 'off')}); "
                 f"tics={cfg.get('tics.stop_mode')}; blocks this prompt: {last_n}/{cfg.get('gate.max_blocks_per_prompt')}"
                 + (f" (prompt {str(last_prompt)[:8]}…)" if last_prompt else "") + f"; prompts this session: {st.get('prompt_count', 0) if isinstance(st, dict) else 0}")
    active = chunkmod.active_chunk(chunkmod.load())
    if active:
        lines.append(f"  chunk: #{active['id']} active — {active.get('goal', '')} | scope {active.get('paths')} | acceptance {active.get('acceptance')} | "
                     + chunkmod.effort_line(chunkmod.load().get("model_id"), active.get("effort"), active.get("effort_reason", "")))
    else:
        data = chunkmod.load()
        lines.append("  chunk: none active" + (f" (plan has {len(data.get('chunks', []))} chunks; /chunk status)" if data else " (no plan; /chunk plan <task>)"))
    # last three log events
    events = []
    try:
        p = config.log_path()
        if p.is_file():
            tail = p.read_text(encoding="utf-8", errors="replace").splitlines()[-3:]
            for raw in tail:
                try:
                    e = json.loads(raw)
                    events.append(f"{e.get('ts', '')} {e.get('event', '')} " + " ".join(f"{k}={str(v)[:40]}" for k, v in e.items() if k not in ("ts", "event") and v not in (None, "", [], {})))
                except Exception:
                    events.append(raw[:160])
    except Exception:
        pass
    lines.append("  last log events (" + str(config.log_path()) + "):")
    lines += [f"    {ev[:200]}" for ev in events] or ["    (none)"]
    # next steps
    nxt = []
    if not d["model_id"]:
        nxt.append("model unknown: run /status (or check the status line) and tell Claude the model ID; the SessionStart hook fills it in on the next /clear, /model or resume [S20]")
    elif d["confidence"] != "high":
        nxt.append(f"model detected with {d['confidence']} confidence via {d['source']}; /model <id> or a new session makes it definitive [S20]")
    if last_n and int(last_n) >= int(cfg.get("gate.max_blocks_per_prompt", 2)):
        nxt.append("the gate hit its per-prompt cap on the last prompt and let the turn through with a warning; check the Verification/Blockers lines yourself")
    if active:
        nxt.append(f"finish chunk #{active['id']} inside its scope, run its acceptance command as a real tool call, then report in the completion format")
    else:
        nxt.append("for anything larger than one file: /chunk plan <task>; to lint CLAUDE.md for this model: /harness-doctor")
    lines.append("  next: " + " | ".join(nxt))
    print("\n".join(lines))
    config.log("status_shown", model_id=d["model_id"], profile=d["profile"])


def cmd_chunk(args, hook):
    project = Path(args.project).resolve() if args.project else config.project_dir()
    data = chunkmod.load(project)
    sub = args.sub
    if sub == "plan":
        spec = json.loads(Path(args.file).read_text(encoding="utf-8")) if args.file else json.loads(sys.stdin.read())
        model_id = args.model or detect_model.detect(hook)["model_id"]     # per-model effort table [S28, S14]
        if not model_id:
            print("note: model unknown to the harness (pass --model <id>); effort defaults to high for every chunk [S14, S28]")
        plan = chunkmod.new_plan(spec.get("task", ""), spec.get("chunks", []), model_id)
        chunkmod.save(plan, project)
        data = plan
        sub = "status"
    if sub == "run":
        if not data:
            print("no chunk plan; run `chunk plan` first"); return 0
        for c in data["chunks"]:
            if c["id"] == int(args.id):
                c["status"] = "active"; data["active"] = c["id"]
                c["paths_at_activation"] = list(c.get("paths") or [])   # the gate reports any later change to `paths`
                chunkmod.save(data, project)
                print(f"chunk {c['id']} active — goal: {c['goal']}\n  scope: {c['paths']}\n  acceptance: {c['acceptance']}\n"
                      f"  {chunkmod.effort_line(data.get('model_id'), c.get('effort'), c.get('effort_reason', ''))}")
                return 0
        print("no such chunk"); return 0
    if sub == "done":
        if data:
            for c in data["chunks"]:
                if c["id"] == int(args.id):
                    c["status"] = "done"; c["evidence"] = args.evidence or c.get("evidence", "")
            if data.get("active") == int(args.id):
                data["active"] = None
            chunkmod.save(data, project)
        sub = "status"
    if sub == "clear":
        try:
            chunkmod.chunks_path(project).unlink()
        except FileNotFoundError:
            pass
        print("chunk plan cleared"); return 0
    if sub == "status":
        if not data:
            print("no chunk plan"); return 0
        print(f"task: {data.get('task','')}\nmodel: {data.get('model_id') or 'unknown'}\nactive: {data.get('active')}")
        for c in data["chunks"]:
            print(f"  [{c['status']:7}] {c['id']}. {c['goal']}  effort={c.get('effort') or 'n/a'}  scope={c['paths']}  accept={c['acceptance']}")
        return 0
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="harness")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("detect"); p.add_argument("--json", action="store_true")
    sp.add_parser("identity"); sp.add_parser("gate"); sp.add_parser("reminder"); sp.add_parser("tics-file"); sp.add_parser("scope"); sp.add_parser("status")
    p = sp.add_parser("doctor")
    p.add_argument("--project"); p.add_argument("--home"); p.add_argument("--profile"); p.add_argument("--model")
    p.add_argument("--json", action="store_true"); p.add_argument("--apply", action="store_true")
    p.add_argument("--mode", choices=["delete", "move"], default="delete"); p.add_argument("--strict", action="store_true")
    p.add_argument("--explain", metavar="RULE", help="print the per-tier cited reasoning for one rule (e.g. R1)")
    p.add_argument("--list-rules", action="store_true")
    p = sp.add_parser("chunk")
    p.add_argument("sub", choices=["plan", "run", "status", "done", "clear"]); p.add_argument("--id", default="0")
    p.add_argument("--file"); p.add_argument("--evidence"); p.add_argument("--project")
    p.add_argument("--model", help="model ID for the effort table (default: detected from the harness cache)")
    args = ap.parse_args(argv)
    hook_cmds = ("identity", "gate", "reminder", "tics-file", "scope")
    hook = _stdin_json(wait=5.0) if args.cmd in hook_cmds else (_stdin_json(wait=0.3) if args.cmd in ("detect", "doctor") else {})
    if args.cmd == "chunk" and getattr(args, "file", None):
        hook = {}   # `chunk plan --file` reads the plan from the file; stdin is not a hook payload
    fn = {"detect": cmd_detect, "identity": cmd_identity, "gate": cmd_gate, "reminder": cmd_reminder,
          "tics-file": cmd_tics_file, "scope": cmd_scope, "doctor": cmd_doctor, "chunk": cmd_chunk, "status": cmd_status}[args.cmd]
    try:
        rc = fn(args, hook)
        return int(rc or 0)
    except SystemExit:
        raise
    except Exception as e:  # fail open, always
        config.log("cli_error", cmd=args.cmd, error=repr(e))
        return 0


if __name__ == "__main__":
    sys.exit(main())

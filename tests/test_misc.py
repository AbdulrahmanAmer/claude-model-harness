"""Reminder cadence, tics detector, PostToolUse file warning, chunk scope lock, API param resolver, PROMPT.md size."""
import json
import subprocess
import sys

import pytest

from conftest import ROOT, hook_input
from harness import chunks as chunkmod
from harness import tics
from harness_client import resolve_params

CLI = ROOT / "plugin" / "scripts" / "harness_cli.py"


def cli(args, stdin):
    return subprocess.run([sys.executable, str(CLI), *args], input=json.dumps(stdin), capture_output=True, text=True, timeout=30)


def test_reminder_every_5_prompts():
    outs = [cli(["reminder"], hook_input(hook_event_name="UserPromptSubmit", prompt="x")).stdout for _ in range(10)]
    assert [bool(o.strip()) for o in outs] == [False] * 4 + [True] + [False] * 4 + [True]
    d = json.loads(outs[4])
    assert d["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "first sentence = outcome" in d["hookSpecificOutput"]["additionalContext"]
    assert "words" not in d["hookSpecificOutput"]["additionalContext"].lower()   # ordering rule, never a word cap


def test_tics_tiers():
    hits = tics.find_tics("Honestly, this is load-bearing. It's not a bug, it's a feature. The dial worth turning is X.")
    tiers = {h["phrase"]: h["tier"] for h in hits}
    assert tiers["honestly"] == "official" and tiers["load-bearing"] == "community"
    assert tiers["it's not X, it's Y"] == "community" and tiers["dial worth turning"] == "mannered"
    assert tics.find_tics("Deleting that section breaks the build.") == []


def test_post_tool_use_warns_on_markdown_only():
    r = cli(["tics-file"], hook_input(hook_event_name="PostToolUse", tool_name="Write", tool_input={"file_path": "/x/README.md", "content": "It's worth noting the seam here."}, tool_response={}))
    d = json.loads(r.stdout)
    assert "writing tics in README.md" in d["hookSpecificOutput"]["additionalContext"]
    r = cli(["tics-file"], hook_input(hook_event_name="PostToolUse", tool_name="Write", tool_input={"file_path": "/x/main.py", "content": "# honestly"}, tool_response={}))
    assert r.stdout.strip() == ""


def test_scope_lock_denies_outside_paths(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    chunkmod.save(chunkmod.new_plan("t", [{"goal": "g", "kind": "feature", "paths": ["src/auth/**", "tests/test_auth.py"], "acceptance": ["pytest"]}]), proj)
    d = chunkmod.load(proj); d["active"] = 1; chunkmod.save(d, proj)
    r = cli(["scope"], hook_input(hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": str(proj / "src/billing/x.py")}))
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "outside chunk 1 scope" in out["permissionDecisionReason"]
    r = cli(["scope"], hook_input(hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": str(proj / "src/auth/login.py")}))
    assert r.stdout.strip() == ""
    r = cli(["scope"], hook_input(hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": "tests/test_auth.py"}))
    assert r.stdout.strip() == ""
    # warn mode
    monkeypatch.setenv("HARNESS_CHUNK__SCOPE_LOCK", "warn")
    r = cli(["scope"], hook_input(hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": str(proj / "src/billing/x.py")}))
    assert "additionalContext" in json.loads(r.stdout)["hookSpecificOutput"]


def test_scope_lock_covers_bash_and_the_plan_file(tmp_path, monkeypatch):
    """Seen live (Sonnet 5, chunks 2 and 7): the model rewrote .claude/harness/chunks.json through a Bash heredoc to add
    files to its own chunk's `paths`, then edited those files; the Edit/Write lock never saw it."""
    proj = tmp_path / "proj"
    chunkmod.save(chunkmod.new_plan("t", [{"goal": "g", "kind": "feature", "paths": ["src/auth/**", "tests/test_auth.py"], "acceptance": ["pytest"]}]), proj)
    d = chunkmod.load(proj); d["active"] = 1; chunkmod.save(d, proj)
    def bash(cmd):
        return cli(["scope"], hook_input(hook_event_name="PreToolUse", tool_name="Bash", tool_input={"command": cmd})).stdout.strip()
    heredoc = "cd \"%s\" && python3 - <<'EOF'\nimport json\np = \".claude/harness/chunks.json\"\ndata = json.load(open(p))\ndata['chunks'][0]['paths'].append('app/main.py')\njson.dump(data, open(p, 'w'))\nEOF" % proj
    out = json.loads(bash(heredoc))["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "chunk plan" in out["permissionDecisionReason"]
    assert bash("python3 /x/plugin/scripts/harness_cli.py chunk status") == ""                 # the harness CLI may read/write it
    assert json.loads(bash("echo x > src/billing/x.py"))["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert bash("echo x > src/auth/login.py") == ""                                             # in scope
    assert json.loads(bash("python - <<'EOF'\nopen('tests/test_other.py', 'w').write('x')\nEOF"))["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert bash("sed -i 's/a/b/' src/auth/login.py") == "" and bash("python -m pytest -q") == "" and bash("cat src/billing/x.py") == ""
    # the Edit tool on the plan file is refused too
    r = cli(["scope"], hook_input(hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": str(proj / ".claude" / "harness" / "chunks.json")}))
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert chunkmod.bash_write_targets("cat a.py | tee out.txt; ls > /dev/null; echo hi") == ["out.txt"]


def test_gate_reports_plan_widened_after_activation(transcript, tmp_path):
    proj = tmp_path / "proj"
    spec = proj / "plan.json"
    spec.write_text(json.dumps({"task": "T", "chunks": [{"goal": "a", "kind": "feature", "paths": ["a.py"], "acceptance": ["pytest -q"]}]}))
    subprocess.run([sys.executable, str(CLI), "chunk", "plan", "--file", str(spec), "--project", str(proj), "--model", "claude-opus-5"], capture_output=True, text=True)
    subprocess.run([sys.executable, str(CLI), "chunk", "run", "--id", "1", "--project", str(proj)], capture_output=True, text=True)
    d = chunkmod.load(proj)
    assert d["chunks"][0]["paths_at_activation"] == ["a.py"]
    d["chunks"][0]["paths"].append("b.py"); chunkmod.save(d, proj)          # what the model did via Bash
    from harness import stop_gate
    t = transcript([("user", "x"), ("text", "still working")])
    out = stop_gate.evaluate(hook_input(transcript_path=str(t), last_assistant_message="still working"), None)
    assert "decision" not in out and "scope was widened after activation by ['b.py']" in out["systemMessage"]
    assert chunkmod.scope_changes(d["chunks"][0]) == ["b.py"]


def test_effort_recommendation_unknown_model_defaults_high():
    eff, why = chunkmod.recommend_effort("feature", 3, True)
    assert eff == "high" and "[S14" in why                      # default high on every model that supports effort [S14, S28]
    assert chunkmod.supported_efforts(None) is None and chunkmod.supported_efforts("gpt-5") is None


# one case per current model (research/MODEL_MATRIX.md; Claude Code effort table [S28], tier sweet spots [S14, S45, S4, S8])
EFFORT_CASES = [
    # model id,                    mechanical/small, routine feature, debug,   large refactor
    ("claude-fable-5-1",           "medium",         "high",          "high",  "xhigh"),
    ("claude-fable-5",             "medium",         "high",          "high",  "xhigh"),
    ("claude-opus-5",              "low",            "medium",        "high",  "high"),
    ("claude-opus-4-8",            "medium",         "high",          "xhigh", "xhigh"),
    ("claude-opus-4-7",            "medium",         "high",          "xhigh", "xhigh"),
    ("claude-opus-4-6",            "medium",         "medium",        "high",  "high"),     # no xhigh [S14, S28]
    ("claude-opus-4-5-20251101",   None,             None,            None,    None),       # not in Claude Code's table [S28]
    ("claude-sonnet-5",            "medium",         "high",          "xhigh", "xhigh"),
    ("claude-sonnet-4-6",          "medium",         "medium",        "high",  "high"),     # medium recommended default, no xhigh [S14]
    ("claude-sonnet-4-5-20250929", None,             None,            None,    None),       # no effort parameter [S47]
    ("claude-haiku-4-5-20251001",  None,             None,            None,    None),       # no effort parameter [S17, S47]
]


@pytest.mark.parametrize("model,mech,feat,dbg,big", EFFORT_CASES)
def test_effort_recommendation_per_model(model, mech, feat, dbg, big):
    got = [chunkmod.recommend_effort("mechanical", 1, True, model), chunkmod.recommend_effort("feature", 3, True, model),
           chunkmod.recommend_effort("debug", 2, False, model), chunkmod.recommend_effort("refactor", 9, True, model)]
    assert [g[0] for g in got] == [mech, feat, dbg, big], got
    for eff, why in got:
        assert "[S" in why, (model, why)
        levels = chunkmod.supported_efforts(model)
        assert (eff is None) == (levels == ()), (model, eff, levels)
        if eff is not None:
            assert eff in levels
    line = chunkmod.effort_line(model, got[1][0], got[1][1])
    if feat is None:
        assert line.startswith("effort: not supported on") and "[S17, S28]" in line and "/effort" not in line
    else:
        assert line.endswith(f"-> run: /effort {feat}")


def test_effort_support_table_matches_docs():
    """Claude Code effort levels per model [S28]."""
    full = ("low", "medium", "high", "xhigh", "max")
    assert chunkmod.supported_efforts("claude-fable-5-1") == full and chunkmod.supported_efforts("claude-opus-4-7") == full
    assert chunkmod.supported_efforts("claude-opus-4-6") == ("low", "medium", "high", "max")
    assert chunkmod.supported_efforts("claude-sonnet-4-6") == ("low", "medium", "high", "max")
    assert chunkmod.supported_efforts("claude-haiku-4-5-20251001") == () and chunkmod.supported_efforts("claude-opus-4-5-20251101") == ()
    # a plan for a model without effort gets effort None and status shows n/a; a plan for Opus 4.6 never recommends xhigh
    plan = chunkmod.new_plan("t", [{"goal": "g", "kind": "debug", "paths": ["a.py"] * 9, "acceptance": ["pytest"]}], "claude-haiku-4-5-20251001")
    assert plan["model_id"] == "claude-haiku-4-5-20251001" and plan["chunks"][0]["effort"] is None
    plan46 = chunkmod.new_plan("t", [{"goal": "g", "kind": "refactor", "paths": ["a.py"] * 9, "acceptance": ["pytest"]}], "claude-opus-4-6")
    assert plan46["chunks"][0]["effort"] == "high"


def test_chunk_cli_plan_run_status(tmp_path):
    proj = tmp_path / "proj"
    spec = proj / "plan.json"
    spec.write_text(json.dumps({"task": "T", "chunks": [{"goal": "a", "kind": "mechanical", "paths": ["a.py"], "acceptance": ["pytest -q"]}, {"goal": "b", "kind": "refactor", "paths": ["b/**"] * 8, "acceptance": ["make test"]}]}))
    r = subprocess.run([sys.executable, str(CLI), "chunk", "plan", "--file", str(spec), "--project", str(proj), "--model", "claude-opus-5"], capture_output=True, text=True)
    assert "effort=low" in r.stdout and "effort=high" in r.stdout and "model: claude-opus-5" in r.stdout
    r = subprocess.run([sys.executable, str(CLI), "chunk", "run", "--id", "2", "--project", str(proj)], capture_output=True, text=True)
    assert "chunk 2 active" in r.stdout and "-> run: /effort high" in r.stdout
    assert chunkmod.load(proj)["active"] == 2
    # a model without an effort parameter: the run line says so and names no /effort command [S17, S28]
    r = subprocess.run([sys.executable, str(CLI), "chunk", "plan", "--file", str(spec), "--project", str(proj), "--model", "claude-haiku-4-5-20251001"], capture_output=True, text=True)
    assert "effort=n/a" in r.stdout
    r = subprocess.run([sys.executable, str(CLI), "chunk", "run", "--id", "1", "--project", str(proj)], capture_output=True, text=True)
    assert "effort: not supported on claude-haiku-4-5-20251001" in r.stdout and "/effort" not in r.stdout


def test_api_param_resolver():
    assert resolve_params("claude-opus-5", "medium") == {"output_config": {"effort": "medium"}}
    assert resolve_params("claude-fable-5-1", "high") == {"output_config": {"effort": "high"}}
    assert resolve_params("claude-opus-4-8", "xhigh") == {"output_config": {"effort": "xhigh"}, "thinking": {"type": "adaptive"}}
    assert resolve_params("claude-sonnet-5", "low", "disabled")["thinking"] == {"type": "disabled"}
    assert resolve_params("claude-sonnet-5", "xhigh") == {"output_config": {"effort": "xhigh"}}          # xhigh on Sonnet 5 [S14]
    assert resolve_params("claude-sonnet-4-6", "medium") == {"output_config": {"effort": "medium"}, "thinking": {"type": "adaptive"}}
    assert resolve_params("claude-opus-4-5-20251101", "medium") == {"output_config": {"effort": "medium"}}  # Opus 4.5 supports effort [S14]
    with pytest.raises(ValueError, match="not supported on claude-sonnet-4-6"):
        resolve_params("claude-sonnet-4-6", "xhigh")                                                       # no xhigh on 4.6 [S14]
    with pytest.raises(ValueError, match="not supported on claude-opus-4-6"):
        resolve_params("claude-opus-4-6", "xhigh")
    with pytest.raises(ValueError, match="does not support the effort parameter"):
        resolve_params("claude-haiku-4-5-20251001", "low")                                                 # no effort on Haiku 4.5 [S47]
    with pytest.raises(ValueError, match="does not support the effort parameter"):
        resolve_params("claude-sonnet-4-5-20250929", "medium")                                             # no effort on Sonnet 4.5 [S47]
    with pytest.raises(ValueError, match="adaptive"):
        resolve_params("claude-haiku-4-5-20251001", None, "adaptive")                                      # extended-only [S16]
    from harness_client import family, rejects_sampling, supported_efforts
    assert family("claude-sonnet-5")[1] == "sonnet-5" and family("claude-haiku-4-5-20251001")[1] == "haiku"
    assert family("claude-sonnet-4-6")[1] == "sonnet-4x" and family("claude-opus-4-5-20251101")[1] == "opus-4x"
    assert supported_efforts("claude-opus-4-7") == ("low", "medium", "high", "xhigh", "max")
    assert supported_efforts("claude-opus-4-6") == ("low", "medium", "high", "max")
    assert rejects_sampling("claude-opus-5") and rejects_sampling("claude-sonnet-5") and not rejects_sampling("claude-sonnet-4-6")  # [S15]
    with pytest.raises(ValueError, match="400"):
        resolve_params("claude-opus-5", "xhigh", "disabled", allow_thinking_off=True)
    with pytest.raises(ValueError, match="tool calls as plain text"):
        resolve_params("claude-opus-5", "high", "disabled")
    with pytest.raises(ValueError, match="Fable"):
        resolve_params("claude-fable-5-1", "low", "disabled")
    with pytest.raises(ValueError, match="rejected on 4.7"):
        resolve_params("claude-opus-5", "high", "enabled")
    assert resolve_params("claude-opus-4-5-20251101", None, "enabled")["thinking"]["budget_tokens"] == 4096


def test_status_command_reports_model_gate_chunk_and_log(tmp_path):
    """/harness-status: detected model + source + confidence, profile, gate state, chunk, last log events, next step."""
    cli(["identity"], hook_input(hook_event_name="SessionStart", source="startup", model="claude-sonnet-5"))
    cli(["gate"], hook_input(prompt_id="p1", last_assistant_message="Done, fixed."))
    r = subprocess.run([sys.executable, str(CLI), "status"], capture_output=True, text=True, timeout=60)
    out = r.stdout
    assert r.returncode == 0
    assert "model: claude-sonnet-5 (Claude Sonnet 5)  via cache:hook:SessionStart.model  confidence high" in out
    assert "profile: sonnet-5" in out and "grounding=block (tier default: block)" in out
    assert "blocks this prompt: 1/2" in out and "chunk: none active" in out
    assert "gate_block" in out and "identity_injected" in out          # last three log events
    assert "next:" in out and "/chunk plan" in out
    # unknown model -> the next step says to run /status; nothing is guessed
    import shutil
    shutil.rmtree(tmp_path / "claude-home", ignore_errors=True); (tmp_path / "claude-home").mkdir()
    out2 = subprocess.run([sys.executable, str(CLI), "status"], capture_output=True, text=True, timeout=60).stdout
    assert "model: unknown" in out2 and "profile: generic" in out2 and "run /status" in out2


def test_prompt_md_under_60_lines_and_has_fill_in():
    lines = (ROOT / "PROMPT.md").read_text().splitlines()
    assert len(lines) <= 60
    assert any("{{MODEL_ID}}" in l for l in lines)


def test_profiles_cite_sources():
    import re
    from harness import detect_model
    for name in detect_model.TIERS + ("_useful-output",):
        txt = (ROOT / "plugin" / "profiles" / f"{name}.md").read_text(encoding="utf-8")
        bullets = [l for l in txt.splitlines() if l.startswith("- ")]
        assert bullets and all(re.search(r"\[src: S\d+", b) for b in bullets), name
        assert "[src: C" not in txt, name                      # community evidence never enters a profile
    from harness import doctor
    # tiers that must contain NO verification/thoroughness/no-thinking instruction (Opus 5 guide [S1]; unknown model may be Opus 5)
    for name in ("opus-5", "generic", "fable-5", "_useful-output"):
        fs = doctor.scan_file(ROOT / "plugin" / "profiles" / f"{name}.md", "opus-5")
        assert not [f for f in fs if f.rule in ("R1-verification-instruction", "R2-thoroughness-cruft", "R3-no-thinking-rule")], (name, [(f.rule, f.text) for f in fs])
    # lower tiers carry the cross-model self-check line, cited to S8, and nothing that S8 says hurts them
    for name in ("opus-4x", "sonnet-5", "sonnet-4x", "haiku"):
        txt = (ROOT / "plugin" / "profiles" / f"{name}.md").read_text(encoding="utf-8")
        line = next(l for l in txt.splitlines() if l.startswith("- Before you finish, verify"))
        assert "[src: S8" in line, name
        fs = doctor.scan_file(ROOT / "plugin" / "profiles" / f"{name}.md", "opus-5")
        assert not [f for f in fs if f.rule in ("R2-thoroughness-cruft", "R3-no-thinking-rule", "R4-forced-status-scaffolding", "R5-word-cap")], name

"""Completion gate: done+no evidence -> blocked; real test run -> allowed; phantom text -> blocked;
third attempt -> allowed with warning; weak evidence; failing output; format; chunk acceptance."""
import json
import subprocess
import sys
from pathlib import Path

from conftest import ROOT, hook_input
from harness import chunks as chunkmod
from harness import config, stop_gate

GOOD = "Fixed the off-by-one in add().\n- calc.py: use + instead of -\nVerification: python -m pytest -q → 1 passed\nBlockers: none"


def ev(hook, cfg=None):
    return stop_gate.evaluate(hook, cfg)


def test_done_without_evidence_is_blocked(transcript):
    t = transcript([("user", "fix add()"), ("tool", "Edit", {"file_path": "calc.py", "new_string": "a + b"}, "ok"), ("text", "Done — fixed add().")])
    out = ev(hook_input(transcript_path=str(t), last_assistant_message="Done — fixed add(). All tests pass now."))
    assert out.get("decision") == "block"
    assert "no evidence" in out["reason"] and "ran no test/build/lint/diff" in out["reason"]


def test_done_with_real_test_run_is_allowed(transcript):
    t = transcript([("user", "fix add()"), ("tool", "Edit", {"file_path": "calc.py"}, "ok"),
                    ("tool", "Bash", {"command": "python -m pytest -q"}, "....\n4 passed in 0.02s"), ("text", GOOD)])
    out = ev(hook_input(transcript_path=str(t), last_assistant_message=GOOD))
    assert "decision" not in out


def test_git_diff_counts_as_evidence(transcript):
    t = transcript([("user", "rename"), ("tool", "Bash", {"command": "git diff --stat"}, " calc.py | 2 +-\n 1 file changed"), ("text", GOOD)])
    out = ev(hook_input(transcript_path=str(t), last_assistant_message=GOOD))
    assert "decision" not in out


def test_phantom_tool_call_text_is_blocked(transcript):
    msg = 'Let me run the tests.\n<invoke name="Bash">\n<parameter name="command">pytest</parameter>\n</invoke>\nDone, all tests pass.'
    t = transcript([("user", "run tests"), ("text", msg)])
    out = ev(hook_input(transcript_path=str(t), last_assistant_message=msg))
    assert out["decision"] == "block" and "tool-call-shaped text" in out["reason"] and "never ran" in out["reason"]


def test_phantom_json_shape(transcript):
    msg = 'Running: {"type": "tool_use", "name": "Bash", "input": {"command": "npm test"}}'
    t = transcript([("user", "x"), ("text", msg)])
    assert ev(hook_input(transcript_path=str(t), last_assistant_message=msg))["decision"] == "block"


def test_third_attempt_allowed_with_warning(transcript):
    t = transcript([("user", "fix"), ("text", "Done.")])
    h = hook_input(transcript_path=str(t), last_assistant_message="Done. It is fixed.")
    assert ev(h)["decision"] == "block"
    assert ev(h)["decision"] == "block"
    third = ev(h)
    assert "decision" not in third and "allowed after 2 block(s)" in third["systemMessage"]
    # counter persisted per prompt id
    assert config.load_state("sess-1")["gate_attempts"]["p-1"] == 2
    # a new prompt starts fresh
    assert ev(hook_input(prompt_id="p-2", transcript_path=str(t), last_assistant_message="Done. It is fixed."))["decision"] == "block"


def test_weak_evidence_blocked_once(transcript):
    t = transcript([("user", "fix"), ("tool", "Bash", {"command": "pytest -k nothing || true"}, "collected 0 items\n"), ("text", GOOD)])
    h = hook_input(transcript_path=str(t), last_assistant_message=GOOD)
    out = ev(h)
    assert out["decision"] == "block" and "narrowed or unfalsifiable" in out["reason"]
    out2 = ev(h)  # second time: weak-only rule does not fire again; format ok -> allowed
    assert "decision" not in out2


def test_failing_output_with_success_claim_is_blocked(transcript):
    t = transcript([("user", "fix"), ("tool", "Bash", {"command": "python -m pytest -q"}, "F\n1 failed in 0.03s"), ("text", GOOD)])
    out = ev(hook_input(transcript_path=str(t), last_assistant_message=GOOD))
    assert out["decision"] == "block" and "shows failures" in out["reason"]


def test_format_enforced(transcript):
    t = transcript([("user", "fix"), ("tool", "Bash", {"command": "npm test"}, "Tests: 3 passed"), ("text", "Done, tests pass.")])
    msg = "Done, tests pass.\n- a\n- b\n- c\n- d\n- e"
    out = ev(hook_input(transcript_path=str(t), last_assistant_message=msg))
    assert out["decision"] == "block" and "Completion format missing" in out["reason"] and "5 bullets" in out["reason"]
    assert "no 'Verification:' line" in out["reason"]


def test_no_claim_no_block(transcript):
    t = transcript([("user", "what does add do?"), ("text", "It subtracts b from a — that is a bug. Want me to fix it?")])
    out = ev(hook_input(transcript_path=str(t), last_assistant_message="It subtracts b from a — that is a bug."))
    assert "decision" not in out


def test_tics_warn_and_block_modes(transcript):
    msg = GOOD + "\nHonestly, the load-bearing change is in calc.py."
    t = transcript([("user", "fix"), ("tool", "Bash", {"command": "pytest -q"}, "1 passed"), ("text", msg)])
    out = ev(hook_input(transcript_path=str(t), last_assistant_message=msg))
    assert "decision" not in out and "writing tics" in out["systemMessage"] and "load-bearing" in out["systemMessage"]
    cfg = dict(config.load_config()); cfg["tics.stop_mode"] = "block"
    out = ev(hook_input(transcript_path=str(t), last_assistant_message=msg), cfg)
    assert out["decision"] == "block" and "Rewrite without these phrases" in out["reason"]


def test_chunk_acceptance_required_and_marks_done(transcript, tmp_path):
    proj = tmp_path / "proj"
    chunkmod.save(chunkmod.new_plan("t", [{"goal": "fix add", "kind": "mechanical", "paths": ["calc.py"], "acceptance": ["python -m pytest -q tests/test_calc.py"]}]), proj)
    d = chunkmod.load(proj); d["active"] = 1; chunkmod.save(d, proj)
    t = transcript([("user", "run chunk 1"), ("tool", "Bash", {"command": "pytest -q"}, "1 passed"), ("text", GOOD)])
    out = ev(hook_input(transcript_path=str(t), last_assistant_message=GOOD))
    assert out["decision"] == "block" and "acceptance command" in out["reason"]
    t2 = transcript([("user", "run chunk 1"), ("tool", "Bash", {"command": "python -m pytest -q tests/test_calc.py"}, "1 passed"), ("text", GOOD)], name="t2.jsonl")
    out = ev(hook_input(prompt_id="p-9", transcript_path=str(t2), last_assistant_message=GOOD))
    assert "decision" not in out and "marked done" in out["systemMessage"]
    assert chunkmod.load(proj)["chunks"][0]["status"] == "done" and chunkmod.load(proj)["active"] is None


def test_effort_mismatch_is_info_only(transcript, tmp_path):
    proj = tmp_path / "proj"
    chunkmod.save(chunkmod.new_plan("t", [{"goal": "g", "kind": "feature", "paths": [], "acceptance": []}], "claude-opus-5"), proj)
    d = chunkmod.load(proj); d["active"] = 1; chunkmod.save(d, proj)
    t = transcript([("user", "x"), ("text", "still working on it")])
    out = ev(hook_input(transcript_path=str(t), last_assistant_message="still working on it", effort={"level": "xhigh"}))
    assert "decision" not in out and "recommends effort 'medium'" in out["systemMessage"]
    # a model without an effort parameter: no mismatch warning at all [S28]
    chunkmod.save(chunkmod.new_plan("t", [{"goal": "g", "kind": "feature", "paths": [], "acceptance": []}], "claude-haiku-4-5-20251001"), proj)
    d = chunkmod.load(proj); d["active"] = 1; chunkmod.save(d, proj)
    out = ev(hook_input(prompt_id="p-2", transcript_path=str(t), last_assistant_message="still working on it", effort={"level": "xhigh"}))
    assert "decision" not in out and "recommends effort" not in out.get("systemMessage", "")


def test_grounding_rule_per_tier(transcript, tmp_path):
    """G7 [S8]: a claim about an existing file nobody opened this turn is sent back once on lower tiers, never on Opus 5 / Fable."""
    proj = tmp_path / "proj"
    (proj / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    cfg = config.load_config("sonnet-5")
    assert cfg["gate.grounding"] == "block" and cfg["harness.profile"] == "sonnet-5"
    msg = "The function add in calc.py returns the difference of its arguments, so the bug is the minus sign."
    t = transcript([("user", "what does add do?"), ("text", msg)])
    out = ev(hook_input(transcript_path=str(t), last_assistant_message=msg), cfg)
    assert out["decision"] == "block" and "did not open" in out["reason"] and "calc.py" in out["reason"]
    assert "decision" not in ev(hook_input(transcript_path=str(t), last_assistant_message=msg), cfg)          # once per prompt
    t2 = transcript([("user", "x"), ("tool", "Read", {"file_path": str(proj / "calc.py")}, "def add"), ("text", msg)], name="t2.jsonl")
    assert "decision" not in ev(hook_input(prompt_id="p-2", transcript_path=str(t2), last_assistant_message=msg), cfg)   # read -> grounded
    t3 = transcript([("user", "x"), ("tool", "Bash", {"command": "sed -n '1,5p' calc.py"}, "def add"), ("text", msg)], name="t3.jsonl")
    assert "decision" not in ev(hook_input(prompt_id="p-3", transcript_path=str(t3), last_assistant_message=msg), cfg)   # bash view -> grounded
    msg2 = "The function add in nowhere.py returns the difference of its arguments."
    t4 = transcript([("user", "x"), ("text", msg2)], name="t4.jsonl")
    assert "decision" not in ev(hook_input(prompt_id="p-4", transcript_path=str(t4), last_assistant_message=msg2), cfg)  # file does not exist
    msg3 = "I could not verify what add in calc.py does; say the word and I will read it."
    t5 = transcript([("user", "x"), ("text", msg3)], name="t5.jsonl")
    assert "decision" not in ev(hook_input(prompt_id="p-5", transcript_path=str(t5), last_assistant_message=msg3), cfg)  # no claim verb
    for tier in ("opus-5", "fable-5"):
        c = config.load_config(tier)
        assert c["gate.grounding"] == "off", tier
        assert "decision" not in ev(hook_input(prompt_id="p-" + tier, transcript_path=str(t), last_assistant_message=msg), c)
    for tier in ("opus-4x", "sonnet-4x", "haiku", "generic"):
        assert config.load_config(tier)["gate.grounding"] == "block", tier


def test_grounding_env_override_wins(transcript, tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_GATE__GROUNDING", "off")
    assert config.load_config("haiku")["gate.grounding"] == "off"
    monkeypatch.setenv("HARNESS_GATE__GROUNDING", "block")
    assert config.load_config("opus-5")["gate.grounding"] == "block"


def test_gate_cli_detects_tier_from_cache(transcript, tmp_path):
    """The Stop hook has no `model` field [S20]; the CLI takes the tier from the SessionStart cache."""
    from harness import detect_model
    detect_model.write_cache("claude-haiku-4-5-20251001", "hook:SessionStart.model", "sess-1")
    proj = tmp_path / "proj"
    (proj / "calc.py").write_text("x = 1\n", encoding="utf-8")
    msg = "calc.py defines x and nothing else."
    t = transcript([("user", "x"), ("text", msg)], model="claude-haiku-4-5-20251001")   # same model as the cache
    r = subprocess.run([sys.executable, str(ROOT / "plugin" / "scripts" / "harness_cli.py"), "gate"],
                       input=json.dumps(hook_input(transcript_path=str(t), last_assistant_message=msg)), capture_output=True, text=True, timeout=60)
    assert json.loads(r.stdout)["decision"] == "block" and "did not open" in r.stdout
    log = (Path(__import__("os").environ["HARNESS_HOME"]) / "harness.log").read_text(encoding="utf-8")
    assert '"profile": "haiku"' in log


def test_stop_hook_shell_blocks(transcript):
    t = transcript([("user", "fix"), ("text", "Done.")])
    r = subprocess.run(["sh", str(ROOT / "plugin" / "hooks" / "stop-gate.sh")],
                       input=json.dumps(hook_input(transcript_path=str(t), last_assistant_message="Done, fixed.")),
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    assert json.loads(r.stdout)["decision"] == "block"


def test_static_transcript_fixtures():
    from conftest import FIXTURES
    base = FIXTURES / "transcripts"
    out = ev(hook_input(transcript_path=str(base / "done-no-evidence.jsonl"), last_assistant_message="Done — fixed add(), all tests pass."))
    assert out["decision"] == "block"
    out = ev(hook_input(prompt_id="p-2", transcript_path=str(base / "done-with-pytest.jsonl"), last_assistant_message=GOOD))
    assert "decision" not in out
    out = ev(hook_input(prompt_id="p-3", transcript_path=str(base / "phantom-tool-call.jsonl"), last_assistant_message=None))
    assert out["decision"] == "block" and "tool-call-shaped" in out["reason"]   # falls back to transcript text

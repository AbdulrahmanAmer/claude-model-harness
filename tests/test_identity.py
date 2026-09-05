"""Identity: hook stdin / statusline / transcript / env -> correct profile; unknown never guesses."""
import json
import subprocess
import sys
from pathlib import Path

from conftest import ROOT, hook_input
from harness import detect_model
from harness.config import model_cache_path

CLI = ROOT / "plugin" / "scripts" / "harness_cli.py"


def run_cli(args, stdin: dict | str | None = None, env=None):
    import os
    e = dict(os.environ)
    e.update(env or {})
    inp = json.dumps(stdin) if isinstance(stdin, dict) else (stdin or "")
    return subprocess.run([sys.executable, str(CLI), *args], input=inp, capture_output=True, text=True, env=e, timeout=30)


def test_profile_mapping_official_ids():
    assert detect_model.profile_for("claude-opus-5") == ("opus-5", "Claude Opus 5")
    assert detect_model.profile_for("claude-fable-5-1") == ("fable-5", "Claude Fable 5.1")
    assert detect_model.profile_for("claude-mythos-5-1")[0] == "fable-5"
    assert detect_model.profile_for("claude-fable-5")[0] == "fable-5"
    assert detect_model.profile_for("claude-opus-4-8") == ("opus-4x", "Claude Opus 4.8")
    assert detect_model.profile_for("claude-opus-4-5-20251101")[0] == "opus-4x"
    assert detect_model.profile_for("anthropic.claude-opus-5")[0] == "opus-5"
    assert detect_model.profile_for(None) == ("generic", "unknown")
    assert detect_model.profile_for("gpt-5") == ("generic", "unknown")


def test_profile_mapping_tiers_added_2026_09_05():
    """IDs from research/MODEL_MATRIX.md (S17, S18, S46, S48, S49, S50, S53)."""
    assert detect_model.profile_for("claude-sonnet-5") == ("sonnet-5", "Claude Sonnet 5")
    assert detect_model.profile_for("claude-sonnet-4-6") == ("sonnet-4x", "Claude Sonnet 4.6")
    assert detect_model.profile_for("claude-sonnet-4-5-20250929") == ("sonnet-4x", "Claude Sonnet 4.5")
    assert detect_model.profile_for("claude-haiku-4-5-20251001") == ("haiku", "Claude Haiku 4.5")
    assert detect_model.profile_for("claude-haiku-4-5") == ("haiku", "Claude Haiku 4.5")
    assert detect_model.profile_for("claude-opus-4-6") == ("opus-4x", "Claude Opus 4.6")
    assert detect_model.profile_for("claude-opus-4-7") == ("opus-4x", "Claude Opus 4.7")
    assert detect_model.profile_for("anthropic.claude-sonnet-5")[0] == "sonnet-5"
    assert detect_model.profile_for("claude-3-5-haiku-20241022") == ("generic", "claude-3-5-haiku-20241022")  # retired [S18]
    for tier in detect_model.TIERS:
        assert (ROOT / "plugin" / "profiles" / f"{tier}.md").is_file(), tier


def test_session_start_model_field_wins_and_caches(tmp_path):
    d = detect_model.detect(hook_input(hook_event_name="SessionStart", model="claude-opus-5", source="startup"))
    assert d["model_id"] == "claude-opus-5" and d["profile"] == "opus-5" and d["source"].startswith("hook:SessionStart")
    assert json.loads(model_cache_path().read_text())["model_id"] == "claude-opus-5"


def test_post_model_switch_to_model():
    d = detect_model.detect({"hook_event_name": "PostModelSwitch", "from_model": "claude-opus-5", "to_model": "claude-fable-5-1", "session_id": "s"})
    assert d["profile"] == "fable-5" and "PostModelSwitch" in d["source"]


def test_statusline_cache_fallback(tmp_path):
    p = model_cache_path(); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"model_id": "claude-opus-4-8", "source": "statusline:model.id", "session_id": "sess-1"}))
    d = detect_model.detect(hook_input())
    assert d["model_id"] == "claude-opus-4-8" and d["profile"] == "opus-4x" and d["source"].startswith("cache:statusline")


def test_transcript_fallback_is_marked_unverified(transcript):
    t = transcript([("user", "hi"), ("text", "hello")], model="claude-fable-5-1")
    d = detect_model.detect(hook_input(transcript_path=str(t)))
    assert d["model_id"] == "claude-fable-5-1" and d["profile"] == "fable-5"
    assert "UNVERIFIED" in d["source"]


def test_env_alias_is_never_trusted(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "opus")          # alias -> not a full ID [S28]
    d = detect_model.detect(hook_input())
    assert d["model_id"] is None and d["profile"] == "generic"
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-5")   # full ID -> low-confidence fallback
    d = detect_model.detect(hook_input())
    assert d["model_id"] == "claude-opus-5" and d["confidence"] == "low"


def test_unknown_never_guesses():
    d = detect_model.detect(hook_input())
    assert d == {"model_id": None, "display_name": "unknown", "profile": "generic", "source": "none", "confidence": "none"}


def test_identity_output_opus5():
    r = run_cli(["identity"], hook_input(hook_event_name="SessionStart", model="claude-opus-5", source="startup"))
    assert r.returncode == 0
    assert r.stdout.startswith("[claude-model-harness plugin")
    assert "\nMODEL IDENTITY: You are running as claude-opus-5 (Claude Opus 5). Apply profile: opus-5." in r.stdout
    assert "PROFILE opus-5" in r.stdout and "COMPLETION FORMAT" in r.stdout
    from harness import doctor
    from pathlib import Path
    prof = ROOT / "plugin" / "profiles" / "opus-5.md"
    assert not [f for f in doctor.scan_file(prof, "opus-5") if f.rule == "R1-verification-instruction"]


def test_identity_output_unknown():
    r = run_cli(["identity"], hook_input(hook_event_name="SessionStart", source="startup"))
    assert r.returncode == 0
    assert "MODEL IDENTITY: not detectable by the harness" in r.stdout
    assert "state your exact model ID" in r.stdout and "PROFILE generic" in r.stdout
    assert "opus-5" not in r.stdout.split("PROFILE")[0]


def test_identity_output_fable_and_opus4x():
    r = run_cli(["identity"], hook_input(model="claude-fable-5-1"))
    assert "PROFILE fable-5" in r.stdout and "mannered prose" in r.stdout
    r = run_cli(["identity"], hook_input(model="claude-opus-4-8"))
    assert "PROFILE opus-4x" in r.stdout


def test_transcript_newer_than_cache_wins_and_resume_is_provisional(transcript):
    """Seen live (tests/REPORT.md §6): `claude -p --resume <id> --model claude-opus-5` re-injected the previous model from the
    transcript and no model field arrived [S20]. Now: newer transcript evidence beats a stale cache, and a resume/fork
    without a model field gets a provisional line that defers to the system prompt."""
    p = model_cache_path(); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"model_id": "claude-sonnet-5", "source": "hook:SessionStart.model", "session_id": "sess-1"}))
    t = transcript([("user", "hi"), ("text", "hello")], model="claude-opus-5")
    d = detect_model.detect(hook_input(transcript_path=str(t)))
    assert d["model_id"] == "claude-opus-5" and d["profile"] == "opus-5" and d["source"].startswith("transcript")
    # resume without a model field: provisional wording, cache dropped, system prompt declared authoritative
    p.write_text(json.dumps({"model_id": "claude-sonnet-5", "source": "hook:SessionStart.model", "session_id": "sess-1"}))
    r = run_cli(["identity"], hook_input(hook_event_name="SessionStart", source="resume", transcript_path=str(t)))
    assert "MODEL IDENTITY (provisional): the last model seen for this session was claude-opus-5" in r.stdout
    assert "If your system prompt names a different model, that is authoritative" in r.stdout
    assert "Do not claim to be a different model" not in r.stdout and "PROFILE opus-5" in r.stdout
    assert not p.is_file()
    # a hook-provided model is still definitive
    r = run_cli(["identity"], hook_input(hook_event_name="SessionStart", source="resume", model="claude-haiku-4-5-20251001", transcript_path=str(t)))
    assert "MODEL IDENTITY: You are running as claude-haiku-4-5-20251001" in r.stdout and "Do not claim to be a different model" in r.stdout
    # startup with only transcript evidence is provisional too
    r = run_cli(["identity"], hook_input(hook_event_name="SessionStart", source="startup", transcript_path=str(t)))
    assert "(provisional)" in r.stdout and "Apply profile: opus-5" not in r.stdout and "Applying profile: opus-5" in r.stdout


def test_identity_output_lower_tiers():
    r = run_cli(["identity"], hook_input(model="claude-sonnet-5"))
    assert "MODEL IDENTITY: You are running as claude-sonnet-5 (Claude Sonnet 5). Apply profile: sonnet-5." in r.stdout
    assert "PROFILE sonnet-5" in r.stdout and "Self-check" in r.stdout and "USEFUL OUTPUT" in r.stdout
    r = run_cli(["identity"], hook_input(model="claude-haiku-4-5-20251001"))
    assert "Apply profile: haiku." in r.stdout and "PROFILE haiku" in r.stdout and "effort parameter is not supported" in r.stdout
    r = run_cli(["identity"], hook_input(model="claude-sonnet-4-6"))
    assert "PROFILE sonnet-4x" in r.stdout and "(4.6)" in r.stdout
    r = run_cli(["identity"], hook_input(model="claude-opus-4-6"))
    assert "PROFILE opus-4x" in r.stdout and "predilection for subagents" in r.stdout
    # every tier gets the shared block, in the same position (after the profile, before the completion format)
    for mid in ("claude-fable-5-1", "claude-opus-5", "claude-opus-4-8", "claude-sonnet-5", "claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001"):
        out = run_cli(["identity"], hook_input(model=mid)).stdout
        assert out.index("PROFILE ") < out.index("USEFUL OUTPUT") < out.index("COMPLETION FORMAT") < out.index("WRITING"), mid


def test_identity_output_under_hook_cap():
    """Claude Code caps hook stdout at 10,000 characters and replaces longer output with a file preview [S20]."""
    from harness_cli import HOOK_OUTPUT_CAP
    assert HOOK_OUTPUT_CAP == 10_000
    ids = {"fable-5": "claude-fable-5-1", "opus-5": "claude-opus-5", "opus-4x": "claude-opus-4-8", "sonnet-5": "claude-sonnet-5",
           "sonnet-4x": "claude-sonnet-4-6", "haiku": "claude-haiku-4-5-20251001", "generic": "claude-opus-3-20240229"}
    assert set(ids) == set(detect_model.TIERS)
    for tier, mid in ids.items():
        out = run_cli(["identity"], hook_input(model=mid)).stdout
        assert f"Apply profile: {tier}." in out, tier
        assert len(out) < HOOK_OUTPUT_CAP - 500, (tier, len(out))       # 500 chars of headroom for the CHUNK MODE line
        assert "profile truncated" not in out
    out = run_cli(["identity"], hook_input()).stdout                       # unknown model
    assert len(out) < HOOK_OUTPUT_CAP - 500 and "profile truncated" not in out


def test_shell_hook_session_start_end_to_end(tmp_path):
    hook = ROOT / "plugin" / "hooks" / "session-start.sh"
    r = subprocess.run(["sh", str(hook)], input=json.dumps(hook_input(hook_event_name="SessionStart", model="claude-opus-5", source="compact")),
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "MODEL IDENTITY: You are running as claude-opus-5" in r.stdout
    log = Path(__import__("os").environ["HARNESS_HOME"]) / "harness.log"
    assert log.is_file() and "session_start" in log.read_text()

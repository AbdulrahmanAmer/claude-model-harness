"""Doctor: cruft fixture -> every planted issue flagged with a citation; --apply produces the expected diff; clean -> zero."""
import json
import shutil
import subprocess
import sys

from conftest import FIXTURES, ROOT
from harness import doctor

PLANTED = {
    "R1-verification-instruction": ["double-check", "final verification step", "re-verify every change"],
    "R2-thoroughness-cruft": ["Be extremely thorough", "CRITICAL: you MUST"],
    "R3-no-thinking-rule": ["Do not think out loud"],
    "R4-forced-status-scaffolding": ["After every 3 tool calls"],
    "R5-word-cap": ["under 150 words"],
    "R6-fable-anti-formatting": ["Never use bullet points"],
    "R7-fable-hold-findings": ["Hold all findings"],
    "R8-long-prompt-no-reminder": [],
    "R9-duplicate-instruction": ["Use pnpm for everything"],
    "R11-thinking-disabled": [],
    "R13-effort-high-routine": [],
    "R14-no-subagent-cap": [],
}


def _copy(tmp_path):
    dst = tmp_path / "cruft"
    shutil.copytree(FIXTURES / "cruft-project", dst)
    return dst


def test_every_planted_issue_flagged_with_citation(tmp_path):
    proj = _copy(tmp_path)
    fs = doctor.run(proj, tmp_path / "nohome", "opus-5")
    rules = {f.rule for f in fs}
    for rule, snippets in PLANTED.items():
        assert rule in rules, f"{rule} not flagged"
        for s in snippets:
            assert any(f.rule == rule and s.lower() in f.text.lower() for f in fs), f"{rule}: '{s}' not found"
    for f in fs:
        assert "[S" in f.why or "COMMUNITY" in f.why, f"{f.rule} has no citation: {f.why}"
    # severities that matter on opus-5
    assert {f.severity for f in fs if f.rule == "R1-verification-instruction"} == {"error"}
    assert any(f.rule == "R11-thinking-disabled" and f.severity == "error" for f in fs)  # xhigh + thinking off -> 400 [S2]
    # rules dir and settings scanned
    assert any("rules/testing.md" in f.file.replace("\\", "/") for f in fs)
    assert any(f.file.endswith("settings.json") for f in fs)


def test_profile_changes_severity(tmp_path):
    proj = _copy(tmp_path)
    fab = doctor.run(proj, tmp_path / "nohome", "fable-5")
    assert {f.severity for f in fab if f.rule == "R1-verification-instruction"} == {"info"}
    assert {f.severity for f in fab if f.rule == "R7-fable-hold-findings"} == {"warning"}
    assert not any(f.rule == "R15-missing-conciseness" for f in fab)


def test_clean_project_zero_findings(tmp_path):
    fs = doctor.run(FIXTURES / "clean-project", tmp_path / "nohome", "opus-5")
    assert fs == [], [f.rule for f in fs]


def test_apply_diff_and_write(tmp_path):
    proj = _copy(tmp_path)
    fs = doctor.run(proj, tmp_path / "nohome", "opus-5")
    edits = doctor.planned_edits(fs)
    diff = doctor.unified_diff(edits)
    assert "-- Always double-check your answer before responding." in diff
    assert "-- Include a final verification step" in diff
    assert "-- Do not think out loud" in diff
    assert "-- After every 3 tool calls" in diff
    assert "-- Keep all answers under 150 words." not in diff        # info-level: reported, not edited
    assert "+<tone_preference>" in diff                              # R8 append
    assert "+Keep responses focused, brief, and concise" in diff     # R15 append
    before = (proj / "CLAUDE.md").read_text()
    written = doctor.apply(edits)
    assert str(proj / "CLAUDE.md") in written
    after = (proj / "CLAUDE.md").read_text()
    assert "double-check" not in after and "<tone_preference>" in after
    assert (proj / "CLAUDE.md.harness.bak").read_text() == before
    assert doctor.run(proj, tmp_path / "nohome", "opus-5") and not any(f.rule == "R1-verification-instruction" and f.file.endswith("CLAUDE.md") and "rules" not in f.file for f in doctor.run(proj, tmp_path / "nohome", "opus-5"))


def test_apply_move_mode_keeps_removed_lines(tmp_path, monkeypatch):
    proj = _copy(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    fs = doctor.run(proj, tmp_path / "nohome", "opus-5")
    edits = doctor.planned_edits(fs, mode="move")
    doctor.apply(edits)
    kept = (proj / ".claude" / "harness" / "removed-instructions.md").read_text()
    assert "double-check" in kept


def test_cli_dry_run_writes_nothing(tmp_path):
    proj = _copy(tmp_path)
    before = (proj / "CLAUDE.md").read_text()
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "doctor.py"), "--project", str(proj), "--home", str(tmp_path / "nohome"), "--profile", "opus-5"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "[ERROR] R1-verification-instruction" in r.stdout and "proposed changes (dry run)" in r.stdout
    assert "Re-run with --apply" in r.stdout
    assert (proj / "CLAUDE.md").read_text() == before
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "doctor.py"), "--project", str(proj), "--home", str(tmp_path / "nohome"), "--profile", "opus-5", "--json"],
                       capture_output=True, text=True, timeout=60)
    data = json.loads(r.stdout)
    assert data["profile"] == "opus-5" and len(data["findings"]) >= 10


# ---------------------------------------------------------------- tier matrix (research/MODEL_MATRIX.md)
# expected severity per rule per tier fixture; None = the rule must not fire on that fixture
TIER_EXPECT = {
    "fable-5":   ("claude-fable-5-1",        {"R1": "info", "R2": "warning", "R6": "warning", "R7": "warning", "R11": "info", "R16": "info", "R15": None, "R3": None}),
    "opus-5":    ("claude-opus-5",            {"R1": "error", "R3": "error", "R4": "warning", "R11": "error", "R13": "info", "R14": "info", "R15": "warning", "R16": "info", "R17": None}),
    "opus-4x":   ("claude-opus-4-6",          {"R1": "info", "R2": "warning", "R3": "warning", "R4": "warning", "R17": "info", "R14": "info", "R15": "info", "R16": "info", "R13": None}),
    "sonnet-5":  ("claude-sonnet-5",          {"R1": "info", "R2": "info", "R3": "info", "R4": "warning", "R11": "warning", "R15": "info", "R16": None, "R17": None}),
    "sonnet-4x": ("claude-sonnet-4-6",        {"R1": "info", "R2": "warning", "R4": "info", "R17": "info", "R15": None, "R16": None, "R14": None}),
    "haiku":     ("claude-haiku-4-5-20251001", {"R1": "info", "R2": "info", "R3": "info", "R11": "info", "R17": "info", "R15": None, "R16": None, "R14": None}),
    "generic":   (None,                       {"R1": "warning", "R3": "warning", "R11": "warning", "R15": None, "R16": None, "R17": None}),
}


def _by_rule(findings):
    out = {}
    for f in findings:
        out.setdefault(f.rule.split("-", 1)[0], set()).add(f.severity)
    return out


def test_tier_severity_matrix(tmp_path):
    for tier, (model_id, expect) in TIER_EXPECT.items():
        src = FIXTURES / f"{tier}-project"
        assert src.is_dir(), tier
        proj = tmp_path / tier
        shutil.copytree(src, proj)
        fs = doctor.run(proj, tmp_path / "nohome", tier, model_id)
        got = _by_rule(fs)
        for rule, sev in expect.items():
            if sev is None:
                assert rule not in got, (tier, rule, got.get(rule))
            else:
                assert got.get(rule) == {sev}, (tier, rule, got.get(rule), sev)
        for f in fs:
            assert "[S" in f.why or "COMMUNITY" in f.why, (tier, f.rule, f.why)
        # the self-check line is auto-removed only on Opus 5 [S1]; everywhere else (incl. unknown model) it is reported, never edited
        edits = doctor.planned_edits(fs)
        joined = "".join(after for (_, after) in edits.values()) or (proj / "CLAUDE.md").read_text(encoding="utf-8")
        if tier != "opus-5":
            assert "double-check" in joined, tier
        else:
            assert "double-check" not in joined


def test_model_specific_settings_rules(tmp_path):
    proj = tmp_path / "p"; shutil.copytree(FIXTURES / "opus-4x-project", proj)
    # Opus 4.8 supports xhigh -> no R17 and no 4.6 subagent note; Opus 4.6 -> both [S28, S8]
    got48 = _by_rule(doctor.run(proj, tmp_path / "nohome", "opus-4x", "claude-opus-4-8"))
    assert "R17" not in got48 and "R14" not in got48
    got46 = _by_rule(doctor.run(proj, tmp_path / "nohome", "opus-4x", "claude-opus-4-6"))
    assert got46["R17"] == {"info"} and got46["R14"] == {"info"}
    # Haiku 4.5: effort not supported at all -> R17 says "no effect"
    proj2 = tmp_path / "h"; shutil.copytree(FIXTURES / "haiku-project", proj2)
    f = next(f for f in doctor.run(proj2, tmp_path / "nohome", "haiku", "claude-haiku-4-5-20251001") if f.rule.startswith("R17"))
    assert "no effect" in f.why and "[S28]" in f.why
    # unknown model id -> R17 never fires
    assert "R17" not in _by_rule(doctor.run(proj2, tmp_path / "nohome", "haiku", None))


def test_explain_rule_prints_per_tier_reasoning():
    txt = doctor.explain("R1")
    for tier in doctor.TIERS:
        assert tier in txt, tier
    assert "error" in txt and "info" in txt and "[S1" in txt and "[S8" in txt and "regex" in txt
    assert doctor.explain("R1-verification-instruction") == txt
    txt2 = doctor.explain("R17")
    assert "S28" in txt2 and "checks:" in txt2
    assert "unknown rule" in doctor.explain("R99")
    assert set(doctor.rule_ids()) >= {"R1-verification-instruction", "R9-duplicate-instruction", "R17-effort-unsupported"}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "doctor.py"), "--explain", "R2"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "R2-thoroughness-cruft" in r.stdout and "sonnet-5" in r.stdout and "[S45]" in r.stdout
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "doctor.py"), "--list-rules"], capture_output=True, text=True, timeout=60)
    assert "R1-verification-instruction" in r.stdout


def test_duplicates_skip_frontmatter_and_labels(tmp_path):
    """Seen live: 156 R9 warnings because every SKILL.md shares `disable-model-invocation: true` in its frontmatter."""
    proj = tmp_path / "p"; (proj / ".claude" / "skills" / "a").mkdir(parents=True); (proj / ".claude" / "skills" / "b").mkdir(parents=True)
    front = "---\nname: {n}\ndescription: skill {n} does a thing for the user\ndisable-model-invocation: true\n---\n"
    (proj / ".claude" / "skills" / "a" / "SKILL.md").write_text(front.format(n="a") + "Gather this context (ask if not provided):\nRun the thing for skill a with the given arguments.\n", encoding="utf-8")
    (proj / ".claude" / "skills" / "b" / "SKILL.md").write_text(front.format(n="b") + "Gather this context (ask if not provided):\nRun the thing for skill b with the given arguments.\n", encoding="utf-8")
    (proj / "CLAUDE.md").write_text("Keep responses concise. Deliver what was asked, at the scope intended.\n", encoding="utf-8")
    fs = doctor.run(proj, tmp_path / "nohome", "sonnet-5")
    assert not [f for f in fs if f.rule.startswith("R9")], [(f.text) for f in fs if f.rule.startswith("R9")]
    # a real duplicated instruction body is still caught
    (proj / ".claude" / "skills" / "b" / "SKILL.md").write_text(front.format(n="b") + "Run the thing for skill a with the given arguments.\n", encoding="utf-8")
    fs = doctor.run(proj, tmp_path / "nohome", "sonnet-5")
    assert [f for f in fs if f.rule.startswith("R9")]


def test_apply_preserves_crlf_line_endings(tmp_path):
    proj = tmp_path / "crlf"; proj.mkdir()
    body = "# Project\r\n- Always double-check your answer before responding.\r\nKeep responses concise. Deliver what was asked, at the scope intended.\r\n"
    (proj / "CLAUDE.md").write_bytes(body.encode("utf-8"))
    fs = doctor.run(proj, tmp_path / "nohome", "opus-5")
    edits = doctor.planned_edits(fs)
    doctor.apply(edits)
    raw = (proj / "CLAUDE.md").read_bytes()
    assert b"double-check" not in raw and b"\r\n" in raw and b"\n\n\n" not in raw
    assert raw.count(b"\r\n") == raw.count(b"\n")          # no bare LF introduced


def test_cli_apply(tmp_path):
    proj = _copy(tmp_path)
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "doctor.py"), "--project", str(proj), "--home", str(tmp_path / "nohome"), "--profile", "opus-5", "--apply"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "applied to:" in r.stdout
    assert "double-check" not in (proj / "CLAUDE.md").read_text()

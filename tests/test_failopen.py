"""Fail-open: corrupt stdin, missing jq, missing python, missing transcript, missing plugin files -> exit 0 and log."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT, hook_input

HOOKS = ROOT / "plugin" / "hooks"
# The two PATH-shim tests build a fake bin dir out of symlinks to `command -v` results; under Git Bash
# those are MSYS paths (/usr/bin/sh) that a Windows symlink cannot resolve. CI runs them on Linux/macOS.
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="PATH shim via symlinks needs POSIX")


def run_hook(name, stdin, env_extra=None, path=None):
    env = dict(os.environ)
    env.update(env_extra or {})
    if path is not None:
        env["PATH"] = path
    return subprocess.run(["sh", str(HOOKS / name)], input=stdin, capture_output=True, text=True, env=env, timeout=30)


def log_text():
    p = Path(os.environ["HARNESS_HOME"]) / "harness.log"
    return p.read_text() if p.is_file() else ""


def test_corrupt_stdin_all_hooks():
    for h in ("session-start.sh", "stop-gate.sh", "user-prompt-submit.sh", "post-tool-use.sh", "pre-tool-use.sh", "model-switch.sh"):
        r = run_hook(h, "{not json")
        assert r.returncode == 0, (h, r.stderr)
        assert not r.stdout.strip().startswith('{"decision"'), h
    assert "stdin_parse_error" in log_text()


def test_empty_stdin():
    for h in ("session-start.sh", "stop-gate.sh"):
        r = run_hook(h, "")
        assert r.returncode == 0


@posix_only
def test_missing_jq_still_works(tmp_path):
    # a PATH with python but without jq
    bindir = tmp_path / "bin"; bindir.mkdir()
    import sys
    (bindir / "python3").symlink_to(sys.executable)
    for tool in ("sh", "cat", "date", "basename", "dirname", "mkdir", "tr", "cut", "timeout", "printf"):
        src = subprocess.run(["sh", "-c", f"command -v {tool}"], capture_output=True, text=True).stdout.strip()
        if src and not (bindir / tool).exists():
            (bindir / tool).symlink_to(src)
    r = run_hook("stop-gate.sh", json.dumps(hook_input(last_assistant_message="Done, fixed.")), path=str(bindir))
    assert r.returncode == 0
    assert json.loads(r.stdout)["decision"] == "block"   # gate still works without jq


@posix_only
def test_missing_python_logs_and_exits_zero(tmp_path):
    bindir = tmp_path / "bin"; bindir.mkdir()
    for tool in ("sh", "cat", "date", "basename", "dirname", "mkdir", "tr", "cut", "printf"):
        src = subprocess.run(["sh", "-c", f"command -v {tool}"], capture_output=True, text=True).stdout.strip()
        if src:
            (bindir / tool).symlink_to(src)
    r = run_hook("stop-gate.sh", json.dumps(hook_input(last_assistant_message="Done, fixed.")), path=str(bindir))
    assert r.returncode == 0 and r.stdout.strip() == ""
    assert "python_missing" in log_text()


def test_missing_transcript_path():
    r = run_hook("stop-gate.sh", json.dumps(hook_input(transcript_path="/nonexistent/x.jsonl", last_assistant_message="Done, fixed.")))
    assert r.returncode == 0 and json.loads(r.stdout)["decision"] == "block"   # evaluates last_assistant_message alone


def test_garbage_transcript(tmp_path):
    t = tmp_path / "t.jsonl"; t.write_bytes(b"\x00\xff{{{{\n{\"type\":\"assistant\"}\nnot json\n")
    r = run_hook("stop-gate.sh", json.dumps(hook_input(transcript_path=str(t), last_assistant_message="thinking about it")))
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_broken_plugin_root():
    r = run_hook("session-start.sh", json.dumps(hook_input(model="claude-opus-5")), env_extra={"CLAUDE_PLUGIN_ROOT": "/nonexistent"})
    assert r.returncode == 0 and r.stdout.strip() == ""
    assert "cli_missing" in log_text()


def test_gate_disabled_by_env():
    r = run_hook("stop-gate.sh", json.dumps(hook_input(last_assistant_message="Done, fixed.")), env_extra={"HARNESS_GATE__ENABLED": "false"})
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_timeout_never_blocks(tmp_path):
    """A hung gate must never hold the turn: the shell `timeout` (where it exists) or the CLI's own watchdog
    (everywhere, incl. macOS which ships no timeout(1)) ends it, the hook exits 0 with no output, and the log says so."""
    import shutil, time
    root = tmp_path / "plug"
    shutil.copytree(ROOT / "plugin", root)
    (root / "scripts" / "harness" / "stop_gate.py").write_text("import time\ndef evaluate(hook_input, cfg=None):\n    time.sleep(30)\n    return {}\n")
    t0 = time.time()
    r = run_hook("stop-gate.sh", json.dumps(hook_input(last_assistant_message="Done.")), env_extra={"CLAUDE_PLUGIN_ROOT": str(root), "HARNESS_TIMEOUT": "2"})
    assert r.returncode == 0 and r.stdout.strip() == ""
    assert time.time() - t0 < 25
    log = log_text()
    assert "cli_timeout" in log or "cli_nonzero" in log, log


def test_watchdog_fires_without_external_timeout(tmp_path):
    """The Python watchdog alone (no `timeout` binary involved): exit 124, no stdout, `cli_timeout` logged."""
    import shutil, subprocess as sp, sys as _sys, time
    root = tmp_path / "plug"
    shutil.copytree(ROOT / "plugin", root)
    (root / "scripts" / "harness" / "stop_gate.py").write_text("import time\ndef evaluate(hook_input, cfg=None):\n    time.sleep(30)\n    return {}\n")
    env = dict(os.environ); env["HARNESS_TIMEOUT"] = "2"
    t0 = time.time()
    r = sp.run([_sys.executable, str(root / "scripts" / "harness_cli.py"), "gate"], input=json.dumps(hook_input(last_assistant_message="Done.")),
               capture_output=True, text=True, env=env, timeout=40)
    assert r.returncode == 124 and r.stdout.strip() == "" and time.time() - t0 < 25
    assert "cli_timeout" in log_text()

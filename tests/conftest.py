import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "scripts"))
sys.path.insert(0, str(ROOT / "api" / "python"))

FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every test gets its own HARNESS_HOME so logs/state/cache never touch ~/.claude."""
    home = tmp_path / "claude-home"
    home.mkdir()
    monkeypatch.setenv("HARNESS_HOME", str(home))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "proj"))
    (tmp_path / "proj").mkdir()
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    for k in list(os.environ):
        if k.startswith("HARNESS_") and k != "HARNESS_HOME":
            monkeypatch.delenv(k)
    return home


# --------------------------------------------------------------- transcript builder
def _user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def _assistant(blocks, model="claude-opus-5"):
    return {"type": "assistant", "message": {"role": "assistant", "model": model, "content": blocks}}


def _tool_result(tool_id, text):
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": [{"type": "text", "text": text}]}]}}


def make_transcript(path: Path, steps, model="claude-opus-5"):
    """steps: list of ('user', text) | ('text', text) | ('tool', name, input, result_text)"""
    lines = []
    n = 0
    for s in steps:
        if s[0] == "user":
            lines.append(_user(s[1]))
        elif s[0] == "text":
            lines.append(_assistant([{"type": "text", "text": s[1]}], model))
        elif s[0] == "tool":
            n += 1
            tid = f"toolu_{n:04d}"
            lines.append(_assistant([{"type": "tool_use", "id": tid, "name": s[1], "input": s[2]}], model))
            lines.append(_tool_result(tid, s[3]))
    path.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def transcript(tmp_path):
    def _mk(steps, model="claude-opus-5", name="t.jsonl"):
        return make_transcript(tmp_path / name, steps, model)
    return _mk


def hook_input(**kw):
    base = {"session_id": "sess-1", "prompt_id": "p-1", "cwd": "/tmp", "hook_event_name": "Stop",
            "stop_hook_active": False, "permission_mode": "default"}
    base.update(kw)
    return base

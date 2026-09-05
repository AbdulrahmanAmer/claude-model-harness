"""Configuration and state for claude-model-harness.

Precedence (last wins): built-in defaults -> ~/.claude/harness.json -> <project>/.claude/harness.json
-> HARNESS_* environment variables. All loading is fail-open: a broken file is logged and ignored.

Files written by the harness (never inside the user's project unless chunk mode creates
`.claude/harness/chunks.json` on explicit request):
  ~/.claude/harness.log                  structured log, one JSON object per line
  ~/.claude/harness/model.json           last detected model (cache shared by hooks/statusline)
  ~/.claude/harness/state/<session>.json per-session counters (gate attempts, prompt count)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    # --- completion gate -------------------------------------------------------------
    "gate.enabled": True,
    "gate.max_blocks_per_prompt": 2,          # then allow with a visible warning (never trap)
    "gate.require_format": True,              # outcome · <=3 bullets · verification · blockers
    "gate.max_bullets": 3,
    "gate.completion_patterns": [
        r"\b(all|the) tests? (now )?pass(es|ed|ing)?\b",
        r"\b(is|are|it's|its|now) (fully )?(done|complete|completed|fixed|implemented|working|resolved|finished|ready)\b",
        r"^\s*(done|fixed|implemented|completed|finished|resolved)\b",
        r"\b(done|fixed|implemented|completed|finished|resolved|all set|good to go)[.!]\s*$",
        r"\b(i|i've|i have) (fixed|implemented|completed|finished|resolved|added|updated|refactored) \b",
        r"\bsuccessfully (fixed|implemented|completed|added|updated|deployed|migrated)\b",
        r"\btask (is )?complete\b",
        r"\bbuild (passes|succeeds|succeeded|is green)\b",
        r"\bship(ped|pable)?\b",
    ],
    # tool calls that count as verification evidence (matched against Bash `command`)
    "gate.evidence_commands": [
        r"\b(pytest|py\.test|python -m pytest|python -m unittest|unittest)\b",
        r"\b(npm|pnpm|yarn|bun)( run)? (test|lint|build|typecheck|check)\b",
        r"\b(npx|bunx) (jest|vitest|mocha|tsc|eslint|playwright|cypress)\b",
        r"\b(jest|vitest|mocha|tsc|eslint|ruff|flake8|mypy|pyright|black --check)\b",
        r"\b(cargo|go|mvn|gradle|dotnet|make|cmake|ninja|swift|zig) (test|build|check|vet|clippy)\b",
        r"\b(rspec|rake test|bundle exec rspec|phpunit|mix test|sbt test|ctest)\b",
        r"\bgit (diff|status|log)\b",
    ],
    # tool_result text that shows a real outcome was observed
    "gate.result_patterns": [
        r"\b\d+ (passed|failed|errors?|skipped|tests?|examples?|specs?)\b",
        r"\b(PASS|FAIL|OK|ok|passed|failed|error)\b",
        r"\bTests?:\s*\d+",
        r"\bexit (code|status)[: ]+\d+",
        r"\b(compiled|built|build succeeded|BUILD SUCCESS|BUILD FAILED|warning|error)\b",
        r"^(diff --git|[MADRU?]{1,2} |\+\+\+ |--- )",
        r"\b\d+ files? changed\b|\|\s*\d+ [+-]+|\b(modified|new file|deleted|renamed):|nothing to commit|On branch\b",
    ],
    # evidence that looks rigged or narrowed (community-reported patterns, see COMMUNITY.md)
    "gate.weak_evidence_patterns": [
        r"\|\|\s*true\b",
        r"--no-verify\b",
        r"\b(-k|--filter|--grep|-t|--testNamePattern)\s+\S+",
        r"\b0 (tests?|passed|examples?)\b",
        r"\bno tests? (ran|collected|found)\b",
        r"\bcollected 0 items\b",
        r"\bgit (checkout|switch) (main|master)\b",
        r"\bgit stash\b",
        r"\b(skip|xfail|only)\(",
    ],
    "gate.phantom_patterns": [
        r"<\s*(antml:)?invoke\b",
        r"<\s*(antml:)?function_calls\b",
        r"<\s*(antml:)?parameter\b",
        r"<\s*tool_(call|use)\b",
        r"\"type\"\s*:\s*\"tool_use\"",
        r"\"tool_use_id\"\s*:",
        r"\"name\"\s*:\s*\"(Bash|Read|Write|Edit|MultiEdit|Grep|Glob|Agent|WebFetch|WebSearch)\"\s*,\s*\"input\"",
    ],
    # --- grounding rule G7 (per-tier default below): a factual claim about an existing project file that no
    # Read/Grep/Glob/Edit/Bash call touched this turn is sent back once with "read the file, then answer".
    # Official basis: "Never speculate about code you have not opened. If the user references a specific file,
    # you MUST read the file before answering" [src: S8]. off | block
    "gate.grounding": "off",
    "gate.grounding_extensions": ["py", "js", "ts", "tsx", "jsx", "mjs", "cjs", "json", "yml", "yaml", "toml", "ini", "cfg",
                                  "md", "rst", "txt", "sh", "bash", "ps1", "go", "rs", "java", "kt", "rb", "php", "c", "h",
                                  "cc", "cpp", "hpp", "cs", "swift", "sql", "html", "css", "scss", "vue", "svelte"],
    "gate.grounding_claim_patterns": [
        r"\b(is|are|gets?|was|were) (defined|declared|implemented|located|configured|registered|handled|imported|exported|set|called|used|read|written) (in|by|at|from)\b",
        r"\b(defines|declares|implements|contains|handles|exports|imports|registers|calls|returns|raises|throws|reads|writes|uses|expects|accepts|takes|has|lacks|does not|doesn't|never|always) \b",
        r"\bthe (function|method|class|module|file|script|config|constant|variable|hook|route|handler|component) [`'\"\w.]+ (does|returns|takes|accepts|raises|throws|is|has|contains|calls|checks|handles|reads|writes)\b",
        r"\bthere (is|are) no\b|\bno (function|class|method|reference|call|import) (to|of|named)\b",
        r"\b(already|currently|only) (contains|handles|returns|does|has|checks|calls|imports|exports)\b",
    ],
    # --- tics --------------------------------------------------------------------------
    "tics.stop_mode": "warn",                 # off | warn | block
    "tics.files_mode": "warn",                # off | warn  (PostToolUse cannot block)
    "tics.file_globs": ["*.md", "*.txt", "*.rst", "*.mdx"],
    "tics.max_hits_before_block": 2,          # only used when stop_mode == block
    # --- reminders ---------------------------------------------------------------------
    "reminder.every_n_prompts": 5,            # 0 disables; community reports decay at 2-6 turns
    # --- chunk mode --------------------------------------------------------------------
    "chunk.scope_lock": "deny",               # off | warn | deny  (PreToolUse on Write/Edit)
    "chunk.require_acceptance": True,
    # --- misc --------------------------------------------------------------------------
    "log.enabled": True,
    "identity.inject_profile": True,
    "identity.unknown_ask_model": True,
}

# Per-tier defaults, applied on top of DEFAULTS and under the user's harness.json (research/MODEL_MATRIX.md).
# Only keys that differ from DEFAULTS are listed; every value carries its source.
TIER_DEFAULTS: dict[str, dict[str, Any]] = {
    # Opus 5 and Fable/Mythos: no grounding re-prompt. Opus 5 "verifies its own work without being told to" and
    # re-check prompts "cause over-verification" [S1]; Fable "investigate[s] before acting" [S28]. The gate's
    # evidence rules G1–G6 stay on for every tier.
    "fable-5": {"gate.grounding": "off"},
    "opus-5": {"gate.grounding": "off"},
    # Lower tiers: the cross-model grounding rule is enforced once per prompt [S8]; format stays required;
    # tics stay warn-only (community-derived list, never a block by default).
    "opus-4x": {"gate.grounding": "block"},
    "sonnet-5": {"gate.grounding": "block"},
    "sonnet-4x": {"gate.grounding": "block"},
    "haiku": {"gate.grounding": "block"},
    "generic": {"gate.grounding": "block"},
}
TIER_DEFAULT_SOURCES: dict[str, str] = {
    "gate.grounding": "off on opus-5 (re-check prompts cause over-verification [S1]) and fable-5 (investigates before acting [S28]); "
                      "block once on every other tier: \"Never speculate about code you have not opened\" [S8]",
}


def tier_defaults(profile: str | None) -> dict[str, Any]:
    return dict(TIER_DEFAULTS.get(profile or "generic", TIER_DEFAULTS["generic"]))


def _home() -> Path:
    return Path(os.environ.get("HARNESS_HOME") or (Path.home() / ".claude"))


def log_path() -> Path:
    return _home() / "harness.log"


def state_dir() -> Path:
    return _home() / "harness" / "state"


def model_cache_path() -> Path:
    return _home() / "harness" / "model.json"


def project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def log(event: str, **fields: Any) -> None:
    """Append one JSON line to ~/.claude/harness.log. Never raises."""
    try:
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, **fields}
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _read_json(p: Path) -> dict[str, Any]:
    try:
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception as e:  # fail open
        log("config_read_error", path=str(p), error=repr(e))
    return {}


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and not key.endswith("_patterns"):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def load_config(profile: str | None = None) -> dict[str, Any]:
    """DEFAULTS -> TIER_DEFAULTS[profile] -> ~/.claude/harness.json -> <project>/.claude/harness.json -> HARNESS_* env."""
    cfg = dict(DEFAULTS)
    if profile:
        cfg.update(tier_defaults(profile))
        cfg["harness.profile"] = profile
    for p in (_home() / "harness.json", project_dir() / ".claude" / "harness.json"):
        cfg.update(_flatten(_read_json(p)))
    for k, v in os.environ.items():
        if k.startswith("HARNESS_") and k not in ("HARNESS_HOME",):
            key = k[len("HARNESS_"):].lower().replace("__", ".")
            if key in cfg:
                cur = cfg[key]
                try:
                    if isinstance(cur, bool):
                        cfg[key] = v.strip().lower() in ("1", "true", "yes", "on")
                    elif isinstance(cur, int):
                        cfg[key] = int(v)
                    elif isinstance(cur, list):
                        cfg[key] = json.loads(v)
                    else:
                        cfg[key] = v
                except Exception:
                    log("config_env_error", key=k, value=v)
    return cfg


# ---------------------------------------------------------------- per-session state
def load_state(session_id: str) -> dict[str, Any]:
    sid = "".join(c for c in (session_id or "unknown") if c.isalnum() or c in "-_") or "unknown"
    return _read_json(state_dir() / f"{sid}.json")


def save_state(session_id: str, state: dict[str, Any]) -> None:
    try:
        sid = "".join(c for c in (session_id or "unknown") if c.isalnum() or c in "-_") or "unknown"
        state_dir().mkdir(parents=True, exist_ok=True)
        (state_dir() / f"{sid}.json").write_text(json.dumps(state, indent=1), encoding="utf-8")
    except Exception as e:
        log("state_write_error", error=repr(e))

# claude-model-harness — shared hook helpers. POSIX sh. Sourced with `.`.
# Contract: hooks FAIL OPEN. Nothing here may exit non-zero; any failure logs and returns 0.
#
# Kept deliberately spawn-free on the happy path: on Windows (Git Bash) every external command costs 0.3–0.8 s,
# and the old wrapper (cat + date + basename + tr + cut + a `python -c` version probe) added ~5 s per hook, which
# is most of the hook timeout. Now: one `timeout` + one Python. The hook's stdin is passed straight to Python.
# Python >= 3.10 is checked inside harness_cli.py (exit 0 + log line if too old). jq is not used.
set -u
HARNESS_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)}"
HARNESS_LOGDIR="${HARNESS_HOME:-${HOME:-/tmp}/.claude}"
HARNESS_LOG="$HARNESS_LOGDIR/harness.log"
HARNESS_TIMEOUT="${HARNESS_TIMEOUT:-12}"   # inner cap on the Python; hooks.json timeouts are the outer cap

hlog() { # hlog <event> <detail> — failure paths only (spawns date/tr/cut)
  mkdir -p "$HARNESS_LOGDIR" 2>/dev/null || return 0
  printf '{"ts":"%s","event":"%s","hook":"%s","detail":"%s"}\n' \
    "$(date +%Y-%m-%dT%H:%M:%S 2>/dev/null)" "$1" "${0##*/}" "$(printf '%s' "${2:-}" | tr -d '"\n' | cut -c1-300)" \
    >>"$HARNESS_LOG" 2>/dev/null || true
}

find_python() { # first of python3/python on PATH; the version is checked by the CLI itself
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then printf '%s' "$c"; return 0; fi
  done
  return 1
}

# run_cli <subcommand> — runs the Python CLI on the hook's own stdin under a timeout. Never fails the hook.
run_cli() {
  PY=$(find_python) || { hlog "python_missing" "python3 >= 3.10 not found; hook skipped"; return 0; }
  CLI="$HARNESS_ROOT/scripts/harness_cli.py"
  [ -f "$CLI" ] || { hlog "cli_missing" "$CLI"; return 0; }
  mkdir -p "$HARNESS_LOGDIR" 2>/dev/null || true
  if command -v timeout >/dev/null 2>&1; then
    timeout "$HARNESS_TIMEOUT" "$PY" "$CLI" "$@" 2>>"$HARNESS_LOGDIR/harness.stderr.log"
  else
    "$PY" "$CLI" "$@" 2>>"$HARNESS_LOGDIR/harness.stderr.log"
  fi
  rc=$?
  [ "$rc" -eq 0 ] || hlog "cli_nonzero" "cmd=$1 rc=$rc (ignored, fail-open)"
  return 0
}

#!/bin/sh
# claude-model-harness installer. Idempotent. Never modifies CLAUDE.md or settings.json content.
#
#   sh scripts/install.sh                 # install from GitHub marketplace (AbdulrahmanAmer/claude-model-harness)
#   sh scripts/install.sh --local         # register this checkout as a local marketplace instead
#   sh scripts/install.sh --repo you/fork # different GitHub repo
#   sh scripts/install.sh --no-selftest   # skip the headless self-test (one short `claude -p` call)
#   sh scripts/install.sh --selftest-only # only run the self-test against this checkout (installs nothing)
#
# Documented commands used [src: S24, S25, S26, S29, S33]:
#   claude plugin marketplace add <owner/repo | local dir>
#   claude plugin install <plugin>@<marketplace> [-s user]
#   claude plugin list / claude plugin validate
#   claude -p --plugin-dir <dir> --output-format json --max-turns N   (self-test)
# Windows: hooks are POSIX sh, so Git Bash must be installed — Claude Code runs command hooks in Git Bash on
# Windows and falls back to PowerShell only when Git Bash is missing [src: S20].
set -u
REPO="AbdulrahmanAmer/claude-model-harness"
MARKET="claude-model-harness"
PLUGIN="claude-model-harness"
LOCAL=0
SELFTEST=1
INSTALL=1
HERE=$(cd "$(dirname "$0")/.." && pwd)
while [ $# -gt 0 ]; do
  case "$1" in
    --local) LOCAL=1 ;;
    --repo) shift; REPO="$1" ;;
    --no-selftest) SELFTEST=0 ;;
    --selftest-only) INSTALL=0 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
  esac
  shift
done

say() { printf '%s\n' "$*"; }
fail() { say "install: $*" >&2; exit 1; }

command -v claude >/dev/null 2>&1 || fail "claude CLI not found. Install Claude Code first: https://code.claude.com/docs/en/quickstart"
say "claude: $(claude --version 2>/dev/null | head -1)"
PY=""
for c in python3 python; do
  command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null && { PY="$c"; break; }
done
[ -n "$PY" ] || fail "python3 >= 3.10 is required by the hooks."
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) say "windows: running under Git Bash — Claude Code runs the hooks here too [S20]" ;;
esac

if [ "$INSTALL" -eq 0 ]; then
  say "(--selftest-only: skipping marketplace/install steps)"
elif [ "$LOCAL" -eq 1 ]; then
  say "Adding local marketplace: $HERE"
  if ! ADD_OUT=$(claude plugin marketplace add "$HERE" 2>&1); then
    if printf '%s' "$ADD_OUT" | grep -qi "already"; then
      say "  (marketplace already added; updating)"; claude plugin marketplace update "$MARKET" >/dev/null 2>&1 || true
    else
      say "  marketplace add failed:"; printf '%s\n' "$ADD_OUT" | tail -3 | sed 's/^/    /'
    fi
  fi
else
  # Full HTTPS URL rather than the owner/repo shorthand: the shorthand can resolve to an SSH clone
  # (git@github.com), which fails on machines without an SSH key; HTTPS URLs are documented [S25].
  REPO_URL="https://github.com/$REPO.git"
  say "Adding GitHub marketplace: $REPO_URL"
  if ! ADD_OUT=$(claude plugin marketplace add "$REPO_URL" 2>&1); then
    if printf '%s' "$ADD_OUT" | grep -qi "already"; then
      say "  (marketplace already added; updating)"; claude plugin marketplace update "$MARKET" >/dev/null 2>&1 || true
    else
      say "  marketplace add failed:"; printf '%s\n' "$ADD_OUT" | tail -3 | sed 's/^/    /'
    fi
  fi
fi

if [ "$INSTALL" -eq 1 ]; then
  say "Installing plugin $PLUGIN@$MARKET (user scope)"
  if claude plugin list 2>/dev/null | grep -q "$PLUGIN"; then
    say "already installed — running update"
    claude plugin update "$PLUGIN@$MARKET" >/dev/null 2>&1 || true
  else
    claude plugin install "$PLUGIN@$MARKET" -s user || fail "plugin install failed. Try: claude --plugin-dir $HERE/plugin"
  fi
fi

say ""
say "Verifying hooks are registered:"
if [ "$INSTALL" -eq 0 ]; then
  say "  plugin listed: skipped (--selftest-only)"
elif claude plugin list 2>/dev/null | grep -q "$PLUGIN"; then
  say "  plugin listed: yes"
else
  say "  plugin listed: NO — check 'claude plugin list'"
fi
claude plugin validate "$HERE/plugin" >/dev/null 2>&1 && say "  plugin validate: ok" || say "  plugin validate: not available or failed (non-fatal)"
say "  hooks file: $HERE/plugin/hooks/hooks.json (SessionStart, PostModelSwitch, UserPromptSubmit, PreToolUse, PostToolUse, Stop)"
say "  in a session, run /hooks to see them [S30]; /harness-status shows what the harness detected."

say ""
say "Detected model (from cache/transcript; SessionStart will refine it):"
"$PY" "$HERE/scripts/detect-model.py" 2>/dev/null || say "  unknown (no session yet)"

say ""
say "Doctor (report only):"
"$PY" "$HERE/scripts/doctor.py" 2>/dev/null | head -60 || true

# ---------------------------------------------------------------- headless self-test
# One `claude -p` turn with the plugin loaded from this checkout: the model is asked to quote the MODEL IDENTITY
# line the SessionStart hook injected. PASS = the reply contains it AND the harness log shows identity_injected.
if [ "$SELFTEST" -eq 1 ]; then
  say ""
  say "Self-test (one short headless turn; --no-selftest skips it):"
  LOG="${HARNESS_HOME:-${HOME:-/tmp}/.claude}/harness.log"
  if [ -f "$LOG" ]; then BEFORE=$(wc -l < "$LOG" | tr -d ' '); else BEFORE=0; fi
  TMPD=$(mktemp -d 2>/dev/null || echo "${TMPDIR:-/tmp}/harness-selftest-$$")
  mkdir -p "$TMPD"
  OUT="$TMPD/selftest.json"
  ( cd "$TMPD" && printf '%s' "Reply with the exact MODEL IDENTITY line you were given at session start (the line that begins 'MODEL IDENTITY:'), verbatim, and nothing else." \
      | claude -p --plugin-dir "$HERE/plugin" --output-format json --max-turns 1 > "$OUT" 2>"$TMPD/stderr.txt" )
  RC=$?
  if [ "$RC" -ne 0 ]; then
    say "  FAIL: claude -p exited $RC (see $TMPD/stderr.txt)"
  elif grep -q "MODEL IDENTITY" "$OUT" 2>/dev/null; then
    if [ -f "$LOG" ] && tail -n +"$((BEFORE + 1))" "$LOG" 2>/dev/null | grep -q '"identity_injected"'; then
      say "  PASS: the model quoted the MODEL IDENTITY line and the log shows identity_injected"
      tail -n +"$((BEFORE + 1))" "$LOG" | grep '"identity_injected"' | tail -1 | cut -c1-200 | sed 's/^/  /'
    else
      say "  PASS (reply): the model quoted the MODEL IDENTITY line; log line not found at $LOG (HARNESS_HOME differs?)"
    fi
    "$PY" - "$OUT" <<'EOF' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    r = d.get("result") if isinstance(d, dict) else None
    if isinstance(r, str):
        line = next((l for l in r.splitlines() if "MODEL IDENTITY" in l), r)
        print("  reply: " + line.strip()[:220])
except Exception:
    pass
EOF
  else
    say "  FAIL: the reply did not contain 'MODEL IDENTITY' (see $OUT). The hook may not have run: check /hooks in a session and $LOG"
  fi
fi

say ""
say "Optional: status-line model cache -> mkdir -p ~/.claude/harness && cp $HERE/plugin/scripts/statusline.sh ~/.claude/harness/ && see plugin/settings.example.json"
say "Done. Start a new session; the first message context will contain 'MODEL IDENTITY: ...'. Run /harness-status any time."

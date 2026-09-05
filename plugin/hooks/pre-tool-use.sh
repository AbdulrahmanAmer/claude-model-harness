#!/bin/sh
# PreToolUse (matcher: Write|Edit|MultiEdit|NotebookEdit) — chunk-mode scope lock.
# Only acts when .claude/harness/chunks.json has an active chunk with `paths`. Uses the documented
# permissionDecision "deny" [src: S20, S21]. Configurable: chunk.scope_lock = off|warn|deny.
. "$(dirname "$0")/_lib.sh" 2>/dev/null || exit 0
run_cli scope
exit 0

#!/bin/sh
# PostToolUse (matcher: Write|Edit|MultiEdit) — writing-tics check on files written to disk. WARN ONLY
# (PostToolUse cannot block; the tool already ran) [src: S20].
. "$(dirname "$0")/_lib.sh" 2>/dev/null || exit 0
run_cli tics-file
exit 0

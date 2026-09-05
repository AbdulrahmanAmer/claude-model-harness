#!/bin/sh
# UserPromptSubmit — periodic profile reminder via hookSpecificOutput.additionalContext [src: S21].
. "$(dirname "$0")/_lib.sh" 2>/dev/null || exit 0
run_cli reminder
exit 0

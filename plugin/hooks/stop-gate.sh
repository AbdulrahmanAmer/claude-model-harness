#!/bin/sh
# Stop — COMPLETION GATE. Blocks with {"decision":"block","reason":...} [src: S21]; otherwise prints
# nothing or a systemMessage warning. Never exits non-zero: a broken gate must never trap the user.
# The CLI logs a `stop` event (stop_hook_active, prompt_id) and gate_block / gate_allow.
. "$(dirname "$0")/_lib.sh" 2>/dev/null || exit 0
run_cli gate
exit 0

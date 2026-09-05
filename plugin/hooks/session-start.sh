#!/bin/sh
# SessionStart (matcher: all sources incl. compact) — MODEL IDENTITY + profile injection.
# Plain-text stdout is added to Claude's context on SessionStart [src: S20, S21]. Exit 0 always.
# The CLI logs a `session_start` event with source= and model= (the stdin `model` field is optional [S20]).
. "$(dirname "$0")/_lib.sh" 2>/dev/null || exit 0
run_cli identity
exit 0

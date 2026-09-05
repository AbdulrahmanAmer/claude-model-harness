#!/bin/sh
# PostModelSwitch — re-inject identity + profile after /model. Plain-text stdout is added to context [src: S20].
# The CLI logs a `model_switch` event with from= and to=.
. "$(dirname "$0")/_lib.sh" 2>/dev/null || exit 0
run_cli identity
exit 0

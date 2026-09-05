---
name: harness-status
description: Show what claude-model-harness knows right now — detected model (with source and confidence), active profile, completion-gate state for this prompt, active chunk, the last three harness log events, and what to do next. Read-only.
argument-hint: ""
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/harness_cli.py status *)
---
Run exactly: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/harness_cli.py status`

Show the user the output verbatim. Then, in one or two sentences, restate the `next:` line in plain words (for example "the model was detected from the transcript, so run /model to make it definitive", or "chunk 2 is active: stay inside its scope and run its acceptance command before claiming it done").

Do not run anything else and do not change any file. If the output says the model is unknown, ask the user to run `/status` and tell you the model ID shown there; the harness never guesses a model [S20].

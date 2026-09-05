---
name: chunk
description: Chunk mode — split a task into small scoped chunks, each with a scope lock, an acceptance command, and a recommended effort level for the running model; run and gate them one at a time. Use for anything larger than a single-file edit.
argument-hint: "plan <task> | run <n> | status | done <n> | clear"
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/harness_cli.py chunk *)
---
Chunk mode for: $ARGUMENTS

Why (cited in `${CLAUDE_PLUGIN_ROOT}/scripts/harness/chunks.py`): plan once at the default high effort with the whole task in view [S1]; run scoped chunks at the effort the running model's official guide recommends (per-model table in `research/MODEL_MATRIX.md`: e.g. Opus 5 "use low and medium liberally" [S14], Opus 4.7/4.8 "start with xhigh for coding" [S14], Sonnet 4.6 "medium (recommended default)" [S14], Haiku 4.5 has no effort parameter [S17, S28]); the Stop gate accepts a chunk only when its acceptance command ran and passed; the PreToolUse scope lock denies edits outside the chunk's paths.

## `plan <task>`
1. Read the task and the relevant code first (no edits). Do this at the current (high) effort.
2. Write a plan JSON to `.claude/harness/chunk-plan.json` with this shape — 3–8 chunks, each finishable in a handful of tool calls, each with a runnable acceptance command:
   {"task": "<task>", "chunks": [{"goal": "...", "kind": "mechanical|feature|refactor|debug|research", "paths": ["src/x/**", "tests/test_x.py"], "acceptance": ["pytest tests/test_x.py -q"]}]}
   Rules: `paths` are project-relative globs and define the scope lock. `acceptance` must be a real command that exercises the goal (tests/build/lint); a chunk with no runnable check gets `kind: research` and a `git diff --stat` acceptance. Kinds: mechanical (rename, config, single file), feature, refactor (multi-file), debug (unknown cause), research.
3. Run: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/harness_cli.py chunk plan --file .claude/harness/chunk-plan.json --model <your exact model ID>`
   `<your exact model ID>` is the string from the MODEL IDENTITY line, or, when that line says the model was not detectable, the model named in your own system prompt (for example `claude-sonnet-5`). Do not guess: if neither names a model, omit `--model`. The command writes `.claude/harness/chunks.json`, records the model, and assigns each chunk a recommended effort for that model (or `n/a` when the model has no effort parameter) with the cited reason.
4. Show the resulting status table to the user and stop. Do not start a chunk until the user says which one.

## `run <n>`
1. Run: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/harness_cli.py chunk run --id <n>` — this activates the chunk (scope lock on) and prints the effort line.
2. Repeat that effort line to the user verbatim. It is one of:
   - `recommended effort: <level> (<cited reason>) -> run: /effort <level>` — tell the user to run exactly that `/effort` command now if the current level differs (effort is user-side: `/effort`, `--effort`, or `CLAUDE_CODE_EFFORT_LEVEL` [S28]; never disable thinking [S1]).
   - `effort: not supported on <model> [S17, S28] — nothing to set` — say so and continue.
3. Do only this chunk's goal, inside its `paths`. Anything else you notice goes under Blockers/follow-ups, not into the code.
4. Run the acceptance command(s) as real tool calls. Report in the completion format: outcome · ≤3 bullets · `Verification:` command → observed result · `Blockers:`. The Stop gate will block a "done" without the acceptance output; on a pass it marks the chunk done automatically.

## `status` / `done <n>` / `clear`
Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/harness_cli.py chunk status|done --id <n>|clear` and show the output. `clear` removes `.claude/harness/chunks.json` (scope lock off).

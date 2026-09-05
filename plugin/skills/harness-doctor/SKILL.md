---
name: harness-doctor
description: Lint CLAUDE.md, rules, skills and settings.json for instructions that Anthropic's official model guides say hurt the current model (verification cruft, thinking disabled, missing conciseness/scope lines). Report only; apply edits only after the user approves the diff.
argument-hint: "[--apply] [--mode delete|move] [--profile fable-5|opus-5|opus-4x|sonnet-5|sonnet-4x|haiku|generic] | --explain R1"
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/harness_cli.py doctor *)
---
Run the harness doctor on this project and report the findings.

1. Run exactly: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/harness_cli.py doctor $ARGUMENTS`
   - Without `--apply` it is a dry run: it prints findings and a unified diff of proposed edits and writes nothing.
   - The `--project` default is the current working directory; the detected model picks the profile unless `--profile` is given.
2. Show the user the report verbatim (findings with rule id, file:line, the cited reason, and the proposed fix) and the diff.
3. Do NOT re-run with `--apply` unless the user explicitly approves after seeing the diff. When they approve, run the same command with `--apply` added; backups are written as `*.harness.bak`. Use `--mode move` when the team runs several models — removed lines are then kept in `.claude/harness/removed-instructions.md` (not loaded by Claude Code).
4. Never edit settings.json yourself; doctor only reports on it.
5. Severities depend on the detected model's tier (the same "double-check" line is an error on Opus 5 and info on Sonnet/Haiku, where Anthropic recommends a self-check). If the user asks why, run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/harness_cli.py doctor --explain <rule>` (e.g. `--explain R1`) and show the cited per-tier reasoning.

Finish with: one-sentence outcome · ≤3 bullets · `Verification:` the exact command and its exit status · `Blockers:`.

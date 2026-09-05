# HANDOFF.md — brief for the local session that finishes and publishes this repo

> Status 2026-09-05 (Windows 11, Claude Code 2.1.257): Chunk 0 and Chunk 1 done (owner = the logged-in `gh` account, `AbdulrahmanAmer`); Chunk 2's interactive checks were run headless where the docs allow it and are recorded in `tests/REPORT.md` §6; Chunk 3 (publish) is recorded there too. The "every model" build that followed (tiers, tier-aware gate and doctor, per-model effort, `/harness-status`, installer self-test) is in `CHANGELOG.md` 0.2.0.

You are running in a local checkout of `claude-model-harness`. The repo is built and tested; your job is to verify the parts that need an interactive machine, replace the `OWNER` placeholder, and push. Work in the chunks below, one at a time; each has an acceptance command. Keep the completion format (outcome · ≤3 bullets · Verification: · Blockers:). Do not widen scope: no refactors, no new features.

## State of the repo (what is already done)
- Phase 0 research: `research/SOURCES.md` (44 official sources), `research/FINDINGS.md`, `research/COMMUNITY.md`.
- Phase 1 design: `ARCHITECTURE.md`.
- Phase 2 build: plugin (6 hooks, 4 profiles, 2 skills), `scripts/`, `api/`, `PROMPT.md`.
- Phase 3 tests: `python3 -m pytest -q` → 51 passed; `claude plugin validate` passes for both manifests; `scripts/install.sh --local` installed and listed the plugin; headless live smoke test showed identity injection and the Stop gate blocking a fake "done" then accepting a real `pytest` run (`tests/REPORT.md`).
- Phase 4 docs: `README.md`, `CHANGELOG.md`, `LICENSE`, `.github/workflows/test.yml`, `RELEASE_NOTES.md`.

## Chunk 0 — restore three files the remote tool could not write (mechanical, effort: low)
The desktop bridge refuses to write under `.github/` and `.claude/`. `claude-model-harness.zip` in this folder has the complete tree. Do:
1. Move `ci/github-workflow-test.yml` → `.github/workflows/test.yml` and delete the `ci/` folder.
2. Extract from the zip (or recreate) `tests/fixtures/cruft-project/.claude/rules/testing.md` and `tests/fixtures/cruft-project/.claude/settings.json`.
3. Delete `claude-model-harness.zip`.
Acceptance: `python3 -m pytest -q` → 51 passed (the doctor tests need those two fixture files).

## Chunk 1 — replace OWNER (mechanical, effort: low)
Scope: `README.md`, `RELEASE_NOTES.md`, `LICENSE`, `plugin/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `plugin/settings.example.json`, `scripts/install.sh`.
Do: replace the literal `OWNER` with the GitHub owner/org name (ask the user if unknown; do not guess). In `LICENSE` use the person/org name.
Acceptance: `grep -rn "OWNER" --include='*.md' --include='*.json' --include='*.sh' . | grep -v research/ ; python3 -m pytest -q` → no OWNER hits outside `research/`, 51 passed.

## Chunk 2 — interactive verification (debug, effort: high)
Scope: no code changes expected; append results to `tests/REPORT.md §5`.
Do, in a **new interactive** `claude` session started with `claude --plugin-dir ./plugin` in `tests/fixtures/fake-repo`:
1. Ask: "Quote the MODEL IDENTITY line you were given." Record whether SessionStart stdin carried `model` (`grep session_start ~/.claude/harness.log` shows `model=<id>` or empty).
2. Run `/model` to switch models, then ask again. Confirm `~/.claude/harness.log` has `model_switch` with `to=<id>` and the quoted line changed. (This is Phase 0 open item 4; `PostModelSwitch` is documented [S20] but was not exercisable headless.)
3. Run `/hooks` and confirm the six events are listed.
4. Run `/chunk plan fix the add() bug` then `/chunk run 1`; try editing a file outside the chunk's paths and confirm the deny message; finish the chunk and confirm the gate marks it done (`chunk_mark`/`gate_allow` in the log and `chunks.json` status `done`).
5. Run `/harness-doctor` in `tests/fixtures/cruft-project` (copy it first); confirm the dry run shows the diff and writes nothing.
Acceptance: `tests/REPORT.md` §5 updated with the actual log lines; `python3 -m pytest -q` still 51 passed.
If any step fails, fix the smallest thing that makes it pass, add a test, and note it in `CHANGELOG.md`. If SessionStart never carries `model` interactively either, leave the code as is (the fallback chain handles it) and say so in README "Model detection order".

## Chunk 3 — publish (mechanical, effort: low)
Scope: git only.
Do:
```
git init -b main
git add -A
git commit -m "claude-model-harness 0.1.0"
gh repo create <owner>/claude-model-harness --public --source=. --push     # or add the remote and push
```
Then confirm the marketplace install path from a clean machine or a temp HOME:
```
claude plugin marketplace add <owner>/claude-model-harness
claude plugin install claude-model-harness@claude-model-harness -s user
claude plugin list
```
Acceptance: `git log --oneline | head -1` shows the commit; `claude plugin list` shows the plugin enabled; CI on GitHub green (`.github/workflows/test.yml`).
Create the GitHub release `v0.1.0` with the body of `RELEASE_NOTES.md`.

## Guardrails for you
- Do not edit `research/*.md` except to add sources you actually fetched (URL + date + what it supports).
- Do not add verification or "double-check" instructions anywhere; the doctor will flag them and Anthropic says they hurt Opus 5 [S1].
- Do not disable thinking to save cost; lower effort instead [S1].
- Every profile bullet must keep its `[src: S#]`; `tests/test_misc.py::test_profiles_cite_sources` enforces it.
- If something here is wrong, say so in one sentence and continue with the chunk as scoped; do not silently redesign.

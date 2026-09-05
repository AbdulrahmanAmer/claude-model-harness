# ARCHITECTURE.md — how each component works (Phase 1 proposal, as built)

Source ids `[S#]` → `research/SOURCES.md`; community evidence → `research/COMMUNITY.md`; conflicts D1–D13 → `research/FINDINGS.md §5`.

## Layout

```
claude-model-harness/
├── README.md · PROMPT.md · SOURCES.md (index → research/SOURCES.md) · ARCHITECTURE.md · HANDOFF.md
├── .claude-plugin/marketplace.json        # this repo IS the marketplace; plugin source "./plugin"   [S25]
├── plugin/                                # the Claude Code plugin
│   ├── .claude-plugin/plugin.json         # manifest (name required)                                  [S24]
│   ├── hooks/hooks.json                   # 6 events, all `type: command`, all fail-open              [S20, S24]
│   ├── hooks/*.sh                         # POSIX sh, no jq; one `timeout` + one Python per hook, stdin passed through
│   ├── scripts/harness_cli.py             # one entry point: identity | gate | reminder | tics-file | scope | doctor | chunk | detect
│   ├── scripts/harness/                   # pure-stdlib Python 3.10+ package (config, detect_model, transcript, stop_gate, tics, doctor, chunks)
│   ├── scripts/statusline.sh              # optional: caches statusline `model.id` for detection      [S22]
│   ├── profiles/{fable-5,opus-5,opus-4x,sonnet-5,sonnet-4x,haiku,generic}.md + _useful-output.md + _completion-format.md + _tics.md
│   ├── skills/harness-doctor/SKILL.md     # /harness-doctor [--explain R#]                              [S32]
│   ├── skills/chunk/SKILL.md              # /chunk plan|run|status|done|clear (per-model effort line)
│   ├── skills/harness-status/SKILL.md     # /harness-status: model+source+confidence, profile, gate, chunk, log, next
│   ├── settings.example.json · harness.example.json
├── scripts/install.sh · doctor.py · detect-model.py   # repo-level entry points (shims into plugin/scripts)
├── api/python/harness_client.py · api/typescript/harness.ts
├── research/SOURCES.md · FINDINGS.md · COMMUNITY.md
└── tests/ (pytest) + fixtures/ + REPORT.md
```

## 1. Model identity — `SessionStart` (+ `PostModelSwitch`, + `compact`)

Detection order (FINDINGS §1): hook `model` → `PostModelSwitch.to_model` → harness cache (written by hooks or the optional statusline script) → transcript `message.model` (UNVERIFIED-BY-DOCS, observed) → `ANTHROPIC_MODEL`/settings `model` only if a full ID → unknown. Never guesses.
Injection: **plain-text stdout** — documented as added to context on SessionStart and PostModelSwitch [S20, S21]; confirmed live (tests/REPORT.md §4). Text = provenance line ("claude-model-harness plugin, installed by the user") → `MODEL IDENTITY: You are running as <id> (<name>). Apply profile: <p>. Do not claim to be a different model.` → profile → completion format → tics block → active chunk (if any). Unknown → "not detectable… if your system prompt states your model, that is authoritative; otherwise state your model ID in your first reply; do not guess."
Matcher `startup|resume|clear|compact` so compaction re-injects [S21]. `PostModelSwitch` (added; D1) is the only documented way to follow `/model` [S20].

## 2. Completion gate — `Stop`

Input: `last_assistant_message` (documented precisely for this; transcript may lag) [S20]; transcript for tool evidence of the current turn. Output: top-level `{"decision":"block","reason":…}` [S21]. Rules G1–G6 (phantom tool-call text; claim without evidence; weak/rigged evidence; failing output + success claim; completion format; chunk acceptance) plus G7 grounding — see `stop_gate.py` docstring. **Tier-aware:** the Stop hook carries no `model` field, so the CLI detects the tier (SessionStart cache → transcript → …) and loads `config.TIER_DEFAULTS[tier]`. G7 (`gate.grounding`): a sentence that names an existing project file with a claim verb ("X defines/returns/contains …") and no Read/Grep/Glob/Edit/Bash call on that file in the turn is blocked once with "read the file, then answer" — Anthropic's `<investigate_before_answering>` rule [S8]. It is `off` on opus-5 (re-check prompts cause over-verification [S1]) and fable-5 (investigates before acting [S28]) and `block` on every other tier; all seven tiers keep G1–G6, the completion format and warn-only tics. Cap: 2 blocks per `prompt_id`, then allow with a `systemMessage` warning; Claude Code's own cap is 8 [S21]. Evidence quality (D11): strong = test/build/lint/diff Bash call whose result shows an outcome; weak = `|| true`, `--no-verify`, `-k`/filters, "0 tests", `git checkout main`/`stash`; failed = `N failed`/`FAILED`/traceback.
D2 resolution: the gate is conditional and deterministic; profiles contain no standing verification instruction [S1].

## 3. Profiles

Seven tiers, derived only from `research/MODEL_MATRIX.md` (2026-09-05): `fable-5.md` (Fable 5.1/5, Mythos: S4/S5/S6/S13), `opus-5.md` (S1/S2/S3/S8; deliberately no verification instruction), `opus-4x.md` (4.8/4.7/4.6/4.5: S2/S8/S9/S14/S16/S28), `sonnet-5.md` (S45/S14/S8/S5), `sonnet-4x.md` (4.6/4.5: S8/S14/S16/S47/S57), `haiku.md` (S8/S17/S28/S51/S58), `generic.md` (cross-model S1/S8/S28, no self-check because the unknown model may be Opus 5). Lower tiers carry the cross-model "Before you finish, verify your answer against [test criteria]" line that S8 recommends for every model except Opus 5. `_useful-output.md` is injected for every tier (answer first; command + observed result for any code/test claim; "could not verify" instead of guessing; read before claiming; no placeholders; partial reported as partial — S5/S1/S8/S4). Every bullet ends with `[src: S#]`; `tests/test_misc.py::test_profiles_cite_sources` enforces it and that community ids never appear in a profile. Identity output is kept under Claude Code's 10,000-character hook-output cap [S20] (`tests/test_identity.py::test_identity_output_under_hook_cap`). `_tics.md`: three tiers — official (S13), mannered (S4), community (C2–C5) — labelled.

## 4. Reminder — `UserPromptSubmit`

Every N prompts (default 5; community decay 2–6 turns) inject `hookSpecificOutput.additionalContext` [S21] with ordering rules only (outcome-first format, scope line, active chunk). Never a word cap (D13).

## 5. Tics — `PostToolUse` (files) and Stop (final message)

PostToolUse on `Write|Edit|MultiEdit`, warn-only via `additionalContext` (cannot block) [S20]; only doc-like globs by default. Stop: `warn` default (systemMessage), `block` opt-in (D12).

## 6. Chunk mode — `/chunk` + `PreToolUse` scope lock

`chunks.json` in `.claude/harness/` (created only by `/chunk plan`). Each chunk: goal, kind, paths (globs), acceptance commands, recommended effort with cited reason (`chunks.recommend_effort(kind, n_paths, has_acceptance, model_id)`): the plan records the detected model; `chunks.supported_efforts` encodes Claude Code's per-model table [S28] (no `xhigh` on Opus 4.6 / Sonnet 4.6; no effort at all on Haiku 4.5 / Sonnet 4.5 / Opus 4.5 → effort `None`, the skill prints "not supported"); tier sweet spots: Opus 5 low/medium liberally [S14]; Opus 4.7/4.8 xhigh for coding, medium as the average-workflow drop-in [S14]; Opus 4.6 medium/high with effort as the over-exploration fallback [S8]; Sonnet 5 high default, xhigh hardest, medium ≈ 4.6 high [S45]; Sonnet 4.6 medium recommended default [S14]; Fable high default, medium where quality holds [S4]. Recommendations are clamped to the model's supported levels. Thinking is never disabled [S1]. Effort is user-side (`/effort`, `--effort`, `CLAUDE_CODE_EFFORT_LEVEL` [S28]); the gate reports mismatches from `effort.level` in hook stdin [S20] as info. Scope lock: PreToolUse `permissionDecision: deny` [S20, S21] for edits outside `paths` (`warn`/`off` configurable). The gate marks a chunk done only when its acceptance command ran with a result and no failure tokens.

## 7. Doctor — `/harness-doctor`, `scripts/doctor.py`

Scans CLAUDE.md variants, `.claude/rules/**`, skills, settings.json (user/project/local) [S27, S31, S32]. Rules R1–R17 with citations; **severity matrix per tier** derived from `research/MODEL_MATRIX.md` (R1 verification: error on opus-5 / warning on generic / info elsewhere [S1, S8]; R2 anti-laziness cruft: warning on opus-5, fable-5, opus-4x, sonnet-4x [S8, S5], info on sonnet-5 where the "Think carefully" nudge is the documented low-effort remedy [S45] and on haiku where no statement exists; R3 no-thinking: error on opus-5 [S1, S16], warning on opus-4x [S8]; R11 thinking disabled: error/warning on opus-5, warning on sonnet-5 [S45], info where thinking is off by default [S16]; R17 effort level unsupported by the model in Claude Code [S28]; R14 subagent cap: opus-5 and Opus 4.6 only [S1, S8]); `doctor --explain <rule>` prints the per-tier reasoning. Negation-aware so official prompts ("do not use subagents to … double-check") are not flagged. Only error/warning findings are edited, and R1 is auto-removed on opus-5 only. Dry-run diff always; `--apply` writes with `.harness.bak` and keeps CRLF/LF as found; `--mode move` keeps removed lines in `.claude/harness/removed-instructions.md` (D10). settings.json is report-only. Fixtures: `tests/fixtures/<tier>-project/` for all seven tiers.

## 7b. Status — `/harness-status`

`harness_cli.py status` is read-only: model detection result (id, display name, source, confidence — from the same chain as SessionStart), the active tier and its gate defaults (grounding on/off, format, tics, blocks used on the latest prompt), the active chunk with its effort line, the last three `harness.log` events, and a `next:` line (unknown model → run `/status` and tell Claude; cap hit → check Verification/Blockers yourself; chunk active → finish inside its scope). The skill shows the output verbatim.

## 8. API snippets

`resolve_params()` encodes the effort/thinking matrix from S14/S15/S16/S38 (400 cases raise before the request) and `identity_block()` builds the system prompt from the profiles [S8].

## Doc-vs-design conflicts and how they were resolved
D1 optional `model` → fallback chain + PostModelSwitch. D2 gate vs "remove verification instructions" → conditional gate, no standing instruction. D3 transcript lag → `last_assistant_message`. D4 SessionStart output shape → plain text (confirmed live). D5 transcript format undocumented → labelled UNVERIFIED, rank 4. D6 Fable history edits → hooks only append. D7 tics tiers labelled. D8 matchers. D9 per-profile severities. D10 `--mode move`. D11 evidence quality. D12 mechanical tics check. D13 ordering-rule reminders.

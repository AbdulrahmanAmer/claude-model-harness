# claude-model-harness

A Claude Code plugin (plus a paste-anywhere prompt and API snippets) for the most-reported Claude Opus 5 failures in agentic use: **claiming work is done when it isn't, phantom tool calls, monologuing / over-verification, scope creep, and "Claudism" prose tics.** It also makes the harness **tell the model which model it is** and loads the matching official Anthropic guidance automatically.

Every behavioural claim cites an official Anthropic page (`[S#]` → [`research/SOURCES.md`](research/SOURCES.md)). Community evidence is kept separate ([`research/COMMUNITY.md`](research/COMMUNITY.md)) and never used to make claims about how the model works.

## The problem, cited

- Opus 5's "default user-facing responses run longer than prior Opus models'", lowering effort "does not reliably shorten the visible response", and it "narrates readily during agentic work" and "narrates corrections … more than prior models" [S1, S2, S3].
- It "verifies its own work without being told to"; verification / double-check instructions carried over from older prompts "cause over-verification" — Anthropic says to **remove** them [S1, S2, S3, S8]. The system card lists "unproductive self-verification" and "poor calibration of task scope" as known behaviours [S10].
- It "can also expand the scope of a task, adding steps that weren't requested" and "delegates to subagents more readily" [S1, S3].
- With thinking disabled it "occasionally writes a tool call into its user-facing text instead of emitting a structured tool_use block. … the call never runs" [S1, S15, S16].
- It "hallucinates factual claims slightly more than Opus 4.8" and shows "a surprising number of cases in which Opus 5 confidently stated an answer about which it was in fact unsure" [S10]. On Fable/Mythos 5.1 Anthropic notes it "exaggerates the completeness of its work, fails to verify important claims" [S11].
- What users report most, in order: verbosity, prose tics, scope creep/overruling, instruction decay after 2–6 turns, false "done" claims with rigged checks, confident wrong claims, phantom tool calls (rare with thinking on) — with quotes and links in [`research/COMMUNITY.md`](research/COMMUNITY.md).

## What is fixable, honestly

| Failure | Verdict | What this repo does |
|---|---|---|
| Monologuing / long replies | Prompt-fixable [S1] | Profile + end-of-prompt reminder + outcome-first completion format |
| Over-verification loops | Fixable by **removing** instructions [S1, S2]; tendency is model-level [S10] | Doctor flags and removes verification cruft; profiles contain none |
| Scope creep | Prompt-mitigable [S1]; tendency model-level [S10] | Scope line in profiles; **chunk mode** with a scope lock |
| False "done" / rigged checks | Partially prompt-fixable [S5]; overconfidence is model-level [S10] | **Deterministic Stop gate**: no test/build/diff evidence → blocked; `\|\| true`, `-k`, "0 tests", `git checkout main` count as weak; failing output + "done" blocked |
| Phantom tool calls | Config-fixable for the documented cause (keep thinking on) [S1] | Gate blocks tool-call-shaped text; doctor flags thinking disabled |
| Prose tics | Only three words are official [S13] + "mannered prose" [S4]; prompting decays (community) | Mechanical check on the final message and on files written (warn; block opt-in) |
| Hallucination / confident wrong answers | **Model-level** [S10] — no prompt fix in Anthropic's guide | Not fixed. Grounding line for code claims only [S8]. Users who need Opus 4.8 behaviour report switching models works; this repo cannot replace that. |

Community durability ranking (COMMUNITY.md §2): hard Stop-hook gates held with no decay reports; output styles mixed; per-turn reminders partial; CLAUDE.md rules alone decay in 2–6 turns. That is why the gate is the centre of this repo and the profiles are secondary.

## 60-second install

Requirements: Claude Code ≥ 2.1.251 (PostModelSwitch [S20]; subagent caps need ≥ 2.1.217 [S1]; tested on 2.1.261 Linux and 2.1.257 Windows), Python ≥ 3.10, Git Bash on Windows. `jq` is not needed.

```sh
# from a clone (or use --local from the checkout)
git clone https://github.com/AbdulrahmanAmer/claude-model-harness && cd claude-model-harness
sh scripts/install.sh --repo AbdulrahmanAmer/claude-model-harness      # or: sh scripts/install.sh --local
```
Under the hood (documented commands [S25, S26, S24]):
```
claude plugin marketplace add https://github.com/AbdulrahmanAmer/claude-model-harness.git   # the owner/repo shorthand also works where git can use SSH
claude plugin install claude-model-harness@claude-model-harness -s user
```
or inside a session: `/plugin marketplace add https://github.com/AbdulrahmanAmer/claude-model-harness.git` then `/plugin install claude-model-harness@claude-model-harness`. For development: `claude --plugin-dir ./plugin`.

Start a new session. The first context contains `MODEL IDENTITY: You are running as <model> …` followed by the matching profile. Check hooks with `/hooks`.

### Paste this prompt (one line)

> Install and configure https://github.com/AbdulrahmanAmer/claude-model-harness per its README, run its doctor on this project, show me the diff, and apply only after I approve.

### No Claude Code? Paste `PROMPT.md`

[`PROMPT.md`](PROMPT.md) is a ≤60-line block for any harness (Cursor, the API, Cowork). Fill in `You are running as: {{MODEL_ID}}`.

## What you will see

Real text from the runs in `tests/REPORT.md` §6 (Claude Code 2.1.257, Windows; Sonnet 5 unless noted).

**1. Session start.** The first context of every session contains the plugin's block. When Claude Code passes the model (interactive `/model`, or a hook payload with `model`), the line is definitive:

```
MODEL IDENTITY: You are running as claude-sonnet-5 (Claude Sonnet 5). Apply profile: sonnet-5. Do not claim to be a different model. [detected via hook:SessionStart.model]
```
When it does not (every headless run we made — the field is optional [S20]), the harness says so rather than guessing, and the model fills it in from its own system prompt:

```
MODEL IDENTITY: not detectable by the harness at this point (Claude Code did not pass a model field). If your system prompt states your model, that is authoritative — use it; otherwise state your exact model ID in your first reply (it appears in the status line / `/status`). Do not guess. Applying the generic profile until the model is known; the matching profile is applied once detected.

My exact model ID: claude-sonnet-5.          <- the model's reply
```
On a resumed or forked session with only past evidence (cache or transcript) the line is provisional — "the last model seen for this session was X … If your system prompt names a different model, that is authoritative" — because a resume can land on another model without any hook event (seen live with `--resume … --model claude-opus-5`).

Then the profile for the tier (`PROFILE sonnet-5 — …`, every bullet ending in `[src: S#]`), the shared `USEFUL OUTPUT` block, the `COMPLETION FORMAT`, and the `WRITING` tics block. Total under 10,000 characters for every tier (Claude Code's hook-output cap [S20]).

**2. A false "done", blocked.** The model was told to reply `Done — implemented the fix.` with no tool calls. The Stop hook sent it back:

```
[harness completion gate 1/2] You state 'Done' but there is no evidence in this session. No test, build, lint, or diff command ran in this turn. Run the relevant test/build/lint command (or `git diff --stat`) as a real tool call and quote its observed result under 'Verification:'. If you cannot verify, say so plainly under 'Blockers:' and do not claim completion.
```
The model then ran `python -m pytest -q` for real (the fixture's test fails on purpose) and its next stop was allowed:

```
Tests fail — not implementing a fix per instructions.

- Verification: `python -m pytest -q` → 1 failed, 0 passed — `test_calc.py::test_add` fails: `add(2, 3)` returned `-1`, expected `5`.
- Blockers: code bug in `add` not fixed (instructed not to fix it).
```
`~/.claude/harness.log` for that exchange: `identity_injected` → `gate_block attempt=1 profile=sonnet-5` → `gate_allow evidence.failed=['python -m pytest -q']`. In an earlier attempt the model wrote "fixed." after the failing run and got the second block: *"You claim completion but the last verification output shows failures (python -m pytest -q). Report the failure under 'Blockers:' instead of claiming done, or fix it and re-run."*

**3. Per tier.** The gate rules are the same on every model; what differs is the profile text and two defaults: the grounding rule (a claim about a file the model never opened → "read the file, then answer", on for opus-4x / sonnet-5 / sonnet-4x / haiku / generic, off for opus-5 / fable-5 [S1, S8, S28]) and the effort line `/chunk` prints (see the table under Chunk mode; "effort: not supported on claude-haiku-4-5-20251001 [S17, S28] — nothing to set" on Haiku). `/harness-status` prints what was detected:

```
harness status
  model: claude-sonnet-5 (Claude Sonnet 5)  via cache:hook:SessionStart.model  confidence high
  profile: sonnet-5  (plugin/profiles/sonnet-5.md + _useful-output + completion format + tics)
  gate: on; format required=True; grounding=block (tier default: block); tics=warn; blocks this prompt: 1/2 (prompt p1…); prompts this session: 0
  chunk: none active (no plan; /chunk plan <task>)
  last log events (…/harness.log):
    2026-09-05T05:54:31+0300 identity_injected hook_event=SessionStart … model_id=claude-sonnet-5 profile=sonnet-5 …
    2026-09-05T05:54:34+0300 gate_block session=s1 prompt=p1 attempt=1 reasons=["You state 'Done' but there is no evide … profile=sonnet-5
  next: for anything larger than one file: /chunk plan <task>; to lint CLAUDE.md for this model: /harness-doctor
```

## What runs

| Hook | Event | Does | Mechanism |
|---|---|---|---|
| `session-start.sh` | SessionStart (`startup\|resume\|clear\|compact`) | Detects the model, injects identity + profile; re-injects after compaction | plain-text stdout → context [S20, S21] |
| `model-switch.sh` | PostModelSwitch | Re-injects after `/model` | plain-text stdout [S20] |
| `stop-gate.sh` | Stop | Completion gate (evidence, phantom calls, format, chunk acceptance); tics warn | `{"decision":"block","reason"}` [S21]; ≤2 blocks per prompt, then allow with warning |
| `user-prompt-submit.sh` | UserPromptSubmit | Every 5 prompts: outcome-first format + scope reminder (ordering rules only) | `hookSpecificOutput.additionalContext` [S21] |
| `pre-tool-use.sh` | PreToolUse (`Write\|Edit\|…`) | Chunk-mode scope lock | `permissionDecision: deny` [S20] |
| `post-tool-use.sh` | PostToolUse (`Write\|Edit\|…`) | Tics warning on `.md/.txt/.rst` written to disk | `additionalContext` (cannot block) [S20] |

All hooks: POSIX sh, `set -u`, exit 0 on any failure, structured log at `~/.claude/harness.log`. The Python CLI bounds itself with an in-process watchdog (`HARNESS_TIMEOUT`, default 12 s; the shell also uses `timeout(1)` where it exists, which macOS lacks). A broken or hung hook never blocks a session (see `tests/test_failopen.py`). On Windows, Claude Code runs command hooks in Git Bash (and only falls back to PowerShell when Git Bash is missing) [S20], so Git Bash is required there; process creation under it is slow, which is why the wrapper spawns exactly one `timeout` and one Python.

Skills: `/harness-status` (what the harness detected and what to do next), `/chunk` (chunk mode), `/harness-doctor` (lint instruction files for this model).

### Model detection order
1. SessionStart stdin `model` — documented but "Claude Code doesn't always include it"; it "can be omitted, for example after `/clear` or when a session is restored through conversation recovery" [S20]. It was absent in every headless run we made (2.1.261 Linux, 2.1.257 Windows), so at session start the identity line says the model is not yet detectable and the Stop gate detects the tier from the transcript by the first turn (`tests/REPORT.md` §6).
2. PostModelSwitch `to_model` [S20].
3. Cache written by the hooks or by the optional status-line script (`plugin/scripts/statusline.sh`, reads `model.id` [S22]; this helper is the one place that needs `jq`).
4. Transcript `message.model` — **UNVERIFIED-BY-DOCS**: the JSONL format is not documented [S34]; observed on 2.1.261.
5. `ANTHROPIC_MODEL` / settings `model` only when it is a full ID (aliases resolve server-side, and the env var does not follow `/model`) [S20, S28].
6. Unknown → generic profile; the model is told to use the model named in its system prompt or state its ID, never to guess. `$CLAUDE_MODEL` does not exist [S20].

## Chunk mode (`/chunk`)

For anything bigger than a single-file edit: `/chunk plan <task>` reads the code at the default high effort and writes 3–8 chunks, each with a goal, scope globs, one runnable acceptance command, and a **recommended effort for the running model** with the cited reason. `/chunk run <n>` activates one: edits outside its paths are denied, the skill prints the exact `/effort <level>` command (or "effort: not supported on this model"), and the Stop gate accepts "done" only after the acceptance command ran and passed, then marks it done. Effort is set by the user (`/effort <level>`); the gate reports mismatches.

Per-model effort table (Claude Code levels [S28]; sweet spots [S14, S45, S4, S8]):

| Model | Levels in Claude Code | mechanical, tested | routine feature | debug / large refactor |
|---|---|---|---|---|
| Fable 5.1 / 5 | low … max | medium | high | high / xhigh |
| Opus 5 | low … max | low | medium | high |
| Opus 4.8 / 4.7 | low … max | medium | high | xhigh |
| Opus 4.6 | low, medium, high, max | medium | medium | high |
| Sonnet 5 | low … max | medium | high | xhigh |
| Sonnet 4.6 | low, medium, high, max | medium | medium | high |
| Haiku 4.5, Sonnet 4.5, Opus 4.5 | none in Claude Code | — | — | — |

Why: Opus 5 "performs best when given the complete task specification up front" [S1] — so plan whole, then execute small; "use low and medium liberally … wherever quality holds" [S14]; Opus 4.7/4.8 "Start with xhigh for coding and agentic use cases" [S14]; Sonnet 4.6 "Medium effort (recommended default)" [S14]; users report medium effort gave better-scoped work on Opus 5 and that only mechanical gates held (COMMUNITY.md).

## Doctor (`/harness-doctor`, `scripts/doctor.py`)

Scans `~/.claude/CLAUDE.md`, project `CLAUDE.md`/`.claude/CLAUDE.md`/`CLAUDE.local.md`, `.claude/rules/**`, skills, and settings.json [S27, S31, S32]. Flags, each with a citation: verification/double-check instructions, thoroughness/anti-laziness cruft, "do not think" rules, forced status scaffolding, word caps (community: decay), Fable anti-formatting / hold-findings lines, duplicated instructions, thinking disabled, unsupported effort levels, missing conciseness/scope lines, long prompts without an end reminder, missing subagent caps. Always a dry-run diff first; `--apply` writes with `.harness.bak` and preserves the file's line endings; `--mode move` keeps removed lines for mixed-model teams. Never edits settings.json.

**Severity follows the detected model's tier** (`research/MODEL_MATRIX.md`). The same "double-check your answer" line is an *error* on Opus 5, where Anthropic says it causes over-verification [S1], and *info* on Sonnet, Haiku and Opus 4.x, where the cross-model guidance recommends an explicit self-check [S8]. Only error/warning findings are ever edited, so `--apply` never strips a self-check line from a Sonnet or Haiku project; on an unknown model it is reported but not removed. `doctor --explain R1` prints the per-tier reasoning with its sources.

```
python3 scripts/doctor.py                      # report + diff, writes nothing
python3 scripts/doctor.py --apply              # after you approved the diff
python3 scripts/doctor.py --profile fable-5 --json
python3 scripts/doctor.py --explain R2         # why this rule has this severity on each tier
python3 scripts/doctor.py --list-rules
```

## Config reference

`~/.claude/harness.json` or `.claude/harness.json` (see `plugin/harness.example.json`); env override `HARNESS_<SECTION>__<KEY>`. Precedence: built-in defaults → the detected model's tier defaults (`config.TIER_DEFAULTS`, every value cited) → user file → project file → env.

| Key | Default | Meaning |
|---|---|---|
| `gate.enabled` | true | Stop gate on/off |
| `gate.max_blocks_per_prompt` | 2 | then allow with a visible warning |
| `gate.require_format` / `gate.max_bullets` | true / 3 | outcome · ≤3 bullets · Verification: · Blockers: |
| `gate.completion_patterns`, `evidence_commands`, `result_patterns`, `weak_evidence_patterns`, `phantom_patterns` | see `config.py` | regex lists |
| `gate.grounding` | per tier: `block` on opus-4x / sonnet-5 / sonnet-4x / haiku / generic, `off` on opus-5 / fable-5 | G7: a claim about an existing project file that no Read/Grep/Edit/Bash call touched this turn is sent back once with "read the file, then answer" ("Never speculate about code you have not opened" [S8]); off on Opus 5 because re-check prompts cause over-verification [S1] and on Fable, which investigates before acting [S28] |
| `gate.grounding_extensions`, `gate.grounding_claim_patterns` | see `config.py` | which file names and claim verbs G7 looks at |
| `tics.stop_mode` / `tics.files_mode` | warn / warn | `off\|warn\|block` (files: warn only) |
| `reminder.every_n_prompts` | 5 | 0 disables |
| `chunk.scope_lock` / `chunk.require_acceptance` | deny / true | `off\|warn\|deny` |

Claude Code settings the harness recommends (`plugin/settings.example.json`): `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` [S1]; optional `statusLine` for model caching [S22]; the built-in `Concise` output style (`outputStyle` [S27]) is a reasonable companion — users report it halves length.

## API (no Claude Code)

`api/python/harness_client.py` and `api/typescript/harness.ts` set `output_config.effort` [S14], keep adaptive thinking on for Opus 5 / Fable [S15], raise before the 400 cases (`thinking: disabled` at xhigh/max on Opus 5 [S2]; any `disabled` on Fable [S6]; `budget_tokens` on 4.7+ [S38]; sampling params [S2]), and prepend the official identity line [S8] plus the profile to the system prompt.

## Limitations

- Model detection depends on Claude Code passing `model` (optional) or on an undocumented transcript field; when neither is available the harness says so instead of guessing.
- The gate recognises evidence by regex over Bash commands and their output; exotic test runners need `gate.evidence_commands` entries. It can be satisfied by a real but irrelevant test run — it raises the floor, it is not a reviewer.
- The Stop gate re-prompts the model at most twice per prompt; Anthropic warns verification instructions cause over-verification on Opus 5 [S1] — the gate is conditional, but a model that cannot produce evidence will spend up to two extra turns.
- Prose tics: prompting alone decays (community); the mechanical check catches a fixed list. Post-processing with a second model is the only complete fix users report; that is out of scope.
- Hallucination and overconfidence are model-level [S10]; nothing here fixes them.
- Destructive shell commands (`rm -rf ~`, reported by users) are a permissions problem, not a completion problem — use Claude Code permission rules / a PreToolUse deny rule for that.
- `PostModelSwitch` and interactive `SessionStart.model` were not exercised interactively (headless only, on Linux and Windows); a `--resume … --model X` relaunch fired no PostModelSwitch, which is why identity that is not backed by a hook field is now provisional. See `tests/REPORT.md` §5–§6 and `HANDOFF.md`.
- Hooks fail open by design, and that includes timeouts: on a slow or heavily loaded machine (Git Bash on Windows spawns processes slowly) a hook can exceed its timeout and its decision is simply dropped — the scope lock or the gate then does nothing for that call. `harness.log` records every hook that ran (`scope_check`, `stop`, `session_start`); a missing line means the hook never finished.

## Contributing

Run `python3 -m pytest -q` (stdlib only + pytest). Add a source to `research/SOURCES.md` before adding a behavioural claim; profile bullets must end with `[src: S#]` (enforced by `tests/test_misc.py`). Community-derived material goes in `COMMUNITY.md` and is labelled as such wherever it surfaces.

License: MIT.

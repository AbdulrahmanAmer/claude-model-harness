# FINDINGS.md — Phase 0

Citations `[S#]` refer to `research/SOURCES.md`. Anything not traceable to a Tier-A source is
marked **UNVERIFIED** or **community**.

## 1. Where the model ID is available (ranked by reliability)

| Rank | Source | Reliability | Evidence |
|---|---|---|---|
| 1 | **`SessionStart` hook stdin `model`** | Documented, but optional: "Only `SessionStart` hooks can receive a `model` field, and Claude Code doesn't always include it." | S20 (verbatim), S37 (`model?: string`) |
| 2 | **`PostModelSwitch` hook stdin `to_model`** | Documented; fires on every `/model` switch (`source: command/picker/sdk/auto/resume`). Needed to *track* changes mid-session. | S20, S37 |
| 3 | **Status line stdin `model.id` / `model.display_name`** | Documented and complete, but it is delivered only to the `statusLine` command, not to hooks. Usable as a cross-check by having the status-line script cache the ID to a file the hooks read. | S22 |
| 4 | **Transcript JSONL `message.model` on `type:"assistant"` lines** | Format is **not documented** (S34 only says the file is "the full conversation transcript"). Observed empirically on CC 2.1.261 [E1]; SDK `SDKAssistantMessage.message` is "shaped like an Anthropic Messages API Message" (S37). Transcript "may lag the in-memory conversation" (S20). → **UNVERIFIED-BY-DOCS**, used as fallback only. |
| 5 | **`claude -p --output-format json` → `modelUsage` / stream `system/init.model`** | Documented, but only in headless mode — not available inside a live interactive hook. | S28, S33 |
| 6 | **`$ANTHROPIC_MODEL` env** | Documented as unreliable: "doesn't change when you switch models with `/model`" and only set if the user set it. Also `ANTHROPIC_DEFAULT_MODEL`, `--model`, settings `model` — all *intent*, not the resolved model, and aliases (`opus`, `fable`) resolve server-side (S28). | S20, S27, S28 |
| — | `$CLAUDE_MODEL` | **Does not exist**: "There is no `$CLAUDE_MODEL` environment variable." | S20 |
| — | Asking the model | Not a source. Anthropic's own docs supply identity in the system prompt (S8 "Model self-knowledge", S12, S13), which is why this repo injects it. |

**Design consequence:** `detect-model.py` order = SessionStart `model` → PostModelSwitch `to_model` (cached) → statusline cache file → transcript `message.model` (newest assistant line) → `ANTHROPIC_MODEL` / settings `model` **only if it is a full ID, never an alias** → `unknown`. Never guess.

**Profile mapping (IDs from S17/S18/S6/S41):** `claude-fable-5-1`, `claude-mythos-5-1` → `fable-5`; `claude-fable-5`, `claude-mythos-5` → `fable-5` (with a note that 5.1-only prompts are marked); `claude-opus-5` → `opus-5`; `claude-opus-4-8`, `-4-7`, `-4-6`, `-4-5*` → `opus-4x`; `claude-sonnet-5`, others → `generic`.

## 2. Official Opus 5 guidance — prompt FOR vs AGAINST

### Prompt FOR (each item is a verbatim-backed instruction)
| # | Behavior | Source |
|---|---|---|
| F1 | **Conciseness**: "To control response length, prompt for it explicitly." Sample: "Keep responses focused, brief, and concise. Keep disclaimers and caveats short…" | S1, S2, S3 |
| F2 | **End-of-prompt reminder** in long system prompts: `<tone_preference>Keep outputs reasonably concise.</tone_preference>` | S1 |
| F3 | **Narration cadence / completion format**: "Before your first tool call, say in one sentence what you're about to do… When you finish, lead with the outcome: your first sentence should answer 'what happened'…" | S1 (Opus 5); S5 (Fable 5 "Lead with the outcome") |
| F4 | **Written-deliverable length**: "do not pad with filler sections, redundant summaries, or boilerplate." | S1 |
| F5 | **Scope constraint**: "Deliver what was asked, at the scope intended… stop short of actions that are clearly beyond what was asked." | S1, S2 |
| F6 | **Subagent cap**: delegation prompt + `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` (CC ≥ 2.1.217). Claude Code adds its own delegation instruction only with the `claude_code` preset. | S1, S2, S3 |
| F7 | **Correction-narration limit**: "Only correct an earlier statement when the error would change the user's code, conclusions, or decisions…" | S1 |
| F8 | **Keep thinking on**; use lower effort instead of disabling: "thinking enabled at `low` effort performs better than thinking disabled at similar cost." | S1, S2, S14, S15 |
| F9 | If thinking must be off: "When you use a tool, you may say a brief sentence first. If no tool can express what the user asked for, say so instead of guessing. Do not include internal or system XML tags in your response." Do **not** name thinking tags. | S1, S16 |
| F10 | **Evidence-backed progress claims** (Fable 5 guide; nearly eliminated fabricated status reports in Anthropic testing): "Before reporting progress, audit each claim against a tool result from this session. Only report work you can point to evidence for…" | S5 — *Fable 5 page*, not the Opus 5 page. Used in `opus-5.md` **only with a cross-model label**; see conflict D2. |
| F11 | **Model identity in system prompt**: "The assistant is Claude, created by Anthropic. The current model is Claude Opus 5." | S8, S12, S13 |

### Prompt AGAINST (remove these)
| # | Anti-pattern | Source |
|---|---|---|
| A1 | Verification instructions ("include a final verification step", "use a subagent to verify"): "remove them: instructions like these cause over-verification on Claude Opus 5… The same applies to legacy harness scaffolding that adds separate verification steps." | S1, S2, S3, S8 |
| A2 | Re-check instructions ("double-check your answer", "re-verify before responding"): "compound with the model's own behavior and add cost without improving results." | S1 |
| A3 | Disabling thinking (esp. tool-heavy): causes "tool calls as text" and internal XML tags; rejected outright at `xhigh`/`max` (400). | S1, S2, S14, S15, S16 |
| A4 | "Do not think / do not reason" rules: "that kind of instruction increases tag leakage." | S1, S16 |
| A5 | Relying on `effort` to shorten output: "does not reliably shorten the visible response." | S1, S14 |
| A6 | (Cross-generation cruft) "be thorough / if in doubt use the tool / CRITICAL: you MUST" anti-laziness prompting written for ≤4.5: "dial back that guidance… may overtrigger." | S8 (stated for 4.6; carried as *legacy cruft* finding, cited as such) |
| A7 | Forced interim status scaffolding ("After every 3 tool calls, summarize progress"): "try removing it." | S2, S9 (Opus 4.7/4.8) |
| A8 | Over-prescriptive skills/prompts written for prior models (Fable): "often too prescriptive… can degrade output quality." | S5 |
| A9 | Telling the model to echo its reasoning as response text (Fable 5: can trigger `reasoning_extraction` refusal). | S5 |

### Fable 5.1-specific deltas (for `fable-5.md`)
Ask *for* progress updates and remove "hold findings" lines (S4, S8); "Finish the whole task" autonomy block incl. last-paragraph check (S4); "Delivering work" scope block (S4); mannered-prose definition / "Please remove all mannered prose." (S4); remove anti-formatting rules (S4, S7); thinking cannot be disabled, forced `tool_choice` → 400 (S6); per-turn reminders must go in as turn-scoped system messages, not history edits (S4, S6); official style-tic line: avoid "genuinely", "honestly", "straightforward" (S13 — claude.ai system prompt, Fable 5.1).

## 3. Fixable vs model-level (for an honest README)

| Reported failure | Verdict | Basis |
|---|---|---|
| Monologuing / long responses / narration | **Prompt-fixable** (explicit conciseness + cadence prompt + end-of-prompt reminder; effort does *not* fix it). Claude Code also ships a "Concise" output style (2.1.237). | S1, S2, S3, S44 |
| Over-verification / self-check loops | **Config-fixable by removal**: delete verification/double-check instructions and legacy verifier scaffolding. Underlying tendency is model-level (system card §2.2.6 "prone to descending into exhaustive correctness checks"), so it can be reduced, not eliminated. | S1, S2, S10 |
| Scope creep / over-engineering | **Prompt-mitigable** (scope block); tendency is model-level (system card §2.2.6 "poor calibration of task scope"). | S1, S10 |
| Phantom tool calls (tool call written as text) | **Config-fixable for the documented cause** (thinking disabled → keep thinking on, lower effort; mitigation prompt). Occurrences with thinking *on* are not documented for Opus 5; the Fable 5 guide documents "text-only statement of intent" deep in long sessions (S5). A harness-level detector (this repo's Stop gate) catches both regardless of cause. | S1, S5, S15, S16, S44 (2.1.221 harness-side cause) |
| Claiming done when not / fabricated status | **Partially fixable**: the evidence-audit prompt "nearly eliminated fabricated status reports" in Anthropic's Fable 5 testing (S5); the "Finish the whole task" block targets describing-instead-of-doing (S4); Claude Code 2.1.211 fixed one harness-side fabrication path (S44). Overconfidence itself is a measured model property ("confidently stated an answer about which it was in fact unsure", S10). A deterministic Stop-gate that demands tool evidence is the honest complement. | S4, S5, S10, S11, S44 |
| Confident wrong answers / hallucination rate | **Model-level.** "hallucinates factual claims slightly more than Opus 4.8" (S10). No prompt fix offered in the Opus 5 guide; the grounding prompt in S8 (`investigate_before_answering`) helps for code claims only. README must say so. | S10, S8 |
| "Claudism" prose tics | **Partially fixable, community-documented decay.** Official: Fable 5.1 guide's mannered-prose definition (S4) and the claude.ai line avoiding "genuinely/honestly/straightforward" (S13). The word-level blocklist ("load-bearing", "it's worth noting", "it's not X, it's Y") is **community-derived** (C2–C5) and reported to decay over long contexts (C3, C4) → the repo's PostToolUse warn-only check exists because prompting alone is not reliable. | S4, S13; C2–C5 |

### 3b. What users report vs what fixes hold (see `research/COMMUNITY.md` for evidence)

| Lever | Community durability | Design consequence |
|---|---|---|
| Stop hook that blocks | **Held** — no decay reports (4 independent) | Completion gate + mechanical tics check are the core; profiles are secondary |
| Mechanical receipts (test output, git SHA, reviewer) | Held / partial | Gate demands *tool output with a result*, flags rigged checks |
| Switch back to Opus 4.8 | Worked (10+) | README says plainly this repo does not replace that option |
| Effort → medium | Worked for scope, not length (6) | Doctor reports effort level; medium noted as community, `high` as official default |
| Output style / UserPromptSubmit reminder | Partial, decays | Reminder = ordering rule only (outcome first), every N turns; no word caps |
| CLAUDE.md rules alone | Decays in 2–6 turns (8+) | Nothing load-critical lives only in CLAUDE.md |
| Post-process with 2nd model | Worked, costly | Out of scope; mentioned in README |

Most-reported pain, by volume: verbosity → tics → scope creep → instruction decay → false "done" (fewest posts, highest severity) → confident wrong claims → phantom tool calls (rare with thinking on; Reddit: none).

## 4. Hook mechanics confirmed (what the code may rely on)

- Stop hook: input has `stop_hook_active`, `last_assistant_message`, `transcript_path`; block with top-level `{"decision":"block","reason":"…"}` — reason is fed back to Claude; exit 2 + stderr also blocks; Claude Code force-allows after 8 consecutive blocks (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`). Our cap of 2 sits well inside that. [S20, S21, S37]
- Stop and UserPromptSubmit take **no matcher**. [S20]
- UserPromptSubmit: `hookSpecificOutput.additionalContext` (nested — top-level is silently ignored), injected "as a system reminder that Claude reads as plain text"; default timeout lowered to 30 s. [S20, S21]
- SessionStart: cannot block; **plain-text stdout is added to context** (documented) and `hookSpecificOutput.additionalContext` exists in SDK types. `source` ∈ startup/resume/clear/compact/fork; the `compact` matcher lets us re-inject after compaction. [S20, S21, S37]
- PostToolUse: cannot block; `additionalContext` / `systemMessage` honored; `tool_name`, `tool_input`, `tool_response`. [S20, S37]
- Hooks fail open by construction: exit 0 + no stdout = no effect; non-zero non-2 = "non-blocking error" notice only. [S20, S21]
- Plugin packaging: `.claude-plugin/plugin.json` (only `name` required), `hooks/hooks.json`, `skills/<name>/SKILL.md`; marketplace via `.claude-plugin/marketplace.json` in the same GitHub repo → `/plugin marketplace add OWNER/claude-model-harness` then `/plugin install claude-model-harness@claude-model-harness`; local dev via `claude --plugin-dir ./plugin`; `claude plugin validate`. [S23–S26]
- Subagent caps: `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` (CC ≥ 2.1.217) — set via settings `env`. [S1, S27]
- Thinking in Claude Code: `MAX_THINKING_TOKENS=0` disables thinking "except on Fable 5.1 and Fable 5" → doctor flags this on Opus 5 (leak risk, A3) and flags it as a no-op on Fable. Effort: `CLAUDE_CODE_EFFORT_LEVEL` / `--effort` / `/effort`. [S28]

## 5. Doc-vs-design conflicts to decide at Gate 1

| ID | Conflict | Proposed resolution |
|---|---|---|
| D1 | `SessionStart` `model` is optional ("doesn't always include it"). | Ranked fallback chain (§1); `unknown` → generic profile + instruction to state its ID. Also register a `PostModelSwitch` hook (not in the original tree) so a mid-session `/model` switch re-injects identity + profile — it is the only documented way to follow model changes. |
| D2 | The Stop-gate re-prompts the model to show evidence, while the Opus 5 guide says verification instructions cause over-verification (A1/A2). | The gate is **conditional and deterministic**: it fires only when a completion claim has no tool evidence, and its reason asks for *evidence or a restated status*, never "verify your work". Profiles contain no standing verification instruction. README states this trade-off with S1 cited. |
| D3 | Requested "phantom tool call" detection needs the assistant text; transcript "may lag" (S20). | Use `last_assistant_message` (documented for exactly this) for the current turn; read transcript only for *earlier* evidence (tool_use/tool_result blocks), tolerating lag. |
| D4 | `additionalContext` support list (summarizer-derived) omits SessionStart, but SDK types include it and plain-text stdout is documented. | SessionStart hook emits **plain text** (documented path). Live smoke test in Phase 3 confirms; if JSON also works, keep plain text anyway. |
| D5 | Transcript `message.model` is undocumented. | Keep as ranked-4 fallback, labelled `UNVERIFIED` in code + README. |
| D6 | Fable 5.1 warns that editing history invalidates thinking blocks / restarts cache. Hook `additionalContext` is appended to the new user turn, not an edit — no conflict, but the profile must not tell users to rewrite system prompts mid-session. | Note in `fable-5.md`. |
| D7 | Opus 5 tics: only "genuinely / honestly / straightforward" (S13) and mannered prose (S4, Fable 5.1 page) are official; the rest is community. | Blocklist section in profiles/PROMPT.md is labelled "community-derived (C2–C5), not official". |
| D8 | User design has `hooks/*.sh` names; Stop and UserPromptSubmit accept no `matcher` — fine; SessionStart gets `matcher: "startup|resume|clear|compact"` (all sources) so compaction re-injects. | Adopt. |
| D9 | The Fable 5 guide *recommends* explicit verifier subagents (S5) while the Opus 5 guide forbids verification prompts. | Profiles are per-model: `fable-5.md` allows "Verify your work however you like" (S4) and does not forbid verifiers; `opus-5.md` forbids. Doctor's "verification cruft" finding is severity **error** for Opus 5 profile, **info** for Fable/generic. |
| D10 | Community: deleting verification rules "degrades every other Claude model in a mixed workflow" (r/ClaudeAI 1vd57c0, 30↑). | Doctor `--apply` offers *mark* (wrap the line in an `<!-- harness: opus-5 ignores -->` comment) or *delete*; default is mark. |
| D11 | Community: rigged verification ("PASS check that cannot fail", "checks out main to prove failure is pre-existing", "0 tests collected") passes a naive "did a test command run" gate. | Gate scores evidence: strong = test/build/lint tool call whose output contains a result token (`passed`, `failed`, `ok`, exit code); weak = `\|\| true`, `--no-verify`, `0 tests`, `-k`/`--filter` narrowing, `git checkout main`/`stash` before the run; weak-only evidence → block once with the specific reason. |
| D12 | Community: prose tics decay in 2–6 turns; only mechanical checks held. Original design had tics as PostToolUse warn-only on files. | Add a Stop-hook tics check on `last_assistant_message`: `warn` (default) or `block` (opt-in). Same regex list, three tiers: official (S13), mannered-prose patterns (S4), community (C2–C5). |
| D13 | Community: word caps decay; ordering rules survive. | UserPromptSubmit reminder is the completion format + scope line only; configurable cadence (default every 5 prompts); never a word ceiling. |

## 6. Open items carried to Phase 3 (live test must confirm)
1. `SessionStart` stdin actually contains `model` on CC 2.1.261 (and in which `source` cases).
2. Plain-text stdout from SessionStart is visible to the model (ask it to echo the identity line).
3. Stop `{"decision":"block"}` reason reaches the model and `stop_hook_active` flips to true on the retry.
4. `PostModelSwitch` fires on `/model` and carries `to_model`.

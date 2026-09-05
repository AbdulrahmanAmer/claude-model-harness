# MODEL_MATRIX.md — official behaviour matrix, one row per current Claude model

Every cell cites an official Anthropic page (`[S#]` → `research/SOURCES.md`). All pages were fetched as raw
markdown on **2026-09-05** (`research/mirror-index-2026-09-05.tsv` lists URL, HTTP status, size, SHA-256 prefix
and UTC timestamp for each). S10 and S11 are system-card PDFs read in Phase 0 (partial); they are not in the markdown mirror, so their quotes are
not script-checked and every cell that uses them says so. Cells that say **no official statement** mean the pages listed in SOURCES.md contain
nothing on that dimension for that model; nothing in this repo is built on such a cell. Community reports are
kept out of this file entirely (see `research/COMMUNITY.md`).

Legend for the *Self-check* column: **harmful** = Anthropic says to remove verification instructions;
**recommended** = the cross-model "Ask Claude to self-check" default applies [S8]; **explicit verifiers** =
the guide recommends verifier subagents on long runs.

## The matrix

| Model | API ID (Claude Code `/model` accepts the same string) | Harness tier | Response-length default | Thoroughness / laziness | Self-check | Tool calls, thinking on vs off | Effort: API / Claude Code, default | Subagents | Known failure modes (official) | Identity line source |
|---|---|---|---|---|---|---|---|---|---|---|
| Claude Fable 5.1 (Claude Mythos 5.1 shares the model) | `claude-fable-5-1` / `claude-mythos-5-1` [S6, S17] | `fable-5` | Fewer user-facing updates than Fable 5; final message may cover only the last step [S4]. In some cases denser prose than Fable 5 (longer sentences, fewer paragraph breaks) [S4]. Uses less formatting than earlier models [S4]. claude.ai: "outputs are reasonably concise" [S13] | Executes very long tasks with little guidance; sometimes describes the next step instead of doing it, or asks permission for a step already requested [S4]. Delivers what was asked "and sometimes more" (fixes nearby code, extra tests) [S4]. At `low`, calls search/retrieval less and answers from memory [S4]. Rewrites whole files more than Fable 5 [S4] | **Recommended** (cross-model default; Opus 5 is the only named exception) [S8]. The 5.1 guide has no verification-instruction guidance (its only "verify" line is text inside a sample scope prompt) [S4]. The Fable 5 guide recommends fresh-context verifier subagents on long runs, measured on Fable 5 [S5]; S8 says to re-check model-named techniques on your own evals before applying them to another model [S8]. System card (PDF, not mirrored): "exaggerates the completeness of its work, fails to verify important claims" [S11] | Thinking always on; `thinking: disabled` → 400 at any effort [S6, S16]. `tool_choice` `any`/`tool` → 400 [S6, S19]. Issues parallel calls as expected when a request names several things; in long agent loops where the next calls are only implied (coding and computer-use harnesses) it may issue one call per turn, so send a batching instruction as a turn-scoped system message [S4, S6] | API: `low`…`max`, default `high` [S14]; per-message effort (beta) keeps cache [S14]. Claude Code: `low`…`max`, default `high` [S28, S43] | Lead agent should keep working while subagents run [S4]; parallel-calls instruction after each round of tool results [S8] | Describes-instead-of-doing; unmarked quotations; denser prose in some cases; whole-file rewrites; low-effort search skipping [S4]. System card (PDF, not mirrored): misrepresents prior findings; exaggerates completeness [S11] | "This iteration of Claude is Claude Fable 5.1" [S13]; avoids "genuinely", "honestly", "straightforward" [S13] |
| Claude Fable 5 (Claude Mythos 5) | `claude-fable-5` / `claude-mythos-5` [S41, S18] | `fable-5` | Can "elaborate beyond what the task needs, especially at higher effort"; arrow-chain shorthand in long sessions [S5]. Longer turns by default (minutes to hours) [S5] | At higher effort on routine work "can gather context and deliberate beyond what the task needs"; higher effort "often produces excellent verification behavior" [S5]. Strong instruction following: one brief instruction steers most behaviours [S5] | **Explicit verifiers recommended**: "Make self-verification explicit in long-run prompts. Separate, fresh-context verifier subagents tend to outperform self-critique" [S5]; evidence-audit prompt "nearly eliminated fabricated status reports" [S5] | Thinking always on; `disabled` → 400 [S16, S41]. Deep into long sessions can "end a turn with a text-only statement of intent ('I'll now run X') without issuing the corresponding tool call" [S5] | API: `low`…`max`, default `high`; per-message effort → 400 [S14]. Claude Code: `low`…`max`, default `high`, and the default is held across sessions until changed once [S28] | Parallel subagents section; explicit verifier subagents [S5] | Rare early stopping; context-budget worry when a countdown is shown; unrequested actions (drafting an email, git-branch backups); `reasoning_extraction` refusal when told to echo reasoning [S5] | "This iteration of Claude is Claude Fable 5" [S63] |
| Claude Opus 5 | `claude-opus-5` [S2, S17] | `opus-5` | "default user-facing responses run longer than prior Opus models'"; lowering effort "can reduce thinking volume without reliably shortening the visible response" [S1, S14]. Narrates progress more often; written deliverables run longer [S3]. Exception to the cross-model "less verbose" trend [S8] | "verifies its own work without being told to"; "can also expand the scope of a task, adding steps that weren't requested" [S1]. System card (PDF, not mirrored): "unproductive self-verification", "poor calibration of task scope" [S10] | **Harmful**: "If your prompt contains explicit verification instructions … remove them: instructions like these cause over-verification" [S1]; "Avoid instructing re-checks it already performs ('double-check your answer,' 're-verify before responding')" [S1]; the stated exception to the cross-model self-check default [S8] | Thinking on by default; `disabled` accepted only at effort ≤ `high`, else 400 [S2, S15, S16]. With thinking off it "occasionally writes a tool call into its user-facing text instead of emitting a structured tool_use block" and can emit internal XML tags [S1, S16]; "thinking enabled at low effort performs better than thinking disabled" [S1, S8] | API: `low`…`max`, default `high`; "use low and medium liberally"; effort "does not reliably shorten responses" [S14]. Per-message effort (beta) [S14]. Claude Code: `low`…`max`, default `high`, no held default [S28] | "delegates to subagents more readily than prior models"; caps: `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` (Claude Code ≥ 2.1.217) [S1, S3, S8] | Over-verification when prompts carry verification or re-check instructions; scope expansion; narrated corrections [S1]. System card (PDF, not mirrored): hallucinates factual claims slightly more than Opus 4.8; confident when unsure [S10] | "The currently selected version of Claude is Claude Opus 5" [S12]; avoids "genuinely", "honestly", "straightforward" [S12] |
| Claude Opus 4.8 | `claude-opus-4-8` [S55, S18] | `opus-4x` | "calibrates response length to how complex it judges the task to be" [S9]. claude.ai: "keeps responses focused, brief, and concise" [S62] | "respects effort levels strictly, especially at the low end. At low and medium, the model scopes its work to what was asked"; at `low` "some risk of under-thinking" [S9]. "tendency to favor reasoning over tool calls" [S9]. Literal instruction following [S9] | **Recommended** (cross-model default): "Append something like 'Before you finish, verify your answer against [test criteria].' This catches errors reliably" [S8] | Thinking **off** unless `thinking: {type: "adaptive"}` is set [S9, S16]; `enabled`/`budget_tokens` → 400 [S16, S38]. Tool-call-as-text leakage is documented only for Opus 5 [S16] | API: `low`…`max`, default `high`, start at `xhigh` for coding [S14]. Claude Code: `low`…`max`; default held across sessions until changed once [S28] | "tends to spawn fewer subagents by default" [S9] | Some risk of under-thinking at `low`; conservative code-review prompts suppress findings; persistent design house style [S9] | "The currently selected version of Claude is Claude Opus 4.8" [S62] |
| Claude Opus 4.7 | `claude-opus-4-7` [S52, S18] | `opus-4x` | "calibrates response length to how complex it judges the task to be, rather than defaulting to a fixed verbosity" [S2]. claude.ai: "keeps its responses focused and concise" [S59] | "interprets prompts more literally and explicitly than Claude Opus 4.6"; "respects effort levels strictly, especially at the low end"; "tendency to use tools less often than Claude Opus 4.6 and to use reasoning more" [S2]. Built-in progress updates; remove forced status scaffolding [S2] | **Recommended** (cross-model default) [S8] | Thinking off unless adaptive is set [S16]; `enabled` → 400 [S16, S38]. No leakage statement for this model [S16] | API: `low`…`max`; API default `high`, recommended start `xhigh`; "Pair low with explicit checklists" [S14]. Claude Code: `low`…`max`; **defaults to `xhigh`** in Claude Code [S28] | "tends to spawn fewer subagents by default than Claude Opus 4.6" [S2] | Some risk of under-thinking at `low` on moderately complex tasks; requests on prohibited or high-risk cyber topics may be refused [S2] | "This iteration of Claude is Claude Opus 4.7" [S59] |
| Claude Opus 4.6 | `claude-opus-4-6` [S53, S18] | `opus-4x` | No model-specific length statement; cross-model: "Less verbose: May skip detailed summaries" [S8]. claude.ai avoids "genuinely", "honestly", "straightforward" [S60] | "does more upfront exploration than previous models, especially at higher effort settings"; "may think extensively" [S8]. "more responsive to the system prompt … may now overtrigger"; "Instructions like 'If in doubt, use [tool]' will cause overtriggering" [S8]. Over-engineers: extra files, abstractions [S8] | **Recommended** (cross-model default) [S8] | Thinking off by default; adaptive or extended (deprecated) [S16]. "may take actions that are difficult to reverse or affect shared systems" → reversibility prompt [S8] | API: `low`, `medium`, `high`, `max` (no `xhigh`), default `high` [S14]. Claude Code: same four; `xhigh` runs as `high` [S28] | "strong predilection for subagents and may spawn them in situations where a simpler, direct approach would suffice" [S8] | Over-exploration; over-triggering on strong wording; over-engineering; risky irreversible actions; subagent overuse [S8] | "This iteration of Claude is Claude Opus 4.6" [S60] |
| Claude Opus 4.5 | `claude-opus-4-5-20251101` [S54, S18] | `opus-4x` | No length statement in the platform docs (cross-model only) [S8]; claude.ai (2026-01-18 prompt): "In casual conversation, it's fine for Claude's responses to be relatively short" [S61] | "more responsive to the system prompt … may now overtrigger" on prompts written to reduce tool or skill under-triggering ("CRITICAL: You MUST use this tool") [S8]. Over-engineers [S8]. With thinking off, "particularly sensitive to the word 'think'" [S8] | **Recommended** (cross-model default) [S8] | Extended thinking only, off by default; `adaptive` → 400 [S16]. Effort composes with `budget_tokens` [S14] | API: supported (`claude-opus-4-5-20251101` in the supported list), default `high` [S14, S54]. Claude Code: not listed → "Models not listed here do not support effort" [S28] | No official statement | Over-triggering; over-engineering [S8] | "This iteration of Claude is Claude Opus 4.5" [S61] |
| Claude Sonnet 5 | `claude-sonnet-5` [S46, S17] | `sonnet-5` | "calibrates response length to the complexity of the task rather than defaulting to a fixed verbosity" [S45] | "more agentic than Claude Sonnet 4.6 by default and will reach for tools and run self-verification loops more readily" [S45]. "respects effort levels strictly, especially at the low end"; at `low` "some risk of under-thinking" [S45]. Literal instruction following; built-in progress updates [S45] | **Recommended** (cross-model default; Sonnet 5 is not named as an exception) [S8]. S45 adds that the model "will reach for tools and run self-verification loops more readily" than Sonnet 4.6 but gives no instruction to remove or shorten verification prompts [S45] | Thinking on by default; `disabled` accepted at any effort [S2, S16, S46]. "With thinking disabled, the model is less likely to reach for tools or consider searching; if you rely on tool calls with thinking off, add an explicit nudge" [S45]. Tool-call-as-text leakage documented only for Opus 5 [S16] | API: `low`…`max`, default `high`; `xhigh` for the hardest coding; `medium` ≈ Sonnet 4.6 at `high` [S14, S45]. Claude Code: `low`…`max`, default `high` [S28] | No model-specific statement; cross-model: orchestrates subagents natively [S8] | Some risk of under-thinking at `low`; conservative review prompts suppress findings; fixed design style; cyber refusals return `stop_reason: "refusal"` [S45, S46] | No claude.ai system-prompt page exists for Sonnet 5 (404 on 2026-09-05); identity from the official template "The assistant is Claude, created by Anthropic. The current model is …" [S8] with the string from [S17]; 'claude-sonnet-5' is listed as a model string in [S12, S13] |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` [S48, S18] | `sonnet-4x` | No model-specific length statement (cross-model only) [S8]. claude.ai avoids "genuinely", "honestly", "straightforward" [S56] | "Claude 4.6 models are more proactive and may overtrigger on instructions that were needed for previous models" → tune anti-laziness prompting [S8]. Has context awareness [S8] | **Recommended** (cross-model default) [S8] | Thinking off by default; adaptive or extended (deprecated) [S16]. Prefill → 400 [S47] | API: `low`, `medium`, `high`, `max` (no `xhigh`); default `high` but "Medium effort (recommended default)" [S14]. Claude Code: same four; `xhigh` → `high` [S28] | No official statement | Over-triggering (4.6 generation) [S8] | "This iteration of Claude is Claude Sonnet 4.6" [S56] |
| Claude Sonnet 4.5 | `claude-sonnet-4-5-20250929` [S49, S18] | `sonnet-4x` | claude.ai (2026-01-18 prompt): "In casual conversation, it's fine for Claude's responses to be relatively short, e.g. just a few sentences long"; avoids over-formatting [S57]. Claude 4 family vs 3.x: "Claude 4 models have a more concise, direct communication style" [S47] | No model-specific thoroughness statement. Context awareness [S8] | **Recommended** (cross-model default) [S8] | Extended thinking only, off by default; `adaptive` → 400 [S16] | **Not supported** ("Sonnet 4.5 which had no effort parameter") [S47, S49]. Claude Code: not listed [S28] | No official statement | No model-specific statement; prefill and tool-JSON escaping change when migrating [S47] | "This iteration of Claude is Claude Sonnet 4.5" [S57] |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` (alias `claude-haiku-4-5`) [S17, S50] | `haiku` | claude.ai (2026-01-18 prompt): "In casual conversation, it's fine for Claude's responses to be relatively short, e.g. just a few sentences long"; avoids over-formatting [S58] | No official statement on thoroughness or laziness. "For significant performance improvements on coding and reasoning tasks, consider enabling extended thinking" [S51]. Context awareness [S8] | **Recommended** (cross-model default) [S8] | Extended thinking only, off by default; `adaptive` → 400 [S16]. `temperature` or `top_p`, not both [S51] | **Not supported** [S17, S47, S50]. Claude Code: not listed → no `/effort` [S28] | No official statement; Claude Code describes the `haiku` alias as "for simple tasks" [S28] | No official statement | "This iteration of Claude is Claude Haiku 4.5" [S58] |

Cross-model rules that apply to every row unless a cell overrides them [S8]: `<investigate_before_answering>` grounding ("Never speculate about code you have not opened"); parallel tool calls with "Never use placeholders or guess missing parameters"; over-engineering prompt; "Migrating … Tune anti-laziness prompting" for 4.6+; model self-knowledge prompt "The assistant is Claude, created by Anthropic. The current model is Claude Opus 5." with the model string. Thinking defaults per model are in the table on [S16].

## Verbatim evidence (checked by script against the mirrored pages)

Each line is `[S#] "exact text"`; `scratchpad/check_quotes.py` greps every quote in the page it cites. Quotes are
single sentences or shorter so the check is strict.

### Fable 5.1
- [S4] "Claude Fable 5.1's default behavior is to write fewer user-facing updates during long tool-calling turns than Claude Fable 5 does."
- [S4] "In some cases, though, its prose is denser than Claude Fable 5's: sentences run longer and there are fewer paragraph breaks."
- [S4] "Claude Fable 5.1 leans the other way: it uses bold less and is less likely to reach for headers, lists, or quotation marks."
- [S4] "Without the nudge, the model sometimes describes what it would do next instead of doing it"
- [S4] "Claude Fable 5.1 delivers what's asked for and sometimes more: it may fix nearby code, extend behavior the task didn't mention, or commit more test files than the change warrants."
- [S4] "At `low` effort, Claude Fable 5.1 is less likely than Claude Fable 5 to call a search or retrieval tool, and more likely to answer from memory."
- [S4] "Claude Fable 5.1 is more likely than Claude Fable 5 to rewrite an entire text file rather than make a targeted edit."
- [S4] "Claude Fable 5.1 usually issues parallel tool calls as expected: when a request names several things to fetch, it issues those calls in parallel."
- [S8] "Where a technique names a specific model, treat it as measured on that model and re-check it against your own evals before applying it to another."
- [S4] "Start at the default [effort](https://platform.claude.com/docs/en/build-with-claude/effort) level, `high`, then test the other levels"
- [S4] "Claude Fable 5.1 is more likely than Claude Fable 5 to reproduce passages of the source text without marking them as quotations."
- [S13] "This iteration of Claude is Claude Fable 5.1"
- [S13] "Claude avoids saying \"genuinely\", \"honestly\", or \"straightforward\"."
- [S13] "Claude's outputs are reasonably concise."
- [S16] "| Claude Fable 5.1      | Adaptive only                    | Always on | `\"enabled\"`, `\"disabled\"`  |"
- [S19] "On Claude Fable 5.1 and Claude Mythos 5.1, `tool_choice` types `any` and `tool` aren't supported and return a 400 error."
- [S28] "| Fable 5.1 and Fable 5                    | `low`, `medium`, `high`, `xhigh`, `max` |"

### Fable 5
- [S5] "Individual requests on hard tasks can run for many minutes at higher"
- [S5] "On routine work at higher effort, Claude Fable 5 can gather context and deliberate beyond what the task needs."
- [S5] "Make self-verification explicit in long-run prompts."
- [S5] "Separate, fresh-context verifier subagents tend to outperform self-critique."
- [S5] "In Anthropic's testing, this nearly eliminated fabricated status reports even on tasks designed to elicit them"
- [S5] "Before reporting progress, audit each claim against a tool result from this session."
- [S5] "Deep into a long session, Claude Fable 5 can occasionally end a turn with a text-only statement of intent"
- [S5] "Claude Fable 5 can occasionally take unrequested actions (drafting an email when none was asked for, creating defensive git-branch backups)."
- [S5] "Skills developed for prior models are often too prescriptive for Claude Fable 5 and can degrade output quality."
- [S14] "Models without per-message effort, including Claude Fable 5, return a 400 error"
- [S41] "| Claude Fable 5  | `claude-fable-5`  |"
- [S63] "This iteration of Claude is Claude Fable 5"

### Opus 5
- [S1] "Claude Opus 5's default user-facing responses run longer than prior Opus models'."
- [S1] "lowering effort can reduce thinking volume without reliably shortening the visible response."
- [S1] "Claude Opus 5 verifies its own work without being told to."
- [S1] "remove them: instructions like these cause over-verification on Claude Opus 5"
- [S1] "Claude Opus 5 can also expand the scope of a task, adding steps that weren't requested"
- [S1] "Claude Opus 5 delegates to subagents more readily than prior models."
- [S1] "Avoid instructing re-checks it already performs (\"double-check your answer,\" \"re-verify before responding\")"
- [S1] "With thinking disabled, the model occasionally writes a tool call into its user-facing text instead of emitting a structured `tool_use` block."
- [S1] "With thinking disabled, two artifacts can occasionally appear in the model's visible output."
- [S1] "If your system prompt contains a rule instructing the model not to think or not to reason, remove it; that kind of instruction increases tag leakage."
- [S1] "They require Claude Code 2.1.217 or later"
- [S3] "In multi-agent frameworks, it delegates to subagents more readily. It also verifies its own work without being told to"
- [S8] "Claude Opus 5 is the exception: it verifies its own work well without explicit instruction"
- [S8] "Claude Opus 5 is an exception on verbosity: its default user-facing responses run longer than prior models'"
- [S12] "The currently selected version of Claude is Claude Opus 5."
- [S14] "On Claude Opus 5, thinking cannot be disabled at `xhigh` or `max` effort"
- [S14] "use `low` and `medium` liberally as your primary control for token cost and response time wherever your evals show quality holds"
- [S16] "This happens on Claude Opus 5 when thinking is disabled, most commonly on tool-heavy workloads such as search."
- [S28] "| Opus 5, Sonnet 5, Opus 4.8, and Opus 4.7 | `low`, `medium`, `high`, `xhigh`, `max` |"

### Opus 4.8
- [S9] "Claude Opus 4.8 calibrates response length to how complex it judges the task to be, rather than defaulting to a fixed verbosity."
- [S9] "Claude Opus 4.8 respects effort levels strictly, especially at the low end."
- [S9] "At `low` and `medium`, the model scopes its work to what was asked rather than going above and beyond."
- [S9] "Claude Opus 4.8 has a tendency to favor reasoning over tool calls."
- [S9] "Claude Opus 4.8 tends to spawn fewer subagents by default."
- [S9] "On Claude Opus 4.8, thinking is off unless you explicitly set `thinking: {type: \"adaptive\"}`."
- [S9] "Claude Opus 4.8 interprets prompts literally and explicitly, particularly at lower effort levels."
- [S9] "Provide concise, focused responses. Skip non-essential context, and keep examples minimal."
- [S14] "The guidance for Claude Opus 4.7 also applies to Claude Opus 4.8."
- [S28] "The model's default effort, on Fable 5, Opus 4.8, or Opus 4.7: from the first time you run one of these models, Claude Code holds that model's default effort across sessions"
- [S62] "The currently selected version of Claude is Claude Opus 4.8."
- [S62] "Claude keeps responses focused, brief, and concise to avoid overwhelming the person."

### Opus 4.7
- [S2] "Claude Opus 4.7 calibrates response length to how complex it judges the task to be, rather than defaulting to a fixed verbosity."
- [S2] "Claude Opus 4.7 interprets prompts more literally and explicitly than Claude Opus 4.6, particularly at lower effort levels."
- [S2] "Claude Opus 4.7 tends to spawn fewer subagents by default than Claude Opus 4.6"
- [S2] "Claude Opus 4.7 respects [effort levels](https://platform.claude.com/docs/en/build-with-claude/effort) strictly, especially at the low end."
- [S2] "Claude Opus 4.7 has a tendency to use tools less often than Claude Opus 4.6 and to use reasoning more."
- [S2] "If you've added scaffolding to force interim status messages (\"After every 3 tool calls, summarize progress\"), try removing it."
- [S14] "Pair `low` with explicit checklists if your task has multiple sections."
- [S28] "except that Opus 4.7 defaults to `xhigh`"
- [S59] "This iteration of Claude is Claude Opus 4.7"
- [S59] "Claude keeps its responses focused and concise"

### Opus 4.6
- [S8] "Claude Opus 4.6 does more upfront exploration than previous models, especially at higher"
- [S8] "Instructions like \"If in doubt, use \\[tool]\" will cause overtriggering."
- [S8] "Claude Opus 4.5 and Claude Opus 4.6 are also more responsive to the system prompt than previous models."
- [S8] "Claude Opus 4.5 and Claude Opus 4.6 have a tendency to overengineer by creating extra files, adding unnecessary abstractions, or building in flexibility that wasn't requested."
- [S8] "Without guidance, Claude Opus 4.6 may take actions that are difficult to reverse or affect shared systems"
- [S8] "Claude Opus 4.6 has a strong predilection for subagents and may spawn them in situations where a simpler, direct approach would suffice."
- [S8] "In some cases, Claude Opus 4.6 may think extensively"
- [S28] "For example, `xhigh` runs as `high` on Opus 4.6."
- [S28] "| Opus 4.6 and Sonnet 4.6                  | `low`, `medium`, `high`, `max`          |"
- [S60] "This iteration of Claude is Claude Opus 4.6"

### Opus 4.5
- [S8] "When extended thinking is disabled, Claude Opus 4.5 is particularly sensitive to the word \"think\" and its variants."
- [S14] "On Claude Opus 4.5, the only extended-thinking-only model that supports effort, it works alongside"
- [S16] "| Claude Opus 4.5       | Extended only                    | Off       | `\"adaptive\"`               |"
- [S54] "Model ID: `claude-opus-4-5-20251101`"
- [S61] "In casual conversation, it's fine for Claude's responses to be relatively short, e.g. just a few sentences long."
- [S28] "Models not listed here do not support effort:"
- [S61] "This iteration of Claude is Claude Opus 4.5"

### Sonnet 5
- [S45] "Claude Sonnet 5 calibrates response length to the complexity of the task rather than defaulting to a fixed verbosity."
- [S45] "Claude Sonnet 5 is more agentic than Claude Sonnet 4.6 by default and will reach for tools and run self-verification loops more readily."
- [S45] "With thinking disabled, the model is less likely to reach for tools or consider searching; if you rely on tool calls with thinking off, add an explicit nudge in the system prompt."
- [S45] "Claude Sonnet 5 respects effort levels strictly, especially at the low end."
- [S45] "This is good for latency and cost, but on moderately complex tasks running at `low` effort there is some risk of under-thinking."
- [S45] "Claude Sonnet 5 interprets prompts literally and explicitly, particularly at lower effort levels."
- [S45] "Claude Sonnet 5 provides regular, higher-quality updates to the user throughout long agentic traces."
- [S9] "This is good for latency and cost, but on moderately complex tasks running at `low` effort there is some risk of under-thinking."
- [S45] "Claude Sonnet 5 at medium is comparable in intelligence to Claude Sonnet 4.6 at high"
- [S45] "For the hardest coding and agentic tasks, raise effort to `xhigh`."
- [S46] "| Claude Sonnet 5 | `claude-sonnet-5` | The best combination of speed and intelligence |"
- [S46] "Refusals return as a successful HTTP 200 response with `stop_reason: \"refusal\"`, not an error."
- [S2] "On Claude Sonnet 5, `thinking: {type: \"disabled\"}` is accepted at any effort level."
- [S16] "| Claude Sonnet 5       | Adaptive only                    | On        | `\"enabled\"`                |"
- [S12] "'claude-fable-5', 'claude-opus-5', 'claude-sonnet-5', and 'claude-haiku-4-5-20251001'"

### Sonnet 4.6
- [S8] "Claude 4.6 models are more proactive and may overtrigger on instructions that were needed for previous models."
- [S8] "Claude Sonnet 5, Claude Sonnet 4.6, Claude Sonnet 4.5, and Claude Haiku 4.5 feature"
- [S14] "Sonnet 4.6 defaults to `high` effort. Explicitly set effort when using Sonnet 4.6 to avoid unexpected latency:"
- [S14] "**Medium effort** (recommended default): Best balance of speed, cost, and performance for most applications."
- [S16] "| Claude Sonnet 4.6     | Adaptive, extended (deprecated)1 | Off       | None                       |"
- [S48] "Model ID: `claude-sonnet-4-6`"
- [S56] "This iteration of Claude is Claude Sonnet 4.6"
- [S56] "Claude avoids saying \"genuinely\", \"honestly\", or \"straightforward\"."

### Sonnet 4.5
- [S47] "Claude Sonnet 5 defaults to an effort level of `high`, in contrast to Sonnet 4.5 which had no effort parameter."
- [S47] "Claude 4 models have a more concise, direct communication style."
- [S16] "| Claude Sonnet 4.5     | Extended only                    | Off       | `\"adaptive\"`               |"
- [S49] "Model ID: `claude-sonnet-4-5-20250929`"
- [S57] "This iteration of Claude is Claude Sonnet 4.5"
- [S57] "In casual conversation, it's fine for Claude's responses to be relatively short, e.g. just a few sentences long."
- [S57] "Claude avoids over-formatting responses with elements like bold emphasis, headers, lists, and bullet points."

### Haiku 4.5
- [S17] "| Claude API ID                                                                                             | `claude-fable-5-1`                                                                | `claude-opus-5`                                                             | `claude-sonnet-5`                                                               | `claude-haiku-4-5-20251001`                                                       |"
- [S17] "| [Default effort](https://platform.claude.com/docs/en/build-with-claude/effort)                            | `high`                                                                            | `high`                                                                      | `high`                                                                          | Not supported                                                                     |"
- [S47] "Effort is not available on Claude Haiku 4.5 and defaults to `high` on Claude Sonnet 5."
- [S50] "Model ID: `claude-haiku-4-5-20251001`"
- [S51] "For significant performance improvements on coding and reasoning tasks, consider enabling extended thinking with `thinking: {type: \"enabled\", budget_tokens: N}`."
- [S51] "Use only `temperature` OR `top_p`, not both."
- [S16] "| Claude Haiku 4.5      | Extended only                    | Off       | `\"adaptive\"`               |"
- [S28] "Uses the fast and efficient Haiku model for simple tasks"
- [S58] "This iteration of Claude is Claude Haiku 4.5"
- [S58] "In casual conversation, it's fine for Claude's responses to be relatively short, e.g. just a few sentences long."
- [S58] "Claude avoids over-formatting responses with elements like bold emphasis, headers, lists, and bullet points."

### Cross-model (applies to all rows unless overridden)
- [S8] "**Ask Claude to self-check.** Append something like \"Before you finish, verify your answer against \\[test criteria].\" This catches errors reliably, especially for coding and math."
- [S8] "Never speculate about code you have not opened."
- [S8] "Never use placeholders or guess missing parameters in tool"
- [S8] "**Tune anti-laziness prompting:** If your prompts previously encouraged the model to be more thorough or use tools more aggressively, dial back that guidance."
- [S8] "The assistant is Claude, created by Anthropic. The current model is Claude Opus 5."
- [S8] "* **Less verbose:** May skip detailed summaries for efficiency unless prompted otherwise"
- [S20] "Hook output strings, including `additionalContext`, `systemMessage`, and plain stdout, are capped at 10,000 characters."
- [S20] "Only [`SessionStart`](#sessionstart) hooks can receive a `model` field, and Claude Code doesn't always include it."
- [S20] "It can be omitted, for example after `/clear` or when a session is restored through conversation recovery, so check for the field before reading it"
- [S20] "PostModelSwitch requires Claude Code v2.1.251 or later."
- [S28] "If you set a level the active model does not support, Claude Code falls back to the highest supported level at or below the one you set."
- [S28] "The model's default effort: `high` on every model that supports effort"

## What changed versus the Phase 0 research (re-fetch of 2026-09-05)

- **S20 (hooks reference) is now read in full** (317 KB raw). New facts used by this repo: hook output strings are capped at 10,000 characters and longer output is replaced by a file path; `model` in SessionStart can be omitted after `/clear` or conversation recovery; Stop hooks accept `hookSpecificOutput.additionalContext` as non-error feedback that keeps the turn going under the same 8-block cap; PostModelSwitch requires Claude Code ≥ 2.1.251; `effort.level` reports the level Claude Code resolved to.
- **S14/S28 give the per-model effort matrix** that Chunk D needs: `xhigh` exists only on Fable 5.x, Mythos 5.x, Opus 5, Opus 4.8, Opus 4.7, Sonnet 5; Opus 4.6 and Sonnet 4.6 stop at `max` without `xhigh`; Haiku 4.5, Sonnet 4.5 have no effort at all; in Claude Code, Opus 4.5 is also not listed; Opus 4.7 defaults to `xhigh` in Claude Code.
- **S8 now lists a Sonnet 5 and an Opus 4.8 guide** in its model-specific table; the "Ask Claude to self-check" paragraph names Opus 5 as the only exception.
- **No standalone pages exist** for Sonnet 4.6, Sonnet 4.5, Haiku 4.5, Opus 4.7, Opus 4.6 or Opus 4.5 prompting or "what's new" (all 404 on 2026-09-05); their guidance lives in S8, the Opus 5 / Sonnet 5 migration guides, the model overview pages and the claude.ai system-prompt pages.
- **Nothing dated after 2026-09-03** appears in the platform release notes (S19); the Fable 5.1 / Opus 5 / Opus 4.8 guides carry the same headings as recorded in Phase 0.

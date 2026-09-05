# claude-model-harness 0.2.0

A Claude Code plugin that tells the model which model it is, loads Anthropic's official guidance for **that** model, and gates "done" claims on real evidence. 0.2.0 extends the Opus 5 harness to every current Claude model: Fable 5.1 / 5 (Mythos), Opus 5, Opus 4.8 / 4.7 / 4.6 / 4.5, Sonnet 5 / 4.6 / 4.5 and Haiku 4.5. Every behavioural claim cites an official Anthropic page (`research/SOURCES.md`, 63 sources; `research/MODEL_MATRIX.md`, one cited row per model, quote-checked against a same-day mirror).

**Install**
```
claude plugin marketplace add https://github.com/AbdulrahmanAmer/claude-model-harness.git
claude plugin install claude-model-harness@claude-model-harness -s user
```
or paste into Claude Code: *Install and configure https://github.com/AbdulrahmanAmer/claude-model-harness per its README, run its doctor on this project, show me the diff, and apply only after I approve.*

**What you get**
- `MODEL IDENTITY: You are running as <model>` injected at session start, after `/model`, and after compaction, followed by the profile for the model's tier (`fable-5`, `opus-5`, `opus-4x`, `sonnet-5`, `sonnet-4x`, `haiku`, `generic`) and a shared "useful output" block (answer first; command + observed result for any claim about code or tests; "could not verify" instead of guessing; partial reported as partial). Lower tiers carry the self-check line Anthropic recommends for every model except Opus 5; the Opus 5 profile contains no verification instruction. Unknown model → the harness says so; it never guesses.
- A Stop-hook **completion gate**: "done / fixed / tests pass" without a real test, build, lint or diff tool call is sent back with a reason; rigged evidence (`|| true`, `-k`, "0 tests", `git checkout main`) is called out; failing output plus a success claim is blocked; tool-call-shaped text that never ran is blocked. New in 0.2.0: a per-tier **grounding rule** — a claim about a file the model never opened is sent back once with "read the file, then answer" (off on Opus 5 and Fable, where the guides say not to add re-check prompts).
- **Chunk mode** (`/chunk`): plan once, run small scoped chunks with a scope lock and per-chunk acceptance; the recommended effort now comes from the running model's own table (Opus 4.6 / Sonnet 4.6 have no `xhigh`; Haiku 4.5 has no effort parameter and the skill says so).
- **Doctor** (`/harness-doctor`): the same "double-check" line is an *error* on Opus 5 and *info* on Sonnet/Haiku; `--explain R1` prints the cited per-tier reasoning; only error/warning findings are ever edited; `--apply` keeps your line endings.
- `/harness-status`: detected model with source and confidence, active profile, gate state, active chunk, last log events, next step.
- Installer self-test: one headless turn that must quote the identity line back, printed as PASS/FAIL.
- Windows: hooks run in Git Bash; hook stdio is UTF-8; the wrapper spawns one `timeout` and one Python.

**Honest limits** — hallucination and overconfidence are model-level; prose-tic prompting decays and is only mechanically checked here; model detection depends on Claude Code passing a model field or an undocumented transcript field; process creation under Git Bash on Windows is slow, so hook timeouts are generous. Details in README "What is fixable, honestly" and "Limitations".

All hooks are POSIX sh + Python 3.10 stdlib, fail open, and log to `~/.claude/harness.log`. MIT.

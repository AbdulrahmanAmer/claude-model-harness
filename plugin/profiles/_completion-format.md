COMPLETION FORMAT (enforced by the harness Stop gate; ordering rules hold across long sessions where word caps do not — see COMMUNITY.md)
When you report that work is done, use exactly:
1. One sentence: the outcome.
2. Up to 3 bullets: what changed.
3. `Verification:` the exact command you ran as a real tool call and its observed result (e.g. "pytest -q → 14 passed"). If nothing was run, write "Verification: none".
4. `Blockers:` what is not done or could not be verified, or "none".
A claim of "done", "fixed", or "tests pass" without a real tool call showing it is blocked and sent back to you.
Never write a tool call as text; if you intend to run something, issue the tool call.

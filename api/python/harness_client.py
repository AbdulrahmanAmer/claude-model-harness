"""Drop-in wrapper for the Anthropic Python SDK that sets effort/thinking correctly per model and
prepends the model-identity line + official profile to the system prompt.

    from harness_client import HarnessClient
    client = HarnessClient()                      # wraps anthropic.Anthropic()
    resp = client.create(model="claude-opus-5", effort="medium",
                         system="You are a coding agent.", messages=[...], max_tokens=4096)

Rules encoded (all from official docs; ids in research/SOURCES.md):
  * effort is `output_config={"effort": ...}`; no beta header for the top-level value      [S14]
  * levels low/medium/high/xhigh/max; default high                                          [S14]
  * Opus 5, Sonnet 5, Fable/Mythos: adaptive thinking on by default; omit `thinking`        [S15, S16]
  * Opus 5: thinking:disabled allowed only at effort <= high, else HTTP 400                  [S2, S14, S15]
    and disabling it risks tool calls emitted as text -> we refuse unless allow_thinking_off  [S1, S15, S16]
  * Fable 5/5.1, Mythos: thinking:disabled always 400; forced tool_choice 400 on 5.1         [S6, S16]
  * Opus 4.6-4.8, Sonnet 4.6: thinking off unless {"type":"adaptive"} is sent               [S9, S16]
  * Opus/Sonnet/Haiku 4.5: extended thinking only ({"type":"enabled","budget_tokens":N})    [S16, S38]
  * effort: Sonnet 4.5 and Haiku 4.5 have none; Opus 4.5 low/medium/high; Opus 4.6 and
    Sonnet 4.6 have no xhigh; xhigh only on Fable/Mythos 5.x, Opus 5, 4.8, 4.7, Sonnet 5    [S14, S47]
  * temperature/top_p/top_k non-default -> 400 on Fable/Mythos, Opus 5, Opus 4.7/4.8, Sonnet 5 [S2, S15]
  * model identity line in the system prompt                                                 [S8]
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
_PROFILES = Path(__file__).resolve().parents[2] / "plugin" / "profiles"

# (regex, thinking family, harness profile tier, display name). Tiers: research/MODEL_MATRIX.md.
#   always_on        thinking cannot be disabled                                  [S6, S16]
#   opus5            on by default; `disabled` only at effort <= high              [S2, S16]
#   on_default       on by default; `disabled` at any effort (Sonnet 5)            [S2, S16]
#   adaptive_opt_in  off unless {"type":"adaptive"} (Opus 4.6–4.8, Sonnet 4.6)     [S9, S16]
#   extended_effort  extended-only thinking but supports effort (Opus 4.5)         [S14, S16]
#   extended_only    extended-only thinking, no effort (Sonnet 4.5, Haiku 4.5)     [S16, S47]
_FAMILY_RULES = [
    (r"claude-(fable|mythos)-", "always_on", "fable-5", "Claude Fable/Mythos"),
    (r"claude-opus-5(?!-)", "opus5", "opus-5", "Claude Opus 5"),
    (r"claude-sonnet-5(?!-)", "on_default", "sonnet-5", "Claude Sonnet 5"),
    (r"claude-opus-4-[678]", "adaptive_opt_in", "opus-4x", "Claude Opus 4.6–4.8"),
    (r"claude-sonnet-4-6", "adaptive_opt_in", "sonnet-4x", "Claude Sonnet 4.6"),
    (r"claude-opus-4-5", "extended_effort", "opus-4x", "Claude Opus 4.5"),
    (r"claude-sonnet-4-5", "extended_only", "sonnet-4x", "Claude Sonnet 4.5"),
    (r"claude-haiku-4-5", "extended_only", "haiku", "Claude Haiku 4.5"),
]

# Effort levels each model accepts on the API [S14]. `xhigh` exists only on Fable/Mythos 5.x, Opus 5, Opus 4.8,
# Opus 4.7 and Sonnet 5; Opus 4.6 and Sonnet 4.6 stop at `max`; Opus 4.5 supports effort but is in neither the
# `xhigh` nor the `max` list; Sonnet 4.5 and Haiku 4.5 have no effort parameter.
def supported_efforts(model: str) -> tuple[str, ...]:
    fam, _, _ = family(model)
    if fam in ("always_on", "opus5", "on_default"):
        return EFFORT_LEVELS
    if fam == "adaptive_opt_in":
        return EFFORT_LEVELS if re.search(r"claude-opus-4-[78]", model) else ("low", "medium", "high", "max")
    if fam == "extended_effort":
        return ("low", "medium", "high")
    return ()


# Non-default temperature/top_p/top_k return 400 on these models [S15]; Opus 4.6 / Sonnet 4.6 / 4.5 still accept them.
def rejects_sampling(model: str) -> bool:
    return bool(re.search(r"claude-(fable|mythos)-|claude-opus-5(?!-)|claude-opus-4-[78]|claude-sonnet-5(?!-)", model))


def family(model: str) -> tuple[str, str, str]:
    for rx, fam, prof, name in _FAMILY_RULES:
        if re.search(rx, model):
            return fam, prof, name
    return "unknown", "generic", model


def resolve_params(model: str, effort: str | None = None, thinking: str | None = None,
                   budget_tokens: int = 4096, allow_thinking_off: bool = False) -> dict[str, Any]:
    """Return kwargs for messages.create. thinking: None|'adaptive'|'disabled'|'enabled'."""
    fam, _, _ = family(model)
    out: dict[str, Any] = {}
    if effort is not None:
        if effort not in EFFORT_LEVELS:
            raise ValueError(f"effort must be one of {EFFORT_LEVELS} [S14]")
        allowed = supported_efforts(model)
        if not allowed:
            raise ValueError(f"{model} does not support the effort parameter [S14, S47]")
        if effort not in allowed:
            raise ValueError(f"effort '{effort}' is not supported on {model}; supported: {allowed} [S14]")
        out["output_config"] = {"effort": effort}
    eff = effort or "high"
    if thinking == "disabled":
        if fam == "always_on":
            raise ValueError("thinking cannot be disabled on Fable/Mythos models (HTTP 400) [S6, S16]")
        if fam == "opus5":
            if eff in ("xhigh", "max"):
                raise ValueError("Opus 5: thinking:disabled with effort xhigh/max returns HTTP 400 [S2, S14]")
            if not allow_thinking_off:
                raise ValueError("Opus 5 with thinking disabled can emit tool calls as plain text [S1, S15]; "
                                 "prefer thinking on at lower effort. Pass allow_thinking_off=True to override.")
        out["thinking"] = {"type": "disabled"}
    elif thinking == "enabled":
        if fam not in ("extended_only", "extended_effort"):
            raise ValueError("thinking:enabled/budget_tokens is rejected on 4.7+ and Fable [S16, S38]; use 'adaptive'")
        out["thinking"] = {"type": "enabled", "budget_tokens": max(1024, budget_tokens)}
    elif thinking == "adaptive" or (thinking is None and fam == "adaptive_opt_in"):
        if fam in ("extended_only", "extended_effort"):
            raise ValueError("4.5 models do not support adaptive thinking [S16]")
        out["thinking"] = {"type": "adaptive"}
    # thinking None on opus5/on_default/always_on: omit -> adaptive on by default [S15]
    return out


def identity_block(model: str) -> str:
    fam, profile, name = family(model)
    head = (f"The assistant is Claude, created by Anthropic. The current model is {name}. "
            f"The exact model string is {model}. Do not claim to be a different model.")  # [S8]
    parts = [head]
    for fn in (f"{profile}.md", "_useful-output.md", "_completion-format.md", "_tics.md"):
        p = _PROFILES / fn
        if p.is_file():
            parts.append(p.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts)


class HarnessClient:
    def __init__(self, client: Any = None, inject_profile: bool = True):
        if client is None:
            import anthropic  # lazy: keep this module importable without the SDK
            client = anthropic.Anthropic()
        self.client = client
        self.inject_profile = inject_profile

    def create(self, *, model: str, messages: list[dict[str, Any]], max_tokens: int = 4096,
               system: str | None = None, effort: str | None = None, thinking: str | None = None,
               allow_thinking_off: bool = False, **kwargs: Any) -> Any:
        for k in ("temperature", "top_p", "top_k"):
            if k in kwargs and rejects_sampling(model):
                raise ValueError(f"{k} is rejected on this model (Fable/Mythos, Opus 5, Opus 4.7+, Sonnet 5) [S2, S15]")
        params = resolve_params(model, effort, thinking, allow_thinking_off=allow_thinking_off)
        if self.inject_profile:
            ident = identity_block(model)
            system = f"{ident}\n\n{system}" if system else ident
        return self.client.messages.create(model=model, max_tokens=max_tokens, messages=messages,
                                           system=system, **params, **kwargs)


if __name__ == "__main__":
    import json
    for m, e, t in [("claude-opus-5", "medium", None), ("claude-fable-5-1", "high", None),
                    ("claude-opus-4-8", "xhigh", "adaptive"), ("claude-sonnet-5", "low", "disabled")]:
        print(m, json.dumps(resolve_params(m, e, t)))

/**
 * Drop-in wrapper for @anthropic-ai/sdk that sets effort/thinking per model and prepends the
 * model-identity line + official profile to the system prompt. Same rules as api/python/harness_client.py
 * (source ids in research/SOURCES.md): effort via `output_config` [S14]; Opus 5 thinking:disabled only at
 * effort <= high and discouraged (tool calls as text) [S1, S2, S15]; Fable/Mythos always-on thinking [S6, S16];
 * 4.6–4.8 need {type:"adaptive"} to think [S9, S16]; 4.5 extended-only [S16, S38]; identity line [S8].
 *
 *   import Anthropic from "@anthropic-ai/sdk";
 *   import { harnessCreate } from "./harness";
 *   const client = new Anthropic();
 *   const res = await harnessCreate(client, { model: "claude-opus-5", effort: "medium", max_tokens: 4096,
 *                                             system: "You are a coding agent.", messages: [...] });
 */
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

export type Effort = "low" | "medium" | "high" | "xhigh" | "max";
export type ThinkingMode = "adaptive" | "disabled" | "enabled";
// Families: always_on (Fable/Mythos) [S6,S16]; opus5 (disabled only <= high) [S2,S16]; on_default (Sonnet 5) [S2,S16];
// adaptive_opt_in (Opus 4.6–4.8, Sonnet 4.6: off unless adaptive) [S9,S16]; extended_effort (Opus 4.5: extended thinking,
// supports effort low/medium/high) [S14,S16]; extended_only (Sonnet 4.5, Haiku 4.5: no effort) [S16,S47].
type Family = "always_on" | "opus5" | "on_default" | "adaptive_opt_in" | "extended_effort" | "extended_only" | "unknown";

const RULES: Array<[RegExp, Family, string, string]> = [
  [/claude-(fable|mythos)-/, "always_on", "fable-5", "Claude Fable/Mythos"],
  [/claude-opus-5(?!-)/, "opus5", "opus-5", "Claude Opus 5"],
  [/claude-sonnet-5(?!-)/, "on_default", "sonnet-5", "Claude Sonnet 5"],
  [/claude-opus-4-[678]/, "adaptive_opt_in", "opus-4x", "Claude Opus 4.6–4.8"],
  [/claude-sonnet-4-6/, "adaptive_opt_in", "sonnet-4x", "Claude Sonnet 4.6"],
  [/claude-opus-4-5/, "extended_effort", "opus-4x", "Claude Opus 4.5"],
  [/claude-sonnet-4-5/, "extended_only", "sonnet-4x", "Claude Sonnet 4.5"],
  [/claude-haiku-4-5/, "extended_only", "haiku", "Claude Haiku 4.5"],
];

export function family(model: string): { fam: Family; profile: string; name: string } {
  for (const [rx, fam, profile, name] of RULES) if (rx.test(model)) return { fam, profile, name };
  return { fam: "unknown", profile: "generic", name: model };
}

const ALL_EFFORTS: Effort[] = ["low", "medium", "high", "xhigh", "max"];

/** Effort levels the API accepts for a model [S14]: xhigh only on Fable/Mythos 5.x, Opus 5, Opus 4.8/4.7, Sonnet 5;
 *  Opus 4.6 and Sonnet 4.6 stop at max; Opus 4.5 low/medium/high; Sonnet 4.5 and Haiku 4.5 none. */
export function supportedEfforts(model: string): Effort[] {
  const { fam } = family(model);
  if (fam === "always_on" || fam === "opus5" || fam === "on_default") return ALL_EFFORTS;
  if (fam === "adaptive_opt_in") return /claude-opus-4-[78]/.test(model) ? ALL_EFFORTS : ["low", "medium", "high", "max"];
  if (fam === "extended_effort") return ["low", "medium", "high"];
  return [];
}

/** Non-default temperature/top_p/top_k return 400 on these models [S15]; Opus 4.6, Sonnet 4.6 and 4.5 still accept them. */
export function rejectsSampling(model: string): boolean {
  return /claude-(fable|mythos)-|claude-opus-5(?!-)|claude-opus-4-[78]|claude-sonnet-5(?!-)/.test(model);
}

export function resolveParams(model: string, effort?: Effort, thinking?: ThinkingMode,
                              opts: { budgetTokens?: number; allowThinkingOff?: boolean } = {}): Record<string, unknown> {
  const { fam } = family(model);
  const out: Record<string, unknown> = {};
  if (effort) {
    const allowed = supportedEfforts(model);
    if (allowed.length === 0) throw new Error(`${model} does not support the effort parameter [S14, S47]`);
    if (!allowed.includes(effort)) throw new Error(`effort '${effort}' is not supported on ${model}; supported: ${allowed.join(", ")} [S14]`);
    out.output_config = { effort };
  }
  const eff = effort ?? "high";
  if (thinking === "disabled") {
    if (fam === "always_on") throw new Error("thinking cannot be disabled on Fable/Mythos (HTTP 400) [S6, S16]");
    if (fam === "opus5") {
      if (eff === "xhigh" || eff === "max") throw new Error("Opus 5: thinking:disabled with xhigh/max -> HTTP 400 [S2, S14]");
      if (!opts.allowThinkingOff) throw new Error("Opus 5 with thinking disabled can emit tool calls as text [S1, S15]; pass allowThinkingOff to override");
    }
    out.thinking = { type: "disabled" };
  } else if (thinking === "enabled") {
    if (fam !== "extended_only" && fam !== "extended_effort") throw new Error("thinking:enabled/budget_tokens rejected on 4.7+ [S16, S38]; use adaptive");
    out.thinking = { type: "enabled", budget_tokens: Math.max(1024, opts.budgetTokens ?? 4096) };
  } else if (thinking === "adaptive" || (thinking === undefined && fam === "adaptive_opt_in")) {
    if (fam === "extended_only" || fam === "extended_effort") throw new Error("4.5 models do not support adaptive thinking [S16]");
    out.thinking = { type: "adaptive" };
  }
  return out;
}

function profilesDir(): string {
  try { return join(dirname(fileURLToPath(import.meta.url)), "..", "..", "plugin", "profiles"); }
  catch { return join(process.cwd(), "plugin", "profiles"); }
}

export function identityBlock(model: string): string {
  const { profile, name } = family(model);
  const parts = [`The assistant is Claude, created by Anthropic. The current model is ${name}. The exact model string is ${model}. Do not claim to be a different model.`];
  for (const f of [`${profile}.md`, "_useful-output.md", "_completion-format.md", "_tics.md"]) {
    const p = join(profilesDir(), f);
    if (existsSync(p)) parts.push(readFileSync(p, "utf8").trim());
  }
  return parts.join("\n\n");
}

export interface HarnessCreateParams {
  model: string; messages: Array<Record<string, unknown>>; max_tokens?: number; system?: string;
  effort?: Effort; thinking?: ThinkingMode; allowThinkingOff?: boolean; injectProfile?: boolean;
  [k: string]: unknown;
}

// `client` is an @anthropic-ai/sdk Anthropic instance (typed loosely to keep this file dependency-free).
export async function harnessCreate(client: { messages: { create: (p: any) => Promise<any> } }, p: HarnessCreateParams) {
  const { model, messages, max_tokens = 4096, system, effort, thinking, allowThinkingOff, injectProfile = true, ...rest } = p;
  for (const k of ["temperature", "top_p", "top_k"]) if (k in rest && rejectsSampling(model))
    throw new Error(`${k} is rejected on this model (Fable/Mythos, Opus 5, Opus 4.7+, Sonnet 5) [S2, S15]`);
  const params = resolveParams(model, effort, thinking, { allowThinkingOff });
  const sys = injectProfile ? (system ? `${identityBlock(model)}\n\n${system}` : identityBlock(model)) : system;
  return client.messages.create({ model, max_tokens, messages, system: sys, ...params, ...rest });
}

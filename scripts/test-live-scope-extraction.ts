/**
 * Offline unit + static safety checks for the staff live GPT-5.6 scope analysis
 * path. Exercises the pure normalizer/payload contract and asserts the server
 * action + panel keep their fail-closed posture. Makes no network calls.
 *
 *   npm run test:live-scope-extraction
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  LIVE_SCOPE_COPY,
  buildLiveScopeExtractionPayload,
  isExpectedLiveExtractionRun,
  isLiveReady,
  normalizeLiveReadiness,
  resolveEnabledTrade,
  sanitizeLiveExtractionRun,
} from "../src/lib/live-scope-extraction";

// --- Payload contract: exact, explicit, bounded -----------------------------
const payload = buildLiveScopeExtractionPayload();
assert.deepEqual(
  payload,
  { use_live_provider: true, force: false, dry_run: false },
  "live payload must pin the live provider on, force off, dry_run off",
);
assert.equal(
  Object.prototype.hasOwnProperty.call(payload, "selected_sheet_ids"),
  false,
  "live payload must not pass caller-supplied sheet ids",
);
assert.equal(
  Object.prototype.hasOwnProperty.call(payload, "max_pages"),
  false,
  "live payload must not pass caller-supplied page overrides",
);

// --- Readiness normalization + fail-closed gate -----------------------------
// The complete, exact live contract. isLiveReady must require ALL of these
// values simultaneously; any deviation fails closed. Mirrors the backend's
// Settings.live_extraction_readiness() locked contract (defense-in-depth).
const COMPLETE_LIVE = {
  provider: "openai",
  api: "responses",
  structured_outputs: true,
  tools: [] as unknown[],
  store: false,
  model: "gpt-5.6",
  reasoning_effort: "medium",
  live_enabled: true,
  api_key_present: true,
  ready_for_live_call: true,
} as const;

const disabled = normalizeLiveReadiness({
  live: { ...COMPLETE_LIVE, ready_for_live_call: false, live_enabled: false, api_key_present: false },
  enabled_trades: [{ trade_code: "painting", trade_name: "Painting" }],
});
assert.equal(isLiveReady(disabled), false, "disabled readiness must not be ready");

const armed = normalizeLiveReadiness({
  live: { ...COMPLETE_LIVE },
  enabled_trades: [{ trade_code: "painting", trade_name: "Painting" }],
});
assert.equal(isLiveReady(armed), true, "the complete exact contract must be ready");
assert.equal(armed.live.model, "gpt-5.6", "readiness must preserve the exact model alias");

// Table-driven: every partial (one field omitted) or wrong (one field off the
// exact contract) packet MUST fail closed. Only the complete packet is ready.
const OMIT_ONE: Array<keyof typeof COMPLETE_LIVE> = [
  "provider", "api", "structured_outputs", "tools", "store",
  "model", "reasoning_effort", "live_enabled", "api_key_present", "ready_for_live_call",
];
for (const key of OMIT_ONE) {
  const partial: Record<string, unknown> = { ...COMPLETE_LIVE };
  delete partial[key];
  assert.equal(
    isLiveReady(normalizeLiveReadiness({ live: partial, enabled_trades: [] })),
    false,
    `omitting '${key}' must fail closed`,
  );
}

const WRONG_PACKETS: Array<[string, Record<string, unknown>]> = [
  ["wrong provider", { ...COMPLETE_LIVE, provider: "anthropic" }],
  ["wrong api", { ...COMPLETE_LIVE, api: "chat" }],
  ["structured_outputs off", { ...COMPLETE_LIVE, structured_outputs: false }],
  ["non-empty tools", { ...COMPLETE_LIVE, tools: [{ type: "web_search" }] }],
  ["store on", { ...COMPLETE_LIVE, store: true }],
  ["wrong model alias", { ...COMPLETE_LIVE, model: "gpt-5.5" }],
  ["wrong reasoning effort", { ...COMPLETE_LIVE, reasoning_effort: "high" }],
  ["live_enabled off", { ...COMPLETE_LIVE, live_enabled: false }],
  ["api_key_present off", { ...COMPLETE_LIVE, api_key_present: false }],
  ["ready_for_live_call off", { ...COMPLETE_LIVE, ready_for_live_call: false }],
  ["string ready flag", { ...COMPLETE_LIVE, ready_for_live_call: "true" }],
  ["tools as string", { ...COMPLETE_LIVE, tools: "[]" }],
];
for (const [label, live] of WRONG_PACKETS) {
  assert.equal(
    isLiveReady(normalizeLiveReadiness({ live, enabled_trades: [] })),
    false,
    `${label} must fail closed`,
  );
}

const empty = normalizeLiveReadiness(undefined);
assert.equal(isLiveReady(empty), false, "missing readiness must fail closed");
assert.deepEqual(empty.enabledTrades, [], "missing readiness must yield no enabled trades");

// --- Trade allowlist: never blind pass-through ------------------------------
const enabled = armed.enabledTrades;
assert.equal(resolveEnabledTrade("painting", enabled), "painting", "enabled trade resolves");
assert.equal(resolveEnabledTrade("  painting ", enabled), "painting", "trade code is trimmed");
assert.equal(resolveEnabledTrade("electrical", enabled), null, "disabled/unknown trade is rejected");
assert.equal(resolveEnabledTrade("", enabled), null, "empty trade is rejected");
assert.equal(resolveEnabledTrade(null, enabled), null, "null trade is rejected");
assert.equal(resolveEnabledTrade("painting", []), null, "no allowlist means nothing resolves");

// --- Hostile / malformed readiness input: fail closed, own-props only -------
// Non-plain and junk inputs must yield an empty, not-ready packet.
for (const hostile of [null, undefined, 42, "str", true, [], () => {}]) {
  const packet = normalizeLiveReadiness(hostile as unknown);
  assert.equal(isLiveReady(packet), false, "hostile readiness must fail closed");
  assert.deepEqual(packet.enabledTrades, [], "hostile readiness must yield no trades");
}

// A malformed `live` (array / primitive) is coerced to an empty object.
assert.deepEqual(
  normalizeLiveReadiness({ live: [1, 2, 3], enabled_trades: "nope" }).live,
  {},
  "malformed live must coerce to {}",
);
assert.deepEqual(
  normalizeLiveReadiness({ live: null, enabled_trades: null }).enabledTrades,
  [],
  "malformed enabled_trades must coerce to []",
);

// Wrong-typed live fields are dropped (never coerced into the wrong type).
const badTypes = normalizeLiveReadiness({
  live: { ready_for_live_call: "true", live_enabled: 1, model: 123, tools: "x", store: "no" },
  enabled_trades: [],
});
assert.equal(isLiveReady(badTypes), false, "string 'true' must not read as ready");
assert.equal("live_enabled" in badTypes.live, false, "non-boolean live_enabled is dropped");
assert.equal("model" in badTypes.live, false, "non-string model is dropped");
assert.equal("tools" in badTypes.live, false, "non-array tools is dropped");

// Inherited (prototype) properties must never be read as own data.
const inheritedLive = Object.create({ ready_for_live_call: true, model: "gpt-5.6" }) as object;
assert.equal(
  isLiveReady(normalizeLiveReadiness({ live: inheritedLive, enabled_trades: [] })),
  false,
  "inherited live properties must be ignored",
);
const inheritedTrade = Object.create({ trade_code: "painting" }) as object;
assert.deepEqual(
  normalizeLiveReadiness({ live: {}, enabled_trades: [inheritedTrade] }).enabledTrades,
  [],
  "inherited trade properties must be ignored",
);

// __proto__ smuggled via JSON.parse must not pollute or be trusted as own data.
const polluted = JSON.parse('{"__proto__": {"ready_for_live_call": true}, "live": {}, "enabled_trades": []}');
assert.equal(isLiveReady(normalizeLiveReadiness(polluted)), false, "__proto__ payload must not enable readiness");
assert.equal(({} as { ready_for_live_call?: unknown }).ready_for_live_call, undefined, "Object prototype must be unpolluted");

// A trade whose class shape is exotic (not a plain object) is rejected.
class ExoticTrade {
  trade_code = "painting";
}
assert.deepEqual(
  normalizeLiveReadiness({ live: {}, enabled_trades: [new ExoticTrade()] }).enabledTrades,
  [],
  "non-plain-object trade entries are rejected",
);

// Duplicate / empty / overlong / non-string trade codes are cleaned up.
const messyTrades = normalizeLiveReadiness({
  live: { ready_for_live_call: true },
  enabled_trades: [
    { trade_code: "painting", trade_name: "Painting" },
    { trade_code: " painting ", trade_name: "Dup (trimmed, deduped)" },
    { trade_code: "painting" },
    { trade_code: "" },
    { trade_code: "   " },
    { trade_code: "x".repeat(500) },
    { trade_code: 123 },
    { trade_name: "no code" },
    { trade_code: "electrical", trade_name: "Electrical" },
  ],
}).enabledTrades;
assert.deepEqual(
  messyTrades,
  [
    { trade_code: "painting", trade_name: "Painting" },
    { trade_code: "electrical", trade_name: "Electrical" },
  ],
  "trades must be trimmed, de-duplicated, bounded, and non-empty",
);

// A trade with no usable name falls back to its code.
assert.deepEqual(
  normalizeLiveReadiness({ live: {}, enabled_trades: [{ trade_code: "drywall" }] }).enabledTrades,
  [{ trade_code: "drywall", trade_name: "drywall" }],
  "missing trade_name falls back to the trade_code",
);

// --- Run sanitization: only safe status fields survive ----------------------
const summary = sanitizeLiveExtractionRun({
  run_id: "run-123",
  trade_code: "painting",
  status: "queued",
  provider: "openai",
  model_identifier: "gpt-5.6",
  candidate_count: 3,
  // Fields that must never survive:
  error_message: "internal traceback /var/secret/path",
  error_code: "boom",
  usage: { prompt_tokens: 999 },
  estimated_cost: "12.34",
});
assert.deepEqual(
  summary,
  { runId: "run-123", tradeCode: "painting", status: "queued", provider: "openai", model: "gpt-5.6", candidateCount: 3 },
  "sanitized run must expose only safe status/id fields",
);
const serialized = JSON.stringify(summary);
for (const leaked of ["error_message", "traceback", "/var/secret", "usage", "estimated_cost", "prompt_tokens"]) {
  assert.equal(serialized.includes(leaked), false, `sanitized run must not leak ${leaked}`);
}

// Hostile / non-plain run inputs sanitize to an all-null summary (fail closed).
const allNull = { runId: null, tradeCode: null, status: null, provider: null, model: null, candidateCount: null };
for (const hostile of [null, undefined, 7, "x", [], () => {}]) {
  assert.deepEqual(sanitizeLiveExtractionRun(hostile as unknown), allNull, "hostile run must sanitize to nulls");
}
// Inherited properties on the run object must not be read as own status fields.
const inheritedRun = Object.create({ run_id: "leaked", status: "queued" }) as object;
assert.deepEqual(sanitizeLiveExtractionRun(inheritedRun), allNull, "inherited run fields must be ignored");
// Non-finite / wrong-typed candidate_count is dropped to null.
assert.equal(
  sanitizeLiveExtractionRun({ candidate_count: Number.NaN }).candidateCount,
  null,
  "non-finite candidate_count is dropped",
);
assert.equal(
  sanitizeLiveExtractionRun({ candidate_count: "3" }).candidateCount,
  null,
  "string candidate_count is dropped",
);

// --- Run-response contract: only the exact expected live-start run passes ----
// Defense-in-depth: the action must refuse to report a run as "started" unless
// the sanitized engine response matches the exact live contract for the trade
// the staff user actually requested.
const VALID_UUID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301";
const VALID_RUN_RAW: Record<string, unknown> = {
  run_id: VALID_UUID,
  trade_code: "painting",
  status: "queued",
  provider: "openai",
  model_identifier: "gpt-5.6",
  candidate_count: null,
};

assert.equal(
  isExpectedLiveExtractionRun(sanitizeLiveExtractionRun(VALID_RUN_RAW), "painting"),
  true,
  "a canonical queued openai/gpt-5.6 run for the requested trade is expected",
);
assert.equal(
  isExpectedLiveExtractionRun(sanitizeLiveExtractionRun({ ...VALID_RUN_RAW, candidate_count: 0 }), "painting"),
  true,
  "zero candidates while queued is valid",
);
// Every safe start status is accepted; nothing else is.
for (const status of ["queued", "running", "needs_review", "completed"]) {
  assert.equal(
    isExpectedLiveExtractionRun(sanitizeLiveExtractionRun({ ...VALID_RUN_RAW, status }), "painting"),
    true,
    `safe start status '${status}' is accepted`,
  );
}

// Table-driven: every off-contract / malformed / mismatched run fails closed.
const INVALID_RUNS: Array<[string, unknown, string]> = [
  ["null id", { ...VALID_RUN_RAW, run_id: null }, "painting"],
  ["missing id", { ...VALID_RUN_RAW, run_id: undefined }, "painting"],
  ["malformed id", { ...VALID_RUN_RAW, run_id: "not-a-uuid" }, "painting"],
  ["non-UUID short id", { ...VALID_RUN_RAW, run_id: "12345" }, "painting"],
  ["numeric id", { ...VALID_RUN_RAW, run_id: 12345 }, "painting"],
  ["wrong requested trade", VALID_RUN_RAW, "electrical"],
  ["run trade mismatches request", { ...VALID_RUN_RAW, trade_code: "electrical" }, "painting"],
  ["mock provider", { ...VALID_RUN_RAW, provider: "mock" }, "painting"],
  ["missing provider", { ...VALID_RUN_RAW, provider: undefined }, "painting"],
  ["wrong model alias", { ...VALID_RUN_RAW, model_identifier: "gpt-5.5" }, "painting"],
  ["failed status", { ...VALID_RUN_RAW, status: "failed" }, "painting"],
  ["cancelled status", { ...VALID_RUN_RAW, status: "cancelled" }, "painting"],
  ["unknown status", { ...VALID_RUN_RAW, status: "banana" }, "painting"],
  ["null status", { ...VALID_RUN_RAW, status: null }, "painting"],
  ["negative candidate count", { ...VALID_RUN_RAW, candidate_count: -1 }, "painting"],
  ["fractional candidate count", { ...VALID_RUN_RAW, candidate_count: 1.5 }, "painting"],
  ["over schema candidate count", { ...VALID_RUN_RAW, candidate_count: 1001 }, "painting"],
  ["unsafe candidate count", { ...VALID_RUN_RAW, candidate_count: Number.MAX_SAFE_INTEGER + 1 }, "painting"],
  ["hostile null raw", null, "painting"],
  ["hostile array raw", [1, 2, 3], "painting"],
  ["hostile string raw", "queued", "painting"],
  ["empty requested trade", VALID_RUN_RAW, ""],
];
for (const [label, raw, requestedTrade] of INVALID_RUNS) {
  assert.equal(
    isExpectedLiveExtractionRun(sanitizeLiveExtractionRun(raw), requestedTrade),
    false,
    `${label} must fail closed`,
  );
}

// __proto__ smuggled into the run response must not satisfy the contract.
const pollutedRun = JSON.parse(
  `{"__proto__": {"run_id": "${VALID_UUID}", "provider": "openai"}, "status": "queued"}`,
);
assert.equal(
  isExpectedLiveExtractionRun(sanitizeLiveExtractionRun(pollutedRun), "painting"),
  false,
  "__proto__-smuggled run fields must not satisfy the contract",
);

// --- Static posture checks on the wired action + panel ----------------------
const root = process.cwd();
const actions = readFileSync(join(root, "src/app/admin/projects/[id]/actions.ts"), "utf8");
const panel = readFileSync(join(root, "src/app/admin/projects/[id]/LiveScopeAnalysisPanel.tsx"), "utf8");
const page = readFileSync(join(root, "src/app/admin/projects/[id]/page.tsx"), "utf8");

assert.ok(actions.includes("export async function startLiveScopeExtraction"), "action must exist");
assert.ok(actions.includes("await requireStaff()"), "live action must be staff-guarded");
assert.ok(actions.includes("buildLiveScopeExtractionPayload()"), "action must post the fixed live payload");
assert.ok(actions.includes("resolveEnabledTrade(tradeCode, packet.enabledTrades)"), "action must validate trade against the server allowlist");
assert.ok(actions.includes("if (!isLiveReady(packet)) return { ok: false, message: LIVE_SCOPE_COPY.notEnabled }"), "action must fail closed when live is not armed");
assert.ok(actions.includes("sanitizeLiveExtractionRun(raw)"), "action must sanitize the returned run");
assert.ok(
  actions.includes("isExpectedLiveExtractionRun(run, trade)"),
  "action must validate the run response against the expected live contract before success",
);
assert.ok(actions.includes("data: run"), "action must return only the validated run summary as data");
assert.ok(!actions.includes("force: true"), "live action must never force a re-run");
assert.ok(!actions.includes("dry_run: true"), "live action must never post a dry_run");

assert.ok(panel.startsWith('"use client";'), "panel must be an explicit client component");
assert.ok(panel.includes("Run GPT-5.6 scope analysis"), "panel must show the clearly labeled run button");
assert.ok(panel.includes("if (busy) return;"), "panel must lock out duplicate submissions while active");
assert.ok(panel.includes("startLiveScopeExtraction"), "panel must call the staff action");
assert.ok(page.includes("<LiveScopeAnalysisPanel"), "panel must be mounted on the admin project page");

console.log("Live scope extraction contract + safety checks passed.");

/**
 * Pure, framework-free helpers for the staff-only live GPT-5.6 scope analysis
 * action. Kept side-effect free so the server action and the offline test
 * harness can share the exact same normalizer/payload contract.
 *
 * Safety posture (do not weaken):
 *  - The request payload ALWAYS pins the live provider explicitly and never
 *    passes arbitrary caller-controlled fields (no free-text model, no source
 *    text/paths, no sheet ids unless a trusted UI supplies verified ones).
 *  - A trade must be validated against the server-fetched enabled-trade
 *    allowlist before it can reach a live model — never blind pass-through.
 *  - The action fails closed ("Live analysis is not enabled") rather than
 *    silently degrading to the offline mock when live GPT is not armed.
 */

/** Fixed, safe copy shown to staff. Never interpolate provider/internal detail. */
export const LIVE_SCOPE_COPY = {
  notEnabled: "Live analysis is not enabled",
  notSynced: "Project has not been sent to the estimating engine yet.",
  notConfigured: "The estimating engine is not configured on this deployment.",
  tradeNotEnabled: "That trade is not enabled for live analysis.",
  chooseTrade: "Choose an enabled trade before running live analysis.",
  success: "Live GPT-5.6 scope analysis started. Results stay pending human review.",
  failure: "Live GPT-5.6 scope analysis could not be started. No run was created.",
  missingId: "Missing project id.",
} as const;

/** Mirrors the engine's live-readiness response (safe fields only, no key). */
export interface LiveExtractionReadiness {
  provider?: string;
  api?: string;
  structured_outputs?: boolean;
  tools?: unknown[];
  store?: boolean;
  model?: string;
  reasoning_effort?: string;
  live_enabled?: boolean;
  api_key_present?: boolean;
  ready_for_live_call?: boolean;
}

export interface EnabledTrade {
  trade_code: string;
  trade_name: string;
}

export interface LiveReadinessPacket {
  live: LiveExtractionReadiness;
  enabledTrades: EnabledTrade[];
}

/**
 * The exact, explicit body posted to the engine extraction endpoint. Locked so
 * a live run is unambiguous and bounded: live provider on, no forced re-run, not
 * a dry run, and no caller-supplied sheet selection.
 */
export interface LiveScopeExtractionPayload {
  use_live_provider: true;
  force: false;
  dry_run: false;
}

export function buildLiveScopeExtractionPayload(): LiveScopeExtractionPayload {
  return { use_live_provider: true, force: false, dry_run: false };
}

// --- Hostile-input normalization primitives ---------------------------------
// Engine responses are untrusted transport. Accept ONLY plain own-property data:
// never read inherited/prototype properties, never trust a non-plain object, and
// coerce/bound every field we keep. This blocks prototype-pollution vectors
// (`__proto__`, `constructor`) and malformed shapes from ever influencing the
// fail-closed gate downstream.

const MAX_TRADE_CODE_LEN = 64;
const MAX_TRADE_NAME_LEN = 128;
const MAX_TRADES = 200;
const MAX_STRING_FIELD_LEN = 200;

/** True only for a plain object literal (not null, array, or a class/exotic). */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/** Read an own (never inherited) property; undefined if absent or not plain. */
function ownProp(obj: Record<string, unknown>, key: string): unknown {
  return Object.prototype.hasOwnProperty.call(obj, key) ? obj[key] : undefined;
}

function ownBoolean(obj: Record<string, unknown>, key: string): boolean | undefined {
  const v = ownProp(obj, key);
  return typeof v === "boolean" ? v : undefined;
}

function ownBoundedString(obj: Record<string, unknown>, key: string, max: number): string | undefined {
  const v = ownProp(obj, key);
  return typeof v === "string" ? v.slice(0, max) : undefined;
}

/** Coerce the `live` sub-object to allowlisted, type-checked, bounded fields. */
function normalizeLive(raw: unknown): LiveExtractionReadiness {
  if (!isPlainObject(raw)) return {};
  const live: LiveExtractionReadiness = {};
  const provider = ownBoundedString(raw, "provider", MAX_STRING_FIELD_LEN);
  if (provider !== undefined) live.provider = provider;
  const api = ownBoundedString(raw, "api", MAX_STRING_FIELD_LEN);
  if (api !== undefined) live.api = api;
  const structuredOutputs = ownBoolean(raw, "structured_outputs");
  if (structuredOutputs !== undefined) live.structured_outputs = structuredOutputs;
  // `tools` is only ever surfaced as an own array; anything else is dropped.
  const tools = ownProp(raw, "tools");
  if (Array.isArray(tools)) live.tools = tools.slice(0, MAX_TRADES);
  const store = ownBoolean(raw, "store");
  if (store !== undefined) live.store = store;
  const model = ownBoundedString(raw, "model", MAX_STRING_FIELD_LEN);
  if (model !== undefined) live.model = model;
  const reasoningEffort = ownBoundedString(raw, "reasoning_effort", MAX_STRING_FIELD_LEN);
  if (reasoningEffort !== undefined) live.reasoning_effort = reasoningEffort;
  const liveEnabled = ownBoolean(raw, "live_enabled");
  if (liveEnabled !== undefined) live.live_enabled = liveEnabled;
  const apiKeyPresent = ownBoolean(raw, "api_key_present");
  if (apiKeyPresent !== undefined) live.api_key_present = apiKeyPresent;
  const readyForLiveCall = ownBoolean(raw, "ready_for_live_call");
  if (readyForLiveCall !== undefined) live.ready_for_live_call = readyForLiveCall;
  return live;
}

/** Coerce `enabled_trades` to bounded, de-duplicated, plain-object entries. */
function normalizeEnabledTrades(raw: unknown): EnabledTrade[] {
  if (!Array.isArray(raw)) return [];
  const out: EnabledTrade[] = [];
  const seen = new Set<string>();
  for (const entry of raw) {
    if (out.length >= MAX_TRADES) break;
    if (!isPlainObject(entry)) continue;
    const code = ownProp(entry, "trade_code");
    if (typeof code !== "string") continue;
    const trimmed = code.trim();
    // Reject empty and overlong codes; de-duplicate by normalized code.
    if (!trimmed || trimmed.length > MAX_TRADE_CODE_LEN || seen.has(trimmed)) continue;
    seen.add(trimmed);
    const nameRaw = ownProp(entry, "trade_name");
    const name = typeof nameRaw === "string" && nameRaw.trim() ? nameRaw.trim().slice(0, MAX_TRADE_NAME_LEN) : trimmed;
    out.push({ trade_code: trimmed, trade_name: name });
  }
  return out;
}

/** Parse the raw engine readiness response into a safe, typed packet. */
export function normalizeLiveReadiness(raw: unknown): LiveReadinessPacket {
  if (!isPlainObject(raw)) return { live: {}, enabledTrades: [] };
  return {
    live: normalizeLive(ownProp(raw, "live")),
    enabledTrades: normalizeEnabledTrades(ownProp(raw, "enabled_trades")),
  };
}

/**
 * True only when the engine reports the ENTIRE exact live GPT-5.6 contract,
 * simultaneously. This is defense-in-depth: the backend config already enforces
 * the same locked contract, but the client refuses to treat a run as armed
 * unless every safe readiness field matches its one expected value. Any omitted,
 * malformed (wrong-typed → dropped by the normalizer), extra-tools, or otherwise
 * off-contract field (wrong provider/api/model alias/effort/store flag) fails
 * closed to false.
 */
export function isLiveReady(packet: LiveReadinessPacket): boolean {
  const live = packet.live;
  return (
    live.provider === "openai" &&
    live.api === "responses" &&
    live.structured_outputs === true &&
    Array.isArray(live.tools) &&
    live.tools.length === 0 &&
    live.store === false &&
    live.model === "gpt-5.6" &&
    live.reasoning_effort === "medium" &&
    live.live_enabled === true &&
    live.api_key_present === true &&
    live.ready_for_live_call === true
  );
}

/**
 * Validate a requested trade against the server-fetched enabled-trade allowlist.
 * Returns the normalized trade code, or null when it is not an enabled trade —
 * the caller must fail closed on null and never forward it to a live model.
 */
export function resolveEnabledTrade(
  tradeCode: string | null | undefined,
  enabledTrades: EnabledTrade[],
): string | null {
  const normalized = (tradeCode ?? "").trim();
  if (!normalized) return null;
  return enabledTrades.some((t) => t.trade_code === normalized) ? normalized : null;
}

/** Mirror of the engine's `_run_public` shape (safe run status subset). */
export interface LiveExtractionRunRaw {
  run_id?: unknown;
  trade_code?: unknown;
  status?: unknown;
  provider?: unknown;
  model_identifier?: unknown;
  candidate_count?: unknown;
  dry_run?: unknown;
}

export interface LiveExtractionRunSummary {
  runId: string | null;
  tradeCode: string | null;
  status: string | null;
  provider: string | null;
  model: string | null;
  candidateCount: number | null;
}

/**
 * Reduce a raw engine run to a fixed, safe status summary. Deliberately drops
 * provider raw payloads, credentials, filesystem paths, internal error strings,
 * and any delivery/pricing fields — only run identity/status is surfaced.
 */
export function sanitizeLiveExtractionRun(raw: unknown): LiveExtractionRunSummary {
  // Fail closed on any non-plain / hostile shape: only own string/number fields
  // from a plain object survive, and only from the small safe allowlist.
  if (!isPlainObject(raw)) {
    return { runId: null, tradeCode: null, status: null, provider: null, model: null, candidateCount: null };
  }
  const ownString = (key: string): string | null => {
    const v = ownProp(raw, key);
    return typeof v === "string" ? v.slice(0, MAX_STRING_FIELD_LEN) : null;
  };
  const candidateCount = ownProp(raw, "candidate_count");
  return {
    runId: ownString("run_id"),
    tradeCode: ownString("trade_code"),
    status: ownString("status"),
    provider: ownString("provider"),
    model: ownString("model_identifier"),
    candidateCount: typeof candidateCount === "number" && Number.isFinite(candidateCount) ? candidateCount : null,
  };
}

/** Canonical hyphenated UUID (8-4-4-4-12 hex). Rejects non-UUID run ids. */
const CANONICAL_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * The ONLY run statuses the engine may report for a just-started live run. A
 * successful start is queued/running (or, for a synchronous fast path, already
 * needs_review/completed). A failed/cancelled/null/unknown status is NOT a
 * successful start and must fail closed — the action never reports success for it.
 */
const SAFE_START_STATUSES: ReadonlySet<string> = new Set([
  "queued",
  "running",
  "needs_review",
  "completed",
]);

/**
 * Validate a sanitized run summary against the EXACT expected live-start contract
 * before the action treats a run as started. Defense-in-depth on top of the
 * backend's own guarantees: the portal refuses to surface a "started" run unless
 * every identity/status field matches its one expected value. Any off-contract,
 * malformed, or mismatched field fails closed to false.
 *
 *  - ``runId`` must be a canonical UUID string.
 *  - ``tradeCode`` must equal the already-allowlisted requested trade (never a
 *    different trade than the one the staff user asked to run).
 *  - ``provider`` must be exactly ``openai`` and ``model`` exactly ``gpt-5.6``.
 *  - ``status`` must be in the safe start allowlist (never failed/cancelled/
 *    null/unknown).
 *  - ``candidateCount`` may be null or zero while queued; any present value must
 *    be a non-negative integer.
 */
export function isExpectedLiveExtractionRun(
  summary: LiveExtractionRunSummary,
  requestedTrade: string,
): boolean {
  // A missing/empty requested trade can never match a real run — fail closed.
  if (!requestedTrade) return false;
  if (summary.runId === null || !CANONICAL_UUID.test(summary.runId)) return false;
  if (summary.tradeCode !== requestedTrade) return false;
  if (summary.provider !== "openai") return false;
  if (summary.model !== "gpt-5.6") return false;
  if (summary.status === null || !SAFE_START_STATUSES.has(summary.status)) return false;
  if (summary.candidateCount !== null) {
    if (
      !Number.isSafeInteger(summary.candidateCount) ||
      summary.candidateCount < 0 ||
      summary.candidateCount > 1000
    ) return false;
  }
  return true;
}

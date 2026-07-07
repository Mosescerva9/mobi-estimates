import { readFileSync } from "node:fs";
import {
  normalizeCustomerRevisionHistory,
  normalizeCustomerRevisionHistoryItem,
  type EngineRevisionHistoryItem,
} from "../src/app/portal/projects/[id]/revisionHistory";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const actionPath = "src/app/portal/projects/[id]/actions.ts";
const formPath = "src/app/portal/projects/[id]/CustomerRevisionRequestForm.tsx";
const pagePath = "src/app/portal/projects/[id]/page.tsx";

const action = readFileSync(actionPath, "utf8");
const form = readFileSync(formPath, "utf8");
const page = readFileSync(pagePath, "utf8");

assert(action.startsWith('"use server";'), "customer revision action must be server-only");
assert(action.includes("await requireUser()"), "customer revision action must require an authenticated user");
assert(action.includes("createClient"), "customer revision action must use the normal Supabase server client/RLS path");
assert(
  action.includes("enginePostJson") && action.includes("/customer-revisions/customer-submit"),
  "customer revision action must call the dedicated customer-safe engine submit endpoint",
);
assert(
  action.includes("engineGetJson") && action.includes("/customer-revisions/customer-history"),
  "customer revision action must call the dedicated customer-safe engine history endpoint",
);
const customerUiFiles = [
  ["form", form],
  ["page", page],
] as const;
for (const [name, source] of customerUiFiles) {
  assert(!source.includes("@/lib/engine"), `${name} must not import the engine client by alias`);
  assert(!source.includes("lib/engine"), `${name} must not import the engine client by relative path`);
  assert(!source.includes("enginePostJson"), `${name} must not reference enginePostJson`);
  assert(!source.includes("engineConfigured"), `${name} must not reference engineConfigured`);
  assert(!source.includes("MOBI_ENGINE"), `${name} must not reference server engine env names`);
  assert(!source.includes("NEXT_PUBLIC_MOBI_ENGINE"), `${name} must not introduce public engine env names`);
}

const allowedNotices = ["recorded", "missing_text", "too_long", "engine_unavailable", "project_unlinked", "failed"];
for (const code of allowedNotices) {
  assert(action.includes(`"${code}"`), `server action is missing notice code ${code}`);
}
assert(action.includes("REVISION_NOTICE_CODES.has(code)"), "server action must whitelist redirect notice codes");
assert(form.includes("REVISION_NOTICE_COPY"), "form module must use fixed notice copy");
assert(form.includes("revisionNoticeCopy"), "form module must resolve notices through a helper");
assert(form.includes("Object.prototype.hasOwnProperty.call(REVISION_NOTICE_COPY, value)"), "notice resolver must reject inherited and unknown query strings with an own-property check");
assert(action.includes("MAX_CUSTOMER_REVISION_TEXT_LENGTH = 5000"), "server action must define the revision text length cap");
assert(action.includes("text.length > MAX_CUSTOMER_REVISION_TEXT_LENGTH"), "server action must enforce the revision text length cap before engine submission");
assert(form.includes("maxLength={5000}"), "customer textarea must match the server-side 5,000 character cap");
assert(form.includes("{notice.message}</p>"), "RevisionNotice must render fixed notice.message copy");
assert(!form.includes(">{code}</p>"), "RevisionNotice must not render the raw notice code");
assert(!form.includes("{String(code)}"), "RevisionNotice must not stringify/render the raw notice code");
assert(page.includes("<RevisionNotice code={revision} />"), "page must render revision notices through the safe RevisionNotice component");
assert(!page.includes(">{revision}<"), "page must not render the raw revision query value as text");
assert(!page.includes("{revision}</"), "page must not render the raw revision query value directly");

const forbiddenRenderedFragments = [
  "engineErrorMessage",
  "Engine returned",
  "raw_text",
  "raw_summary",
  "internal_notes",
  "actor_id",
  "actor_type",
  "reviewer",
  "before_snapshot",
  "after_snapshot",
  "readiness_snapshot",
  "confidence_snapshot",
  "payload",
];
for (const [name, source] of customerUiFiles) {
  for (const fragment of forbiddenRenderedFragments) {
    assert(!source.includes(fragment), `${name} must not render ${fragment}`);
  }
}

const submitSection = page.slice(page.indexOf("Request a revision"));
assert(submitSection.includes("CustomerRevisionRequestForm"), "project page must render the customer revision form");
assert(submitSection.includes("submitCustomerRevision"), "project page must wire the form to the server action");
assert(submitSection.includes("projectId={id}"), "project page must pass the current project id to the form");

const historySection = page.slice(page.indexOf("function RevisionHistoryPanel"));
assert(page.includes("<RevisionHistoryPanel history={revisionHistory} />"), "project page must render the customer revision history panel");
assert(historySection.includes("item.summary"), "history panel must render the sanitized customer summary field");
assert(historySection.includes("item.status_label"), "history panel must render sanitized status labels");
assert(historySection.includes("item.requested_action_label"), "history panel must render sanitized action labels");
assert(!historySection.includes("raw_"), "history panel must not render raw engine fields");
assert(!historySection.includes("reprice"), "history panel must not render pricing/reprice language");

const unsafeRevisionCopyPatterns = [
  /auto(?:matic|matically|mated)?[-\s]+(?:\w+\s+){0,4}(?:price|pricing|reprice|approve|approval|bill|billing|deliver|delivery|generate|updates?)/i,
  /final estimate is ready/i,
  /instant(?:ly)?\s+(?:\w+\s+){0,4}(?:price|pricing|reprice|approve|approval|bill|billing|deliver|delivery|generate|updates?)/i,
  /(?:price|pricing|reprice|approval|billing|delivery)\s+(?:is\s+)?(?:automatic|automated|instant)/i,
  /auto-(?:approve|approved|price|pricing|bill|billing|deliver|delivery|generate)/i,
];
const revisionUi = `${form}\n${submitSection}`;
for (const pattern of unsafeRevisionCopyPatterns) {
  assert(!pattern.test(revisionUi), `revision UI copy must not match unsafe pattern ${pattern}`);
}
assert(form.includes("does not approve, price, bill, or deliver"), "form copy must warn against automatic approval/pricing/billing/delivery");

// --- Engine -> portal contract mapping regression --------------------------
// The engine's customer-history endpoint emits safe label values under its own
// field names (`action`, `status`, `trade`, `sheet_refs[]`, `follow_up`,
// `latest_version_at`). The portal view model uses `*_label` names and a scalar
// `sheet_ref`. These checks prove the loader remaps the engine shape to the
// non-empty, customer-safe labels the RevisionHistoryPanel actually renders.
const engineItem: EngineRevisionHistoryItem = {
  id: "rev-1",
  action: "Include",
  status: "Received",
  trade: "painting",
  summary: "Requested added scope for painting.",
  sheet_refs: ["A-101", "A-102"],
  follow_up: "Scope update in progress",
  version_count: 2,
  latest_version_at: "2026-07-01T12:00:00Z",
  created_at: "2026-06-30T09:00:00Z",
  updated_at: "2026-07-01T12:00:00Z",
};

const mapped = normalizeCustomerRevisionHistoryItem(engineItem);
assert(mapped.id === "rev-1", "mapping must preserve the item id");
assert(mapped.requested_action_label === "Include", "engine `action` must map to non-empty requested_action_label");
assert(mapped.status_label === "Received", "engine `status` must map to non-empty status_label");
assert(mapped.trade_label === "painting", "engine `trade` must map to trade_label");
assert(mapped.sheet_ref === "A-101", "engine `sheet_refs[]` must collapse to the first non-empty scalar sheet_ref");
assert(mapped.summary === "Requested added scope for painting.", "summary must pass through unchanged");
assert(mapped.follow_up_label === "Scope update in progress", "engine `follow_up` must map to follow_up_label");
assert(mapped.version_count === 2, "version_count must pass through");
assert(mapped.latest_version_created_at === "2026-07-01T12:00:00Z", "engine `latest_version_at` must map to latest_version_created_at");
assert(mapped.created_at === "2026-06-30T09:00:00Z", "created_at must pass through");
assert(mapped.updated_at === "2026-07-01T12:00:00Z", "updated_at must pass through");

// The remap is a strict whitelist: no raw engine field names survive.
const mappedKeys = Object.keys(mapped);
for (const forbiddenKey of ["action", "status", "trade", "sheet_refs", "follow_up", "latest_version_at", "payload", "confidence", "raw_text"]) {
  assert(!mappedKeys.includes(forbiddenKey), `mapped view model must not expose raw engine key ${forbiddenKey}`);
}

// Empty / missing sheet refs collapse to null, not an empty string or array.
const noSheets = normalizeCustomerRevisionHistoryItem({ id: "rev-2", sheet_refs: ["   ", ""] });
assert(noSheets.sheet_ref === null, "blank sheet refs must collapse to null");
const noArray = normalizeCustomerRevisionHistoryItem({ id: "rev-3" });
assert(noArray.sheet_ref === null, "missing sheet_refs must yield null sheet_ref");
// Labels always fall back to safe non-empty copy so the panel never renders blank.
assert(noArray.requested_action_label.length > 0, "requested_action_label must never be blank");
assert(noArray.status_label.length > 0, "status_label must never be blank");
assert(noArray.summary.length > 0, "summary must never be blank");

// List normalizer tolerates non-array input without throwing.
assert(normalizeCustomerRevisionHistory(undefined).length === 0, "undefined items must normalize to an empty list");
assert(normalizeCustomerRevisionHistory([engineItem]).length === 1, "list normalizer must map each engine item");

console.log("customer revision portal safety checks passed");

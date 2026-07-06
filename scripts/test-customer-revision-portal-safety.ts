import { readFileSync } from "node:fs";

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

console.log("customer revision portal safety checks passed");

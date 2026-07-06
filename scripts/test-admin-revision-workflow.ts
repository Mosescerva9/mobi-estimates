import { readFileSync } from "node:fs";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const panelPath = "src/app/admin/projects/[id]/AutomationV1Panel.tsx";
const panel = readFileSync(panelPath, "utf8");

assert(panel.startsWith('"use client";'), "admin automation panel must remain an explicit client component");
assert(panel.includes("Customer revision review"), "admin panel must keep the customer revision workflow section");
assert(panel.includes("RevisionWorkflowSummary"), "admin revision workflow must render a summary row");
assert(panel.includes("summarizeRevisions"), "admin revision workflow must compute status summary counts");
assert(panel.includes("filterRevisions"), "admin revision workflow must filter revision requests before rendering");
assert(panel.includes("revisionStatusFilter"), "admin revision workflow must expose a status filter");
assert(panel.includes("revisionTradeFilter"), "admin revision workflow must expose a trade filter");
assert(panel.includes("revisionActionFilter"), "admin revision workflow must expose an action filter");
assert(panel.includes("revisionSearch"), "admin revision workflow must expose a search filter");
assert(panel.includes('value="accepted"'), "admin workflow must allow filtering accepted requests");
assert(panel.includes('value="accepted_for_rescope"'), "admin workflow must allow filtering scope-update-needed requests");
assert(panel.includes('value="rescope_resolved"'), "admin workflow must allow filtering resolved scope updates");
assert(panel.includes('value="needs_customer_clarification"'), "admin workflow must allow filtering clarification requests");
assert(panel.includes("No revision requests match the current filters."), "admin workflow must show an empty filtered-state message");
assert(panel.includes("filteredRevisions.map"), "admin workflow must render the filtered request list, not the raw list");

const summaryLabels = ["Total", "Needs decision", "Accepted", "Scope updates", "Resolved", "Clarification", "Rejected"];
for (const label of summaryLabels) {
  assert(panel.includes(`label=\"${label}\"`), `admin summary is missing ${label}`);
}

const guardedCopy = panel.slice(panel.indexOf("Customer revision review"));
assert(
  guardedCopy.includes("never sends a customer message") &&
    guardedCopy.includes("never unlocks a final estimate or customer delivery"),
  "admin revision workflow must keep explicit internal-only guardrail copy",
);
assert(
  !/auto(?:matic|matically|mated)?[-\s]+(?:\w+\s+){0,4}(?:approve|approval|bill|billing|deliver|delivery|send|publish)/i.test(guardedCopy),
  "admin revision workflow copy must not imply automatic approval/sending/billing/delivery",
);

console.log("admin revision workflow checks passed");

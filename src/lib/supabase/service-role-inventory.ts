export type ServiceRoleInventoryEntry = {
  path: string;
  owner:
    | "checkout"
    | "billing"
    | "project-provisioning"
    | "admin-ops"
    | "engine-sync"
    | "lead-capture";
  allowedOperations: readonly string[];
  requires: readonly string[];
  rationale: string;
};

/**
 * Audit P0/P1 service-role inventory.
 *
 * Supabase service-role clients bypass RLS. Every portal import of
 * createAdminClient must be listed here with a narrow rationale and required
 * guards. scripts/test-service-role-inventory.ts fails when a new import is
 * added without updating this inventory, or if service-role code appears in a
 * client component.
 */
export const SERVICE_ROLE_INVENTORY: readonly ServiceRoleInventoryEntry[] = [
  {
    path: "src/app/api/projects/[id]/estimate-job-sync/route.ts",
    owner: "engine-sync",
    allowedOperations: ["ensure estimate_jobs row for an authenticated user's project"],
    requires: ["authenticated user", "project ownership/company check before service-role write"],
    rationale:
      "Route uses service-role only after verifying the caller can access the project; RLS-bypassing write creates/syncs internal engine job metadata.",
  },
  {
    path: "src/app/api/projects/route.ts",
    owner: "project-provisioning",
    allowedOperations: ["rollback failed project creation", "insert initial project details/files"],
    requires: ["authenticated user", "primary company membership", "claim_project RPC ownership result"],
    rationale:
      "Project creation needs atomic provisioning helpers and rollback for partially created rows; caller identity and company linkage must be established first.",
  },
  {
    path: "src/app/api/stripe/webhook/route.ts",
    owner: "billing",
    allowedOperations: ["idempotent Stripe event writes", "subscription entitlement activation", "checkout claim email side effect after verified webhook"],
    requires: ["verified Stripe signature", "event idempotency check", "server-only environment"],
    rationale:
      "Stripe webhooks are trusted server-to-server events and must update billing/entitlement state without an end-user RLS session.",
  },
  {
    path: "src/app/checkout/complete/actions.ts",
    owner: "checkout",
    allowedOperations: ["claim lookup by token", "link checkout claim to authenticated user"],
    requires: ["valid claim token", "authenticated user for account linking", "server action only"],
    rationale:
      "Checkout completion bridges anonymous payment claims to authenticated accounts; token and session checks constrain service-role usage.",
  },
  {
    path: "src/app/checkout/complete/page.tsx",
    owner: "checkout",
    allowedOperations: ["server-render claim lookup by token"],
    requires: ["claim token from success redirect", "server component only", "no client import"],
    rationale:
      "The success page renders claim state for account setup and must not expose service-role credentials to the browser.",
  },
  {
    path: "src/app/start/route.ts",
    owner: "checkout",
    allowedOperations: ["create pending checkout claim for unauthenticated plan start"],
    requires: ["plan lookup", "server route only", "claim token hashing"],
    rationale:
      "Unauthenticated checkout starts need a server-side pending claim before Stripe redirect; only hashed claim metadata is persisted.",
  },
  {
    path: "src/app/admin/projects/[id]/actions.ts",
    owner: "admin-ops",
    allowedOperations: ["staff-only project/file read", "estimate job sync", "engine processing status updates"],
    requires: ["requireStaff gate", "project id validation", "server action only"],
    rationale:
      "Admin operations intentionally bypass customer RLS for reviewed internal workflows; staff authorization must happen before service-role access.",
  },
  {
    path: "src/app/admin/projects/[id]/takeoff-actions.ts",
    owner: "engine-sync",
    allowedOperations: ["staff-only project identity lookup for takeoff worker context"],
    requires: ["requireStaff gate", "engine_project_id gate", "server action only", "browser cannot supply tenant/API-key headers"],
    rationale:
      "Live takeoff worker actions need a service-role project lookup to derive company/tenant identity server-side before calling the authenticated worker; staff authorization and worker-context guards constrain the RLS bypass.",
  },
  {
    path: "src/app/admin/projects/[id]/takeoff-sheet-image/route.ts",
    owner: "engine-sync",
    allowedOperations: [
      "staff-only project identity lookup to derive engine/tenant context for a single sheet-image proxy",
    ],
    requires: [
      "requireStaff gate before any lookup",
      "opaque sheetId format validation",
      "company/engine_project_id derived server-side from the project row, never from the client",
      "route streams image bytes only — no key, path, or tenant identifier returned",
    ],
    rationale:
      "The browser cannot hold the engine API key, so this staff-only route resolves the project's tenant/engine identity via a narrow service-role read and streams back only the rendered sheet image bytes; identity is derived server-side and never trusted from the request.",
  },
  {
    path: "src/lib/lead-capture-server.ts",
    owner: "lead-capture",
    allowedOperations: ["idempotent insert of a validated, normalized public lead-capture record"],
    requires: [
      "pure parse/normalize/allowlist + honeypot check before any write",
      "server-only module called only by the bounded server action or origin-restricted API route",
      "only the normalized record is persisted, never raw form input",
    ],
    rationale:
      "lead_captures is RLS default-deny with no public write policy, so public forms cannot write directly; this shared server-only helper is the sole service-role insert boundary after validation.",
  },
] as const;

export type ServiceRoleInventoryEntry = {
  path: string;
  owner: "checkout" | "billing" | "project-provisioning" | "admin-ops" | "engine-sync";
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
] as const;

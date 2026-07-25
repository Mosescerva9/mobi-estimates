import dns from "node:dns/promises";
import {
  intakeEmailDomain,
  intakeMailbox,
  sharedIntakeAddress,
} from "../src/lib/intake-email";

/**
 * Live readiness probe for forwarded-bid intake.
 *
 * Everything the intake needs lives outside the repository — DNS, a Resend
 * receiving domain, a webhook, env vars on the host, and two migrations applied
 * to the Supabase project — so "the code is merged" says nothing about whether a
 * contractor's forwarded ITB will actually arrive. This reports the state of
 * each of those, and for anything missing, the exact action that fixes it.
 *
 * Read-only: it selects zero rows, writes nothing, and sends no email. Safe to
 * run against production at any time. Deliberately NOT part of test:mvp-flow —
 * it fails when the environment isn't provisioned yet, which is not a code
 * defect.
 */

type Status = "pass" | "fail" | "warn" | "skip";

interface Check {
  name: string;
  status: Status;
  detail: string;
  /** What the operator must do. Omitted when the check passed. */
  fix?: string;
}

const checks: Check[] = [];

function record(check: Check): Check {
  checks.push(check);
  return check;
}

function env(name: string): string | undefined {
  const value = process.env[name]?.trim();
  return value ? value : undefined;
}

// ---- 1. configuration -------------------------------------------------------

function checkEnv(): { supabaseUrl?: string; serviceKey?: string; resendKey?: string } {
  const supabaseUrl = env("NEXT_PUBLIC_SUPABASE_URL");
  const anonKey = env("NEXT_PUBLIC_SUPABASE_ANON_KEY");
  const serviceKey = env("SUPABASE_SERVICE_ROLE_KEY");
  const resendKey = env("RESEND_API_KEY");
  const webhookSecret = env("RESEND_INBOUND_WEBHOOK_SECRET");

  record({
    name: "Supabase project configured",
    status: supabaseUrl && anonKey ? "pass" : "fail",
    detail: supabaseUrl ? `URL ${supabaseUrl}` : "NEXT_PUBLIC_SUPABASE_URL is not set",
    fix:
      supabaseUrl && anonKey
        ? undefined
        : "Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY (Supabase → Project Settings → API).",
  });

  record({
    name: "Service-role key present",
    status: serviceKey ? "pass" : "fail",
    detail: serviceKey ? "set (server-only)" : "SUPABASE_SERVICE_ROLE_KEY is not set",
    fix: serviceKey
      ? undefined
      : "Set SUPABASE_SERVICE_ROLE_KEY. Without it /api/email/inbound fails closed with 503 and no forward is captured.",
  });

  record({
    name: "Intake address",
    status: "pass",
    detail: `${sharedIntakeAddress()} (shared) and ${intakeMailbox()}+{intake_slug}@${intakeEmailDomain()} (per company)`,
  });

  record({
    name: "Resend API key present",
    status: resendKey ? "pass" : "fail",
    detail: resendKey ? "set" : "RESEND_API_KEY is not set",
    fix: resendKey
      ? undefined
      : "Set RESEND_API_KEY. The webhook payload carries metadata only; the key is what fetches the body and attachments.",
  });

  record({
    name: "Inbound webhook signing secret present",
    status: webhookSecret ? "pass" : "fail",
    detail: webhookSecret ? "set" : "RESEND_INBOUND_WEBHOOK_SECRET is not set",
    fix: webhookSecret
      ? undefined
      : "Set RESEND_INBOUND_WEBHOOK_SECRET to the signing secret (whsec_…) of the Resend webhook.",
  });

  return { supabaseUrl, serviceKey, resendKey };
}

// ---- 2. schema --------------------------------------------------------------

interface Rest {
  /** Returns the HTTP status and body of a zero-row PostgREST probe. */
  probe(path: string): Promise<{ status: number; body: string }>;
}

function restClient(url: string, serviceKey: string): Rest {
  return {
    async probe(path: string) {
      const res = await fetch(`${url}/rest/v1/${path}`, {
        headers: { apikey: serviceKey, Authorization: `Bearer ${serviceKey}` },
        cache: "no-store",
      });
      return { status: res.status, body: await res.text() };
    },
  };
}

const MIGRATION_FIX =
  "Apply the intake migrations: `npm run db:apply-migrations -- 0036 0037` (or paste supabase/migrations/0036_inbound_bid_intake.sql and 0037_inbound_intake_routing.sql into the Supabase SQL editor, in order).";

async function checkSchema(rest: Rest): Promise<void> {
  const slug = await rest.probe("companies?select=intake_slug&limit=0");
  record({
    name: "companies.intake_slug exists (migration 0036)",
    status: slug.status === 200 ? "pass" : "fail",
    detail: slug.status === 200 ? "present" : slug.body.slice(0, 160),
    fix: slug.status === 200 ? undefined : MIGRATION_FIX,
  });

  for (const table of ["inbound_intake_messages", "inbound_intake_attachments"]) {
    const res = await rest.probe(`${table}?select=id&limit=0`);
    record({
      name: `${table} exists (migration 0036)`,
      status: res.status === 200 ? "pass" : "fail",
      detail: res.status === 200 ? "present" : res.body.slice(0, 160),
      fix: res.status === 200 ? undefined : MIGRATION_FIX,
    });
  }

  const routing = await rest.probe("inbound_intake_messages?select=routed_by,unrouted_reason&limit=0");
  record({
    name: "shared-mailbox routing columns exist (migration 0037)",
    status: routing.status === 200 ? "pass" : "fail",
    detail: routing.status === 200 ? "present" : routing.body.slice(0, 160),
    fix: routing.status === 200 ? undefined : MIGRATION_FIX,
  });

  // A company without a slug has no per-company address to print, so the portal
  // silently falls back to the shared mailbox for that tenant.
  if (slug.status === 200) {
    const missing = await rest.probe("companies?select=id&intake_slug=is.null&limit=1");
    const hasMissing = missing.status === 200 && missing.body.trim() !== "[]";
    record({
      name: "every company has an intake slug",
      status: missing.status === 200 ? (hasMissing ? "fail" : "pass") : "fail",
      detail:
        missing.status !== 200
          ? missing.body.slice(0, 160)
          : hasMissing
            ? "at least one company has a null intake_slug"
            : "backfilled",
      fix: hasMissing
        ? "Re-run migration 0036 — its backfill block fills every null intake_slug and is safe to re-run."
        : undefined,
    });
  }
}

async function checkRpcs(url: string, serviceKey: string): Promise<void> {
  const res = await fetch(`${url}/rest/v1/`, {
    headers: { apikey: serviceKey, Authorization: `Bearer ${serviceKey}` },
    cache: "no-store",
  });
  const spec = (await res.json()) as { paths?: Record<string, unknown> };
  const paths = Object.keys(spec.paths ?? {});
  for (const rpc of ["dismiss_inbound_intake", "claim_inbound_intake_for_project"]) {
    const present = paths.includes(`/rpc/${rpc}`);
    record({
      name: `RPC ${rpc} exposed`,
      status: present ? "pass" : "fail",
      detail: present ? "present" : "missing from the PostgREST schema",
      fix: present ? undefined : MIGRATION_FIX,
    });
  }
}

async function checkStorage(url: string, serviceKey: string): Promise<void> {
  const res = await fetch(`${url}/storage/v1/bucket/project-files`, {
    headers: { apikey: serviceKey, Authorization: `Bearer ${serviceKey}` },
    cache: "no-store",
  });
  const body = await res.text();
  const isPublic = res.ok && /"public"\s*:\s*true/.test(body);
  record({
    name: "private project-files bucket exists",
    status: res.ok ? (isPublic ? "fail" : "pass") : "fail",
    detail: res.ok
      ? isPublic
        ? "bucket is PUBLIC — forwarded bid documents would be world-readable"
        : "present and private"
      : `${res.status} ${body.slice(0, 120)}`,
    fix: res.ok
      ? isPublic
        ? "Make the project-files bucket private in Supabase → Storage. Captured forwards are written into it."
        : undefined
      : "Create the private 'project-files' bucket (Supabase → Storage). Captured attachments are written there.",
  });
}

// ---- 3. mail delivery -------------------------------------------------------

/** Resend's receiving MX hosts all sit under resend.com. */
function isResendMx(exchange: string): boolean {
  return /(^|\.)resend\.com\.?$/i.test(exchange.trim());
}

async function checkMx(domain: string): Promise<void> {
  let records: { exchange: string; priority: number }[];
  try {
    records = await dns.resolveMx(domain);
  } catch (e) {
    const code = (e as NodeJS.ErrnoException).code ?? "lookup failed";
    record({
      name: `MX for ${domain}`,
      status: "fail",
      detail: `no MX records (${code})`,
      fix: `Enable receiving for ${domain} in Resend → Domains, then add the MX record it shows to your DNS provider. Nothing forwarded to this domain is delivered until it exists.`,
    });
    return;
  }

  const resend = records.filter((r) => isResendMx(r.exchange));
  const others = records.filter((r) => !isResendMx(r.exchange));
  const describe = records
    .map((r) => `${r.exchange} (priority ${r.priority})`)
    .join(", ");

  if (resend.length === 0) {
    record({
      name: `MX for ${domain}`,
      status: "fail",
      detail: describe || "none",
      fix: `No Resend MX record on ${domain}. Add the MX record from Resend → Domains → Receiving. If this domain hosts real mailboxes, do NOT repoint it — set NEXT_PUBLIC_INTAKE_EMAIL_DOMAIN to a receiving subdomain such as bids.${domain} and add the MX record there instead.`,
    });
    return;
  }

  // Mail goes to the lowest priority value only, so a co-resident record at an
  // equal or lower number means forwards land somewhere else — or unpredictably.
  const bestResend = Math.min(...resend.map((r) => r.priority));
  const competing = others.filter((r) => r.priority <= bestResend);
  record({
    name: `MX for ${domain}`,
    status: competing.length === 0 ? "pass" : "fail",
    detail: describe,
    fix:
      competing.length === 0
        ? undefined
        : `Another mail host (${competing.map((r) => r.exchange).join(", ")}) has an equal or lower MX priority, so forwards will not reliably reach Resend. Give Resend's record the lowest priority value on a dedicated receiving subdomain rather than mixing hosts on one domain.`,
  });
}

interface ResendDomain {
  name?: string;
  status?: string;
  id?: string;
}

async function checkResendDomain(resendKey: string, domain: string): Promise<void> {
  const res = await fetch("https://api.resend.com/domains", {
    headers: { Authorization: `Bearer ${resendKey}` },
    cache: "no-store",
  });
  if (!res.ok) {
    record({
      name: "Resend domain",
      status: "fail",
      detail: `GET /domains failed (${res.status})`,
      fix: "Check RESEND_API_KEY — it must be a valid key with access to the account that owns the receiving domain.",
    });
    return;
  }
  const payload = (await res.json()) as { data?: ResendDomain[] };
  const list = payload.data ?? [];
  const match = list.find((d) => d.name?.toLowerCase() === domain.toLowerCase());
  record({
    name: `Resend domain ${domain}`,
    status: match ? (match.status === "verified" ? "pass" : "fail") : "fail",
    detail: match
      ? `status: ${match.status ?? "unknown"}`
      : `not in the account (found: ${list.map((d) => d.name).join(", ") || "none"})`,
    fix: match
      ? match.status === "verified"
        ? undefined
        : `Finish verifying ${domain} in Resend → Domains (its DNS records are not all confirmed yet).`
      : `Add ${domain} in Resend → Domains and enable receiving on it.`,
  });
}

// ---- 4. deployment ----------------------------------------------------------

/**
 * Confirm the webhook route is deployed. Posting an unsigned body is the safest
 * possible probe: signature verification rejects it before anything is read, so
 * this cannot create an intake row.
 */
async function checkWebhookRoute(portalUrl: string): Promise<void> {
  const endpoint = `${portalUrl.replace(/\/+$/, "")}/api/email/inbound`;
  let status: number;
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
      cache: "no-store",
    });
    status = res.status;
  } catch (e) {
    record({
      name: "inbound webhook endpoint",
      status: "fail",
      detail: `${endpoint} unreachable (${e instanceof Error ? e.message : String(e)})`,
      fix: "Confirm the portal is deployed and reachable over HTTPS.",
    });
    return;
  }

  // 400 = deployed and configured (rejected our unsigned body).
  // 503 = deployed but missing a secret. 404 = the route isn't live yet.
  const meaning: Record<number, { status: Status; detail: string; fix?: string }> = {
    400: { status: "pass", detail: "deployed; rejected an unsigned request as expected" },
    503: {
      status: "fail",
      detail: "deployed but not configured",
      fix: "The deployment is missing RESEND_INBOUND_WEBHOOK_SECRET, RESEND_API_KEY, or SUPABASE_SERVICE_ROLE_KEY. Add them to the host's environment and redeploy.",
    },
    404: {
      status: "fail",
      detail: "route not found",
      fix: "The branch adding /api/email/inbound is not deployed to this host yet. Merge and deploy it.",
    },
  };
  const known = meaning[status];
  record({
    name: "inbound webhook endpoint",
    status: known?.status ?? "fail",
    detail: `${endpoint} → ${status}${known ? ` (${known.detail})` : ""}`,
    fix: known
      ? known.fix
      : `Unexpected status ${status}. The endpoint should answer 400 to an unsigned POST.`,
  });
}

// ---- report -----------------------------------------------------------------

const ICON: Record<Status, string> = { pass: "PASS", fail: "FAIL", warn: "WARN", skip: "SKIP" };

async function main(): Promise<void> {
  const { supabaseUrl, serviceKey, resendKey } = checkEnv();
  const domain = intakeEmailDomain();

  if (supabaseUrl && serviceKey) {
    const rest = restClient(supabaseUrl, serviceKey);
    await checkSchema(rest);
    await checkRpcs(supabaseUrl, serviceKey);
    await checkStorage(supabaseUrl, serviceKey);
  } else {
    record({
      name: "database schema",
      status: "skip",
      detail: "needs NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY",
    });
  }

  await checkMx(domain);

  if (resendKey) {
    await checkResendDomain(resendKey, domain);
  } else {
    record({ name: "Resend domain", status: "skip", detail: "needs RESEND_API_KEY" });
  }

  await checkWebhookRoute(
    env("NEXT_PUBLIC_PORTAL_URL") ?? "https://portal.mobiestimates.com",
  );

  console.log("");
  console.log(`Forwarded-bid intake readiness — ${sharedIntakeAddress()}`);
  console.log("");
  for (const check of checks) {
    console.log(`  ${ICON[check.status]}  ${check.name}`);
    console.log(`        ${check.detail}`);
    if (check.fix) console.log(`        → ${check.fix}`);
  }

  const failures = checks.filter((c) => c.status === "fail");
  const skipped = checks.filter((c) => c.status === "skip");
  console.log("");
  console.log(
    `${checks.length - failures.length - skipped.length}/${checks.length} ready` +
      (skipped.length ? `, ${skipped.length} not checked` : "") +
      (failures.length ? `, ${failures.length} blocking` : ""),
  );

  if (failures.length > 0) {
    console.log("");
    console.log("Forwarded bids will NOT be captured until the blocking items above are fixed.");
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

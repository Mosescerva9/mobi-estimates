import assert from "assert";
import crypto from "crypto";
import { readFileSync } from "fs";
import { join } from "path";
import {
  attachmentSkipReason,
  bidDueDateFromText,
  buildBodyPreview,
  isConvertibleIntakeStatus,
  intakeStatusBadgeClass,
  intakeStatusLabel,
  MAX_BODY_PREVIEW_CHARS,
  MAX_INBOUND_ATTACHMENTS,
  scopeNotesPrefill,
  projectNameFromSubject,
  unroutedReasonCopy,
} from "../src/lib/inbound-intake";
import {
  displayNameFromAddress,
  findIntakeRecipient,
  findIntakeSlug,
  inboundIntakeStorageFolder,
  intakeAddressForSlug,
  intakeSlugFromAddress,
  isIntakeDomainAddress,
  isSharedIntakeAddress,
  isValidIntakeSlug,
  normalizeEmailAddress,
  sharedIntakeAddress,
} from "../src/lib/intake-email";
import {
  parseEmailReceivedEvent,
  readSvixHeaders,
  verifySvixSignature,
} from "../src/lib/resend-inbound";

/**
 * Offline guard for forwarded bid-invitation intake.
 *
 * Covers the three things that would quietly hurt a contractor if they broke:
 * addresses resolving to the wrong tenant, a webhook accepting unsigned or
 * replayed payloads, and a captured forward being able to create a project (and
 * therefore spend the one free estimate) without an authenticated confirmation.
 */

const ROOT = join(__dirname, "..");

let failures = 0;
function test(name: string, fn: () => void): void {
  try {
    fn();
    console.log(`  ok  ${name}`);
  } catch (err) {
    failures += 1;
    console.error(`  FAIL  ${name}`);
    console.error(`        ${err instanceof Error ? err.message : String(err)}`);
  }
}

const DOMAIN = "mobiestimates.com";
const MAILBOX = "estimates";
const SLUG = "acme-mechanical-a1b2c3";

// ---- address routing -------------------------------------------------------

test("the shared intake address is the configured mailbox on the receiving domain", () => {
  assert.strictEqual(sharedIntakeAddress(), `${MAILBOX}@${DOMAIN}`);
});

test("the per-company address tags the shared mailbox with a validated slug", () => {
  assert.strictEqual(intakeAddressForSlug(SLUG), `${MAILBOX}+${SLUG}@${DOMAIN}`);
  assert.strictEqual(intakeAddressForSlug(null), null, "missing slug must not render an address");
  assert.strictEqual(intakeAddressForSlug(""), null);
  assert.strictEqual(intakeAddressForSlug("no"), null, "too-short slug must be rejected");
  assert.strictEqual(intakeAddressForSlug("Bad Slug"), null, "spaces must be rejected");
  assert.strictEqual(intakeAddressForSlug("-leading"), null, "leading hyphen must be rejected");
  assert.strictEqual(isValidIntakeSlug("a".repeat(65)), false, "over-long slug must be rejected");
});

test("a slug must carry its random hex suffix to be recognized", () => {
  // This is what stops an ordinary address on the domain from being mistaken for
  // a company tag now that intake shares the root domain.
  assert.strictEqual(isValidIntakeSlug("estimates"), false);
  assert.strictEqual(isValidIntakeSlug("support"), false);
  assert.strictEqual(isValidIntakeSlug("acme-mechanical"), false, "no hex suffix");
  assert.strictEqual(isValidIntakeSlug(SLUG), true);
  assert.strictEqual(isValidIntakeSlug("company-b894c3"), true, "generic-stem fallback");
  assert.strictEqual(
    isValidIntakeSlug(`co-${"a1b2c3d4".repeat(4)}`),
    true,
    "degenerate-collision fallback form",
  );
});

test("the plain shared mailbox is not mistaken for a company tag", () => {
  assert.strictEqual(intakeSlugFromAddress(`${MAILBOX}@${DOMAIN}`, DOMAIN), null);
  assert.ok(isSharedIntakeAddress(`${MAILBOX}@${DOMAIN}`, DOMAIN, MAILBOX));
  assert.ok(!isSharedIntakeAddress(`${MAILBOX}+${SLUG}@${DOMAIN}`, DOMAIN, MAILBOX));
  assert.ok(!isSharedIntakeAddress(`support@${DOMAIN}`, DOMAIN, MAILBOX));
});

test("other mail arriving on the root domain resolves to no company", () => {
  // Receiving on the root domain means a catch-all: everything lands here.
  for (const local of ["support", "info", "moses", "noreply", "billing", "hello"]) {
    assert.strictEqual(
      intakeSlugFromAddress(`${local}@${DOMAIN}`, DOMAIN),
      null,
      `${local}@ must not resolve to a tenant`,
    );
  }
});

test("recipient parsing only accepts our receiving domain", () => {
  assert.strictEqual(intakeSlugFromAddress(`${MAILBOX}+${SLUG}@${DOMAIN}`, DOMAIN), SLUG);
  assert.strictEqual(
    intakeSlugFromAddress(`${MAILBOX}+${SLUG}@evil.example.com`, DOMAIN),
    null,
    "a lookalike domain must never resolve to a tenant",
  );
  assert.strictEqual(
    intakeSlugFromAddress(`${MAILBOX}+${SLUG}@mobiestimates.com.evil.com`, DOMAIN),
    null,
    "a suffix-attack domain must never resolve to a tenant",
  );
  assert.strictEqual(intakeSlugFromAddress("not-an-address", DOMAIN), null);
  assert.strictEqual(intakeSlugFromAddress(`${MAILBOX}@`, DOMAIN), null);
  assert.strictEqual(intakeSlugFromAddress(null, DOMAIN), null);
});

test("the bare slug form still routes, for anyone who saved the short address", () => {
  assert.strictEqual(intakeSlugFromAddress(`${SLUG}@${DOMAIN}`, DOMAIN), SLUG);
});

test("recipient parsing tolerates display names and case", () => {
  assert.strictEqual(
    intakeSlugFromAddress(
      `"Mobi Estimates" <${MAILBOX.toUpperCase()}+ACME-MECHANICAL-A1B2C3@${DOMAIN.toUpperCase()}>`,
      DOMAIN,
    ),
    SLUG,
  );
});

test("a company tag is accepted under any base local part", () => {
  // The slug is the unguessable part, so being lenient about the base only
  // improves routing and cannot deliver documents to the wrong tenant.
  assert.strictEqual(intakeSlugFromAddress(`bids+${SLUG}@${DOMAIN}`, DOMAIN), SLUG);
});

test("the intake slug is found among unrelated recipients", () => {
  const slug = findIntakeSlug(
    [
      "estimating@generalcontractor.com",
      null,
      `${MAILBOX}+${SLUG}@${DOMAIN}`,
      "pm@acme.com",
    ],
    DOMAIN,
  );
  assert.strictEqual(slug, SLUG);
  assert.strictEqual(
    findIntakeSlug(["estimating@gc.com", "pm@acme.com"], DOMAIN),
    null,
    "a message with no address of ours must not resolve to a company",
  );
});

test("a recipient on our domain is detected even with no company tag", () => {
  assert.ok(isIntakeDomainAddress(`${MAILBOX}@${DOMAIN}`, DOMAIN));
  assert.ok(!isIntakeDomainAddress("pm@acme.com", DOMAIN));
  assert.strictEqual(
    findIntakeRecipient(["pm@acme.com", `${MAILBOX}@${DOMAIN}`], DOMAIN),
    `${MAILBOX}@${DOMAIN}`,
    "sender-routed forwards still need a recipient of ours recorded",
  );
  assert.strictEqual(findIntakeRecipient(["pm@acme.com"], DOMAIN), null);
});

test("sender addresses normalize for member comparison", () => {
  assert.strictEqual(normalizeEmailAddress("  Pat Estimator <Pat@Acme.COM> "), "pat@acme.com");
  assert.strictEqual(normalizeEmailAddress("pat@acme.com"), "pat@acme.com");
  assert.strictEqual(normalizeEmailAddress(null), "");
  // +tags are NOT stripped: a tagged address is a different mailbox and must not
  // be treated as a verified member.
  assert.strictEqual(normalizeEmailAddress("pat+bids@acme.com"), "pat+bids@acme.com");
  assert.strictEqual(displayNameFromAddress("Pat Estimator <pat@acme.com>"), "Pat Estimator");
  assert.strictEqual(displayNameFromAddress("pat@acme.com"), null);
});

test("stored documents stay inside the company storage folder", () => {
  const folder = inboundIntakeStorageFolder("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222");
  assert.ok(
    folder.startsWith("11111111-1111-1111-1111-111111111111/"),
    "company_id must be the first path segment so the bucket RLS policy applies",
  );
});

// ---- subject / body parsing ------------------------------------------------

test("forwarded subject prefixes are stripped to a usable project name", () => {
  assert.strictEqual(projectNameFromSubject("FW: Riverside Medical Office"), "Riverside Medical Office");
  assert.strictEqual(projectNameFromSubject("Fwd: RE: Riverside Medical Office"), "Riverside Medical Office");
  assert.strictEqual(
    projectNameFromSubject("[EXTERNAL] Invitation to Bid: Riverside Medical Office"),
    "Riverside Medical Office",
  );
  assert.strictEqual(projectNameFromSubject("ITB - Riverside Medical Office"), "Riverside Medical Office");
  assert.strictEqual(
    projectNameFromSubject(null),
    "Forwarded bid invitation",
    "a missing subject must still yield a usable name",
  );
  assert.strictEqual(projectNameFromSubject("FW:"), "Forwarded bid invitation");
});

test("bid due dates are only taken from lines that mention a deadline", () => {
  const now = new Date("2026-03-01T00:00:00Z");
  assert.strictEqual(
    bidDueDateFromText("Project kickoff 01/15/2026\nBids due 4/15/2026 at 2pm", now),
    "2026-04-15",
  );
  assert.strictEqual(
    bidDueDateFromText("Bid deadline: April 15, 2026", now),
    "2026-04-15",
  );
  assert.strictEqual(
    bidDueDateFromText("Sent from my iPhone on 01/02/2026", now),
    null,
    "a date with no deadline cue must be ignored",
  );
  assert.strictEqual(
    bidDueDateFromText("Bids due 4/15/1998", now),
    null,
    "an implausible deadline must be ignored rather than prefilled",
  );
  assert.strictEqual(
    bidDueDateFromText("Bids due 2/30/2026", now),
    null,
    "an impossible calendar date must be ignored",
  );
  assert.strictEqual(bidDueDateFromText(null, now), null);
});

test("body previews are bounded", () => {
  const long = "x".repeat(MAX_BODY_PREVIEW_CHARS + 500);
  const preview = buildBodyPreview(long)!;
  assert.ok(preview.length <= MAX_BODY_PREVIEW_CHARS + 20, "preview must be truncated");
  assert.ok(preview.endsWith("(truncated)"), "truncation must be visible");
  assert.strictEqual(buildBodyPreview("   "), null);
});

test("scope note prefill records provenance without inventing scope", () => {
  const notes = scopeNotesPrefill({
    fromEmail: "pat@acme.com",
    subject: "Riverside Medical Office",
    receivedAt: "2026-03-01T12:00:00Z",
  });
  assert.ok(notes.includes("pat@acme.com"), "prefill must record who forwarded it");
  assert.ok(notes.includes("Riverside Medical Office"));
  assert.ok(
    !/turnaround|guarantee|approved scope/i.test(notes),
    "prefill must not assert scope or promise turnaround",
  );
});

// ---- attachment filtering --------------------------------------------------

test("only real bid documents are stored", () => {
  assert.strictEqual(
    attachmentSkipReason({ filename: "A1-Floor-Plan.pdf", size: 2_000_000 }, 0),
    null,
  );
  assert.strictEqual(
    attachmentSkipReason({ filename: "logo.png", size: 4096, content_id: "img001" }, 0),
    "inline_image",
    "signature logos must not pollute the document register",
  );
  assert.strictEqual(
    attachmentSkipReason({ filename: "macro.exe", size: 1024 }, 0),
    "unsupported_type",
  );
  assert.strictEqual(attachmentSkipReason({ filename: "empty.pdf", size: 0 }, 0), "empty");
  assert.strictEqual(
    attachmentSkipReason({ filename: "huge.pdf", size: 500_000_000 }, 0),
    "too_large",
  );
  assert.strictEqual(
    attachmentSkipReason({ filename: "ok.pdf", size: 1024 }, MAX_INBOUND_ATTACHMENTS),
    "over_limit",
  );
});

// ---- webhook verification --------------------------------------------------

const SECRET = `whsec_${Buffer.from("mobi-inbound-test-secret").toString("base64")}`;

function sign(body: string, id: string, timestamp: string, secret = SECRET): string {
  const key = Buffer.from(secret.slice("whsec_".length), "base64");
  const digest = crypto
    .createHmac("sha256", key)
    .update(`${id}.${timestamp}.${body}`, "utf8")
    .digest("base64");
  return `v1,${digest}`;
}

const NOW = new Date("2026-03-01T00:00:00Z");
const TS = String(Math.floor(NOW.getTime() / 1000));
const BODY = JSON.stringify({
  type: "email.received",
  data: {
    email_id: "56761188-7520-42d8-8898-ff6fc54ce618",
    from: "pat@acme.com",
    to: [`${MAILBOX}+${SLUG}@${DOMAIN}`],
    subject: "FW: Invitation to Bid",
  },
});

test("a correctly signed payload verifies", () => {
  const payload = verifySvixSignature(
    BODY,
    { id: "msg_1", timestamp: TS, signature: sign(BODY, "msg_1", TS) },
    SECRET,
    NOW,
  );
  assert.strictEqual(payload.type, "email.received");
});

test("signature rotation (multiple candidates) verifies", () => {
  const header = `v1,${crypto.randomBytes(32).toString("base64")} ${sign(BODY, "msg_1", TS)}`;
  const payload = verifySvixSignature(
    BODY,
    { id: "msg_1", timestamp: TS, signature: header },
    SECRET,
    NOW,
  );
  assert.strictEqual(payload.type, "email.received");
});

test("unsigned, wrongly signed, tampered, and replayed payloads are all rejected", () => {
  assert.throws(
    () => verifySvixSignature(BODY, { id: null, timestamp: TS, signature: sign(BODY, "msg_1", TS) }, SECRET, NOW),
    /Missing webhook signature headers/,
  );
  assert.throws(
    () => verifySvixSignature(BODY, { id: "msg_1", timestamp: TS, signature: "v1,not-a-signature" }, SECRET, NOW),
    /signature verification failed/i,
  );
  assert.throws(
    () =>
      verifySvixSignature(
        BODY,
        { id: "msg_1", timestamp: TS, signature: sign(BODY, "msg_1", TS, `whsec_${Buffer.from("other").toString("base64")}`) },
        SECRET,
        NOW,
      ),
    /signature verification failed/i,
  );
  // Body swapped after signing (a different tenant's alias).
  const tampered = BODY.replace(SLUG, "victim-9f8e7d");
  assert.throws(
    () => verifySvixSignature(tampered, { id: "msg_1", timestamp: TS, signature: sign(BODY, "msg_1", TS) }, SECRET, NOW),
    /signature verification failed/i,
  );
  // Signature id swapped (signed content includes the id).
  assert.throws(
    () => verifySvixSignature(BODY, { id: "msg_2", timestamp: TS, signature: sign(BODY, "msg_1", TS) }, SECRET, NOW),
    /signature verification failed/i,
  );
  // Replay outside the tolerance window.
  const old = String(Number(TS) - 3600);
  assert.throws(
    () => verifySvixSignature(BODY, { id: "msg_1", timestamp: old, signature: sign(BODY, "msg_1", old) }, SECRET, NOW),
    /outside tolerance/,
  );
  assert.throws(
    () => verifySvixSignature(BODY, { id: "msg_1", timestamp: "not-a-number", signature: sign(BODY, "msg_1", TS) }, SECRET, NOW),
    /Malformed webhook timestamp/,
  );
});

test("both svix-* and webhook-* header aliases are read", () => {
  const svix = readSvixHeaders(new Headers({ "svix-id": "a", "svix-timestamp": "1", "svix-signature": "v1,x" }));
  assert.deepStrictEqual(svix, { id: "a", timestamp: "1", signature: "v1,x" });
  const standard = readSvixHeaders(
    new Headers({ "webhook-id": "b", "webhook-timestamp": "2", "webhook-signature": "v1,y" }),
  );
  assert.deepStrictEqual(standard, { id: "b", timestamp: "2", signature: "v1,y" });
});

test("only email.received events are processed", () => {
  assert.ok(parseEmailReceivedEvent(JSON.parse(BODY)));
  assert.strictEqual(parseEmailReceivedEvent({ type: "email.delivered", data: { email_id: "x" } }), null);
  assert.strictEqual(parseEmailReceivedEvent({ type: "email.received", data: {} }), null);
});

// ---- entitlement boundary --------------------------------------------------

/** Executable SQL only — the header comments legitimately name the RPCs this
 *  migration must NOT call, so asserting against raw text would self-trip. */
function sqlWithoutComments(sql: string): string {
  return sql
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("--"))
    .join("\n");
}

test("captured forwards are read-only to customers and cannot create projects", () => {
  const migration = sqlWithoutComments(
    readFileSync(join(ROOT, "supabase/migrations/0036_inbound_bid_intake.sql"), "utf8"),
  );

  // Migration 0034 restricted project inserts to staff so the free-estimate
  // boundary can only be crossed through the entitlement RPCs. An email is
  // unauthenticated input, so this migration must not reopen that.
  assert.ok(
    !/insert\s+into\s+public\.projects/i.test(migration),
    "inbound intake must never insert a project row",
  );
  assert.ok(
    !/create_free_offer_project|create_entitled_project|intro_offer_claims/i.test(migration),
    "inbound intake must not touch the entitlement or intro-offer path",
  );
  for (const table of ["inbound_intake_messages", "inbound_intake_attachments"]) {
    assert.ok(
      migration.includes(`alter table public.${table} enable row level security`),
      `${table} must have RLS enabled`,
    );
    assert.ok(
      new RegExp(`create policy ${table}_select on public\\.${table}\\s+for select`).test(migration),
      `${table} must expose a select-only policy`,
    );
    assert.ok(
      !new RegExp(`create policy [\\w]+ on public\\.${table}\\s+for (insert|update|delete)`).test(migration),
      `${table} must not grant customers direct writes — transitions go through the RPCs`,
    );
  }
  assert.ok(
    migration.includes("tenant_mismatch"),
    "conversion must fail closed when the project and forward belong to different companies",
  );
  assert.ok(
    /status not in \('pending', 'sender_unverified'\)/.test(migration),
    "conversion must be single-use",
  );
});

test("the inbound webhook fails closed without a signing secret", () => {
  const route = readFileSync(join(ROOT, "src/app/api/email/inbound/route.ts"), "utf8");
  assert.ok(
    route.includes("RESEND_INBOUND_WEBHOOK_SECRET"),
    "route must require the signing secret",
  );
  // A half-configured deployment must answer one clear 503 rather than a 500 the
  // provider retries forever (or an HTML error page from a throwing constructor).
  for (const secret of [
    "!process.env.RESEND_API_KEY",
    "!process.env.SUPABASE_SERVICE_ROLE_KEY",
  ]) {
    assert.ok(route.includes(secret), `route must check ${secret} up front`);
  }
  assert.ok(route.includes("status: 503"), "an unconfigured intake must fail closed, not open");
  // Compare positions inside the handler, not the import block (whose order is
  // alphabetical and says nothing about execution order).
  const handler = route.slice(route.indexOf("export async function POST"));
  assert.ok(
    handler.indexOf("verifySvixSignature") < handler.indexOf("captureForwardedBid"),
    "signature verification must happen before any capture work",
  );
  assert.ok(
    route.includes("await request.text()"),
    "the raw body must be used for verification, not re-serialized JSON",
  );
});

test("only a verified member sender is emailed back", () => {
  const capture = readFileSync(join(ROOT, "src/lib/inbound-intake-server.ts"), "utf8");
  assert.ok(
    capture.includes("notifyEmail: senderVerified ? senderEmail : null"),
    "an unrecognized sender must not receive mail from us (backscatter/spam vector)",
  );
  assert.ok(
    capture.includes("MAX_PENDING_INTAKE_MESSAGES"),
    "the pending intake queue must be bounded",
  );
  assert.ok(
    capture.includes("MAX_UNROUTED_INTAKE_MESSAGES_PER_DAY"),
    "the shared-address triage queue must be bounded (public domain receives spam)",
  );
});

test("shared-mailbox routing prefers the tag and refuses to guess", () => {
  const capture = readFileSync(join(ROOT, "src/lib/inbound-intake-server.ts"), "utf8");

  // The tag is explicit and unguessable, so it must win over sender matching.
  assert.ok(
    capture.indexOf("findIntakeSlug") < capture.indexOf("companiesForSender"),
    "the company tag must be resolved before falling back to the sender",
  );
  assert.ok(
    /companyIds\.length > 1[\s\S]{0,120}ambiguous_sender/.test(capture),
    "an address belonging to several companies must not be guessed at — routing a plan set into the wrong tenant is worse than staff triage",
  );
  assert.ok(
    /companyIds\.length === 1/.test(capture),
    "sender routing must require exactly one matching company",
  );
  // Both routing paths must exclude soft-deleted companies: the tag lookup and
  // the sender lookup.
  assert.strictEqual(
    capture.match(/\.is\("deleted_at", null\)/g)?.length,
    2,
    "both the tag lookup and the sender lookup must exclude deleted companies",
  );
});

test("unrouted forwards are recorded for triage but store no documents", () => {
  const capture = readFileSync(join(ROOT, "src/lib/inbound-intake-server.ts"), "utf8");
  const unrouted = capture.slice(capture.indexOf("async function captureUnrouted"));

  assert.ok(unrouted.includes("company_id: null"), "an unrouted forward has no tenant");
  assert.ok(unrouted.includes('status: "unrouted"'));
  assert.ok(unrouted.includes("attachment_count: 0"), "no documents are stored for an unrouted forward");
  assert.ok(
    !unrouted.includes("downloadAttachment") && !unrouted.includes(".upload("),
    "a shared address anyone can write to must not become a file host",
  );
  assert.ok(
    unrouted.includes("skipped_attachment_count: attachmentCount"),
    "the attachment count is still recorded so staff can tell the contractor what didn't arrive",
  );
});

test("unrouted reasons carry a staff next step and are never customer-facing", () => {
  for (const reason of ["unknown_sender", "ambiguous_sender", "unknown_alias", null]) {
    const copy = unroutedReasonCopy(reason);
    assert.ok(copy.label.length > 0, `${reason} needs a label`);
    assert.ok(copy.nextStep.length > 0, `${reason} needs a next step`);
  }
  assert.ok(
    !isConvertibleIntakeStatus("unrouted"),
    "an unrouted forward has no tenant, so no customer may convert it",
  );
  assert.ok(
    !intakeStatusBadgeClass("unrouted").includes("green"),
    "a forward that needs routing must not get success styling",
  );
});

test("the staff triage view is behind the admin layout's staff gate", () => {
  const actions = readFileSync(join(ROOT, "src/app/admin/inbox/actions.ts"), "utf8");
  assert.ok(
    actions.includes("requireStaff()"),
    "staff dismissal must require a staff role, not merely an authenticated user",
  );
  assert.ok(
    actions.includes("dismiss_inbound_intake"),
    "staff dismissal must go through the RPC so DB-enforced transitions still apply",
  );
});

test("migration 0037 keeps tenant and status consistent", () => {
  const migration = sqlWithoutComments(
    readFileSync(join(ROOT, "supabase/migrations/0037_inbound_intake_routing.sql"), "utf8"),
  );

  assert.ok(
    /alter column company_id drop not null/.test(migration),
    "an unrouted forward must be able to exist without a tenant",
  );
  assert.ok(
    migration.includes("'unrouted'"),
    "the unrouted status must be added to the allowed set",
  );
  // Without this, an unrouted row could sit in a company's queue and inflate the
  // portal's "waiting for your review" count with something the customer can't open.
  assert.ok(
    /status = 'unrouted' and company_id is null/.test(migration),
    "an unrouted forward must never carry a tenant",
  );
  assert.ok(
    /status in \('pending', 'sender_unverified', 'converted'\) and company_id is not null/.test(
      migration,
    ),
    "every live customer-facing status must carry a tenant",
  );
  // Staff dismiss untenanted spam out of the triage queue; if 'dismissed' required
  // a tenant, that transition would fail the check constraint and the triage
  // button would error.
  assert.ok(
    /or status = 'dismissed'/.test(migration),
    "dismissal must be allowed with or without a tenant so untenanted spam can be cleared",
  );
  assert.ok(
    !/create policy/.test(migration),
    "0036's select policies already fail closed for null company_id (is_member_of(null) is false) — no new policy should widen that",
  );
});

// ---- presentation ----------------------------------------------------------

test("intake statuses present honestly", () => {
  assert.strictEqual(intakeStatusLabel("pending"), "Ready to review");
  assert.strictEqual(intakeStatusLabel("sender_unverified"), "Unrecognized sender");
  assert.strictEqual(intakeStatusLabel("unrouted"), "Needs routing");
  assert.ok(isConvertibleIntakeStatus("pending"));
  assert.ok(isConvertibleIntakeStatus("sender_unverified"));
  assert.ok(!isConvertibleIntakeStatus("converted"), "a converted forward must not be reusable");
  assert.ok(!isConvertibleIntakeStatus("dismissed"));
  assert.ok(
    !intakeStatusBadgeClass("sender_unverified").includes("green"),
    "an unverified sender must not get success styling",
  );
});

if (failures > 0) {
  console.error(`\n${failures} inbound intake check(s) failed`);
  process.exit(1);
}
console.log("\ninbound bid intake checks passed");

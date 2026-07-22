import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { SupabaseClient } from "@supabase/supabase-js";
import {
  buildStatusNotifications,
  createStatusChangeNotifications,
  statusNotificationTemplate,
} from "../src/lib/notifications";

/**
 * Notification templates are deterministic + safe, external outbox rows are
 * always held (never sent), and there is no external sender in this packet.
 */

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => void | Promise<void> };
const tests: Test[] = [];
const test = (name: string, fn: () => void | Promise<void>) => tests.push({ name, fn });

test("status templates are deterministic and safe", () => {
  const a = statusNotificationTemplate("pricing_in_progress");
  const b = statusNotificationTemplate("pricing_in_progress");
  assert(JSON.stringify(a) === JSON.stringify(b), "same status must yield identical copy");
  // Final/locked statuses must never claim delivery/completion.
  for (const status of ["delivered", "approved", "revised"]) {
    const t = statusNotificationTemplate(status);
    const blob = `${t.title} ${t.body}`.toLowerCase();
    assert(!blob.includes("delivered"), `${status} template implies delivery`);
    assert(!blob.includes("complete"), `${status} template implies completion`);
  }
});

test("build produces one in-app row per recipient + email outbox only when email present", () => {
  const built = buildStatusNotifications({
    companyId: "co-1",
    projectId: "pr-1",
    statusHistoryId: "sh-1",
    toStatus: "takeoff_in_progress",
    recipients: [
      { userId: "u1", email: "a@co.com" },
      { userId: "u2", email: null },
    ],
  });
  assert(built.notifications.length === 2, "one in-app notification per recipient");
  assert(built.outbox.length === 1, "outbox only for recipients with an email");
  assert(built.outbox[0].recipient === "a@co.com", "outbox targets the email");
});

test("every external outbox row is held (approval_required), never sent", () => {
  const built = buildStatusNotifications({
    companyId: "co-1",
    projectId: "pr-1",
    statusHistoryId: "sh-1",
    toStatus: "document_review",
    recipients: [{ userId: "u1", email: "a@co.com" }],
  });
  for (const row of built.outbox) {
    assert(row.status === "approval_required", "outbox rows must be approval_required");
    assert(row.channel === "email", "only the email channel is prepared in this packet");
  }
});

test("notification rows carry the idempotency key and no internal note", () => {
  const built = buildStatusNotifications({
    companyId: "co-1",
    projectId: "pr-1",
    statusHistoryId: "sh-1",
    toStatus: "qa_review",
    recipients: [{ userId: "u1", email: "a@co.com" }],
  });
  const n = built.notifications[0] as Record<string, unknown>;
  assert(n.status_history_id === "sh-1", "in-app row keyed to status-history event");
  assert(n.channel === "in_app", "in-app channel");
  assert(!("internal_note" in n), "in-app row must not carry an internal note");
});

test("migration outbox constraint forbids any sent/queued state", () => {
  const migration = readFileSync(
    join(process.cwd(), "supabase/migrations/0032_notifications_outbox.sql"),
    "utf8",
  ).toLowerCase();
  const statusCheck = migration.match(/check \(status in \([^)]*\)\)/);
  assert(statusCheck, "outbox status check constraint not found");
  assert(
    statusCheck![0] === "check (status in ('approval_required', 'held', 'canceled'))",
    `outbox status constraint must only allow held states, got: ${statusCheck![0]}`,
  );
  // Scan the CONSTRAINT clause (not comments) for any sent/queued state.
  for (const sent of ["'sent'", "'queued'", "'sending'", "'delivered'"]) {
    assert(!statusCheck![0].includes(sent), `outbox constraint must not allow ${sent}`);
  }
  assert(
    migration.includes("unique (status_history_id, channel, recipient)"),
    "outbox must be idempotent on (status_history_id, channel, recipient)",
  );
});

test("no external sender/provider is wired into the notification path", () => {
  const lib = readFileSync(join(process.cwd(), "src/lib/notifications.ts"), "utf8").toLowerCase();
  for (const provider of ["resend", "twilio", "sendgrid", "nodemailer", "fetch("]) {
    assert(!lib.includes(provider), `notifications lib must not call a sender (${provider})`);
  }
});

test("in-app rows match the EVOLVED production schema (user_id/type, not recipient_user_id/kind)", () => {
  const built = buildStatusNotifications({
    companyId: "co-1",
    projectId: "pr-1",
    statusHistoryId: "sh-1",
    toStatus: "takeoff_in_progress",
    recipients: [{ userId: "u1", email: "a@co.com" }],
  });
  const n = built.notifications[0] as Record<string, unknown>;
  assert(n.user_id === "u1", "recipient must be keyed on the pre-existing user_id column");
  assert(n.type === "project_status", "kind must map to the pre-existing type column");
  assert(!("recipient_user_id" in n), "must not write the nonexistent recipient_user_id column");
  assert(!("kind" in n), "must not write the nonexistent kind column");
});

test("null/empty status-history id never produces notifications (idempotency-safe)", async () => {
  // A stub client that explodes if any query is attempted proves the guard
  // short-circuits BEFORE touching the database.
  const explodingClient = new Proxy(
    {},
    {
      get() {
        throw new Error("createStatusChangeNotifications must not query when the history id is missing");
      },
    },
  ) as unknown as SupabaseClient;

  const result = await createStatusChangeNotifications(explodingClient, {
    companyId: "co-1",
    projectId: "pr-1",
    statusHistoryId: "",
    toStatus: "takeoff_in_progress",
  });
  assert(result.inApp === 0 && result.outbox === 0, "no notifications when the canonical history id is missing");
});

test("changeStatus only notifies after a successful status update AND history event", () => {
  const actions = readFileSync(
    join(process.cwd(), "src/app/admin/projects/[id]/actions.ts"),
    "utf8",
  );
  // The notification call is gated on both errors being absent AND a real id.
  assert(
    /!updateErr && !historyErr && historyRow\?\.id && current\?\.company_id/.test(actions),
    "changeStatus must gate notifications on update+history success and a canonical history id",
  );
  assert(
    /statusHistoryId: historyRow\.id/.test(actions),
    "changeStatus must pass the canonical (non-null) history id",
  );
});

test("migration 0032 EVOLVES the existing notifications table (no recreate, no policy clash)", () => {
  const migration = readFileSync(
    join(process.cwd(), "supabase/migrations/0032_notifications_outbox.sql"),
    "utf8",
  );
  // It must ALTER, never CREATE, the existing production notifications table.
  assert(/alter table public\.notifications/i.test(migration), "0032 must ALTER the existing notifications table");
  assert(
    !/create table[\s\S]*public\.notifications\b/i.test(migration),
    "0032 must not recreate public.notifications (would silently skip the new shape)",
  );
  // Partial idempotency index over the event key, non-null history id only.
  assert(
    /create unique index[^;]*on public\.notifications[^;]*\(status_history_id, channel, user_id\)[^;]*where status_history_id is not null/is.test(
      migration,
    ),
    "0032 must add a PARTIAL unique index so legacy null-history rows are untouched",
  );
  // Only a NEW staff insert policy — never recreate the 0002 select/update names.
  assert(migration.includes("notifications_insert_staff"), "0032 must add the staff insert policy");
  assert(
    !/create policy notifications_select\b/.test(migration) &&
      !/create policy notifications_update_self\b/.test(migration),
    "0032 must NOT recreate the existing notifications_select / notifications_update_self policies",
  );
});

async function main(): Promise<void> {
  let failures = 0;
  for (const t of tests) {
    try {
      await t.fn();
      console.log(`  PASS  ${t.name}`);
    } catch (e) {
      failures += 1;
      console.error(`  FAIL  ${t.name}`);
      console.error(`        ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  console.log(`\n${tests.length - failures}/${tests.length} passed`);
  if (failures > 0) process.exit(1);
}

void main();

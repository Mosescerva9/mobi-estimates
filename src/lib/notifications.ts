import type { SupabaseClient } from "@supabase/supabase-js";
import { customerProgressForStatus } from "./milestones";

/**
 * Notification foundation.
 *
 * On staff project status changes we create tenant-scoped IN-APP notification
 * rows for the customer company's members, plus HELD external-outbox rows for a
 * future (separately-approved) email/sms sender. THIS PACKET SENDS NOTHING:
 * there is no worker/provider call anywhere, and every outbox row is created in
 * an `approval_required` state that the DB check constraint holds.
 *
 * Copy is DETERMINISTIC and derived only from the public status milestone
 * (src/lib/milestones.ts). It never contains internal notes, provider output,
 * plan text, or secrets.
 */

export type NotificationChannel = "in_app" | "email" | "sms";

export interface StatusNotificationTemplate {
  title: string;
  body: string;
}

/**
 * Pure, deterministic customer-facing status message. Same status always yields
 * the same safe copy. Derives only from the fail-closed milestone mapping — so
 * it can never leak a delivered/complete claim or any internal note.
 */
export function statusNotificationTemplate(toStatus: string): StatusNotificationTemplate {
  const progress = customerProgressForStatus(toStatus);
  if (progress.isClosed) {
    return {
      title: `Project ${(progress.closedLabel ?? "closed").toLowerCase()}`,
      body: progress.nextStep,
    };
  }
  return {
    title: `Project update: ${progress.label}`,
    body: progress.nextStep,
  };
}

export function projectLink(projectId: string): string {
  return `/portal/projects/${projectId}`;
}

export interface NotificationRecipient {
  userId: string;
  email: string | null;
}

export interface InAppNotificationRow {
  company_id: string;
  // The evolved production public.notifications table keys the recipient on the
  // pre-existing `user_id` column and the kind on the pre-existing `type` column.
  user_id: string;
  project_id: string;
  status_history_id: string;
  channel: "in_app";
  type: "project_status";
  status_event: string;
  title: string;
  body: string;
  link: string;
}

export interface OutboxNotificationRow {
  company_id: string;
  project_id: string;
  status_history_id: string;
  channel: "email";
  recipient: string;
  recipient_user_id: string;
  subject: string;
  body: string;
  status: "approval_required";
}

export interface BuiltStatusNotifications {
  notifications: InAppNotificationRow[];
  outbox: OutboxNotificationRow[];
}

/**
 * Pure row builder. Given the tenant/project/event and the recipients, produce
 * the in-app rows (one per recipient) and the held external-outbox rows (email
 * only, one per recipient WITH an email). External rows are always
 * `approval_required` — this function never marks anything sent/queued.
 */
export function buildStatusNotifications(input: {
  companyId: string;
  projectId: string;
  /** Canonical status-history event id. Required — null-keyed rows would defeat idempotency. */
  statusHistoryId: string;
  toStatus: string;
  recipients: NotificationRecipient[];
}): BuiltStatusNotifications {
  const { title, body } = statusNotificationTemplate(input.toStatus);
  const link = projectLink(input.projectId);

  const notifications: InAppNotificationRow[] = input.recipients.map((r) => ({
    company_id: input.companyId,
    user_id: r.userId,
    project_id: input.projectId,
    status_history_id: input.statusHistoryId,
    channel: "in_app",
    type: "project_status",
    status_event: input.toStatus,
    title,
    body,
    link,
  }));

  const outbox: OutboxNotificationRow[] = input.recipients
    .filter((r): r is NotificationRecipient & { email: string } => Boolean(r.email))
    .map((r) => ({
      company_id: input.companyId,
      project_id: input.projectId,
      status_history_id: input.statusHistoryId,
      channel: "email",
      recipient: r.email,
      recipient_user_id: r.userId,
      subject: title,
      body,
      status: "approval_required",
    }));

  return { notifications, outbox };
}

/**
 * Server helper: create the in-app + held-outbox rows for a status change.
 * Idempotent — the unique constraints on (status_history_id, channel, recipient)
 * mean a retried status change never duplicates notifications. Best-effort:
 * callers should not fail the status change if this throws (it is wrapped by the
 * caller). Uses whatever client is passed (staff RLS client is sufficient — the
 * notification/outbox insert policies allow staff).
 */
export async function createStatusChangeNotifications(
  supabase: SupabaseClient,
  input: { companyId: string; projectId: string; statusHistoryId: string; toStatus: string },
): Promise<{ inApp: number; outbox: number }> {
  // Never create null-keyed notifications: the caller must pass a canonical
  // status-history event id. Without it the idempotency key is undefined and a
  // retry would duplicate. Fail closed to a no-op.
  if (!input.statusHistoryId) return { inApp: 0, outbox: 0 };

  // Company members are the recipients. Read their profile emails for the held
  // outbox. Staff RLS can read company_members/profiles for the customer tenant.
  const { data: members } = await supabase
    .from("company_members")
    .select("user_id")
    .eq("company_id", input.companyId);

  const userIds = (members ?? [])
    .map((m) => (m as { user_id: string | null }).user_id)
    .filter((id): id is string => Boolean(id));
  if (userIds.length === 0) return { inApp: 0, outbox: 0 };

  const { data: profiles } = await supabase
    .from("profiles")
    .select("id, email")
    .in("id", userIds);
  const emailByUser = new Map<string, string | null>(
    (profiles ?? []).map((p) => [
      (p as { id: string }).id,
      (p as { email: string | null }).email ?? null,
    ]),
  );

  const recipients: NotificationRecipient[] = userIds.map((userId) => ({
    userId,
    email: emailByUser.get(userId) ?? null,
  }));

  const { notifications, outbox } = buildStatusNotifications({
    companyId: input.companyId,
    projectId: input.projectId,
    statusHistoryId: input.statusHistoryId,
    toStatus: input.toStatus,
    recipients,
  });

  // Plain inserts: idempotency is enforced by the DB unique indexes. The in-app
  // table's index is PARTIAL (status_history_id is not null), which ON CONFLICT
  // target inference does not support, so a retry surfaces a unique-violation
  // error we intentionally ignore (this whole helper is best-effort). All rows
  // here carry a non-null status_history_id, so the partial index always applies.
  if (notifications.length > 0) {
    await supabase.from("notifications").insert(notifications);
  }

  if (outbox.length > 0) {
    await supabase
      .from("notification_outbox")
      .upsert(outbox, {
        onConflict: "status_history_id,channel,recipient",
        ignoreDuplicates: true,
      });
  }

  return { inApp: notifications.length, outbox: outbox.length };
}

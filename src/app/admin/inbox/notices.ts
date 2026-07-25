/**
 * Admin forwarded-bid notice copy. Split from actions.ts because a "use server"
 * module may only export async functions.
 */

export const ADMIN_INBOX_NOTICE_CODES = ["dismissed", "already_submitted", "failed"] as const;
export type AdminInboxNoticeCode = (typeof ADMIN_INBOX_NOTICE_CODES)[number];

export function isAdminInboxNoticeCode(value: string | undefined): value is AdminInboxNoticeCode {
  return (ADMIN_INBOX_NOTICE_CODES as readonly string[]).includes(value ?? "");
}

export function adminInboxNoticeCopy(
  value: string | undefined,
): { tone: "success" | "warning" | "error"; message: string } | null {
  switch (value) {
    case "dismissed":
      return { tone: "success", message: "Forwarded bid dismissed." };
    case "already_submitted":
      return {
        tone: "warning",
        message: "That forward was already submitted as a project, so it can't be dismissed.",
      };
    case "failed":
      return { tone: "error", message: "Could not dismiss that forward. Please try again." };
    default:
      return null;
  }
}

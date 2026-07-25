/**
 * Forwarded-bid notice copy.
 *
 * Kept out of actions.ts because a "use server" module may only export async
 * functions, and out of the page so the strings can be asserted offline.
 */

export type InboxNoticeTone = "success" | "warning" | "error";

export const INBOX_NOTICE_CODES = ["dismissed", "already_submitted", "failed"] as const;
export type InboxNoticeCode = (typeof INBOX_NOTICE_CODES)[number];

export function isInboxNoticeCode(value: string | undefined): value is InboxNoticeCode {
  return (INBOX_NOTICE_CODES as readonly string[]).includes(value ?? "");
}

export function inboxNoticeCopy(
  value: string | undefined,
): { tone: InboxNoticeTone; message: string } | null {
  switch (value) {
    case "dismissed":
      return {
        tone: "success",
        message: "Forwarded bid dismissed. The documents stay in your account.",
      };
    case "already_submitted":
      return {
        tone: "warning",
        message:
          "That forwarded bid was already submitted as a project, so it can't be dismissed.",
      };
    case "failed":
      return {
        tone: "error",
        message: "We couldn't dismiss that forwarded bid. Please try again.",
      };
    default:
      return null;
  }
}

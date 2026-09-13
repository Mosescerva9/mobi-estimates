/**
 * The daily guide. This is the single source shared by the in-app Help screen.
 * The README keeps the same steps in sync by hand.
 */
export type GuideStep = { title: string; body: string };

export const DAILY_GUIDE: GuideStep[] = [
  {
    title: "1. Open today's queue",
    body: "Start on the Today screen. Everything waiting for you is listed here, with posts to approve first. If it's empty, you're caught up.",
  },
  {
    title: "2. Review your posts",
    body: "Read each draft. If it feels generic, click Rewrite sharper. Edit the wording, then Approve to publish (or dry-run if LinkedIn isn't connected). Reject anything off-brand.",
  },
  {
    title: "3. Comment on a LinkedIn post (extension)",
    body: "Open the LinkedIn post → Mobi extension → Draft comment for this post → review → Approve & Post. The extension submits the comment on that page after you approve.",
  },
  {
    title: "4. Or approve drafts in Engage",
    body: "If a draft is already in Engage, Approve & open for extension, then on the LinkedIn tab tap Post an already-approved comment. Backup paste still works if LinkedIn’s layout blocks the submitter.",
  },
  {
    title: "5. Send warm DMs",
    body: "Warm DMs are only for people who already engaged. Rewrite if it sounds salesy, Approve & copy, paste into LinkedIn, then Mark sent.",
  },
  {
    title: "6. Optional: batch Scout + Hermes",
    body: "Capture several feed posts with the extension, or paste into Scout. Draft comments now (or Hermes) fills Engage. Prefer drafting one post at a time on LinkedIn when you can.",
  },
];

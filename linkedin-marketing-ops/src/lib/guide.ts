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
    title: "3. Capture posts in Scout (no extension needed)",
    body: "Open a LinkedIn post → Share → Copy link. In Scout, paste the URL and post text, Save to Scout, then click Draft comments now.",
  },
  {
    title: "4. Approve comments in Engage",
    body: "Review each recommendation, then Approve & open post — it copies the text and opens the exact LinkedIn URL. Paste there, click Post yourself, then Mark commented.",
  },
  {
    title: "5. Send warm DMs",
    body: "Warm DMs are only for people who already engaged. Rewrite if it sounds salesy, Approve & copy, paste into LinkedIn, then Mark sent.",
  },
  {
    title: "6. Optional later: extension + Hermes",
    body: "If you want one-tap capture later, pair the Safari/Chrome extension. Hermes Telegram processing is optional — Draft comments now works without it.",
  },
];

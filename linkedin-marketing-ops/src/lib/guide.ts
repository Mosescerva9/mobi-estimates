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
    title: "3. Handle comments & connections",
    body: "On Engage, paste the real LinkedIn post URL and the post text (or a short description). Review the comment, then Approve & open post — it copies the text and opens the exact post. Paste it there and click Post, then click Mark commented. Connection notes stay Approve & copy. Mobi never browses the feed or submits comments for you.",
  },
  {
    title: "4. Scout posts from your iPhone (optional)",
    body: "On your phone, open LinkedIn in Safari and tap the Mobi Scout button while you browse — it saves the posts you can see. Then message Hermes in Telegram: “Process my LinkedIn batch.” Any good comments appear in Engage for you to approve. Nothing is posted for you, and Scout never scrolls or clicks on its own.",
  },
  {
    title: "5. Send your warm DMs",
    body: "Warm DMs are only for people who already engaged. Rewrite if it sounds salesy, Approve & copy, paste into LinkedIn, then Mark sent.",
  },
  {
    title: "6. Adjust settings, then repeat tomorrow",
    body: "Every so often, open Settings to update your brand voice, keywords, link, and daily caps. That's the whole routine — come back tomorrow and do it again.",
  },
];

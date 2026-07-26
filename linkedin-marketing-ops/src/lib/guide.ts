/**
 * The five-step daily guide. This is the single source shared by the in-app
 * Help screen. The README keeps the same five steps in sync by hand.
 */
export type GuideStep = { title: string; body: string };

export const DAILY_GUIDE: GuideStep[] = [
  {
    title: "1. Open today's queue",
    body: "Start on the Today screen. Everything waiting for you is listed here, with posts to approve first. If it's empty, you're caught up.",
  },
  {
    title: "2. Review your posts",
    body: "Read each post draft and edit the wording right in the box. Click Approve to publish it (or save it as a dry run if LinkedIn isn't connected), or Reject to throw it away.",
  },
  {
    title: "3. Handle comments & connections",
    body: "On the Engage screen, tweak each suggested comment or connection note, then click Approve. The text is copied for you automatically — paste it into LinkedIn.",
  },
  {
    title: "4. Send your warm DMs",
    body: "On the Warm DMs screen (only people who already engaged with you), edit the message, click Approve to copy it, paste it into LinkedIn, then click Mark sent.",
  },
  {
    title: "5. Adjust settings, then repeat tomorrow",
    body: "Every so often, open Settings to update your brand voice, keywords, link, and daily caps. That's the whole routine — come back tomorrow and do it again.",
  },
];

import { polishPostBody, polishShortText } from "./content-quality";
import { createId } from "./id";
import {
  POST_ANGLES,
  POST_TOPICS,
  type PostAngle,
  commentSystemPrompt,
  connectSystemPrompt,
  dmSystemPrompt,
  postSystemPrompt,
  postUserPrompt,
  regeneratePostUserPrompt,
} from "./prompts";
import type {
  DmItem,
  DmTrigger,
  EngageItem,
  EngageKind,
  PostItem,
  Settings,
} from "./types";

type JsonDraft = Record<string, string>;

function nowIso(): string {
  return new Date().toISOString();
}

export function hasOpenAI(): boolean {
  return Boolean(process.env.OPENAI_API_KEY?.trim());
}

export function modelLabel(): string {
  if (!hasOpenAI()) return "mock-local";
  return process.env.OPENAI_MODEL?.trim() || "gpt-4o-mini";
}

async function callOpenAI(
  system: string,
  user: string,
  temperature = 0.7
): Promise<JsonDraft> {
  const apiKey = process.env.OPENAI_API_KEY!.trim();
  const model = process.env.OPENAI_MODEL?.trim() || "gpt-4o-mini";

  const res = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      temperature,
      response_format: { type: "json_object" },
      messages: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`OpenAI error ${res.status}: ${text.slice(0, 300)}`);
  }

  const data = (await res.json()) as {
    choices?: Array<{ message?: { content?: string } }>;
  };
  const content = data.choices?.[0]?.message?.content;
  if (!content) throw new Error("OpenAI returned empty content");
  return JSON.parse(content) as JsonDraft;
}

const MOCK_POSTS: Record<
  string,
  (settings: Settings) => { topic: string; body: string; cta: string }
> = {
  default: (settings) => ({
    topic: "Bid delays usually start before pricing",
    body: [
      "Most bid delays do not start in pricing.",
      "",
      "They start earlier — incomplete scopes, fuzzy quantities, and plan sets sitting in an inbox while the field team is already moving.",
      "",
      "When that happens, markup becomes guesswork and addenda turn into overnight scrambles.",
      "",
      "If your bottleneck is the takeoff — not the sell price — where does it usually show up first for your team?",
    ].join("\n"),
    cta: `Invite reply, then point to ${settings.ctaUrl} if they ask for help`,
  }),
  overflow_capacity: (settings) => ({
    topic: "Overflow estimating before the next bid night",
    body: [
      "Your estimating team can be excellent and still run out of hours.",
      "",
      "That is usually when overflow support matters — not as a permanent replacement, but as capacity for the week when every invitation lands at once.",
      "",
      "A clean takeoff path keeps the bid calendar moving without forcing a rushed hire mid-cycle.",
      "",
      "Curious: do you handle overflow in-house, with freelancers, or not at all right now?",
    ].join("\n"),
    cta: `Soft path to ${settings.ctaUrl} for contractors who need capacity`,
  }),
  takeoff_quality: (settings) => ({
    topic: "Pretty PDF vs usable takeoff",
    body: [
      "A polished estimate PDF can still be hard to build from.",
      "",
      "What PMs usually need is clearer quantities, cleaner scope boundaries, and fewer assumptions buried in the notes.",
      "",
      "That is the difference between a document that looks finished and a package the field can actually run.",
      "",
      "When you review an estimate, what do you check first — presentation, or whether the quantities hold up?",
    ].join("\n"),
    cta: `Conversation CTA; share ${settings.ctaUrl} only if asked`,
  }),
};

function mockPost(topic: string, settings: Settings, angle?: PostAngle): JsonDraft {
  if (angle && MOCK_POSTS[angle]) {
    const draft = MOCK_POSTS[angle](settings);
    return draft;
  }
  if (angle === "overflow_capacity") return MOCK_POSTS.overflow_capacity(settings);
  if (angle === "takeoff_quality") return MOCK_POSTS.takeoff_quality(settings);

  const base = MOCK_POSTS.default(settings);
  return {
    topic,
    body: [
      `${topic.replace(/\.$/, "")}.`,
      "",
      "Most bid friction shows up before the sell price is even discussed — incomplete scopes, missing addenda, and quantities that still need a second pass.",
      "",
      `${settings.companyName} helps contractors get a clearer takeoff path when the in-house team is already underwater.`,
      "",
      "If that sounds familiar, what usually breaks first on your bids: documents, quantities, or review time?",
    ].join("\n"),
    cta: base.cta,
  };
}

function mockComment(targetName: string, summary: string): JsonDraft {
  const first = targetName.split(" ")[0] || "there";
  const clue = summary.trim().replace(/\s+/g, " ").slice(0, 90);
  return {
    suggestedText: `${first}, that tracks. Once ${clue.toLowerCase()} slips, the estimate inherits schedule risk before anyone prices a single line.`,
  };
}

function mockConnect(targetName: string, title: string, company: string): JsonDraft {
  const first = targetName.split(" ")[0] || "there";
  return {
    suggestedText: `Hi ${first} — noticed your work as ${title} at ${company}. I spend a lot of time around estimating capacity for contractors. Happy to connect.`,
  };
}

function mockDm(
  leadName: string,
  trigger: DmTrigger,
  company: string,
  settings: Settings
): JsonDraft {
  const first = leadName.split(" ")[0] || "there";
  const triggerLine: Record<DmTrigger, string> = {
    liked_post: "thanks for the like on the estimating post",
    commented: "appreciate the comment on the takeoff thread",
    accepted_connect: "thanks for connecting",
    demo_request: "got your estimate / demo request",
    site_visit: "saw you checked out Mobi Estimates",
  };

  return {
    body: [
      `Hi ${first} — ${triggerLine[trigger]}.`,
      "",
      `I work with teams like ${company} that need cleaner quantity takeoffs without adding permanent headcount overnight.`,
      "",
      `If useful, you can start with one project here: ${settings.ctaUrl}`,
      "",
      "Either way, glad we’re connected.",
    ].join("\n"),
  };
}

function toPostItem(
  draft: JsonDraft,
  fallbackTopic: string,
  settings: Settings
): PostItem {
  const stamp = nowIso();
  return {
    id: createId("post"),
    type: "post",
    status: "pending_approval",
    topic: (draft.topic || fallbackTopic).trim(),
    body: polishPostBody(draft.body || ""),
    cta: (draft.cta || `Soft CTA → ${settings.ctaUrl}`).trim(),
    scheduledFor: null,
    createdAt: stamp,
    updatedAt: stamp,
    aiModel: modelLabel(),
  };
}

function pickTopics(count: number): string[] {
  return [...POST_TOPICS].sort(() => Math.random() - 0.5).slice(0, count);
}

function pickAngles(count: number): PostAngle[] {
  return [...POST_ANGLES]
    .sort(() => Math.random() - 0.5)
    .slice(0, count)
    .map((a) => a.id);
}

export async function generatePostDrafts(
  settings: Settings,
  count = 3,
  angle?: PostAngle
): Promise<PostItem[]> {
  const topics = pickTopics(count);
  const angles = angle ? Array(count).fill(angle) : pickAngles(count);
  const items: PostItem[] = [];

  for (let i = 0; i < topics.length; i++) {
    const topic = topics[i];
    const chosenAngle = angles[i] as PostAngle | undefined;
    const draft = hasOpenAI()
      ? await callOpenAI(
          postSystemPrompt(settings),
          postUserPrompt(topic, chosenAngle),
          0.75
        )
      : mockPost(topic, settings, chosenAngle);
    items.push(toPostItem(draft, topic, settings));
  }
  return items;
}

export async function regeneratePostDraft(
  settings: Settings,
  post: PostItem,
  instruction?: string
): Promise<PostItem> {
  const draft = hasOpenAI()
    ? await callOpenAI(
        postSystemPrompt(settings),
        regeneratePostUserPrompt(
          { topic: post.topic, body: post.body },
          instruction
        ),
        0.8
      )
    : mockPost(post.topic, settings);

  const next = toPostItem(draft, post.topic, settings);
  return {
    ...post,
    topic: next.topic,
    body: next.body,
    cta: next.cta,
    status: "pending_approval",
    updatedAt: nowIso(),
    aiModel: modelLabel(),
    notes: "Regenerated — review before approving.",
  };
}

export async function generateEngageDraft(
  settings: Settings,
  input: {
    kind: EngageKind;
    targetName: string;
    targetTitle: string;
    targetCompany: string;
    sourcePostSummary: string;
  }
): Promise<EngageItem> {
  const draft = hasOpenAI()
    ? await callOpenAI(
        input.kind === "comment"
          ? commentSystemPrompt(settings)
          : connectSystemPrompt(settings),
        JSON.stringify(input),
        input.kind === "comment" ? 0.55 : 0.5
      )
    : input.kind === "comment"
      ? mockComment(input.targetName, input.sourcePostSummary)
      : mockConnect(input.targetName, input.targetTitle, input.targetCompany);

  const stamp = nowIso();
  const text = polishShortText(draft.suggestedText || "");
  return {
    id: createId("eng"),
    type: "engage",
    kind: input.kind,
    status: "pending_approval",
    targetName: input.targetName,
    targetTitle: input.targetTitle,
    targetCompany: input.targetCompany,
    sourcePostSummary: input.sourcePostSummary,
    suggestedText:
      input.kind === "connect" && text.length > 280 ? text.slice(0, 277) + "…" : text,
    createdAt: stamp,
    updatedAt: stamp,
    aiModel: modelLabel(),
  };
}

export async function regenerateEngageDraft(
  settings: Settings,
  item: EngageItem,
  instruction?: string
): Promise<EngageItem> {
  const regenerated = await generateEngageDraft(settings, {
    kind: item.kind,
    targetName: item.targetName,
    targetTitle: item.targetTitle,
    targetCompany: item.targetCompany,
    sourcePostSummary: instruction
      ? `${item.sourcePostSummary}\nRewrite note: ${instruction}`
      : item.sourcePostSummary,
  });

  return {
    ...item,
    suggestedText: regenerated.suggestedText,
    status: "pending_approval",
    updatedAt: nowIso(),
    aiModel: modelLabel(),
  };
}

export async function generateDmDraft(
  settings: Settings,
  input: {
    leadName: string;
    leadTitle: string;
    leadCompany: string;
    trigger: DmTrigger;
  }
): Promise<DmItem> {
  const draft = hasOpenAI()
    ? await callOpenAI(dmSystemPrompt(settings), JSON.stringify(input), 0.6)
    : mockDm(input.leadName, input.trigger, input.leadCompany, settings);

  const stamp = nowIso();
  return {
    id: createId("dm"),
    type: "dm",
    status: "pending_approval",
    leadName: input.leadName,
    leadTitle: input.leadTitle,
    leadCompany: input.leadCompany,
    trigger: input.trigger,
    body: polishPostBody(draft.body || ""),
    createdAt: stamp,
    updatedAt: stamp,
    aiModel: modelLabel(),
  };
}

export async function regenerateDmDraft(
  settings: Settings,
  item: DmItem,
  instruction?: string
): Promise<DmItem> {
  const user = [
    JSON.stringify({
      leadName: item.leadName,
      leadTitle: item.leadTitle,
      leadCompany: item.leadCompany,
      trigger: item.trigger,
    }),
    "Rewrite the warm DM to be clearer and more personal.",
    instruction ? `Operator note: ${instruction}` : "",
    `Current draft:\n${item.body}`,
  ]
    .filter(Boolean)
    .join("\n\n");

  const draft = hasOpenAI()
    ? await callOpenAI(dmSystemPrompt(settings), user, 0.65)
    : mockDm(item.leadName, item.trigger, item.leadCompany, settings);

  return {
    ...item,
    body: polishPostBody(draft.body || item.body),
    status: "pending_approval",
    updatedAt: nowIso(),
    aiModel: modelLabel(),
  };
}

export function aiMode(): "openai" | "mock" {
  return hasOpenAI() ? "openai" : "mock";
}

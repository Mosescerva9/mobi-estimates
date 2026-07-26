import { createId } from "./id";
import {
  POST_TOPICS,
  commentSystemPrompt,
  connectSystemPrompt,
  dmSystemPrompt,
  postSystemPrompt,
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

async function callOpenAI(system: string, user: string): Promise<JsonDraft> {
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
      temperature: 0.7,
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

function mockPost(topic: string, settings: Settings): JsonDraft {
  return {
    topic,
    body: [
      `${topic}.`,
      "",
      "Most bid delays do not start in pricing. They start earlier — incomplete scopes, fuzzy quantities, and plans sitting in an inbox while the site team is already in the field.",
      "",
      `${settings.companyName} is built for estimators and GCs who need a usable takeoff path without parking at a desktop all day. Upload plans, clarify scope, and move toward a number you can defend.`,
      "",
      "If your team is buried in bid nights, reply and tell me where the bottleneck usually hits.",
    ].join("\n"),
    cta: `Soft CTA → ${settings.ctaUrl}`,
  };
}

function mockComment(targetName: string, summary: string): JsonDraft {
  return {
    suggestedText: `Good point, ${targetName.split(" ")[0]}. The estimating bottleneck you called out — ${summary.slice(0, 80).toLowerCase()} — is usually where schedule risk gets baked in before anyone notices.`,
  };
}

function mockConnect(targetName: string, title: string, company: string): JsonDraft {
  return {
    suggestedText: `Hi ${targetName.split(" ")[0]} — saw your work as ${title} at ${company}. I help GCs and estimators speed up takeoffs. Would be good to connect.`,
  };
}

function mockDm(
  leadName: string,
  trigger: DmTrigger,
  company: string,
  settings: Settings
): JsonDraft {
  const first = leadName.split(" ")[0];
  const triggerLine: Record<DmTrigger, string> = {
    liked_post: "thanks for the like on the estimating post",
    commented: "appreciate the comment on the takeoff thread",
    accepted_connect: "thanks for connecting",
    demo_request: "got your demo request",
    site_visit: "noticed you checked out Mobi",
  };

  return {
    body: [
      `Hi ${first} — ${triggerLine[trigger]}.`,
      "",
      `I work with teams at places like ${company} who need faster quantity takeoffs without adding headcount overnight.`,
      "",
      `If useful, I can walk you through a short sample workflow here: ${settings.ctaUrl}`,
      "",
      "Either way, glad to be connected.",
    ].join("\n"),
  };
}

export async function generatePostDrafts(
  settings: Settings,
  count = 3
): Promise<PostItem[]> {
  const topics = [...POST_TOPICS]
    .sort(() => Math.random() - 0.5)
    .slice(0, count);

  const items: PostItem[] = [];
  for (const topic of topics) {
    const draft = hasOpenAI()
      ? await callOpenAI(
          postSystemPrompt(settings),
          `Write one LinkedIn post about: ${topic}`
        )
      : mockPost(topic, settings);

    const stamp = nowIso();
    items.push({
      id: createId("post"),
      type: "post",
      status: "pending_approval",
      topic: draft.topic || topic,
      body: draft.body || "",
      cta: draft.cta || settings.ctaUrl,
      scheduledFor: null,
      createdAt: stamp,
      updatedAt: stamp,
      aiModel: modelLabel(),
    });
  }
  return items;
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
        JSON.stringify(input)
      )
    : input.kind === "comment"
      ? mockComment(input.targetName, input.sourcePostSummary)
      : mockConnect(input.targetName, input.targetTitle, input.targetCompany);

  const stamp = nowIso();
  return {
    id: createId("eng"),
    type: "engage",
    kind: input.kind,
    status: "pending_approval",
    targetName: input.targetName,
    targetTitle: input.targetTitle,
    targetCompany: input.targetCompany,
    sourcePostSummary: input.sourcePostSummary,
    suggestedText: draft.suggestedText || "",
    createdAt: stamp,
    updatedAt: stamp,
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
    ? await callOpenAI(dmSystemPrompt(settings), JSON.stringify(input))
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
    body: draft.body || "",
    createdAt: stamp,
    updatedAt: stamp,
    aiModel: modelLabel(),
  };
}

export function aiMode(): "openai" | "mock" {
  return hasOpenAI() ? "openai" : "mock";
}

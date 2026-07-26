export type ItemStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "scheduled"
  | "published"
  | "sent"
  | "rejected"
  | "skipped";

export type PostItem = {
  id: string;
  type: "post";
  status: ItemStatus;
  topic: string;
  body: string;
  cta: string;
  scheduledFor: string | null;
  createdAt: string;
  updatedAt: string;
  aiModel: string;
  notes?: string;
  /**
   * Internal: identifies the in-flight publish attempt that atomically claimed
   * this post (pending_approval → approved). Cleared once the attempt resolves.
   * Not shown in the UI.
   */
  publishToken?: string;
};

export type EngageKind = "comment" | "connect";

export type EngageItem = {
  id: string;
  type: "engage";
  kind: EngageKind;
  status: ItemStatus;
  targetName: string;
  targetTitle: string;
  targetCompany: string;
  sourcePostSummary: string;
  suggestedText: string;
  createdAt: string;
  updatedAt: string;
  aiModel: string;
};

export type DmTrigger =
  | "liked_post"
  | "commented"
  | "accepted_connect"
  | "demo_request"
  | "site_visit";

export type DmItem = {
  id: string;
  type: "dm";
  status: ItemStatus;
  leadName: string;
  leadTitle: string;
  leadCompany: string;
  trigger: DmTrigger;
  body: string;
  createdAt: string;
  updatedAt: string;
  aiModel: string;
};

export type Settings = {
  brandVoice: string;
  icpKeywords: string[];
  dailyConnectCap: number;
  dailyCommentCap: number;
  dailyDmCap: number;
  doNotContact: string[];
  ctaUrl: string;
  companyName: string;
};

export type StoreData = {
  settings: Settings;
  posts: PostItem[];
  engage: EngageItem[];
  dms: DmItem[];
};

export type QueueKind = "posts" | "engage" | "dms";

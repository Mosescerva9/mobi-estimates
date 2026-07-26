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
  /**
   * Validated LinkedIn post URL for an assisted comment. Optional and
   * backward-compatible: older items (and connection notes) may not have one.
   */
  sourcePostUrl?: string;
  /**
   * Set when the owner confirms they posted the comment on LinkedIn (the item
   * moves to the existing `sent` status). Absent until then.
   */
  completedAt?: string;
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

/**
 * Lifecycle of a candidate captured by the iPhone Safari Scout extension.
 *  - collected : captured from the visible feed, not yet processed by Hermes.
 *  - queued    : Hermes qualified it and it produced exactly one pending
 *                EngageItem now awaiting the owner's approval.
 *  - skipped   : Hermes decided not to comment (whitelisted reason).
 *  - rejected  : the owner dismissed it from the Scout list.
 *  - failed    : a processing/audit error was recorded for this candidate.
 */
export type ScoutCandidateStatus =
  | "collected"
  | "queued"
  | "skipped"
  | "rejected"
  | "failed";

/**
 * A single LinkedIn feed post the owner captured with the Safari extension.
 * Only non-secret, human-visible fields are stored — no cookies, no tokens.
 */
export type ScoutCandidate = {
  id: string;
  type: "scout";
  status: ScoutCandidateStatus;
  /** Canonical, validated LinkedIn post permalink. */
  postUrl: string;
  /** Normalized dedupe key derived from postUrl (host + path). */
  postKey: string;
  /** Visible post text/excerpt used to ground a recommendation. */
  sourceText: string;
  authorName?: string;
  authorHeadline?: string;
  authorCompany?: string;
  capturedAt: string;
  updatedAt: string;
  /** Populated by the Hermes job when it processes the candidate. */
  relevance?: number;
  safety?: string;
  reason?: string;
  model?: string;
  suggestedComment?: string;
  /** The batch run id that last processed this candidate. */
  batchId?: string;
  /** The EngageItem this candidate produced, once queued. */
  engageItemId?: string;
};

/**
 * Non-secret Scout pairing state. The capture token itself is NEVER stored;
 * only a domain-separated SHA-256 hash is kept, and even that hash is never
 * returned by owner list/status APIs. `tokenLast4` and the timestamps are safe
 * to show so the owner can recognise which code is active.
 */
export type ScoutState = {
  captureTokenHash?: string;
  captureTokenLast4?: string;
  captureTokenUpdatedAt?: string;
};

export type StoreData = {
  settings: Settings;
  posts: PostItem[];
  engage: EngageItem[];
  dms: DmItem[];
  scout: ScoutState;
  scoutCandidates: ScoutCandidate[];
};

export type QueueKind = "posts" | "engage" | "dms";

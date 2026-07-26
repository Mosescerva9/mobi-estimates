"use client";

import { useEffect, useState, useTransition } from "react";
import { charCount, wordCount } from "@/lib/content-quality";
import { engageStatusLabel } from "@/lib/engage";
import { DAILY_GUIDE } from "@/lib/guide";
import { validateLinkedInPostUrl } from "@/lib/linkedin-url";
import { navigateOpenedTab, type OpenedTab } from "@/lib/open-post";
import { POST_ANGLES } from "@/lib/prompts";
import type { DmItem, EngageItem, EngageKind, PostItem, Settings } from "@/lib/types";
import { StatusPill } from "./StatusPill";

type Tab = "queue" | "posts" | "engage" | "scout" | "dms" | "settings" | "help";

type ScoutCandidateView = {
  id: string;
  status: string;
  postUrl: string;
  sourceText: string;
  authorName?: string;
  authorHeadline?: string;
  authorCompany?: string;
  capturedAt: string;
  updatedAt: string;
  relevance?: number;
  reason?: string;
  safety?: string;
  suggestedComment?: string;
  engageItemId?: string;
};

type ScoutPayload = {
  counts: {
    collected: number;
    queued: number;
    skipped: number;
    rejected: number;
    failed: number;
    total: number;
  };
  candidates: ScoutCandidateView[];
  pairing: { paired: boolean; last4: string | null; updatedAt: string | null };
  jobConfigured: boolean;
};

type NewPairing = { token: string; warning: string } | null;

type StatusPayload = {
  app: string;
  aiMode: "openai" | "mock";
  authRequired: boolean;
  linkedinConfigured: boolean;
  pending: { posts: number; engage: number; dms: number };
  settings: Settings;
};

type CopyHint = { ok: boolean; text: string; note: string } | null;

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (res.status === 401 && !url.startsWith("/api/auth/")) {
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = (data as { error?: unknown })?.error;
    const message =
      typeof err === "string"
        ? err
        : (err as { formErrors?: string[] })?.formErrors?.[0] ||
          "Something went wrong. Please try again.";
    throw new Error(message);
  }
  return data as T;
}

const TABS: [Tab, string][] = [
  ["queue", "Today"],
  ["posts", "Posts"],
  ["engage", "Engage"],
  ["scout", "Scout"],
  ["dms", "Warm DMs"],
  ["settings", "Settings"],
  ["help", "Help"],
];

export function Dashboard() {
  const [tab, setTab] = useState<Tab>("queue");
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [posts, setPosts] = useState<PostItem[]>([]);
  const [engage, setEngage] = useState<EngageItem[]>([]);
  const [dms, setDms] = useState<DmItem[]>([]);
  const [scout, setScout] = useState<ScoutPayload | null>(null);
  const [newPairing, setNewPairing] = useState<NewPairing>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copyHint, setCopyHint] = useState<CopyHint>(null);
  const [loading, setLoading] = useState(true);
  const [busy, startTransition] = useTransition();

  async function refresh() {
    const [s, p, e, d, sc] = await Promise.all([
      api<StatusPayload>("/api/status"),
      api<{ items: PostItem[] }>("/api/posts"),
      api<{ items: EngageItem[] }>("/api/engage"),
      api<{ items: DmItem[] }>("/api/dms"),
      api<ScoutPayload>("/api/scout"),
    ]);
    setStatus(s);
    setPosts(p.items);
    setEngage(e.items);
    setDms(d.items);
    setScout(sc);
    setSettings(s.settings);
  }

  useEffect(() => {
    refresh()
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  function run(label: string, fn: () => Promise<string | void>) {
    setError(null);
    setMessage(null);
    startTransition(() => {
      void (async () => {
        try {
          const custom = await fn();
          setMessage(custom || label);
          await refresh();
        } catch (err) {
          setError(err instanceof Error ? err.message : "Something went wrong.");
        }
      })();
    });
  }

  /** Approve engage/DM: persist the latest typed text, approve, then copy it. */
  async function approveAndCopy(
    url: string,
    field: "suggestedText" | "body",
    text: string,
    kind: "note" | "DM"
  ): Promise<string> {
    await api(url, {
      method: "PATCH",
      body: JSON.stringify({ action: "edit", [field]: text }),
    });
    await api(url, { method: "PATCH", body: JSON.stringify({ action: "approve" }) });
    const ok = await copyText(text);
    setCopyHint({
      ok,
      text,
      note: ok
        ? "Copied to your clipboard. Paste it into LinkedIn."
        : "Automatic copy was blocked by your browser. Use the Copy button below, then paste into LinkedIn.",
    });
    return ok
      ? `Approved — ${kind} copied. Paste it into LinkedIn.`
      : `Approved. Copy the ${kind} below and paste it into LinkedIn.`;
  }

  /**
   * Approve a comment: persist the latest typed text, approve, copy it, then
   * navigate the tab that was opened synchronously on the click (see
   * openBlankTab) to the exact validated post. If approval fails (including a
   * post-target mismatch rejected by the server), the blank tab is closed and we
   * copy/navigate nothing. We drive the copy and navigation off the server's
   * returned item, never the client's pre-request values, so both match exactly
   * what the server approved.
   */
  async function approveCommentAndOpen(
    url: string,
    text: string,
    sourcePostUrl: string | undefined,
    tab: OpenedTab | null
  ): Promise<string> {
    let approved: EngageItem;
    try {
      // One atomic PATCH: approve the exact text we are about to copy and bind
      // the approval to the post URL this client is showing, so a concurrent
      // edit or URL repair can't leave the copied text or opened post out of
      // sync with what the server approved.
      const res = await api<{ item: EngageItem }>(url, {
        method: "PATCH",
        body: JSON.stringify({
          action: "approve",
          suggestedText: text,
          sourcePostUrl,
        }),
      });
      approved = res.item;
    } catch (err) {
      if (tab) tab.close();
      throw err;
    }

    const approvedText = approved.suggestedText;
    const copied = await copyText(approvedText);
    const opened = navigateOpenedTab(tab, approved.sourcePostUrl);
    setCopyHint({
      ok: copied,
      text: approvedText,
      note: copied
        ? "Comment copied. Paste it into the LinkedIn post and click Post."
        : "Automatic copy was blocked. Use “Copy again” below, then paste it into LinkedIn.",
    });

    if (copied && opened) return "Comment copied. LinkedIn opened. Paste it and click Post.";
    if (copied) return "Comment copied. Open the post, paste it, and click Post.";
    if (opened) return "LinkedIn opened. Use “Copy again”, then paste it and click Post.";
    return "Approved. Use “Copy again” and “Open post”, then paste it and click Post.";
  }

  const pendingPosts = posts.filter((p) => p.status === "pending_approval");
  const pendingEngage = engage.filter((e) => e.status === "pending_approval");
  const pendingDms = dms.filter((d) => d.status === "pending_approval");
  const approvedDms = dms.filter((d) => d.status === "approved");
  const queueCount =
    pendingPosts.length + pendingEngage.length + pendingDms.length + approvedDms.length;

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 md:px-8 md:py-12">
      <header className="rise mb-6 flex flex-col gap-4 border-b border-steel-200 pb-6 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-blueprint">
            Mobi Estimating
          </p>
          <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight text-steel-900 md:text-4xl">
            LinkedIn Control Panel
          </h1>
          <p className="mt-2 max-w-xl text-steel-700">
            The assistant writes the drafts. You review and approve. Nothing is posted
            or sent until you say so.
          </p>
        </div>
        <div className="panel rise-delay-1 px-4 py-3 text-sm">
          <div className="text-steel-900">
            Writing mode:{" "}
            <strong>
              {status ? (status.aiMode === "openai" ? "AI (OpenAI)" : "Built-in") : "…"}
            </strong>
          </div>
          <div className="mt-1 text-steel-900">
            Posting:{" "}
            <strong>
              {status
                ? status.linkedinConfigured
                  ? "Connected to LinkedIn"
                  : "Draft only (dry run)"
                : "…"}
            </strong>
          </div>
          <div className="mt-1 text-steel-700">
            {status
              ? `${queueCount} item${queueCount === 1 ? "" : "s"} waiting for you`
              : "Loading your queue…"}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => {
                setTab("posts");
                postHandlers().onGenerate();
              }}
            >
              Create today&apos;s posts
            </button>
            {status?.authRequired && (
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() =>
                  run("Signed out.", async () => {
                    await api("/api/auth/logout", { method: "POST" });
                    window.location.href = "/login";
                  })
                }
              >
                Sign out
              </button>
            )}
          </div>
        </div>
      </header>

      <nav className="rise-delay-1 mb-6 flex flex-wrap gap-2">
        {TABS.map(([id, label]) => {
          const badge =
            id === "queue" && queueCount > 0 ? ` (${queueCount})` : "";
          return (
            <button
              key={id}
              type="button"
              className={`btn ${tab === id ? "btn-primary" : ""}`}
              onClick={() => {
                setTab(id);
                setCopyHint(null);
              }}
            >
              {label}
              {badge}
            </button>
          );
        })}
      </nav>

      {copyHint && (
        <div
          className={`mb-4 border-l-4 px-4 py-3 ${
            copyHint.ok
              ? "border-blueprint bg-blueprint-soft"
              : "border-signal bg-signal-soft"
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-display text-base font-semibold text-steel-900">
              {copyHint.ok ? "✓ Paste this into LinkedIn" : "Copy this into LinkedIn"}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn"
                onClick={() =>
                  void copyText(copyHint.text).then((ok) =>
                    setCopyHint({ ...copyHint, ok })
                  )
                }
              >
                Copy again
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => setCopyHint(null)}
              >
                Dismiss
              </button>
            </div>
          </div>
          <p className="mt-1 text-sm text-steel-700">{copyHint.note}</p>
          <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap border border-steel-200 bg-white p-3 text-sm text-steel-900">
            {copyHint.text}
          </pre>
        </div>
      )}

      {(message || error) && (
        <div
          className={`mb-4 border px-4 py-3 text-sm ${
            error
              ? "border-red-300 bg-red-50 text-red-900"
              : "border-blueprint/30 bg-blueprint-soft text-blueprint-dark"
          }`}
        >
          {error || message}
        </div>
      )}

      {loading && (
        <div className="panel p-6 text-steel-700">Loading your queue…</div>
      )}

      {!loading && tab === "queue" && (
        <QueuePanel
          pendingPosts={pendingPosts}
          pendingEngage={pendingEngage}
          pendingDms={pendingDms}
          approvedDms={approvedDms}
          busy={busy}
          onGoToPosts={() => setTab("posts")}
          postHandlers={postHandlers()}
          engageHandlers={engageHandlers()}
          dmHandlers={dmHandlers()}
        />
      )}

      {!loading && tab === "posts" && (
        <PostsPanel posts={posts} busy={busy} handlers={postHandlers()} />
      )}

      {!loading && tab === "engage" && (
        <EngagePanel items={engage} busy={busy} handlers={engageHandlers()} />
      )}

      {!loading && tab === "scout" && (
        <ScoutPanel
          scout={scout}
          newPairing={newPairing}
          busy={busy}
          handlers={scoutHandlers()}
        />
      )}

      {!loading && tab === "dms" && (
        <DmPanel items={dms} busy={busy} handlers={dmHandlers()} />
      )}

      {!loading && tab === "settings" && settings && (
        <SettingsPanel
          settings={settings}
          busy={busy}
          onSave={(next) =>
            run("Settings saved.", async () => {
              await api("/api/settings", {
                method: "PATCH",
                body: JSON.stringify(next),
              });
            })
          }
        />
      )}

      {!loading && tab === "help" && <HelpPanel />}
    </main>
  );

  function postHandlers(): PostHandlers {
    return {
      onGenerate: (angle) =>
        run("Created 3 sharper post drafts.", async () => {
          await api("/api/posts/generate", {
            method: "POST",
            body: JSON.stringify({ count: 3, angle: angle || undefined }),
          });
        }),
      onEdit: (id, body) =>
        run("Saved your edit.", async () => {
          await api(`/api/posts/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "edit", body }),
          });
        }),
      onApprove: (id, body) =>
        run("Post approved.", async () => {
          await api(`/api/posts/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "edit", body }),
          });
          const res = await api<{ item: PostItem }>(`/api/posts/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "approve" }),
          });
          return res.item?.notes || "Post approved and published.";
        }),
      onReject: (id) =>
        run("Post rejected.", async () => {
          await api(`/api/posts/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "reject" }),
          });
        }),
      onRegenerate: (id, instruction) =>
        run("Rewrote the draft. Review it before approving.", async () => {
          await api(`/api/posts/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "regenerate", instruction }),
          });
        }),
    };
  }

  function engageHandlers(): EngageHandlers {
    return {
      onCreate: (payload) =>
        run("Drafted a new suggestion.", async () => {
          await api("/api/engage", {
            method: "POST",
            body: JSON.stringify(payload),
          });
        }),
      onEdit: (id, text) =>
        run("Saved your edit.", async () => {
          await api(`/api/engage/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "edit", suggestedText: text }),
          });
        }),
      onApprove: (id, text, kind, sourcePostUrl, tab) =>
        run("Approved.", () =>
          kind === "comment"
            ? approveCommentAndOpen(
                `/api/engage/${id}`,
                text,
                sourcePostUrl,
                tab ?? null
              )
            : approveAndCopy(`/api/engage/${id}`, "suggestedText", text, "note")
        ),
      onMarkCommented: (id) =>
        run("Marked as commented.", async () => {
          await api(`/api/engage/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "mark_commented" }),
          });
        }),
      onSetUrl: (id, url) =>
        run("Saved the post link.", async () => {
          await api(`/api/engage/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "set_source_url", sourcePostUrl: url }),
          });
        }),
      onCopy: (text) => {
        void copyText(text).then((ok) =>
          setCopyHint({
            ok,
            text,
            note: ok
              ? "Copied to your clipboard. Paste it into LinkedIn."
              : "Automatic copy was blocked. Use the Copy button below.",
          })
        );
      },
      onReject: (id) =>
        run("Rejected.", async () => {
          await api(`/api/engage/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "reject" }),
          });
        }),
      onSkip: (id) =>
        run("Skipped.", async () => {
          await api(`/api/engage/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "skip" }),
          });
        }),
      onRegenerate: (id, instruction) =>
        run("Rewrote the suggestion.", async () => {
          await api(`/api/engage/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "regenerate", instruction }),
          });
        }),
    };
  }

  function dmHandlers(): DmHandlers {
    return {
      onCreate: (payload) =>
        run("Drafted a warm DM.", async () => {
          await api("/api/dms", { method: "POST", body: JSON.stringify(payload) });
        }),
      onEdit: (id, text) =>
        run("Saved your edit.", async () => {
          await api(`/api/dms/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "edit", body: text }),
          });
        }),
      onApprove: (id, text) =>
        run("Approved.", () =>
          approveAndCopy(`/api/dms/${id}`, "body", text, "DM")
        ),
      onReject: (id) =>
        run("Rejected.", async () => {
          await api(`/api/dms/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "reject" }),
          });
        }),
      onMarkSent: (id) =>
        run("Marked as sent.", async () => {
          await api(`/api/dms/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "mark_sent" }),
          });
        }),
      onCopy: (text) => {
        void copyText(text).then((ok) =>
          setCopyHint({
            ok,
            text,
            note: ok
              ? "Copied to your clipboard. Paste it into LinkedIn."
              : "Automatic copy was blocked. Use the Copy button below.",
          })
        );
      },
      onRegenerate: (id, instruction) =>
        run("Rewrote the warm DM.", async () => {
          await api(`/api/dms/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "regenerate", instruction }),
          });
        }),
    };
  }

  function scoutHandlers(): ScoutHandlers {
    const rotating = Boolean(scout?.pairing.paired);
    return {
      onPair: () =>
        run(
          "New pairing code created. Copy it now — it is shown only once.",
          async () => {
            const res = await api<{ token: string; warning: string }>(
              "/api/scout/pairing",
              {
                method: "POST",
                body: JSON.stringify({ action: rotating ? "rotate" : "create" }),
              }
            );
            setNewPairing({ token: res.token, warning: res.warning });
            return rotating
              ? "New code created. Your old code stopped working — re-pair Safari with the new one."
              : "Pairing code created. Copy it into the Safari extension now.";
          }
        ),
      onRevoke: () =>
        run("Pairing turned off.", async () => {
          await api("/api/scout/pairing", { method: "DELETE" });
          setNewPairing(null);
        }),
      onReject: (id) =>
        run("Removed from Scout.", async () => {
          await api(`/api/scout/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "reject" }),
          });
        }),
      onDismissToken: () => setNewPairing(null),
      onCopyToken: (token) => {
        void copyText(token).then((ok) =>
          setCopyHint({
            ok,
            text: token,
            note: ok
              ? "Copied. Paste it into the Safari extension’s pairing field."
              : "Automatic copy was blocked. Select the code above and copy it by hand.",
          })
        );
      },
    };
  }
}

/* --------------------------------------------------------------- handlers */

type PostHandlers = {
  onGenerate: (angle?: string) => void;
  onEdit: (id: string, body: string) => void;
  onApprove: (id: string, body: string) => void;
  onReject: (id: string) => void;
  onRegenerate: (id: string, instruction?: string) => void;
};

type ScoutHandlers = {
  onPair: () => void;
  onRevoke: () => void;
  onReject: (id: string) => void;
  onDismissToken: () => void;
  onCopyToken: (token: string) => void;
};

type EngageHandlers = {
  onCreate: (payload: Record<string, string>) => void;
  onEdit: (id: string, text: string) => void;
  onApprove: (
    id: string,
    text: string,
    kind: EngageKind,
    sourcePostUrl?: string,
    tab?: OpenedTab | null
  ) => void;
  onMarkCommented: (id: string) => void;
  onSetUrl: (id: string, url: string) => void;
  onCopy: (text: string) => void;
  onReject: (id: string) => void;
  onSkip: (id: string) => void;
  onRegenerate: (id: string, instruction?: string) => void;
};

/**
 * Open a blank tab synchronously inside a click handler so the later
 * navigation (after an awaited approval) is not treated as a blocked popup.
 * Sever `opener` for rel="noopener" safety once we hold the handle.
 */
function openBlankTab(): OpenedTab | null {
  if (typeof window === "undefined") return null;
  const tab = window.open("about:blank", "_blank");
  if (tab) {
    try {
      tab.opener = null;
    } catch {
      /* some browsers disallow setting opener; the tab is still ours to drive */
    }
  }
  return tab as OpenedTab | null;
}

/** Client-side safe href for a stored post URL, or null if it does not validate. */
function safePostHref(url: string | undefined): string | null {
  const check = validateLinkedInPostUrl(url);
  return check.ok ? check.url : null;
}

type DmHandlers = {
  onCreate: (payload: Record<string, string>) => void;
  onEdit: (id: string, text: string) => void;
  onApprove: (id: string, text: string) => void;
  onReject: (id: string) => void;
  onMarkSent: (id: string) => void;
  onCopy: (text: string) => void;
  onRegenerate: (id: string, instruction?: string) => void;
};

/* ------------------------------------------------------------------ cards */

function PostCard({
  post,
  busy,
  handlers,
}: {
  post: PostItem;
  busy: boolean;
  handlers: PostHandlers;
}) {
  const [body, setBody] = useState(post.body);
  useEffect(() => {
    setBody(post.body);
  }, [post.id, post.body, post.updatedAt]);

  const words = wordCount(body);
  const lengthHint =
    words < 90
      ? "A bit short — consider adding one concrete detail."
      : words > 220
        ? "A bit long for LinkedIn — trim if you can."
        : "Good length for LinkedIn.";

  return (
    <article className="panel p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-display text-lg font-semibold">{post.topic}</h3>
        <StatusPill status={post.status} />
      </div>
      <textarea
        className="field min-h-40"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onBlur={(event) => {
          if ((event.relatedTarget as HTMLElement | null)?.closest("button")) return;
          if (body !== post.body) handlers.onEdit(post.id, body);
        }}
      />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-sm text-steel-700">
        <p>
          {words} words · {lengthHint}
        </p>
        <p className="font-mono text-xs">Operator note: {post.cta}</p>
      </div>
      {post.status === "pending_approval" && (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => handlers.onApprove(post.id, body)}
          >
            Approve &amp; publish
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() =>
              handlers.onRegenerate(
                post.id,
                "Make the hook sharper and more specific to estimating."
              )
            }
          >
            Rewrite sharper
          </button>
          <button
            type="button"
            className="btn btn-danger"
            disabled={busy}
            onClick={() => handlers.onReject(post.id)}
          >
            Reject
          </button>
        </div>
      )}
      {post.notes && <p className="mt-3 text-sm text-blueprint-dark">{post.notes}</p>}
    </article>
  );
}

function EngageCard({
  item,
  busy,
  handlers,
}: {
  item: EngageItem;
  busy: boolean;
  handlers: EngageHandlers;
}) {
  const [text, setText] = useState(item.suggestedText);
  useEffect(() => {
    setText(item.suggestedText);
  }, [item.id, item.suggestedText, item.updatedAt]);
  const [urlDraft, setUrlDraft] = useState(item.sourcePostUrl ?? "");
  useEffect(() => {
    setUrlDraft(item.sourcePostUrl ?? "");
  }, [item.id, item.sourcePostUrl, item.updatedAt]);

  const chars = charCount(text);
  const limit = item.kind === "connect" ? 300 : 300;
  const over = chars > limit;
  const isComment = item.kind === "comment";
  const isPending = item.status === "pending_approval";
  const postHref = isComment ? safePostHref(item.sourcePostUrl) : null;
  // A pending comment with no valid stored URL (a legacy capture) can't be
  // approved until the owner supplies one. Show the repair field, not Approve.
  const needsUrlRepair = isComment && isPending && !postHref;

  return (
    <article className="panel p-5">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-display text-lg font-semibold">
            {isComment ? "Comment" : "Connection note"} · {item.targetName}
          </h3>
          <p className="text-sm text-steel-700">
            {item.targetTitle} @ {item.targetCompany}
          </p>
        </div>
        <StatusPill status={item.status} label={engageStatusLabel(item)} />
      </div>
      <p className="mb-2 whitespace-pre-wrap text-sm text-steel-700">
        {item.sourcePostSummary}
      </p>
      {postHref && (
        <p className="mb-2">
          <a
            className="btn"
            href={postHref}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open LinkedIn post ↗
          </a>
        </p>
      )}
      <textarea
        className="field min-h-28"
        value={text}
        readOnly={!isPending}
        onChange={(e) => setText(e.target.value)}
        onBlur={(event) => {
          // Approved/sent text is immutable — never fire a blur-save once the
          // item has left pending.
          if (!isPending) return;
          if ((event.relatedTarget as HTMLElement | null)?.closest("button")) return;
          if (text !== item.suggestedText) handlers.onEdit(item.id, text);
        }}
      />
      <p className={`mt-2 text-sm ${over ? "text-red-800" : "text-steel-700"}`}>
        {chars}/{limit} characters
        {over ? " — trim before sending on LinkedIn." : ""}
      </p>
      {isPending && (
        <div className="mt-4 space-y-3">
          {needsUrlRepair && (
            <div className="border-l-4 border-signal bg-signal-soft px-3 py-3">
              <label className="block text-sm text-steel-900">
                Add the LinkedIn post URL to approve this comment
                <input
                  className="field mt-1"
                  type="url"
                  placeholder="https://www.linkedin.com/posts/…"
                  value={urlDraft}
                  onChange={(e) => setUrlDraft(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="btn btn-primary mt-2"
                disabled={busy || !urlDraft.trim()}
                onClick={() => handlers.onSetUrl(item.id, urlDraft.trim())}
              >
                Save post link
              </button>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {isComment ? (
              // No Approve path until a valid post URL is stored.
              postHref && (
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => {
                    // Open the blank tab now, inside the click gesture, so the
                    // post-approval navigation is not blocked as a popup.
                    const tab = openBlankTab();
                    handlers.onApprove(item.id, text, item.kind, item.sourcePostUrl, tab);
                  }}
                >
                  Approve &amp; open post
                </button>
              )
            ) : (
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => handlers.onApprove(item.id, text, item.kind)}
              >
                Approve &amp; copy
              </button>
            )}
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() =>
                handlers.onRegenerate(
                  item.id,
                  isComment
                    ? "Make it more specific and less complimentary."
                    : "Make it shorter and more personal, under 280 characters."
                )
              }
            >
              Rewrite
            </button>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => handlers.onSkip(item.id)}
            >
              Skip
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy}
              onClick={() => handlers.onReject(item.id)}
            >
              Reject
            </button>
          </div>
        </div>
      )}
      {isComment && item.status === "approved" && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-sm text-steel-700">
            Paste it into the LinkedIn post and click Post, then:
          </span>
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => handlers.onCopy(text)}
          >
            Copy again
          </button>
          {postHref && (
            <a className="btn" href={postHref} target="_blank" rel="noopener noreferrer">
              Open post ↗
            </a>
          )}
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => handlers.onMarkCommented(item.id)}
          >
            Mark commented
          </button>
        </div>
      )}
    </article>
  );
}

function DmCard({
  item,
  busy,
  handlers,
}: {
  item: DmItem;
  busy: boolean;
  handlers: DmHandlers;
}) {
  const [text, setText] = useState(item.body);
  useEffect(() => {
    setText(item.body);
  }, [item.id, item.body, item.updatedAt]);

  return (
    <article className="panel p-5">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-display text-lg font-semibold">{item.leadName}</h3>
          <p className="text-sm text-steel-700">
            {item.leadTitle} @ {item.leadCompany} · {item.trigger.replaceAll("_", " ")}
          </p>
        </div>
        <StatusPill status={item.status} />
      </div>
      <textarea
        className="field min-h-36"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={(event) => {
          if ((event.relatedTarget as HTMLElement | null)?.closest("button")) return;
          if (text !== item.body) handlers.onEdit(item.id, text);
        }}
      />
      <p className="mt-2 text-sm text-steel-700">{wordCount(text)} words</p>
      {item.status === "pending_approval" && (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => handlers.onApprove(item.id, text)}
          >
            Approve &amp; copy
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() =>
              handlers.onRegenerate(
                item.id,
                "Make it warmer, shorter, and clearly tied to their trigger."
              )
            }
          >
            Rewrite
          </button>
          <button
            type="button"
            className="btn btn-danger"
            disabled={busy}
            onClick={() => handlers.onReject(item.id)}
          >
            Reject
          </button>
        </div>
      )}
      {item.status === "approved" && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-sm text-steel-700">
            Paste it into LinkedIn, then:
          </span>
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => handlers.onCopy(text)}
          >
            Copy again
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => handlers.onMarkSent(item.id)}
          >
            Mark sent
          </button>
        </div>
      )}
    </article>
  );
}

/* ----------------------------------------------------------------- panels */

function QueuePanel({
  pendingPosts,
  pendingEngage,
  pendingDms,
  approvedDms,
  busy,
  onGoToPosts,
  postHandlers,
  engageHandlers,
  dmHandlers,
}: {
  pendingPosts: PostItem[];
  pendingEngage: EngageItem[];
  pendingDms: DmItem[];
  approvedDms: DmItem[];
  busy: boolean;
  onGoToPosts: () => void;
  postHandlers: PostHandlers;
  engageHandlers: EngageHandlers;
  dmHandlers: DmHandlers;
}) {
  const total =
    pendingPosts.length +
    pendingEngage.length +
    pendingDms.length +
    approvedDms.length;

  if (total === 0) {
    return (
      <section className="rise-delay-2 space-y-4">
        <h2 className="font-display text-xl font-semibold">Today&apos;s queue</h2>
        <div className="panel p-6">
          <p className="font-display text-lg font-semibold text-steel-900">
            You&apos;re all caught up
          </p>
          <p className="mt-2 text-steel-700">
            Nothing is waiting for approval. Create 3 fresh estimating posts for today.
          </p>
          <button
            type="button"
            className="btn btn-primary mt-4"
            disabled={busy}
            onClick={() => {
              onGoToPosts();
              postHandlers.onGenerate();
            }}
          >
            Create today&apos;s posts
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="rise-delay-2 space-y-8">
      <div>
        <h2 className="font-display text-xl font-semibold">Today&apos;s queue</h2>
        <p className="text-sm text-steel-700">
          Work top to bottom. Posts first, then comments and connections, then warm DMs.
        </p>
      </div>

      {pendingPosts.length > 0 && (
        <div className="space-y-4">
          <h3 className="font-mono text-xs uppercase tracking-wide text-blueprint">
            Posts to approve ({pendingPosts.length})
          </h3>
          {pendingPosts.map((p) => (
            <PostCard key={p.id} post={p} busy={busy} handlers={postHandlers} />
          ))}
        </div>
      )}

      {pendingEngage.length > 0 && (
        <div className="space-y-4">
          <h3 className="font-mono text-xs uppercase tracking-wide text-blueprint">
            Comments &amp; connections ({pendingEngage.length})
          </h3>
          {pendingEngage.map((e) => (
            <EngageCard key={e.id} item={e} busy={busy} handlers={engageHandlers} />
          ))}
        </div>
      )}

      {(pendingDms.length > 0 || approvedDms.length > 0) && (
        <div className="space-y-4">
          <h3 className="font-mono text-xs uppercase tracking-wide text-blueprint">
            Warm DMs ({pendingDms.length + approvedDms.length})
          </h3>
          {[...pendingDms, ...approvedDms].map((d) => (
            <DmCard key={d.id} item={d} busy={busy} handlers={dmHandlers} />
          ))}
        </div>
      )}
    </section>
  );
}

function PostsPanel({
  posts,
  busy,
  handlers,
}: {
  posts: PostItem[];
  busy: boolean;
  handlers: PostHandlers;
}) {
  const [angle, setAngle] = useState("");
  const [pendingOnly, setPendingOnly] = useState(true);
  const ordered = [...posts]
    .filter((p) => !pendingOnly || p.status === "pending_approval")
    .sort((a, b) => rankStatus(a.status) - rankStatus(b.status));

  return (
    <section className="rise-delay-2 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-semibold">Posts</h2>
          <p className="text-sm text-steel-700">
            Pick an angle, generate drafts, rewrite anything weak, then approve.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-sm">
            Angle
            <select
              className="field mt-1 min-w-56"
              value={angle}
              onChange={(e) => setAngle(e.target.value)}
            >
              <option value="">Mix best angles</option>
              {POST_ANGLES.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => handlers.onGenerate(angle || undefined)}
          >
            Create 3 drafts
          </button>
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm text-steel-700">
        <input
          type="checkbox"
          checked={pendingOnly}
          onChange={(e) => setPendingOnly(e.target.checked)}
        />
        Show only drafts waiting for approval
      </label>

      {ordered.length === 0 && (
        <div className="panel p-6 text-steel-700">
          No posts in this view. Click <strong>Create 3 drafts</strong> to generate
          estimating content for LinkedIn.
        </div>
      )}

      {ordered.map((post) => (
        <PostCard key={post.id} post={post} busy={busy} handlers={handlers} />
      ))}
    </section>
  );
}

function EngagePanel({
  items,
  busy,
  handlers,
}: {
  items: EngageItem[];
  busy: boolean;
  handlers: EngageHandlers;
}) {
  const [form, setForm] = useState({
    kind: "comment",
    targetName: "",
    targetTitle: "",
    targetCompany: "",
    sourcePostSummary: "",
    sourcePostUrl: "",
  });
  const isComment = form.kind === "comment";
  const ordered = [...items].sort(
    (a, b) => rankStatus(a.status) - rankStatus(b.status)
  );

  return (
    <section className="rise-delay-2 space-y-4">
      <div>
        <h2 className="font-display text-xl font-semibold">Engage</h2>
        <p className="text-sm text-steel-700">
          The assistant drafts comments and connection notes. For a comment, paste the
          real LinkedIn post URL. You approve, the text is copied, and the exact post
          opens so you can paste it and click Post yourself. Mobi never browses the feed
          or submits comments automatically.
        </p>
      </div>

      <form
        className="panel grid gap-3 p-5 md:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          handlers.onCreate(form);
          setForm({
            kind: form.kind,
            targetName: "",
            targetTitle: "",
            targetCompany: "",
            sourcePostSummary: "",
            sourcePostUrl: "",
          });
        }}
      >
        <label className="text-sm">
          Type
          <select
            className="field mt-1"
            value={form.kind}
            onChange={(e) => setForm({ ...form, kind: e.target.value })}
          >
            <option value="comment">Comment on their post</option>
            <option value="connect">Connection note</option>
          </select>
        </label>
        <label className="text-sm">
          Their name
          <input
            className="field mt-1"
            required
            value={form.targetName}
            onChange={(e) => setForm({ ...form, targetName: e.target.value })}
          />
        </label>
        <label className="text-sm">
          Their title
          <input
            className="field mt-1"
            required
            value={form.targetTitle}
            onChange={(e) => setForm({ ...form, targetTitle: e.target.value })}
          />
        </label>
        <label className="text-sm">
          Their company
          <input
            className="field mt-1"
            required
            value={form.targetCompany}
            onChange={(e) => setForm({ ...form, targetCompany: e.target.value })}
          />
        </label>
        {isComment && (
          <label className="text-sm md:col-span-2">
            LinkedIn post URL
            <input
              className="field mt-1"
              type="url"
              required
              placeholder="https://www.linkedin.com/posts/…"
              value={form.sourcePostUrl}
              onChange={(e) => setForm({ ...form, sourcePostUrl: e.target.value })}
            />
          </label>
        )}
        <label className="text-sm md:col-span-2">
          {isComment
            ? "Paste the post text or describe what they shared"
            : "What is this about? (their post or context)"}
          <textarea
            className="field mt-1 min-h-24"
            required
            value={form.sourcePostSummary}
            onChange={(e) => setForm({ ...form, sourcePostSummary: e.target.value })}
          />
        </label>
        <div className="md:col-span-2">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            Draft it for me
          </button>
        </div>
      </form>

      {ordered.length === 0 && (
        <div className="panel p-6 text-steel-700">
          No suggestions yet. Fill in a name and a bit of context above, then click{" "}
          <strong>Draft it for me</strong>.
        </div>
      )}

      {ordered.map((item) => (
        <EngageCard key={item.id} item={item} busy={busy} handlers={handlers} />
      ))}
    </section>
  );
}

function DmPanel({
  items,
  busy,
  handlers,
}: {
  items: DmItem[];
  busy: boolean;
  handlers: DmHandlers;
}) {
  const [form, setForm] = useState({
    leadName: "",
    leadTitle: "",
    leadCompany: "",
    trigger: "liked_post",
  });
  const ordered = [...items].sort(
    (a, b) => rankStatus(a.status) - rankStatus(b.status)
  );

  return (
    <section className="rise-delay-2 space-y-4">
      <div>
        <h2 className="font-display text-xl font-semibold">Warm DMs</h2>
        <p className="text-sm text-steel-700">
          Only for people who already engaged with you or asked for a demo — never cold
          outreach. Approve to copy, paste into LinkedIn, then mark it sent.
        </p>
      </div>

      <form
        className="panel grid gap-3 p-5 md:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          handlers.onCreate(form);
          setForm({
            leadName: "",
            leadTitle: "",
            leadCompany: "",
            trigger: form.trigger,
          });
        }}
      >
        <label className="text-sm">
          Their name
          <input
            className="field mt-1"
            required
            value={form.leadName}
            onChange={(e) => setForm({ ...form, leadName: e.target.value })}
          />
        </label>
        <label className="text-sm">
          What did they do?
          <select
            className="field mt-1"
            value={form.trigger}
            onChange={(e) => setForm({ ...form, trigger: e.target.value })}
          >
            <option value="liked_post">Liked a post</option>
            <option value="commented">Commented</option>
            <option value="accepted_connect">Accepted a connection</option>
            <option value="demo_request">Requested a demo</option>
            <option value="site_visit">Visited the website</option>
          </select>
        </label>
        <label className="text-sm">
          Their title
          <input
            className="field mt-1"
            required
            value={form.leadTitle}
            onChange={(e) => setForm({ ...form, leadTitle: e.target.value })}
          />
        </label>
        <label className="text-sm">
          Their company
          <input
            className="field mt-1"
            required
            value={form.leadCompany}
            onChange={(e) => setForm({ ...form, leadCompany: e.target.value })}
          />
        </label>
        <div className="md:col-span-2">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            Draft warm DM
          </button>
        </div>
      </form>

      {ordered.length === 0 && (
        <div className="panel p-6 text-steel-700">
          No warm DMs yet. Add someone who already engaged with you above, then click{" "}
          <strong>Draft warm DM</strong>.
        </div>
      )}

      {ordered.map((item) => (
        <DmCard key={item.id} item={item} busy={busy} handlers={handlers} />
      ))}
    </section>
  );
}

function SettingsPanel({
  settings,
  busy,
  onSave,
}: {
  settings: Settings;
  busy: boolean;
  onSave: (next: Partial<Settings>) => void;
}) {
  const [form, setForm] = useState(settings);

  useEffect(() => {
    setForm(settings);
  }, [settings]);

  return (
    <section className="rise-delay-2 space-y-4">
      <div>
        <h2 className="font-display text-xl font-semibold">Settings</h2>
        <p className="text-sm text-steel-700">
          Your brand voice, who you want to reach, your link, and how much to do each
          day. Daily caps are reminders for your own pace.
        </p>
      </div>
      <form
        className="panel grid gap-3 p-5"
        onSubmit={(e) => {
          e.preventDefault();
          onSave(form);
        }}
      >
        <label className="text-sm">
          Company name
          <input
            className="field mt-1"
            value={form.companyName}
            onChange={(e) => setForm({ ...form, companyName: e.target.value })}
          />
        </label>
        <label className="text-sm">
          Brand voice (how you want to sound)
          <textarea
            className="field mt-1 min-h-28"
            value={form.brandVoice}
            onChange={(e) => setForm({ ...form, brandVoice: e.target.value })}
          />
        </label>
        <label className="text-sm">
          Who you want to reach (keywords, comma-separated)
          <input
            className="field mt-1"
            value={form.icpKeywords.join(", ")}
            onChange={(e) =>
              setForm({
                ...form,
                icpKeywords: splitList(e.target.value),
              })
            }
          />
        </label>
        <label className="text-sm">
          Your link (call-to-action URL)
          <input
            className="field mt-1"
            value={form.ctaUrl}
            onChange={(e) => setForm({ ...form, ctaUrl: e.target.value })}
          />
        </label>
        <div className="grid gap-3 md:grid-cols-3">
          <label className="text-sm">
            Connections per day
            <input
              type="number"
              className="field mt-1"
              value={form.dailyConnectCap}
              onChange={(e) =>
                setForm({ ...form, dailyConnectCap: Number(e.target.value) })
              }
            />
          </label>
          <label className="text-sm">
            Comments per day
            <input
              type="number"
              className="field mt-1"
              value={form.dailyCommentCap}
              onChange={(e) =>
                setForm({ ...form, dailyCommentCap: Number(e.target.value) })
              }
            />
          </label>
          <label className="text-sm">
            DMs per day
            <input
              type="number"
              className="field mt-1"
              value={form.dailyDmCap}
              onChange={(e) =>
                setForm({ ...form, dailyDmCap: Number(e.target.value) })
              }
            />
          </label>
        </div>
        <label className="text-sm">
          Never contact these people (names, comma-separated)
          <input
            className="field mt-1"
            value={form.doNotContact.join(", ")}
            onChange={(e) =>
              setForm({ ...form, doNotContact: splitList(e.target.value) })
            }
          />
        </label>
        <div>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            Save settings
          </button>
        </div>
      </form>
    </section>
  );
}

const SCOUT_STATUS_LABEL: Record<string, string> = {
  collected: "New",
  queued: "Comment in Engage",
  skipped: "Skipped",
  rejected: "Removed",
  failed: "Needs a look",
};

const SCOUT_SKIP_REASON_LABEL: Record<string, string> = {
  off_topic: "Not about construction",
  sensitive: "Sensitive or controversial",
  low_information: "Too little to say",
  do_not_contact: "On your do-not-contact list",
  duplicate: "Already had one for this post",
  insufficient_text: "Not enough post text",
  invalid_comment: "Draft failed a safety check",
  other: "Skipped",
};

function ScoutPanel({
  scout,
  newPairing,
  busy,
  handlers,
}: {
  scout: ScoutPayload | null;
  newPairing: NewPairing;
  busy: boolean;
  handlers: ScoutHandlers;
}) {
  const counts = scout?.counts;
  const candidates = scout?.candidates ?? [];
  const paired = scout?.pairing.paired ?? false;
  const ordered = [...candidates].sort(
    (a, b) => scoutRank(a.status) - scoutRank(b.status)
  );

  return (
    <section className="rise-delay-2 space-y-4">
      <div>
        <h2 className="font-display text-xl font-semibold">Scout</h2>
        <p className="text-sm text-steel-700">
          Scout collects LinkedIn posts you see on your iPhone so Hermes can draft
          comments for them. On your phone, open LinkedIn in Safari, tap the Mobi Scout
          button while you browse, and it saves the posts you can see. Then message
          Hermes in Telegram: <strong>“Process my LinkedIn batch.”</strong> Any good
          comments show up in <strong>Engage</strong> for you to approve — nothing is ever
          posted for you.
        </p>
      </div>

      {/* Pairing ------------------------------------------------------------- */}
      <div className="panel space-y-3 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="font-display text-lg font-semibold text-steel-900">
              iPhone pairing code
            </h3>
            <p className="text-sm text-steel-700">
              {paired ? (
                <>
                  Paired
                  {scout?.pairing.last4 ? (
                    <>
                      {" "}· code ends in{" "}
                      <span className="font-mono">…{scout.pairing.last4}</span>
                    </>
                  ) : null}
                  {scout?.pairing.updatedAt ? (
                    <> · set {new Date(scout.pairing.updatedAt).toLocaleDateString()}</>
                  ) : null}
                </>
              ) : (
                "Not paired yet. Create a code, then paste it into the Safari extension once."
              )}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={handlers.onPair}
            >
              {paired ? "Create new code" : "Create pairing code"}
            </button>
            {paired && (
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={handlers.onRevoke}
              >
                Turn off pairing
              </button>
            )}
          </div>
        </div>

        {newPairing && (
          <div className="border-l-4 border-signal bg-signal-soft px-4 py-3">
            <p className="font-display text-base font-semibold text-steel-900">
              Copy this pairing code now
            </p>
            <p className="mt-1 text-sm text-steel-700">{newPairing.warning}</p>
            <pre className="mt-2 overflow-auto whitespace-pre-wrap break-all border border-steel-200 bg-white p-3 font-mono text-sm text-steel-900">
              {newPairing.token}
            </pre>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                className="btn"
                onClick={() => handlers.onCopyToken(newPairing.token)}
              >
                Copy code
              </button>
              <button type="button" className="btn" onClick={handlers.onDismissToken}>
                I’ve saved it
              </button>
            </div>
          </div>
        )}

        {scout && !scout.jobConfigured && (
          <p className="text-sm text-steel-700">
            Note: the Hermes worker token isn’t set on the server yet, so batches can’t be
            processed until it is. Captured posts are still saved safely here.
          </p>
        )}
      </div>

      {/* Counts ------------------------------------------------------------- */}
      {counts && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <ScoutCount label="Waiting" value={counts.collected} />
          <ScoutCount label="In Engage" value={counts.queued} />
          <ScoutCount label="Skipped" value={counts.skipped} />
          <ScoutCount label="Removed" value={counts.rejected + counts.failed} />
        </div>
      )}

      {/* Candidates --------------------------------------------------------- */}
      {ordered.length === 0 ? (
        <div className="panel p-6 text-steel-700">
          No captured posts yet. On your iPhone, open LinkedIn in Safari, tap the Mobi
          Scout button while you scroll, and the posts you see will show up here.
        </div>
      ) : (
        ordered.map((c) => (
          <ScoutCard key={c.id} candidate={c} busy={busy} handlers={handlers} />
        ))
      )}
    </section>
  );
}

function ScoutCount({ label, value }: { label: string; value: number }) {
  return (
    <div className="panel p-4 text-center">
      <div className="font-display text-2xl font-semibold text-steel-900">{value}</div>
      <div className="text-xs text-steel-700">{label}</div>
    </div>
  );
}

function ScoutCard({
  candidate,
  busy,
  handlers,
}: {
  candidate: ScoutCandidateView;
  busy: boolean;
  handlers: ScoutHandlers;
}) {
  const statusLabel = SCOUT_STATUS_LABEL[candidate.status] ?? candidate.status;
  const reasonLabel = candidate.reason
    ? SCOUT_SKIP_REASON_LABEL[candidate.reason] ?? candidate.reason
    : null;

  return (
    <article className="panel space-y-3 p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-display text-base font-semibold text-steel-900">
            {candidate.authorName || "LinkedIn author"}
          </h3>
          {(candidate.authorHeadline || candidate.authorCompany) && (
            <p className="text-sm text-steel-700">
              {[candidate.authorHeadline, candidate.authorCompany]
                .filter(Boolean)
                .join(" · ")}
            </p>
          )}
        </div>
        <span className="status-pill">
          <span className={`status-dot ${scoutDotStatus(candidate.status)}`} />
          {statusLabel}
        </span>
      </div>

      <p className="whitespace-pre-wrap border-l-2 border-steel-200 pl-3 text-sm text-steel-700">
        {candidate.sourceText.length > 400
          ? candidate.sourceText.slice(0, 400) + "…"
          : candidate.sourceText}
      </p>

      {candidate.status === "queued" && candidate.suggestedComment && (
        <div className="border-l-4 border-blueprint bg-blueprint-soft px-3 py-2 text-sm">
          <p className="font-semibold text-steel-900">
            Draft comment waiting in Engage
          </p>
          <p className="mt-1 whitespace-pre-wrap text-steel-700">
            {candidate.suggestedComment}
          </p>
        </div>
      )}

      {candidate.status === "skipped" && reasonLabel && (
        <p className="text-sm text-steel-700">Skipped — {reasonLabel}.</p>
      )}

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <a
          className="text-blueprint underline"
          href={candidate.postUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open the post
        </a>
        {candidate.status !== "queued" && (
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => handlers.onReject(candidate.id)}
          >
            Remove
          </button>
        )}
      </div>
    </article>
  );
}

/** Map a Scout status to an existing status-dot colour class. */
function scoutDotStatus(status: string): string {
  switch (status) {
    case "collected":
      return "pending_approval";
    case "queued":
      return "approved";
    case "failed":
      return "rejected";
    case "rejected":
      return "rejected";
    default:
      return "skipped";
  }
}

function scoutRank(status: string): number {
  const order: Record<string, number> = {
    collected: 0,
    queued: 1,
    failed: 2,
    skipped: 3,
    rejected: 4,
  };
  return order[status] ?? 9;
}

function HelpPanel() {
  return (
    <section className="rise-delay-2 space-y-4">
      <div>
        <h2 className="font-display text-xl font-semibold">Your daily routine</h2>
        <p className="text-sm text-steel-700">
          Follow these steps once a day. It usually takes just a few minutes.
        </p>
      </div>
      <ol className="space-y-3">
        {DAILY_GUIDE.map((step) => (
          <li key={step.title} className="panel p-5">
            <h3 className="font-display text-lg font-semibold text-steel-900">
              {step.title}
            </h3>
            <p className="mt-1 text-steel-700">{step.body}</p>
          </li>
        ))}
      </ol>
      <div className="panel p-5">
        <h3 className="font-display text-base font-semibold text-steel-900">
          Good to know
        </h3>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-steel-700">
          <li>Nothing is posted or sent automatically. You approve every item.</li>
          <li>
            Comments, connections, and DMs are copied for you to paste into LinkedIn
            yourself — that keeps your account safe.
          </li>
          <li>
            For a comment, paste the real post URL. <strong>Approve &amp; open post</strong>{" "}
            copies the text and opens that exact post; you paste it, click Post, then{" "}
            <strong>Mark commented</strong>. Mobi never browses the feed or submits
            comments automatically.
          </li>
          <li>
            Direct commenting from inside Mobi would require separately approved LinkedIn
            Community Management API access, which is not enabled.
          </li>
          <li>
            <strong>Scout</strong> only saves posts you can already see when you tap the
            button in Safari. It never scrolls, likes, connects, comments, or runs in the
            background. Its comment ideas always land in Engage for your approval first.
          </li>
          <li>
            If LinkedIn isn&apos;t connected, approving a post saves it as a “dry run” so
            you can copy and post it by hand.
          </li>
          <li>
            Status labels: <strong>Needs approval</strong>, <strong>Approved</strong>,{" "}
            <strong>Published</strong>, <strong>Sent</strong>,{" "}
            <strong>Rejected</strong>.
          </li>
        </ul>
      </div>
    </section>
  );
}

/* ----------------------------------------------------------------- helpers */

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function rankStatus(status: string): number {
  const order: Record<string, number> = {
    pending_approval: 0,
    approved: 1,
    scheduled: 2,
    draft: 3,
    published: 4,
    sent: 5,
    skipped: 6,
    rejected: 7,
  };
  return order[status] ?? 9;
}

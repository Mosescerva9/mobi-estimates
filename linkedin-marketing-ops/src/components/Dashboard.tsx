"use client";

import { useEffect, useState, useTransition } from "react";
import { DAILY_GUIDE } from "@/lib/guide";
import { statusLabel } from "@/lib/status";
import type { DmItem, EngageItem, PostItem, Settings } from "@/lib/types";
import { StatusPill } from "./StatusPill";

type Tab = "queue" | "posts" | "engage" | "dms" | "settings" | "help";

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
  const [settings, setSettings] = useState<Settings | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copyHint, setCopyHint] = useState<CopyHint>(null);
  const [loading, setLoading] = useState(true);
  const [busy, startTransition] = useTransition();

  async function refresh() {
    const [s, p, e, d] = await Promise.all([
      api<StatusPayload>("/api/status"),
      api<{ items: PostItem[] }>("/api/posts"),
      api<{ items: EngageItem[] }>("/api/engage"),
      api<{ items: DmItem[] }>("/api/dms"),
    ]);
    setStatus(s);
    setPosts(p.items);
    setEngage(e.items);
    setDms(d.items);
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
    kind: "comment or note" | "DM"
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
              className="btn"
              disabled={busy}
              onClick={() =>
                run("Added sample drafts to your queue.", async () => {
                  await api("/api/seed", { method: "POST" });
                })
              }
            >
              Add sample drafts
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
      onGenerate: () =>
        run("Created 3 new post drafts.", async () => {
          await api("/api/posts/generate", {
            method: "POST",
            body: JSON.stringify({ count: 3 }),
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
      onApprove: (id, text) =>
        run("Approved.", () =>
          approveAndCopy(
            `/api/engage/${id}`,
            "suggestedText",
            text,
            "comment or note"
          )
        ),
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
    };
  }
}

/* --------------------------------------------------------------- handlers */

type PostHandlers = {
  onGenerate: () => void;
  onEdit: (id: string, body: string) => void;
  onApprove: (id: string, body: string) => void;
  onReject: (id: string) => void;
};

type EngageHandlers = {
  onCreate: (payload: Record<string, string>) => void;
  onEdit: (id: string, text: string) => void;
  onApprove: (id: string, text: string) => void;
  onReject: (id: string) => void;
  onSkip: (id: string) => void;
};

type DmHandlers = {
  onCreate: (payload: Record<string, string>) => void;
  onEdit: (id: string, text: string) => void;
  onApprove: (id: string, text: string) => void;
  onReject: (id: string) => void;
  onMarkSent: (id: string) => void;
  onCopy: (text: string) => void;
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
      <p className="mt-2 text-sm text-steel-700">Call to action: {post.cta}</p>
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
  return (
    <article className="panel p-5">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-display text-lg font-semibold">
            {item.kind === "comment" ? "Comment" : "Connection note"} · {item.targetName}
          </h3>
          <p className="text-sm text-steel-700">
            {item.targetTitle} @ {item.targetCompany}
          </p>
        </div>
        <StatusPill status={item.status} />
      </div>
      <p className="mb-2 text-sm text-steel-700">{item.sourcePostSummary}</p>
      <textarea
        className="field min-h-28"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={(event) => {
          if ((event.relatedTarget as HTMLElement | null)?.closest("button")) return;
          if (text !== item.suggestedText) handlers.onEdit(item.id, text);
        }}
      />
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
            You&apos;re all caught up 🎉
          </p>
          <p className="mt-2 text-steel-700">
            Nothing is waiting for your approval right now. Create today&apos;s posts to
            get started.
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
  const ordered = [...posts].sort(
    (a, b) => rankStatus(a.status) - rankStatus(b.status)
  );
  return (
    <section className="rise-delay-2 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-semibold">Posts</h2>
          <p className="text-sm text-steel-700">
            Create drafts, edit the wording, then approve to publish.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={handlers.onGenerate}
        >
          Create 3 drafts
        </button>
      </div>

      {ordered.length === 0 && (
        <div className="panel p-6 text-steel-700">
          No posts yet. Click <strong>Create 3 drafts</strong> above (or{" "}
          <strong>Load sample drafts</strong> at the top) to get started.
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
  });
  const ordered = [...items].sort(
    (a, b) => rankStatus(a.status) - rankStatus(b.status)
  );

  return (
    <section className="rise-delay-2 space-y-4">
      <div>
        <h2 className="font-display text-xl font-semibold">Engage</h2>
        <p className="text-sm text-steel-700">
          The assistant drafts comments and connection notes. You approve, and the text
          is copied so you can paste it into LinkedIn.
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
        <label className="text-sm md:col-span-2">
          What is this about? (their post or context)
          <input
            className="field mt-1"
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

function HelpPanel() {
  return (
    <section className="rise-delay-2 space-y-4">
      <div>
        <h2 className="font-display text-xl font-semibold">Your daily 5-step routine</h2>
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

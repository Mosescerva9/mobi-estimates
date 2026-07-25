"use client";

import { useEffect, useState, useTransition } from "react";
import type { DmItem, EngageItem, PostItem, Settings } from "@/lib/types";
import { StatusPill } from "./StatusPill";

type Tab = "posts" | "engage" | "dms" | "settings";

type StatusPayload = {
  app: string;
  aiMode: "openai" | "mock";
  authRequired: boolean;
  linkedinConfigured: boolean;
  pending: { posts: number; engage: number; dms: number };
  settings: Settings;
};

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
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (res.status === 401 && !url.startsWith("/api/auth/")) {
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  const data = await res.json();
  if (!res.ok) {
    const err = data?.error;
    const message =
      typeof err === "string"
        ? err
        : err?.formErrors?.[0] || "Request failed";
    throw new Error(message);
  }
  return data as T;
}

export function Dashboard() {
  const [tab, setTab] = useState<Tab>("posts");
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [posts, setPosts] = useState<PostItem[]>([]);
  const [engage, setEngage] = useState<EngageItem[]>([]);
  const [dms, setDms] = useState<DmItem[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

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
    refresh().catch((err: Error) => setError(err.message));
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
          setError(err instanceof Error ? err.message : "Something went wrong");
        }
      })();
    });
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 md:px-8 md:py-12">
      <header className="rise mb-8 flex flex-col gap-4 border-b border-steel-200 pb-6 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-blueprint">
            Mobi Estimating
          </p>
          <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight text-steel-900 md:text-4xl">
            LinkedIn Ops
          </h1>
          <p className="mt-2 max-w-xl text-steel-700">
            AI drafts posts, comments, connects, and warm DMs. Nothing leaves without your approval.
          </p>
        </div>
        <div className="panel rise-delay-1 px-4 py-3 text-sm">
          <div className="font-mono text-xs uppercase tracking-wide text-steel-700">
            Runtime
          </div>
          <div className="mt-1 text-steel-900">
            AI: <strong>{status?.aiMode ?? "…"}</strong>
            {" · "}
            LinkedIn:{" "}
            <strong>{status?.linkedinConfigured ? "live" : "dry-run"}</strong>
          </div>
          <div className="mt-1 text-steel-700">
            Pending: {status?.pending.posts ?? 0} posts · {status?.pending.engage ?? 0}{" "}
            engage · {status?.pending.dms ?? 0} DMs
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              className="btn"
              disabled={pending}
              onClick={() =>
                run("Seeded sample queue.", async () => {
                  await api("/api/seed", { method: "POST" });
                })
              }
            >
              Seed sample data
            </button>
            {status?.authRequired && (
              <button
                type="button"
                className="btn"
                disabled={pending}
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
        {(
          [
            ["posts", "Posts"],
            ["engage", "Engage"],
            ["dms", "Warm DMs"],
            ["settings", "Settings"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`btn ${tab === id ? "btn-primary" : ""}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

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

      {tab === "posts" && (
        <PostsPanel
          posts={posts}
          busy={pending}
          onGenerate={() =>
            run("Generated post drafts.", async () => {
              await api("/api/posts/generate", {
                method: "POST",
                body: JSON.stringify({ count: 3 }),
              });
            })
          }
          onPatch={(id, body) =>
            run("Post updated.", async () => {
              await api(`/api/posts/${id}`, {
                method: "PATCH",
                body: JSON.stringify(body),
              });
            })
          }
        />
      )}

      {tab === "engage" && (
        <EngagePanel
          items={engage}
          busy={pending}
          onCreate={(payload) =>
            run("Engagement draft added.", async () => {
              await api("/api/engage", {
                method: "POST",
                body: JSON.stringify(payload),
              });
            })
          }
          onPatch={(id, body, copySource) =>
            run(
              body.action === "approve"
                ? "Approved — text copied. Paste it in LinkedIn."
                : "Engagement updated.",
              async () => {
                await api(`/api/engage/${id}`, {
                  method: "PATCH",
                  body: JSON.stringify(body),
                });
                if (body.action === "approve" && copySource) {
                  const ok = await copyText(copySource);
                  if (!ok) {
                    return "Approved, but clipboard copy failed. Copy the text manually.";
                  }
                }
              }
            )
          }
        />
      )}

      {tab === "dms" && (
        <DmPanel
          items={dms}
          busy={pending}
          onCreate={(payload) =>
            run("Warm DM draft added.", async () => {
              await api("/api/dms", {
                method: "POST",
                body: JSON.stringify(payload),
              });
            })
          }
          onPatch={(id, body, copySource) =>
            run(
              body.action === "approve"
                ? "Approved — DM copied. Paste it in LinkedIn, then mark sent."
                : "DM updated.",
              async () => {
                await api(`/api/dms/${id}`, {
                  method: "PATCH",
                  body: JSON.stringify(body),
                });
                if (body.action === "approve" && copySource) {
                  const ok = await copyText(copySource);
                  if (!ok) {
                    return "Approved, but clipboard copy failed. Copy the DM manually.";
                  }
                }
              }
            )
          }
        />
      )}

      {tab === "settings" && settings && (
        <SettingsPanel
          settings={settings}
          busy={pending}
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
    </main>
  );
}

function PostsPanel({
  posts,
  busy,
  onGenerate,
  onPatch,
}: {
  posts: PostItem[];
  busy: boolean;
  onGenerate: () => void;
  onPatch: (id: string, body: Record<string, unknown>) => void;
}) {
  return (
    <section className="rise-delay-2 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-semibold">Post queue</h2>
          <p className="text-sm text-steel-700">
            Generate drafts, edit, then approve to publish (or dry-run).
          </p>
        </div>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={onGenerate}>
          Generate 3 drafts
        </button>
      </div>

      {posts.length === 0 && (
        <div className="panel p-6 text-steel-700">
          No posts yet. Generate drafts or run <code className="font-mono">npm run seed</code>.
        </div>
      )}

      {posts.map((post) => (
        <article key={post.id} className="panel p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-display text-lg font-semibold">{post.topic}</h3>
            <StatusPill status={post.status} />
          </div>
          <textarea
            className="field min-h-40"
            defaultValue={post.body}
            onBlur={(e) => {
              if (e.target.value !== post.body) {
                onPatch(post.id, { action: "edit", body: e.target.value });
              }
            }}
          />
          <p className="mt-2 text-sm text-steel-700">CTA: {post.cta}</p>
          <p className="mt-1 font-mono text-xs text-steel-700">Model: {post.aiModel}</p>
          {post.status === "pending_approval" && (
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => onPatch(post.id, { action: "approve" })}
              >
                Approve & publish
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={busy}
                onClick={() => onPatch(post.id, { action: "reject" })}
              >
                Reject
              </button>
            </div>
          )}
          {post.notes && <p className="mt-3 text-sm text-blueprint-dark">{post.notes}</p>}
        </article>
      ))}
    </section>
  );
}

function EngagePanel({
  items,
  busy,
  onCreate,
  onPatch,
}: {
  items: EngageItem[];
  busy: boolean;
  onCreate: (payload: Record<string, string>) => void;
  onPatch: (
    id: string,
    body: Record<string, unknown>,
    copySource?: string
  ) => void;
}) {
  const [form, setForm] = useState({
    kind: "comment",
    targetName: "",
    targetTitle: "",
    targetCompany: "",
    sourcePostSummary: "",
  });

  return (
    <section className="rise-delay-2 space-y-4">
      <div>
        <h2 className="font-display text-xl font-semibold">Engagement desk</h2>
        <p className="text-sm text-steel-700">
          AI suggests comments and connection notes. You approve, then send from LinkedIn.
        </p>
      </div>

      <form
        className="panel grid gap-3 p-5 md:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          onCreate(form);
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
          Kind
          <select
            className="field mt-1"
            value={form.kind}
            onChange={(e) => setForm({ ...form, kind: e.target.value })}
          >
            <option value="comment">Comment</option>
            <option value="connect">Connect</option>
          </select>
        </label>
        <label className="text-sm">
          Name
          <input
            className="field mt-1"
            required
            value={form.targetName}
            onChange={(e) => setForm({ ...form, targetName: e.target.value })}
          />
        </label>
        <label className="text-sm">
          Title
          <input
            className="field mt-1"
            required
            value={form.targetTitle}
            onChange={(e) => setForm({ ...form, targetTitle: e.target.value })}
          />
        </label>
        <label className="text-sm">
          Company
          <input
            className="field mt-1"
            required
            value={form.targetCompany}
            onChange={(e) => setForm({ ...form, targetCompany: e.target.value })}
          />
        </label>
        <label className="text-sm md:col-span-2">
          Context / post summary
          <input
            className="field mt-1"
            required
            value={form.sourcePostSummary}
            onChange={(e) => setForm({ ...form, sourcePostSummary: e.target.value })}
          />
        </label>
        <div className="md:col-span-2">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            Draft with AI
          </button>
        </div>
      </form>

      {items.map((item) => (
        <article key={item.id} className="panel p-5">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="font-display text-lg font-semibold">
                {item.kind === "comment" ? "Comment" : "Connect"} · {item.targetName}
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
            defaultValue={item.suggestedText}
            onBlur={(e) => {
              if (e.target.value !== item.suggestedText) {
                onPatch(item.id, { action: "edit", suggestedText: e.target.value });
              }
            }}
          />
          {item.status === "pending_approval" && (
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() =>
                  onPatch(item.id, { action: "approve" }, item.suggestedText)
                }
              >
                Approve (copy & send)
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => onPatch(item.id, { action: "skip" })}
              >
                Skip
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={busy}
                onClick={() => onPatch(item.id, { action: "reject" })}
              >
                Reject
              </button>
            </div>
          )}
        </article>
      ))}
    </section>
  );
}

function DmPanel({
  items,
  busy,
  onCreate,
  onPatch,
}: {
  items: DmItem[];
  busy: boolean;
  onCreate: (payload: Record<string, string>) => void;
  onPatch: (
    id: string,
    body: Record<string, unknown>,
    copySource?: string
  ) => void;
}) {
  const [form, setForm] = useState({
    leadName: "",
    leadTitle: "",
    leadCompany: "",
    trigger: "liked_post",
  });

  return (
    <section className="rise-delay-2 space-y-4">
      <div>
        <h2 className="font-display text-xl font-semibold">Warm DM queue</h2>
        <p className="text-sm text-steel-700">
          Only for people who already engaged or requested a demo — no cold spam.
        </p>
      </div>

      <form
        className="panel grid gap-3 p-5 md:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          onCreate(form);
          setForm({
            leadName: "",
            leadTitle: "",
            leadCompany: "",
            trigger: form.trigger,
          });
        }}
      >
        <label className="text-sm">
          Lead name
          <input
            className="field mt-1"
            required
            value={form.leadName}
            onChange={(e) => setForm({ ...form, leadName: e.target.value })}
          />
        </label>
        <label className="text-sm">
          Trigger
          <select
            className="field mt-1"
            value={form.trigger}
            onChange={(e) => setForm({ ...form, trigger: e.target.value })}
          >
            <option value="liked_post">Liked post</option>
            <option value="commented">Commented</option>
            <option value="accepted_connect">Accepted connect</option>
            <option value="demo_request">Demo request</option>
            <option value="site_visit">Site visit</option>
          </select>
        </label>
        <label className="text-sm">
          Title
          <input
            className="field mt-1"
            required
            value={form.leadTitle}
            onChange={(e) => setForm({ ...form, leadTitle: e.target.value })}
          />
        </label>
        <label className="text-sm">
          Company
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

      {items.map((item) => (
        <article key={item.id} className="panel p-5">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="font-display text-lg font-semibold">{item.leadName}</h3>
              <p className="text-sm text-steel-700">
                {item.leadTitle} @ {item.leadCompany} · trigger: {item.trigger.replaceAll("_", " ")}
              </p>
            </div>
            <StatusPill status={item.status} />
          </div>
          <textarea
            className="field min-h-36"
            defaultValue={item.body}
            onBlur={(e) => {
              if (e.target.value !== item.body) {
                onPatch(item.id, { action: "edit", body: e.target.value });
              }
            }}
          />
          {item.status === "pending_approval" && (
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => onPatch(item.id, { action: "approve" }, item.body)}
              >
                Approve (copy DM)
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={busy}
                onClick={() => onPatch(item.id, { action: "reject" })}
              >
                Reject
              </button>
            </div>
          )}
          {item.status === "approved" && (
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() =>
                  void copyText(item.body).then((ok) => {
                    if (!ok) window.alert("Clipboard copy failed.");
                  })
                }
              >
                Copy again
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => onPatch(item.id, { action: "mark_sent" })}
              >
                Mark sent
              </button>
            </div>
          )}
        </article>
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
        <h2 className="font-display text-xl font-semibold">Control settings</h2>
        <p className="text-sm text-steel-700">
          Brand voice, ICP keywords, and daily caps. Caps are guidance for your review pace.
        </p>
      </div>
      <form
        className="panel grid gap-3 p-5"
        onSubmit={(e) => {
          e.preventDefault();
          onSave({
            ...form,
            icpKeywords: form.icpKeywords,
            doNotContact: form.doNotContact,
          });
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
          Brand voice
          <textarea
            className="field mt-1 min-h-28"
            value={form.brandVoice}
            onChange={(e) => setForm({ ...form, brandVoice: e.target.value })}
          />
        </label>
        <label className="text-sm">
          ICP keywords (comma-separated)
          <input
            className="field mt-1"
            value={form.icpKeywords.join(", ")}
            onChange={(e) =>
              setForm({
                ...form,
                icpKeywords: e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
          />
        </label>
        <label className="text-sm">
          CTA URL
          <input
            className="field mt-1"
            value={form.ctaUrl}
            onChange={(e) => setForm({ ...form, ctaUrl: e.target.value })}
          />
        </label>
        <div className="grid gap-3 md:grid-cols-3">
          <label className="text-sm">
            Daily connect cap
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
            Daily comment cap
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
            Daily DM cap
            <input
              type="number"
              className="field mt-1"
              value={form.dailyDmCap}
              onChange={(e) => setForm({ ...form, dailyDmCap: Number(e.target.value) })}
            />
          </label>
        </div>
        <label className="text-sm">
          Do-not-contact names (comma-separated)
          <input
            className="field mt-1"
            value={form.doNotContact.join(", ")}
            onChange={(e) =>
              setForm({
                ...form,
                doNotContact: e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
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

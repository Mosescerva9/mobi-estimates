/**
 * LinkedIn publisher stub.
 *
 * Posts can eventually go out via LinkedIn's official API with OAuth.
 * Likes / comments / connects / DMs stay human-approved and are not
 * mass-automated here (LinkedIn ToS + account risk).
 */

export type PublishResult =
  | { ok: true; mode: "live" | "dry_run"; externalId?: string; message: string }
  | { ok: false; message: string };

export async function publishPost(body: string): Promise<PublishResult> {
  const token = process.env.LINKEDIN_ACCESS_TOKEN?.trim();
  const author = process.env.LINKEDIN_AUTHOR_URN?.trim();

  if (!token || !author) {
    return {
      ok: true,
      mode: "dry_run",
      message:
        "Approved locally. LinkedIn credentials not configured — marked as published in dry-run mode.",
    };
  }

  const res = await fetch("https://api.linkedin.com/v2/ugcPosts", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      "X-Restli-Protocol-Version": "2.0.0",
    },
    body: JSON.stringify({
      author,
      lifecycleState: "PUBLISHED",
      specificContent: {
        "com.linkedin.ugc.ShareContent": {
          shareCommentary: { text: body },
          shareMediaCategory: "NONE",
        },
      },
      visibility: {
        "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
      },
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    return {
      ok: false,
      message: `LinkedIn publish failed (${res.status}): ${text.slice(0, 240)}`,
    };
  }

  const id = res.headers.get("x-restli-id") || undefined;
  return {
    ok: true,
    mode: "live",
    externalId: id,
    message: "Published to LinkedIn.",
  };
}

export function assistedSendMessage(kind: "comment" | "connect" | "dm"): string {
  return `Approved for assisted send (${kind}). Copy the text from the dashboard and send from your LinkedIn account — no autonomous browser botting.`;
}

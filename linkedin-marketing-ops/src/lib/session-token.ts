/** Shared session token helper safe for Edge middleware and Node routes. */

export async function hashSessionToken(password: string): Promise<string> {
  const data = new TextEncoder().encode(`mobi-linkedin-ops:${password}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

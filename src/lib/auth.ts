import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export type AppRole = "client" | "estimator" | "reviewer" | "admin";

export interface SessionUser {
  id: string;
  email: string | null;
  role: AppRole;
  fullName: string | null;
}

/**
 * Returns the authenticated user + profile role, or null. Always verifies the
 * user against Supabase Auth (getUser), not just a decoded cookie.
 */
export async function getSessionUser(): Promise<SessionUser | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;

  const { data: profile } = await supabase
    .from("profiles")
    .select("role, full_name, email")
    .eq("id", user.id)
    .single();

  return {
    id: user.id,
    email: profile?.email ?? user.email ?? null,
    role: (profile?.role as AppRole) ?? "client",
    fullName: profile?.full_name ?? null,
  };
}

/** Require any authenticated user (redirects to /login otherwise). */
export async function requireUser(): Promise<SessionUser> {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  return user;
}

const STAFF: AppRole[] = ["estimator", "reviewer", "admin"];

/** Require a staff role (estimator/reviewer/admin). Clients are sent to the portal. */
export async function requireStaff(): Promise<SessionUser> {
  const user = await requireUser();
  if (!STAFF.includes(user.role)) redirect("/portal");
  return user;
}

export function isStaff(role: AppRole) {
  return STAFF.includes(role);
}

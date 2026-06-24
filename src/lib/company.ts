import { createClient } from "@/lib/supabase/server";

/**
 * Returns the company_id the current user belongs to (their first / primary
 * membership), or null if they have not onboarded yet.
 *
 * RLS: company_members has a self-select policy (user_id = auth.uid()), so this
 * runs safely with the anon-key server client bound to the user's session.
 */
export async function getPrimaryCompanyId(): Promise<string | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;

  const { data } = await supabase
    .from("company_members")
    .select("company_id")
    .eq("user_id", user.id)
    .order("is_primary", { ascending: false })
    .limit(1)
    .maybeSingle();

  return data?.company_id ?? null;
}

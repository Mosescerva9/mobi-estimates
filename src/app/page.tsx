import { redirect } from "next/navigation";
import { getSessionUser, isStaff } from "@/lib/auth";
import { getPrimaryCompanyId } from "@/lib/company";

export default async function Home() {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  if (isStaff(user.role)) redirect("/admin");

  // Clients go to the portal once onboarded; otherwise set up their company.
  const companyId = await getPrimaryCompanyId();
  redirect(companyId ? "/portal" : "/onboarding");
}

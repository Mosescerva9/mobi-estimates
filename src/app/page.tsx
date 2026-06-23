import { redirect } from "next/navigation";
import { getSessionUser, isStaff } from "@/lib/auth";

export default async function Home() {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  redirect(isStaff(user.role) ? "/admin" : "/portal");
}

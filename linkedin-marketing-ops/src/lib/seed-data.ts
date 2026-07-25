import { generateDmDraft, generateEngageDraft, generatePostDrafts } from "./ai";
import { DEFAULT_SETTINGS } from "./prompts";
import { writeStore } from "./store";
import type { StoreData } from "./types";

export async function seedStore(replace = true): Promise<StoreData> {
  const settings = { ...DEFAULT_SETTINGS };
  const posts = await generatePostDrafts(settings, 3);

  const engage = await Promise.all([
    generateEngageDraft(settings, {
      kind: "comment",
      targetName: "Jordan Hale",
      targetTitle: "Senior Estimator",
      targetCompany: "Northline Construction",
      sourcePostSummary: "Talked about bid-night overtime and incomplete plan sets",
    }),
    generateEngageDraft(settings, {
      kind: "connect",
      targetName: "Sam Rivera",
      targetTitle: "Project Manager",
      targetCompany: "Rivera Remodeling",
      sourcePostSummary: "Hiring for estimating support on multifamily rehabs",
    }),
  ]);

  const dms = await Promise.all([
    generateDmDraft(settings, {
      leadName: "Alex Chen",
      leadTitle: "Owner",
      leadCompany: "Chen Build Co",
      trigger: "demo_request",
    }),
    generateDmDraft(settings, {
      leadName: "Taylor Brooks",
      leadTitle: "Chief Estimator",
      leadCompany: "Brooks & Sons GC",
      trigger: "liked_post",
    }),
  ]);

  const data: StoreData = replace
    ? { settings, posts, engage, dms }
    : { settings, posts, engage, dms };

  await writeStore(data);
  return data;
}

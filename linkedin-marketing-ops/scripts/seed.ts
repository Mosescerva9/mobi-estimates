import { generateDmDraft, generateEngageDraft, generatePostDrafts } from "../src/lib/ai";
import { DEFAULT_SETTINGS } from "../src/lib/prompts";
import { writeStore } from "../src/lib/store";

async function main() {
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

  await writeStore({ settings, posts, engage, dms });
  console.log(
    `Seeded ${posts.length} posts, ${engage.length} engage items, ${dms.length} DMs.`
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

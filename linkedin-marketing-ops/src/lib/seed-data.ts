import { generateDmDraft, generateEngageDraft, generatePostDrafts } from "./ai";
import { readStore as defaultReadStore, writeStore as defaultWriteStore } from "./store";
import type { StoreData } from "./types";

export type SeedDeps = {
  readStore: () => Promise<StoreData>;
  writeStore: (data: StoreData) => Promise<void>;
};

const defaultDeps: SeedDeps = {
  readStore: defaultReadStore,
  writeStore: defaultWriteStore,
};

/**
 * Append demo queue items to the durable store.
 *
 * This never replaces the store: existing settings, posts, engage items and DMs
 * are all preserved, so running seed on a live deployment can only ever add
 * sample drafts — it can never erase real data. Existing settings are reused so
 * the demo drafts match the owner's configured brand voice and CTA.
 */
export async function seedStore(deps: SeedDeps = defaultDeps): Promise<StoreData> {
  const store = await deps.readStore();
  const settings = store.settings;

  const posts = await generatePostDrafts(settings, 3);

  const engage = await Promise.all([
    generateEngageDraft(settings, {
      kind: "comment",
      targetName: "Jordan Hale",
      targetTitle: "Senior Estimator",
      targetCompany: "Northline Construction",
      sourcePostSummary: "Talked about bid-night overtime and incomplete plan sets",
      sourcePostUrl:
        "https://www.linkedin.com/posts/jordan-hale_bid-night-activity-7100000000000000000-abcd",
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

  // Append demo items ahead of existing ones; keep everything already stored.
  store.posts = [...posts, ...store.posts];
  store.engage = [...engage, ...store.engage];
  store.dms = [...dms, ...store.dms];

  await deps.writeStore(store);
  return store;
}

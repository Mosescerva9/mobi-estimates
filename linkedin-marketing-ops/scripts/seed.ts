import { seedStore } from "../src/lib/seed-data";

async function main() {
  const data = await seedStore(true);
  console.log(
    `Seeded ${data.posts.length} posts, ${data.engage.length} engage items, ${data.dms.length} DMs.`
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

import { seedStore } from "../src/lib/seed-data";

async function main() {
  const data = await seedStore();
  console.log(
    `Store now has ${data.posts.length} posts, ${data.engage.length} engage items, ${data.dms.length} DMs (demo items appended).`
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

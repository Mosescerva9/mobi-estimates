import assert from "node:assert/strict";
import { test } from "node:test";
import {
  clampHashtags,
  cleanupMarketingSpeak,
  polishPostBody,
  polishShortText,
  stripEmojis,
  wordCount,
} from "./content-quality";

test("stripEmojis removes pictographs", () => {
  const cleaned = stripEmojis("Great takeoff 🚀 today");
  assert.equal(cleaned, "Great takeoff today");
  assert.ok(!stripEmojis("Bid night 🔥").includes("🔥"));
});

test("cleanupMarketingSpeak removes banned fluff", () => {
  const cleaned = cleanupMarketingSpeak(
    "This is a game-changer for estimators in today's competitive landscape."
  );
  assert.ok(!/game-changer/i.test(cleaned));
  assert.ok(!/competitive landscape/i.test(cleaned));
});

test("clampHashtags keeps at most two trailing tags", () => {
  const result = clampHashtags(
    "Useful takeoff tip.\n\n#Estimating #Construction #Takeoff #Bidding"
  );
  const tags = result.match(/#[\w-]+/g) || [];
  assert.equal(tags.length, 2);
});

test("polish helpers produce clean short text", () => {
  assert.equal(polishShortText("  Hello   world  "), "Hello world");
  assert.ok(wordCount(polishPostBody("One two three")) === 3);
});

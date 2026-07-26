import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { aiMode, generatePostDrafts, modelLabel } from "./ai";
import { DEFAULT_SETTINGS } from "./prompts";

const savedKey = process.env.OPENAI_API_KEY;
const savedModel = process.env.OPENAI_MODEL;

afterEach(() => {
  if (savedKey === undefined) delete process.env.OPENAI_API_KEY;
  else process.env.OPENAI_API_KEY = savedKey;
  if (savedModel === undefined) delete process.env.OPENAI_MODEL;
  else process.env.OPENAI_MODEL = savedModel;
});

test("mock mode when no OpenAI key is set", () => {
  delete process.env.OPENAI_API_KEY;
  assert.equal(aiMode(), "mock");
  assert.equal(modelLabel(), "mock-local");
});

test("openai mode and default model gpt-4o-mini when key is set", () => {
  process.env.OPENAI_API_KEY = "sk-test";
  delete process.env.OPENAI_MODEL;
  assert.equal(aiMode(), "openai");
  assert.equal(modelLabel(), "gpt-4o-mini");
});

test("OPENAI_MODEL overrides the default label", () => {
  process.env.OPENAI_API_KEY = "sk-test";
  process.env.OPENAI_MODEL = "gpt-4o";
  assert.equal(modelLabel(), "gpt-4o");
});

test("mock drafts are usable: pending approval with non-empty body", async () => {
  delete process.env.OPENAI_API_KEY;
  const items = await generatePostDrafts(DEFAULT_SETTINGS, 2);
  assert.equal(items.length, 2);
  for (const item of items) {
    assert.equal(item.status, "pending_approval");
    assert.equal(item.aiModel, "mock-local");
    assert.ok(item.body.trim().length > 0);
    assert.ok(item.topic.trim().length > 0);
    assert.ok(!/\p{Extended_Pictographic}/u.test(item.body));
    assert.ok(!/game-changer/i.test(item.body));
  }
});

test("mock drafts can target a specific angle", async () => {
  delete process.env.OPENAI_API_KEY;
  const items = await generatePostDrafts(DEFAULT_SETTINGS, 1, "overflow_capacity");
  assert.equal(items.length, 1);
  assert.match(items[0].body.toLowerCase(), /overflow|capacity|bid/);
});

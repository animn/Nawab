import test from "node:test";
import assert from "node:assert/strict";
import {
  lane,
  review,
  retention,
  validTikTok,
  validSegments,
  SAMPLES,
  EMPTY_PRACTICE,
} from "../src/domain.ts";
test("legacy score progression and reset preserve identity and notes", () => {
  const v = { ...SAMPLES[0], id: "legacy-md5-id", notes: "keep" };
  const next = review(v, true);
  assert.equal(next.id, v.id);
  assert.equal(next.notes, "keep");
  assert.equal(next.score, 1);
  assert.equal(review(next, false).score, 0);
  assert.equal(lane(0), "Inbox");
  assert.equal(lane(2), "Review");
  assert.equal(lane(3), "Mastered");
});
test("retention has no invented denominator", () => {
  assert.equal(retention(EMPTY_PRACTICE), null);
  assert.equal(retention({ ...EMPTY_PRACTICE, attempts: 4, correct: 3 }), 75);
});
test("TikTok URL validates exact domain and https", () => {
  assert.ok(validTikTok("https://vm.tiktok.com/abc"));
  for (const u of [
    "https://tiktok.com.evil.com/a",
    "https://eviltiktok.com/a",
    "http://tiktok.com/a",
    "file:///a",
    "bad",
  ])
    assert.equal(validTikTok(u), false);
});
test("segment bounds and overlap validated", () => {
  const s = {
    start: 0,
    end: 2,
    arabic: "شلونك",
    english: "Hi",
    transliteration: "",
    explanation: "",
  };
  assert.ok(validSegments([s], 3));
  assert.equal(validSegments([{ ...s, end: 4 }], 3), false);
  assert.equal(validSegments([s, { ...s, start: 1, end: 3 }]), false);
  assert.equal(validSegments([{ ...s, start: NaN }]), false);
});

import test from "node:test";
import assert from "node:assert/strict";
import {
  savedSegmentMatches,
  sentenceVideoPath,
  videoSourceKey,
} from "../src/video.ts";
const segment = {
  start: 1,
  end: 3,
  arabic: "شلونك",
  english: "How are you?",
  transliteration: "shlonak",
  explanation: "Greeting",
};
test("only saved matching text and timing is paired with source video", () => {
  assert.ok(savedSegmentMatches({ ...segment }, segment));
  assert.equal(savedSegmentMatches(undefined, segment), false);
  for (const key of [
    "start",
    "end",
    "arabic",
    "english",
    "transliteration",
    "explanation",
  ] as const) {
    const changed = {
      ...segment,
      [key]: typeof segment[key] === "number" ? 7 : "different",
    };
    assert.equal(savedSegmentMatches(changed, segment), false);
  }
});
test("video boundaries invalidate player key and removed/reordered sentences cannot use stale clips", () => {
  assert.notEqual(
    videoSourceKey("job", 0, segment),
    videoSourceKey("job", 0, { ...segment, end: 4 }),
  );
  assert.notEqual(
    videoSourceKey("job", 0, segment),
    videoSourceKey("job", 1, segment),
  );
  assert.equal(
    savedSegmentMatches({ ...segment, arabic: "Other sentence" }, segment),
    false,
  );
});
test("video source routes stay relative and encode job identifiers; invalid index rejected", () => {
  assert.equal(
    sentenceVideoPath("job-1", 2),
    "/v1/jobs/job-1/segments/2/video",
  );
  assert.equal(
    sentenceVideoPath("https://evil.test/secret", 0),
    "/v1/jobs/https%3A%2F%2Fevil.test%2Fsecret/segments/0/video",
  );
  for (const i of [-1, 1.5, NaN])
    assert.throws(() => sentenceVideoPath("job", i));
});

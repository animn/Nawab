import test from "node:test";
import assert from "node:assert/strict";
import {
  restoreState,
  serializeState,
  validateAPI,
  createOperationGate,
} from "../src/state.ts";
import { SAMPLES, EMPTY_PRACTICE } from "../src/domain.ts";
import { request } from "../src/api.ts";
import { mergeCSV } from "../src/sheets.ts";
test("hydration preserves scores, notes and IDs; corrupt storage throws before writes can be enabled", () => {
  const data = {
    local: [{ ...SAMPLES[0], id: "legacy-id", score: 8, notes: "keep me" }],
    stats: { ...EMPTY_PRACTICE, attempts: 4 },
    api: "https://example.test",
    sheet: "sheet",
  };
  assert.deepEqual(restoreState(serializeState(data)), data);
  assert.deepEqual(restoreState(null), {});
  assert.throws(() => restoreState("{broken"));
  assert.throws(() => restoreState('{"local":[]}'));
});
test("serialization explicitly excludes password and bearer tokens", () => {
  const input = {
    local: SAMPLES,
    stats: EMPTY_PRACTICE,
    api: "https://example.test",
    sheet: "sheet",
    token: "DO_NOT_SAVE",
    password: "NOPE",
  };
  assert.equal(serializeState(input).includes("DO_NOT_SAVE"), false);
  assert.equal(serializeState(input).includes("NOPE"), false);
});
test("API URL rejects insecure hosts, embedded credentials and non-http schemes", () => {
  assert.equal(validateAPI("https://example.test/"), "https://example.test");
  assert.equal(validateAPI("http://localhost:8000"), "http://localhost:8000");
  for (const x of [
    "http://example.test",
    "ftp://localhost",
    "https://user:secret@example.test",
    "https://example.test?token=secret",
    "not a url",
  ])
    assert.throws(() => validateAPI(x));
});
test("duplicate approve/save clicks run once, failures release the gate", async () => {
  const gate = createOperationGate();
  let count = 0;
  let release: () => void = () => {};
  const wait = new Promise<void>((r) => (release = r));
  const first = gate(async () => {
    count++;
    await wait;
  });
  await gate(async () => {
    count++;
  });
  assert.equal(count, 1);
  release();
  await first;
  await assert.rejects(() =>
    gate(async () => {
      throw Error("failed");
    }),
  );
  await gate(async () => {
    count++;
  });
  assert.equal(count, 2);
});
test("failed API responses surface server errors and attach bearer only when provided", async () => {
  const original = globalThis.fetch;
  let headers: any;
  try {
    globalThis.fetch = async (_url, init) => {
      headers = init?.headers;
      return new Response(
        JSON.stringify({ detail: "Provider is not configured" }),
        { status: 503 },
      );
    };
    await assert.rejects(
      () => request("https://api.test", "abc", "/v1/jobs"),
      /Provider is not configured/,
    );
    assert.equal(headers.Authorization, "Bearer abc");
    await assert.rejects(() =>
      request("https://api.test", "", "/auth/login", "POST", {
        password: "test",
      }),
    );
    assert.equal(headers.Authorization, undefined);
  } finally {
    globalThis.fetch = original;
  }
});
test("Sheet reimport computes MD5 identity and preserves progress and notes", () => {
  const csv =
    "arabicscript,englishmeaning,pronunciation\nشلونك,How are you,shlonak";
  const imported = mergeCSV(csv, []);
  assert.match(imported[0].id, /^[a-f0-9]{32}$/);
  const saved = { ...imported[0], score: 5, notes: "remember" };
  const again = mergeCSV(csv, [saved]);
  assert.equal(again.length, 1);
  assert.equal(again[0].id, saved.id);
  assert.equal(again[0].score, 5);
  assert.equal(again[0].notes, "remember");
  assert.throws(() => mergeCSV("<html>not csv</html>", []));
});

test("exact legacy public Sheet headers normalize spaces, punctuation and invisible format marks", () => {
  const csv =
    "Level,Chapter,Arabic Script,Pronunciation,English Meaning\u2060,Explanation,Letter-wise pronounciation,Letter-wise English,TTSText,\n1,Office,شلونك,shlonak,How are you,Greeting,letters,letter meanings,شلونك,";
  const initial = mergeCSV(csv, []);
  assert.equal(initial.length, 1);
  assert.equal(initial[0].english, "How are you");
  assert.equal(initial[0].chapter, "Office");
  const saved = {
    ...initial[0],
    score: 7,
    notes: "Keep this",
    has_audio: true,
    audio_provider: "source_video",
    custom_metadata: "preserved",
  };
  const again = mergeCSV(csv, [saved]);
  assert.equal(again[0].id, saved.id);
  assert.equal(again[0].score, 7);
  assert.equal(again[0].notes, "Keep this");
  assert.equal(again[0].has_audio, true);
  assert.equal((again[0] as typeof saved).audio_provider, "source_video");
  assert.equal((again[0] as typeof saved).custom_metadata, "preserved");
});

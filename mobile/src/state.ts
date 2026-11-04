import type { Vocab, Practice } from "./domain";
export type SavedState = {
  local: Vocab[];
  stats: Practice;
  api: string;
  sheet: string;
};
export function restoreState(raw: string | null): Partial<SavedState> {
  if (raw === null) return {};
  const x = JSON.parse(raw);
  if (
    !x ||
    typeof x !== "object" ||
    !Array.isArray(x.local) ||
    !x.local.every(
      (v: any) =>
        typeof v.id === "string" &&
        typeof v.arabic === "string" &&
        typeof v.english === "string" &&
        typeof v.notes === "string" &&
        typeof v.score === "number" &&
        v.score >= 0,
    )
  )
    throw Error("Invalid saved vocabulary.");
  if (
    !x.stats ||
    !["attempts", "correct", "listens", "recordings"].every(
      (k) => typeof x.stats[k] === "number" && x.stats[k] >= 0,
    )
  )
    throw Error("Invalid saved practice.");
  return {
    local: x.local,
    stats: x.stats,
    api: typeof x.api === "string" ? x.api : "",
    sheet: typeof x.sheet === "string" ? x.sheet : "",
  };
}
export function validateAPI(base: string) {
  let u: URL;
  try {
    u = new URL(base);
  } catch {
    throw Error("Enter a valid HTTPS API URL.");
  }
  if (u.username || u.password || u.search || u.hash)
    throw Error("Use a clean API URL without credentials, query or fragment.");
  if (
    u.protocol !== "https:" &&
    !(
      u.protocol === "http:" &&
      ["localhost", "127.0.0.1", "10.0.2.2"].includes(u.hostname)
    )
  )
    throw Error("Use HTTPS for your private backend.");
  return base.replace(/\/$/, "");
}
export function createOperationGate() {
  let pending = false;
  return async function <T>(
    operation: () => Promise<T>,
  ): Promise<T | undefined> {
    if (pending) return undefined;
    pending = true;
    try {
      return await operation();
    } finally {
      pending = false;
    }
  };
}
export function serializeState(state: SavedState) {
  return JSON.stringify({
    local: state.local,
    stats: state.stats,
    api: state.api,
    sheet: state.sheet,
  });
}

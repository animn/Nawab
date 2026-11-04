import Papa from "papaparse";
import { md5 } from "js-md5";
import type { Vocab } from "./domain";
export const EXISTING_SHEET =
  "https://docs.google.com/spreadsheets/d/1DQ_74TZtMpbinusdnMOU2441hEFa7RRnaqeMx8qrBg0/export?format=csv";
export function mergeCSV(csv: string, existing: Vocab[]): Vocab[] {
  const parsed = Papa.parse<Record<string, string>>(csv, {
    header: true,
    skipEmptyLines: true,
    transformHeader: (h) => h.toLowerCase().replace(/[^a-z0-9]/g, ""),
  });
  if (parsed.errors.some((e) => e.type === "Quotes"))
    throw Error("The Sheet CSV could not be parsed.");
  const all = new Map(existing.map((v) => [v.id, v]));
  let count = 0;
  for (const row of parsed.data) {
    const arabic = (row.arabicscript || row.arabic || "").trim();
    if (!arabic) continue;
    count++;
    const id = md5(arabic);
    const old = all.get(id);
    all.set(id, {
      ...old,
      id,
      chapter: row.chapter || "My vocabulary",
      arabic,
      english: row.englishmeaning || row.english || "",
      pronunciation: row.pronunciation || "",
      explanation: row.explanation || "",
      score: old?.score || 0,
      notes: old?.notes || "",
    });
  }
  if (!count)
    throw Error(
      "No Arabic vocabulary found. Expected an arabicscript or arabic CSV column.",
    );
  return [...all.values()];
}

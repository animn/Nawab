import type { Segment } from "./domain";
export function savedSegmentMatches(
  saved: Segment | undefined,
  draft: Segment,
) {
  return (
    !!saved &&
    (
      [
        "start",
        "end",
        "arabic",
        "english",
        "transliteration",
        "explanation",
      ] as const
    ).every((k) => saved[k] === draft[k])
  );
}
export function sentenceVideoPath(jobId: string, index: number) {
  if (!jobId || !Number.isInteger(index) || index < 0)
    throw Error("Invalid sentence video reference.");
  return `/v1/jobs/${encodeURIComponent(jobId)}/segments/${index}/video`;
}
export function videoSourceKey(jobId: string, index: number, segment: Segment) {
  return `${jobId}:${index}:${segment.start}:${segment.end}`;
}

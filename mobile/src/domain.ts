export type Vocab = {
  id: string;
  chapter: string;
  arabic: string;
  english: string;
  pronunciation: string;
  explanation: string;
  score: number;
  notes: string;
  has_audio?: boolean;
  has_video?: boolean;
  illustrative?: boolean;
};
export type Segment = {
  start: number;
  end: number;
  arabic: string;
  english: string;
  transliteration: string;
  explanation: string;
};
export type Job = {
  id: string;
  status: string;
  error?: string;
  source_url?: string;
  segments: Segment[];
  duration?: number;
  has_video?: boolean;
  video_metadata?: {
    duration: number;
    width: number;
    height: number;
    has_audio?: boolean;
  } | null;
  created_at?: string;
};
export type Practice = {
  attempts: number;
  correct: number;
  listens: number;
  recordings: number;
};
export const EMPTY_PRACTICE: Practice = {
  attempts: 0,
  correct: 0,
  listens: 0,
  recordings: 0,
};
export function lane(score: number) {
  return score >= 3 ? "Mastered" : score > 0 ? "Review" : "Inbox";
}
export function review(v: Vocab, correct: boolean): Vocab {
  return { ...v, score: correct ? v.score + 1 : 0 };
}
export function retention(p: Practice) {
  return p.attempts ? Math.round((p.correct / p.attempts) * 100) : null;
}
export function validTikTok(url: string) {
  try {
    const u = new URL(url);
    return (
      u.protocol === "https:" &&
      (u.hostname === "tiktok.com" || u.hostname.endsWith(".tiktok.com")) &&
      u.pathname !== "/"
    );
  } catch {
    return false;
  }
}
export function validSegments(s: Segment[], duration?: number) {
  return (
    s.length > 0 &&
    s.every(
      (x, i) =>
        Number.isFinite(x.start) &&
        Number.isFinite(x.end) &&
        x.start >= 0 &&
        x.end > x.start &&
        (!duration || x.end <= duration) &&
        (!i || x.start >= s[i - 1].end) &&
        x.arabic.trim() &&
        x.english.trim(),
    )
  );
}
export const SAMPLES: Vocab[] = [
  {
    id: "sample-office-1",
    chapter: "AT THE OFFICE",
    arabic: "متى الاجتماع؟",
    english: "When is the meeting?",
    pronunciation: "Mita il-ijtimaaʿ?",
    explanation:
      "A practical question used across the Gulf. Illustrative learning material, not transcribed from a video.",
    score: 0,
    notes: "",
    illustrative: true,
  },
  {
    id: "sample-office-2",
    chapter: "EVERYDAY KUWAIT",
    arabic: "شلونك؟",
    english: "How are you?",
    pronunciation: "Shlōnak?",
    explanation:
      "A common Kuwaiti greeting when addressing a man. Shlōnich addresses a woman. Illustrative material.",
    score: 0,
    notes: "",
    illustrative: true,
  },
  {
    id: "sample-treasury-1",
    chapter: "TREASURY DESK",
    arabic: "دز لي التقرير",
    english: "Send me the report.",
    pronunciation: "Dizz li it-taqrīr.",
    explanation:
      "دز means “send” in Kuwaiti usage. التقرير is a formal workplace noun. Illustrative, not a verified video transcription.",
    score: 0,
    notes: "",
    illustrative: true,
  },
];

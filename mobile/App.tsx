import React, { useEffect, useState, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  TextInput,
  Modal,
  Platform,
  useWindowDimensions,
  ActivityIndicator,
  Linking,
  KeyboardAvoidingView,
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as DocumentPicker from "expo-document-picker";
import { AudioPractice } from "./src/AudioPractice";
import { C } from "./src/theme";
import {
  Vocab,
  Job,
  Segment,
  Practice,
  SAMPLES,
  EMPTY_PRACTICE,
  lane,
  retention,
  review,
  validTikTok,
  validSegments,
} from "./src/domain";
import { request, fileForm } from "./src/api";
import { EXISTING_SHEET, mergeCSV } from "./src/sheets";
import {
  restoreState,
  serializeState,
  validateAPI,
  createOperationGate,
} from "./src/state";

type Tab = "Today" | "Vocabulary" | "Lessons" | "Practice" | "Settings";
const KEY = "nawab-local-v1";
const Icon = ({ text }: { text: string }) => (
  <Text style={{ fontSize: 20, color: C.emerald }}>{text}</Text>
);
function Button({
  label,
  onPress,
  secondary = false,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  secondary?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        s.button,
        secondary && s.secondary,
        disabled && { opacity: 0.4 },
        pressed && { opacity: 0.75 },
      ]}
    >
      <Text style={[s.buttonText, secondary && { color: C.text }]}>
        {label}
      </Text>
    </Pressable>
  );
}
function Field({
  label,
  value,
  onChange,
  multiline = false,
  secure = false,
  numeric = false,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  multiline?: boolean;
  secure?: boolean;
  numeric?: boolean;
  disabled?: boolean;
}) {
  return (
    <View style={{ gap: 7, flex: 1 }}>
      <Text style={s.fieldLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        editable={!disabled}
        value={value}
        onChangeText={onChange}
        multiline={multiline}
        secureTextEntry={secure}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType={numeric ? "decimal-pad" : "default"}
        placeholderTextColor={C.muted}
        style={[
          s.input,
          multiline && { minHeight: 80, textAlignVertical: "top" },
        ]}
      />
    </View>
  );
}
export default function App() {
  return (
    <SafeAreaProvider>
      <Nawab />
    </SafeAreaProvider>
  );
}
function Nawab() {
  const { width } = useWindowDimensions();
  const wide = width >= 900;
  const [tab, setTab] = useState<Tab>("Today");
  const [local, setLocal] = useState<Vocab[]>(SAMPLES);
  const [remote, setRemote] = useState<Vocab[]>([]);
  const [stats, setStats] = useState<Practice>(EMPTY_PRACTICE);
  const [loaded, setLoaded] = useState(false);
  const [api, setApi] = useState("");
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [sheet, setSheet] = useState(EXISTING_SHEET);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<Vocab | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [notes, setNotes] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("All");
  const [query, setQuery] = useState("");
  const [url, setUrl] = useState("");
  const [rights, setRights] = useState(false);
  const [editing, setEditing] = useState<Job | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [writeSheet, setWriteSheet] = useState(false);
  const [health, setHealth] = useState<any>(null);
  const gate = useRef(createOperationGate()).current;
  const vocab = token ? remote : local;
  const mastered = vocab.filter((v) => v.score >= 3).length;
  const rate = retention(stats);
  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((raw) => {
        if (raw) {
          const x = restoreState(raw);
          if (Array.isArray(x.local)) setLocal(x.local);
          if (x.stats) setStats(x.stats);
          if (x.api) setApi(x.api);
          if (x.sheet) setSheet(x.sheet);
        }
      })
      .then(() => setLoaded(true))
      .catch(() =>
        setMessage(
          "Saved progress could not be read. Storage writes are paused to protect existing data.",
        ),
      );
  }, []);
  useEffect(() => {
    if (loaded)
      AsyncStorage.setItem(
        KEY,
        serializeState({ local, stats, api, sheet }),
      ).catch(() =>
        setMessage(
          "Device storage is full or unavailable. This session’s changes may not persist.",
        ),
      );
  }, [loaded, local, stats, api, sheet]);
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let polling = false;
    const timer = setInterval(() => {
      if (polling) return;
      polling = true;
      request(api, token, "/v1/jobs")
        .then((data) => {
          if (!cancelled) setJobs(data);
        })
        .catch((error) => {
          if (cancelled) return;
          if (error.status === 401) {
            setToken("");
            setRemote([]);
            setJobs([]);
            setMessage(
              "Your session expired. Sign in again to access server data.",
            );
          } else
            setMessage(
              "Could not refresh lesson statuses. Your server data is unchanged; check the connection.",
            );
        })
        .finally(() => {
          polling = false;
        });
    }, 7000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [token, api]);
  async function run(fn: () => Promise<void>) {
    await gate(async () => {
      setBusy(true);
      setMessage("");
      try {
        await fn();
      } catch (e) {
        setMessage(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    });
  }
  async function refresh() {
    const [v, j] = await Promise.all([
      request(api, token, "/v1/vocab"),
      request(api, token, "/v1/jobs"),
    ]);
    setRemote(v);
    setJobs(j);
  }
  function open(v: Vocab) {
    setSelected(v);
    setNotes(v.notes);
    setRevealed(false);
  }
  async function answer(correct: boolean) {
    if (!selected) return;
    await run(async () => {
      if (token) {
        const next = await request(
          api,
          token,
          `/v1/vocab/${selected.id}/review`,
          "POST",
          { correct },
        );
        setRemote((a) =>
          a.map((v) => (v.id === selected.id ? { ...v, ...next } : v)),
        );
      } else
        setLocal((a) =>
          a.map((v) => (v.id === selected.id ? review(v, correct) : v)),
        );
      setStats((p) => ({
        ...p,
        attempts: p.attempts + 1,
        correct: p.correct + (correct ? 1 : 0),
      }));
      setSelected(null);
      setMessage(
        correct
          ? "Recall recorded. Keep building that memory."
          : "Marked for another review. That is how learning works.",
      );
    });
  }
  async function saveNotes() {
    if (!selected) return;
    await run(async () => {
      if (token) {
        await request(api, token, `/v1/vocab/${selected.id}/notes`, "PUT", {
          notes,
        });
        setRemote((v) =>
          v.map((x) => (x.id === selected.id ? { ...x, notes } : x)),
        );
      } else
        setLocal((v) =>
          v.map((x) => (x.id === selected.id ? { ...x, notes } : x)),
        );
      setMessage("Notes saved.");
    });
  }
  async function login() {
    await run(async () => {
      validateAPI(api);
      const result = await request(api, "", "/auth/login", "POST", {
        password,
      });
      const [v, j, h] = await Promise.all([
        request(api, result.access_token, "/v1/vocab"),
        request(api, result.access_token, "/v1/jobs"),
        request(api, "", "/health"),
      ]);
      setToken(result.access_token);
      setPassword("");
      setRemote(v);
      setJobs(j);
      setHealth(h);
      setMessage(
        "Signed in. Your server vocabulary is separate from local practice.",
      );
    });
  }
  async function upload() {
    if (!token) {
      setMessage("Sign in to your API in Settings to upload a video.");
      return;
    }
    if (!rights) {
      setMessage("Confirm you own or have permission to use this video first.");
      return;
    }
    await run(async () => {
      const picked = await DocumentPicker.getDocumentAsync({
        type: ["video/*", "audio/*"],
        copyToCacheDirectory: true,
      });
      if (picked.canceled) return;
      const f = picked.assets[0];
      const form = await fileForm(
        f.uri,
        f.name,
        f.mimeType || "video/mp4",
        Platform.OS === "web",
      );
      form.append("rights_confirmed", "true");
      const result = await request(api, token, "/v1/jobs/upload", "POST", form);
      setJobs((a) => [result, ...a]);
      setMessage("Upload accepted. Check its processing status below.");
    });
  }
  async function importURL() {
    if (!validTikTok(url)) {
      setMessage("Paste a valid HTTPS tiktok.com video link.");
      return;
    }
    if (!rights) {
      setMessage("Confirm your rights to use this video first.");
      return;
    }
    await run(async () => {
      const result = await request(api, token, "/v1/jobs", "POST", {
        url,
        rights_confirmed: true,
      });
      setJobs((a) => [result, ...a]);
      setUrl("");
      setMessage(
        "Import submitted. It is not a completed lesson until processing and your review finish.",
      );
    });
  }
  function beginEdit(j: Job) {
    setEditing(j);
    setSegments(
      j.segments.length
        ? j.segments.map((x) => ({ ...x }))
        : [
            {
              start: 0,
              end: 1,
              arabic: "",
              english: "",
              transliteration: "",
              explanation: "",
            },
          ],
    );
    setWriteSheet(false);
  }
  async function saveSegments() {
    if (!editing) return;
    await run(async () => {
      if (!validSegments(segments, editing.duration))
        throw Error(
          "Use ordered, non-overlapping timestamps within the video duration, and fill Arabic and English.",
        );
      const next = await request(
        api,
        token,
        `/v1/jobs/${editing.id}/segments`,
        "PUT",
        { segments },
      );
      setEditing(next);
      setJobs((a) => a.map((j) => (j.id === editing.id ? next : j)));
      setMessage("Sentence edits saved. Approval is a separate step.");
    });
  }
  async function approve() {
    if (!editing) return;
    await run(async () => {
      if (!validSegments(segments, editing.duration))
        throw Error("Review all sentence text and boundaries first.");
      await request(api, token, `/v1/jobs/${editing.id}/segments`, "PUT", {
        segments,
      });
      const result = await request(
        api,
        token,
        `/v1/jobs/${editing.id}/approve`,
        "POST",
        { approved: true, write_to_sheet: writeSheet },
      );
      await refresh();
      setEditing(null);
      const problems = (result.sheet_results || []).filter(
        (x: any) => !["sent", "already_present"].includes(x.status),
      );
      setMessage(
        writeSheet
          ? problems.length
            ? "Vocabulary saved. Sheet write needs attention: " +
              problems.map((x: any) => x.status + ": " + x.error).join("; ")
            : "Approved sentences saved to vocabulary and Google Sheet."
          : "Approved sentences saved to your vocabulary.",
      );
    });
  }
  const heading: Record<Tab, string> = {
    Today: "A little Kuwaiti. Every day.",
    Vocabulary: "Words that stay with you.",
    Lessons: "Real moments. Real Kuwaiti.",
    Practice: "From knowing to saying.",
    Settings: "Make yourself at home.",
  };
  const nav: [Tab, string][] = [
    ["Today", "◈"],
    ["Vocabulary", "▤"],
    ["Lessons", "▷"],
    ["Practice", "◎"],
    ["Settings", "⚙"],
  ];
  return (
    <SafeAreaView style={s.root}>
      <StatusBar style="light" />
      <View style={[s.shell, wide && { flexDirection: "row" }]}>
        {wide && (
          <View style={s.sidebar}>
            <View style={s.brand}>
              <Text style={s.logo}>ن</Text>
              <View>
                <Text style={s.brandName}>nawab</Text>
                <Text style={s.eyebrow}>KUWAITI, IN YOUR WORDS</Text>
              </View>
            </View>
            <View style={{ gap: 10, marginTop: 52 }}>
              {nav.map(([name, icon]) => (
                <Pressable
                  key={name}
                  onPress={() => setTab(name)}
                  style={[s.navItem, tab === name && s.navActive]}
                >
                  <Icon text={icon} />
                  <Text style={[s.navText, tab === name && { color: C.green }]}>
                    {name}
                  </Text>
                  {name === "Lessons" && (
                    <Text style={s.navCount}>{jobs.length}</Text>
                  )}
                </Pressable>
              ))}
            </View>
            <View style={s.sidebarBottom}>
              <Text style={s.arabicSmall}>حياك الله</Text>
              <Text style={s.muted}>
                A language feels like home{`\n`}one conversation at a time.
              </Text>
              <Text style={[s.tiny, { marginTop: 18 }]}>
                {token ? "● Connected to your server" : "○ Local practice mode"}
              </Text>
            </View>
          </View>
        )}
        <View style={{ flex: 1 }}>
          <ScrollView
            contentContainerStyle={[
              s.content,
              wide && { paddingHorizontal: 48 },
            ]}
            keyboardShouldPersistTaps="handled"
          >
            {!wide && (
              <View
                style={[
                  s.row,
                  { justifyContent: "space-between", marginBottom: 24 },
                ]}
              >
                <View style={s.brand}>
                  <Text style={s.logo}>ن</Text>
                  <Text style={s.brandName}>nawab</Text>
                </View>
                <Pressable onPress={() => setTab("Settings")}>
                  <Text style={s.mode}>
                    {token ? "● CONNECTED" : "○ LOCAL PRACTICE"}
                  </Text>
                </Pressable>
              </View>
            )}
            <View style={s.topline}>
              <Text style={s.eyebrow}>
                {tab === "Today" ? "YOUR DAILY MAJLIS" : tab.toUpperCase()}
              </Text>
              {wide && (
                <Text style={s.mode}>
                  {token ? "● CONNECTED" : "○ LOCAL PRACTICE"}
                </Text>
              )}
            </View>
            <Text style={[s.heading, !wide && { fontSize: 32 }]}>
              {heading[tab]}
            </Text>
            <Text style={s.subtitle}>
              {tab === "Today"
                ? "Listen closely. Speak confidently. Build a habit that lasts."
                : tab === "Lessons"
                  ? "Turn videos you have permission to use into sentences worth remembering."
                  : tab === "Vocabulary"
                    ? "Your Inbox → Review → Mastered journey, with your notes intact."
                    : tab === "Practice"
                      ? "Listen, hide, recall, then compare. No pretend fluency scores."
                      : "Your progress is yours. Keep credentials on the server."}
            </Text>
            {!!message && (
              <View accessibilityRole="alert" style={s.notice}>
                <Text style={{ color: C.text, flex: 1, lineHeight: 21 }}>
                  {message}
                </Text>
                <Pressable
                  accessibilityLabel="Dismiss notice"
                  onPress={() => setMessage("")}
                >
                  <Text style={s.muted}>✕</Text>
                </Pressable>
              </View>
            )}
            {busy && (
              <ActivityIndicator
                color={C.green}
                style={{ marginVertical: 12 }}
              />
            )}
            {tab === "Today" && (
              <>
                <View style={[s.hero, wide && { flexDirection: "row" }]}>
                  <View style={{ flex: 1, gap: 18 }}>
                    <Text style={s.heroTag}>
                      SMALL STEPS. REAL CONVERSATIONS.
                    </Text>
                    <Text style={s.heroTitle}>
                      Your next conversation{`\n`}starts here.
                    </Text>
                    <Text style={s.heroDescription}>
                      {vocab.length
                        ? vocab.length + " phrases ready to explore."
                        : "Your collection is ready for its first phrases."}
                      {`\n`}One good sentence is a great place to start.
                    </Text>
                    <View style={s.row}>
                      <Button
                        label="Start a quick review  ↗"
                        onPress={() =>
                          vocab.length
                            ? open(vocab.find((v) => v.score < 3) || vocab[0])
                            : setTab("Settings")
                        }
                      />
                      <Pressable onPress={() => setTab("Vocabulary")}>
                        <Text style={{ color: C.text, padding: 12 }}>
                          Explore vocabulary
                        </Text>
                      </Pressable>
                    </View>
                  </View>
                  <View style={s.heroArt}>
                    <View style={s.orbit1} />
                    <View style={s.orbit2} />
                    <Text style={s.heroArabic}>يلا{`\n`}نتعلّم</Text>
                    <Text style={s.artCaption}>YALLA, LET’S LEARN</Text>
                  </View>
                </View>
                <View style={[s.metrics, !wide && { gap: 10 }]}>
                  {[
                    [
                      rate === null ? "—" : rate + "%",
                      "Self-rated recall",
                      stats.attempts + " self-rated attempts",
                    ],
                    [
                      String(stats.listens),
                      "Listening plays",
                      "Started on this device",
                    ],
                    [
                      String(mastered),
                      "Mastered phrases",
                      "3+ correct recalls",
                    ],
                    [
                      String(stats.recordings),
                      "Speaking sessions",
                      "Recordings completed",
                    ],
                  ].map(([value, label, sub]) => (
                    <View
                      key={label}
                      style={[s.metric, !wide && { minWidth: "46%" }]}
                    >
                      <Text style={s.metricValue}>{value}</Text>
                      <Text style={s.metricLabel}>{label}</Text>
                      <Text style={s.tiny}>{sub}</Text>
                    </View>
                  ))}
                </View>
                <View style={s.sectionHead}>
                  <Text style={s.sectionTitle}>Make it part of your day</Text>
                  <Text style={s.eyebrow}>YOUR LEARNING PATH</Text>
                </View>
                <View
                  style={[s.twoColumns, !wide && { flexDirection: "column" }]}
                >
                  <Pressable
                    style={[s.card, { flex: 1 }]}
                    onPress={() => setTab("Lessons")}
                  >
                    <View style={s.row}>
                      <Text style={s.featureIcon}>▷</Text>
                      <Text style={s.pill}>VIDEO → VOCABULARY</Text>
                    </View>
                    <Text style={s.cardTitle}>
                      A clip. A conversation. A lesson.
                    </Text>
                    <Text style={s.muted}>
                      Bring a TikTok link or upload your own video. Review the
                      Arabic, choose your sentences, then save.
                    </Text>
                    <Text style={s.link}>Create a video lesson ↗</Text>
                  </Pressable>
                  <Pressable
                    style={[s.card, { flex: 1 }]}
                    onPress={() => {
                      setTab("Practice");
                    }}
                  >
                    <View style={s.row}>
                      <Text style={s.featureIcon}>◎</Text>
                      <Text style={s.pill}>AT YOUR OWN PACE</Text>
                    </View>
                    <Text style={s.cardTitle}>
                      Practice for your working day.
                    </Text>
                    <Text style={s.muted}>
                      Meetings, greetings and the treasury desk. Clearly
                      labelled examples to help you find your words.
                    </Text>
                    <Text style={s.link}>Open practice studio ↗</Text>
                  </Pressable>
                </View>
                <Text style={[s.tiny, { marginTop: 22 }]}>
                  {token
                    ? "Server vocabulary is loaded from your authenticated account."
                    : "Local practice begins with illustrative examples, not imported video transcripts. Sync your existing Sheet in Settings."}{" "}
                  Accuracy reflects self-reported recall, not a clinical or
                  pronunciation assessment.
                </Text>
              </>
            )}
            {tab === "Vocabulary" && (
              <>
                <TextInput
                  accessibilityLabel="Search vocabulary"
                  placeholder="Search Arabic, English or your notes…"
                  placeholderTextColor={C.muted}
                  value={query}
                  onChangeText={setQuery}
                  style={s.input}
                />
                <View style={[s.row, { marginVertical: 20 }]}>
                  {["All", "Inbox", "Review", "Mastered"].map((f) => (
                    <Pressable
                      key={f}
                      onPress={() => setFilter(f)}
                      style={[s.chip, filter === f && s.chipActive]}
                    >
                      <Text style={{ color: filter === f ? C.bg : C.muted }}>
                        {f} ·{" "}
                        {
                          vocab.filter(
                            (v) => f === "All" || lane(v.score) === f,
                          ).length
                        }
                      </Text>
                    </Pressable>
                  ))}
                </View>
                <View style={s.wordGrid}>
                  {vocab
                    .filter(
                      (v) =>
                        (filter === "All" || lane(v.score) === filter) &&
                        `${v.arabic} ${v.english} ${v.notes}`
                          .toLowerCase()
                          .includes(query.toLowerCase()),
                    )
                    .map((v) => (
                      <Pressable
                        key={v.id}
                        onPress={() => open(v)}
                        style={[s.wordCard, wide && { width: "48%" }]}
                      >
                        <View style={s.topline}>
                          <Text style={s.eyebrow}>
                            {v.chapter || "MY VOCABULARY"}
                          </Text>
                          <Text style={s.pill}>{lane(v.score)}</Text>
                        </View>
                        <Text style={s.arabic}>{v.arabic}</Text>
                        <Text style={s.wordEnglish}>{v.english}</Text>
                        <Text style={s.muted}>{v.pronunciation}</Text>
                        <View style={[s.topline, { marginTop: 20 }]}>
                          <Text style={s.tiny}>
                            {v.illustrative
                              ? "ILLUSTRATIVE EXAMPLE"
                              : v.has_audio
                                ? "AUDIO AVAILABLE"
                                : "YOUR COLLECTION"}
                          </Text>
                          <Text style={s.link}>{Math.min(v.score, 3)}/3 ↗</Text>
                        </View>
                        {!!v.notes && (
                          <Text numberOfLines={2} style={s.notePreview}>
                            {v.notes}
                          </Text>
                        )}
                      </Pressable>
                    ))}
                </View>
                {!vocab.length && (
                  <Text style={s.muted}>
                    No vocabulary yet. Sync your Sheet or approve a video lesson
                    to begin.
                  </Text>
                )}
              </>
            )}
            {tab === "Lessons" && (
              <>
                <View style={s.card}>
                  <Text style={s.sectionTitle}>Bring a moment from Kuwait</Text>
                  <Text style={s.muted}>
                    Paste a public TikTok video link. If downloading is
                    restricted, upload a video or audio file you are allowed to
                    use. No access controls are bypassed.
                  </Text>
                  <Field
                    label="TikTok video URL"
                    value={url}
                    onChange={setUrl}
                  />
                  <Pressable
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: rights }}
                    onPress={() => setRights(!rights)}
                    style={s.checkRow}
                  >
                    <Text style={s.checkbox}>{rights ? "☑" : "☐"}</Text>
                    <Text style={[s.muted, { flex: 1 }]}>
                      I own this content or have permission to download and
                      process it.
                    </Text>
                  </Pressable>
                  <View style={s.row}>
                    <Button
                      label="Create lesson  ↗"
                      disabled={busy || !rights || !token}
                      onPress={importURL}
                    />
                    <Button
                      label="Upload video / audio"
                      secondary
                      disabled={busy || !rights || !token}
                      onPress={upload}
                    />
                  </View>
                  {!token && (
                    <Text style={s.warning}>
                      Connect your private API in Settings to process videos.
                      Local practice does not simulate successful imports.
                    </Text>
                  )}
                </View>
                <View style={s.sectionHead}>
                  <Text style={s.sectionTitle}>Your video lessons</Text>
                  {!!token && (
                    <Button
                      label="Refresh"
                      secondary
                      onPress={() => run(refresh)}
                      disabled={busy}
                    />
                  )}
                </View>
                {jobs.length === 0 ? (
                  <View
                    style={[
                      s.card,
                      { alignItems: "center", paddingVertical: 45 },
                    ]}
                  >
                    <Text style={s.featureIcon}>▷</Text>
                    <Text style={s.cardTitle}>
                      Your first real-world lesson awaits.
                    </Text>
                    <Text style={[s.muted, { textAlign: "center" }]}>
                      Imported clips appear here with their actual processing
                      state.{`\n`}Nothing is added to vocabulary until you
                      approve it.
                    </Text>
                  </View>
                ) : (
                  jobs.map((j) => (
                    <View key={j.id} style={[s.card, { marginBottom: 14 }]}>
                      <View style={s.topline}>
                        <Text style={s.pill}>
                          {j.status.replaceAll("_", " ").toUpperCase()}
                        </Text>
                        <Text style={s.tiny}>{j.created_at?.slice(0, 10)}</Text>
                      </View>
                      <Text style={s.cardTitle}>
                        {j.source_url ? "TikTok lesson" : "Uploaded lesson"}
                      </Text>
                      {!!j.source_url && (
                        <Pressable
                          accessibilityRole="link"
                          onPress={() => {
                            if (j.source_url && validTikTok(j.source_url))
                              Linking.openURL(j.source_url).catch(() =>
                                setMessage(
                                  "Could not open the original video.",
                                ),
                              );
                          }}
                        >
                          <Text numberOfLines={2} style={s.link}>
                            Open original video ↗
                          </Text>
                          <Text numberOfLines={2} style={s.tiny}>
                            {j.source_url}
                          </Text>
                        </Pressable>
                      )}
                      {!!j.error && <Text style={s.warning}>{j.error}</Text>}
                      <Text style={s.muted}>
                        {j.segments?.length || 0} sentences ·{" "}
                        {j.duration
                          ? Math.round(j.duration) + " seconds"
                          : "Duration not yet available"}
                      </Text>
                      <View style={s.row}>
                        {!["queued", "processing", "approved"].includes(
                          j.status,
                        ) && (
                          <Button
                            label="Review / edit sentences"
                            onPress={() => beginEdit(j)}
                          />
                        )}{" "}
                        {["failed", "needs_configuration"].includes(
                          j.status,
                        ) && (
                          <Button
                            label="Retry processing"
                            secondary
                            onPress={() =>
                              run(async () => {
                                await request(
                                  api,
                                  token,
                                  `/v1/jobs/${j.id}/retry`,
                                  "POST",
                                );
                                await refresh();
                              })
                            }
                          />
                        )}
                      </View>
                    </View>
                  ))
                )}
              </>
            )}
            {tab === "Practice" && (
              <>
                <View style={[s.card, { borderColor: C.emerald }]}>
                  <Text style={s.heroTag}>THE RECALL STUDIO</Text>
                  <Text style={s.cardTitle}>
                    Can you find the words without looking?
                  </Text>
                  <Text style={s.muted}>
                    Open a phrase, listen if source audio is available, hide the
                    words and recall the meaning. Reveal to check, then honestly
                    rate yourself. You can also record and replay your own
                    voice.
                  </Text>
                  <Button
                    label="Practice next phrase  ↗"
                    onPress={() =>
                      vocab.length
                        ? open(vocab.find((v) => v.score < 3) || vocab[0])
                        : setTab("Settings")
                    }
                  />
                </View>
                <View style={s.sectionHead}>
                  <Text style={s.sectionTitle}>Everyday & office practice</Text>
                  <Text style={s.pill}>ILLUSTRATIVE</Text>
                </View>
                {SAMPLES.map((v) => (
                  <Pressable
                    key={v.id}
                    style={[s.card, { marginBottom: 14 }]}
                    onPress={() => {
                      if (token) {
                        setMessage(
                          "These are local illustrative examples. Sign out to practice them without changing server vocabulary.",
                        );
                        return;
                      }
                      const exists = local.find((x) => x.id === v.id);
                      if (!exists) setLocal((a) => [...a, v]);
                      open(exists || v);
                    }}
                  >
                    <Text style={s.eyebrow}>{v.chapter}</Text>
                    <Text style={s.arabic}>{v.arabic}</Text>
                    <Text style={s.wordEnglish}>{v.english}</Text>
                    <Text style={s.tiny}>
                      Original illustrative learning material. Not a TikTok
                      transcription. ↗
                    </Text>
                  </Pressable>
                ))}
              </>
            )}
            {tab === "Settings" && (
              <>
                <View style={s.card}>
                  <Text style={s.sectionTitle}>Your private backend</Text>
                  <Text style={s.muted}>
                    Video processing, private Sheets sync and original audio
                    need your own authenticated API. Passwords and provider keys
                    are never bundled in this app. Your session token is held in
                    memory only.
                  </Text>
                  <Field
                    label="API base URL (HTTPS)"
                    disabled={busy}
                    value={api}
                    onChange={(v) => {
                      if (token) {
                        setToken("");
                        setRemote([]);
                        setJobs([]);
                      }
                      setApi(v);
                    }}
                  />
                  <Field
                    label="Owner password"
                    secure
                    value={password}
                    onChange={setPassword}
                  />
                  <View style={s.row}>
                    {token ? (
                      <Button
                        label="Sign out"
                        secondary
                        onPress={() => {
                          setToken("");
                          setRemote([]);
                          setJobs([]);
                          setHealth(null);
                          setMessage(
                            "Signed out. Back to your separate local practice collection.",
                          );
                        }}
                      />
                    ) : (
                      <Button
                        label="Sign in"
                        disabled={busy || !api || !password}
                        onPress={login}
                      />
                    )}
                    <Button
                      label="Check API status"
                      secondary
                      disabled={!api || busy}
                      onPress={() =>
                        run(async () => {
                          setHealth(await request(api, "", "/health"));
                        })
                      }
                    />
                  </View>
                  {health && (
                    <Text style={s.muted}>
                      API: {health.status || "reachable"} · Authentication:{" "}
                      {health.auth_configured ? "configured" : "not configured"}{" "}
                      · Processing provider:{" "}
                      {health.provider_configured
                        ? "configured"
                        : "not configured"}
                    </Text>
                  )}
                </View>
                <View style={[s.card, { marginTop: 20 }]}>
                  <Text style={s.sectionTitle}>
                    Keep your existing vocabulary
                  </Text>
                  <Text style={s.muted}>
                    {token
                      ? "Sync your configured Google Sheet through the server. Existing IDs, scores and notes are preserved."
                      : "Import your existing public Nawab Sheet on demand into local storage. Arabic MD5 IDs preserve your existing progress during repeat imports. Private Sheets require the backend."}
                  </Text>
                  {!token && (
                    <Field
                      label="Existing Nawab Sheet · CSV URL"
                      value={sheet}
                      onChange={setSheet}
                    />
                  )}
                  <Button
                    label={
                      token
                        ? "Sync Google Sheet"
                        : "Import public Sheet to this device"
                    }
                    disabled={busy}
                    onPress={() =>
                      run(async () => {
                        if (token) {
                          await request(
                            api,
                            token,
                            "/v1/sheets/import",
                            "POST",
                          );
                          await refresh();
                          setMessage("Sheet sync complete.");
                        } else {
                          const u = new URL(sheet);
                          if (
                            u.protocol !== "https:" ||
                            u.hostname !== "docs.google.com"
                          )
                            throw Error(
                              "Use an HTTPS docs.google.com CSV export URL.",
                            );
                          const r = await fetch(sheet);
                          if (!r.ok)
                            throw Error(
                              "Could not read the Sheet. Check public access or use the authenticated backend.",
                            );
                          const next = mergeCSV(await r.text(), local);
                          setLocal(next);
                          setMessage(
                            `Sheet imported. ${next.filter((v) => !v.illustrative).length} vocabulary entries on this device; existing progress preserved.`,
                          );
                        }
                      })
                    }
                  />
                  <Text style={s.tiny}>
                    A public Sheet fetch may be blocked by browser CORS. The
                    native Expo app or your configured backend can handle that
                    case. Local practice data is not automatically written to
                    your Sheet.
                  </Text>
                </View>
                <View style={[s.card, { marginTop: 20 }]}>
                  <Text style={s.sectionTitle}>A few honest boundaries</Text>
                  <Text style={s.muted}>
                    • Kuwaiti explanations need human review, especially
                    ambiguous slang.{`\n`}• No video is marked complete without
                    actual processing.{`\n`}• No automatic Google Sheet writes.
                    You choose when to approve and export.{`\n`}• Local progress
                    stays on this device; server progress stays on your server.
                    {`\n`}• Microphone access is requested only when you choose
                    Record.
                  </Text>
                </View>
              </>
            )}
            <View style={s.footer}>
              <Text style={s.eyebrow}>NAWAB</Text>
              <Text style={s.tiny}>Made for the Kuwaiti you actually use.</Text>
              <Text style={s.arabicSmall}>شوي شوي</Text>
            </View>
          </ScrollView>
          {!wide && (
            <View style={s.bottomNav}>
              {nav.map(([name, icon]) => (
                <Pressable
                  accessibilityRole="tab"
                  accessibilityState={{ selected: tab === name }}
                  key={name}
                  onPress={() => setTab(name)}
                  style={s.bottomItem}
                >
                  <Text
                    style={{
                      color: tab === name ? C.green : C.muted,
                      fontSize: 21,
                    }}
                  >
                    {icon}
                  </Text>
                  <Text
                    style={{
                      color: tab === name ? C.green : C.muted,
                      fontSize: 10,
                    }}
                  >
                    {name}
                  </Text>
                </Pressable>
              ))}
            </View>
          )}
        </View>
      </View>
      <Modal
        visible={!!selected}
        transparent
        animationType="slide"
        onRequestClose={() => setSelected(null)}
      >
        <View style={s.modalBackdrop}>
          <KeyboardAvoidingView
            behavior={Platform.OS === "ios" ? "padding" : undefined}
            style={s.modal}
          >
            <ScrollView
              contentContainerStyle={{ padding: 24, gap: 18 }}
              keyboardShouldPersistTaps="handled"
            >
              {selected && (
                <>
                  <View style={s.topline}>
                    <Text style={s.eyebrow}>
                      {selected.illustrative
                        ? "ILLUSTRATIVE PRACTICE"
                        : "YOUR VOCABULARY"}
                    </Text>
                    <Button
                      label="Close"
                      secondary
                      onPress={() => setSelected(null)}
                    />
                  </View>
                  <Text style={s.sectionTitle}>Listen. Recall. Reveal.</Text>
                  {revealed ? (
                    <>
                      <Text style={s.arabic}>{selected.arabic}</Text>
                      <Text style={s.wordEnglish}>{selected.english}</Text>
                      <Text style={{ color: C.gold, fontSize: 17 }}>
                        {selected.pronunciation}
                      </Text>
                      <Text style={s.muted}>{selected.explanation}</Text>
                    </>
                  ) : (
                    <View style={s.hiddenCard}>
                      <Text style={{ color: C.emerald, fontSize: 40 }}>◎</Text>
                      <Text style={s.cardTitle}>
                        {selected.has_audio
                          ? "Find the phrase in your memory."
                          : "Say this in Kuwaiti"}
                      </Text>
                      <Text style={[s.muted, { textAlign: "center" }]}>
                        {selected.has_audio
                          ? "Listen to the original, then say what you remember."
                          : selected.english}
                        {!selected.has_audio &&
                          `\nRecall the Arabic, then reveal to check yourself.`}
                      </Text>
                    </View>
                  )}
                  <Button
                    label={
                      revealed ? "Hide words again" : "Reveal phrase & meaning"
                    }
                    onPress={() => setRevealed(!revealed)}
                  />
                  <AudioPractice
                    key={selected.id}
                    source={
                      selected.has_audio && token
                        ? {
                            uri:
                              api.replace(/\/$/, "") +
                              `/v1/vocab/${selected.id}/audio`,
                            headers: { Authorization: `Bearer ${token}` },
                          }
                        : undefined
                    }
                    base={api}
                    token={token}
                    arabic={selected.arabic}
                    vocabId={token ? selected.id : undefined}
                    onListen={() =>
                      setStats((p) => ({ ...p, listens: p.listens + 1 }))
                    }
                    onRecord={() =>
                      setStats((p) => ({ ...p, recordings: p.recordings + 1 }))
                    }
                    onError={setMessage}
                  />
                  {revealed && (
                    <View style={s.row}>
                      <Button
                        label="I recalled it ✓"
                        disabled={busy}
                        onPress={() => answer(true)}
                      />
                      <Button
                        label="Needs another look"
                        secondary
                        disabled={busy}
                        onPress={() => answer(false)}
                      />
                    </View>
                  )}
                  <Field
                    label="Your notes"
                    value={notes}
                    onChange={setNotes}
                    multiline
                  />
                  <Button
                    label="Save notes"
                    secondary
                    disabled={busy}
                    onPress={saveNotes}
                  />
                  <Text style={s.tiny}>{message}</Text>
                </>
              )}
            </ScrollView>
          </KeyboardAvoidingView>
        </View>
      </Modal>
      <Modal
        visible={!!editing}
        transparent
        animationType="slide"
        onRequestClose={() => setEditing(null)}
      >
        <View style={s.modalBackdrop}>
          <View style={[s.modal, { maxWidth: 850 }]}>
            <ScrollView
              contentContainerStyle={{ padding: 24, gap: 18 }}
              keyboardShouldPersistTaps="handled"
            >
              <View style={s.topline}>
                <Text style={s.sectionTitle}>Review your lesson</Text>
                <Button
                  label="Close"
                  secondary
                  onPress={() => setEditing(null)}
                />
              </View>
              <Text style={s.muted}>
                Edit the text and source boundaries. Remove any sentences you do
                not want to save. Approval saves only the sentences shown below.
                Interpretations are drafts until you review them.
              </Text>
              {!!editing?.duration && !editing.segments.length && (
                <View style={s.card}>
                  <Text style={s.sectionTitle}>
                    Transcribe from the original
                  </Text>
                  <Text style={s.muted}>
                    No machine transcript is available. Listen to the full
                    extracted source, then write only the sentences you can
                    verify and set their timestamps below.
                  </Text>
                  <AudioPractice
                    key={`${editing.id}-full-original`}
                    source={{
                      uri:
                        api.replace(/\/$/, "") + `/v1/jobs/${editing.id}/audio`,
                      headers: { Authorization: `Bearer ${token}` },
                    }}
                    sourceLabel="full original audio"
                    base={api}
                    token={token}
                    arabic=""
                    onListen={() =>
                      setStats((p) => ({ ...p, listens: p.listens + 1 }))
                    }
                    onRecord={() =>
                      setStats((p) => ({ ...p, recordings: p.recordings + 1 }))
                    }
                    onError={setMessage}
                  />
                </View>
              )}
              {segments.map((seg, i) => (
                <View key={i} style={s.card}>
                  <Text style={s.eyebrow}>SENTENCE {i + 1}</Text>
                  <View style={s.row}>
                    {(["start", "end"] as const).map((k) => (
                      <Field
                        key={k}
                        label={k + " (seconds)"}
                        value={String(seg[k])}
                        numeric
                        onChange={(v) =>
                          setSegments((a) =>
                            a.map((x, n) =>
                              n === i
                                ? { ...x, [k]: v === "" ? NaN : Number(v) }
                                : x,
                            ),
                          )
                        }
                      />
                    ))}
                  </View>
                  {(
                    [
                      "arabic",
                      "english",
                      "transliteration",
                      "explanation",
                    ] as const
                  ).map((k) => (
                    <Field
                      key={k}
                      label={k}
                      value={seg[k]}
                      multiline={k === "explanation"}
                      onChange={(v) =>
                        setSegments((a) =>
                          a.map((x, n) => (n === i ? { ...x, [k]: v } : x)),
                        )
                      }
                    />
                  ))}
                  {editing && editing.segments[i] && (
                    <AudioPractice
                      key={`${editing.id}-${i}-${editing.segments[i].start}-${editing.segments[i].end}`}
                      source={{
                        uri:
                          api.replace(/\/$/, "") +
                          `/v1/jobs/${editing.id}/segments/${i}/audio`,
                        headers: { Authorization: `Bearer ${token}` },
                      }}
                      base={api}
                      token={token}
                      arabic={seg.arabic}
                      onListen={() =>
                        setStats((p) => ({ ...p, listens: p.listens + 1 }))
                      }
                      onRecord={() =>
                        setStats((p) => ({
                          ...p,
                          recordings: p.recordings + 1,
                        }))
                      }
                      onError={setMessage}
                    />
                  )}
                  <Button
                    label="Remove this sentence"
                    secondary
                    onPress={() =>
                      setSegments((a) => a.filter((_, n) => n !== i))
                    }
                  />
                </View>
              ))}
              <Button
                label="Add sentence"
                secondary
                onPress={() =>
                  setSegments((a) => [
                    ...a,
                    {
                      start: a.at(-1)?.end || 0,
                      end: (a.at(-1)?.end || 0) + 1,
                      arabic: "",
                      english: "",
                      transliteration: "",
                      explanation: "",
                    },
                  ])
                }
              />
              <Text style={s.warning}>
                Save timestamp edits before listening to the updated source
                clip.
              </Text>
              <Button
                label="Save edits only"
                secondary
                disabled={busy}
                onPress={saveSegments}
              />
              <Pressable
                accessibilityRole="checkbox"
                accessibilityState={{ checked: writeSheet }}
                style={s.checkRow}
                onPress={() => setWriteSheet(!writeSheet)}
              >
                <Text style={s.checkbox}>{writeSheet ? "☑" : "☐"}</Text>
                <Text style={[s.muted, { flex: 1 }]}>
                  Also append approved sentences to my configured Google Sheet.
                </Text>
              </Pressable>
              <Button
                label={`Approve & save ${segments.length} sentences${writeSheet ? " + write to Sheet" : ""}`}
                disabled={busy || !segments.length}
                onPress={approve}
              />
              <Text style={s.warning}>{message}</Text>
            </ScrollView>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  shell: { flex: 1 },
  sidebar: {
    width: 245,
    borderRightWidth: 1,
    borderColor: C.line,
    padding: 26,
  },
  brand: { flexDirection: "row", gap: 12, alignItems: "center" },
  logo: {
    width: 42,
    height: 46,
    color: C.green,
    fontSize: 37,
    fontWeight: "600",
    textAlign: "center",
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 14,
  },
  brandName: {
    fontSize: 30,
    fontWeight: "700",
    letterSpacing: -1.3,
    color: C.text,
  },
  eyebrow: {
    fontSize: 9,
    letterSpacing: 1.6,
    color: C.muted,
    fontWeight: "700",
  },
  navItem: {
    flexDirection: "row",
    gap: 14,
    padding: 15,
    borderRadius: 13,
    alignItems: "center",
  },
  navActive: { backgroundColor: C.panel2 },
  navText: { color: C.muted, fontSize: 14, fontWeight: "600" },
  navCount: { marginLeft: "auto", color: C.muted, fontSize: 11 },
  sidebarBottom: { marginTop: "auto", gap: 12, paddingTop: 40 },
  arabicSmall: { color: C.emerald, fontSize: 25 },
  content: {
    padding: 22,
    paddingTop: 30,
    paddingBottom: 28,
    maxWidth: 1440,
    width: "100%",
    alignSelf: "center",
  },
  topline: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 10,
  },
  mode: { fontSize: 9, color: C.green, letterSpacing: 1.2 },
  heading: {
    color: C.text,
    fontSize: 39,
    letterSpacing: -1.4,
    fontWeight: "600",
    marginTop: 16,
    lineHeight: 47,
  },
  subtitle: {
    color: C.muted,
    fontSize: 14,
    lineHeight: 22,
    marginTop: 8,
    marginBottom: 30,
    maxWidth: 650,
  },
  hero: {
    backgroundColor: "#153D3B",
    borderRadius: 23,
    padding: 28,
    overflow: "hidden",
    gap: 20,
    borderWidth: 1,
    borderColor: "#2C5750",
  },
  heroTag: {
    color: C.green,
    letterSpacing: 1.8,
    fontWeight: "700",
    fontSize: 9,
  },
  heroTitle: {
    color: C.text,
    fontSize: 31,
    lineHeight: 39,
    fontWeight: "600",
    letterSpacing: -0.7,
  },
  heroDescription: { fontSize: 14, color: "#B7CDC5", lineHeight: 24 },
  heroArt: {
    height: 210,
    width: 220,
    alignSelf: "center",
    alignItems: "center",
    justifyContent: "center",
  },
  orbit1: {
    position: "absolute",
    width: 205,
    height: 205,
    borderRadius: 110,
    borderWidth: 1,
    borderColor: "#416356",
  },
  orbit2: {
    position: "absolute",
    width: 165,
    height: 165,
    borderRadius: 90,
    borderWidth: 1,
    borderColor: "#416356",
  },
  heroArabic: {
    fontSize: 55,
    lineHeight: 66,
    color: C.green,
    textAlign: "center",
    fontWeight: "700",
    transform: [{ rotate: "-8deg" }],
  },
  artCaption: {
    fontSize: 8,
    color: C.green,
    letterSpacing: 2.2,
    marginTop: 20,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 10,
  },
  button: {
    backgroundColor: C.green,
    borderRadius: 28,
    paddingHorizontal: 18,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 46,
  },
  buttonText: { fontWeight: "700", fontSize: 12, color: C.bg },
  secondary: {
    backgroundColor: "transparent",
    borderWidth: 1,
    borderColor: C.line,
  },
  metrics: { flexDirection: "row", flexWrap: "wrap", gap: 16, marginTop: 22 },
  metric: {
    flex: 1,
    backgroundColor: C.panel,
    padding: 20,
    borderRadius: 17,
    borderWidth: 1,
    borderColor: C.line,
    gap: 8,
  },
  metricValue: { fontSize: 31, color: C.text, fontWeight: "500" },
  metricLabel: { fontSize: 12, color: C.text, fontWeight: "600" },
  tiny: { fontSize: 10, color: C.muted, lineHeight: 17 },
  sectionHead: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 34,
    marginBottom: 18,
    gap: 10,
    flexWrap: "wrap",
  },
  sectionTitle: {
    color: C.text,
    fontSize: 20,
    fontWeight: "600",
    letterSpacing: -0.4,
  },
  twoColumns: { flexDirection: "row", gap: 16 },
  card: {
    backgroundColor: C.panel,
    borderWidth: 1,
    borderColor: C.line,
    padding: 22,
    borderRadius: 18,
    gap: 17,
  },
  cardTitle: {
    fontSize: 21,
    lineHeight: 28,
    color: C.text,
    fontWeight: "500",
    letterSpacing: -0.3,
  },
  featureIcon: { fontSize: 28, color: C.emerald },
  pill: {
    fontSize: 8,
    color: C.emerald,
    backgroundColor: C.panel2,
    paddingHorizontal: 9,
    paddingVertical: 6,
    borderRadius: 15,
    letterSpacing: 1,
  },
  muted: { color: C.muted, fontSize: 13, lineHeight: 22 },
  link: { color: C.green, fontSize: 12, fontWeight: "600" },
  footer: {
    borderTopWidth: 1,
    borderColor: C.line,
    marginTop: 40,
    paddingTop: 24,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    flexWrap: "wrap",
  },
  bottomNav: {
    flexDirection: "row",
    borderTopWidth: 1,
    borderColor: C.line,
    backgroundColor: C.bg,
    paddingBottom: 5,
    paddingTop: 8,
  },
  bottomItem: {
    flex: 1,
    alignItems: "center",
    gap: 4,
    padding: 7,
    minHeight: 52,
  },
  input: {
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 11,
    padding: 14,
    color: C.text,
    fontSize: 14,
    backgroundColor: C.bg,
    minHeight: 48,
  },
  fieldLabel: { color: C.muted, fontSize: 11, textTransform: "capitalize" },
  chip: {
    paddingHorizontal: 15,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 25,
  },
  chipActive: { backgroundColor: C.green, borderColor: C.green },
  wordGrid: { flexDirection: "row", flexWrap: "wrap", gap: 16 },
  wordCard: {
    width: "100%",
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 18,
    padding: 22,
    backgroundColor: C.panel,
    gap: 10,
  },
  arabic: {
    fontSize: 32,
    color: C.text,
    textAlign: "right",
    writingDirection: "rtl",
    lineHeight: 50,
    marginVertical: 10,
  },
  wordEnglish: { fontSize: 18, color: C.text, lineHeight: 26 },
  notePreview: {
    fontSize: 12,
    lineHeight: 19,
    color: C.gold,
    borderTopWidth: 1,
    borderColor: C.line,
    paddingTop: 12,
  },
  notice: {
    backgroundColor: C.panel2,
    borderWidth: 1,
    borderColor: C.emerald,
    padding: 14,
    borderRadius: 12,
    marginBottom: 18,
    flexDirection: "row",
    gap: 14,
  },
  warning: { color: C.gold, fontSize: 12, lineHeight: 20 },
  checkRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  checkbox: { fontSize: 26, color: C.green },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,.75)",
    justifyContent: "center",
    alignItems: "center",
    padding: Platform.OS === "web" ? 20 : 10,
  },
  modal: {
    width: "100%",
    maxWidth: 650,
    maxHeight: "94%",
    backgroundColor: C.bg,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 24,
    overflow: "hidden",
  },
  hiddenCard: {
    backgroundColor: C.panel,
    padding: 25,
    borderRadius: 16,
    alignItems: "center",
    gap: 18,
  },
});

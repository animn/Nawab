import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useVideoPlayer, VideoView } from "expo-video";
import type { Segment } from "./domain";
import { C } from "./theme";
import { request } from "./api";
import { sentenceVideoPath, videoSourceKey } from "./video";

type Props = {
  base: string;
  token: string;
  path: string;
  segment?: Segment;
  showText?: boolean;
  label?: string;
  onPlay?: () => void;
};
export function SentenceVideo({
  base,
  token,
  path,
  segment,
  showText = true,
  label = "Sentence video",
  onPlay,
}: Props) {
  const [open, setOpen] = useState(false);
  return (
    <View style={s.box}>
      <View style={s.row}>
        <Text style={s.label}>{label.toUpperCase()}</Text>
        {segment && (
          <Text style={s.meta}>
            {segment.start.toFixed(2)}–{segment.end.toFixed(2)}s in original
          </Text>
        )}
      </View>
      {open ? (
        <>
          <VideoPlayback
            base={base}
            token={token}
            path={path}
            onPlay={onPlay}
          />
          <Pressable
            accessibilityRole="button"
            onPress={() => setOpen(false)}
            style={s.button}
          >
            <Text style={s.text}>Close video</Text>
          </Pressable>
        </>
      ) : (
        <Pressable
          accessibilityRole="button"
          onPress={() => setOpen(true)}
          style={s.preview}
        >
          <Text style={s.symbol}>▷</Text>
          <Text style={s.text}>
            Load {segment ? "sentence clip" : "original video"}
          </Text>
          <Text style={s.meta}>
            Private source video · loads only when you choose
          </Text>
        </Pressable>
      )}
      {segment && showText && (
        <View style={{ gap: 8 }}>
          <Text style={s.arabic}>{segment.arabic}</Text>
          <Text style={s.meaning}>{segment.english}</Text>
          {!!segment.transliteration && (
            <Text style={s.transliteration}>{segment.transliteration}</Text>
          )}
          {!!segment.explanation && (
            <Text style={s.meta}>{segment.explanation}</Text>
          )}
        </View>
      )}
      {segment && !showText && (
        <Text style={s.meta}>
          Transcript and meaning are hidden for recall. Reveal the phrase to
          check.
        </Text>
      )}
    </View>
  );
}
function VideoPlayback({
  base,
  token,
  path,
  onPlay,
}: Pick<Props, "base" | "token" | "path" | "onPlay">) {
  const player = useVideoPlayer(null, (p) => {
    p.loop = false;
    p.audioMixingMode = "doNotMix";
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [loop, setLoop] = useState(false);
  const [rate, setRate] = useState(1);
  const onPlayRef = useRef(onPlay);
  onPlayRef.current = onPlay;
  useEffect(() => {
    const status = player.addListener("statusChange", (e) => {
      setLoading(e.status === "loading");
      if (e.status === "error")
        setError(
          "Video playback failed. Check your session and connection, or retry after the clip is available.",
        );
    });
    const playing = player.addListener("playingChange", (e) => {
      if (e.isPlaying) onPlayRef.current?.();
    });
    return () => {
      status.remove();
      playing.remove();
    };
  }, [player]);
  useEffect(() => {
    let cancelled = false;
    let objectUrl = "";
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 120000);
    setLoading(true);
    setError("");
    async function load() {
      try {
        if (!path.startsWith("/v1/") || path.includes("://"))
          throw Error("Invalid private video path.");
        const uri = base.replace(/\/$/, "") + path;
        if (Platform.OS === "web") {
          const response = await fetch(uri, {
            headers: { Authorization: `Bearer ${token}` },
            signal: controller.signal,
          });
          if (!response.ok)
            throw Error(
              response.status === 401
                ? "Your session expired. Sign in again to play this video."
                : `Video could not be loaded (${response.status}). Audio-only uploads do not contain video.`,
            );
          const blob = await response.blob();
          if (cancelled) return;
          objectUrl = URL.createObjectURL(blob);
          await player.replaceAsync({
            uri: objectUrl,
            contentType: "progressive",
          });
        } else
          await player.replaceAsync({
            uri,
            headers: { Authorization: `Bearer ${token}` },
            contentType: "progressive",
            useCaching: false,
          });
        if (!cancelled) setLoading(false);
      } catch (e) {
        if (!cancelled) {
          setError(
            controller.signal.aborted
              ? "Video loading timed out. Close and reopen the player to retry."
              : e instanceof Error
                ? e.message
                : "Video could not be loaded.",
          );
          setLoading(false);
        }
      } finally {
        clearTimeout(timer);
      }
    }
    load();
    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(timer);
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [base, token, path, player]);
  return (
    <View style={{ gap: 12 }}>
      {loading && (
        <View style={s.row}>
          <ActivityIndicator color={C.green} />
          <Text style={s.meta}>Loading actual video…</Text>
        </View>
      )}
      {!!error && (
        <Text accessibilityRole="alert" style={s.error}>
          {error}
        </Text>
      )}
      <VideoView
        player={player}
        nativeControls
        contentFit="contain"
        allowsFullscreen
        allowsPictureInPicture={false}
        style={s.video}
      />
      <View style={s.row}>
        {[0.75, 1, 1.25].map((r) => (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: rate === r }}
            key={r}
            onPress={() => {
              player.playbackRate = r;
              setRate(r);
            }}
            style={[s.button, rate === r && s.active]}
          >
            <Text style={s.text}>{r}×</Text>
          </Pressable>
        ))}
        <Pressable
          accessibilityRole="switch"
          accessibilityState={{ checked: loop }}
          style={s.button}
          onPress={() => {
            player.loop = !loop;
            setLoop(!loop);
          }}
        >
          <Text style={s.text}>{loop ? "↻ Loop on" : "↻ Loop off"}</Text>
        </Pressable>
      </View>
    </View>
  );
}
type Source = Segment & {
  job_id: string;
  segment_index: number;
  video_url: string;
};
export function VocabularyVideos({
  base,
  token,
  vocabId,
  showText,
  onPlay,
}: {
  base: string;
  token: string;
  vocabId: string;
  showText: boolean;
  onPlay?: () => void;
}) {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const gate = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  async function load() {
    if (gate.current) return;
    gate.current = true;
    setBusy(true);
    setError("");
    try {
      const data = await request(
        base,
        token,
        `/v1/vocab/${encodeURIComponent(vocabId)}/videos`,
      );
      if (!Array.isArray(data)) throw Error("Invalid video source response.");
      if (mounted.current) setSources(data);
    } catch (e) {
      if (mounted.current)
        setError(
          e instanceof Error ? e.message : "Could not load source clips.",
        );
    } finally {
      gate.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return (
    <View style={{ gap: 16 }}>
      {sources === null ? (
        <Pressable
          disabled={busy}
          accessibilityRole="button"
          onPress={load}
          style={s.button}
        >
          <Text style={s.text}>
            {busy ? "Finding source clips…" : "Show approved sentence videos"}
          </Text>
        </Pressable>
      ) : sources.length ? (
        sources.map((source) => (
          <SentenceVideo
            key={videoSourceKey(source.job_id, source.segment_index, source)}
            base={base}
            token={token}
            path={sentenceVideoPath(source.job_id, source.segment_index)}
            segment={source}
            showText={showText}
            onPlay={onPlay}
          />
        ))
      ) : (
        <Text style={s.meta}>
          No approved video sources are available for this phrase.
        </Text>
      )}
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}
const s = StyleSheet.create({
  box: {
    gap: 15,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 16,
    padding: 16,
    backgroundColor: C.bg,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 10,
  },
  label: {
    color: C.emerald,
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1.6,
  },
  meta: { color: C.muted, fontSize: 12, lineHeight: 20 },
  text: { color: C.text, fontSize: 13 },
  symbol: { color: C.green, fontSize: 36 },
  preview: {
    minHeight: 130,
    justifyContent: "center",
    alignItems: "center",
    gap: 10,
    backgroundColor: C.panel,
    borderRadius: 12,
    padding: 16,
  },
  button: {
    paddingHorizontal: 13,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 25,
    alignSelf: "flex-start",
  },
  active: { backgroundColor: C.panel2, borderColor: C.emerald },
  video: {
    width: "100%",
    height: 260,
    backgroundColor: "#000",
    borderRadius: 12,
  },
  error: { color: C.danger, fontSize: 12, lineHeight: 20 },
  arabic: {
    color: C.text,
    fontSize: 28,
    lineHeight: 44,
    textAlign: "right",
    writingDirection: "rtl",
  },
  meaning: { color: C.text, fontSize: 17, lineHeight: 25 },
  transliteration: { color: C.gold, fontSize: 14, lineHeight: 22 },
});

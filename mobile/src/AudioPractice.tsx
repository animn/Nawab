import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  Platform,
  TextInput,
} from "react-native";
import {
  useAudioPlayer,
  useAudioPlayerStatus,
  useAudioRecorder,
  useAudioRecorderState,
  RecordingPresets,
  AudioModule,
  setAudioModeAsync,
} from "expo-audio";
import { C } from "./theme";
import { fileForm, request } from "./api";
type Props = {
  source?: { uri: string; headers?: Record<string, string> };
  base: string;
  token: string;
  arabic: string;
  vocabId?: string;
  sourceLabel?: string;
  onListen: () => void;
  onRecord: () => void;
  onError: (s: string) => void;
};
export function AudioPractice({
  source,
  base,
  token,
  arabic,
  vocabId,
  sourceLabel = "original sentence audio",
  onListen,
  onRecord,
  onError,
}: Props) {
  const player = useAudioPlayer(null, { updateInterval: 150 });
  const status = useAudioPlayerStatus(player);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const rec = useAudioRecorderState(recorder);
  const [recordingUri, setRecordingUri] = useState<string | null>(null);
  const own = useAudioPlayer(recordingUri);
  const [rate, setRate] = useState(1);
  const [loop, setLoop] = useState(false);
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [audioError, setAudioError] = useState("");
  useEffect(() => {
    let cancelled = false;
    let objectUrl = "";
    setAudioError("");
    if (source) {
      if (Platform.OS === "web") {
        fetch(source.uri, { headers: source.headers })
          .then(async (r) => {
            if (!r.ok) throw Error("Source audio could not be loaded.");
            return r.blob();
          })
          .then((blob) => {
            if (cancelled) return;
            objectUrl = URL.createObjectURL(blob);
            player.replace(objectUrl);
          })
          .catch((e) => {
            if (!cancelled) setAudioError(String(e));
          });
      } else player.replace(source);
    }
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [source?.uri, source?.headers?.Authorization, player]);
  useEffect(() => {
    player.loop = loop;
    player.setPlaybackRate(rate);
  }, [player, loop, rate]);
  useEffect(() => {
    if (status.playing) onListen();
  }, [status.playing]);
  async function play() {
    try {
      await setAudioModeAsync({
        playsInSilentMode: true,
        allowsRecording: false,
      });
      if (status.playing) {
        player.pause();
        return;
      }
      if (status.didJustFinish) await player.seekTo(0);
      player.play();
    } catch (e) {
      onError(String(e));
    }
  }
  async function record() {
    try {
      if (rec.isRecording) {
        await recorder.stop();
        setRecordingUri(recorder.uri);
        await setAudioModeAsync({
          allowsRecording: false,
          playsInSilentMode: true,
        });
        onRecord();
        return;
      }
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!permission.granted)
        throw Error(
          "Microphone permission was not granted. You can still listen and recall.",
        );
      player.pause();
      own.pause();
      setResult("");
      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
      });
      await recorder.prepareToRecordAsync();
      recorder.record();
    } catch (e) {
      onError(String(e));
    }
  }
  async function compare() {
    if (!recordingUri || !vocabId || !transcript.trim()) return;
    setBusy(true);
    try {
      const form = await fileForm(
        recordingUri,
        Platform.OS === "web" ? "practice.webm" : "practice.m4a",
        Platform.OS === "web" ? "audio/webm" : "audio/mp4",
        Platform.OS === "web",
      );
      form.append("transcript", transcript);
      form.append("rights_confirmed", "true");
      const data = await request(
        base,
        token,
        `/v1/vocab/${vocabId}/practice/recording`,
        "POST",
        form,
      );
      setResult(
        `${data.transcript || data.text || "No transcript returned"}${data.similarity !== undefined ? " · Text similarity: " + Math.round(data.similarity) + "%" : ""}. This compares your manually entered text, not pronunciation quality.`,
      );
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <View style={s.box}>
      <Text style={s.label}>LISTEN · REPEAT · MAKE IT YOURS</Text>
      {source ? (
        <>
          <View style={s.row}>
            <Pressable accessibilityRole="button" onPress={play} style={s.play}>
              <Text style={s.playText}>
                {status.playing ? "Ⅱ Pause original" : "▶ Play original"}
              </Text>
            </Pressable>
            {[0.75, 1, 1.25].map((r) => (
              <Pressable
                accessibilityRole="button"
                key={r}
                onPress={() => setRate(r)}
                style={[s.chip, rate === r && s.active]}
              >
                <Text style={s.text}>{r}×</Text>
              </Pressable>
            ))}
          </View>
          <Pressable
            onPress={() => setLoop(!loop)}
            accessibilityRole="switch"
            accessibilityState={{ checked: loop }}
          >
            <Text style={s.muted}>
              {loop ? "↻ Loop on" : "↻ Loop off"} · {sourceLabel}
            </Text>
          </Pressable>
        </>
      ) : (
        <Text style={s.muted}>
          No original audio for this card. Illustrative examples never pretend
          to be video recordings.
        </Text>
      )}
      <View style={s.row}>
        <Pressable
          accessibilityRole="button"
          onPress={record}
          style={[s.chip, rec.isRecording && { borderColor: C.danger }]}
        >
          <Text style={s.text}>
            {rec.isRecording
              ? `■ Stop · ${Math.floor(rec.durationMillis / 1000)}s`
              : "● Record yourself"}
          </Text>
        </Pressable>
        {recordingUri && (
          <Pressable
            style={s.chip}
            onPress={async () => {
              try {
                await own.seekTo(0);
                own.play();
              } catch (e) {
                onError(String(e));
              }
            }}
          >
            <Text style={s.text}>▷ Hear yourself</Text>
          </Pressable>
        )}
      </View>
      {!!audioError && <Text style={s.muted}>{audioError}</Text>}
      {recordingUri && token && vocabId && (
        <>
          <Text style={s.muted}>
            Optional: type what you actually said. Automatic speech
            transcription is not configured.
          </Text>
          <TextInput
            accessibilityLabel="Your spoken transcript"
            value={transcript}
            onChangeText={setTranscript}
            placeholder="Type your spoken Arabic…"
            placeholderTextColor={C.muted}
            style={[s.chip, s.text]}
          />
          <Pressable
            style={s.chip}
            disabled={busy || !transcript.trim()}
            onPress={compare}
          >
            <Text style={s.text}>
              {busy ? "Comparing…" : "Save my recording & compare entered text"}
            </Text>
          </Pressable>
        </>
      )}
      <Text style={s.tiny}>
        Your recording stays on this device unless you choose to send it for
        comparison. The comparison uses text you type; this is not a
        pronunciation score.
      </Text>
      {!!result && <Text style={s.text}>{result}</Text>}
    </View>
  );
}
const s = StyleSheet.create({
  box: { gap: 14, paddingTop: 20, borderTopWidth: 1, borderColor: C.line },
  row: { flexDirection: "row", gap: 8, flexWrap: "wrap", alignItems: "center" },
  label: {
    color: C.emerald,
    fontSize: 10,
    letterSpacing: 2,
    fontWeight: "700",
  },
  play: {
    backgroundColor: C.green,
    paddingHorizontal: 15,
    paddingVertical: 13,
    borderRadius: 30,
  },
  playText: { color: C.bg, fontWeight: "700" },
  chip: {
    borderWidth: 1,
    borderColor: C.line,
    paddingHorizontal: 12,
    paddingVertical: 11,
    borderRadius: 25,
  },
  active: { backgroundColor: C.line, borderColor: C.emerald },
  text: { color: C.text, fontSize: 13 },
  muted: { color: C.muted, fontSize: 13, lineHeight: 21 },
  tiny: { color: C.muted, fontSize: 11, lineHeight: 18 },
});

# Nawab · Kuwaiti Arabic

Nawab 2 adds an Expo Go / mobile web client and a video-to-lesson API alongside the original Streamlit application. Work is on `feature/kuwaiti-video-lessons`; `main` and the existing live app are not replaced.

## What lives where

- `app.py`: existing Streamlit app, unchanged. Its Google Sheets integration, vocabulary IDs, scores, notes and saved audio remain intact.
- `mobile/`: Expo client for iOS, Android and responsive web. A clearly labelled local practice mode works without a server. It keeps its own on-device progress, never represents that progress as migrated from Streamlit, and can refresh the existing public Sheet on demand.
- `api/`: authenticated Python API, persistent import queue, media processing, transcription/learning providers, lesson review, and backwards-compatible SQLite storage.
- `docs/`: architecture, operational readiness and verification notes.

## Development

Mobile:

```sh
cd mobile
npm ci
npm run typecheck
npm test
npx expo start
```

Open the development QR in a compatible Expo Go version. A development QR is not a permanent release. Run `npx expo export --platform web` or `npx expo export --platform ios --platform android` for release bundle checks.

API:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-api.lock
python -m pytest tests/test_api*.py -q
```

See `api/README.md` for actual configuration and launch commands. API secrets belong only in the server's secret manager. Never put passwords, AI API keys or Sheets secrets into `EXPO_PUBLIC_*`, Expo configuration, a mobile bundle or Git.

## Video learning workflow

1. Upload a video file you have permission to process. Public visibility alone is not permission. Direct-link importing is hidden from the client for now.
2. The configured API validates file size and duration, retains the original video, and extracts its audio. Real H264/AAC sentence MP4 clips are paired with their saved transcript and meaning, with private playback, seeking, speed controls and looping. Audio-only uploads never receive invented visuals. Missing hosting or credentials are reported clearly; the client does not pretend processing is available.
3. A configured speech/learning provider produces a draft with sentence timings. Missing configuration or failed processing is shown as such, not replaced with an invented transcript. Manual segment editing remains available.
4. Review the Arabic, timing, transliteration and English explanation against the original speaker. Kuwaiti ASR and AI explanations can be wrong.
5. Approve the reviewed lesson, then optionally save to the existing Google Sheet. Uploading a video does not silently write vocabulary to that Sheet.
6. Loop original sentences, record a reply and practice recall. Transcript similarity is not an acoustic pronunciation score, and cards mastered are not a fluency measurement.

## Preservation and deployment

See [deployment requirements](docs/DEPLOYMENT.md). Before an API deployment reuses real learning records, obtain a verified SQLite backup from the old host and configure its exact path. A clean checkout does not contain the live database. No destructive reset or fabricated migration is part of this project.

Source/build checks are separate from a live end-to-end test. AI-backed import, Google Sheet writes, microphone behavior and physical Expo Go opening require their respective configured services and device checks. The legacy Streamlit security and design pull requests remain separate; this feature branch does not claim to deploy them.

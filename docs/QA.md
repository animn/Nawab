# Verification record

Verified in the cloud on 2026-11-04. This is not a declaration that all deployment requirements are complete.

## Passed

- 66 API/deployment/backup tests, including authenticated access, rejected unsafe URLs, pinned public network destinations, media bounds, SQLite migration/backup and preservation, interrupted-job recovery, explicit approval, duplicate-aware Sheets outbox and actual FFmpeg operations against synthetic media. Video tests verify H264/AAC output, timestamped clips, Range/206/416, authenticated range requests, silent-video/manual captions, audio-only fallback, disk headroom, and approval failure safety.
- 14 client tests and TypeScript typecheck. Regression fixtures include the exact legacy Sheet headers (spaces, hyphens and invisible Unicode marks), repeat imports preserving scores/notes and unknown audio fields, URL validation, text-similarity labeling, and saved-segment/video pairing.
- Expo production exports for web, iOS and Android using SDK 54 after compatibility migration; Expo Doctor 18/18, client tests and typecheck pass. SDK 54 is intentional for standard iPhone App Store Expo Go compatibility. Export success is not a physical-device runtime test.
- Python compilation and exact original app.py blob check against feature-branch baseline 2d8b8a05cf85bf97262360de545655b9b596ac92.
- Managed cloud browser: desktop and 500-pixel narrow layout, bottom-tab navigation, recall/reveal, saved notes, reload persistence, vocabulary search and disabled no-backend lesson import state.
- Real existing public Google Sheet read: 353 CSV rows, resulting in 311 distinct Arabic vocabulary entries. Browser import succeeded; the three explicitly labeled illustrative starter examples remained separate. Existing local progress and a QA-only note survived the import. No Sheet writes occurred.
- Synthetic runtime backup/recovery drill preserves original IDs, scores, notes, saved audio, extra legacy columns and media checksums; detects media corruption; rejects active jobs and overwrites. Modern runtime restoration also checks original video/audio, practice recordings and sentence-asset paths after the original synthetic files are moved away. Missing referenced files or manifest omissions fail verification. No real user runtime backup or restore was performed.
- Cloud-browser isolated video API: authenticated sentence MP4 visibly plays beside matching Arabic/meaning; 1.25× speed, looping and Close work; audio-only lesson clearly reports no video and plays its actual audio. This uses synthetic local media and manually supplied text, not a paid-provider transcription test.
- Approved vocabulary source-video playback and hidden/revealed text work. Synthetic server notes survive reload and re-login, session tokens clear on reload, and the existing 314-entry local collection remains unchanged. Upload storage/AI-processing disclosure is visible. Temporary QA servers were stopped afterward.

## Not yet verified or released

- No live Python API host, TLS endpoint, AI provider credentials or real historical database were available. The Docker recipe has not been built in this environment.
- Real-provider Kuwaiti transcription has not been exercised. Direct TikTok import is hidden; authorized upload and manual transcript review are the supported client workflow.
- No real learner data migration or Google Sheets write-back was performed.
- Native device execution is separate from successful Expo publication. Remote simulator availability for this account returned false; no paid simulator session was started.
- Native microphone/audio behavior still requires a physical Expo Go device test after publication.
- Native video playback also needs a physical-device check. Browser playback and bundle export are not evidence of iOS/Android hardware behavior.
- AI transcription accuracy and timestamps require human review. Text comparison is not pronunciation scoring.

See DEPLOYMENT.md and api/README.md for the remaining host, data and credential requirements. Do not merge into main solely on the basis of these local results.

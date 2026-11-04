# Verification record

Verified in the cloud on 2026-11-04. This is not a declaration that all deployment requirements are complete.

## Passed

- 38 API tests, including authenticated access, rejected unsafe URLs, pinned public network destinations, media bounds, SQLite migration/backup and preservation, interrupted-job recovery, explicit approval, duplicate-aware Sheets outbox and actual FFmpeg operations against synthetic media.
- 11 client tests and TypeScript typecheck. Regression fixtures include the exact legacy Sheet headers (spaces, hyphens and invisible Unicode marks), repeat imports preserving scores/notes and unknown audio fields, URL validation and text-similarity labeling.
- Expo production exports for web, iOS and Android using SDK 54 after compatibility migration; Expo Doctor 18/18, client tests and typecheck pass. SDK 54 is intentional for standard iPhone App Store Expo Go compatibility. Export success is not a physical-device runtime test.
- Python compilation and exact original app.py blob check against feature-branch baseline 2d8b8a05cf85bf97262360de545655b9b596ac92.
- Managed cloud browser: desktop and 500-pixel narrow layout, bottom-tab navigation, recall/reveal, saved notes, reload persistence, vocabulary search and disabled no-backend lesson import state.
- Real existing public Google Sheet read: 353 CSV rows, resulting in 311 distinct Arabic vocabulary entries. Browser import succeeded; the three explicitly labeled illustrative starter examples remained separate. Existing local progress and a QA-only note survived the import. No Sheet writes occurred.

## Not yet verified or released

- No live Python API host, TLS endpoint, AI provider credentials or real historical database were available. The Docker recipe has not been built in this environment.
- Live TikTok extraction and real-provider Kuwaiti transcription have not been exercised. Providers can reject downloads; authorized upload and manual transcript review are supported fallbacks.
- No real learner data migration or Google Sheets write-back was performed.
- Native device execution is separate from successful Expo publication. Remote simulator availability for this account returned false; no paid simulator session was started.
- Native microphone/audio behavior still requires a physical Expo Go device test after publication.
- AI transcription accuracy and timestamps require human review. Text comparison is not pronunciation scoring.

See DEPLOYMENT.md and api/README.md for the remaining host, data and credential requirements. Do not merge into main solely on the basis of these local results.

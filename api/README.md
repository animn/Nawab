# Nawab mobile API

Python 3.12+, ffmpeg/ffprobe and `requirements-api.txt` are required. Start with
`uvicorn api.main:app --host 0.0.0.0 --port 8000`. Interactive contract: `/docs`.
No credentials are bundled. All `/v1` endpoints, including audio, require Bearer authentication.

## Operator setup

- `NAWAB_DB_PATH`: persistent path to **the original** `learning_progress_v8.db`. Default is that name in the working directory; `NAWAB_DB` remains an alias. Mount a verified original backup before production deployment. No actual user database was available during development, so only synthetic migration has been tested.
- `NAWAB_MEDIA_DIR`: persistent private media directory (default `nawab_media`). Back up this and the database together. Original media, audio and recordings are retained; do not expose the directory as static public files.
- `NAWAB_PASSWORD`: owner password, at least 12 characters. `NAWAB_TOKEN_SECRET`: random secret, at least 32 characters. Both are required; absent/short configuration fails closed. Supply through your hosting secret manager, never commit them or put them in Expo public variables. Rotating the token secret invalidates all 12-hour sessions.
- Serve HTTPS behind a trusted TLS reverse proxy. Only trust forwarded headers from that proxy (`uvicorn --forwarded-allow-ips=<proxy IP>`), never arbitrary clients. Remote HTTP is rejected by default. `NAWAB_REQUIRE_HTTPS=false` is for development on a private LAN only. Loopback is allowed for testing. `NAWAB_CORS_ORIGINS` is a comma-separated explicit web origin allowlist; no CORS origins are allowed by default. Native Expo does not need browser CORS.
- Enforce a 32 MB request limit and rate limits at the ingress too. App limits are 30 MB per media file, 180 seconds, two processing slots, 25 pending jobs, and 10 login attempts/minute. Use one API process/replica for the durable local SQLite queue. Multiple API processes are not supported: startup deliberately marks interrupted jobs failed.
- `SHEET_URL`: public Google Sheets CSV export URL (defaults to the existing app's Sheet). Import is explicit and preserves IDs, notes, scores and saved audio. Run an import before first writeback to recognize already-existing Sheet entries. Only Google HTTPS endpoints are accepted.
- `SHEET_APPEND_WEBHOOK_URL` and `SHEET_APPEND_SECRET`: optional existing Apps Script append integration. No write occurs until explicit lesson approval with `write_to_sheet:true`. Formula-leading values are escaped. Payload preserves existing `secret` + `entry` contract and adds `operation_id`; `Idempotency-Key` header matches. Webhook should deduplicate by `operation_id` or Arabic MD5. Local persistent outbox prevents duplicate dispatch. A timeout is **uncertain**, never automatically retried; inspect the Sheet before operator reconciliation. Do not delete the outbox to retry blindly. For multiple independent clients/databases, server-side webhook idempotency is mandatory.
- AI is disabled by default. Explicitly enable `NAWAB_ENABLE_AI=true` and select `NAWAB_AI_PROVIDER=gemini` or `openai`, with the matching server `GEMINI_API_KEY` / `OPENAI_API_KEY`, only after authorizing provider costs and transmission of the source audio. The app itself never enables/configures paid access. Models may be overridden with `GEMINI_TRANSCRIPTION_MODEL`, `OPENAI_TRANSCRIPTION_MODEL`, `OPENAI_LESSON_MODEL`. Default: Gemini 2.5 Flash. OpenAI has no implicit transcription model default: explicitly set `OPENAI_TRANSCRIPTION_MODEL=whisper-1` only for the compatibility path, with GPT-4.1 mini enrichment. OpenAI has announced whisper-1 retirement February 26, 2027; the current replacement transcription API does not supply equivalent segment timestamps. Prefer configured Gemini or manual transcription, and validate any future timestamp-capable replacement before deployment. See [OpenAI speech-to-text documentation](https://developers.openai.com/api/docs/guides/speech-to-text). Missing/disabled AI leaves extracted audio in `needs_configuration` and accepts manual timestamped text. Generated content always requires review.

## Data safety

Startup adds missing columns/tables without deleting legacy columns. Before first API migration of an existing vocabulary database, a consistent SQLite backup is written beside it as `.pre-api-<timestamp>.bak`. IDs remain MD5 of stripped Arabic UTF-8. Review behavior remains correct +1, incorrect resets to zero. Approved words use original source audio only if no saved audio exists; existing Azure/custom audio is retained.

Jobs persist `queued`, `processing`, `needs_configuration`, `needs_review`, `failed`, or `approved`. Background processing starts after submission; restart changes interrupted jobs to failed, with explicit retry. TikTok login/CAPTCHA/private-content restrictions are not bypassed. Download failures offer authorized file upload. URLs, redirect destinations and all extractor HTTP requests use public-IP-pinned HTTPS transport with verified TLS; media parsing disallows playlists/network inputs. Limits are enforced before AI calls. This does not replace regular dependency/security updates or host isolation.

Manual segments have `start`, `end` seconds, `arabic`, `english`, `transliteration`, `explanation`. A nonempty transcript within media duration is required before approval. Original source URLs, timestamps, media and vocabulary associations are retained separately from legacy vocabulary.

Speaking practice is **transcript text similarity**, never pronunciation, fluency, accent or acoustic scoring. The recording endpoint requires an actual user-supplied transcript, stores the recording, and returns the transparent text measurement. It does not pretend to have listened to an untranscribed recording.

## Contract

- `POST /auth/login {password}` → `{access_token, token_type, expires_in}`
- `GET /health` → configuration booleans only.
- `GET /v1/vocab` → legacy vocabulary fields, `has_audio`.
- `POST /v1/vocab/{id}/review {correct}`; `PUT .../notes {notes}`; `GET .../audio`.
- `POST /v1/jobs {url,rights_confirmed:true}` or multipart `POST /v1/jobs/upload` with `file`, `rights_confirmed`, optional `source_url`.
- `GET /v1/jobs`; `GET /v1/jobs/{id}`; `POST .../retry`.
- `PUT /v1/jobs/{id}/segments {segments:[...]}`; `GET .../segments/{index}/audio`.
- `POST /v1/jobs/{id}/approve {approved:true,write_to_sheet:false}` → saved IDs and individual Sheet results.
- `POST /v1/sheets/import`; `GET /v1/sheets/status`.
- `POST /v1/vocab/{id}/practice {transcript}` or multipart `.../practice/recording` with `file`, `transcript`, `rights_confirmed`; `GET /v1/practice/{id}/audio`.

Tests: `python -m pytest tests/test_api*.py -q`. They use synthetic data, mocked providers/Sheets and local ffmpeg media; no paid provider calls or real Sheet writes. Deployment, real TikTok availability and real-provider transcription require separate authorized smoke tests in the hosting environment.

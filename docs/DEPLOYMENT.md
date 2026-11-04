# Deployment and data-preservation checklist

## Independent release surfaces

The Expo mobile application, its private web build, and the Python processing API are separate deployments. Publishing the client alone does not activate TikTok downloading or AI transcription.

The existing Streamlit application is not replaced by the new web build. Do not merge or deploy `main` as part of a preview release.

## Required API host

Use a host able to run Python, FFmpeg and yt-dlp with a persistent filesystem. Cloudflare Workers / static Sites cannot execute these processing binaries. Do not deploy a SQLite database to ephemeral storage and call it preserved.

Before enabling real imports:

- Verify HTTPS, explicit CORS origins, authentication and unauthenticated media rejection.
- Configure the server password and signing secret securely with the owner's authorization. Do not paste credentials into chat or commit them.
- Configure the selected AI provider and budget. No subscription, paid hosting or new API credentials are provisioned by the source build.
- Confirm persistent database and media paths, retention, restricted filesystem permissions, backups and recovery.
- Configure the existing Sheets receiver URL and secret only on the server. Verify receiver-side authorization and literal-text writes before enabling write-back.
- Preserve any stricter existing Streamlit hosting access controls; API authentication does not secure the legacy app.

## Live data migration

1. Obtain the live `learning_progress_v8.db` through the original host's supported export/backup path. The repository contains code, not these learning records.
2. Use SQLite's backup facility while writers are active. Preserve the original backup unchanged and record its SHA-256 checksum.
3. Validate the backup with `PRAGMA integrity_check`, then count vocabulary, scores, notes and nonempty audio before migration.
4. Copy it into the API's persistent volume, explicitly configure the database path and run additive migrations. Preserve the same `md5(arabic)` vocabulary identifiers.
5. Recount and sample records after migration. Confirm Sheet refresh does not overwrite notes, scores or saved audio.
6. Test a new disposable practice record and verify both persistent storage and backup recovery. Never test a destructive reset on the real data.

If the database is unavailable, continue to offer local learning and public Sheet reads. Label on-device data as separate; do not imply historical progress was recovered.

## Release verification

- Backend tests, Python compilation, client typecheck and unit tests pass on the final source commit.
- Web, iOS and Android production exports complete.
- Mobile layout is visually inspected; slow requests, repeated taps, failed imports, dismissed dialogs, login failure and storage reloads are checked.
- Public read-only `/health` does not leak secret material. All learner data/media endpoints reject missing or invalid credentials.
- A rights-cleared Kuwaiti clip is processed using the real configured provider. A human checks Arabic and segment boundaries; a successful mocked test is not this check.
- The original speaker's audio plays and loops. Native microphone permission, recording/playback and interruption behavior are checked on iPhone/Android.
- An approved sentence reaches the existing Sheet once; retries cannot silently duplicate writes.
- The exact source commit is on the feature branch and its CI is green before any merge discussion.
- A hosted Expo update is read back for the intended project, branch, SDK and platform; never relabel a web link as an Expo Go link.

## Privacy

Learning progress and notes are private runtime records. They are not bundled with public source or uploaded to Expo. Only media deliberately submitted for processing is sent to the configured AI provider. Obtain rights before submitting third-party media and consent before recording another speaker. Do not upload confidential workplace meetings to a third-party AI service without the appropriate permission.

## Optional Docker deployment

`compose.yaml` deliberately binds only to loopback. A production host must supply a properly configured HTTPS reverse proxy and persistent `runtime-data` directory. Put the verified legacy database into that directory before first startup; do not create a fresh empty runtime directory and mistake it for migration. Put server values into an untracked `.env`, following `api/README.md`. Review and authorize the final host, network exposure, storage, credentials and any paid commitment before deploying.

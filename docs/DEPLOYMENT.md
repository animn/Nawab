# Deployment and data-preservation checklist

## Independent release surfaces

The Expo mobile application, its private web build, and the Python processing API are separate deployments. Publishing the client alone does not activate uploaded-video processing or AI transcription. Direct TikTok-link import is hidden from the client.

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

## Proposed Render deployment

`render.yaml` is a deployment recipe, not evidence that a service exists. It proposes one Docker web service on `feature/kuwaiti-video-lessons`, Frankfurt, plan `1c-2g` (1 CPU / 2 GB), with a 5 GB persistent disk at `/data`. Auto-deployment is off. The original Streamlit app and `main` stay untouched. AI remains disabled until its provider, credentials, data transmission and spending are authorized.

Public prices checked November 4, 2026: compute $25/month and disk $1.25/month, totaling **$26.25/month before tax, AI and usage overages**. The Hobby workspace has no subscription fee and includes 5 GB outbound bandwidth/month, then $0.15/GB; standard builds include 500 minutes/month, then $5/1,000 minutes. Confirm the actual workspace plan, payment method, final price and terms before creating resources. The 512 MB plan is cheaper but has not been qualified for this video workload. Free services cannot attach persistent disks and lose local runtime data on restarts.

Sources: [Render pricing](https://render.com/pricing), [compute plans](https://render.com/docs/compute-plans), [persistent disks](https://render.com/docs/disks), [workspace billing details](https://render.com/articles/how-much-does-cloud-application-hosting-cost-for-small-businesses).

Provisioning prerequisites:

1. Verify the connected Render workspace and repository access. Review the exact feature-branch commit and its passing CI.
2. Obtain approval for the recurring service/storage charge and any visible terms. Do not upgrade the workspace or add resources automatically.
3. Configure the owner password and session-signing secret only through the approved secure secret-management flow. No credential is generated by the recipe. Do not put secrets in chat, source, Expo variables, logs, or a deployment archive.
4. Verify the host's actual trusted proxy IPs/CIDRs and set `FORWARDED_ALLOW_IPS`; wildcard trust is rejected. `scripts/start-api.sh` supports the host's `PORT` and enforces one API worker. HTTP is accepted only for the read-only health check and loopback development; learning/auth/media routes remain HTTPS-only.
5. Verify the non-root process can write to `/data`, not to a public static directory. If mount ownership is wrong, correct only the intended volume through an authorized setup action; do not make it world-writable or run the application as root.
6. Supply a verified original database backup before migration. If unavailable, explicitly label the new server collection as separate and retain the original app/on-device progress. A public Sheet import does not restore historical notes, scores or recordings.
7. Select and authorize the AI provider/model and audio transmission. The legacy app expects a Gemini key in its own host's secret store, but this is not proof that an accessible or billable key exists. Moving an existing key into Render is new ongoing access and needs approval.
8. Validate upload, full/segment MP4 playback including seeking, transcript/meaning review, explicit approval, unauthorized access rejection, restart persistence and backup recovery on the live service before calling processing operational.

Render disks are single-instance, and deployments involving them have downtime. Disk-backed services do not permit a custom shutdown delay; interrupted processing remains visibly failed and can be explicitly retried. Do not add replicas or a separate worker against this SQLite queue. Preserve the media directory and database together. Automatic disk snapshots are not a substitute for a verified database-native backup.

### AI configuration and cost

Use an explicitly configured, currently supported timestamp-capable model. `gemini-2.5-flash` is deprecated and restricted to prior users; new installations must not silently select it. A candidate for the first authorized smoke test is `gemini-3.5-flash-lite`, supporting audio and structured text. Its listed paid rate is $0.30 per million input tokens and $2.50 per million output tokens; real cost depends on clip length and generated text. Verify Kuwaiti accuracy and boundary quality on a rights-cleared sample before accepting it. Current adapters do not require uploading video frames to the AI service: only extracted audio is sent, and the server cuts the original video locally.

Gemini's paid tier states prompts/responses are not used to improve Google products; the free tier may use them. New paid accounts may require a minimum $5 prepayment. Obtain approval before enabling billing, automatic top-ups or paid requests. An app output-token limit is not an account spending cap; do not promise a hard dollar cap without verifying the provider's actual billing controls.

Sources: [Gemini model](https://aistudio.google.com/docs/models/gemini-3.5-flash-lite), [pricing](https://aistudio.google.com/docs/pricing#gemini-3.5-flash-lite), [billing](https://ai.google.dev/gemini-api/docs/billing/), [deprecations](https://aistudio.google.com/docs/deprecations).

## Verified runtime backup procedure

Pause new requests and wait for processing/Sheet writes to finish. Run the bundled tool against a quiesced runtime:

```sh
python scripts/backup_runtime.py create \
  --database /data/learning_progress_v8.db --media /data/media \
  --destination /data/backups/unique-snapshot-name --quiesced
python scripts/backup_runtime.py verify /data/backups/unique-snapshot-name
```

The tool uses SQLite's backup API, rejects active jobs and symlinks, refuses to overwrite existing snapshots, checks database integrity and record counts, and hashes every copied media file. It checks every job original/audio, practice recording and video-asset reference against the backed-up media tree; missing references prevent a successful verification. It records the original database and media mount paths. It creates the manifest last; a directory without a valid manifest is incomplete. It never deletes originals. The operator must actually pause writers: `--quiesced` is an assertion, not a remote maintenance command.

For a recovery drill, first verify the snapshot, then use an **isolated disposable environment mounted at the same absolute database and media paths recorded in the manifest**. Copy `database.sqlite3` to that environment's `learning_progress_v8.db` and its `media` tree to the original media mount path. API records contain absolute file paths: copying the database to an arbitrary directory does not relocate those references. No automatic rebasing is provided. The original live filesystem must be inaccessible during the drill so playback cannot fall back to it. Run additive migrations and verify job video/audio, practice recordings, sentence assets, scores, notes, extra legacy columns and media checksums. Only restore to the live `/data` paths after a verified drill and an explicitly approved recovery operation; preserve the pre-restore runtime. Store a verified off-host copy only at an authorized destination. Backups on the same disk do not protect against losing that disk. No scheduled backup, off-host upload, destructive retention rule or live restore is enabled by this recipe.

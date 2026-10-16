# Security review — 9 October 2026

Reviewed baseline: `2d8b8a05cf85bf97262360de545655b9b596ac92`
(last commit 18 September 2026). No open PR was found at the start of this review.
This is a configuration/code review, not evidence of a breach or a penetration
test of the deployed service.

## Findings and changes

| Finding | Patch |
| --- | --- |
| Devcontainer explicitly disabled CORS and XSRF | Enable both in launch flags and committed Streamlit config |
| Development server had no explicit loopback bind and automatically opened a preview | Bind to 127.0.0.1; notify about forwarded port; document Private visibility |
| No app-level access control before sheet reads, shared database work or paid services | Fail-closed shared-password gate before initialization; sign out; constant-time comparison; remove submitted password from session state |
| Streamlit callbacks run before the main script | Recheck authorization inside the note callback and mutation/service entry points; old password sessions lose access after rotation |
| Gemini API key appeared in request URLs | Send it through the x-goog-api-key header; do not follow Gemini/Azure redirects |
| Provider errors and webhook messages could be rendered verbatim | Use bounded generic messages/status codes; suppress uncaught browser exception detail |
| Sheets webhook could follow arbitrary redirects with a secret-bearing body | Require HTTPS; follow only Apps Script's HTTPS response-host 302/303 using a fresh GET without credentials/body; reject 307/308 |
| Dynamic sheet/AI text inserted into HTML | Escape chapter/Arabic display values; escape SSML voice attributes and validate Azure region |
| No ignore rules for local secrets/progress | Ignore Streamlit secrets, environment files and SQLite databases |

## Confirmed scope and uncertainty

- The app uses one shared SQLite database. The gate intentionally protects the
  entire app; it does not introduce user accounts, roles or per-user progress.
- The Google Sheet CSV URL is hard-coded in public source. This patch does not
  make that sheet private. Its actual sharing/export permissions were not tested.
- The Sheets receiver is not in this repository. The client already required a
  nonempty secret; that does not prove the receiver checks it. Verify the receiver
  rejects missing/wrong secrets **before** writing, stores its secret server-side,
  treats vocabulary fields as plain text, and only writes to the intended sheet.
- At the initial review, no live URL or hosting access was available. The
  October 13 follow-up below verifies that the supplied live UI can be reached
  from the review browser without an app-password prompt. Hosting-account
  permissions, effective runtime flags, direct origin/port exposure, access logs
  and receiver-side authentication remain unverified.
- CORS/XSRF are not login controls. A private Codespace/cloud app may already have
  restricted access, while a publicly exposed instance of the old code would not
  have an app-level barrier against using services or changing shared progress.
- No real API calls, webhook writes or credential rotation were performed.

A limited pattern scan of 49 historical Git blobs found no recognized private
keys, Google API keys or GitHub tokens. Literal credential matches were
placeholder-like strings. This is not proof that no secret was ever exposed;
unknown key formats, hosting secrets and logs were outside that scan.

## Before rollout

1. Set a unique random APP_PASSWORD (20+ characters; 32 random bytes recommended)
   in the hosting secret store, then deploy the reviewed branch. Do not paste
   secrets into GitHub, issues, screenshots or logs.
2. Confirm HTTPS, intended viewers and Private forwarded-port visibility. For
   Internet hosting, use platform authentication/rate controls or an authenticated
   proxy in addition to this small personal-app gate. Do not share the password
   with untrusted users; authorized sessions can spend API quota.
3. Inspect effective CORS/XSRF settings and all startup/environment overrides.
   Verify the actual external hostname/port and WebSocket proxy route.
4. In a signed-out/private browser, check the real app URL: it must show a hosting
   access denial or the app sign-in screen, with no learning data or service UI.
   Check any direct origin/port too; verify the proxy also protects WebSockets.
5. Sign in and check flashcards, scoring, notes, AI generation and audio. With an
   approved disposable entry, verify Google Sheets write-back and receiver-side
   rejection of a wrong secret. These live integration checks remain outstanding.
6. Apply least-privilege service credentials and provider quotas/budget alerts.
   Review historical logs for URL-embedded Gemini keys; rotate any credential
   found exposed. Do not log request bodies/headers or raw provider errors.

If rollout fails, keep the app private/stop it while fixing the hostname or
secret setup. Do not restore disabled protections or an anonymous bypass.

## Validation

Offline pytest regressions cover missing/short credentials, anonymous access,
wrong-password rejection, sign-in/rerun/sign-out, password rotation, protected
callbacks and service functions, local score/note persistence, Gemini header
credentials, sanitized responses, missing Sheets secrets, insecure endpoints,
unsafe redirects and the normal Apps Script redirect. AppTest verifies all five
app tabs still initialize after authorized sign-in with mocked reference data.
Local validation: 27 tests passed on Python 3.12 / Streamlit 1.65.0. A separately
started local Streamlit server returned HTTP 200 for health, accepted a same-origin
WebSocket and rejected an untrusted-origin WebSocket with HTTP 403. The CI workflow
runs the regression suite on Python 3.11. These are not live deployment/proxy tests
or real-provider compatibility guarantees.

## Live follow-up — 13 October 2026

The owner supplied https://chalechalo.streamlit.app/ after the initial review.
At approximately 06:08 UTC, the app was opened in the reviewer's cloud browser.
It initially showed Streamlit's inactivity/sleep screen; the normal wake button
was used and the app loaded successfully.

- No sign-in was performed during this visit and no app-password prompt appeared.
  The learning dashboard, all five tabs and the Inbox's Process Word control were
  visible. This verifies UI reachability from this browser; it does not establish
  every hosting access rule or independently prove a cookie-free private session.
- The dashboard showed 311 Needs Practice, 0 Learning and 0 Mastered. Those values
  alone are not evidence of lost progress.
- No vocabulary was submitted, no score/note was saved, no sync was triggered,
  and no paid provider or Sheets write-back action was tested. The test does not
  prove unauthorized mutations or credential exposure, and is not a breach finding.
- PR #1 remained draft, open and unmerged at head
  `8a656db3cf0dee309f9951a5be8ce6ac3d8eca55`. Its Security regressions workflow
  completed successfully, including the pytest step:
  https://github.com/animn/Nawab/actions/runs/37901627004/job/113725282262 .
- The reviewable code patch is complete. Production rollout is still pending:
  the owner must securely configure APP_PASSWORD before authorizing merge/deploy.
  Do not paste it into chat or GitHub. GitHub repository access does not grant
  Streamlit hosting administration or authorize credential changes.
- Post-deployment verification of the password gate, authenticated learning flows,
  effective CORS/XSRF settings and Sheets receiver authentication remains required.
  Preserve/backup learning data before any hosting restart or deployment; the
  existing shared local SQLite database is not a durable cloud backup.

## References

- https://docs.streamlit.io/develop/api-reference/configuration/config.toml
- https://docs.streamlit.io/knowledge-base/deploy/remote-start
- https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/share-your-app
- https://ai.google.dev/api

## Merge-readiness follow-up — 17 October 2026 (Kuwait)

Reviewed PR head: `cc39a0e708956a33eb046a0555cafc274abb967b`.
GitHub reported open, draft, unmerged and mergeable, with no completed reviews.
Contrary to the uncertainty from the empty combined-status response, the Actions
API confirms a successful Security regressions run for this exact head, including
its pytest step: https://github.com/animn/Nawab/actions/runs/38355093658 .
That result predates the corrections below; require green CI on the new head too.

### Corrections from this review

- Add authorization wrappers outside the Sheets-read and gTTS caches, including
  cache clearing, so cache hits cannot skip the service-entry authorization check.
  This closes a defense-in-depth gap; the existing top-level login gate already
  protects normal UI entry. Limit cached fallback audio to 512 entries.
- Reject vocabulary fields beginning with `=` (including after whitespace) before
  Sheets write-back. Apps Script spreadsheet writes can interpret these as formulas.
  This is client-side defense, not proof the absent receiver is safe. It must also
  authenticate every write and store fields as literal text. Other spreadsheet/CSV
  consumers can have additional formula conventions; exports need their own review.
- Fail closed with a generic response for malformed webhook URLs, embedded URL
  credentials and nonstandard HTTPS ports. The configured host remains an owner
  trust decision; HTTPS is not a host allowlist. Google Apps Script uses port 443.
- Add regressions for these paths, Azure region validation/SSML escaping/no redirects,
  and a populated flashcard with HTML-like input plus the reference-refresh UI.
  Clear shared Streamlit caches between app tests to prevent empty-fixture reuse.
- Expand CI to Python 3.11 and 3.12. Local validation: **49 passed**, Python 3.12.14,
  Streamlit 1.66.0, pandas 3.0.6. No live provider calls or real Sheets writes.

### Decision and evidence needed

**Keep this PR draft; do not merge or deploy until hosting conditions are verified.**
The URL is recorded as https://chalechalo.streamlit.app/ in the October 13 notes;
this follow-up did not revisit it or establish current runtime controls. An HTTPS
URL in documentation is not a live TLS or access-control verification.

| Requirement | GitHub evidence | Remaining confirmation |
| --- | --- | --- |
| APP_PASSWORD | Code rejects missing/short values before initialization | Host administrator confirms a unique random 20+ character value in Streamlit Secrets; never disclose it |
| Hosting identity and branch | Historical live URL in review notes | Confirm current URL, hosting account and deployed branch; ensure pushing this PR branch cannot auto-deploy production |
| Private access and HTTPS | README requires private viewers/authenticated proxy | Confirm viewer controls, HTTPS and WebSocket protection, with no direct-origin bypass |
| Codespaces | Loopback binding and notification-only forwarding | If used, inspect actual port 8501 visibility and keep it Private; otherwise record not applicable |
| Runtime CORS/XSRF | Both enabled in TOML and development launch flags | Inspect effective settings and environment/CLI overrides on host |
| Sheets receiver | Client sends a secret and rejects unsafe redirects/formulas | Inspect receiver code; verify missing/wrong secret rejected before any write, literal-text storage and target-sheet restriction |
| Service credentials | No real secrets added by this review | Confirm least privilege, quotas/budget alerts and assess prior URL-key logging for rotation |
| Learning data | Shared local SQLite, unchanged schema | Back up progress, notes and saved audio before restart; verify restore plan |

After host configuration is confirmed and new-head CI passes, the code is a
reasonable hardening change for a private single-owner app. A controlled deployment
must then verify signed-out denial, authenticated learning/notes/audio/AI, actual
CORS/WebSocket behavior and an approved disposable Sheets write. These acceptance
tests cannot be claimed complete before deployment. Keep the app private during
verification; stop it if verification fails rather than rolling back to anonymous
access or disabled request protections.

Remaining limits: no per-user identity/isolation, login rate limiter or API budget
enforcement in the application; Streamlit media URLs are not protected by this
script gate. Hosting access controls must cover the entire service. The public
CSV source is not made private by this PR. Dependencies remain broadly versioned,
so future installs may differ; this review is not a full dependency/CVE audit or
proof of compatibility with every supported Streamlit version. Re-run CI for the
chosen deployment runtime and retain its resolved dependency versions. No breach
or public unauthorized mutation was demonstrated.

References for these corrections:
- https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data
- https://developers.google.com/apps-script/reference/spreadsheet/range#setvaluesvalues

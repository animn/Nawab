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

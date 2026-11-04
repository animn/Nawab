# Nawab mobile

Expo Go compatible React Native app for iOS, Android and responsive web. Targets Expo SDK 54 with Expo's matched dependencies so it can open in the standard iPhone App Store version of Expo Go. No custom native modules, secrets or provider credentials are included.

## Run

```sh
npm ci
npm start
# Scan the development QR using an SDK 54 compatible Expo Go app.
# For browser development:
npm run web
```

Local practice works without a backend. It contains three clearly labelled illustrative examples (not video transcripts), persistent recall scores/notes, and an explicit on-demand import of the legacy public Google Sheet. Browser CORS may prevent direct Sheet reads; use native Expo or the authenticated backend in that case. Imported vocabulary IDs use MD5 of trimmed Arabic, matching the legacy app. Existing local scores and notes survive repeat imports.

To use real video uploads, enter the HTTPS backend URL and owner password in Settings. Configure server credentials and processing providers in the backend environment, never in this client. A session token lives only in memory and is cleared on sign-out or API URL change. Local and server vocabulary are deliberately separate; local demo progress is never uploaded automatically. The server must allow the deployed web origin in CORS. A backend on `localhost` is reachable only on the same machine; a physical phone needs a reachable HTTPS endpoint.

Video uploads require a rights confirmation. Upload is the primary workflow; direct-link import is hidden for now. Missing providers and failed jobs remain visibly incomplete. Sentence drafts can be edited and removed before explicit approval. Sheet write-back is a separate opt-in, and uncertain/failed write results are reported without automatic retry.

Native microphone recording and playback use expo-audio. Recording is requested only on tap. Recordings remain local unless the user chooses to save them to the server. Optional server comparison uses the manually entered spoken transcript, not automatic speech recognition and never a pronunciation score. Original source clips are authenticated; web fetches them into temporary blob URLs and releases URLs on unmount. Native device playback/recording requires physical-device testing; production export alone does not certify hardware behavior.

## Checks

```sh
npm run typecheck
npm test
npm run export
```

Tests cover legacy score/ID behavior, URL boundaries, segment bounds, honest metrics, corrupt storage, credential exclusion, duplicate operation protection, HTTP errors and Sheet merge preservation. `expo export --platform all` produces web, iOS and Android bundles in `dist/`. An export is not an App Store/Play Store build or a running backend.

The hosted project is [@anim.gcc1/nawab-kuwaiti](https://expo.dev/accounts/anim.gcc1/projects/nawab-kuwaiti), separate from every other app. It uses the `sdkVersion` runtime policy, preventing accidental SDK 54/58 update mixing. No API password or provider keys are embedded in the Expo update.

Current Expo documentation says the iPhone App Store version of Expo Go stops at SDK 54: https://docs.expo.dev/troubleshooting/expo-go-version-mismatch/ . Android users must also install the matching SDK 54 build from https://expo.dev/go . Installed Expo's `bundledNativeModules.json` is the dependency compatibility source of truth.

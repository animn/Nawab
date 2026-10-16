# Yalla Kuwaiti

Personal Streamlit vocabulary trainer with Gemini, Azure pronunciation, shared
SQLite learning progress, and optional Google Sheets write-back.

## Run securely

1. Install Python 3.11+ and `pip install -r requirements.txt`.
2. Generate a unique random password, for example with
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
3. Store it as `APP_PASSWORD = "<your generated password>"` in the hosting
   platform's Streamlit Secrets or local `.streamlit/secrets.toml`. Do not commit
   that file. The app requires at least 20 characters and stops if missing.
4. Keep the existing service secrets in that same secret store:
   `GEMINI_API_KEY`, `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`, optional
   `AZURE_SPEECH_VOICE`, `SHEET_APPEND_WEBHOOK_URL`, and `SHEET_APPEND_SECRET`.
   Use a separate random secret for the Sheets webhook.
5. Run `streamlit run app.py --server.address 127.0.0.1` from the repository root.
   Sign in using the app password. Sign out when finished.

**Existing deployments: configure APP_PASSWORD before deploying this change.**
Without it, the app deliberately shows a setup error instead of loading data.
Refreshing a browser may require signing in again. Rotation revokes old sessions
on their next rerun or protected callback; restart the app to terminate sessions
and in-flight work immediately.

Keep Codespaces port 8501 **Private**. Loopback binding does not make a forwarded
port private; visibility is controlled by Codespaces. The devcontainer now only
notifies about the port. Open the forwarded URL in a normal browser tab.

For remote hosting, use HTTPS and private-app viewer controls or an authenticated
reverse proxy covering HTTP **and WebSockets**. Do not expose an alternate direct
port that bypasses the proxy. Only override the listen address to `0.0.0.0` if the
hosting platform requires it and its network/access controls are in place.
The app password is a small single-owner gate, not multi-user identity management,
per-user data isolation, a rate limiter, or protection for every Streamlit HTTP
endpoint. All authorized users share the same data and service permissions.

CORS and XSRF protections are explicitly enabled in `.streamlit/config.toml`.
If a proxy/forwarded URL fails, set `browser.serverAddress` to the actual external
hostname and `browser.serverPort` to its external port; preserve WebSocket support
and host/origin headers. Do not disable the protections to fix a preview.
Environment variables and CLI flags can override this file; check them too.

## Tests and review

Run `pip install pytest` then `python -m pytest -q`. Tests use fake credentials,
mock providers, temporary databases and Streamlit's AppTest. They do not spend
API credits or write to a real Google Sheet.

See [SECURITY_REVIEW.md](SECURITY_REVIEW.md) for confirmed findings, evidence
limits and the remaining deployment checks.

"""Small, fail-closed access gate for a single-owner Streamlit app."""

import hashlib
import hmac

import streamlit as st


def _password():
    try:
        value = st.secrets.get("APP_PASSWORD", "")
    except (FileNotFoundError, KeyError):
        return ""
    return value if isinstance(value, str) and len(value) >= 20 else ""


def _fingerprint(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def is_authorized():
    password = _password()
    token = st.session_state.get("_access_token", "")
    return bool(password) and isinstance(token, str) and hmac.compare_digest(
        token, _fingerprint(password)
    )


def require_authorized():
    # Callbacks execute before the main script reruns. Recheck here too.
    if not is_authorized():
        st.stop()


def _sign_in():
    supplied = st.session_state.pop("_access_password", "")
    password = _password()
    if password and hmac.compare_digest(
        supplied.encode("utf-8"), password.encode("utf-8")
    ):
        st.session_state["_access_token"] = _fingerprint(password)
        st.session_state.pop("_access_failed", None)
    else:
        st.session_state.pop("_access_token", None)
        st.session_state["_access_failed"] = True


def _sign_out():
    st.session_state.clear()


def require_access():
    if not _password():
        st.error("Access is not configured. Ask the app owner to configure APP_PASSWORD.")
        st.stop()
    if is_authorized():
        st.sidebar.button("Sign out", on_click=_sign_out)
        return
    st.title("🇰🇼 Yalla Kuwaiti!")
    with st.form("sign_in"):
        st.text_input("App password", type="password", key="_access_password")
        st.form_submit_button("Sign in", on_click=_sign_in)
    if st.session_state.get("_access_failed"):
        st.error("Incorrect password.")
    st.stop()

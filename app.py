import streamlit as st
import pandas as pd
import sqlite3
from gtts import gTTS
import io
import random
import hashlib
import requests
import json
import re

# --- Configuration & Keys ---
st.set_page_config(page_title="Yalla Kuwaiti!", page_icon="🇰🇼", layout="centered")

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    GEMINI_API_KEY = None

SHEET_URL = "https://docs.google.com/spreadsheets/d/1DQ_74TZtMpbinusdnMOU2441hEFa7RRnaqeMx8qrBg0/export?format=csv"
DB_NAME = "learning_progress_v8.db"

# Google Sheet write-back via Google Apps Script Web App.
# Add these in Streamlit Secrets after deploying the Apps Script:
# SHEET_APPEND_WEBHOOK_URL = "https://script.google.com/macros/s/.../exec"
# SHEET_APPEND_SECRET = "your-long-random-secret"
def get_secret_value(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

SHEET_APPEND_WEBHOOK_URL = get_secret_value("SHEET_APPEND_WEBHOOK_URL")
SHEET_APPEND_SECRET = get_secret_value("SHEET_APPEND_SECRET", "")

INBOX_JSON_KEYS = [
    "chapter",
    "arabicscript",
    "pronunciation",
    "englishmeaning",
    "explanation",
    "letterwisepronounciation",
    "letterwiseenglish",
]

# --- SAFE NATIVE CSS ---
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 1rem !important;
            max-width: 600px;
        }
        audio {
            height: 45px !important;
            width: 100% !important;
            margin-bottom: 0 !important;
        }
        .arabic-word {
            text-align: right;
            font-size: 42px;
            margin: 0 0 0.5rem 0;
            line-height: 1.2;
        }
        .note-preview {
            font-size: 0.9rem;
            color: #ddd;
            border: 1px solid #555;
            border-radius: 5px;
            padding: 10px;
            min-height: 80px;
            max-height: 150px;
            overflow-y: auto;
            white-space: pre-wrap;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- HELPER FUNCTIONS ---
def clean_val(val):
    """
    Robust cleaner for strings, numbers, pandas values, lists, arrays, dicts.
    Prevents: 'truth value of an array is ambiguous'
    """
    if val is None:
        return ""

    # If Gemini returns a list/array, flatten it into readable text
    if isinstance(val, (list, tuple, set)):
        parts = []
        for item in val:
            item_text = clean_val(item)
            if item_text:
                parts.append(item_text)
        return " | ".join(parts)

    # If Gemini returns a dict/object, flatten key-value pairs
    if isinstance(val, dict):
        parts = []
        for k, v in val.items():
            k_text = clean_val(k)
            v_text = clean_val(v)
            if k_text and v_text:
                parts.append(f"{k_text}: {v_text}")
            elif v_text:
                parts.append(v_text)
        return " | ".join(parts)

    # If pandas gives a Series due to duplicate columns, flatten it
    if isinstance(val, pd.Series):
        parts = []
        for item in val.tolist():
            item_text = clean_val(item)
            if item_text:
                parts.append(item_text)
        return " | ".join(parts)

    # Safe pandas NaN check
    try:
        if pd.isna(val):
            return ""
    except Exception:
        pass

    text = str(val).strip()

    if text.lower() in ["nan", "none", "null"]:
        return ""

    return text


@st.cache_data(show_spinner=False)
def get_audio_bytes(text):
    text = clean_val(text)
    if not text:
        return None
    try:
        tts = gTTS(text=text, lang="ar")
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        return fp.getvalue()
    except Exception:
        return None


def extract_json_object(text):
    if not text:
        raise ValueError("Empty AI response.")

    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No valid JSON object found in AI response.")

    return json.loads(cleaned[start:end + 1])


def normalize_inbox_payload(payload, fallback_text=""):
    """Make Gemini output safe even if it changes casing/spaces/underscore names."""
    if not isinstance(payload, dict):
        raise ValueError("AI response JSON is not an object.")

    compact = {
        re.sub(r"[^a-zA-Z0-9]", "", str(k)).lower(): v
        for k, v in payload.items()
    }

    aliases = {
        "chapter": ["chapter", "category", "lesson", "customlessoncategory"],
        "arabicscript": ["arabicscript", "arabic", "arabictext", "arabicword"],
        "pronunciation": ["pronunciation", "pronounciation", "phonetic", "transliteration"],
        "englishmeaning": ["englishmeaning", "meaning", "english", "translation"],
        "explanation": ["explanation", "explain", "usage"],
        "letterwisepronounciation": [
            "letterwisepronounciation",
            "letterwisepronunciation",
            "letterpronunciation",
            "soundbreakdown",
        ],
        "letterwiseenglish": ["letterwiseenglish", "letterenglish", "morphology", "morphologycontext"],
    }

    normalized = {}
    for target_key, possible_keys in aliases.items():
        value = ""
        for possible_key in possible_keys:
            if possible_key in compact:
                value = compact[possible_key]
                break
        normalized[target_key] = clean_val(value)

    if not normalized["arabicscript"]:
        normalized["arabicscript"] = clean_val(fallback_text)
    if not normalized["chapter"]:
        normalized["chapter"] = "Custom Lesson"

    return normalized


# --- DATABASE MODULE ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS vocab
        (
            id TEXT PRIMARY KEY,
            chapter TEXT,
            arabic TEXT,
            pronunciation TEXT,
            english TEXT,
            explanation TEXT,
            letter_pronunc TEXT,
            letter_eng TEXT,
            score INTEGER DEFAULT 0,
            notes TEXT DEFAULT ''
        )
        """
    )
    conn.commit()
    return conn


@st.cache_data(ttl=600, show_spinner=False)
def fetch_sheet_data(url):
    return pd.read_csv(url)


def sync_data(conn, df):
    c = conn.cursor()
    df.columns = df.columns.str.replace(r"[^a-zA-Z0-9]", "", regex=True).str.lower()

    for _, row in df.iterrows():
        arabic_text = clean_val(row.get("arabicscript", ""))
        if not arabic_text:
            continue

        word_id = hashlib.md5(arabic_text.encode()).hexdigest()
        l_pron = clean_val(
            row.get(
                "letterwisepronounciation",
                row.get("letterwisepronunciation", "")
            )
        )

        c.execute(
            """
            INSERT INTO vocab
            (id, chapter, arabic, pronunciation, english, explanation, letter_pronunc, letter_eng, score, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                chapter = excluded.chapter,
                arabic = excluded.arabic,
                pronunciation = excluded.pronunciation,
                english = excluded.english,
                explanation = excluded.explanation,
                letter_pronunc = excluded.letter_pronunc,
                letter_eng = excluded.letter_eng
            """,
            (
                word_id,
                clean_val(row.get("chapter")),
                arabic_text,
                clean_val(row.get("pronunciation")),
                clean_val(row.get("englishmeaning")),
                clean_val(row.get("explanation")),
                l_pron,
                clean_val(row.get("letterwiseenglish")),
                0,
                "",
            ),
        )

    conn.commit()


def upsert_vocab_entry(conn, chapter, arabic, pronunciation, english, explanation, letter_pronunc, letter_eng):
    arabic = clean_val(arabic)
    if not arabic:
        raise ValueError("Arabic Script cannot be empty.")

    word_id = hashlib.md5(arabic.encode()).hexdigest()
    conn.cursor().execute(
        """
        INSERT INTO vocab
        (id, chapter, arabic, pronunciation, english, explanation, letter_pronunc, letter_eng, score, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '')
        ON CONFLICT(id) DO UPDATE SET
            chapter = excluded.chapter,
            arabic = excluded.arabic,
            pronunciation = excluded.pronunciation,
            english = excluded.english,
            explanation = excluded.explanation,
            letter_pronunc = excluded.letter_pronunc,
            letter_eng = excluded.letter_eng
        """,
        (
            word_id,
            clean_val(chapter) or "Custom Lesson",
            arabic,
            clean_val(pronunciation),
            clean_val(english),
            clean_val(explanation),
            clean_val(letter_pronunc),
            clean_val(letter_eng),
        ),
    )
    conn.commit()
    return word_id


def append_vocab_entry_to_google_sheet(chapter, arabic, pronunciation, english, explanation, letter_pronunc, letter_eng):
    """Send approved inbox entries back to Google Sheets through Apps Script.

    Returns:
        (success: bool, message: str)
    """
    if not SHEET_APPEND_WEBHOOK_URL:
        return False, "Google Sheet write-back is not configured. Add SHEET_APPEND_WEBHOOK_URL in Streamlit Secrets."

    payload = {
        "secret": SHEET_APPEND_SECRET,
        "entry": {
            "chapter": clean_val(chapter) or "Custom Lesson",
            "arabicscript": clean_val(arabic),
            "pronunciation": clean_val(pronunciation),
            "englishmeaning": clean_val(english),
            "explanation": clean_val(explanation),
            "letterwisepronounciation": clean_val(letter_pronunc),
            "letterwiseenglish": clean_val(letter_eng),
        },
    }

    try:
        resp = requests.post(SHEET_APPEND_WEBHOOK_URL, json=payload, timeout=30)
    except Exception as exc:
        return False, f"Google Sheet write failed: {exc}"

    if resp.status_code != 200:
        return False, f"Google Sheet write failed. HTTP {resp.status_code}: {resp.text[:300]}"

    try:
        data = resp.json()
    except Exception:
        return False, f"Google Sheet returned a non-JSON response: {resp.text[:300]}"

    if data.get("ok") is True:
        return True, clean_val(data.get("message")) or "Saved to Google Sheet."

    return False, clean_val(data.get("error")) or f"Google Sheet write failed: {data}"


def update_score(conn, word_id, is_correct):
    c = conn.cursor()
    row = c.execute("SELECT score FROM vocab WHERE id = ?", (word_id,)).fetchone()
    if not row:
        return 0

    new_score = (row[0] or 0) + 1 if is_correct else 0
    c.execute("UPDATE vocab SET score = ? WHERE id = ?", (new_score, word_id))
    conn.commit()
    return new_score


def save_note(conn, word_id, note_text):
    conn.cursor().execute("UPDATE vocab SET notes = ? WHERE id = ?", (note_text, word_id))
    conn.commit()


def autosave_note_from_state(word_id, text_key, note_key):
    note_text = st.session_state.get(text_key, "")
    st.session_state[note_key] = note_text
    temp_conn = sqlite3.connect(DB_NAME)
    save_note(temp_conn, word_id, note_text)
    temp_conn.close()


def get_stats(conn):
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM vocab").fetchone()[0]
    mastered = c.execute("SELECT COUNT(*) FROM vocab WHERE score >= 3").fetchone()[0]
    practice = c.execute("SELECT COUNT(*) FROM vocab WHERE score = 0").fetchone()[0]
    learning = total - mastered - practice
    return total, mastered, learning, practice


# --- GEMINI REST API MODULE ---
def call_gemini_dynamic(prompt, api_key):
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    list_resp = requests.get(list_url, timeout=30)

    if list_resp.status_code != 200:
        raise Exception(f"Google rejected key entirely: {list_resp.text}")

    models_data = list_resp.json().get("models", [])
    valid_model_name = None

    for m in models_data:
        name = m.get("name", "")
        methods = m.get("supportedGenerationMethods", [])
        if "gemini" in name.lower() and "generateContent" in methods:
            valid_model_name = name
            if "flash" in name.lower():
                break

    if not valid_model_name:
        raise Exception("Your API key has 0 authorized text models.")

    generate_url = f"https://generativelanguage.googleapis.com/v1beta/{valid_model_name}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    resp = requests.post(generate_url, headers=headers, json=payload, timeout=60)
    data = resp.json()

    if resp.status_code == 200:
        return data["candidates"][0]["content"]["parts"][0]["text"]

    raise Exception(data.get("error", {}).get("message", str(data)))


def clean_two_example_response(ai_answer):
    raw_lines = [line.strip() for line in ai_answer.splitlines() if line.strip()]
    numbered_lines = [line for line in raw_lines if line.startswith("1.") or line.startswith("2.")]
    if len(numbered_lines) >= 2:
        return "\n".join(numbered_lines[:2])
    return "\n".join(raw_lines[:2])


# --- UI COMPONENT: SMART INBOX ---
def render_inbox(conn):
    st.subheader("📥 Smart Inbox")
    st.caption(
        "Add English, Arabic script, Arabizi, or any phrase. S.AI converts it into your flashcard schema."
    )

    raw_input = st.text_input(
        "Enter English, Arabic, Arabizi, or any phrase",
        key="inbox_raw_text",
        placeholder="Examples: water, where are you going, ماكو, shلونك...",
    )

    if st.button("✨ Process Word", use_container_width=True):
        raw_clean = clean_val(raw_input)
        if not GEMINI_API_KEY:
            st.error("Add GEMINI_API_KEY in Streamlit Secrets.")
        elif not raw_clean:
            st.warning("Please type a phrase first.")
        else:
            with st.spinner("S.AI is preparing the flashcard fields..."):
                try:
                    prompt = f"""
You are an expert Kuwaiti Arabic linguist and tutor.

The user may enter:
- an English word
- an English phrase
- Arabic script
- Arabizi / Franco Arabic
- mixed English-Arabic text

User input:
"{raw_clean}"

Your job:
Convert the input into a high-quality Kuwaiti Arabic flashcard.

Return ONLY one valid JSON object. Do not use markdown.
Use exactly these keys:
{{
  "chapter": "lesson category such as Daily Phrases, Home, Office, Shopping, Greetings, Food & Drinks, Family, Travel, Questions, Time, Numbers",
  "arabicscript": "natural Kuwaiti Arabic phrase in Arabic script",
  "pronunciation": "simple English transliteration for a beginner",
  "englishmeaning": "concise English meaning",
  "explanation": "short practical usage explanation",
  "letterwisepronounciation": "sound-by-sound or phrase-part breakdown",
  "letterwiseenglish": "word/part-by-part meaning or morphology context"
}}

Rules:
- The output must be natural Kuwaiti spoken Arabic, not Modern Standard Arabic.
- If the input is English, translate the intended meaning into the most natural Kuwaiti Arabic expression, not word-for-word Arabic.
- If the English input is grammatically imperfect, infer the natural meaning before translating.
- Prefer phrases a Kuwaiti person would actually say in daily conversation.
- Prefer Kuwaiti/Gulf spoken dialect over formal Arabic.
- Avoid textbook/formal Arabic unless there is no natural spoken equivalent.
- If the output is Gulf-common rather than specifically Kuwaiti, clearly mention that in the explanation.
- If formal Arabic is used, clearly mention in the explanation that it is more formal and why it was used.
- Use Kuwaiti/Gulf spoken expressions where suitable, such as شلون، شنو، وين، ماكو، أبي، عندي، في، خوش.
- Keep the Arabic phrase short, practical, and usable in real conversation.
- "arabicscript" must contain only the final Arabic/Kuwaiti phrase in Arabic script.
- "pronunciation" must be simple for an English speaker to read.
- "englishmeaning" must be concise.
- "explanation" must be practical and short, and must state whether the phrase is Kuwaiti spoken, Gulf-common, or formal Arabic.
- "letterwisepronounciation" must explain the sound breakdown in simple English.
- "letterwiseenglish" must explain the phrase components or word-by-word meaning in simple English.
- "chapter" should be a useful lesson category such as Daily Phrases, Home, Office, Food & Drinks, Shopping, Family, Travel, Emotions, Questions, Time, Numbers, Greetings, Building/Neighbours, Work, or Travel.
- Every JSON value must be a plain string only.
- Do not return arrays, lists, nested objects, markdown, bullet points, or comments.
- Do not add comments before or after the JSON.
"""
                    response = call_gemini_dynamic(prompt, GEMINI_API_KEY)
                    payload = normalize_inbox_payload(extract_json_object(response), raw_clean)
                    st.session_state.inbox_pending = payload
                    st.toast("AI parsing successful. Review before saving.")
                except Exception as e:
                    st.error(f"Processing Failure: {e}")

    if "inbox_pending" in st.session_state:
        st.divider()
        st.subheader("Review Before Saving")
        pending = st.session_state.inbox_pending

        with st.form("inbox_review_form"):
            edit_cat = st.text_input("Custom Lesson Category", value=pending.get("chapter", "Custom Lesson"))
            edit_ar = st.text_input("Arabic Script", value=pending.get("arabicscript", raw_input), dir="rtl")
            edit_pron = st.text_input("Pronunciation", value=pending.get("pronunciation", ""))
            edit_mean = st.text_input("English Meaning", value=pending.get("englishmeaning", ""))
            edit_expl = st.text_area("Explanation", value=pending.get("explanation", ""))
            edit_l_pron = st.text_input("Letter-wise Pronunciation", value=pending.get("letterwisepronounciation", ""))
            edit_l_eng = st.text_input("Letter-wise English", value=pending.get("letterwiseenglish", ""))

            submit_col, cancel_col = st.columns(2)

            if submit_col.form_submit_button("✅ Approve & Save", use_container_width=True):
                try:
                    upsert_vocab_entry(
                        conn,
                        edit_cat,
                        edit_ar,
                        edit_pron,
                        edit_mean,
                        edit_expl,
                        edit_l_pron,
                        edit_l_eng,
                    )

                    sheet_ok, sheet_msg = append_vocab_entry_to_google_sheet(
                        edit_cat,
                        edit_ar,
                        edit_pron,
                        edit_mean,
                        edit_expl,
                        edit_l_pron,
                        edit_l_eng,
                    )

                    if sheet_ok:
                        fetch_sheet_data.clear()
                        st.session_state.flash_toast = (
                            f"Saved locally + Google Sheet under: {clean_val(edit_cat) or 'Custom Lesson'}"
                        )
                    else:
                        st.session_state.flash_toast = (
                            f"Saved locally, but Google Sheet was not updated: {sheet_msg}"
                        )

                    del st.session_state.inbox_pending
                    st.session_state.current_word = None
                    st.rerun()
                except Exception as e:
                    st.error(f"Save failed: {e}")

            if cancel_col.form_submit_button("🗑️ Discard", use_container_width=True):
                del st.session_state.inbox_pending
                st.toast("Draft removed.")
                st.rerun()


# --- UI COMPONENT: FLASHCARD ---
def render_flashcard(conn, word_data, tab_key):
    word_id, chapter, arabic, pronunc, english, expl, l_pronunc, l_eng, score, saved_note = word_data

    display_label = chapter if chapter else "Custom Lesson"
    st.markdown(
        f"""
        <div style='font-size:18px; font-weight:bold; margin-bottom:10px;'>
            📚 {display_label}
            <span style='font-weight:normal; color:#aaa; font-size:14px;'>
                (Score: {score}/3)
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    btn_col1, btn_col2 = st.columns(2)

    if btn_col1.button("👍 Got it", key=f"up_{word_id}_{tab_key}", use_container_width=True):
        new_score = update_score(conn, word_id, True)
        st.session_state.flash_toast = (
            f"👍 Score increased to {new_score}/3" if new_score < 3 else "👑 Word Mastered!"
        )
        if tab_key == "home":
            st.session_state.current_word = None
        st.rerun()

    if btn_col2.button("👎 Practice", key=f"down_{word_id}_{tab_key}", use_container_width=True):
        update_score(conn, word_id, False)
        st.session_state.flash_toast = "👎 Score reset to 0."
        if tab_key == "home":
            st.session_state.current_word = None
        st.rerun()

    with st.container(border=True):
        st.markdown(f"<h1 class='arabic-word' dir='rtl'>{arabic}</h1>", unsafe_allow_html=True)

        audio_bytes = get_audio_bytes(arabic)
        if audio_bytes:
            st.audio(audio_bytes, format="audio/mp3")

        display_title = f"{pronunc if pronunc else 'Pronunciation'} | {english if english else 'Meaning'}"
        with st.expander(f"🗣️ {display_title}"):
            if expl:
                st.info(f"**Explanation:** {expl}")
            if l_pronunc:
                st.write(f"**Sound Breakdown:** {l_pronunc}")
            if l_eng:
                st.write(f"**Morphology Context:** {l_eng}")

    # S.AI Tutor Logic
    note_key = f"note_{word_id}_{tab_key}"
    note_text_key = f"text_{word_id}_{tab_key}"

    if note_key not in st.session_state:
        st.session_state[note_key] = saved_note if saved_note else ""
    if note_text_key not in st.session_state:
        st.session_state[note_text_key] = st.session_state[note_key]

    st.markdown("<br>", unsafe_allow_html=True)

    with st.form(key=f"sai_form_{word_id}_{tab_key}", clear_on_submit=False):
        question = st.text_input(
            "Ask S.AI a question",
            key=f"q_{word_id}_{tab_key}",
            placeholder="Type 1 for exactly 2 examples...",
        )
        submitted = st.form_submit_button("🤖 S.AI", use_container_width=True)

    if submitted:
        question_clean = str(question).strip()

        if not GEMINI_API_KEY:
            st.error("Add API key in Streamlit Secrets!")
        elif not question_clean:
            st.warning("Type something first.")
        else:
            with st.spinner("Thinking..."):
                try:
                    if question_clean == "1":
                        prompt = f"""
Arabic word: {arabic}
Pronunciation: {pronunc}
Meaning: {english}

Give exactly 2 short Kuwaiti Arabic examples using this word.

Strict format:
1. Arabic sentence - English meaning
2. Arabic sentence - English meaning

Rules:
- No blank line between the two examples.
- Do not add explanation.
- Do not add introduction.
- Do not add extra text.
"""
                    else:
                        prompt = (
                            f"Arabic: {arabic}. "
                            f"Meaning: {english}. "
                            f"Question: {question_clean}. "
                            f"Answer short in Kuwaiti context."
                        )

                    ai_answer = call_gemini_dynamic(prompt, GEMINI_API_KEY).strip()
                    if question_clean == "1":
                        ai_answer = clean_two_example_response(ai_answer)

                    old_note = st.session_state.get(note_key, "").strip()
                    updated_note = (
                        f"{old_note}\n\nQ: {question_clean}\nS.AI:\n{ai_answer}"
                        if old_note
                        else f"Q: {question_clean}\nS.AI:\n{ai_answer}"
                    )

                    st.session_state[note_key] = updated_note
                    st.session_state[note_text_key] = updated_note
                    save_note(conn, word_id, updated_note)
                    st.toast("AI response added!")
                    st.rerun()
                except Exception as ex:
                    st.error(f"S.AI Error: {ex}")

    st.text_area(
        "Notes",
        key=note_text_key,
        height=150,
        placeholder="Notes will appear here. You can edit directly...",
        on_change=autosave_note_from_state,
        args=(word_id, note_text_key, note_key),
    )
    st.caption("Notes autosave after editing when you tap outside / press done.")


# --- MAIN APP SETUP ---
if "flash_toast" in st.session_state:
    st.toast(st.session_state.flash_toast)
    del st.session_state.flash_toast

st.markdown("## 🇰🇼 Yalla Kuwaiti!")
conn = init_db()

try:
    df = fetch_sheet_data(SHEET_URL)
    sync_data(conn, df)
except Exception:
    st.warning("Public reference engine standalone operation active.")

# Sidebar Filters & Metrics
st.sidebar.header("Filters")
chapters = [
    row[0]
    for row in conn.cursor()
    .execute("SELECT DISTINCT chapter FROM vocab WHERE chapter != '' ORDER BY chapter")
    .fetchall()
]
selected_chapter = st.sidebar.selectbox("Chapter", ["All"] + chapters)

total, mastered, learning, practice = get_stats(conn)
st.sidebar.divider()
st.sidebar.markdown("🏆 **Dashboard**")
st.sidebar.metric("👑 Mastered (Score 3+)", mastered)
st.sidebar.metric("📈 Learning (Score 1-2)", learning)
st.sidebar.metric("🔴 Needs Practice (Score 0)", practice)
st.sidebar.progress(
    mastered / total if total > 0 else 0,
    text=f"Fluency: {int((mastered / total) * 100) if total else 0}%",
)

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📥 Inbox", "🎮 Daily", "🏋️ Review", "👑 Mastered", "⚙️ Sync"]
)

base_q = "SELECT id, chapter, arabic, pronunciation, english, explanation, letter_pronunc, letter_eng, score, notes FROM vocab"
params = []
if selected_chapter != "All":
    base_q += " WHERE chapter = ?"
    params.append(selected_chapter)

with tab1:
    render_inbox(conn)

with tab2:
    query = base_q + (" AND score < 3" if "WHERE" in base_q else " WHERE score < 3")
    words = conn.cursor().execute(query, params).fetchall()

    if words:
        current = st.session_state.get("current_word")
        valid_ids = {w[0] for w in words}

        if current is None or current[0] not in valid_ids:
            st.session_state.current_word = random.choice(words)

        render_flashcard(conn, st.session_state.current_word, "home")
    else:
        st.success("🎉 Section fully mastered!")

with tab3:
    query = base_q + (
        " AND score < 3 ORDER BY score ASC"
        if "WHERE" in base_q
        else " WHERE score < 3 ORDER BY score ASC"
    )
    rows = conn.cursor().execute(query, params).fetchall()

    for w in rows[:20]:
        with st.expander(f"🔴 {w[2]} ({w[4]}) - Score: {w[8]}/3"):
            render_flashcard(conn, w, f"prac_{w[0]}")

with tab4:
    query = base_q + (" AND score >= 3" if "WHERE" in base_q else " WHERE score >= 3")
    rows = conn.cursor().execute(query, params).fetchall()

    for w in rows[:20]:
        with st.expander(f"👑 {w[2]} ({w[4]})"):
            render_flashcard(conn, w, f"mast_{w[0]}")

with tab5:
    st.subheader("⚙️ Sync Management")

    if SHEET_APPEND_WEBHOOK_URL:
        st.success("Google Sheet write-back is configured.")
    else:
        st.warning("Google Sheet write-back is not configured yet. Approved Inbox words will save only inside the app database.")

    if st.button("Refresh Reference Datasets", use_container_width=True):
        fetch_sheet_data.clear()
        st.session_state.current_word = None
        st.rerun()

conn.close()

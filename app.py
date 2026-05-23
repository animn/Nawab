import streamlit as st
import pandas as pd
import sqlite3
from gtts import gTTS
import io
import random
import hashlib
import requests

# --- Configuration & Keys ---
st.set_page_config(page_title="Yalla Kuwaiti!", page_icon="🇰🇼", layout="centered")

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    GEMINI_API_KEY = None

SHEET_URL = "https://docs.google.com/spreadsheets/d/1DQ_74TZtMpbinusdnMOU2441hEFa7RRnaqeMx8qrBg0/export?format=csv"
DB_NAME = "learning_progress_v8.db"

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
    if pd.isna(val) or str(val).strip().lower() == "nan":
        return ""
    return str(val).strip()


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
            score INTEGER,
            notes TEXT
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
            (
                id,
                chapter,
                arabic,
                pronunciation,
                english,
                explanation,
                letter_pronunc,
                letter_eng,
                score,
                notes
            )
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
    conn.cursor().execute(
        "UPDATE vocab SET notes = ? WHERE id = ?",
        (note_text, word_id)
    )
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


# --- BULLETPROOF DYNAMIC REST API MODULE ---
def call_gemini_dynamic(prompt, api_key):
    """
    Fetches exactly what models Google allows your key to use,
    then picks the best one.
    """

    # 1. Ask Google for your authorized models
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    list_resp = requests.get(list_url)

    if list_resp.status_code != 200:
        raise Exception(f"Google rejected key entirely: {list_resp.text}")

    models_data = list_resp.json().get("models", [])
    valid_model_name = None

    # 2. Scan the list for a Gemini model that supports text generation
    for m in models_data:
        name = m.get("name", "")
        methods = m.get("supportedGenerationMethods", [])

        if "gemini" in name.lower() and "generateContent" in methods:
            valid_model_name = name

            if "flash" in name.lower():
                valid_model_name = name
                break

    if not valid_model_name:
        raise Exception(
            "Your API key has 0 authorized text models. Check Google AI Studio permissions."
        )

    # 3. Call the guaranteed-to-work model
    generate_url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"{valid_model_name}:generateContent?key={api_key}"
    )

    headers = {"Content-Type": "application/json"}

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }

    resp = requests.post(generate_url, headers=headers, json=payload)
    data = resp.json()

    if resp.status_code == 200:
        return data["candidates"][0]["content"]["parts"][0]["text"]

    raise Exception(data.get("error", {}).get("message", str(data)))


def clean_two_example_response(ai_answer):
    """
    Removes blank lines and keeps exactly two example lines where possible.
    This is important because Gemini may add spacing even when told not to.
    """

    raw_lines = [line.strip() for line in ai_answer.splitlines() if line.strip()]

    numbered_lines = [
        line for line in raw_lines
        if line.startswith("1.") or line.startswith("2.")
    ]

    if len(numbered_lines) >= 2:
        return "\n".join(numbered_lines[:2])

    return "\n".join(raw_lines[:2])


# --- UI COMPONENT MODULE ---
def render_flashcard(conn, word_data, tab_key):
    word_id, chapter, arabic, pronunc, english, expl, l_pronunc, l_eng, score, saved_note = word_data

    # Header
    st.markdown(
        f"""
        <div style='font-size:18px; font-weight:bold; margin-bottom:10px;'>
            {chapter}
            <span style='font-weight:normal; color:#aaa; font-size:14px;'>
                (Score: {score}/3)
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    btn_col1, btn_col2 = st.columns(2)

    if btn_col1.button(
        "👍 Got it",
        key=f"up_{word_id}_{tab_key}",
        use_container_width=True
    ):
        new_score = update_score(conn, word_id, True)

        st.session_state.flash_toast = (
            f"👍 Score increased to {new_score}/3"
            if new_score < 3
            else "👑 Word Mastered!"
        )

        if tab_key == "home":
            st.session_state.current_word = None

        st.rerun()

    if btn_col2.button(
        "👎 Practice",
        key=f"down_{word_id}_{tab_key}",
        use_container_width=True
    ):
        update_score(conn, word_id, False)

        st.session_state.flash_toast = "👎 Score reset to 0."

        if tab_key == "home":
            st.session_state.current_word = None

        st.rerun()

    # Flashcard Body
    with st.container(border=True):
        st.markdown(
            f"<h1 class='arabic-word' dir='rtl'>{arabic}</h1>",
            unsafe_allow_html=True
        )

        audio_bytes = get_audio_bytes(arabic)

        if audio_bytes:
            st.audio(audio_bytes, format="audio/mp3")

        display_title = (
            f"{pronunc if pronunc else 'Pronunciation'} | "
            f"{english if english else 'Meaning'}"
        )

        with st.expander(f"🗣️ {display_title}"):
            if expl:
                st.info(f"**Explanation:** {expl}")

            if l_pronunc:
                st.write(f"**Sound:** {l_pronunc}")

            if l_eng:
                st.write(f"**Letters:** {l_eng}")

    # S.AI Tutor Segment
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
            placeholder="Type 1 for exactly 2 examples..."
        )

        submitted = st.form_submit_button(
            "🤖 S.AI",
            use_container_width=True
        )

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

                    if old_note:
                        updated_note = (
                            f"{old_note}\n"
                            f"Q: {question_clean}\n"
                            f"S.AI:\n"
                            f"{ai_answer}\n"
                        )
                    else:
                        updated_note = (
                            f"Q: {question_clean}\n"
                            f"S.AI:\n"
                            f"{ai_answer}\n"
                        )

                    st.session_state[note_key] = updated_note
                    st.session_state[note_text_key] = updated_note

                    save_note(conn, word_id, updated_note)

                    st.toast("AI response added!")
                    st.rerun()

                except Exception as ex:
                    st.error(f"S.AI Error: {ex}")

    # Editable autosave notes
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
    st.error("Spreadsheet error.")

st.sidebar.header("Filters")

chapters = [
    row[0]
    for row in conn.cursor()
    .execute(
        """
        SELECT DISTINCT chapter
        FROM vocab
        WHERE chapter != ''
        ORDER BY chapter
        """
    )
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
    text=f"Fluency: {int((mastered / total) * 100) if total else 0}%"
)

tab1, tab2, tab3, tab4 = st.tabs(
    ["🎮 Daily", "🏋️ Review", "👑 Mastered", "⚙️ Sync"]
)

base_q = "SELECT * FROM vocab"
params = []

if selected_chapter != "All":
    base_q += " WHERE chapter = ?"
    params.append(selected_chapter)

with tab1:
    words = conn.cursor().execute(
        base_q + (
            " AND score < 3"
            if "WHERE" in base_q
            else " WHERE score < 3"
        ),
        params,
    ).fetchall()

    if words:
        current = st.session_state.get("current_word")
        valid_ids = {w[0] for w in words}

        if current is None or current[0] not in valid_ids:
            st.session_state.current_word = random.choice(words)

        render_flashcard(conn, st.session_state.current_word, "home")

    else:
        st.success("🎉 Section fully mastered!")

with tab2:
    rows = conn.cursor().execute(
        base_q + (
            " AND score < 3 ORDER BY score ASC"
            if "WHERE" in base_q
            else " WHERE score < 3 ORDER BY score ASC"
        ),
        params,
    ).fetchall()

    for w in rows[:20]:
        with st.expander(f"🔴 {w[2]} ({w[4]}) - Score: {w[8]}/3"):
            render_flashcard(conn, w, f"prac_{w[0]}")

with tab3:
    rows = conn.cursor().execute(
        base_q + (
            " AND score >= 3"
            if "WHERE" in base_q
            else " WHERE score >= 3"
        ),
        params,
    ).fetchall()

    for w in rows[:20]:
        with st.expander(f"👑 {w[2]} ({w[4]})"):
            render_flashcard(conn, w, f"mast_{w[0]}")

with tab4:
    if st.button("Refresh Spreadsheet Data"):
        fetch_sheet_data.clear()
        st.session_state.current_word = None
        st.rerun()

conn.close()
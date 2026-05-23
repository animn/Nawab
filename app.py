import streamlit as st
import pandas as pd
import sqlite3
from gtts import gTTS
import io
import random
import hashlib
import base64
import google.generativeai as genai

# --- Configuration & Keys ---
st.set_page_config(page_title="Yalla Kuwaiti!", page_icon="🇰🇼", layout="centered")

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    GEMINI_API_KEY = None

SHEET_URL = "https://docs.google.com/spreadsheets/d/1DQ_74TZtMpbinusdnMOU2441hEFa7RRnaqeMx8qrBg0/export?format=csv"
DB_NAME = "learning_progress_v8.db"

# --- Compact UI CSS ---
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.1rem;
            padding-bottom: 0.5rem;
            max-width: 760px;
        }
        h2, h3, p {
            margin-top: 0rem;
            margin-bottom: 0.25rem;
        }
        div[data-testid="stVerticalBlock"] {
            gap: 0.35rem;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: 0.35rem;
            align-items: center;
        }
        div[data-testid="column"] {
            padding: 0rem 0.05rem;
        }
        .stButton > button {
            min-height: 2rem;
            height: 2rem;
            padding: 0rem 0.45rem;
            line-height: 1;
            width: 100%;
        }
        .stTextInput input {
            min-height: 2rem;
            height: 2rem;
            padding-top: 0.15rem;
            padding-bottom: 0.15rem;
        }
        textarea {
            min-height: 42px !important;
            padding-top: 0.25rem !important;
            padding-bottom: 0.25rem !important;
        }
        div[data-testid="stExpander"] details summary {
            padding-top: 0.35rem;
            padding-bottom: 0.35rem;
        }
        div[data-testid="stExpander"] details div[data-testid="stExpanderDetails"] {
            padding-top: 0.35rem;
            padding-bottom: 0.35rem;
        }
        audio {
            height: 30px !important;
        }
        .compact-arabic {
            text-align: right;
            font-size: 34px;
            line-height: 1.05;
            margin: 0;
        }
        .compact-meta {
            font-size: 0.86rem;
            line-height: 1.1;
            margin: 0;
            white-space: nowrap;
        }
        .score-right {
            text-align: right;
            width: 100%;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- HELPER FUNCTIONS ---
def clean_val(val):
    """Prevents 'nan' from showing up in the UI and crashing the app."""
    if pd.isna(val) or str(val).strip().lower() == 'nan':
        return ""
    return str(val).strip()

@st.cache_data(show_spinner=False)
def get_audio_player(text, player_style):
    """Generates audio once and caches it. Returns HTML for mini player or bytes for native."""
    if not text:
        return None
    try:
        tts = gTTS(text=text, lang='ar')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        audio_bytes = fp.getvalue()

        if player_style == "Mini Player":
            b64 = base64.b64encode(audio_bytes).decode()
            return f'''
                <audio controls style="height: 30px; width: 100%; border-radius: 5px;">
                    <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
                </audio>
            '''
        return audio_bytes
    except Exception:
        return None

# --- DATABASE MODULE ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vocab
                 (id TEXT PRIMARY KEY, chapter TEXT, arabic TEXT,
                  pronunciation TEXT, english TEXT, explanation TEXT,
                  letter_pronunc TEXT, letter_eng TEXT, score INTEGER, notes TEXT)''')
    conn.commit()
    return conn

@st.cache_data(ttl=600, show_spinner=False)
def fetch_sheet_data(url):
    return pd.read_csv(url)

def sync_data(conn, df):
    c = conn.cursor()
    df.columns = df.columns.str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.lower()
    for _, row in df.iterrows():
        arabic_text = clean_val(row.get('arabicscript', ''))
        if not arabic_text:
            continue

        chapter = clean_val(row.get('chapter'))
        english = clean_val(row.get('englishmeaning'))
        word_id = hashlib.md5(f"{chapter}|{arabic_text}|{english}".encode()).hexdigest()
        l_pron = clean_val(row.get('letterwisepronounciation', row.get('letterwisepronunciation', '')))

        c.execute('''INSERT INTO vocab (id, chapter, arabic, pronunciation, english,
                                        explanation, letter_pronunc, letter_eng, score, notes)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                     ON CONFLICT(id) DO UPDATE SET
                        chapter=excluded.chapter,
                        arabic=excluded.arabic,
                        pronunciation=excluded.pronunciation,
                        english=excluded.english,
                        explanation=excluded.explanation,
                        letter_pronunc=excluded.letter_pronunc,
                        letter_eng=excluded.letter_eng''',
                  (word_id, chapter, arabic_text,
                   clean_val(row.get('pronunciation')), english,
                   clean_val(row.get('explanation')), l_pron,
                   clean_val(row.get('letterwiseenglish')), 0, ""))
    conn.commit()

def update_score(conn, word_id, is_correct):
    c = conn.cursor()
    row = c.execute("SELECT score FROM vocab WHERE id=?", (word_id,)).fetchone()
    if not row:
        return
    current_score = row[0] or 0
    new_score = current_score + 1 if is_correct else 0
    c.execute("UPDATE vocab SET score=? WHERE id=?", (new_score, word_id))
    conn.commit()

def save_note(conn, word_id, note_text):
    conn.cursor().execute("UPDATE vocab SET notes=? WHERE id=?", (note_text, word_id))
    conn.commit()

def get_stats(conn):
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM vocab").fetchone()[0]
    mastered = c.execute("SELECT COUNT(*) FROM vocab WHERE score >= 3").fetchone()[0]
    practice = c.execute("SELECT COUNT(*) FROM vocab WHERE score = 0").fetchone()[0]
    return total, mastered, total - mastered - practice, practice

# --- UI COMPONENT MODULE ---
def render_flashcard(conn, word_data, tab_key, player_style):
    word_id, chapter, arabic, pronunc, english, expl, l_pronunc, l_eng, score, saved_note = word_data

    # One-line header: chapter left, thumbs + score right
    hc1, hc2, hc3, hc4 = st.columns([5.8, 0.65, 0.65, 1.7], vertical_alignment="center")
    hc1.markdown(f"<div class='compact-meta'><b>{chapter}</b></div>", unsafe_allow_html=True)
    if hc2.button("👍", key=f"up_{word_id}_{tab_key}", help="I know this"):
        update_score(conn, word_id, True)
        if tab_key == "home":
            st.session_state.current_word = None
        st.rerun()
    if hc3.button("👎", key=f"down_{word_id}_{tab_key}", help="Needs practice"):
        update_score(conn, word_id, False)
        if tab_key == "home":
            st.session_state.current_word = None
        st.rerun()
    hc4.markdown(f"<div class='compact-meta score-right'>Score {score}/3</div>", unsafe_allow_html=True)

    # Compact flashcard body
    with st.container(border=True):
        f_col1, f_col2 = st.columns([3.5, 2], vertical_alignment="center")
        f_col1.markdown(f"<h1 class='compact-arabic' dir='rtl'>{arabic}</h1>", unsafe_allow_html=True)

        with f_col2:
            audio_data = get_audio_player(arabic, player_style)
            if audio_data:
                if player_style == "Mini Player":
                    st.markdown(audio_data, unsafe_allow_html=True)
                else:
                    st.audio(audio_data, format="audio/mp3")

        with st.expander(f"🗣️ {pronunc} | {english}"):
            if expl:
                st.info(f"**Explanation:** {expl}")
            if l_pronunc or l_eng:
                if l_pronunc:
                    st.write(f"**Letter pronunciation:** {l_pronunc}")
                if l_eng:
                    st.write(f"**Letter English:** {l_eng}")

    # One compact AI + notes row
    note_key = f"note_{word_id}_{tab_key}"
    text_key = f"text_{word_id}_{tab_key}"
    if note_key not in st.session_state:
        st.session_state[note_key] = saved_note if saved_note else ""

    ai_c1, ai_c2, ai_c3, ai_c4 = st.columns([4.2, 0.65, 3.2, 0.65], vertical_alignment="center")
    question = ai_c1.text_input(
        "Ask AI",
        key=f"q_{word_id}_{tab_key}",
        label_visibility="collapsed",
        placeholder="Ask AI..."
    )

    if ai_c2.button("A", key=f"ask_{word_id}_{tab_key}", help="Ask AI tutor"):
        if not GEMINI_API_KEY:
            st.error("Add valid Gemini API key in Streamlit secrets.")
        elif question:
            with st.spinner("AI..."):
                try:
                    genai.configure(api_key=GEMINI_API_KEY)
                    prompt = f"""
                    You are a Kuwaiti Arabic tutor.
                    Arabic word: {arabic}
                    Meaning: {english}
                    Student question: {question}
                    Answer in simple English. Focus on Kuwaiti dialect. Keep it under 4 lines.
                    """
                    try:
                        response = genai.GenerativeModel('gemini-1.5-flash').generate_content(prompt)
                    except Exception:
                        response = genai.GenerativeModel('gemini-pro').generate_content(prompt)
                    st.session_state[note_key] += f"\nQ: {question}\nAI: {response.text.strip()}\n"
                    save_note(conn, word_id, st.session_state[note_key])
                    st.toast("AI note added")
                except Exception:
                    st.error("AI error. Please check Gemini API key/model access.")

    st.session_state[note_key] = ai_c3.text_area(
        "Edit notes",
        value=st.session_state[note_key],
        key=text_key,
        label_visibility="collapsed",
        placeholder="Notes...",
        height=42
    )

    if ai_c4.button("✎", key=f"save_{word_id}_{tab_key}", help="Save note"):
        save_note(conn, word_id, st.session_state[note_key])
        st.toast("Saved")

# --- MAIN APP SETUP ---
st.markdown("## 🇰🇼 Yalla Kuwaiti!")

if "player_style" not in st.session_state:
    st.session_state.player_style = "Mini Player"
if "selected_tab" not in st.session_state:
    st.session_state.selected_tab = "🎮 Daily"

conn = init_db()
try:
    df = fetch_sheet_data(SHEET_URL)
    sync_data(conn, df)
except Exception as e:
    st.error(f"Sheet Error: {e}")

# Sidebar
st.sidebar.header("Filter")
chapters = [row[0] for row in conn.cursor().execute("SELECT DISTINCT chapter FROM vocab WHERE chapter != '' ORDER BY chapter").fetchall()]
selected_chapter = st.sidebar.selectbox("Choose Chapter", ["All Chapters"] + chapters)

total, mastered, learning, practice = get_stats(conn)
st.sidebar.divider()
st.sidebar.markdown("### 🏆 Progress")
st.sidebar.metric("Mastered", mastered)
st.sidebar.metric("Needs Practice", practice)
st.sidebar.progress(mastered / total if total > 0 else 0, text=f"Fluency: {int((mastered/total)*100) if total else 0}%")

# Use segmented control instead of tabs so Settings does not render Practice/Mastered lists unnecessarily.
selected_tab = st.segmented_control(
    "Section",
    options=["🎮 Daily", "🏋️ Practice", "👑 Mastered", "⚙️ Settings"],
    default=st.session_state.selected_tab,
    label_visibility="collapsed"
)
st.session_state.selected_tab = selected_tab

base_q = "SELECT * FROM vocab"
params = []
if selected_chapter != "All Chapters":
    base_q += " WHERE chapter = ?"
    params.append(selected_chapter)

if selected_tab == "🎮 Daily":
    q1 = base_q + (" AND score < 3" if "WHERE" in base_q else " WHERE score < 3")
    words = conn.cursor().execute(q1, params).fetchall()
    if words:
        if "current_word" not in st.session_state or st.session_state.current_word is None:
            st.session_state.current_word = random.choice(words)
        render_flashcard(conn, st.session_state.current_word, "home", st.session_state.player_style)
    else:
        st.success("🎉 You've mastered all words in this section!")

elif selected_tab == "🏋️ Practice":
    q2 = base_q + (" AND score = 0" if "WHERE" in base_q else " WHERE score = 0")
    rows = conn.cursor().execute(q2, params).fetchall()
    st.caption(f"Showing {len(rows)} practice words")
    for w in rows[:25]:
        with st.expander(f"🔴 {w[2]} ({w[4]})"):
            render_flashcard(conn, w, f"prac_{w[0]}", st.session_state.player_style)
    if len(rows) > 25:
        st.info("Showing first 25 only to keep the page fast. Choose a chapter to narrow the list.")

elif selected_tab == "👑 Mastered":
    q3 = base_q + (" AND score >= 3" if "WHERE" in base_q else " WHERE score >= 3")
    rows = conn.cursor().execute(q3, params).fetchall()
    st.caption(f"Showing {len(rows)} mastered words")
    for w in rows[:25]:
        with st.expander(f"👑 {w[2]} ({w[4]})"):
            render_flashcard(conn, w, f"mast_{w[0]}", st.session_state.player_style)
    if len(rows) > 25:
        st.info("Showing first 25 only to keep the page fast. Choose a chapter to narrow the list.")

elif selected_tab == "⚙️ Settings":
    st.markdown("### ⚙️ App Preferences")
    st.session_state.player_style = st.radio(
        "Audio Player Style:",
        options=["Mini Player", "Full Streamlit Player"],
        index=0 if st.session_state.player_style == "Mini Player" else 1,
        horizontal=True,
        help="Mini Player uses a smaller footprint. Full Player uses Streamlit's native audio UI."
    )
    if st.button("Refresh sheet data"):
        fetch_sheet_data.clear()
        st.session_state.current_word = None
        st.rerun()

conn.close()

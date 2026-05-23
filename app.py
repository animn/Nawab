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

# --- Mobile-first compact UI CSS ---
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 0.75rem;
            padding-bottom: 0.75rem;
            max-width: 760px;
        }
        h2, h3, p { margin-top: 0rem; margin-bottom: 0.2rem; }
        div[data-testid="stVerticalBlock"] { gap: 0.36rem; }
        div[data-testid="stHorizontalBlock"] { gap: 0.32rem; align-items: center; }
        div[data-testid="column"] { padding: 0rem 0.03rem; }
        .stButton > button {
            min-height: 2.05rem;
            height: 2.05rem;
            padding: 0rem 0.35rem;
            line-height: 1;
            width: 100%;
            font-size: 0.92rem;
        }
        .stTextInput input {
            min-height: 2.05rem;
            height: 2.05rem;
            padding-top: 0.1rem;
            padding-bottom: 0.1rem;
            font-size: 0.94rem;
        }
        textarea {
            min-height: 44px !important;
            padding-top: 0.25rem !important;
            padding-bottom: 0.25rem !important;
            font-size: 0.9rem !important;
        }
        div[data-testid="stExpander"] details summary {
            padding-top: 0.32rem;
            padding-bottom: 0.32rem;
        }
        .word-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 8px;
            margin: 0.05rem 0 0.1rem 0;
        }
        .word-chapter { font-size: 0.92rem; font-weight: 700; overflow-wrap: anywhere; }
        .word-score { font-size: 0.88rem; white-space: nowrap; text-align: right; }
        .compact-arabic {
            text-align: right;
            font-size: 34px;
            line-height: 1.05;
            margin: 0.05rem 0 0.25rem 0;
        }
        .mini-audio-wrap {
            width: 1px;
            height: 1px;
            overflow: hidden;
            opacity: 0.01;
            position: absolute;
            pointer-events: none;
        }
        .note-preview {
            font-size: 0.82rem;
            opacity: 0.82;
            border: 1px solid rgba(128,128,128,0.35);
            border-radius: 0.5rem;
            padding: 0.4rem 0.55rem;
            min-height: 2.05rem;
            max-height: 2.6rem;
            overflow: hidden;
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
def get_audio_bytes(text):
    if not text:
        return None
    try:
        tts = gTTS(text=text, lang='ar')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        return fp.getvalue()
    except Exception:
        return None

def render_mini_audio(audio_bytes, word_id):
    if not audio_bytes:
        st.caption("Audio unavailable")
        return
    b64 = base64.b64encode(audio_bytes).decode()
    audio_id = f"aud_{word_id}"
    st.markdown(
        f"""
        <div style="display:flex; gap:8px; align-items:center; width:100%;">
            <button onclick="const a=document.getElementById('{audio_id}'); a.currentTime=0; a.play();" style="height:34px; min-width:62px; border-radius:8px; border:1px solid rgba(128,128,128,.45); background:transparent; color:inherit; font-size:15px;">▶</button>
            <select onchange="document.getElementById('{audio_id}').playbackRate=parseFloat(this.value);" style="height:34px; min-width:68px; border-radius:8px; border:1px solid rgba(128,128,128,.45); background:transparent; color:inherit; font-size:14px;">
                <option value="0.75">0.75x</option>
                <option value="1" selected>1x</option>
                <option value="1.25">1.25x</option>
                <option value="1.5">1.5x</option>
            </select>
            <audio id="{audio_id}" preload="auto" src="data:audio/mp3;base64,{b64}"></audio>
        </div>
        """,
        unsafe_allow_html=True,
    )

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

        word_id = hashlib.md5(arabic_text.encode()).hexdigest()
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
                  (word_id, clean_val(row.get('chapter')), arabic_text,
                   clean_val(row.get('pronunciation')), clean_val(row.get('englishmeaning')),
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

    st.markdown(
        f"""
        <div class="word-header">
            <div class="word-chapter">{chapter}</div>
            <div class="word-score">Score {score}/3</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    b1, b2 = st.columns([1, 1])
    if b1.button("👍", key=f"up_{word_id}_{tab_key}", use_container_width=True, help="I know this"):
        update_score(conn, word_id, True)
        if tab_key == "home":
            st.session_state.current_word = None
        st.rerun()
    if b2.button("👎", key=f"down_{word_id}_{tab_key}", use_container_width=True, help="Needs practice"):
        update_score(conn, word_id, False)
        if tab_key == "home":
            st.session_state.current_word = None
        st.rerun()

    with st.container(border=True):
        st.markdown(f"<h1 class='compact-arabic' dir='rtl'>{arabic}</h1>", unsafe_allow_html=True)
        audio_bytes = get_audio_bytes(arabic)
        if player_style == "Mini Player":
            render_mini_audio(audio_bytes, word_id)
        else:
            if audio_bytes:
                st.audio(audio_bytes, format="audio/mp3")
            else:
                st.caption("Audio unavailable")

        with st.expander(f"🗣️ {pronunc} | {english}"):
            if expl:
                st.info(f"**Explanation:** {expl}")
            if l_pronunc or l_eng:
                if l_pronunc:
                    st.write(f"**Letter pronunciation:** {l_pronunc}")
                if l_eng:
                    st.write(f"**Letter English:** {l_eng}")

    note_key = f"note_{word_id}_{tab_key}"
    edit_key = f"edit_note_{word_id}_{tab_key}"
    if note_key not in st.session_state:
        st.session_state[note_key] = saved_note if saved_note else ""
    if edit_key not in st.session_state:
        st.session_state[edit_key] = False

    sa_input, sa_button = st.columns([5, 1.05])
    question = sa_input.text_input(
        "S.A",
        key=f"q_{word_id}_{tab_key}",
        label_visibility="collapsed",
        placeholder="S.A..."
    )

    if sa_button.button("S.A", key=f"ask_{word_id}_{tab_key}", use_container_width=True, help="Ask S.A"):
        if not GEMINI_API_KEY:
            st.error("Add valid Gemini API key in Streamlit secrets.")
        elif question:
            with st.spinner("S.A..."):
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
                    answer = response.text.strip()
                    st.session_state[note_key] += f"\nQ: {question}\nS.A: {answer}\n"
                    save_note(conn, word_id, st.session_state[note_key])
                    st.toast("Saved to notes")
                except Exception:
                    st.error("S.A error. Please check Gemini API key/model access.")

    note_col, edit_col = st.columns([5, 1.05])
    note_preview = st.session_state[note_key].strip() or "Notes..."
    note_col.markdown(f"<div class='note-preview'>{note_preview[-160:]}</div>", unsafe_allow_html=True)
    if edit_col.button("✎", key=f"edit_{word_id}_{tab_key}", use_container_width=True, help="Edit notes"):
        st.session_state[edit_key] = not st.session_state[edit_key]

    if st.session_state[edit_key]:
        st.session_state[note_key] = st.text_area(
            "Edit notes",
            value=st.session_state[note_key],
            key=f"text_{word_id}_{tab_key}",
            label_visibility="collapsed",
            placeholder="Notes...",
            height=54
        )
        if st.button("Save", key=f"save_{word_id}_{tab_key}", use_container_width=True):
            save_note(conn, word_id, st.session_state[note_key])
            st.session_state[edit_key] = False
            st.toast("Saved")
            st.rerun()

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

selected_tab = st.radio(
    "Section",
    options=["🎮 Daily", "🏋️ Practice", "👑 Mastered", "⚙️ Settings"],
    index=["🎮 Daily", "🏋️ Practice", "👑 Mastered", "⚙️ Settings"].index(st.session_state.selected_tab),
    horizontal=True,
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
        current = st.session_state.get("current_word")
        valid_ids = {w[0] for w in words}
        if current is None or current[0] not in valid_ids:
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
        help="Mini Player shows only Play + speed. Full Player uses Streamlit's native audio UI."
    )
    if st.button("Refresh sheet data"):
        fetch_sheet_data.clear()
        st.session_state.current_word = None
        st.rerun()

conn.close()

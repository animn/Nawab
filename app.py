import streamlit as st
import pandas as pd
import sqlite3
from gtts import gTTS
import io
import random
import hashlib
import google.generativeai as genai

# --- Configuration & Keys ---
st.set_page_config(page_title="Yalla Kuwaiti!", page_icon="🇰🇼", layout="centered")

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    GEMINI_API_KEY = None

SHEET_URL = "https://docs.google.com/spreadsheets/d/1DQ_74TZtMpbinusdnMOU2441hEFa7RRnaqeMx8qrBg0/export?format=csv"
DB_NAME = "learning_progress_v8.db" # Kept v8 so your current progress is saved!

# --- AGGRESSIVE COMPRESSION CSS ---
st.markdown(
    """
    <style>
        .block-container { padding-top: 2rem !important; padding-bottom: 0.5rem !important; max-width: 600px; }
        [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; align-items: center !important; gap: 0.2rem !important; }
        [data-testid="column"] { min-width: 0 !important; flex-basis: 0 !important; flex-grow: 1 !important; }
        [data-testid="stVerticalBlockBorderWrapper"] { padding: 0.5rem !important; }
        audio { height: 40px !important; width: 100% !important; }
        .stButton button, .stTextInput input { min-height: 34px !important; height: 34px !important; padding: 0 5px !important; font-size: 14px !important; }
        .arabic-word { text-align: right; font-size: 40px; margin: 0 0 0.2rem 0; line-height: 1.1; }
        .note-preview { font-size: 0.8rem; color: #ccc; border: 1px solid #555; border-radius: 5px; padding: 6px 8px; height: 34px; line-height: 1.2; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- HELPER FUNCTIONS ---
def clean_val(val):
    if pd.isna(val) or str(val).strip().lower() == 'nan': return ""
    return str(val).strip()

@st.cache_data(show_spinner=False)
def get_audio_bytes(text):
    text = clean_val(text)
    if not text: return None
    try:
        tts = gTTS(text=text, lang='ar')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        return fp.getvalue()
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
        if not arabic_text: continue

        word_id = hashlib.md5(arabic_text.encode()).hexdigest()
        l_pron = clean_val(row.get('letterwisepronounciation', row.get('letterwisepronunciation', '')))

        c.execute('''INSERT INTO vocab (id, chapter, arabic, pronunciation, english,
                                        explanation, letter_pronunc, letter_eng, score, notes)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                     ON CONFLICT(id) DO UPDATE SET
                        chapter=excluded.chapter, arabic=excluded.arabic, pronunciation=excluded.pronunciation,
                        english=excluded.english, explanation=excluded.explanation,
                        letter_pronunc=excluded.letter_pronunc, letter_eng=excluded.letter_eng''',
                  (word_id, clean_val(row.get('chapter')), arabic_text, clean_val(row.get('pronunciation')), 
                   clean_val(row.get('englishmeaning')), clean_val(row.get('explanation')), l_pron,
                   clean_val(row.get('letterwiseenglish')), 0, ""))
    conn.commit()

def update_score(conn, word_id, is_correct):
    c = conn.cursor()
    row = c.execute("SELECT score FROM vocab WHERE id=?", (word_id,)).fetchone()
    if not row: return 0
    new_score = (row[0] or 0) + 1 if is_correct else 0
    c.execute("UPDATE vocab SET score=? WHERE id=?", (new_score, word_id))
    conn.commit()
    return new_score

def save_note(conn, word_id, note_text):
    conn.cursor().execute("UPDATE vocab SET notes=? WHERE id=?", (note_text, word_id))
    conn.commit()

def get_stats(conn):
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM vocab").fetchone()[0]
    mastered = c.execute("SELECT COUNT(*) FROM vocab WHERE score >= 3").fetchone()[0]
    practice = c.execute("SELECT COUNT(*) FROM vocab WHERE score = 0").fetchone()[0]
    learning = total - mastered - practice
    return total, mastered, learning, practice

# --- UI COMPONENT MODULE ---
def render_flashcard(conn, word_data, tab_key):
    word_id, chapter, arabic, pronunc, english, expl, l_pronunc, l_eng, score, saved_note = word_data

    c1, c2, c3 = st.columns([5, 1.2, 1.2])
    c1.markdown(f"<div style='line-height:1.2; margin-bottom:5px;'><b>{chapter}</b><br><span style='font-size:12px; color:#aaa;'>Score: {score}/3</span></div>", unsafe_allow_html=True)
    
    if c2.button("👍", key=f"up_{word_id}_{tab_key}"):
        new_score = update_score(conn, word_id, True)
        # Set a session state toast so it triggers after the page reruns
        st.session_state.flash_toast = f"👍 Correct! Score increased to {new_score}/3" if new_score < 3 else "👑 Word Mastered!"
        if tab_key == "home": st.session_state.current_word = None
        st.rerun()
        
    if c3.button("👎", key=f"down_{word_id}_{tab_key}"):
        update_score(conn, word_id, False)
        st.session_state.flash_toast = "👎 Score reset to 0. We'll practice this more!"
        if tab_key == "home": st.session_state.current_word = None
        st.rerun()

    with st.container(border=True):
        st.markdown(f"<h1 class='arabic-word' dir='rtl'>{arabic}</h1>", unsafe_allow_html=True)
        audio_bytes = get_audio_bytes(arabic)
        if audio_bytes: st.audio(audio_bytes, format="audio/mp3")
        
        display_title = f"{pronunc if pronunc else 'Pronunciation'} | {english if english else 'Meaning'}"
        with st.expander(f"🗣️ {display_title}"):
            if expl: st.info(f"**Explanation:** {expl}")
            if l_pronunc: st.write(f"**Letters (Sound):** {l_pronunc}")
            if l_eng: st.write(f"**Letters (English):** {l_eng}")

    note_key = f"note_{word_id}_{tab_key}"
    edit_key = f"edit_note_{word_id}_{tab_key}"
    if note_key not in st.session_state: st.session_state[note_key] = saved_note if saved_note else ""
    if edit_key not in st.session_state: st.session_state[edit_key] = False

    sa_col1, sa_col2 = st.columns([4.2, 1])
    question = sa_col1.text_input("Ask S.AI", key=f"q_{word_id}_{tab_key}", label_visibility="collapsed", placeholder="Ask S.AI a short question...")
    
    if sa_col2.button("S.AI", key=f"ask_{word_id}_{tab_key}"):
        if not GEMINI_API_KEY: st.error("Add API key!")
        elif question:
            with st.spinner(".."):
                try:
                    genai.configure(api_key=GEMINI_API_KEY)
                    try: resp = genai.GenerativeModel('gemini-1.5-flash').generate_content(f"Arabic: {arabic}. Meaning: {english}. Question: {question}. Answer short in Kuwaiti context.")
                    except: resp = genai.GenerativeModel('gemini-pro').generate_content(f"Arabic: {arabic}. Meaning: {english}. Question: {question}. Answer short in Kuwaiti context.")
                    st.session_state[note_key] += f"\nQ: {question}\nS.AI: {resp.text.strip()}\n"
                    save_note(conn, word_id, st.session_state[note_key])
                    st.toast("Note updated!")
                except Exception: st.error("S.AI Error.")

    nt_col1, nt_col2 = st.columns([4.2, 1])
    display_text = st.session_state[note_key].strip() or "No notes yet..."
    nt_col1.markdown(f"<div class='note-preview'>{display_text}</div>", unsafe_allow_html=True)
    
    if nt_col2.button("✏️", key=f"edit_btn_{word_id}_{tab_key}"):
        st.session_state[edit_key] = not st.session_state[edit_key]

    if st.session_state[edit_key]:
        st.session_state[note_key] = st.text_area("Edit notes", value=st.session_state[note_key], key=f"text_{word_id}_{tab_key}", label_visibility="collapsed", height=70)
        if st.button("💾 Save", key=f"save_{word_id}_{tab_key}", use_container_width=True):
            save_note(conn, word_id, st.session_state[note_key])
            st.session_state[edit_key] = False
            st.toast("Saved")
            st.rerun()

# --- MAIN APP SETUP ---
# Trigger any pending toast notifications immediately on load
if "flash_toast" in st.session_state:
    st.toast(st.session_state.flash_toast)
    del st.session_state.flash_toast

st.markdown("### 🇰🇼 Yalla Kuwaiti!")

conn = init_db()
try:
    df = fetch_sheet_data(SHEET_URL)
    sync_data(conn, df)
except Exception as e: st.error("Spreadsheet error. Check access.")

st.sidebar.header("Filters")
chapters = [row[0] for row in conn.cursor().execute("SELECT DISTINCT chapter FROM vocab WHERE chapter != '' ORDER BY chapter").fetchall()]
selected_chapter = st.sidebar.selectbox("Chapter", ["All"] + chapters)

total, mastered, learning, practice = get_stats(conn)
st.sidebar.divider()
st.sidebar.markdown("🏆 **Progress Dashboard**")
st.sidebar.metric("👑 Mastered (Score 3+)", mastered)
st.sidebar.metric("📈 Learning (Score 1-2)", learning)
st.sidebar.metric("🔴 Needs Practice (Score 0)", practice)
st.sidebar.progress(mastered / total if total > 0 else 0, text=f"Overall Fluency: {int((mastered/total)*100) if total else 0}%")

tab1, tab2, tab3, tab4 = st.tabs(["🎮 Daily", "🏋️ Review", "👑 Mastered", "⚙️ Sync"])

base_q = "SELECT * FROM vocab"
params = []
if selected_chapter != "All":
    base_q += " WHERE chapter = ?"
    params.append(selected_chapter)

with tab1:
    words = conn.cursor().execute(base_q + (" AND score < 3" if "WHERE" in base_q else " WHERE score < 3"), params).fetchall()
    if words:
        current = st.session_state.get("current_word")
        valid_ids = {w[0] for w in words}
        if current is None or current[0] not in valid_ids:
            st.session_state.current_word = random.choice(words)
        render_flashcard(conn, st.session_state.current_word, "home")
    else:
        st.success("🎉 Section fully mastered! Check the Mastered tab.")

with tab2:
    # Changed from score=0 to score<3 so words don't vanish while you are learning them!
    rows = conn.cursor().execute(base_q + (" AND score < 3 ORDER BY score ASC" if "WHERE" in base_q else " WHERE score < 3 ORDER BY score ASC"), params).fetchall()
    for w in rows[:20]:
        with st.expander(f"🔴 {w[2]} ({w[4]}) - Score: {w[8]}/3"):
            render_flashcard(conn, w, f"prac_{w[0]}")

with tab3:
    rows = conn.cursor().execute(base_q + (" AND score >= 3" if "WHERE" in base_q else " WHERE score >= 3"), params).fetchall()
    for w in rows[:20]:
        with st.expander(f"👑 {w[2]} ({w[4]})"):
            render_flashcard(conn, w, f"mast_{w[0]}")

with tab4:
    st.info("Force a manual sync with your Google Sheet below if new words aren't showing up.")
    if st.button("Refresh Spreadsheet Data"):
        fetch_sheet_data.clear()
        st.session_state.current_word = None
        st.rerun()

conn.close()
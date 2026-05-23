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

# --- HELPER FUNCTIONS ---
def clean_val(val):
    """Prevents 'nan' from showing up in the UI and crashing the app."""
    if pd.isna(val) or str(val).strip().lower() == 'nan':
        return ""
    return str(val).strip()

@st.cache_data(show_spinner=False)
def get_audio_player(text, player_style):
    """Generates audio once and caches it. Returns HTML for mini player or bytes for native."""
    if not text: return None
    try:
        tts = gTTS(text=text, lang='ar')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        audio_bytes = fp.getvalue()
        
        if player_style == "Mini Player":
            b64 = base64.b64encode(audio_bytes).decode()
            # Custom HTML audio player to save space
            return f'''
                <audio controls style="height: 35px; width: 100%; border-radius: 5px;">
                    <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
                </audio>
            '''
        return audio_bytes
    except:
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

@st.cache_data(ttl=600)
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
        
        c.execute("SELECT id FROM vocab WHERE id=?", (word_id,))
        if not c.fetchone():
            c.execute('''INSERT INTO vocab (id, chapter, arabic, pronunciation, english, 
                                            explanation, letter_pronunc, letter_eng, score, notes)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                      (word_id, clean_val(row.get('chapter')), arabic_text, 
                       clean_val(row.get('pronunciation')), clean_val(row.get('englishmeaning')), 
                       clean_val(row.get('explanation')), l_pron, 
                       clean_val(row.get('letterwiseenglish')), 0, ""))
    conn.commit()

def update_score(conn, word_id, is_correct):
    conn.cursor().execute("UPDATE vocab SET score = ? WHERE id=?", 
                          (conn.cursor().execute("SELECT score FROM vocab WHERE id=?", (word_id,)).fetchone()[0] + 1 if is_correct else 0, word_id))
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
    
    # Inline Compact Header
    hc1, hc2, hc3, hc4 = st.columns([4, 2, 1, 1])
    hc1.markdown(f"**{chapter}**")
    hc2.caption(f"Score: {score}/3")
    if hc3.button("👍", key=f"up_{word_id}_{tab_key}"):
        update_score(conn, word_id, True)
        if tab_key == "home": st.session_state.current_word = None
        st.rerun()
    if hc4.button("👎", key=f"down_{word_id}_{tab_key}"):
        update_score(conn, word_id, False)
        if tab_key == "home": st.session_state.current_word = None
        st.rerun()

    # Flashcard Body
    with st.container(border=True):
        f_col1, f_col2 = st.columns([3, 2])
        f_col1.markdown(f"<h1 style='text-align: right; font-size: 40px; margin:0;' dir='rtl'>{arabic}</h1>", unsafe_allow_html=True)
        
        # Audio Player (No Rerun Required)
        with f_col2:
            st.write("") # Spacing
            audio_data = get_audio_player(arabic, player_style)
            if audio_data:
                if player_style == "Mini Player":
                    st.markdown(audio_data, unsafe_allow_html=True)
                else:
                    st.audio(audio_data, format="audio/mp3")

        # Expander for Meaning (No Rerun Required)
        with st.expander(f"🗣️ Meaning: **{pronunc}**"):
            if english: st.success(f"**English:** {english}")
            if expl: st.info(f"**Explanation:** {expl}")
            if l_pronunc or l_eng:
                st.divider()
                st.caption("🔍 Letter-wise Breakdown")
                if l_pronunc: st.write(f"**Pronunciation:** {l_pronunc}")
                if l_eng: st.write(f"**English:** {l_eng}")

    # Compact AI & Notes Bar
    note_key = f"note_{word_id}_{tab_key}"
    if note_key not in st.session_state: st.session_state[note_key] = saved_note if saved_note else ""
    
    st.caption("📝 Notes & AI Tutor")
    ai_c1, ai_c2, ai_c3 = st.columns([5, 1, 1])
    question = ai_c1.text_input("Ask AI", key=f"q_{word_id}_{tab_key}", label_visibility="collapsed", placeholder="Ask AI a quick question...")
    
    if ai_c2.button("🤖", key=f"ask_{word_id}_{tab_key}", help="Ask Gemini"):
        if not GEMINI_API_KEY: st.error("Add valid API Key!")
        elif question:
            with st.spinner(".."):
                try:
                    genai.configure(api_key=GEMINI_API_KEY)
                    try: # Try Flash first, fallback to Pro
                        response = genai.GenerativeModel('gemini-1.5-flash').generate_content(f"Word: {arabic} ({english}). Q: {question}. Answer in 2 short sentences.")
                    except:
                        response = genai.GenerativeModel('gemini-pro').generate_content(f"Word: {arabic} ({english}). Q: {question}. Answer in 2 short sentences.")
                    
                    st.session_state[note_key] += f"\nQ: {question}\nAI: {response.text.strip()}\n"
                    conn.cursor().execute("UPDATE vocab SET notes=? WHERE id=?", (st.session_state[note_key], word_id))
                    conn.commit()
                except Exception as e: st.error(f"API Error.")

    if ai_c3.button("💾", key=f"save_{word_id}_{tab_key}", help="Save Note"):
        conn.cursor().execute("UPDATE vocab SET notes=? WHERE id=?", (st.session_state[note_key], word_id))
        conn.commit()
        st.toast("Note Saved!")

    # Editable Text Box
    st.session_state[note_key] = st.text_area("Edit", value=st.session_state[note_key], key=f"text_{word_id}_{tab_key}", label_visibility="collapsed", height=68)

# --- MAIN APP SETUP ---
st.markdown("## 🇰🇼 Yalla Kuwaiti!")

if "player_style" not in st.session_state:
    st.session_state.player_style = "Mini Player"

conn = init_db()
try:
    df = fetch_sheet_data(SHEET_URL)
    sync_data(conn, df)
except Exception as e: st.error(f"Sheet Error: {e}")

# Sidebar
st.sidebar.header("Filter")
chapters = [row[0] for row in conn.cursor().execute("SELECT DISTINCT chapter FROM vocab WHERE chapter != ''").fetchall()]
selected_chapter = st.sidebar.selectbox("Choose Chapter", ["All Chapters"] + chapters)

total, mastered, learning, practice = get_stats(conn)
st.sidebar.divider()
st.sidebar.markdown("### 🏆 Progress")
st.sidebar.metric("Mastered", mastered)
st.sidebar.metric("Needs Practice", practice)
st.sidebar.progress(mastered / total if total > 0 else 0, text=f"Fluency: {int((mastered/total)*100) if total else 0}%")

# Main Tabs
tab1, tab2, tab3, tab4 = st.tabs(["🎮 Daily", "🏋️ Practice", "👑 Mastered", "⚙️ Settings"])

base_q = "SELECT * FROM vocab"
params = []
if selected_chapter != "All Chapters":
    base_q += " WHERE chapter = ?"
    params.append(selected_chapter)

with tab1:
    q1 = base_q + (" AND score < 3" if "WHERE" in base_q else " WHERE score < 3")
    words = conn.cursor().execute(q1, params).fetchall()
    if words:
        if "current_word" not in st.session_state or st.session_state.current_word is None:
            st.session_state.current_word = random.choice(words)
        render_flashcard(conn, st.session_state.current_word, "home", st.session_state.player_style)
    else:
        st.success("🎉 You've mastered all words in this section!")

with tab2:
    q2 = base_q + (" AND score = 0" if "WHERE" in base_q else " WHERE score = 0")
    for w in conn.cursor().execute(q2, params).fetchall():
        with st.expander(f"🔴 {w[2]} ({w[4]})"):
            render_flashcard(conn, w, f"prac_{w[0]}", st.session_state.player_style)

with tab3:
    q3 = base_q + (" AND score >= 3" if "WHERE" in base_q else " WHERE score >= 3")
    for w in conn.cursor().execute(q3, params).fetchall():
        with st.expander(f"👑 {w[2]} ({w[4]})"):
            render_flashcard(conn, w, f"mast_{w[0]}", st.session_state.player_style)

with tab4:
    st.markdown("### ⚙️ App Preferences")
    st.session_state.player_style = st.radio(
        "Audio Player Style:", 
        options=["Mini Player", "Full Streamlit Player"], 
        index=0 if st.session_state.player_style == "Mini Player" else 1,
        help="Mini Player uses a smaller footprint. Full Player uses Streamlit's native audio UI."
    )

conn.close()
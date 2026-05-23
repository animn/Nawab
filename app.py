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

# AGGRESSIVE UI COMPRESSION & MOBILE STACKING OVERRIDE
st.markdown("""
    <style>
        /* Remove top whitespace */
        .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
        
        /* Force Streamlit to NEVER stack columns vertically on mobile */
        [data-testid="column"] {
            min-width: 0 !important;
            flex-basis: 0 !important;
            flex-grow: 1 !important;
        }
        
        /* Shrink input boxes and buttons to save space */
        .stTextInput input { min-height: 35px !important; height: 35px !important; padding: 5px !important; }
        .stButton button { min-height: 35px !important; height: 35px !important; padding: 0 !important; }
        
        /* Tighten expander spacing */
        .streamlit-expanderHeader { padding-top: 0 !important; padding-bottom: 0 !important; }
    </style>
""", unsafe_allow_html=True)

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    GEMINI_API_KEY = None

SHEET_URL = "https://docs.google.com/spreadsheets/d/1DQ_74TZtMpbinusdnMOU2441hEFa7RRnaqeMx8qrBg0/export?format=csv"
DB_NAME = "learning_progress_v9.db"

# --- HELPER FUNCTIONS ---
def clean_val(val):
    if pd.isna(val) or str(val).strip().lower() == 'nan': return ""
    return str(val).strip()

def generate_mini_audio(text):
    """Generates a compact HTML audio player with speed controls."""
    try:
        tts = gTTS(text=text, lang='ar')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        b64 = base64.b64encode(fp.getvalue()).decode()
        return f'''
            <audio controls style="height: 30px; width: 180px;">
                <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
            </audio>
        '''
    except:
        return "<p>Audio Error</p>"

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
    c = conn.cursor()
    current_score = c.execute("SELECT score FROM vocab WHERE id=?", (word_id,)).fetchone()[0]
    new_score = current_score + 1 if is_correct else 0
    c.execute("UPDATE vocab SET score = ? WHERE id=?", (new_score, word_id))
    conn.commit()

def get_stats(conn):
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM vocab").fetchone()[0]
    mastered = c.execute("SELECT COUNT(*) FROM vocab WHERE score >= 3").fetchone()[0]
    practice = c.execute("SELECT COUNT(*) FROM vocab WHERE score = 0").fetchone()[0]
    return total, mastered, total - mastered - practice, practice

# --- UI COMPONENT MODULE ---
def render_flashcard(conn, word_data, tab_key):
    word_id, chapter, arabic, pronunc, english, expl, l_pronunc, l_eng, score, saved_note = word_data
    
    # ROW 1: INLINE HEADER (Forced by CSS)
    h_col1, h_col2, h_col3, h_col4 = st.columns([5, 3, 1, 1])
    h_col1.markdown(f"**{chapter}**")
    h_col2.caption(f"Score:{score}/3")
    if h_col3.button("👍", key=f"up_{word_id}_{tab_key}"):
        update_score(conn, word_id, True)
        if tab_key == "home": st.session_state.current_word = None
        st.rerun()
    if h_col4.button("👎", key=f"down_{word_id}_{tab_key}"):
        update_score(conn, word_id, False)
        if tab_key == "home": st.session_state.current_word = None
        st.rerun()

    # ROW 2: FLASHCARD BODY
    with st.container(border=True):
        st.markdown(f"<h1 style='text-align: right; font-size: 38px; margin:0;' dir='rtl'>{arabic}</h1>", unsafe_allow_html=True)
        
        audio_key = f"audio_{word_id}_{tab_key}"
        if audio_key not in st.session_state: st.session_state[audio_key] = False
        
        # Audio Button right beneath text to save space
        if st.button("🔊 Load Audio", key=f"btn_{audio_key}"):
            st.session_state[audio_key] = True
            
        if st.session_state[audio_key]:
            st.markdown(generate_mini_audio(arabic), unsafe_allow_html=True)

        with st.expander(f"🗣️ Meaning: **{pronunc}**"):
            if english: st.success(f"**English:** {english}")
            if expl: st.info(f"**Explanation:** {expl}")
            if l_pronunc or l_eng:
                st.divider()
                st.caption("🔍 Breakdown")
                if l_pronunc: st.write(f"**Sound:** {l_pronunc}")
                if l_eng: st.write(f"**Letters:** {l_eng}")

    # ROW 3: AI & NOTES (Forced Inline by CSS)
    note_key = f"note_{word_id}_{tab_key}"
    if note_key not in st.session_state: st.session_state[note_key] = saved_note if saved_note else ""
    
    ai_col1, ai_col2, ai_col3 = st.columns([5, 1, 1])
    question = ai_col1.text_input("Ask AI", key=f"q_{word_id}_{tab_key}", label_visibility="collapsed", placeholder="Ask AI...")
    
    if ai_col2.button("🤖", key=f"ask_{word_id}_{tab_key}"):
        if not GEMINI_API_KEY: st.error("Add API Key!")
        elif question:
            with st.spinner(".."):
                try:
                    genai.configure(api_key=GEMINI_API_KEY)
                    try:
                        resp = genai.GenerativeModel('gemini-1.5-flash').generate_content(f"Word: {arabic}. Q: {question}. Answer 1 sentence.")
                    except:
                        resp = genai.GenerativeModel('gemini-pro').generate_content(f"Word: {arabic}. Q: {question}. Answer 1 sentence.")
                    
                    st.session_state[note_key] += f"\nQ: {question}\nAI: {resp.text.strip()}\n"
                    conn.cursor().execute("UPDATE vocab SET notes=? WHERE id=?", (st.session_state[note_key], word_id))
                    conn.commit()
                except Exception as e: st.error("API Error.")

    if ai_col3.button("💾", key=f"save_{word_id}_{tab_key}"):
        conn.cursor().execute("UPDATE vocab SET notes=? WHERE id=?", (st.session_state[note_key], word_id))
        conn.commit()
        st.toast("Saved!")

    st.session_state[note_key] = st.text_area("Edit Notes", value=st.session_state[note_key], key=f"text_{word_id}_{tab_key}", label_visibility="collapsed", height=60)

# --- MAIN APP SETUP ---
st.markdown("### 🇰🇼 Yalla Kuwaiti!")

conn = init_db()
try:
    df = fetch_sheet_data(SHEET_URL)
    sync_data(conn, df)
except Exception as e: st.error(f"Sheet Error: {e}")

# Gamification Stats
total, mastered, learning, practice = get_stats(conn)
st.progress(mastered / total if total > 0 else 0, text=f"Fluency: {int((mastered/total)*100) if total else 0}%")

tab1, tab2, tab3 = st.tabs(["🎮 Daily", "🏋️ Practice", "👑 Mastered"])

base_q = "SELECT * FROM vocab"

with tab1:
    words = conn.cursor().execute(base_q + " WHERE score < 3").fetchall()
    if words:
        if "current_word" not in st.session_state or st.session_state.current_word is None:
            st.session_state.current_word = random.choice(words)
        render_flashcard(conn, st.session_state.current_word, "home")
    else:
        st.success("🎉 You've mastered all words!")

with tab2:
    for w in conn.cursor().execute(base_q + " WHERE score = 0").fetchall():
        with st.expander(f"🔴 {w[2]} ({w[4]})"):
            render_flashcard(conn, w, f"prac_{w[0]}")

with tab3:
    for w in conn.cursor().execute(base_q + " WHERE score >= 3").fetchall():
        with st.expander(f"👑 {w[2]} ({w[4]})"):
            render_flashcard(conn, w, f"mast_{w[0]}")

conn.close()
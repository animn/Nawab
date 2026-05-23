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

# --- UI CSS ---
st.markdown("""
    <style>
        .block-container { padding: 1rem !important; max-width: 600px; }
        .arabic-word { text-align: right; font-size: 38px; margin: 0; line-height: 1.1; }
        .note-display { font-size: 0.9rem; color: #ddd; background: #262730; padding: 10px; border-radius: 5px; border: 1px solid #444; }
    </style>
""", unsafe_allow_html=True)

# --- DATABASE FUNCTIONS ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vocab (id TEXT PRIMARY KEY, chapter TEXT, arabic TEXT, pronunciation TEXT, english TEXT, explanation TEXT, score INTEGER, notes TEXT)''')
    conn.commit()
    return conn

@st.cache_data(ttl=600)
def fetch_sheet_data(url): return pd.read_csv(url)

def sync_data(conn, df):
    c = conn.cursor()
    df.columns = df.columns.str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.lower()
    for _, row in df.iterrows():
        arabic = str(row.get('arabicscript', ''))
        if not arabic or arabic == 'nan': continue
        word_id = hashlib.md5(arabic.encode()).hexdigest()
        c.execute("INSERT OR IGNORE INTO vocab (id, chapter, arabic, pronunciation, english, explanation, score, notes) VALUES (?,?,?,?,?,?,?,?)",
                  (word_id, str(row.get('chapter','')), arabic, str(row.get('pronunciation','')), str(row.get('englishmeaning','')), str(row.get('explanation','')), 0, ""))
    conn.commit()

# --- GEMINI REST API ---
def call_gemini(prompt, api_key):
    # This URL uses the latest stable generation method
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
    return resp.json()['candidates'][0]['content']['parts'][0]['text']

# --- UI MODULE ---
def render_flashcard(conn, word_data, tab_key):
    word_id, chapter, arabic, pronunc, english, expl, score, saved_note = word_data
    
    st.markdown(f"**{chapter}** | Score: {score}/3")
    
    # 50/50 Buttons
    c1, c2 = st.columns(2)
    if c1.button("👍 Got it", key=f"up_{word_id}", use_container_width=True):
        conn.cursor().execute("UPDATE vocab SET score=score+1 WHERE id=?", (word_id,))
        conn.commit()
        st.rerun()
    if c2.button("👎 Practice", key=f"down_{word_id}", use_container_width=True):
        conn.cursor().execute("UPDATE vocab SET score=0 WHERE id=?", (word_id,))
        conn.commit()
        st.rerun()

    with st.container(border=True):
        st.markdown(f"<h1 class='arabic-word' dir='rtl'>{arabic}</h1>", unsafe_allow_html=True)
        if st.button("🔊 Play Audio", key=f"play_{word_id}"):
            st.audio(io.BytesIO(gTTS(arabic, lang='ar').get_compressed_data()), format="audio/mp3")
        with st.expander(f"Meaning: {english}"):
            st.write(f"Pronunciation: {pronunc}")
            st.write(f"Explanation: {expl}")

    # S.AI Section
    note_key = f"note_{word_id}"
    if note_key not in st.session_state: st.session_state[note_key] = saved_note
    
    question = st.text_input("Ask S.AI:", key=f"q_{word_id}", placeholder="Ask 1 or 2...")
    
    if st.button("🤖 Ask S.AI", key=f"ask_{word_id}", use_container_width=True):
        # The prompt forces exactly 2 examples with no spacing
        prompt = f"Arabic word: {arabic}. Meaning: {english}. If the user asked '1', provide exactly 2 examples in Kuwaiti context without empty lines between them. Otherwise, answer the question normally."
        ans = call_gemini(prompt, GEMINI_API_KEY)
        st.session_state[note_key] = st.session_state[note_key] + "\n" + ans
        conn.cursor().execute("UPDATE vocab SET notes=? WHERE id=?", (st.session_state[note_key], word_id))
        conn.commit()
        st.rerun()

    # Autosave Edit Mode
    if st.session_state.get(f"edit_{word_id}"):
        new_note = st.text_area("Edit Notes", value=st.session_state[note_key], key=f"edit_area_{word_id}", height=150)
        if st.button("💾 Save & Close", key=f"save_{word_id}"):
            conn.cursor().execute("UPDATE vocab SET notes=? WHERE id=?", (new_note, word_id))
            conn.commit()
            st.session_state[note_key] = new_note
            st.session_state[f"edit_{word_id}"] = False
            st.rerun()
    else:
        st.markdown(f"<div class='note-display'>{st.session_state[note_key]}</div>", unsafe_allow_html=True)
        if st.button("✏️ Edit Notes", key=f"edit_btn_{word_id}"):
            st.session_state[f"edit_{word_id}"] = True
            st.rerun()

# --- MAIN ---
conn = init_db()
sync_data(conn, fetch_sheet_data(SHEET_URL))
st.title("🇰🇼 Yalla Kuwaiti!")

tab1, tab2 = st.tabs(["🎮 Daily", "👑 Mastered"])
with tab1:
    words = conn.cursor().execute("SELECT * FROM vocab WHERE score < 3").fetchall()
    if words: render_flashcard(conn, random.choice(words), "daily")
with tab2:
    for w in conn.cursor().execute("SELECT * FROM vocab WHERE score >= 3").fetchall():
        with st.expander(w[2]): render_flashcard(conn, w, "mastered")
conn.close()
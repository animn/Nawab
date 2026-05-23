import streamlit as st
import pandas as pd
import sqlite3
from gtts import gTTS
import io
import random
import hashlib
import requests

st.set_page_config(page_title="Yalla Kuwaiti!", page_icon="🇰🇼", layout="centered")

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    GEMINI_API_KEY = None

DB_NAME = "learning_progress_v8.db"

# --- DATABASE MODULE ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Ensure the table has the 'notes' column
    c.execute('''CREATE TABLE IF NOT EXISTS vocab 
                 (id TEXT PRIMARY KEY, chapter TEXT, arabic TEXT, 
                  pronunciation TEXT, english TEXT, explanation TEXT, 
                  score INTEGER, notes TEXT)''')
    # Add notes column if it doesn't exist
    try:
        c.execute("ALTER TABLE vocab ADD COLUMN notes TEXT")
    except: pass
    conn.commit()
    return conn

def sync_data(conn):
    url = "https://docs.google.com/spreadsheets/d/1DQ_74TZtMpbinusdnMOU2441hEFa7RRnaqeMx8qrBg0/export?format=csv"
    df = pd.read_csv(url)
    df.columns = df.columns.str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.lower()
    c = conn.cursor()
    for _, row in df.iterrows():
        arabic = str(row.get('arabicscript', ''))
        if not arabic or arabic == 'nan': continue
        word_id = hashlib.md5(arabic.encode()).hexdigest()
        c.execute("INSERT OR IGNORE INTO vocab VALUES (?,?,?,?,?,?,?,?)",
                  (word_id, str(row.get('chapter','')), arabic, str(row.get('pronunciation','')), 
                   str(row.get('englishmeaning','')), str(row.get('explanation','')), 0, ""))
    conn.commit()

# --- GEMINI REST API ---
def call_gemini(prompt, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
    return resp.json()['candidates'][0]['content']['parts'][0]['text']

# --- UI ---
def render_flashcard(conn, word_id, tab_key):
    # Fetch fresh data for this specific ID
    word_data = conn.cursor().execute("SELECT * FROM vocab WHERE id=?", (word_id,)).fetchone()
    id, chap, ar, pron, eng, expl, score, note = word_data
    
    st.markdown(f"**{chap}** | Score: {score}/3")
    
    c1, c2 = st.columns(2)
    if c1.button("👍 Got it", key=f"up_{id}", use_container_width=True):
        conn.cursor().execute("UPDATE vocab SET score=score+1 WHERE id=?", (id,))
        conn.commit()
        st.session_state.current_word = None
        st.rerun()
    if c2.button("👎 Practice", key=f"down_{id}", use_container_width=True):
        conn.cursor().execute("UPDATE vocab SET score=0 WHERE id=?", (id,))
        conn.commit()
        st.rerun()

    with st.container(border=True):
        st.markdown(f"<h1 style='text-align:right; font-size:40px;' dir='rtl'>{ar}</h1>", unsafe_allow_html=True)
        if st.button("🔊 Play", key=f"play_{id}"):
            st.audio(io.BytesIO(gTTS(ar, lang='ar').get_compressed_data()), format="audio/mp3")
        with st.expander(f"Meaning: {eng}"):
            st.write(f"Pronunciation: {pron}")
            st.write(f"Explanation: {expl}")

    # S.AI
    if f"note_{id}" not in st.session_state: st.session_state[f"note_{id}"] = note
    q = st.text_input("Ask S.AI:", key=f"q_{id}")
    if st.button("🤖 Ask", key=f"ask_{id}"):
        ans = call_gemini(f"Arabic word: {ar}. Question: {q}. 2 examples, no spaces.", GEMINI_API_KEY)
        st.session_state[f"note_{id}"] += "\n" + ans
        conn.cursor().execute("UPDATE vocab SET notes=? WHERE id=?", (st.session_state[f"note_{id}"], id))
        conn.commit()
        st.rerun()

    # Edit Notes
    if st.session_state.get(f"edit_{id}"):
        new = st.text_area("Edit", value=st.session_state[f"note_{id}"], key=f"text_{id}")
        if st.button("💾 Save", key=f"save_{id}"):
            conn.cursor().execute("UPDATE vocab SET notes=? WHERE id=?", (new, id))
            conn.commit()
            st.session_state[f"note_{id}"] = new
            st.session_state[f"edit_{id}"] = False
            st.rerun()
    else:
        st.info(st.session_state[f"note_{id}"] if st.session_state[f"note_{id}"] else "No notes.")
        if st.button("✏️ Edit", key=f"editbtn_{id}"):
            st.session_state[f"edit_{id}"] = True
            st.rerun()

# --- MAIN ---
conn = init_db()
sync_data(conn)
st.title("🇰🇼 Yalla Kuwaiti!")

tab1, tab2 = st.tabs(["🎮 Daily", "👑 Mastered"])
with tab1:
    words = conn.cursor().execute("SELECT id FROM vocab WHERE score < 3").fetchall()
    if words:
        if "current_word" not in st.session_state or st.session_state.current_word is None:
            st.session_state.current_word = random.choice(words)[0]
        render_flashcard(conn, st.session_state.current_word, "daily")
with tab2:
    for w in conn.cursor().execute("SELECT * FROM vocab WHERE score >= 3").fetchall():
        with st.expander(w[2]): render_flashcard(conn, w[0], "mastered")
conn.close()
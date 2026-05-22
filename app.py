import streamlit as st
import pandas as pd
import sqlite3
from gtts import gTTS
import io
import random
import hashlib

# --- Page Configuration ---
st.set_page_config(page_title="Kuwaiti Lingo", page_icon="🇰🇼", layout="centered")

# --- Database & Setup ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1DQ_74TZtMpbinusdnMOU2441hEFa7RRnaqeMx8qrBg0/export?format=csv"
DB_NAME = "learning_progress.db"

# Initialize SQLite Database to save scores permanently
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vocab 
                 (id TEXT PRIMARY KEY, level TEXT, chapter TEXT, arabic TEXT, 
                  pronunciation TEXT, english TEXT, explanation TEXT, example TEXT, score INTEGER)''')
    conn.commit()
    return conn

# Fetch new words from Google Sheets and add them to SQLite (without overwriting scores)
@st.cache_data(ttl=600)
def fetch_sheet_data(url):
    return pd.read_csv(url)

def sync_data(conn, df):
    c = conn.cursor()
    for _, row in df.iterrows():
        # Create a unique ID for the word based on the Arabic script
        word_id = hashlib.md5(str(row.get('Arabic Script', '')).encode()).hexdigest()
        
        # Check if word exists in DB
        c.execute("SELECT id FROM vocab WHERE id=?", (word_id,))
        if not c.fetchone():
            c.execute('''INSERT INTO vocab (id, level, chapter, arabic, pronunciation, english, explanation, example, score)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                      (word_id, str(row.get('Level', '')), str(row.get('Chapter', '')), 
                       str(row.get('Arabic Script', '')), str(row.get('Pronunciation', '')), 
                       str(row.get('English Meaning', '')), str(row.get('Explanation', '')), 
                       str(row.get('Example Sentence', '')), 0))
    conn.commit()

# --- Session State Management ---
if "show_meaning" not in st.session_state:
    st.session_state.show_meaning = False
if "current_word" not in st.session_state:
    st.session_state.current_word = None

def get_next_word(conn, level):
    c = conn.cursor()
    # Fetch words that haven't been mastered yet (score < 3)
    c.execute("SELECT * FROM vocab WHERE level=? AND score < 3", (level,))
    words = c.fetchall()
    
    if not words:
        # If all words mastered, reset or congratulate
        return None
    
    # Pick a random word from the unmastered list
    st.session_state.current_word = random.choice(words)
    st.session_state.show_meaning = False

def update_score(conn, word_id, is_correct):
    c = conn.cursor()
    if is_correct:
        c.execute("UPDATE vocab SET score = score + 1 WHERE id=?", (word_id,))
    else:
        # Thumbs down resets progress on this word
        c.execute("UPDATE vocab SET score = 0 WHERE id=?", (word_id,))
    conn.commit()

# --- App Layout ---
st.title("🇰🇼 Learn Kuwaiti Arabic")

# Initialize and sync databases
conn = init_db()
try:
    df = fetch_sheet_data(SHEET_URL)
    sync_data(conn, df)
except Exception as e:
    st.error(f"Error reading Google Sheet: {e}")

# Navigation
st.sidebar.header("Navigation")
# Get unique levels from DB
levels = [row[0] for row in conn.cursor().execute("SELECT DISTINCT level FROM vocab WHERE level != 'nan'").fetchall()]

if levels:
    selected_level = st.sidebar.selectbox("Choose your Level", levels)
    
    # Load first word if empty or level changed
    if "last_level" not in st.session_state or st.session_state.last_level != selected_level:
        st.session_state.last_level = selected_level
        get_next_word(conn, selected_level)

    # --- Flashcard UI ---
    word = st.session_state.current_word
    
    if word:
        # DB Columns: 0:id, 1:level, 2:chapter, 3:arabic, 4:pronunciation, 5:english, 6:explanation, 7:example, 8:score
        word_id, _, chapter, arabic, pronunc, english, expl, ex, score = word
        
        st.subheader(f"Chapter: {chapter}")
        st.caption(f"Mastery Score: {score}/3")
        
        # Word and Audio Container
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"<h1 style='text-align: right; font-size: 50px;' dir='rtl'>{arabic}</h1>", unsafe_allow_html=True)
            with col2:
                # Generate native audio instantly
                with st.spinner("🔊"):
                    tts = gTTS(text=str(arabic), lang='ar')
                    fp = io.BytesIO()
                    tts.write_to_fp(fp)
                    fp.seek(0)
                    st.audio(fp, format="audio/mp3")

            st.divider()
            
            # The Toggle Pronunciation Button
            if st.button(f"🗣️ Click to toggle meaning: **{pronunc}**", use_container_width=True):
                st.session_state.show_meaning = not st.session_state.show_meaning

            # The English Pop-up/Reveal
            if st.session_state.show_meaning:
                st.success(f"**Meaning:** {english}")
                if expl and expl != 'nan':
                    st.info(f"**Explanation:** {expl}")
                if ex and ex != 'nan':
                    st.warning(f"**Example:** {ex}")

        # Thumbs Up / Thumbs Down Controls
        st.write("How well did you know this?")
        b_col1, b_col2, b_col3 = st.columns([1, 1, 2])
        
        with b_col1:
            if st.button("👍 Got it", type="primary", use_container_width=True):
                update_score(conn, word_id, True)
                get_next_word(conn, selected_level)
                st.rerun()
                
        with b_col2:
            if st.button("👎 Need Practice", use_container_width=True):
                update_score(conn, word_id, False)
                get_next_word(conn, selected_level)
                st.rerun()

    else:
        st.balloons()
        st.success(f"🎉 You have mastered all the current words in {selected_level}!")
        if st.button("Reset my progress and practice again"):
            conn.cursor().execute("UPDATE vocab SET score = 0 WHERE level=?", (selected_level,))
            conn.commit()
            get_next_word(conn, selected_level)
            st.rerun()
else:
    st.info("Loading your vocabulary from Google Sheets...")

conn.close()
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
DB_NAME = "learning_progress_v3.db" # Updated to v3 for the new Chapter-based structure

# Initialize SQLite Database to save scores permanently
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vocab 
                 (id TEXT PRIMARY KEY, chapter TEXT, arabic TEXT, 
                  pronunciation TEXT, english TEXT, letter_pronunc TEXT, letter_eng TEXT, score INTEGER)''')
    conn.commit()
    return conn

# Fetch new words from Google Sheets
@st.cache_data(ttl=600)
def fetch_sheet_data(url):
    return pd.read_csv(url)

def sync_data(conn, df):
    c = conn.cursor()
    
    # Strip invisible whitespace from column names just in case
    df.columns = df.columns.str.strip()
    
    for _, row in df.iterrows():
        # Skip empty rows safely
        arabic_text = str(row.get('Arabic Script', ''))
        if not arabic_text or arabic_text == 'nan':
            continue
            
        # Create a unique ID for the word based on the Arabic script
        word_id = hashlib.md5(arabic_text.encode()).hexdigest()
        
        # Check if word exists in DB
        c.execute("SELECT id FROM vocab WHERE id=?", (word_id,))
        if not c.fetchone():
            c.execute('''INSERT INTO vocab (id, chapter, arabic, pronunciation, english, letter_pronunc, letter_eng, score)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                      (word_id, 
                       str(row.get('Chapter', '')), 
                       arabic_text, 
                       str(row.get('Pronunciation', '')), 
                       str(row.get('English Meaning', '')), 
                       str(row.get('Letter-wise pronounciation', '')), 
                       str(row.get('Letter-wise English', '')), 
                       0))
    conn.commit()

# --- Session State Management ---
if "show_meaning" not in st.session_state:
    st.session_state.show_meaning = False
if "current_word" not in st.session_state:
    st.session_state.current_word = None

def get_next_word(conn, chapter):
    c = conn.cursor()
    # Fetch words that haven't been mastered yet (score < 3)
    c.execute("SELECT * FROM vocab WHERE chapter=? AND score < 3", (chapter,))
    words = c.fetchall()
    
    if not words:
        return None
    
    st.session_state.current_word = random.choice(words)
    st.session_state.show_meaning = False

def update_score(conn, word_id, is_correct):
    c = conn.cursor()
    if is_correct:
        c.execute("UPDATE vocab SET score = score + 1 WHERE id=?", (word_id,))
    else:
        c.execute("UPDATE vocab SET score = 0 WHERE id=?", (word_id,))
    conn.commit()

# --- App Layout ---
st.title("🇰🇼 Learn Kuwaiti Arabic")

# Initialize and sync databases
conn = init_db()
try:
    df = fetch_sheet_data(SHEET_URL)
    # Strip whitespace from headers to ensure match
    df.columns = df.columns.str.strip()
    
    # Failsafe: Ensure 'Chapter' column exists
    if 'Chapter' not in df.columns:
        st.error("🚨 Critical Error: Could not find the 'Chapter' column in your Google Sheet.")
        st.write("Found these columns instead:", list(df.columns))
        st.stop()
        
    sync_data(conn, df)
except Exception as e:
    st.error(f"Error reading Google Sheet: {e}")

# Navigation (Now based on Chapters instead of Levels)
st.sidebar.header("Navigation")
chapters = [row[0] for row in conn.cursor().execute("SELECT DISTINCT chapter FROM vocab WHERE chapter != 'nan' AND chapter != ''").fetchall()]

if chapters:
    selected_chapter = st.sidebar.selectbox("Choose your Chapter", chapters)
    
    if "last_chapter" not in st.session_state or st.session_state.last_chapter != selected_chapter:
        st.session_state.last_chapter = selected_chapter
        get_next_word(conn, selected_chapter)

    # --- Flashcard UI ---
    word = st.session_state.current_word
    
    if word:
        # DB Columns: 0:id, 1:chapter, 2:arabic, 3:pronunciation, 4:english, 5:letter_pronunc, 6:letter_eng, 7:score
        word_id, chapter, arabic, pronunc, english, l_pronunc, l_eng, score = word
        
        st.subheader(f"Chapter: {chapter}")
        st.caption(f"Mastery Score: {score}/3")
        
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"<h1 style='text-align: right; font-size: 50px;' dir='rtl'>{arabic}</h1>", unsafe_allow_html=True)
            with col2:
                with st.spinner("🔊"):
                    tts = gTTS(text=str(arabic), lang='ar')
                    fp = io.BytesIO()
                    tts.write_to_fp(fp)
                    fp.seek(0)
                    st.audio(fp, format="audio/mp3")

            st.divider()
            
            if st.button(f"🗣️ Click to toggle meaning: **{pronunc}**", use_container_width=True):
                st.session_state.show_meaning = not st.session_state.show_meaning

            if st.session_state.show_meaning:
                st.success(f"**Meaning:** {english}")
                if l_pronunc and l_pronunc != 'nan':
                    st.info(f"**Letter-wise Pronunciation:** {l_pronunc}")
                if l_eng and l_eng != 'nan':
                    st.warning(f"**Letter-wise English:** {l_eng}")

        st.write("How well did you know this?")
        b_col1, b_col2, b_col3 = st.columns([1, 1, 2])
        
        with b_col1:
            if st.button("👍 Got it", type="primary", use_container_width=True):
                update_score(conn, word_id, True)
                get_next_word(conn, selected_chapter)
                st.rerun()
                
        with b_col2:
            if st.button("👎 Need Practice", use_container_width=True):
                update_score(conn, word_id, False)
                get_next_word(conn, selected_chapter)
                st.rerun()

    else:
        st.balloons()
        st.success(f"🎉 You have mastered all the current words in {selected_chapter}!")
        if st.button("Reset my progress and practice again"):
            conn.cursor().execute("UPDATE vocab SET score = 0 WHERE chapter=?", (selected_chapter,))
            conn.commit()
            get_next_word(conn, selected_chapter)
            st.rerun()
else:
    st.info("Loading your vocabulary from Google Sheets...")

conn.close()
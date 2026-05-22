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
DB_NAME = "learning_progress_v2.db" # Updated to v2 to prevent schema crashes

# Initialize SQLite Database to save scores permanently
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vocab 
                 (id TEXT PRIMARY KEY, level TEXT, chapter TEXT, arabic TEXT, 
                  pronunciation TEXT, english TEXT, letter_pronunc TEXT, letter_eng TEXT, score INTEGER)''')
    conn.commit()
    return conn

# Fetch new words from Google Sheets
@st.cache_data(ttl=600)
def fetch_sheet_data(url):
    return pd.read_csv(url)

def sync_data(conn, df):
    c = conn.cursor()
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
            c.execute('''INSERT INTO vocab (id, level, chapter, arabic, pronunciation, english, letter_pronunc, letter_eng, score)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                      (word_id, 
                       str(row.get('Level', '')), 
                       str(row.get('Chapter', '')), 
                       arabic_text, 
                       str(row.get('Pronunciation', '')), 
                       str(row.get('English Meaning', '')), 
                       str(row.get('letterwise pronounciation', '')), 
                       str(row.get('letterwise english', '')), 
                       0))
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
    
    # Failsafe: Ensure 'Level' column exists to prevent KeyError
    if 'Level' not in df.columns:
        st.error("🚨 Critical Error: Could not find the 'Level' column in your Google Sheet. Please check your spelling and spacing in Row 1.")
        st.stop()
        
    sync_data(conn, df)
except Exception as e:
    st.error(f"Error reading Google Sheet: {e}")

# Navigation
st.sidebar.header("Navigation")
levels = [row[0] for row in conn.cursor().execute("SELECT DISTINCT level FROM vocab WHERE level != 'nan' AND level != ''").fetchall()]

if levels:
    selected_level = st.sidebar.selectbox("Choose your Level", levels)
    
    if "last_level" not in st.session_state or st.session_state.last_level != selected_level:
        st.session_state.last_level = selected_level
        get_next_word(conn, selected_level)

    # --- Flashcard UI ---
    word = st.session_state.current_word
    
    if word:
        # DB Columns: 0:id, 1:level, 2:chapter, 3:arabic, 4:pronunciation, 5:english, 6:letter_pronunc, 7:letter_eng, 8:score
        word_id, _, chapter, arabic, pronunc, english, l_pronunc, l_eng, score = word
        
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
                # Display the new letter-wise data if it exists
                if l_pronunc and l_pronunc != 'nan':
                    st.info(f"**Letter-wise Pronunciation:** {l_pronunc}")
                if l_eng and l_eng != 'nan':
                    st.warning(f"**Letter-wise English:** {l_eng}")

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
    st.info("Loading your vocabulary from Google Sheets... Make sure your sheet has a column exactly named 'Level'.")

conn.close()
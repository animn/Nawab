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
DB_NAME = "learning_progress_v5.db" # Updated to v5 for Regex column cleaning

# Initialize SQLite Database to save scores permanently
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vocab 
                 (id TEXT PRIMARY KEY, chapter TEXT, arabic TEXT, 
                  pronunciation TEXT, english TEXT, explanation TEXT, letter_pronunc TEXT, letter_eng TEXT, score INTEGER)''')
    conn.commit()
    return conn

# Fetch new words from Google Sheets
@st.cache_data(ttl=600)
def fetch_sheet_data(url):
    return pd.read_csv(url)

def sync_data(conn, df):
    c = conn.cursor()
    
    # THE ULTIMATE FIX: This removes ALL spaces, hyphens, and invisible Apple/iPad characters
    # "English Meaning" safely becomes "englishmeaning"
    df.columns = df.columns.str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.lower()
    
    for _, row in df.iterrows():
        arabic_text = str(row.get('arabicscript', ''))
        if not arabic_text or arabic_text == 'nan':
            continue
            
        word_id = hashlib.md5(arabic_text.encode()).hexdigest()
        
        # Checking both spellings just in case
        letter_pronunc = str(row.get('letterwisepronounciation', row.get('letterwisepronunciation', '')))
        
        # Check if word exists in DB
        c.execute("SELECT id FROM vocab WHERE id=?", (word_id,))
        if not c.fetchone():
            c.execute('''INSERT INTO vocab (id, chapter, arabic, pronunciation, english, explanation, letter_pronunc, letter_eng, score)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                      (word_id, 
                       str(row.get('chapter', '')), 
                       arabic_text, 
                       str(row.get('pronunciation', '')), 
                       str(row.get('englishmeaning', '')), 
                       str(row.get('explanation', '')),
                       letter_pronunc, 
                       str(row.get('letterwiseenglish', '')), 
                       0))
    conn.commit()

# --- Session State Management ---
if "show_meaning" not in st.session_state:
    st.session_state.show_meaning = False
if "current_word" not in st.session_state:
    st.session_state.current_word = None

def get_next_word(conn, chapter):
    c = conn.cursor()
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
    # Apply the same Regex fix for the failsafe checker
    df.columns = df.columns.str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.lower()
    
    if 'chapter' not in df.columns:
        st.error("🚨 Critical Error: Could not find the 'Chapter' column in your Google Sheet.")
        st.write("Found these columns instead:", list(df.columns))
        st.stop()
        
    sync_data(conn, df)
except Exception as e:
    st.error(f"Error reading Google Sheet: {e}")

# Navigation
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
        # DB Columns: 0:id, 1:chapter, 2:arabic, 3:pronunciation, 4:english, 5:explanation, 6:letter_pronunc, 7:letter_eng, 8:score
        word_id, chapter, arabic, pronunc, english, expl, l_pronunc, l_eng, score = word
        
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
            
            # Toggle Button
            if st.button(f"🗣️ Click to toggle meaning: **{pronunc}**", use_container_width=True):
                st.session_state.show_meaning = not st.session_state.show_meaning

            # The English Meaning & Collapsible Breakdown (Only shows if toggled ON)
            if st.session_state.show_meaning:
                # Show standard meaning
                if english and english != 'nan' and english != '':
                    st.success(f"**Meaning:** {english}")
                    
                # Show explanation if you ever use that column
                if expl and expl != 'nan' and expl != '':
                    st.info(f"**Explanation:** {expl}")
                
                # Show Letter-wise breakdown in a neat, clickable expander
                if (l_pronunc and l_pronunc != 'nan' and l_pronunc != '') or (l_eng and l_eng != 'nan' and l_eng != ''):
                    with st.expander("🔍 Letter-wise Breakdown"):
                        if l_pronunc and l_pronunc != 'nan' and l_pronunc != '':
                            st.write(f"**Pronunciation:** {l_pronunc}")
                        if l_eng and l_eng != 'nan' and l_eng != '':
                            st.write(f"**English:** {l_eng}")

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
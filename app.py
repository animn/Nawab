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

# Securely load the API key from Streamlit Secrets
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    GEMINI_API_KEY = None

SHEET_URL = "https://docs.google.com/spreadsheets/d/1DQ_74TZtMpbinusdnMOU2441hEFa7RRnaqeMx8qrBg0/export?format=csv"
DB_NAME = "learning_progress_v6.db"

# --- Database & Setup ---
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
        arabic_text = str(row.get('arabicscript', ''))
        if not arabic_text or arabic_text == 'nan':
            continue
            
        word_id = hashlib.md5(arabic_text.encode()).hexdigest()
        letter_pronunc = str(row.get('letterwisepronounciation', row.get('letterwisepronunciation', '')))
        
        c.execute("SELECT id FROM vocab WHERE id=?", (word_id,))
        if not c.fetchone():
            c.execute('''INSERT INTO vocab (id, chapter, arabic, pronunciation, english, 
                                            explanation, letter_pronunc, letter_eng, score, notes)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                      (word_id, str(row.get('chapter', '')), arabic_text, 
                       str(row.get('pronunciation', '')), str(row.get('englishmeaning', '')), 
                       str(row.get('explanation', '')), letter_pronunc, 
                       str(row.get('letterwiseenglish', '')), 0, ""))
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
    
    if "ai_draft_note" in st.session_state:
        del st.session_state["ai_draft_note"]

def update_score(conn, word_id, is_correct):
    c = conn.cursor()
    if is_correct:
        c.execute("UPDATE vocab SET score = score + 1 WHERE id=?", (word_id,))
    else:
        c.execute("UPDATE vocab SET score = 0 WHERE id=?", (word_id,))
    conn.commit()

# --- App Layout ---
st.title("🇰🇼 Yalla Kuwaiti!")

conn = init_db()
try:
    df = fetch_sheet_data(SHEET_URL)
    df.columns = df.columns.str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.lower()
    if 'chapter' not in df.columns:
        st.error("🚨 Critical Error: Could not find the 'Chapter' column.")
        st.stop()
    sync_data(conn, df)
except Exception as e:
    st.error(f"Error reading Google Sheet: {e}")

st.sidebar.header("Navigation")
chapters = [row[0] for row in conn.cursor().execute("SELECT DISTINCT chapter FROM vocab WHERE chapter != 'nan' AND chapter != ''").fetchall()]

if chapters:
    selected_chapter = st.sidebar.selectbox("Choose your Chapter", chapters)
    
    if "last_chapter" not in st.session_state or st.session_state.last_chapter != selected_chapter:
        st.session_state.last_chapter = selected_chapter
        get_next_word(conn, selected_chapter)

    word = st.session_state.current_word
    
    if word:
        word_id, chapter, arabic, pronunc, english, expl, l_pronunc, l_eng, score, saved_note = word
        
        top_col1, top_col2, top_col3 = st.columns([5, 1, 1])
        with top_col1:
            st.subheader(f"{chapter}")
            st.caption(f"Mastery: {score}/3")
        with top_col2:
            if st.button("👍", use_container_width=True, key="got_it"):
                update_score(conn, word_id, True)
                get_next_word(conn, selected_chapter)
                st.rerun()
        with top_col3:
            if st.button("👎", use_container_width=True, key="need_prac"):
                update_score(conn, word_id, False)
                get_next_word(conn, selected_chapter)
                st.rerun()
        
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
                if english and english != 'nan' and english != '':
                    st.success(f"**Meaning:** {english}")
                if expl and expl != 'nan' and expl != '':
                    st.info(f"**Explanation:** {expl}")
                
                if (l_pronunc and l_pronunc != 'nan' and l_pronunc != '') or (l_eng and l_eng != 'nan' and l_eng != ''):
                    with st.expander("🔍 Letter-wise Breakdown"):
                        if l_pronunc and l_pronunc != 'nan' and l_pronunc != '':
                            st.write(f"**Pronunciation:** {l_pronunc}")
                        if l_eng and l_eng != 'nan' and l_eng != '':
                            st.write(f"**English:** {l_eng}")

        st.markdown("### 📝 My Notes & AI Tutor")
        
        display_note = st.session_state.get("ai_draft_note", saved_note)
        if display_note == 'nan' or display_note is None:
            display_note = ""

        ai_col1, ai_col2 = st.columns([4, 1])
        with ai_col1:
            user_question = st.text_input("Ask a quick question about this word:", placeholder="e.g. How do I use this in a sentence?")
        with ai_col2:
            st.write("") 
            if st.button("Ask AI", use_container_width=True):
                if not GEMINI_API_KEY:
                    st.error("API Key not found in Streamlit Secrets!")
                elif user_question:
                    with st.spinner("Thinking..."):
                        try:
                            genai.configure(api_key=GEMINI_API_KEY)
                            model = genai.GenerativeModel('gemini-1.5-flash')
                            prompt = f"The user is learning the Kuwaiti Arabic word '{arabic}' ({english}). They asked: '{user_question}'. Provide an extremely brief answer (maximum 2 to 3 sentences)."
                            response = model.generate_content(prompt)
                            
                            new_draft = display_note + f"\n\nQ: {user_question}\nAI: {response.text.strip()}" if display_note else f"Q: {user_question}\nAI: {response.text.strip()}"
                            st.session_state["ai_draft_note"] = new_draft
                            st.rerun()
                        except Exception as e:
                            st.error(f"API Error: {e}")

        final_note = st.text_area("Edit your notes here:", value=display_note, height=100)
        
        if st.button("💾 Save Note"):
            c = conn.cursor()
            c.execute("UPDATE vocab SET notes=? WHERE id=?", (final_note, word_id))
            conn.commit()
            if "ai_draft_note" in st.session_state:
                del st.session_state["ai_draft_note"]
            
            c.execute("SELECT * FROM vocab WHERE id=?", (word_id,))
            st.session_state.current_word = c.fetchone()
            st.success("Note saved permanently!")
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
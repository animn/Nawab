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
DB_NAME = "learning_progress_v7.db" 

# --- 1. DATABASE MODULE ---
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
        if not arabic_text or arabic_text == 'nan': continue
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

def update_score(conn, word_id, is_correct):
    c = conn.cursor()
    if is_correct:
        c.execute("UPDATE vocab SET score = score + 1 WHERE id=?", (word_id,))
    else:
        c.execute("UPDATE vocab SET score = 0 WHERE id=?", (word_id,))
    conn.commit()

def get_stats(conn):
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM vocab").fetchone()[0]
    mastered = c.execute("SELECT COUNT(*) FROM vocab WHERE score >= 3").fetchone()[0]
    practice = c.execute("SELECT COUNT(*) FROM vocab WHERE score = 0").fetchone()[0]
    learning = total - mastered - practice
    return total, mastered, learning, practice

# --- 2. UI COMPONENT MODULE (The Master Blueprint) ---
def render_flashcard(conn, word_data, tab_key):
    """This function stamps out the exact same flashcard design everywhere."""
    word_id, chapter, arabic, pronunc, english, expl, l_pronunc, l_eng, score, saved_note = word_data
    
    # Inline Compact Header
    c1, c2, c3, c4 = st.columns([5, 2, 1, 1])
    c1.markdown(f"**{chapter}**")
    c2.caption(f"Score: {score}/3")
    if c3.button("👍", key=f"up_{word_id}_{tab_key}", help="Got it!"):
        update_score(conn, word_id, True)
        if tab_key == "home": st.session_state.current_word = None
        st.rerun()
    if c4.button("👎", key=f"down_{word_id}_{tab_key}", help="Needs Practice"):
        update_score(conn, word_id, False)
        if tab_key == "home": st.session_state.current_word = None
        st.rerun()

    # Flashcard Body
    with st.container(border=True):
        f_col1, f_col2 = st.columns([3, 1])
        with f_col1:
            st.markdown(f"<h1 style='text-align: right; font-size: 40px;' dir='rtl'>{arabic}</h1>", unsafe_allow_html=True)
        with f_col2:
            # Generate Audio ONLY when clicked to save speed in large lists
            if st.button("🔊 Play", key=f"audio_{word_id}_{tab_key}"):
                with st.spinner(".."):
                    tts = gTTS(text=str(arabic), lang='ar')
                    fp = io.BytesIO()
                    tts.write_to_fp(fp)
                    fp.seek(0)
                    st.audio(fp, format="audio/mp3")

        st.divider()
        
        # Toggle Meaning
        toggle_key = f"toggle_{word_id}_{tab_key}"
        if toggle_key not in st.session_state: st.session_state[toggle_key] = False
        
        if st.button(f"🗣️ Toggle Meaning: **{pronunc}**", key=f"btn_{word_id}_{tab_key}", use_container_width=True):
            st.session_state[toggle_key] = not st.session_state[toggle_key]

        if st.session_state[toggle_key]:
            if english and english != 'nan': st.success(f"**Meaning:** {english}")
            if expl and expl != 'nan': st.info(f"**Explanation:** {expl}")
            
            if (l_pronunc and l_pronunc != 'nan') or (l_eng and l_eng != 'nan'):
                with st.expander("🔍 Letter-wise Breakdown"):
                    if l_pronunc and l_pronunc != 'nan': st.write(f"**Pronunciation:** {l_pronunc}")
                    if l_eng and l_eng != 'nan': st.write(f"**English:** {l_eng}")

    # Compact AI & Notes Bar
    note_key = f"note_{word_id}_{tab_key}"
    if note_key not in st.session_state: st.session_state[note_key] = saved_note if saved_note != 'nan' else ""
    
    ai_c1, ai_c2, ai_c3 = st.columns([4, 1, 1])
    question = ai_c1.text_input("Ask AI...", key=f"q_{word_id}_{tab_key}", label_visibility="collapsed", placeholder="Ask AI a quick question...")
    
    if ai_c2.button("🤖 AI", key=f"ask_{word_id}_{tab_key}", use_container_width=True):
        if not GEMINI_API_KEY: st.error("Add valid API Key!")
        elif question:
            with st.spinner("..."):
                try:
                    genai.configure(api_key=GEMINI_API_KEY)
                    response = genai.GenerativeModel('gemini-1.5-flash').generate_content(
                        f"Word: {arabic} ({english}). Question: {question}. Keep answer strictly to 2 short sentences."
                    )
                    st.session_state[note_key] += f"\nQ: {question}\nAI: {response.text.strip()}\n"
                    conn.cursor().execute("UPDATE vocab SET notes=? WHERE id=?", (st.session_state[note_key], word_id))
                    conn.commit()
                except Exception as e: st.error(f"API Error: Check key.")

    if ai_c3.button("✏️ Edit", key=f"edit_{word_id}_{tab_key}", use_container_width=True):
        st.session_state[f"edit_mode_{word_id}"] = not st.session_state.get(f"edit_mode_{word_id}", False)

    # Note Display / Edit Box
    if st.session_state.get(f"edit_mode_{word_id}", False):
        new_note = st.text_area("Edit Note", value=st.session_state[note_key], key=f"text_{word_id}_{tab_key}")
        if st.button("💾 Save Edits", key=f"save_{word_id}_{tab_key}"):
            conn.cursor().execute("UPDATE vocab SET notes=? WHERE id=?", (new_note, word_id))
            conn.commit()
            st.session_state[note_key] = new_note
            st.session_state[f"edit_mode_{word_id}"] = False
            st.rerun()
    elif st.session_state[note_key]:
        st.caption("📝 " + st.session_state[note_key].replace("\n", " | "))

# --- 3. MAIN APP ROUTING ---
st.markdown("## 🇰🇼 Yalla Kuwaiti!")

# Init Database & Fetch Data
conn = init_db()
try:
    df = fetch_sheet_data(SHEET_URL)
    df.columns = df.columns.str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.lower()
    sync_data(conn, df)
except Exception as e: st.error(f"Sheet Error: {e}")

# Navigation Sidebar
st.sidebar.header("Filter")
chapters = [row[0] for row in conn.cursor().execute("SELECT DISTINCT chapter FROM vocab WHERE chapter != 'nan' AND chapter != ''").fetchall()]
selected_chapter = st.sidebar.selectbox("Choose Chapter", ["All Chapters"] + chapters)

# --- Gamification Dashboard ---
total, mastered, learning, practice = get_stats(conn)
st.sidebar.divider()
st.sidebar.markdown("### 🏆 Progress")
m1, m2 = st.sidebar.columns(2)
m1.metric("Mastered", mastered)
m2.metric("Needs Practice", practice)
st.sidebar.progress(mastered / total if total > 0 else 0, text=f"Overall Fluency: {int((mastered/total)*100) if total else 0}%")

# Main Tabs
tab1, tab2, tab3 = st.tabs(["🎮 Daily Practice", "🏋️ Needs Practice", "👑 Mastered List"])

# Base SQL Query for selected chapter
base_query = "SELECT * FROM vocab"
params = []
if selected_chapter != "All Chapters":
    base_query += " WHERE chapter = ?"
    params.append(selected_chapter)

with tab1:
    # Fetch random unmastered word for the Home screen
    q1 = base_query + (" AND score < 3" if "WHERE" in base_query else " WHERE score < 3")
    words = conn.cursor().execute(q1, params).fetchall()
    
    if words:
        if "current_word" not in st.session_state or st.session_state.current_word is None:
            st.session_state.current_word = random.choice(words)
        render_flashcard(conn, st.session_state.current_word, tab_key="home")
    else:
        st.success("🎉 You've mastered all words in this section! Check the Mastered Tab.")

with tab2:
    st.markdown("### Focus on these words:")
    q2 = base_query + (" AND score = 0" if "WHERE" in base_query else " WHERE score = 0")
    bad_words = conn.cursor().execute(q2, params).fetchall()
    for w in bad_words:
        # Use expanders to keep the list clean and scrollable
        with st.expander(f"🔴 {w[2]} ({w[4]})"):
            render_flashcard(conn, w, tab_key="practice")

with tab3:
    st.markdown("### Words you know perfectly:")
    q3 = base_query + (" AND score >= 3" if "WHERE" in base_query else " WHERE score >= 3")
    good_words = conn.cursor().execute(q3, params).fetchall()
    for w in good_words:
        with st.expander(f"👑 {w[2]} ({w[4]})"):
            render_flashcard(conn, w, tab_key="mastered")

conn.close()
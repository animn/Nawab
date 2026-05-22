import streamlit as st
import json
import random
import io
from gtts import gTTS

try:
    from google import genai
    from google.genai import types
except ImportError:
    st.error("Missing libraries. Please run: pip install streamlit google-genai gTTS")
    st.stop()

# --- 1. PAGE CONFIG & MOBILE STYLING ---
st.set_page_config(page_title="Kanfani Kuwaiti", page_icon="🇰🇼", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
<style>
.main .block-container { max-width: 450px !important; padding-top: 2rem !important; margin: 0 auto !important; }
.stApp { background-color: #0f172a; color: #f8fafc; }
div[data-testid="stButton"] > button { border-radius: 12px; height: 50px; font-weight: 600; background: rgba(255, 255, 255, 0.05); color: #f8fafc; border: 1px solid rgba(255, 255, 255, 0.2); }
div[data-testid="stButton"] > button:active { background: #3b82f6; }
.stSuccess { background: rgba(34, 197, 94, 0.1) !important; border: 1px solid #22c55e !important; color: #f8fafc !important; }
.stError { background: rgba(239, 68, 68, 0.1) !important; border: 1px solid #ef4444 !important; color: #f8fafc !important; }
</style>
""", unsafe_allow_html=True)

# --- 2. STATE MANAGEMENT ---
for key in ['streak', 'points', 'lesson_progress']:
    if key not in st.session_state: st.session_state[key] = 0
if 'mistake_bank' not in st.session_state: st.session_state.mistake_bank = []
if 'current_q' not in st.session_state: st.session_state.current_q = None
if 'feedback' not in st.session_state: st.session_state.feedback = None
if 'voice_feedback' not in st.session_state: st.session_state.voice_feedback = None
if 'more_examples' not in st.session_state: st.session_state.more_examples = None

# --- 3. HELPER FUNCTIONS & GEMINI ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=GEMINI_API_KEY)
except:
    client = None
    GEMINI_API_KEY = None

SYSTEM_PROMPT = """
You are Kanfani, a gamified Kuwaiti Arabic AI coach. Output EXCLUSIVELY in JSON format.

Modes:
1. `generate`: Create a multiple choice question relevant to living in Kuwait.
{"question": "English phrase", "options": ["opt1", "opt2", "opt3", "opt4"], "correct_answer": "Exact match", "phonetic": "English transliteration of correct answer", "explanation": "Grammar/vocab rule"}

2. `evaluate_audio`: Listen to the user's audio and evaluate their pronunciation of the target phrase.
{"feedback": "Short, friendly critique of their pronunciation or accent based on Kuwaiti dialect."}

3. `generate_examples`: Generate 2 more examples using the target vocabulary.
{"examples": [{"kuwaiti": "Arabic text", "phonetic": "Transliteration", "english": "English meaning"}]}
"""

def fetch_new_question():
    if not client: return None
    with st.spinner("Loading next challenge..."):
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Mode: generate",
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, response_mime_type="application/json")
        )
        data = json.loads(resp.text)
        random.shuffle(data["options"])
        return data

def generate_audio(text):
    """Converts Arabic text to MP3 bytes."""
    try:
        tts = gTTS(text=text, lang='ar', slow=False)
        audio_stream = io.BytesIO()
        tts.write_to_fp(audio_stream)
        audio_stream.seek(0)
        return audio_stream
    except:
        return None

# --- 4. APP LAYOUT ---
st.markdown("<h2 style='text-align: center;'>🇰🇼 Kanfani</h2>", unsafe_allow_html=True)
tab_learn, tab_review, tab_dash = st.tabs(["📚 Learn", "🔄 Mistakes", "📊 Dash"])

with tab_learn:
    if not GEMINI_API_KEY:
        st.warning("Please configure `GEMINI_API_KEY` in Streamlit secrets.")
    else:
        if st.session_state.current_q is None:
            st.session_state.current_q = fetch_new_question()
            st.rerun()
            
        q = st.session_state.current_q
        
        # --- A. QUESTION STATE ---
        if not st.session_state.feedback:
            st.write("Translate this phrase:")
            st.subheader(q.get("question", ""))
            
            for idx, opt in enumerate(q.get("options", [])):
                if st.button(opt, key=f"opt_{idx}"):
                    if opt == q.get("correct_answer"):
                        st.session_state.points += 15
                        st.session_state.streak += 1
                        st.session_state.lesson_progress += 10
                        st.session_state.feedback = {"correct": True, "msg": f"**ممتاز!**\n\n{q.get('explanation')}"}
                    else:
                        st.session_state.streak = 0
                        if q not in st.session_state.mistake_bank: st.session_state.mistake_bank.append(q)
                        st.session_state.feedback = {"correct": False, "msg": f"The correct answer is **{q.get('correct_answer')}**.\n\n*Rule:* {q.get('explanation')}"}
                    st.rerun()
        
        # --- B. FEEDBACK STATE (WITH NEW AUDIO FEATURES) ---
        else:
            if st.session_state.feedback["correct"]: st.success(st.session_state.feedback["msg"])
            else: st.error(st.session_state.feedback["msg"])
                
            st.markdown(f"🗣️ **Phonetic:** *{q.get('phonetic', '')}*")
            
            # 1. Listen to phrase
            audio_bytes = generate_audio(q.get("correct_answer"))
            if audio_bytes: st.audio(audio_bytes, format="audio/mp3")

            st.write("---")
            
            # 2. Voice Validation
            st.write("**🎙️ Test your pronunciation:**")
            user_audio = st.audio_input("Record yourself")
            
            if user_audio:
                if st.button("Check Accent"):
                    with st.spinner("AI is listening..."):
                        resp = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=[
                                f"Mode: evaluate_audio. The user is trying to say: {q.get('correct_answer')}",
                                types.Part.from_bytes(data=user_audio.read(), mime_type='audio/wav')
                            ],
                            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, response_mime_type="application/json")
                        )
                        st.session_state.voice_feedback = json.loads(resp.text).get("feedback")
            
            if st.session_state.voice_feedback:
                st.info(f"🤖 **Coach:** {st.session_state.voice_feedback}")

            st.write("---")

            # 3. Generate More Examples
            if st.button("Give me 2 more examples"):
                with st.spinner("Generating examples..."):
                    resp = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=f"Mode: generate_examples. Target concept: {q.get('correct_answer')}",
                        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, response_mime_type="application/json")
                    )
                    st.session_state.more_examples = json.loads(resp.text).get("examples", [])
                    
            if st.session_state.more_examples:
                st.write("**Extra Practice:**")
                for ex in st.session_state.more_examples:
                    with st.container(border=True):
                        st.markdown(f"**{ex.get('kuwaiti')}** (*{ex.get('phonetic')}*)")
                        st.caption(ex.get('english'))
                        ex_audio = generate_audio(ex.get('kuwaiti'))
                        if ex_audio: st.audio(ex_audio, format="audio/mp3")

            st.write("")
            # Continue Button
            if st.button("Next Question ➡️", type="primary"):
                st.session_state.current_q = None
                st.session_state.feedback = None
                st.session_state.voice_feedback = None
                st.session_state.more_examples = None
                st.rerun()

# --- TAB 2 & 3: REVIEW & DASHBOARD ---
with tab_review:
    st.subheader("Your Mistake Bank")
    for mistake in reversed(st.session_state.mistake_bank):
        with st.expander(f"{mistake.get('question')}"):
            st.markdown(f"**Answer:** {mistake.get('correct_answer')} (*{mistake.get('phonetic')}*)")
    if st.button("Clear Mistake Bank"):
        st.session_state.mistake_bank = []
        st.rerun()

with tab_dash:
    col1, col2 = st.columns(2)
    col1.metric("🔥 Streak", f"{st.session_state.streak}")
    col2.metric("⭐ XP", st.session_state.points)
    st.progress((st.session_state.lesson_progress % 100) / 100.0)
    st.caption(f"Level {(st.session_state.lesson_progress // 100) + 1}")

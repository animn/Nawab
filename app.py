import streamlit as st
import pandas as pd
import sqlite3
from gtts import gTTS
import io
import random
import hashlib
import requests
import json
import re
import html

# --- Configuration & Keys ---
st.set_page_config(
    page_title="Yalla Kuwaiti!",
    page_icon="🇰🇼",
    layout="centered"
)

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    GEMINI_API_KEY = None

SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1DQ_74TZtMpbinusdnMOU2441hEFa7RRnaqeMx8qrBg0/"
    "export?format=csv"
)

DB_NAME = "learning_progress_v8.db"


# =========================================================
# SECRETS
# =========================================================

def get_secret_value(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


# Google Sheet write-back
SHEET_APPEND_WEBHOOK_URL = get_secret_value(
    "SHEET_APPEND_WEBHOOK_URL"
)
SHEET_APPEND_SECRET = get_secret_value(
    "SHEET_APPEND_SECRET",
    ""
)

# Azure Kuwait Arabic Text-to-Speech
AZURE_SPEECH_KEY = get_secret_value(
    "AZURE_SPEECH_KEY",
    ""
)

AZURE_SPEECH_REGION = get_secret_value(
    "AZURE_SPEECH_REGION",
    ""
)

AZURE_SPEECH_VOICE = get_secret_value(
    "AZURE_SPEECH_VOICE",
    "ar-KW-FahedNeural"
)


# =========================================================
# INBOX FIELDS
# =========================================================

INBOX_JSON_KEYS = [
    "chapter",
    "arabicscript",
    "pronunciation",
    "ttstext",
    "englishmeaning",
    "explanation",
    "letterwisepronounciation",
    "letterwiseenglish",
]


# =========================================================
# KUWAITI DIALECT GUARDRAILS
# =========================================================

KUWAITI_DIALECT_GUARDRAILS = """
You are an expert in natural spoken Kuwaiti Arabic.

Rules:
- Generate and explain Kuwaiti spoken Arabic, not Modern Standard Arabic,
  unless formal Arabic is genuinely required.
- Prefer what a Kuwaiti person would actually say in normal daily conversation.
- Always check whether a Kuwaiti/Gulf verb changes meaning depending on
  whether its object is physical or abstract.
- Important example: بطل can mean "open" with a physical object/body part,
  but "stop/quit" with an action or habit.
- If a phrase involves a body part, door, bag, phone, eye, mouth, container,
  or another physical object, first test the literal physical meaning
  of the verb.
- If a phrase involves an action, habit, behaviour, or activity,
  test meanings such as stop, quit, start, or continue.
- Never invent a metaphorical idiom merely because a literal translation
  sounds unusual.
- Cross-check the final English meaning against realistic native
  Kuwaiti/Gulf usage.
- Do not hallucinate slang, fake idioms, or cultural explanations.
- If usage is Gulf-common rather than specifically Kuwaiti,
  say so briefly.
- If uncertain about a dialect expression, state the uncertainty
  instead of confidently inventing a meaning.
- Keep answers practical for a learner who wants real everyday
  Kuwaiti Arabic.
"""


# =========================================================
# CSS
# =========================================================

st.markdown(
    """
    <style>

        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 1rem !important;
            max-width: 600px;
        }

        audio {
            height: 45px !important;
            width: 100% !important;
            margin-bottom: 0 !important;
        }

        .arabic-word {
            text-align: right;
            font-size: 42px;
            margin: 0 0 0.5rem 0;
            line-height: 1.2;
        }

        .note-preview {
            font-size: 0.9rem;
            color: #ddd;
            border: 1px solid #555;
            border-radius: 5px;
            padding: 10px;
            min-height: 80px;
            max-height: 150px;
            overflow-y: auto;
            white-space: pre-wrap;
        }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def clean_val(val):

    if val is None:
        return ""

    # Gemini occasionally returns arrays
    if isinstance(val, (list, tuple, set)):
        parts = []

        for item in val:
            item_text = clean_val(item)

            if item_text:
                parts.append(item_text)

        return " | ".join(parts)

    # Gemini occasionally returns nested objects
    if isinstance(val, dict):
        parts = []

        for k, v in val.items():
            k_text = clean_val(k)
            v_text = clean_val(v)

            if k_text and v_text:
                parts.append(
                    f"{k_text}: {v_text}"
                )

            elif v_text:
                parts.append(v_text)

        return " | ".join(parts)

    # pandas duplicate column / Series protection
    if isinstance(val, pd.Series):

        parts = []

        for item in val.tolist():

            item_text = clean_val(item)

            if item_text:
                parts.append(item_text)

        return " | ".join(parts)

    try:

        if pd.isna(val):
            return ""

    except Exception:
        pass

    text = str(val).strip()

    if text.lower() in [
        "nan",
        "none",
        "null"
    ]:
        return ""

    return text


# =========================================================
# gTTS FALLBACK
# =========================================================

@st.cache_data(show_spinner=False)
def get_audio_bytes(text):

    """
    Generic Arabic gTTS fallback.

    Used mainly for:
    - old existing words
    - Azure failures
    - words without saved Azure audio

    TTSText should be supplied whenever available.
    """

    text = clean_val(text)

    if not text:
        return None

    try:

        tts = gTTS(
            text=text,
            lang="ar"
        )

        fp = io.BytesIO()

        tts.write_to_fp(fp)

        return fp.getvalue()

    except Exception:

        return None


# =========================================================
# AZURE KUWAIT TTS
# =========================================================

def azure_tts_is_configured():

    return bool(
        clean_val(AZURE_SPEECH_KEY)
        and clean_val(AZURE_SPEECH_REGION)
    )


def get_azure_tts_audio_bytes(
    text,
    voice=None
):

    """
    Generate Kuwait Arabic MP3 using Azure Speech REST API.

    Uses REST instead of Azure SDK to keep Streamlit deployment light.
    """

    text = clean_val(text)

    if not text:

        raise ValueError(
            "TTS text is empty."
        )

    if not azure_tts_is_configured():

        raise ValueError(
            "Azure Speech is not configured. "
            "Add AZURE_SPEECH_KEY and "
            "AZURE_SPEECH_REGION in Streamlit Secrets."
        )

    region = clean_val(
        AZURE_SPEECH_REGION
    )

    selected_voice = (
        clean_val(voice)
        or clean_val(AZURE_SPEECH_VOICE)
        or "ar-KW-FahedNeural"
    )

    endpoint = (
        f"https://{region}."
        f"tts.speech.microsoft.com/"
        f"cognitiveservices/v1"
    )

    escaped_text = html.escape(
        text,
        quote=False
    )

    # IMPORTANT:
    # Azure SSML namespace included here.
    ssml = f"""
<speak version='1.0'
       xmlns='http://www.w3.org/2001/10/synthesis'
       xml:lang='ar-KW'>
  <voice name='{selected_voice}'>{escaped_text}</voice>
</speak>
""".strip()

    headers = {

        "Ocp-Apim-Subscription-Key":
            clean_val(AZURE_SPEECH_KEY),

        "Content-Type":
            "application/ssml+xml",

        "X-Microsoft-OutputFormat":
            "audio-16khz-128kbitrate-mono-mp3",

        "User-Agent":
            "YallaKuwaitiStreamlit",
    }

    resp = requests.post(
        endpoint,
        headers=headers,
        data=ssml.encode("utf-8"),
        timeout=45,
    )

    if resp.status_code != 200:

        details = (
            clean_val(resp.text)
            or clean_val(resp.reason)
            or "No error body returned by Azure."
        )

        raise Exception(
            f"Azure TTS failed "
            f"(region={region}, "
            f"voice={selected_voice}). "
            f"HTTP {resp.status_code}: "
            f"{details[:400]}"
        )

    if not resp.content:

        raise Exception(
            "Azure TTS returned HTTP 200 "
            "but no audio bytes "
            f"(region={region}, "
            f"voice={selected_voice})."
        )

    return resp.content


def generate_approved_word_audio(
    tts_text,
    arabic_text
):

    """
    Generate Azure audio once when approving
    a new Inbox word.

    Returns:
        audio_bytes
        provider
        message
    """

    source_text = (
        clean_val(tts_text)
        or clean_val(arabic_text)
    )

    if not source_text:

        return (
            None,
            "",
            "No TTS text available."
        )

    if not azure_tts_is_configured():

        return (
            None,
            "",
            "Azure TTS not configured; "
            "flashcards will use generic "
            "gTTS fallback."
        )

    try:

        audio = get_azure_tts_audio_bytes(
            source_text
        )

        provider = (
            clean_val(AZURE_SPEECH_VOICE)
            or "ar-KW-FahedNeural"
        )

        return (
            audio,
            provider,
            f"Azure Kuwait audio generated "
            f"with {provider}."
        )

    except Exception as exc:

        return (
            None,
            "",
            "Azure TTS failed; generic gTTS "
            "fallback will be used. "
            f"Details: {exc}"
        )


# =========================================================
# INBOX AUDIO PREVIEW CACHE
# =========================================================

def inbox_audio_signature(
    tts_text,
    arabic_text
):

    """
    Creates signature for preview audio.

    This lets us reuse the previewed Azure MP3
    during approval instead of calling Azure again.
    """

    source_text = (
        clean_val(tts_text)
        or clean_val(arabic_text)
    )

    voice = (
        clean_val(AZURE_SPEECH_VOICE)
        or "ar-KW-FahedNeural"
    )

    region = clean_val(
        AZURE_SPEECH_REGION
    )

    raw = (
        f"{source_text}|"
        f"{voice}|"
        f"{region}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def clear_inbox_audio_preview():

    for key in (

        "inbox_preview_audio",
        "inbox_preview_provider",
        "inbox_preview_signature",
        "inbox_preview_error",

    ):

        st.session_state.pop(
            key,
            None
        )


# =========================================================
# JSON HELPERS
# =========================================================

def extract_json_object(text):

    if not text:

        raise ValueError(
            "Empty AI response."
        )

    cleaned = text.strip()

    cleaned = re.sub(
        r"^```json\s*",
        "",
        cleaned,
        flags=re.IGNORECASE
    )

    cleaned = re.sub(
        r"^```\s*",
        "",
        cleaned
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned
    )

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if (
        start == -1
        or end == -1
        or end <= start
    ):

        raise ValueError(
            "No valid JSON object found "
            "in AI response."
        )

    return json.loads(
        cleaned[start:end + 1]
    )


def normalize_inbox_payload(
    payload,
    fallback_text=""
):

    """
    Make Gemini output safe even if
    keys change casing/spaces/spelling.
    """

    if not isinstance(
        payload,
        dict
    ):

        raise ValueError(
            "AI response JSON is not an object."
        )

    compact = {

        re.sub(
            r"[^a-zA-Z0-9]",
            "",
            str(k)
        ).lower(): v

        for k, v
        in payload.items()
    }

    aliases = {

        "chapter": [
            "chapter",
            "category",
            "lesson",
            "customlessoncategory",
        ],

        "arabicscript": [
            "arabicscript",
            "arabic",
            "arabictext",
            "arabicword",
        ],

        "pronunciation": [
            "pronunciation",
            "pronounciation",
            "phonetic",
            "transliteration",
        ],

        "ttstext": [
            "ttstext",
            "tts",
            "audiotext",
            "texttospeech",
            "speechtext",
        ],

        "englishmeaning": [
            "englishmeaning",
            "meaning",
            "english",
            "translation",
        ],

        "explanation": [
            "explanation",
            "explain",
            "usage",
        ],

        "letterwisepronounciation": [
            "letterwisepronounciation",
            "letterwisepronunciation",
            "letterpronunciation",
            "soundbreakdown",
        ],

        "letterwiseenglish": [
            "letterwiseenglish",
            "letterenglish",
            "morphology",
            "morphologycontext",
        ],
    }

    normalized = {}

    for (
        target_key,
        possible_keys
    ) in aliases.items():

        value = ""

        for possible_key in possible_keys:

            if possible_key in compact:

                value = compact[
                    possible_key
                ]

                break

        normalized[
            target_key
        ] = clean_val(value)

    if not normalized[
        "arabicscript"
    ]:

        normalized[
            "arabicscript"
        ] = clean_val(
            fallback_text
        )

    if not normalized[
        "chapter"
    ]:

        normalized[
            "chapter"
        ] = "Custom Lesson"

    return normalized


# =========================================================
# DATABASE
# =========================================================

def ensure_column(
    conn,
    table_name,
    column_name,
    column_type
):

    existing = {

        row[1]

        for row in conn.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    }

    if column_name not in existing:

        conn.execute(
            f"ALTER TABLE "
            f"{table_name} "
            f"ADD COLUMN "
            f"{column_name} "
            f"{column_type}"
        )

        conn.commit()


def init_db():

    conn = sqlite3.connect(
        DB_NAME
    )

    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS vocab
        (
            id TEXT PRIMARY KEY,
            chapter TEXT,
            arabic TEXT,
            pronunciation TEXT,
            english TEXT,
            explanation TEXT,
            letter_pronunc TEXT,
            letter_eng TEXT,
            score INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            ttstext TEXT DEFAULT '',
            audio_mp3 BLOB,
            audio_provider TEXT DEFAULT ''
        )
        """
    )

    conn.commit()

    # Upgrade old databases safely
    ensure_column(
        conn,
        "vocab",
        "ttstext",
        "TEXT DEFAULT ''"
    )

    ensure_column(
        conn,
        "vocab",
        "audio_mp3",
        "BLOB"
    )

    ensure_column(
        conn,
        "vocab",
        "audio_provider",
        "TEXT DEFAULT ''"
    )

    return conn


@st.cache_data(
    ttl=600,
    show_spinner=False
)
def fetch_sheet_data(url):

    return pd.read_csv(url)


def sync_data(
    conn,
    df
):

    c = conn.cursor()

    df.columns = (
        df.columns
        .str.replace(
            r"[^a-zA-Z0-9]",
            "",
            regex=True
        )
        .str.lower()
    )

    for _, row in df.iterrows():

        arabic_text = clean_val(
            row.get(
                "arabicscript",
                ""
            )
        )

        if not arabic_text:
            continue

        word_id = hashlib.md5(
            arabic_text.encode()
        ).hexdigest()

        l_pron = clean_val(

            row.get(

                "letterwisepronounciation",

                row.get(
                    "letterwisepronunciation",
                    ""
                )
            )
        )

        tts_text = clean_val(

            row.get(
                "ttstext",
                row.get(
                    "tts",
                    ""
                )
            )
        )

        c.execute(
            """
            INSERT INTO vocab
            (
                id,
                chapter,
                arabic,
                pronunciation,
                english,
                explanation,
                letter_pronunc,
                letter_eng,
                score,
                notes,
                ttstext,
                audio_mp3,
                audio_provider
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )

            ON CONFLICT(id)
            DO UPDATE SET

                chapter =
                    excluded.chapter,

                arabic =
                    excluded.arabic,

                pronunciation =
                    excluded.pronunciation,

                english =
                    excluded.english,

                explanation =
                    excluded.explanation,

                letter_pronunc =
                    excluded.letter_pronunc,

                letter_eng =
                    excluded.letter_eng,

                ttstext =
                    CASE
                        WHEN
                            excluded.ttstext
                            IS NOT NULL
                        AND
                            excluded.ttstext != ''
                        THEN
                            excluded.ttstext
                        ELSE
                            vocab.ttstext
                    END
            """,

            (
                word_id,

                clean_val(
                    row.get(
                        "chapter"
                    )
                ),

                arabic_text,

                clean_val(
                    row.get(
                        "pronunciation"
                    )
                ),

                clean_val(
                    row.get(
                        "englishmeaning"
                    )
                ),

                clean_val(
                    row.get(
                        "explanation"
                    )
                ),

                l_pron,

                clean_val(
                    row.get(
                        "letterwiseenglish"
                    )
                ),

                0,

                "",

                tts_text,

                None,

                "",
            ),
        )

    conn.commit()


def upsert_vocab_entry(
    conn,
    chapter,
    arabic,
    pronunciation,
    english,
    explanation,
    letter_pronunc,
    letter_eng,
    ttstext="",
    audio_mp3=None,
    audio_provider=""
):

    arabic = clean_val(
        arabic
    )

    if not arabic:

        raise ValueError(
            "Arabic Script cannot be empty."
        )

    word_id = hashlib.md5(
        arabic.encode()
    ).hexdigest()

    conn.cursor().execute(
        """
        INSERT INTO vocab
        (
            id,
            chapter,
            arabic,
            pronunciation,
            english,
            explanation,
            letter_pronunc,
            letter_eng,
            score,
            notes,
            ttstext,
            audio_mp3,
            audio_provider
        )

        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?,
            0, '', ?, ?, ?
        )

        ON CONFLICT(id)
        DO UPDATE SET

            chapter =
                excluded.chapter,

            arabic =
                excluded.arabic,

            pronunciation =
                excluded.pronunciation,

            english =
                excluded.english,

            explanation =
                excluded.explanation,

            letter_pronunc =
                excluded.letter_pronunc,

            letter_eng =
                excluded.letter_eng,

            ttstext =
                excluded.ttstext,

            audio_mp3 =
                COALESCE(
                    excluded.audio_mp3,
                    vocab.audio_mp3
                ),

            audio_provider =
                CASE
                    WHEN
                        excluded.audio_mp3
                        IS NOT NULL
                    THEN
                        excluded.audio_provider
                    ELSE
                        vocab.audio_provider
                END
        """,

        (
            word_id,

            clean_val(
                chapter
            )
            or "Custom Lesson",

            arabic,

            clean_val(
                pronunciation
            ),

            clean_val(
                english
            ),

            clean_val(
                explanation
            ),

            clean_val(
                letter_pronunc
            ),

            clean_val(
                letter_eng
            ),

            clean_val(
                ttstext
            )
            or arabic,

            audio_mp3,

            clean_val(
                audio_provider
            ),
        ),
    )

    conn.commit()

    return word_id


# =========================================================
# GOOGLE SHEET WRITE-BACK
# =========================================================

def append_vocab_entry_to_google_sheet(
    chapter,
    arabic,
    pronunciation,
    english,
    explanation,
    letter_pronunc,
    letter_eng,
    ttstext=""
):

    if not SHEET_APPEND_WEBHOOK_URL:

        return (
            False,
            "Google Sheet write-back is not configured. "
            "Add SHEET_APPEND_WEBHOOK_URL "
            "in Streamlit Secrets."
        )

    if not SHEET_APPEND_SECRET:

        return (
            False,
            "Google Sheet write-back secret is missing. "
            "Add SHEET_APPEND_SECRET "
            "in Streamlit Secrets."
        )

    payload = {

        "secret":
            SHEET_APPEND_SECRET,

        "entry": {

            "chapter":
                clean_val(chapter)
                or "Custom Lesson",

            "arabicscript":
                clean_val(arabic),

            "pronunciation":
                clean_val(pronunciation),

            "ttstext":
                clean_val(ttstext)
                or clean_val(arabic),

            "englishmeaning":
                clean_val(english),

            "explanation":
                clean_val(explanation),

            "letterwisepronounciation":
                clean_val(
                    letter_pronunc
                ),

            "letterwiseenglish":
                clean_val(
                    letter_eng
                ),
        },
    }

    try:

        resp = requests.post(
            SHEET_APPEND_WEBHOOK_URL,
            json=payload,
            timeout=30
        )

    except Exception as exc:

        return (
            False,
            f"Google Sheet write failed: {exc}"
        )

    if resp.status_code != 200:

        return (
            False,
            "Google Sheet write failed. "
            f"HTTP {resp.status_code}: "
            f"{resp.text[:300]}"
        )

    try:

        data = resp.json()

    except Exception:

        return (
            False,
            "Google Sheet returned a "
            "non-JSON response: "
            f"{resp.text[:300]}"
        )

    if data.get("ok") is True:

        return (
            True,
            clean_val(
                data.get("message")
            )
            or "Saved to Google Sheet."
        )

    return (
        False,
        clean_val(
            data.get("error")
        )
        or
        f"Google Sheet write failed: {data}"
    )


# =========================================================
# SCORE / NOTES
# =========================================================

def update_score(
    conn,
    word_id,
    is_correct
):

    c = conn.cursor()

    row = c.execute(
        "SELECT score "
        "FROM vocab "
        "WHERE id = ?",
        (word_id,)
    ).fetchone()

    if not row:
        return 0

    new_score = (
        (row[0] or 0) + 1
        if is_correct
        else 0
    )

    c.execute(
        "UPDATE vocab "
        "SET score = ? "
        "WHERE id = ?",
        (
            new_score,
            word_id
        )
    )

    conn.commit()

    return new_score


def save_note(
    conn,
    word_id,
    note_text
):

    conn.cursor().execute(
        "UPDATE vocab "
        "SET notes = ? "
        "WHERE id = ?",
        (
            note_text,
            word_id
        )
    )

    conn.commit()


def autosave_note_from_state(
    word_id,
    text_key,
    note_key
):

    note_text = (
        st.session_state.get(
            text_key,
            ""
        )
    )

    st.session_state[
        note_key
    ] = note_text

    temp_conn = sqlite3.connect(
        DB_NAME
    )

    save_note(
        temp_conn,
        word_id,
        note_text
    )

    temp_conn.close()


def get_stats(conn):

    c = conn.cursor()

    total = c.execute(
        "SELECT COUNT(*) "
        "FROM vocab"
    ).fetchone()[0]

    mastered = c.execute(
        "SELECT COUNT(*) "
        "FROM vocab "
        "WHERE score >= 3"
    ).fetchone()[0]

    practice = c.execute(
        "SELECT COUNT(*) "
        "FROM vocab "
        "WHERE score = 0"
    ).fetchone()[0]

    learning = (
        total
        - mastered
        - practice
    )

    return (
        total,
        mastered,
        learning,
        practice
    )


# =========================================================
# GEMINI REST API
# =========================================================

def call_gemini_dynamic(
    prompt,
    api_key,
    system_instruction=None,
    temperature=None,
    force_json=False,
):

    list_url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models?key={api_key}"
    )

    list_resp = requests.get(
        list_url,
        timeout=30
    )

    if list_resp.status_code != 200:

        raise Exception(
            "Google rejected key entirely: "
            f"{list_resp.text}"
        )

    models_data = (
        list_resp.json()
        .get(
            "models",
            []
        )
    )

    valid_model_name = None

    for m in models_data:

        name = m.get(
            "name",
            ""
        )

        methods = m.get(
            "supportedGenerationMethods",
            []
        )

        if (
            "gemini" in name.lower()
            and
            "generateContent"
            in methods
        ):

            valid_model_name = name

            if (
                "flash"
                in name.lower()
            ):
                break

    if not valid_model_name:

        raise Exception(
            "Your API key has 0 "
            "authorized text models."
        )

    generate_url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/{valid_model_name}:"
        f"generateContent?key={api_key}"
    )

    headers = {
        "Content-Type":
            "application/json"
    }

    payload = {

        "contents": [
            {
                "role": "user",

                "parts": [
                    {
                        "text": prompt
                    }
                ],
            }
        ]
    }

    if system_instruction:

        payload[
            "system_instruction"
        ] = {

            "parts": [
                {
                    "text":
                        system_instruction
                }
            ]
        }

    generation_config = {}

    if temperature is not None:

        generation_config[
            "temperature"
        ] = temperature

    if force_json:

        generation_config[
            "responseMimeType"
        ] = "application/json"

    if generation_config:

        payload[
            "generationConfig"
        ] = generation_config

    resp = requests.post(
        generate_url,
        headers=headers,
        json=payload,
        timeout=60
    )

    try:

        data = resp.json()

    except Exception:

        raise Exception(
            "Gemini returned non-JSON "
            "API response: "
            f"{resp.text[:500]}"
        )

    if resp.status_code == 200:

        try:

            return (
                data[
                    "candidates"
                ][0][
                    "content"
                ][
                    "parts"
                ][0][
                    "text"
                ]
            )

        except Exception:

            raise Exception(
                "Gemini response structure "
                f"unexpected: {data}"
            )

    raise Exception(
        data.get(
            "error",
            {}
        ).get(
            "message",
            str(data)
        )
    )


def clean_two_example_response(
    ai_answer
):

    raw_lines = [

        line.strip()

        for line
        in ai_answer.splitlines()

        if line.strip()
    ]

    numbered_lines = [

        line

        for line
        in raw_lines

        if (
            line.startswith("1.")
            or
            line.startswith("2.")
        )
    ]

    if len(
        numbered_lines
    ) >= 2:

        return "\n".join(
            numbered_lines[:2]
        )

    return "\n".join(
        raw_lines[:2]
    )


# =========================================================
# SMART INBOX
# =========================================================

def render_inbox(conn):

    st.subheader(
        "📥 Smart Inbox"
    )

    st.caption(
        "Add English, Arabic script, Arabizi, "
        "or any phrase. S.AI converts it "
        "into your flashcard schema."
    )

    raw_input = st.text_input(
        "Enter English, Arabic, Arabizi, or any phrase",
        key="inbox_raw_text",
        placeholder=(
            "Examples: water, "
            "where are you going, "
            "ماكو, shلونك..."
        ),
    )

    if st.button(
        "✨ Process Word",
        use_container_width=True
    ):

        raw_clean = clean_val(
            raw_input
        )

        if not GEMINI_API_KEY:

            st.error(
                "Add GEMINI_API_KEY "
                "in Streamlit Secrets."
            )

        elif not raw_clean:

            st.warning(
                "Please type a phrase first."
            )

        else:

            with st.spinner(
                "S.AI is preparing "
                "the flashcard fields..."
            ):

                try:

                    prompt = f"""
You are an expert Kuwaiti Arabic linguist and tutor.

The user may enter:
- an English word
- an English phrase
- Arabic script
- Arabizi / Franco Arabic
- mixed English-Arabic text

User input:
"{raw_clean}"

Your job:
Convert the input into a high-quality Kuwaiti Arabic flashcard.

Return ONLY one valid JSON object.
Do not use markdown.

Use exactly these keys:

{{
  "chapter": "lesson category such as Daily Phrases, Home, Office, Shopping, Greetings, Food & Drinks, Family, Travel, Questions, Time, Numbers",
  "arabicscript": "natural Kuwaiti Arabic phrase in Arabic script",
  "pronunciation": "simple English transliteration for a beginner",
  "ttstext": "Arabic-only text optimized for text-to-speech pronunciation",
  "englishmeaning": "concise English meaning",
  "explanation": "short practical usage explanation",
  "letterwisepronounciation": "sound-by-sound or phrase-part breakdown",
  "letterwiseenglish": "word/part-by-part meaning or morphology context"
}}

Rules:
- The output must be natural Kuwaiti spoken Arabic, not Modern Standard Arabic.
- If the input is English, translate the intended meaning into the most natural Kuwaiti Arabic expression, not word-for-word Arabic.
- If the English input is grammatically imperfect, infer the natural meaning before translating.
- Prefer phrases a Kuwaiti person would actually say in daily conversation.
- Prefer Kuwaiti/Gulf spoken dialect over formal Arabic.
- Avoid textbook/formal Arabic unless there is no natural spoken equivalent.
- Before finalizing the meaning, check whether the main verb is being used with a physical object/body part or with an abstract action/habit.
- Do not translate a physical command as a metaphorical insult or idiom unless that meaning is genuinely used by native Kuwaiti speakers.
- For context-sensitive verbs such as بطل, سكّر, مسك, طلع, نزل, خله, شال, and حط, choose the meaning from the object and context, not from the most common dictionary meaning.
- If a word changes meaning by context, mention that briefly in the explanation when relevant.
- If the output is Gulf-common rather than specifically Kuwaiti, clearly mention that in the explanation.
- If formal Arabic is used, clearly mention in the explanation that it is more formal and why it was used.
- Use Kuwaiti/Gulf spoken expressions where suitable, such as شلون، شنو، وين، ماكو، أبي، عندي، في، خوش.
- Keep the Arabic phrase short, practical, and usable in real conversation.
- "arabicscript" must contain only the final Arabic/Kuwaiti phrase in Arabic script.
- "pronunciation" must be simple for an English speaker to read.
- "ttstext" must be Arabic script only, written to help a Kuwait Arabic TTS voice pronounce it naturally.
- Use simple vowel marks, spacing, or wording adjustments if useful in "ttstext".
- Do not use English letters in "ttstext".
- "englishmeaning" must be concise.
- "explanation" must be practical and short, and must state whether the phrase is Kuwaiti spoken, Gulf-common, or formal Arabic.
- "letterwisepronounciation" must explain the sound breakdown in simple English.
- "letterwiseenglish" must explain the phrase components or word-by-word meaning in simple English.
- "chapter" should be a useful lesson category such as Daily Phrases, Home, Office, Food & Drinks, Shopping, Family, Travel, Emotions, Questions, Time, Numbers, Greetings, Building/Neighbours, Work, or Travel.
- Every JSON value must be a plain string only.
- Do not return arrays, lists, nested objects, markdown, bullet points, or comments.
- Do not add comments before or after the JSON.
"""

                    response = (
                        call_gemini_dynamic(
                            prompt,
                            GEMINI_API_KEY,
                            system_instruction=(
                                KUWAITI_DIALECT_GUARDRAILS
                            ),
                            temperature=0.3,
                            force_json=True,
                        )
                    )

                    payload = (
                        normalize_inbox_payload(
                            extract_json_object(
                                response
                            ),
                            raw_clean
                        )
                    )

                    st.session_state[
                        "inbox_pending"
                    ] = payload

                    clear_inbox_audio_preview()

                    st.toast(
                        "AI parsing successful. "
                        "Review before saving."
                    )

                except Exception as e:

                    st.error(
                        f"Processing Failure: {e}"
                    )

    # =====================================================
    # REVIEW GENERATED FLASHCARD
    # =====================================================

    if (
        "inbox_pending"
        in st.session_state
    ):

        st.divider()

        st.subheader(
            "Review Before Saving"
        )

        pending = (
            st.session_state[
                "inbox_pending"
            ]
        )

        with st.form(
            "inbox_review_form"
        ):

            edit_cat = (
                st.text_input(
                    "Custom Lesson Category",
                    value=clean_val(
                        pending.get(
                            "chapter",
                            "Custom Lesson"
                        )
                    )
                )
            )

            edit_ar = (
                st.text_input(
                    "Arabic Script",
                    value=clean_val(
                        pending.get(
                            "arabicscript",
                            raw_input
                        )
                    )
                )
            )

            edit_pron = (
                st.text_input(
                    "Pronunciation",
                    value=clean_val(
                        pending.get(
                            "pronunciation",
                            ""
                        )
                    )
                )
            )

            edit_tts = (
                st.text_input(
                    "TTS Text for Audio",
                    value=clean_val(
                        pending.get(
                            "ttstext",
                            pending.get(
                                "arabicscript",
                                raw_input
                            )
                        )
                    )
                )
            )

            st.caption(
                "TTS Text is Arabic-only audio text. "
                "Preview it before saving. "
                "New approved words use the Azure "
                "Kuwait voice when Azure succeeds."
            )

            edit_mean = (
                st.text_input(
                    "English Meaning",
                    value=clean_val(
                        pending.get(
                            "englishmeaning",
                            ""
                        )
                    )
                )
            )

            edit_expl = (
                st.text_area(
                    "Explanation",
                    value=clean_val(
                        pending.get(
                            "explanation",
                            ""
                        )
                    )
                )
            )

            edit_l_pron = (
                st.text_input(
                    "Letter-wise Pronunciation",
                    value=clean_val(
                        pending.get(
                            "letterwisepronounciation",
                            ""
                        )
                    )
                )
            )

            edit_l_eng = (
                st.text_input(
                    "Letter-wise English",
                    value=clean_val(
                        pending.get(
                            "letterwiseenglish",
                            ""
                        )
                    )
                )
            )

            (
                preview_col,
                submit_col,
                cancel_col
            ) = st.columns(3)

            preview_clicked = (
                preview_col
                .form_submit_button(
                    "🔊 Preview Audio",
                    use_container_width=True
                )
            )

            submit_clicked = (
                submit_col
                .form_submit_button(
                    "✅ Approve & Save",
                    use_container_width=True
                )
            )

            cancel_clicked = (
                cancel_col
                .form_submit_button(
                    "🗑️ Discard",
                    use_container_width=True
                )
            )

        current_signature = (
            inbox_audio_signature(
                edit_tts,
                edit_ar
            )
        )

        # =================================================
        # PREVIEW AUDIO BEFORE SAVING
        # =================================================

        if preview_clicked:

            source_text = (
                clean_val(edit_tts)
                or clean_val(edit_ar)
            )

            clear_inbox_audio_preview()

            st.session_state[
                "inbox_preview_signature"
            ] = current_signature

            if not source_text:

                st.error(
                    "TTS Text and Arabic Script "
                    "are both empty."
                )

            elif azure_tts_is_configured():

                try:

                    with st.spinner(
                        "Generating Azure Kuwait "
                        "audio preview..."
                    ):

                        preview_audio = (
                            get_azure_tts_audio_bytes(
                                source_text
                            )
                        )

                    st.session_state[
                        "inbox_preview_audio"
                    ] = preview_audio

                    st.session_state[
                        "inbox_preview_provider"
                    ] = (
                        clean_val(
                            AZURE_SPEECH_VOICE
                        )
                        or
                        "ar-KW-FahedNeural"
                    )

                    st.session_state[
                        "inbox_preview_signature"
                    ] = current_signature

                    st.session_state[
                        "inbox_preview_error"
                    ] = ""

                except Exception as exc:

                    # Show actual Azure error
                    st.session_state[
                        "inbox_preview_error"
                    ] = str(exc)

                    # Then try gTTS fallback
                    fallback_audio = (
                        get_audio_bytes(
                            source_text
                        )
                    )

                    if fallback_audio:

                        st.session_state[
                            "inbox_preview_audio"
                        ] = fallback_audio

                        st.session_state[
                            "inbox_preview_provider"
                        ] = "gTTS fallback"

                        st.session_state[
                            "inbox_preview_signature"
                        ] = current_signature

            else:

                fallback_audio = (
                    get_audio_bytes(
                        source_text
                    )
                )

                if fallback_audio:

                    st.session_state[
                        "inbox_preview_audio"
                    ] = fallback_audio

                    st.session_state[
                        "inbox_preview_provider"
                    ] = "gTTS fallback"

                    st.session_state[
                        "inbox_preview_signature"
                    ] = current_signature

                st.session_state[
                    "inbox_preview_error"
                ] = (
                    "Azure TTS is not configured. "
                    "Preview is using generic "
                    "Arabic gTTS."
                )

        preview_audio = (
            st.session_state.get(
                "inbox_preview_audio"
            )
        )

        preview_provider = clean_val(
            st.session_state.get(
                "inbox_preview_provider",
                ""
            )
        )

        preview_error = clean_val(
            st.session_state.get(
                "inbox_preview_error",
                ""
            )
        )

        preview_signature = clean_val(
            st.session_state.get(
                "inbox_preview_signature",
                ""
            )
        )

        # Display preview only if it matches current TTS text
        if (
            preview_audio
            and
            preview_signature
            == current_signature
        ):

            st.markdown(
                "**🔊 Audio Preview**"
            )

            st.audio(
                preview_audio,
                format="audio/mp3"
            )

            if (
                preview_provider
                == "gTTS fallback"
            ):

                st.warning(
                    "Preview provider: "
                    "generic Arabic gTTS fallback."
                )

            else:

                st.success(
                    "Preview provider: "
                    "Azure Kuwait voice "
                    f"({preview_provider})."
                )

        if (
            preview_error
            and
            preview_signature
            == current_signature
        ):

            st.error(
                "Azure preview issue: "
                f"{preview_error}"
            )

        # =================================================
        # APPROVE AND SAVE
        # =================================================

        if submit_clicked:

            try:

                # Reuse previewed Azure MP3
                # if TTSText has not changed.
                if (
                    preview_audio
                    and
                    preview_signature
                    == current_signature
                    and
                    preview_provider
                    and
                    preview_provider
                    != "gTTS fallback"
                ):

                    audio_mp3 = (
                        preview_audio
                    )

                    audio_provider = (
                        preview_provider
                    )

                    audio_msg = (
                        "Azure Kuwait preview "
                        "reused and saved "
                        f"({audio_provider})."
                    )

                else:

                    with st.spinner(
                        "Generating Kuwait Arabic "
                        "audio once..."
                    ):

                        (
                            audio_mp3,
                            audio_provider,
                            audio_msg
                        ) = (
                            generate_approved_word_audio(
                                edit_tts,
                                edit_ar
                            )
                        )

                # Save locally
                upsert_vocab_entry(
                    conn,
                    edit_cat,
                    edit_ar,
                    edit_pron,
                    edit_mean,
                    edit_expl,
                    edit_l_pron,
                    edit_l_eng,
                    edit_tts,
                    audio_mp3,
                    audio_provider,
                )

                # Save to Google Sheet
                (
                    sheet_ok,
                    sheet_msg
                ) = (
                    append_vocab_entry_to_google_sheet(
                        edit_cat,
                        edit_ar,
                        edit_pron,
                        edit_mean,
                        edit_expl,
                        edit_l_pron,
                        edit_l_eng,
                        edit_tts,
                    )
                )

                if sheet_ok:

                    fetch_sheet_data.clear()

                    st.session_state[
                        "flash_toast"
                    ] = (
                        "Saved locally + "
                        "Google Sheet under: "
                        f"{clean_val(edit_cat) or 'Custom Lesson'}. "
                        f"{audio_msg}"
                    )

                else:

                    st.session_state[
                        "flash_toast"
                    ] = (
                        "Saved locally, but "
                        "Google Sheet was not updated: "
                        f"{sheet_msg}. "
                        f"{audio_msg}"
                    )

                del st.session_state[
                    "inbox_pending"
                ]

                clear_inbox_audio_preview()

                st.session_state[
                    "current_word"
                ] = None

                st.rerun()

            except Exception as e:

                st.error(
                    f"Save failed: {e}"
                )

        # =================================================
        # DISCARD
        # =================================================

        if cancel_clicked:

            del st.session_state[
                "inbox_pending"
            ]

            clear_inbox_audio_preview()

            st.toast(
                "Draft removed."
            )

            st.rerun()


# =========================================================
# FLASHCARD
# =========================================================

def render_flashcard(
    conn,
    word_data,
    tab_key
):

    # Supports old and new DB rows
    padded = (
        list(word_data)
        + [
            "",
            None,
            ""
        ]
    )

    (
        word_id,
        chapter,
        arabic,
        pronunc,
        english,
        expl,
        l_pronunc,
        l_eng,
        score,
        saved_note,
        tts_text,
        saved_audio,
        audio_provider
    ) = padded[:13]

    display_label = (
        chapter
        if chapter
        else "Custom Lesson"
    )

    st.markdown(
        f"""
        <div style='font-size:18px;
                    font-weight:bold;
                    margin-bottom:10px;'>
            📚 {display_label}
            <span style='font-weight:normal;
                         color:#aaa;
                         font-size:14px;'>
                (Score: {score}/3)
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    (
        btn_col1,
        btn_col2
    ) = st.columns(2)

    if btn_col1.button(
        "👍 Got it",
        key=f"up_{word_id}_{tab_key}",
        use_container_width=True
    ):

        new_score = update_score(
            conn,
            word_id,
            True
        )

        st.session_state[
            "flash_toast"
        ] = (

            f"👍 Score increased to "
            f"{new_score}/3"

            if new_score < 3

            else
            "👑 Word Mastered!"
        )

        if tab_key == "home":

            st.session_state[
                "current_word"
            ] = None

        st.rerun()

    if btn_col2.button(
        "👎 Practice",
        key=f"down_{word_id}_{tab_key}",
        use_container_width=True
    ):

        update_score(
            conn,
            word_id,
            False
        )

        st.session_state[
            "flash_toast"
        ] = (
            "👎 Score reset to 0."
        )

        if tab_key == "home":

            st.session_state[
                "current_word"
            ] = None

        st.rerun()

    # =====================================================
    # FLASHCARD BODY
    # =====================================================

    with st.container(
        border=True
    ):

        st.markdown(
            f"<h1 class='arabic-word' "
            f"dir='rtl'>{arabic}</h1>",
            unsafe_allow_html=True
        )

        # First preference:
        # stored Azure audio
        audio_bytes = saved_audio

        if isinstance(
            audio_bytes,
            memoryview
        ):

            audio_bytes = (
                audio_bytes.tobytes()
            )

        if audio_bytes:

            st.audio(
                audio_bytes,
                format="audio/mp3"
            )

            if audio_provider:

                st.caption(
                    "Audio: Azure Kuwait voice "
                    f"({audio_provider})"
                )

        else:

            # Existing/old words:
            # gTTS reads TTSText first
            fallback_audio = (
                get_audio_bytes(
                    clean_val(tts_text)
                    or arabic
                )
            )

            if fallback_audio:

                st.audio(
                    fallback_audio,
                    format="audio/mp3"
                )

                st.caption(
                    "Audio: generic Arabic gTTS fallback "
                    "using TTSText where available."
                )

        display_title = (

            f"{pronunc if pronunc else 'Pronunciation'}"
            " | "
            f"{english if english else 'Meaning'}"
        )

        with st.expander(
            f"🗣️ {display_title}"
        ):

            if expl:

                st.info(
                    f"**Explanation:** "
                    f"{expl}"
                )

            if l_pronunc:

                st.write(
                    "**Sound Breakdown:** "
                    f"{l_pronunc}"
                )

            if l_eng:

                st.write(
                    "**Morphology Context:** "
                    f"{l_eng}"
                )

    # =====================================================
    # S.AI TUTOR
    # =====================================================

    note_key = (
        f"note_{word_id}_{tab_key}"
    )

    note_text_key = (
        f"text_{word_id}_{tab_key}"
    )

    if (
        note_key
        not in st.session_state
    ):

        st.session_state[
            note_key
        ] = (
            saved_note
            if saved_note
            else ""
        )

    if (
        note_text_key
        not in st.session_state
    ):

        st.session_state[
            note_text_key
        ] = (
            st.session_state[
                note_key
            ]
        )

    st.markdown(
        "<br>",
        unsafe_allow_html=True
    )

    with st.form(
        key=(
            f"sai_form_"
            f"{word_id}_"
            f"{tab_key}"
        ),
        clear_on_submit=False
    ):

        question = st.text_input(
            "Ask S.AI a question",
            key=(
                f"q_{word_id}_"
                f"{tab_key}"
            ),
            placeholder=(
                "Type 1 for exactly "
                "2 examples..."
            ),
        )

        submitted = (
            st.form_submit_button(
                "🤖 S.AI",
                use_container_width=True
            )
        )

    if submitted:

        question_clean = str(
            question
        ).strip()

        if not GEMINI_API_KEY:

            st.error(
                "Add API key "
                "in Streamlit Secrets!"
            )

        elif not question_clean:

            st.warning(
                "Type something first."
            )

        else:

            with st.spinner(
                "Thinking..."
            ):

                try:

                    if (
                        question_clean
                        == "1"
                    ):

                        prompt = f"""
Arabic word: {arabic}
Pronunciation: {pronunc}
Meaning: {english}

Give exactly 2 short Kuwaiti Arabic examples using this word.

Strict format:
1. Arabic sentence - English meaning
2. Arabic sentence - English meaning

Rules:
- Use genuine Kuwaiti/Gulf spoken usage.
- Do not invent idioms.
- If the word changes meaning by context, use the meaning appropriate to that sentence.
- No blank line between the two examples.
- Do not add explanation.
- Do not add introduction.
- Do not add extra text.
"""

                    else:

                        prompt = f"""
Arabic: {arabic}
Pronunciation: {pronunc}
Meaning: {english}

User question:
{question_clean}

Answer briefly in natural Kuwaiti context.

If the question involves meaning, slang,
usage, or an idiom, check whether the
verb meaning changes according to its
physical or abstract context.

Do not invent idioms or overconfident
dialect explanations.
"""

                    ai_answer = (
                        call_gemini_dynamic(
                            prompt,
                            GEMINI_API_KEY,
                            system_instruction=(
                                KUWAITI_DIALECT_GUARDRAILS
                            ),
                            temperature=0.3,
                        )
                        .strip()
                    )

                    if (
                        question_clean
                        == "1"
                    ):

                        ai_answer = (
                            clean_two_example_response(
                                ai_answer
                            )
                        )

                    old_note = (
                        st.session_state
                        .get(
                            note_key,
                            ""
                        )
                        .strip()
                    )

                    if old_note:

                        updated_note = (
                            f"{old_note}\n\n"
                            f"Q: {question_clean}\n"
                            f"S.AI:\n"
                            f"{ai_answer}"
                        )

                    else:

                        updated_note = (
                            f"Q: {question_clean}\n"
                            f"S.AI:\n"
                            f"{ai_answer}"
                        )

                    st.session_state[
                        note_key
                    ] = updated_note

                    st.session_state[
                        note_text_key
                    ] = updated_note

                    save_note(
                        conn,
                        word_id,
                        updated_note
                    )

                    st.toast(
                        "AI response added!"
                    )

                    st.rerun()

                except Exception as ex:

                    st.error(
                        f"S.AI Error: {ex}"
                    )

    st.text_area(
        "Notes",
        key=note_text_key,
        height=150,
        placeholder=(
            "Notes will appear here. "
            "You can edit directly..."
        ),
        on_change=(
            autosave_note_from_state
        ),
        args=(
            word_id,
            note_text_key,
            note_key
        ),
    )

    st.caption(
        "Notes autosave after editing "
        "when you tap outside / press done."
    )


# =========================================================
# MAIN APP
# =========================================================

if (
    "flash_toast"
    in st.session_state
):

    st.toast(
        st.session_state[
            "flash_toast"
        ]
    )

    del st.session_state[
        "flash_toast"
    ]


st.markdown(
    "## 🇰🇼 Yalla Kuwaiti!"
)

conn = init_db()


# =========================================================
# SYNC GOOGLE SHEET → SQLITE
# =========================================================

try:

    df = fetch_sheet_data(
        SHEET_URL
    )

    sync_data(
        conn,
        df
    )

except Exception:

    st.warning(
        "Public reference engine "
        "standalone operation active."
    )


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header(
    "Filters"
)

chapters = [

    row[0]

    for row
    in conn.cursor()
    .execute(
        """
        SELECT DISTINCT chapter
        FROM vocab
        WHERE chapter != ''
        ORDER BY chapter
        """
    )
    .fetchall()
]

selected_chapter = (
    st.sidebar.selectbox(
        "Chapter",
        ["All"] + chapters
    )
)

(
    total,
    mastered,
    learning,
    practice
) = get_stats(conn)

st.sidebar.divider()

st.sidebar.markdown(
    "🏆 **Dashboard**"
)

st.sidebar.metric(
    "👑 Mastered (Score 3+)",
    mastered
)

st.sidebar.metric(
    "📈 Learning (Score 1-2)",
    learning
)

st.sidebar.metric(
    "🔴 Needs Practice (Score 0)",
    practice
)

st.sidebar.progress(
    mastered / total
    if total > 0
    else 0,

    text=(
        "Fluency: "
        f"{int((mastered / total) * 100) if total else 0}%"
    )
)


# =========================================================
# TABS
# =========================================================

(
    tab1,
    tab2,
    tab3,
    tab4,
    tab5
) = st.tabs(
    [
        "📥 Inbox",
        "🎮 Daily",
        "🏋️ Review",
        "👑 Mastered",
        "⚙️ Sync",
    ]
)


base_q = """
SELECT
    id,
    chapter,
    arabic,
    pronunciation,
    english,
    explanation,
    letter_pronunc,
    letter_eng,
    score,
    notes,
    ttstext,
    audio_mp3,
    audio_provider
FROM vocab
"""

params = []

if (
    selected_chapter
    != "All"
):

    base_q += (
        " WHERE chapter = ?"
    )

    params.append(
        selected_chapter
    )


# =========================================================
# TAB 1 — INBOX
# =========================================================

with tab1:

    render_inbox(
        conn
    )


# =========================================================
# TAB 2 — DAILY
# =========================================================

with tab2:

    query = (
        base_q
        +
        (
            " AND score < 3"
            if "WHERE" in base_q
            else
            " WHERE score < 3"
        )
    )

    words = (
        conn.cursor()
        .execute(
            query,
            params
        )
        .fetchall()
    )

    if words:

        current = (
            st.session_state
            .get(
                "current_word"
            )
        )

        valid_ids = {
            w[0]
            for w
            in words
        }

        if (
            current is None
            or
            current[0]
            not in valid_ids
        ):

            st.session_state[
                "current_word"
            ] = random.choice(
                words
            )

        render_flashcard(
            conn,
            st.session_state[
                "current_word"
            ],
            "home"
        )

    else:

        st.success(
            "🎉 Section fully mastered!"
        )


# =========================================================
# TAB 3 — REVIEW
# =========================================================

with tab3:

    query = (
        base_q
        +
        (
            " AND score < 3 "
            "ORDER BY score ASC"

            if "WHERE" in base_q

            else

            " WHERE score < 3 "
            "ORDER BY score ASC"
        )
    )

    rows = (
        conn.cursor()
        .execute(
            query,
            params
        )
        .fetchall()
    )

    for w in rows[:20]:

        with st.expander(
            f"🔴 {w[2]} "
            f"({w[4]}) "
            f"- Score: {w[8]}/3"
        ):

            render_flashcard(
                conn,
                w,
                f"prac_{w[0]}"
            )


# =========================================================
# TAB 4 — MASTERED
# =========================================================

with tab4:

    query = (
        base_q
        +
        (
            " AND score >= 3"

            if "WHERE" in base_q

            else

            " WHERE score >= 3"
        )
    )

    rows = (
        conn.cursor()
        .execute(
            query,
            params
        )
        .fetchall()
    )

    for w in rows[:20]:

        with st.expander(
            f"👑 {w[2]} "
            f"({w[4]})"
        ):

            render_flashcard(
                conn,
                w,
                f"mast_{w[0]}"
            )


# =========================================================
# TAB 5 — SYNC / DIAGNOSTICS
# =========================================================

with tab5:

    st.subheader(
        "⚙️ Sync Management"
    )

    # Google Sheet status
    if (
        SHEET_APPEND_WEBHOOK_URL
        and
        SHEET_APPEND_SECRET
    ):

        st.success(
            "Google Sheet write-back "
            "is configured."
        )

    elif (
        SHEET_APPEND_WEBHOOK_URL
        and
        not SHEET_APPEND_SECRET
    ):

        st.warning(
            "Google Sheet webhook URL "
            "is configured, but "
            "SHEET_APPEND_SECRET is missing. "
            "Google Sheet write-back will fail."
        )

    else:

        st.warning(
            "Google Sheet write-back "
            "is not configured yet. "
            "Approved Inbox words will "
            "save only inside the app database."
        )

    st.divider()

    # Azure status
    if azure_tts_is_configured():

        configured_voice = (
            clean_val(
                AZURE_SPEECH_VOICE
            )
            or
            "ar-KW-FahedNeural"
        )

        st.success(
            "Azure Speech secrets are present. "
            f"Configured voice: {configured_voice}"
        )

        st.caption(
            "Use the test below to confirm "
            "the key, region, endpoint, "
            "and Kuwait voice actually work."
        )

        if st.button(
            "🔊 Test Azure Kuwait Voice",
            use_container_width=True
        ):

            try:

                with st.spinner(
                    "Calling Azure Speech directly..."
                ):

                    test_audio = (
                        get_azure_tts_audio_bytes(
                            "شلونك؟"
                        )
                    )

                st.audio(
                    test_audio,
                    format="audio/mp3"
                )

                st.success(
                    "Azure TTS test succeeded "
                    f"with {configured_voice}."
                )

            except Exception as exc:

                st.error(
                    "Azure TTS test failed: "
                    f"{exc}"
                )

    else:

        st.info(
            "Azure Kuwait TTS is not "
            "configured yet. "
            "Audio will use generic "
            "Arabic gTTS fallback."
        )

    st.divider()

    if st.button(
        "Refresh Reference Datasets",
        use_container_width=True
    ):

        fetch_sheet_data.clear()

        st.session_state[
            "current_word"
        ] = None

        st.rerun()


# =========================================================
# CLOSE DB
# =========================================================

conn.close()
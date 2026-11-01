"""Presentation-only helpers. Never read secrets, call providers or mutate progress."""
from html import escape

STYLE = """
<style>
:root {--yk-ink:#193b39;--yk-muted:#526b68;--yk-line:#d7e5df;--yk-accent:#12675b;--yk-sand:#f5f3e9;--yk-surface:#ffffff;}
[data-testid="stAppViewContainer"] {background:#f6f8f4;color:var(--yk-ink);}
.block-container {max-width:960px;padding:4.5rem 1.5rem 4rem;}
[data-testid="stHeader"] {background:transparent;}
h1,h2,h3 {color:var(--yk-ink);letter-spacing:-.025em;}
[data-testid="stSidebar"] {background:#edf3ed;border-right:1px solid var(--yk-line);}
[data-testid="stSidebar"] .block-container {padding:1.5rem 1rem;}
[data-testid="stVerticalBlockBorderWrapper"] > div {border-color:var(--yk-line)!important;border-radius:20px!important;background:var(--yk-surface);}
[role="tablist"] {gap:.35rem;background:#eaf1eb;border-radius:16px;padding:.4rem;overflow-x:auto;}
[role="tab"] {min-height:48px;padding:.55rem .85rem;border-radius:11px;color:#35514d;white-space:nowrap;font-weight:600;}
[role="tab"][aria-selected="true"] {background:#fff;color:#125b50;box-shadow:0 2px 6px #153f3410;}
[data-baseweb="tab-highlight"] {display:none;}
[role="tabpanel"] {padding-top:1.5rem;}
.stButton button,.stFormSubmitButton button {min-height:46px;border-radius:12px;font-weight:600;}
.stButton button:focus-visible,.stFormSubmitButton button:focus-visible,[role="tab"]:focus-visible {outline:3px solid #ae6b23;outline-offset:3px;}
.stButton button[kind="primary"],.stFormSubmitButton button[kind="primary"] {background:#12675b;border-color:#12675b;color:#fff;}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea {font-size:1rem;}
.yk-hero {padding:1.65rem 1.8rem;border:1px solid #d7e5df;border-radius:24px;background:linear-gradient(125deg,#e7f0e6,#fcf9ee);margin:0 0 1.4rem;position:relative;overflow:hidden;}
.yk-eyebrow {color:#36685c;text-transform:uppercase;font-weight:700;letter-spacing:.13em;font-size:.72rem;margin:0 0 .6rem;}
.yk-hero h1 {font-size:2.35rem;font-weight:750;margin:0;line-height:1.15;}
.yk-hero p {max-width:560px;color:#42645d;font-size:1rem;line-height:1.6;margin:.75rem 0 0;}
.yk-wordmark {position:absolute;right:2rem;top:1.4rem;font-size:2.9rem;color:#37705d;opacity:.18;transform:rotate(-8deg);}
.yk-stats {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem;margin:1rem 0 .7rem;}
.yk-stat {background:#fff;border:1px solid var(--yk-line);border-radius:16px;padding:1rem 1.2rem;}
.yk-stat dt {font-size:.8rem;font-weight:600;color:var(--yk-muted);margin:0 0 .35rem;}
.yk-stat dd {font-size:1.8rem;line-height:1.2;font-weight:700;color:var(--yk-ink);margin:0;}
.yk-section {margin:.1rem 0 1.2rem;}
.yk-section h2 {font-size:1.3rem;margin:0 0 .3rem;}
.yk-section p {color:var(--yk-muted);font-size:.9rem;line-height:1.5;margin:0;}
.yk-card-meta {display:flex;justify-content:space-between;gap:1rem;align-items:center;flex-wrap:wrap;margin:.3rem 0 .8rem;color:var(--yk-muted);font-size:.85rem;}
.yk-pill {padding:.3rem .65rem;border-radius:100px;background:#e7f1eb;color:#245f4f;font-size:.75rem;font-weight:650;}
.arabic-word {font-family:Tahoma,Arial,sans-serif;text-align:center;font-size:3.25rem;line-height:1.65;margin:.45rem 0 .6rem!important;overflow-wrap:anywhere;}
.yk-pronunciation {font-size:1.12rem;color:#53746b;text-align:center;margin:0 0 .35rem;line-height:1.5;overflow-wrap:anywhere;}
.yk-meaning {text-align:center;color:#193b39;font-size:1.35rem;font-weight:650;margin:0 0 1.15rem;line-height:1.5;overflow-wrap:anywhere;}
audio {width:100%;min-height:45px;margin:.3rem 0;}
.note-preview {font-size:.95rem;line-height:1.6;color:var(--yk-ink);background:#f7faf6;border:1px solid var(--yk-line);border-radius:12px;padding:14px;min-height:80px;max-height:220px;overflow:auto;white-space:pre-wrap;}
.yk-empty {padding:2rem 1.5rem;border:1px dashed #b9cec2;border-radius:18px;background:#f0f5ed;text-align:center;color:#35574e;}
.yk-empty strong {display:block;font-size:1.15rem;margin-bottom:.5rem;}
.yk-footer {font-size:.78rem;color:#617970;text-align:center;margin:2rem 0 0;}
@media(max-width:640px) {.block-container{padding:4rem .8rem 3rem;}.yk-hero{padding:1.3rem 1.2rem;border-radius:18px;}.yk-hero h1{font-size:1.85rem;}.yk-wordmark{font-size:2rem;right:1rem;}.yk-stats{gap:.4rem;}.yk-stat{padding:.8rem .65rem;}.yk-stat dd{font-size:1.5rem;}.yk-stat dt{font-size:.72rem;}.arabic-word{font-size:2.6rem;}[role="tab"]{padding:.5rem .65rem;}.yk-meaning{font-size:1.15rem;}}
@media(prefers-reduced-motion:reduce) {*{scroll-behavior:auto!important;}}
</style>
"""

HERO = """<header class="yk-hero"><span class="yk-wordmark" lang="ar" dir="rtl" aria-hidden="true">يلا</span><div class="yk-eyebrow">Everyday conversations • Kuwaiti Arabic</div><h1>Yalla Kuwaiti</h1><p>A little practice. More confidence.<br>Listen, understand and make the words your own.</p></header>"""


def progress_cards(practice, learning, mastered):
    values = [("Needs practice", practice), ("Learning", learning), ("Mastered", mastered)]
    return '<dl class="yk-stats" aria-label="Vocabulary progress">' + ''.join(
        f'<div class="yk-stat"><dt>{label}</dt><dd>{int(value)}</dd></div>'
        for label, value in values
    ) + '</dl>'


def section_heading(title, description):
    return f'<div class="yk-section"><h2>{escape(title)}</h2><p>{escape(description)}</p></div>'


def empty_state(title, description):
    return f'<div class="yk-empty"><strong>{escape(title)}</strong>{escape(description)}</div>'


def word_heading(chapter, score):
    return f'<div class="yk-card-meta"><span>{escape(str(chapter))}</span><span class="yk-pill">Recall score {int(score)}</span></div>'


def word_translation(pronunciation, meaning):
    return f'<p class="yk-pronunciation">{escape(str(pronunciation or ""))}</p><p class="yk-meaning">{escape(str(meaning or ""))}</p>'



BRIGHT = """
<style>
:root {--yk-ink:#133452;--yk-muted:#45617c;--yk-line:#d0e2ed;--yk-surface:#ffffff;--yk-bg:#f1f8ff;--yk-soft:#e1f3ff;--yk-input:#ffffff;--yk-accent:#007e87;}
[data-testid="stAppViewContainer"]{background:var(--yk-bg);color:var(--yk-ink);}
[data-testid="stSidebar"]{background:var(--yk-soft);}
.yk-hero{background:linear-gradient(115deg,#05b7ac,#1374c7);border:0;box-shadow:0 12px 28px #076d8a24;}
.yk-hero h1,.yk-hero p,.yk-eyebrow{color:#fff;}.yk-wordmark{color:#fff;opacity:.28;font-size:4rem;}
.yk-stat:nth-child(1){border-top:4px solid #ee9660;}.yk-stat:nth-child(2){border-top:4px solid #4996ed;}.yk-stat:nth-child(3){border-top:4px solid #16b69e;}
[role="tablist"]{background:var(--yk-soft);border:0;gap:.25rem;}
[role="tab"]{color:var(--yk-ink);flex-shrink:0;}
[role="tab"][aria-selected="true"]{background:var(--yk-accent);color:white;box-shadow:0 3px 8px #007d8730;}
[role="tab"][aria-selected="true"] p,[role="tab"][aria-selected="true"] [data-testid="stMarkdownContainer"]{color:white;}
.yk-stat,.note-preview{background:var(--yk-surface);}
.yk-pronunciation,.yk-footer{color:var(--yk-muted);}.yk-meaning{color:var(--yk-ink);}
.yk-pill{background:var(--yk-soft);color:var(--yk-ink);}
.yk-empty{background:var(--yk-soft);color:var(--yk-ink);}
[data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"], [data-testid="stMetricValue"], [data-testid="stMetricLabel"]{color:var(--yk-ink);}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{color:var(--yk-muted);}
.stButton button,.stFormSubmitButton button{background:var(--yk-surface);color:var(--yk-ink);border-color:var(--yk-line);}
.stButton button:hover,.stFormSubmitButton button:hover{background:var(--yk-soft);border-color:var(--yk-accent);color:var(--yk-ink);}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea{background:var(--yk-input);color:var(--yk-ink);}
[data-testid="stTextInput"] input::placeholder,[data-testid="stTextArea"] textarea::placeholder{color:var(--yk-muted);opacity:1;}
[data-testid="stExpander"] details{background:var(--yk-surface);color:var(--yk-ink);border-color:var(--yk-line);}
[data-testid="stVerticalBlockBorderWrapper"]>div,[data-testid="stVerticalBlockBorderWrapper"]{border-color:var(--yk-line);}
[data-testid="stRadio"]{background:var(--yk-soft);border-radius:14px;padding:.6rem .9rem;}
@media(max-width:640px){.block-container{padding-top:3.5rem;}.yk-hero{padding:1.1rem 1.2rem;margin-bottom:.6rem;}.yk-hero h1{font-size:1.85rem;}.yk-hero p{font-size:.9rem;}.yk-stats{margin-top:.7rem;}[role="tablist"]{overflow-x:auto;scrollbar-width:thin;}[role="tab"]{min-width:72px;}.yk-eyebrow{font-size:.63rem;}.yk-wordmark{font-size:2.8rem;}.yk-section{margin-bottom:.7rem;}}
</style>
"""
DARK = """<style>
:root{--yk-ink:#eef6ff;--yk-muted:#b8ccdf;--yk-line:#36536d;--yk-surface:#18334b;--yk-bg:#0c1d30;--yk-soft:#203f58;--yk-input:#18334b;--yk-accent:#087e87;color-scheme:dark;}
.yk-hero{background:linear-gradient(115deg,#087c82,#215bb3);box-shadow:0 12px 28px #0003;}
[data-testid="stHeader"]{background:#0c1d30ed;}
[data-testid="stAlert"]{color:#eef6ff;}
[data-testid="stToast"],[role="alertdialog"]{background:#18334b!important;color:#eef6ff!important;border:1px solid #36536d;}
[role="alertdialog"] p{color:#eef6ff!important;}
[data-testid="stSelectbox"] [role="combobox"], [data-testid="stSelectbox"] button{background:#18334b;color:#eef6ff;}
</style>"""

def theme_style(mode):
    """Explicit in-app choice, never inferred from an OS setting."""
    return STYLE + BRIGHT + (DARK if mode == "Dark" else "")

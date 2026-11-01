"""Presentation-only helpers. Never read secrets, call providers or mutate progress."""
from html import escape

STYLE = """
<style>
:root {--yk-ink:#193b39;--yk-muted:#526b68;--yk-line:#d7e5df;--yk-accent:#12675b;--yk-sand:#f5f3e9;--yk-surface:#ffffff;}
[data-testid="stAppViewContainer"] {background:#f6f8f4;color:var(--yk-ink);}
.block-container {max-width:960px;padding:2rem 1.5rem 4rem;}
[data-testid="stHeader"] {background:transparent;}
h1,h2,h3 {color:var(--yk-ink);letter-spacing:-.025em;}
[data-testid="stSidebar"] {background:#edf3ed;border-right:1px solid var(--yk-line);}
[data-testid="stSidebar"] .block-container {padding:1.5rem 1rem;}
[data-testid="stVerticalBlockBorderWrapper"] > div {border-color:var(--yk-line)!important;border-radius:20px!important;background:var(--yk-surface);}
[data-baseweb="tab-list"] {gap:.35rem;background:#eaf1eb;border-radius:16px;padding:.4rem;overflow-x:auto;}
button[data-baseweb="tab"] {min-height:48px;padding:.55rem .85rem;border-radius:11px;color:#35514d;white-space:nowrap;font-weight:600;}
button[data-baseweb="tab"][aria-selected="true"] {background:#fff;color:#125b50;box-shadow:0 2px 6px #153f3410;}
[data-baseweb="tab-highlight"] {display:none;}
[data-baseweb="tab-panel"] {padding-top:1.5rem;}
.stButton button,.stFormSubmitButton button {min-height:46px;border-radius:12px;font-weight:600;}
.stButton button:focus-visible,.stFormSubmitButton button:focus-visible,button[data-baseweb="tab"]:focus-visible {outline:3px solid #ae6b23;outline-offset:3px;}
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
@media(max-width:640px) {.block-container{padding:1rem .8rem 3rem;}.yk-hero{padding:1.3rem 1.2rem;border-radius:18px;}.yk-hero h1{font-size:1.85rem;}.yk-wordmark{font-size:2rem;right:1rem;}.yk-stats{gap:.4rem;}.yk-stat{padding:.8rem .65rem;}.yk-stat dd{font-size:1.5rem;}.yk-stat dt{font-size:.72rem;}.arabic-word{font-size:2.6rem;}button[data-baseweb="tab"]{padding:.5rem .65rem;}.yk-meaning{font-size:1.15rem;}}
@media(prefers-reduced-motion:reduce) {*{scroll-behavior:auto!important;}}
@media(prefers-color-scheme:dark) {:root{--yk-ink:#e3f0e8;--yk-muted:#acc3b8;--yk-line:#38574c;--yk-surface:#1b3029;}[data-testid="stAppViewContainer"]{background:#14251f;}[data-testid="stSidebar"]{background:#192e25;}.yk-hero{background:linear-gradient(125deg,#233f30,#30382b);border-color:#38574c;}.yk-hero p,.yk-eyebrow{color:#b7cebf;}.yk-wordmark{color:#d4e5cc;}[data-baseweb="tab-list"]{background:#20392d;}button[data-baseweb="tab"]{color:#bdd0c5;}button[data-baseweb="tab"][aria-selected="true"]{background:#345442;color:#fff;}.yk-stat{background:#1b3029;}.yk-pronunciation{color:#accbbc;}.yk-meaning{color:#e3f0e8;}.yk-pill{background:#31503f;color:#dcf1df;}.note-preview{background:#1b3029;}.yk-empty{background:#20372b;color:#c8dbcd;}}
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

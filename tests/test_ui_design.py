"""Presentation helpers escape source content and describe real progress."""
import pytest
from ui_design import HERO, STYLE, empty_state, progress_cards, section_heading, word_heading, word_translation

@pytest.mark.parametrize('render', [lambda:empty_state('<script>x</script>', '<img src=x>'),lambda:section_heading('<script>x</script>', '<img src=x>'),lambda:word_heading('<script>x</script>',4),lambda:word_translation('<script>x</script>', '<img src=x>')])
def test_untrusted_content_is_escaped(render):
    result=render()
    assert '<script>' not in result and '<img ' not in result
    assert '&lt;script&gt;' in result

def test_score_is_not_falsely_capped():
    assert 'Recall score 4' in word_heading('Greetings',4)
    assert '/3' not in word_heading('Greetings',4)

def test_progress_has_semantic_labels_and_no_fluency_claim():
    result=progress_cards(7,2,3)
    assert '<dl ' in result and '<dt>Needs practice</dt>' in result
    assert '<dd>7</dd>' in result and '<dd>2</dd>' in result and '<dd>3</dd>' in result
    assert 'Fluency' not in result

def test_responsive_and_keyboard_styles_present():
    assert '@media(max-width:640px)' in STYLE
    assert ':focus-visible' in STYLE and 'min-height:46px' in STYLE
    assert 'lang="ar"' in HERO and 'aria-hidden="true"' in HERO


def test_tabs_style_uses_current_semantic_roles():
    # Streamlit 1.66 tabs are role=tab divs, not BaseWeb buttons.
    assert '[role="tablist"]' in STYLE
    assert '[role="tab"][aria-selected="true"]' in STYLE
    assert '[role="tab"]:focus-visible' in STYLE

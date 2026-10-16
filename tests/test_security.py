"""Offline security regressions: no real credentials or provider calls."""
import ast
import json
from pathlib import Path
import sqlite3
import tomllib
from unittest.mock import Mock

import pandas as pd
import pytest
import requests
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'test-only-high-entropy-password-12345'


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    import streamlit as st
    st.cache_data.clear()
    monkeypatch.chdir(tmp_path)
    # Any unexpected provider access fails the test, even in broad app handlers.
    network = Mock(side_effect=AssertionError('Unexpected network call'))
    monkeypatch.setattr(requests.sessions.Session, 'request', network)
    sheet = Mock(return_value=pd.DataFrame(columns=['ArabicScript']))
    monkeypatch.setattr(pd, 'read_csv', sheet)
    return tmp_path, network, sheet


def app(password=PASSWORD):
    at = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=15)
    if password is not None:
        at.secrets['APP_PASSWORD'] = password
    return at


def sign_in(at, password=PASSWORD):
    at.text_input(key='_access_password').input(password)
    next(b for b in at.button if b.label == 'Sign in').click().run()
    return at


@pytest.mark.parametrize('password', [None, '', 'short'])
def test_missing_or_weak_config_is_closed(isolated, password):
    folder, network, sheet = isolated
    at = app(password).run()
    assert not at.exception
    assert at.error
    assert not at.tabs
    assert not list(folder.glob('*.db'))
    network.assert_not_called()
    sheet.assert_not_called()


def test_anonymous_and_wrong_password_have_no_side_effects(isolated):
    folder, network, sheet = isolated
    at = app().run()
    assert not at.exception
    assert not at.tabs
    sign_in(at, 'wrong password')
    assert not at.exception
    assert any('Incorrect' in e.value for e in at.error)
    assert not at.tabs
    assert not list(folder.glob('*.db'))
    assert '_access_password' not in at.session_state or not at.session_state['_access_password']
    network.assert_not_called()
    sheet.assert_not_called()


def test_login_app_rerun_and_logout(isolated):
    folder, network, sheet = isolated
    at = sign_in(app().run())
    assert not at.exception
    assert len(at.tabs) == 5
    assert list(folder.glob('*.db'))
    assert '_access_password' not in at.session_state or not at.session_state['_access_password']
    at.run()
    assert not at.exception
    assert len(at.tabs) == 5
    next(b for b in at.button if b.label == 'Sign out').click().run()
    assert not at.exception
    assert not at.tabs
    assert '_access_token' not in at.session_state
    network.assert_not_called()


def test_password_rotation_revokes_session(isolated):
    at = sign_in(app().run())
    assert not at.exception
    at.secrets['APP_PASSWORD'] = PASSWORD + '-rotated'
    at.run()
    assert not at.exception
    assert not at.tabs


def functions():
    # Load function definitions without running the app or using real secrets.
    tree = ast.parse((ROOT / 'app.py').read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    for n in nodes:
        n.decorator_list = []
    import html
    import hashlib
    import re
    from urllib.parse import urlsplit
    ns = dict(hashlib=hashlib, pd=pd, requests=requests, json=json, html=html, re=re,
              sqlite3=sqlite3, urlsplit=urlsplit, require_authorized=Mock())
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'app.py', 'exec'), ns)
    return ns


@pytest.mark.parametrize('name,args', [
    ('init_db', ()), ('sync_data', (None, None)),
    ('get_audio_bytes', ('hello',)), ('fetch_sheet_data', ('https://example.test',)),
    ('clear_sheet_cache', ()),
    ('upsert_vocab_entry', (None, '', '', '', '', '', '', '')),
    ('update_score', (None, '', True)), ('save_note', (None, '', '')),
    ('autosave_note_from_state', ('', '', '')),
    ('call_gemini_dynamic', ('hello', 'fake-key')),
    ('get_azure_tts_audio_bytes', ('hello',)),
    ('append_vocab_entry_to_google_sheet', ('', '', '', '', '', '', '')),
])
def test_services_and_callbacks_check_access_before_side_effects(name, args):
    ns = functions()
    class Denied(BaseException):
        pass
    ns['require_authorized'].side_effect = Denied
    with pytest.raises(Denied):
        ns[name](*args)


def test_revoked_callback_stops_before_opening_db(monkeypatch):
    import access_control
    fake = Mock()
    fake.secrets = {'APP_PASSWORD': PASSWORD + '-rotated'}
    fake.session_state = {'_access_token': access_control._fingerprint(PASSWORD)}
    class Stopped(BaseException):
        pass
    fake.stop.side_effect = Stopped
    monkeypatch.setattr(access_control, 'st', fake)
    ns = functions()
    ns['require_authorized'] = access_control.require_authorized
    db = Mock()
    ns['sqlite3'] = db
    with pytest.raises(Stopped):
        ns['autosave_note_from_state']('word', 'text', 'note')
    db.connect.assert_not_called()


def test_gemini_key_only_in_header_and_normal_response(monkeypatch):
    ns = functions()
    get = Mock(return_value=Mock(status_code=200, json=lambda: {
        'models': [{'name':'models/gemini-flash', 'supportedGenerationMethods':['generateContent']}]}))
    post = Mock(return_value=Mock(status_code=200, json=lambda: {
        'candidates':[{'content':{'parts':[{'text':'answer'}]}}]}))
    monkeypatch.setattr(requests, 'get', get)
    monkeypatch.setattr(requests, 'post', post)
    assert ns['call_gemini_dynamic']('hello', 'fake-secret') == 'answer'
    for call in (get.call_args, post.call_args):
        assert 'fake-secret' not in call.args[0]
        assert call.kwargs['headers']['x-goog-api-key'] == 'fake-secret'
        assert call.kwargs['allow_redirects'] is False


def test_provider_body_is_not_in_error(monkeypatch):
    ns = functions()
    monkeypatch.setattr(requests, 'get', Mock(return_value=Mock(status_code=403, text='fake-secret')))
    with pytest.raises(Exception, match='HTTP 403') as exc:
        ns['call_gemini_dynamic']('hello', 'fake-secret')
    assert 'fake-secret' not in str(exc.value)


@pytest.mark.parametrize('url,secret', [('https://example.test/exec', ''), ('http://example.test/exec', 'fake-secret')])
def test_sheet_missing_secret_or_plain_http_never_sends(monkeypatch, url, secret):
    ns = functions()
    ns.update(SHEET_APPEND_WEBHOOK_URL=url, SHEET_APPEND_SECRET=secret)
    post = Mock()
    monkeypatch.setattr(requests, 'post', post)
    ok, _ = ns['append_vocab_entry_to_google_sheet'](*(['word'] * 7))
    assert not ok
    post.assert_not_called()


def test_sheet_success_does_not_echo_server_payload(monkeypatch):
    ns = functions()
    ns.update(SHEET_APPEND_WEBHOOK_URL='https://example.test/exec', SHEET_APPEND_SECRET='fake-secret')
    monkeypatch.setattr(requests, 'post', Mock(return_value=Mock(status_code=200, json=lambda: {'ok':True, 'message':'fake-secret'})))
    ok, message = ns['append_vocab_entry_to_google_sheet'](*(['word'] * 7))
    assert ok
    assert 'fake-secret' not in message


def test_security_configuration():
    config = tomllib.loads((ROOT / '.streamlit/config.toml').read_text())
    assert config['server']['enableCORS'] is True
    assert config['server']['enableXsrfProtection'] is True
    import re
    dev = json.loads(re.sub(r'^\s*//.*$', '', (ROOT / '.devcontainer/devcontainer.json').read_text(), flags=re.M))
    cmd = dev['postAttachCommand']['server']
    assert '--server.address 127.0.0.1' in cmd
    assert '--server.enableCORS true' in cmd
    assert '--server.enableXsrfProtection true' in cmd
    assert dev['portsAttributes']['8501']['onAutoForward'] == 'notify'


def test_authorized_local_progress_and_notes(tmp_path):
    ns = functions()
    ns['DB_NAME'] = str(tmp_path / 'progress.db')
    conn = ns['init_db']()
    ns['upsert_vocab_entry'](conn, 'Lesson', 'شلونك', 'shlonak', 'How are you?', '', '', '')
    word_id = conn.execute('SELECT id FROM vocab').fetchone()[0]
    assert ns['update_score'](conn, word_id, True) == 1
    ns['save_note'](conn, word_id, "learner's note")
    assert conn.execute('SELECT notes FROM vocab').fetchone()[0] == "learner's note"
    conn.close()


@pytest.mark.parametrize('status,location', [(307, 'https://evil.test'), (302, 'http://script.googleusercontent.com/x'), (302, 'https://evil.test')])
def test_sheet_never_forwards_secret_on_unsafe_redirect(monkeypatch, status, location):
    ns = functions()
    ns.update(SHEET_APPEND_WEBHOOK_URL='https://script.google.com/macros/s/test/exec', SHEET_APPEND_SECRET='fake-secret')
    post = Mock(return_value=Mock(status_code=status, headers={'Location':location}))
    get = Mock()
    monkeypatch.setattr(requests, 'post', post)
    monkeypatch.setattr(requests, 'get', get)
    ok, _ = ns['append_vocab_entry_to_google_sheet'](*(['word'] * 7))
    assert not ok
    assert post.call_args.kwargs['allow_redirects'] is False
    get.assert_not_called()


def test_apps_script_response_redirect_uses_get_without_secret(monkeypatch):
    ns = functions()
    ns.update(SHEET_APPEND_WEBHOOK_URL='https://script.google.com/macros/s/test/exec', SHEET_APPEND_SECRET='fake-secret')
    monkeypatch.setattr(requests, 'post', Mock(return_value=Mock(status_code=302, headers={'Location':'https://script.googleusercontent.com/response'})))
    get = Mock(return_value=Mock(status_code=200, json=lambda: {'ok':True}))
    monkeypatch.setattr(requests, 'get', get)
    assert ns['append_vocab_entry_to_google_sheet'](*(['word'] * 7))[0]
    assert get.call_args.kwargs == {'timeout':30, 'allow_redirects':False}
    assert 'fake-secret' not in str(get.call_args)


@pytest.mark.parametrize('name,cache_name', [
    ('get_audio_bytes', '_cached_audio_bytes'),
    ('fetch_sheet_data', '_cached_sheet_data'),
])
def test_cached_services_recheck_access_before_cached_result(name, cache_name):
    ns = functions()
    cached = Mock(return_value='cached-result')
    ns[cache_name] = cached
    assert ns[name]('word') == 'cached-result'
    class Denied(BaseException):
        pass
    ns['require_authorized'].side_effect = Denied
    with pytest.raises(Denied):
        ns[name]('word')
    cached.assert_called_once_with('word')


@pytest.mark.parametrize('field', range(8))
def test_sheet_formula_fields_rejected_before_request(monkeypatch, field):
    ns = functions()
    ns.update(SHEET_APPEND_WEBHOOK_URL='https://script.google.com/macros/s/test/exec',
              SHEET_APPEND_SECRET='fake-secret')
    post = Mock()
    monkeypatch.setattr(requests, 'post', post)
    values = ['word'] * 8
    values[field] = ' \t=IMPORTDATA("https://example.test")'
    ok, message = ns['append_vocab_entry_to_google_sheet'](*values)
    assert not ok
    assert 'plain text' in message
    post.assert_not_called()


def test_azure_ssml_escaping_and_no_redirect(monkeypatch):
    import xml.etree.ElementTree as ET
    ns = functions()
    ns.update(AZURE_SPEECH_KEY='fake-secret', AZURE_SPEECH_REGION='eastus',
              AZURE_SPEECH_VOICE="voice' /><audio src='https://example.test")
    post = Mock(return_value=Mock(status_code=200, content=b'audio'))
    monkeypatch.setattr(requests, 'post', post)
    assert ns['get_azure_tts_audio_bytes']('<hello>&') == b'audio'
    call = post.call_args
    assert call.kwargs['allow_redirects'] is False
    root = ET.fromstring(call.kwargs['data'])
    assert len(list(root.iter())) == 2
    assert root[0].text == '<hello>&'
    assert root[0].attrib['name'] == ns['AZURE_SPEECH_VOICE']


@pytest.mark.parametrize('region', ['eastus.evil.test/', 'eastus@evil.test', 'https://evil.test'])
def test_azure_invalid_region_never_sends(monkeypatch, region):
    ns = functions()
    ns.update(AZURE_SPEECH_KEY='fake-secret', AZURE_SPEECH_REGION=region,
              AZURE_SPEECH_VOICE='ar-KW-FahedNeural')
    post = Mock()
    monkeypatch.setattr(requests, 'post', post)
    with pytest.raises(ValueError, match='region'):
        ns['get_azure_tts_audio_bytes']('hello')
    post.assert_not_called()


@pytest.mark.parametrize('url', [
    'https://[broken', 'https://example.test:invalid/exec',
    'https://user:password@example.test/exec', 'https://example.test:8443/exec',
])
def test_malformed_sheet_endpoint_fails_closed(monkeypatch, url):
    ns = functions()
    ns.update(SHEET_APPEND_WEBHOOK_URL=url, SHEET_APPEND_SECRET='fake-secret')
    post = Mock()
    monkeypatch.setattr(requests, 'post', post)
    assert not ns['append_vocab_entry_to_google_sheet'](*(['word'] * 7))[0]
    post.assert_not_called()


def test_populated_flashcard_escapes_html_and_refresh_still_works(isolated, monkeypatch):
    import gtts
    _, network, sheet = isolated
    sheet.return_value = pd.DataFrame([{
        'Chapter': '<img src=x onerror=alert(1)>',
        'ArabicScript': '<script>alert(1)</script>',
        'EnglishMeaning': 'test word',
    }])
    monkeypatch.setattr(gtts, 'gTTS', Mock())
    at = sign_in(app().run())
    assert not at.exception
    rendered = '\n'.join(m.value for m in at.markdown)
    assert '&lt;img src=x onerror=alert(1)&gt;' in rendered
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in rendered
    assert '<script>alert(1)</script>' not in rendered
    next(b for b in at.button if b.label == 'Refresh Reference Datasets').click().run()
    assert not at.exception
    assert len(at.tabs) == 5
    network.assert_not_called()

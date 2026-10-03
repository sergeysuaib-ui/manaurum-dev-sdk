"""The shell contract that lives in the static files.

Everything here fails ONLY inside the Manaurum desktop, which is why it is
worth a test: the standalone URL looks perfectly healthy in all of the failure
modes below, so "I opened it in my browser" proves nothing.

* Lose `app.css` (or its `<link>`) and the app still works and ships unstyled.
* Lose the inline handshake and the shell shows "App is not responding"
  instead of your UI after 10 seconds.
* Lose the `data-appearance` write and the app stops following the OS between
  light and dark — it silently follows the *browser* instead.
* Lose the `lang`/`dir` write and the app ignores the language the person
  chose in ManAurum; a Hebrew reader gets an English, left-to-right window.

NOTE THE `_code()` HELPER, and keep it. The first version of this file
asserted against the raw file text and TWO mutations survived: index.html
explains the handshake and the theme message in its comments, so
`"manaurum:ready" in html` stayed true after the actual postMessage call was
deleted. The test was reading prose. Assert against code only.

Every assertion here has been checked by breaking the thing it covers and
confirming it goes red. If you edit these files, do that again — a test you
have not seen fail is a test you do not have.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)

_STATIC = Path(__file__).parent.parent / "src" / "static"
_INDEX_RAW = (_STATIC / "index.html").read_text(encoding="utf-8")

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
# Only comments that OWN their line — so `https://…` mid-line survives.
_JS_LINE_COMMENT = re.compile(r"^[ \t]*//.*$", re.MULTILINE)


def _code(html: str) -> str:
    """index.html with its explanatory comments removed."""
    return _JS_LINE_COMMENT.sub("", _HTML_COMMENT.sub("", html))


_INDEX = _code(_INDEX_RAW)


def test_stylesheet_is_actually_served():
    """A `<link>` to a path the container does not serve is an unstyled app."""
    response = client.get("/app.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert len(response.content) > 1000


def test_index_links_the_stylesheet_it_ships():
    """Guards the rename: moving app.css without updating the href leaves a
    200 on the file and a blank-looking app in the window."""
    hrefs = _hrefs(_INDEX)
    assert "/app.css" in hrefs
    for href in hrefs:
        assert client.get(href).status_code == 200, f"{href} is linked but not served"


def test_handshake_is_answered_from_inline_head_script():
    """The reply must be a real postMessage, and must precede the bundle.

    An SPA whose only listener lives inside a module bundle can miss
    `manaurum:init` entirely — the shell posts it as soon as the iframe loads.
    """
    replies = re.findall(r"type:\s*'manaurum:ready'", _INDEX)
    assert replies, "no manaurum:ready postMessage payload in the document"
    assert _INDEX.index("manaurum:ready") < _INDEX.index('<script type="module">'), (
        "the handshake reply must precede the module bundle"
    )


def test_handshake_trusts_the_shell_not_the_first_sender():
    """MAN-2506: act on `manaurum:*` only from the parent window, and only
    from the shell's own origins.

    Every v2 app can be framed by another `*.manaurum.com` page. A listener
    that answers whoever posts `manaurum:init` hands that page the app's
    appearance and its `manaurum:ready`, and manaurum-v2.mjs 2.3.0 adopts
    every `init` sender as its shell. The guard has to run before the init
    branch, drop what it refuses, and be registered before the SDK's listener.
    It lets exactly `manaurum:session-*` through, for Core's injected session
    runtime, and nothing broader.
    """
    assert "'https://manaurum.com'" in _INDEX and "'https://app.manaurum.com'" in _INDEX
    assert "*.manaurum.com'" not in _INDEX, "a wildcard origin admits every app"
    guard = re.search(r"event\.source\s*===\s*window\.parent", _INDEX)
    assert guard, "no check that the message came from the parent window"
    assert re.search(r"event\.source\s*!==\s*window\b", _INDEX), (
        "a page posting to itself is its own parent when not framed")
    assert "SHELL_ORIGINS.indexOf(event.origin)" in _INDEX
    assert "stopImmediatePropagation" in _INDEX, (
        "a refused message must not reach later listeners (the SDK's)")
    assert guard.start() < _INDEX.index("=== 'manaurum:init'"), (
        "the sender check must run before init is handled")
    # The loopback exception admits the page's own origin and nothing else.
    assert "SHELL_ORIGINS.push(location.origin)" in _INDEX
    assert not re.search(r"SHELL_ORIGINS\.push\(\s*'\*'", _INDEX)
    # The only pass-through is Core's session channel.
    passes = re.findall(r"indexOf\('(manaurum:[^']*)'\)\s*===\s*0\)\s*return;", _INDEX)
    assert passes == ["manaurum:session-"], passes
    # Registered before anything that could listen for `message` after it.
    assert guard.start() < _INDEX.index('<script type="module">')
    assert "postMessage({ type: 'manaurum:ready' }, '*')" not in _INDEX


def test_appearance_comes_from_the_shell_not_only_the_browser():
    """The shell's appearance must reach the DOM, on init AND on change.

    `prefers-color-scheme` alone tracks the browser, so a user in OS dark mode
    with a light browser profile would get a light app inside a dark desktop.
    """
    assert re.search(r"===\s*'manaurum:theme-change'", _INDEX), (
        "no live handler for manaurum:theme-change — the app would not follow "
        "the OS when the user switches appearance while it is open"
    )
    assert re.search(r"dataset\.appearance\s*=", _INDEX), (
        "appearance is never written to the DOM"
    )


def test_the_language_comes_from_the_shell_on_init_and_on_change():
    """The person's language reaches <html lang dir>, on init AND on a switch.

    The shell sends `locale` and `dir` in `manaurum:init` and posts
    `manaurum:locale-change` whenever the person changes language;
    manaurum-v2.mjs 2.3.0 passes neither on, so the inline listener is the
    only thing that applies them. Without `dir` a Hebrew screen is laid out
    left to right; without the change handler one window stays in the old
    language until it is reopened.
    """
    body = re.search(r"function applyShellLocale\(payload\)\s*\{(.*?)\n    \}", _INDEX, re.S)
    assert body, "no applyShellLocale(payload) in the inline listener"
    code = body.group(1)
    assert "payload.locale" in code and "payload.dir" in code, (
        "the language is not read off the payload")
    assert re.search(r"root\.lang\s*=\s*locale", code), "<html lang> is never written"
    assert re.search(r"root\.dir\s*=\s*dir", code), "<html dir> is never written"
    assert re.search(r"window\.__manaurum\.locale\s*=", code)

    init = _INDEX.index("=== 'manaurum:init'")
    change = re.search(r"===\s*'manaurum:locale-change'", _INDEX)
    assert change, "no live handler for manaurum:locale-change"
    calls = [m.start() for m in re.finditer(r"applyShellLocale\(payload\)", _INDEX)]
    assert any(init < c < change.start() for c in calls), "init never applies the language"
    assert any(c > change.start() for c in calls), "a language switch is never applied"
    assert "new CustomEvent('manaurum-locale')" in _INDEX
    # The sender check still runs first: a stranger cannot switch the language.
    assert re.search(r"event\.source\s*===\s*window\.parent", _INDEX).start() < change.start()


def test_the_standalone_tab_guesses_from_the_browser():
    """No shell, no OS language: the browser's languages, mapped to ours."""
    body = re.search(r"function applyBrowserLocale\(\)\s*\{(.*?)\n    \}", _INDEX, re.S)
    assert body, "no standalone default for the language"
    assert "navigator.language" in body.group(1)
    table = re.search(r"var LOCALE_DIR = \{([^}]*)\}", _INDEX)
    assert table and re.findall(r"(\w+): '(ltr|rtl)'", table.group(1)) == [
        ("en", "ltr"), ("ru", "ltr"), ("he", "rtl")]


def _catalogue(locale: str) -> list[str]:
    block = re.search(r"\n    %s: \{\n(.*?)\n    \}," % locale, _INDEX, re.S)
    assert block, f"no {locale} catalogue in STRINGS"
    return re.findall(r"'([\w.]+)':\s*'", block.group(1))


def test_every_catalogue_has_every_key():
    """en, ru and he carry the same keys, and every key the page uses exists.

    A missing key reads as English at run time, which is the bug this
    prevents: a Hebrew screen with one English sentence in the middle.
    """
    en, ru, he = _catalogue("en"), _catalogue("ru"), _catalogue("he")
    assert len(en) > 10 and len(set(en)) == len(en), "duplicate keys in en"
    assert set(ru) == set(en), sorted(set(en) ^ set(ru))
    assert set(he) == set(en), sorted(set(en) ^ set(he))
    used = set(re.findall(r'data-i18n(?:-placeholder)?="([\w.]+)"', _INDEX))
    used |= set(re.findall(r"\b(?:t|say\(\w+,)\s*\(?\s*'([a-z]+\.[\w.]+)'", _INDEX))
    assert used, "nothing on the page is translated"
    assert used <= set(en), sorted(used - set(en))


def test_numbers_and_dates_use_the_os_tags():
    """Intl gets the same BCP-47 tags as the OS (frontend/src/i18n/config.ts)."""
    assert "const INTL_LOCALE = { en: 'en', ru: 'ru-RU', he: 'he-IL' };" in _INDEX
    assert "new Intl.NumberFormat(INTL_LOCALE[" in _INDEX
    assert "new Intl.DateTimeFormat(" in _INDEX


def test_stylesheet_mirrors_for_right_to_left():
    """No physical left/right in app.css: under dir="rtl" it would not mirror."""
    css = re.sub(r"/\*.*?\*/", "", (_STATIC / "app.css").read_text(encoding="utf-8"), flags=re.S)
    physical = re.findall(r"\b(?:margin|padding|border)-(?:left|right)\b|"
                          r"text-align:\s*(?:left|right)\b|float:\s*(?:left|right)\b", css)
    assert not physical, physical


def test_stylesheet_defeats_the_hidden_attribute():
    """`[hidden]` is only the browser's default; any author `display` rule beats
    it. Without an explicit override, `el.hidden = true` silently does nothing
    and an empty state renders stacked on top of the list it should replace.
    This shipped once; keep the guard."""
    css = (_STATIC / "app.css").read_text(encoding="utf-8")
    assert re.search(r"\[hidden\]\s*\{[^}]*display:\s*none\s*!important", css)


def test_every_view_has_a_url():
    """A view reachable only by clicking is a view nothing can check.

    The desktop cannot deep-link into it, the back button does nothing, and a
    headless screenshot — which cannot click — never gets past the first
    screen, so every UI check you run only ever sees the home view.
    """
    views = re.findall(r'data-view="([a-z0-9-]+)"', _INDEX)
    assert len(views) >= 2, "no second view: the router has nothing to route"
    assert "hashchange" in _INDEX, "views exist but the URL never selects one"


def test_clickable_rows_are_list_items_that_say_they_are_clickable():
    """`<button class="row">` is the obvious guess and it is wrong.

    A button brings ButtonFace, its own border, Arial over the tokens and a
    width that hugs its content, so the list stops reaching the card edge —
    which is what an owner saw and rejected. And a row with a handler but no
    `is-interactive` has no cursor, no hover and no focus ring.
    """
    assert not re.search(r'<button[^>]*class="[^"]*\brow\b', _INDEX), (
        "a list row is <li class=\"row is-interactive\">, never a <button>"
    )
    assert "'row is-interactive'" in _INDEX or '"row is-interactive"' in _INDEX, (
        "rows are built without is-interactive — a silent click target"
    )


def test_the_ui_linter_is_clean():
    """The contract in `templates/check_ui.py`, run against this app.

    Skipped in a copied app that did not take the linter along; in the SDK
    repo it guards the starter itself, which is what every app is copied from.
    """
    import subprocess
    import sys

    linter = Path(__file__).resolve().parents[2] / "check_ui.py"
    if not linter.exists():                                   # pragma: no cover
        import pytest

        pytest.skip("check_ui.py not alongside this template — copy it from the plugin's templates/")
    done = subprocess.run([sys.executable, str(linter), str(_STATIC)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def _hrefs(html: str) -> list[str]:
    """Every root-relative href in the document."""
    return [h for h in re.findall(r'href="([^"]+)"', html) if h.startswith("/")]

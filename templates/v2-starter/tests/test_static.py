"""The shell contract that lives in the static files.

Everything here fails ONLY inside the Manaurum desktop, which is why it is
worth a test: the standalone URL looks perfectly healthy in all of the failure
modes below, so "I opened it in my browser" proves nothing.

* Lose `app.css` (or its `<link>`) and the app still works and ships unstyled.
* Lose the inline handshake and the shell shows "App is not responding"
  instead of your UI after 10 seconds.
* Lose the `data-appearance` write and the app stops following the OS between
  light and dark — it silently follows the *browser* instead.

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

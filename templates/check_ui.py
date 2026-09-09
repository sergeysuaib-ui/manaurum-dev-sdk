#!/usr/bin/env python3
"""Mechanical check of a v2 app's UI against the platform contract.

Every rule here is one that has already reached an owner and been rejected -
and none of them is visible in a green deploy, in the tests, or in the diff.
A rule a program checks is the only kind that survives an agent in a hurry.

Standard library only. Run it BEFORE the screenshots in Step 3.5: it is
cheaper, and it catches what a picture cannot show (a hex hidden in a var()
fallback, a class the shell will never style, a missing handshake).

    python check_ui.py src/static

Exit code: 0 clean, 1 problems found, 2 could not run.

A stylesheet is where colours live: `*.css` files and `<style>` blocks are
scanned for the tokens they DECLARE, and are exempt from the "no hex in the
markup" rule. Everything else - attributes, scripts, template strings - is
markup.

The rules come from `manaurum-app/references/design.md` (the `Never` table and
the token table) and from the seven rules in `manaurum-app/SKILL.md`. If a
finding looks wrong, fix the rule here rather than working around it in the
app: a linter nobody trusts is worse than no linter.

Output is deliberately ASCII, because a Windows console renders anything else
as mojibake and an unreadable finding is an ignored finding.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ── What we look for ────────────────────────────────────────────────────────
# A 6- or 8-digit hex is a colour wherever it appears. A 3- or 4-digit one is
# only a colour in a colour context: this skill now teaches a URL fragment per
# view, so `location.hash === '#add'` and `href="#fed"` are ordinary code, and
# a linter that calls them hardcoded colours is a linter people switch off.
HEX_LONG = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6})(?![0-9a-fA-F])")
HEX_SHORT = re.compile(r"#[0-9a-fA-F]{3,4}(?![0-9a-fA-F])")
COLOUR_WORD = re.compile(
    r"\b(colou?r|background|border|fill|stroke|shadow|gradient|outline|accent|"
    r"theme|palette)\b", re.I)
RGBA = re.compile(r"\brgba?\s*\(")
VAR_USE = re.compile(r"var\(\s*(--[a-z0-9-]+)")
VAR_DECL = re.compile(r"(--[a-z0-9-]+)\s*:")
# `style="width:42%"` on a progress bar is legitimate and cannot be a token;
# `style="color:#333"` is the rule being broken. Only the second is a finding.
STYLE_ATTR_COLOUR = re.compile(
    r"""\sstyle\s*=\s*(?P<q>["'])(?P<body>[^"']*)(?P=q)""")
STYLE_PROP = re.compile(r"\.style\.[a-zA-Z]")
MODALS = re.compile(r"\b(alert|confirm|prompt)\s*\(")
BANNED_CLASS = re.compile(r'class="[^"]*\b(tabs?|sidebar)\b')
MEDIA_WIDTH = re.compile(r"@media[^{]*max-width")
BUTTON_ROW = re.compile(r'<button[^>]*class="[^"]*\brow\b')
PRIMARY = re.compile(r"btn-primary")
ROW_INTERACTIVE = re.compile(r'class="row(?![^"]*is-interactive)[^"]*"[^>]*(?:data-id|onclick)')
VIEW_SPLIT = re.compile(r"data-view\s*=")

# Anchors are not colours. `href="#card"` must not read as a hardcoded hex,
# especially now that the skill teaches a URL fragment per view.
HREF_FRAGMENT = re.compile(r'href\s*=\s*"#[^"]*"')

STYLE_BLOCK = re.compile(r"<style[^>]*>.*?</style>", re.S)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
# Trailing `//` comments too, but never the `//` in `https://`.
LINE_COMMENT = re.compile(r"(?m)(?<![:\\])//[^\n]*$")

CHECKED_SUFFIXES = (".html", ".htm", ".js", ".mjs")


def strip_comments(text: str) -> str:
    """Comments are not code.

    Without this, the sentence "never call confirm()" inside a comment is
    itself a finding - which is how the first run of this linter failed.
    """
    text = HTML_COMMENT.sub("", text)
    text = BLOCK_COMMENT.sub("", text)
    return LINE_COMMENT.sub("", text)


def style_blocks(text: str) -> list:
    """`<style>` bodies, or nothing.

    The guard is not paranoia: `<style[^>]*>.*?</style>` backtracks
    quadratically over a file with `<style` tags and no closing one - measured
    at 2.4s for 64KB and minutes for a large page.
    """
    return STYLE_BLOCK.findall(text) if "</style>" in text else []


def without_style_blocks(text: str) -> str:
    return STYLE_BLOCK.sub("", text) if "</style>" in text else text


def short_hex_colours(text: str) -> list:
    """3/4-digit hex sitting in a colour context, not a URL fragment."""
    out = []
    for match in HEX_SHORT.finditer(text):
        window = text[max(0, match.start() - 40):match.end() + 10]
        if COLOUR_WORD.search(window):
            out.append(match.group(0))
    return out


def declared_tokens(static_dir: Path) -> set:
    """Every custom property the app declares, wherever it keeps them."""
    names = set()
    for css in sorted(static_dir.rglob("*.css")):
        names |= set(VAR_DECL.findall(css.read_text(encoding="utf-8", errors="replace")))
    for page in sorted(static_dir.rglob("*.htm*")):
        for block in style_blocks(page.read_text(encoding="utf-8", errors="replace")):
            names |= set(VAR_DECL.findall(block))
    return names


def check(static_dir: Path) -> list:
    problems = []
    declared = declared_tokens(static_dir)

    # A var() whose token does not exist is a hardcoded value wearing a
    # token's clothes - and a STYLESHEET can do it too. The reference
    # stylesheet in this very plugin shipped `var(--container-lg, 1024px)`
    # with that name declared nowhere, and this linter did not see it because
    # it only read `.css` files for what they DECLARE.
    for path in sorted(static_dir.rglob("*.css")):
        name = str(path.relative_to(static_dir)).replace("\\", "/")
        css = BLOCK_COMMENT.sub("", path.read_text(encoding="utf-8", errors="replace"))
        for var in sorted(set(VAR_USE.findall(css))):
            if var not in declared:
                problems.append(
                    "%s: var(%s) is declared nowhere in this app - the fallback quietly "
                    "becomes a hardcoded value" % (name, var))
        # A media query lives in a stylesheet, and the loop below reads only
        # .html/.js - so until 2.10.0 this rule could not fire at all on the
        # one file type that carries it. Found by a mutation, not by reading.
        if MEDIA_WIDTH.search(css):
            problems.append("%s: @media max-width - branch on body[data-device], which is "
                            "what the shell actually reports" % name)

    sources = [p for p in sorted(static_dir.rglob("*"))
               if p.is_file() and p.suffix in CHECKED_SUFFIXES
               and ".min." not in p.name]

    for path in sources:
        name = str(path.relative_to(static_dir)).replace("\\", "/")
        text = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        # Stylesheets are exempt from the colour rules and only from those.
        markup = HREF_FRAGMENT.sub("", without_style_blocks(text))

        for var in sorted(set(VAR_USE.findall(text))):
            if var not in declared:
                problems.append(
                    "%s: var(%s) is declared nowhere in this app - the fallback quietly "
                    "becomes a hardcoded value" % (name, var))
        for match in sorted(set(HEX_LONG.findall(markup))):
            problems.append("%s: hex %s in markup - use a token" % (name, match))
        for match in sorted(set(short_hex_colours(markup))):
            problems.append("%s: hex %s in markup - use a token" % (name, match))
        if RGBA.search(markup):
            problems.append("%s: rgba() in markup - use a token" % name)
        if any(COLOUR_WORD.search(m.group("body")) or HEX_LONG.search(m.group("body"))
               for m in STYLE_ATTR_COLOUR.finditer(markup)):
            problems.append("%s: a colour in a style= attribute - an inline colour "
                            "cannot follow an appearance change" % name)
        if STYLE_PROP.search(text):
            problems.append("%s: element.style.* assignment - same as style=; toggle a "
                            "class instead" % name)
        if MODALS.search(text):
            problems.append("%s: alert/confirm/prompt - the shell's iframe has no "
                            "allow-modals, so they return silently" % name)
        if BANNED_CLASS.search(text):
            problems.append("%s: a tab/tabs/sidebar class - an app window is not a "
                            "browser window; stack sections as cards" % name)
        if MEDIA_WIDTH.search(text):
            problems.append("%s: @media max-width - branch on body[data-device], which is "
                            "what the shell actually reports" % name)
        if BUTTON_ROW.search(text):
            problems.append('%s: <button class="row"> - a list row is <li class="row '
                            'is-interactive">; a button falls back to ButtonFace, Arial '
                            'and its own width' % name)
        if ROW_INTERACTIVE.search(text):
            problems.append("%s: a row with a click target but no is-interactive - no "
                            "hover, no cursor, no focus ring" % name)

    entry = static_dir / "index.html"
    if not entry.exists():
        problems.append("index.html is missing - frontend.entry_point has nothing to point at")
        return problems

    html = strip_comments(entry.read_text(encoding="utf-8", errors="replace"))

    # One primary action per VIEW, not per file: a hash-routed app keeps every
    # view in index.html, and each view is allowed its own primary button.
    worst = max((len(PRIMARY.findall(chunk)) for chunk in VIEW_SPLIT.split(html)), default=0)
    if worst > 1:
        problems.append("index.html: %d primary buttons in one view - one per view, and "
                        "never one per row" % worst)

    if "manaurum:ready" not in html:
        problems.append("index.html: no manaurum:ready - after 10s the shell covers the "
                        'app with "App is not responding"')
    if "data-appearance" not in html and "dataset.appearance" not in html:
        problems.append("index.html: appearance from manaurum:init is never written onto "
                        "<html> - the app will sit in its own palette inside a dark desktop")
    if "dataset.device" not in html and "data-device" not in html:
        problems.append("index.html: device from the shell is never written - every "
                        "body[data-device=\"mobile\"] rule in app.css is dead")
    if "payload" not in html:
        problems.append("index.html: nothing reads `payload` - appearance and accent "
                        "arrive in e.data.payload, not on the message root")
    return problems


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "src/static")
    if not target.is_dir():
        print("not a directory: %s - pass the directory that holds index.html" % target)
        return 2

    problems = check(target)
    for problem in problems:
        print("x %s" % problem)
    print("%d problem(s)" % len(problems) if problems else "clean")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

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
# A colour set from script is the same finding as one in style=. Geometry is
# not: `el.style.width = pct + "%"` on a progress bar cannot be a token, and
# `style.setProperty("--x", ...)` sets a token. Only colour properties count.
STYLE_PROP = re.compile(
    r"\.style\.(color|background(?:Color|Image)?|border\w*Color|fill|stroke|"
    r"boxShadow|outlineColor|textShadow|cssText)\b"
    r"|\.style\.setProperty\(\s*['\"](?!--)(color|background[\w-]*|border[\w-]*color|"
    r"fill|stroke|box-shadow)")
# The global functions, not a method that happens to share the name:
# `ui.confirm(...)` is the in-app dialog the skill tells you to use instead.
MODALS = re.compile(r"(?:(?<![\w.$])|\b(?:window|globalThis|self)\.)(alert|confirm|prompt)\s*\(")
SCRIPT_BLOCK = re.compile(r"<script[^>]*>(.*?)</script>", re.S | re.I)
# Inline handlers are script too: <button onclick="return confirm('Delete?')">.
INLINE_HANDLER = re.compile(r"""\son[a-z]+\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""", re.I)
# The shell's appearance written onto the document...
APPEARANCE_WRITE = re.compile(
    r"(?:dataset\.appearance\s*=(?!=)|setAttribute\(\s*['\"]data-appearance['\"]\s*,)"
    r"[^;\n]*")
# ...from a value read off the payload: `payload.appearance`, or destructured,
# `const { appearance } = payload`. The write's own `dataset.appearance =` is
# not a read, which is what keeps the `prefers-color-scheme` fallback out.
# `dataset.appearance` is the document's own value, not the payload's: a
# fallback that reads it (`if (!root.dataset.appearance) ...`) applies nothing.
APPEARANCE_READ = re.compile(r"(?<!dataset)\.appearance\b(?!\s*=(?!=))|"
                             r"\{[^{}]*\bappearance\b[^{}]*\}\s*(?:=|\)|,)")
# The person's language, the same shape (3.16.0): `lang` and `dir` written onto
# the document - `root.lang = ...`, `document.documentElement.dir = ...`,
# `setAttribute('dir', ...)` - from `locale` / `dir` read off the payload. The
# document's own values (`root.dir`, `documentElement.lang`) are not the
# payload's, so a standalone guess from `navigator.languages` applies nothing;
# and the starter's copy on `window.__manaurum` is neither the document nor
# the payload - counting `__manaurum.dir = dir` as the write let an app that
# never set <html dir> pass (found by a mutation).
LANG_WRITE = re.compile(r"(?:(?<!__manaurum)\.lang\s*=(?!=)|setAttribute\(\s*['\"]lang['\"]\s*,)[^;\n]*")
DIR_WRITE = re.compile(r"(?:(?<!__manaurum)\.dir\s*=(?!=)|setAttribute\(\s*['\"]dir['\"]\s*,)[^;\n]*")
LOCALE_READ = re.compile(
    r"(?<!\broot)(?<!documentElement)(?<!__manaurum)\.(?:locale|dir)\b(?!\s*=(?!=))|"
    r"\{[^{}]*\b(?:locale|dir)\b[^{}]*\}\s*(?:=|\)|,)")
# Left and right in a stylesheet are the reading direction, and Hebrew reads
# the other way: under <html dir="rtl"> these do not mirror. `left:` /
# `right:` positioning is not here - centring a toast with `left: 50%` is
# direction-neutral, and a linter that flags it is a linter people switch off.
PHYSICAL_PROPERTY = re.compile(r"(margin|padding|border)-(left|right)(-(?:width|style|color))?")
PHYSICAL_VALUE = {"text-align": "text-align: start / end", "float": "float: inline-start / inline-end",
                  "clear": "clear: inline-start / inline-end"}
# A function: declared by name, bound to a name, or anonymous. An anonymous
# one, or a named one written where an argument goes (`addEventListener(
# 'message', function onMessage(e) {...})`), runs when it is passed.
FUNCTION_DEF = re.compile(
    r"function\s+([A-Za-z_$][\w$]*)\s*\(|"
    r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?"
    r"(?:function\b|\([^()]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)|"
    r"function\s*\(|(?:\([^()]*\)|[A-Za-z_$][\w$]*)\s*=>")
BANNED_CLASS = re.compile(r'class="[^"]*\b(tabs?|sidebar)\b')
MEDIA_WIDTH = re.compile(r"@media[^{]*max-width")
BUTTON_ROW = re.compile(r'<button[^>]*class="[^"]*\brow\b')
PRIMARY = re.compile(r"btn-primary")
ROW_INTERACTIVE = re.compile(r'class="row(?![^"]*is-interactive)[^"]*"[^>]*(?:data-id|onclick)')
VIEW_SPLIT = re.compile(r"data-view\s*=")
# Accent is a pointer (design.md -> "Accent is a pointer, not a paint"). These
# classes paint a thing in the accent. `.chip.is-on` is accent too, but
# toggling it in a loop over the chips is exactly the right pattern - only the
# selected one ends up coloured - so it is not on this list. From PR #27.
ACCENT_CLASS = re.compile(r"\b(btn-primary|btn-ghost|badge-accent)\b")
ACCENT_BUDGET = 4
# Inside a loop, what paints: `className = 'btn btn-ghost'`, `classList.add(
# 'badge-accent')`, a `class="..."` template. What does not: a selector
# (`querySelector('.btn-primary')` - the class follows a dot), a
# `classList.remove(...)`, and `classList.toggle(cls, condition)`, which puts
# the class on the items the condition picks - the chip pattern. A one-argument
# toggle flips it onto every item that lacked it, so that one still counts.
PAINTED_ACCENT = re.compile(r"(?<![\w.-])(btn-primary|btn-ghost|badge-accent)\b")
NOT_PAINTING = re.compile(r"classList\.remove\s*\([^)]*\)|"
                          r"classList\.toggle\s*\(\s*[^,()]+,[^)]*\)")
LOOP_HEAD = re.compile(r"\bfor\s*\(|\bwhile\s*\(|\.(?:forEach|map|flatMap)\s*\(")

# Anchors are not colours. `href="#card"` must not read as a hardcoded hex,
# especially now that the skill teaches a URL fragment per view.
HREF_FRAGMENT = re.compile(r'href\s*=\s*"#[^"]*"')

STYLE_BLOCK = re.compile(r"<style[^>]*>.*?</style>", re.S)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
# Trailing `//` comments too, but never the `//` in `https://`.
LINE_COMMENT = re.compile(r"(?m)(?<![:\\])//[^\n]*$")

CHECKED_SUFFIXES = (".html", ".htm", ".js", ".mjs")

# Geometry of the page root. A leaf CSS rule is `selector { declarations }`
# with no brace inside; an @media wrapper is simply skipped over, which is
# what we want - a cap set under a media query is still a cap.
CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
CSS_DECL = re.compile(r"([a-z-]+)\s*:\s*([^;]+)")
BODY_OPEN = re.compile(r"<body\b[^>]*>", re.I)
FIRST_TAG = re.compile(r"<([a-zA-Z][a-zA-Z0-9-]*)\b([^>]*)>")
NOT_LAYOUT = frozenset(("script", "noscript", "template", "style", "link", "meta"))
ATTR_CLASS = re.compile(r"""\bclass\s*=\s*["']([^"']*)["']""")
ATTR_ID = re.compile(r"""\bid\s*=\s*["']([^"']*)["']""")
BODY_SELECTOR = re.compile(r"body(?:[.\[:#][^\s>+~]*)?")
NO_CAP = frozenset(("none", "100%", "100vw", "initial", "unset", "inherit", "revert"))


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


def closing(text: str, start: int, open_ch: str, close_ch: str) -> int:
    """Index just past the bracket that closes the one before `start`."""
    depth, i = 1, start
    while i < len(text) and depth:
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
        i += 1
    return i


def loop_bodies(js: str) -> list:
    """The code a loop repeats: `for (...) {...}` or a `.map(...)` callback.

    Brace counting, not a parser - a brace inside a string can fool it. It is
    good enough for the question asked: does a render loop hand out accent.
    """
    bodies = []
    for head in LOOP_HEAD.finditer(js):
        after = closing(js, head.end(), "(", ")")
        if head.group(0).startswith("."):
            bodies.append(js[head.end():after])
            continue
        rest = js[after:].lstrip()
        start = len(js) - len(rest)
        if rest.startswith("{"):
            bodies.append(js[start:closing(js, start + 1, "{", "}")])
        else:
            end = js.find(";", start)
            bodies.append(js[start:end if end >= 0 else len(js)])
    return bodies


def declared_tokens(static_dir: Path) -> set:
    """Every custom property the app declares, wherever it keeps them."""
    names = set()
    for css in sorted(static_dir.rglob("*.css")):
        names |= set(VAR_DECL.findall(css.read_text(encoding="utf-8", errors="replace")))
    for page in sorted(static_dir.rglob("*.htm*")):
        for block in style_blocks(page.read_text(encoding="utf-8", errors="replace")):
            names |= set(VAR_DECL.findall(block))
    return names


def root_hooks(html: str) -> set:
    """The `.class` / `#id` handles of the element that holds the whole page.

    That is the first layout element inside `<body>` - `.app` in the starter.
    Only its geometry is judged: a `max-width` deeper in the page (a paragraph
    in an empty state, a toast) is centred or not by its parent's layout, and
    a linter that second-guesses every one of them is a linter people switch
    off. A cap on a wrapper one level further down is not seen - that is the
    price of staying quiet, and the wide screenshot in Step 3.5 is what covers it.
    """
    opened = BODY_OPEN.search(html)
    if not opened:
        return set()
    for tag in FIRST_TAG.finditer(html, opened.end()):
        if tag.group(1).lower() in NOT_LAYOUT:
            continue
        attrs = tag.group(2)
        hooks = set()
        for cls in (ATTR_CLASS.search(attrs) or [None, ""])[1].split():
            hooks.add("." + cls)
        ident = ATTR_ID.search(attrs)
        if ident and ident.group(1).strip():
            hooks.add("#" + ident.group(1).strip())
        return hooks
    return set()


def css_rules(static_dir: Path) -> list:
    """(file, selector, {property: value}) for every leaf rule the app ships."""
    out = []
    sheets = [(p, BLOCK_COMMENT.sub("", p.read_text(encoding="utf-8", errors="replace")))
              for p in sorted(static_dir.rglob("*.css"))]
    for page in sorted(static_dir.rglob("*.htm*")):
        text = page.read_text(encoding="utf-8", errors="replace")
        sheets += [(page, BLOCK_COMMENT.sub("", re.sub(r"</?style[^>]*>", "", block)))
                   for block in style_blocks(text)]
    for path, css in sheets:
        name = str(path.relative_to(static_dir)).replace("\\", "/")
        for selector, body in CSS_RULE.findall(css):
            decls = {prop.lower(): value.replace("!important", "").strip()
                     for prop, value in CSS_DECL.findall(body)}
            out.append((name, selector.strip(), decls))
    return out


def targets(selector: str, hooks) -> bool:
    """Does any comma-separated part of the selector END on one of the hooks?

    `body[data-device="mobile"] .app` targets `.app`; `.app .card` does not.
    """
    for part in selector.split(","):
        compounds = re.split(r"[\s>+~]+", part.strip())
        last = compounds[-1] if compounds else ""
        for hook in hooks:
            if re.search(re.escape(hook) + r"(?![\w-])", last):
                return True
    return False


def centres_itself(decls: dict) -> bool:
    """margin auto on both sides, in any of the ways CSS lets you say it."""
    margin = decls.get("margin", "").split()
    if margin and (margin[0] == "auto" if len(margin) == 1
                   else margin[1] == "auto" and (len(margin) < 4 or margin[3] == "auto")):
        return True
    inline = decls.get("margin-inline", "").split()
    if inline and all(v == "auto" for v in inline):
        return True
    # The fixed-position trick: left 50% and pulled back by half its width.
    return (decls.get("left") == "50%"
            and re.search(r"translate(?:x)?\(\s*-50%", decls.get("transform", ""), re.I)
            is not None)


def uncentred_cap(static_dir: Path, html: str) -> list:
    """A capped page root that nothing centres (MAN-2849).

    Below the cap, a centred and an uncentred root are pixel-identical, so
    every screenshot at or under 1024px passes it; above the cap the app is
    glued to the left edge with dead space on the right. The starter shipped
    exactly that, and four apps copied it verbatim.
    """
    hooks = root_hooks(html)
    if not hooks:
        return []
    rules = css_rules(static_dir)
    mine = [(name, decls) for name, sel, decls in rules if targets(sel, hooks)]
    caps = [(name, decls["max-width"]) for name, decls in mine
            if decls.get("max-width", "none").lower() not in NO_CAP]
    if not caps:
        return []
    union = {}
    for _, decls in mine:
        union.update(decls)
    if centres_itself(union) or (union.get("margin-left") == "auto"
                                 and union.get("margin-right") == "auto"):
        return []
    # Or the parent does it: <body> as a flex/grid container that centres.
    body = {}
    for _, sel, decls in rules:
        if any(BODY_SELECTOR.fullmatch(part.strip()) for part in sel.split(",")):
            body.update(decls)
    if (body.get("display", "") in ("flex", "inline-flex", "grid")
            and any("center" in body.get(prop, "") for prop in
                    ("justify-content", "align-items", "place-items",
                     "justify-items", "place-content"))):
        return []
    name, value = caps[0]
    hook = sorted(hooks)[0]
    return ["%s: %s caps its width (max-width: %s) and nothing centres it - in any "
            "window wider than that the app sits on the left edge with dead space "
            "on the right. Add `margin-inline: auto`" % (name, hook, value)]


def applies_shell_appearance(html: str) -> bool:
    """Is `payload.appearance` written onto the document, by code that runs?

    The substring `dataset.appearance` was the whole check until 3.7.0, and
    the starter's standalone fallback (`prefers-color-scheme`) always
    contains it: deleting every call that applies the shell's value left the
    check green. So: a write whose function (or the write itself) reads
    `.appearance` off something, and, when it sits in a named function, that
    function used somewhere else - called, or passed by name, as in
    `addEventListener('message', onShellMessage)`.
    """
    return written_from_payload(html, APPEARANCE_WRITE, APPEARANCE_READ)


def written_from_payload(html: str, write, read) -> bool:
    """Is a value read off the payload written onto the document, by code that
    runs? The shape `applies_shell_appearance` describes, for any pair."""
    for match in write.finditer(html):
        definitions = list(FUNCTION_DEF.finditer(html, 0, match.start()))
        start = definitions[-1].start() if definitions else 0
        if not read.search(html, start, match.end()):
            continue
        if not definitions:
            return True
        name = definitions[-1].group(1) or definitions[-1].group(2)
        before = html[:definitions[-1].start()].rstrip()[-1:]
        if not name or before in ("(", ","):
            return True                   # passed where it is written
        uses = len(re.findall(r"(?<![\w$.])%s\b" % re.escape(name), html))
        if uses > 1:                      # the definition itself is one
            return True
    return False


def applies_shell_language(html: str) -> list:
    """What of the shell's language never reaches <html lang dir> (3.16.0).

    `lang` is what a screen reader and the browser's hyphenation and fonts
    follow; `dir` is what mirrors the page for Hebrew. An app that applies the
    locale and not the direction is a Hebrew screen laid out left to right.
    Both come from the payload, on `manaurum:init`, and again on
    `manaurum:locale-change`, which the shell posts whenever the person
    switches language while the window is open.
    """
    missing = [name for name, write in (("lang", LANG_WRITE), ("dir", DIR_WRITE))
               if not written_from_payload(html, write, LOCALE_READ)]
    if missing:
        return ["index.html: the language from manaurum:init is never written onto "
                "<html %s> - read payload.locale and payload.dir and set both, or the "
                "app ignores the language the person chose in ManAurum%s"
                % (" ".join(missing),
                   "; without dir a Hebrew screen is laid out left to right"
                   if "dir" in missing else "")]
    if "manaurum:locale-change" not in html:
        return ["index.html: no manaurum:locale-change - when the person switches "
                "language the app stays in the old one until the window is reopened"]
    return []


def physical_directions(static_dir: Path) -> list:
    """Left/right in a stylesheet that will not mirror under dir="rtl".

    A rule that sets both sides to the same value (`margin-left: auto;
    margin-right: auto`) mirrors trivially and is not a finding.
    """
    problems, seen = [], set()
    for name, selector, decls in css_rules(static_dir):
        for prop, value in decls.items():
            match = PHYSICAL_PROPERTY.fullmatch(prop)
            if match:
                flip = "right" if match.group(2) == "left" else "left"
                other = "%s-%s%s" % (match.group(1), flip, match.group(3) or "")
                if decls.get(other) == value:
                    continue
                side = "start" if match.group(2) == "left" else "end"
                logical = "%s-inline-%s%s" % (match.group(1), side, match.group(3) or "")
                found = prop
            elif prop in PHYSICAL_VALUE and value.lower() in ("left", "right"):
                logical = PHYSICAL_VALUE[prop]
                found = "%s: %s" % (prop, value.lower())
            else:
                continue
            if (name, found) in seen:
                continue
            seen.add((name, found))
            problems.append(
                "%s: `%s` in `%s` does not mirror when the person reads Hebrew "
                "(dir=\"rtl\") - use %s" % (name, found, " ".join(selector.split()), logical))
    return problems


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
    problems += physical_directions(static_dir)

    sources =[p for p in sorted(static_dir.rglob("*"))
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
            problems.append("%s: a colour set through element.style - same as style=; "
                            "toggle a class or set a token instead" % name)
        code = text
        if path.suffix == ".html":
            code = "\n".join(SCRIPT_BLOCK.findall(text) + [
                "".join(m.groups(default="")) for m in INLINE_HANDLER.finditer(text)])
        if MODALS.search(code):
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
        # Only code has loops: in an .html file that is the scripts and the
        # inline handlers, so "for (example)" in a paragraph is not one.
        looped = sorted({m.group(1) for body in loop_bodies(code)
                         for m in PAINTED_ACCENT.finditer(NOT_PAINTING.sub("", body))})
        if looped:
            problems.append("%s: an accent class (%s) set inside a loop - one per item "
                            "is a column of accent. A repeated control is a .chip "
                            "(quiet until selected) or .btn-secondary; a repeated "
                            "status is a neutral .badge" % (name, ", ".join(looped)))

    entry = static_dir / "index.html"
    if not entry.exists():
        problems.append("index.html is missing - frontend.entry_point has nothing to point at")
        return problems

    html = strip_comments(entry.read_text(encoding="utf-8", errors="replace"))

    # Elements, not mentions: a class counts where it sits in a `class="..."`
    # value of the markup. A `<style>` block that styles `.btn-primary`, or a
    # script that names it in a selector, puts nothing on the screen.
    markup_only = without_style_blocks(SCRIPT_BLOCK.sub("", html) if "</script>" in html
                                       else html)
    chunks = [" ".join(ATTR_CLASS.findall(chunk))
              for chunk in VIEW_SPLIT.split(markup_only)]

    # One primary action per VIEW, not per file: a hash-routed app keeps every
    # view in index.html, and each view is allowed its own primary button.
    worst = max((len(PRIMARY.findall(chunk)) for chunk in chunks), default=0)
    if worst > 1:
        problems.append("index.html: %d primary buttons in one view - one per view, and "
                        "never one per row" % worst)

    # Accent is a pointer. One primary button is not enough if every ghost
    # button and badge beside it is accent too - that is how a screen with no
    # broken rule ended up with twenty accent-coloured things on it (PR #27).
    # The budget is per FIRST SCREEN, and what comes before the first view (a
    # page header) is on screen with every view, so it counts towards each.
    # Only the static markup is counted here; preview.py counts the rendered
    # frame, and the loop rule above covers what a script hands out.
    shared = len(ACCENT_CLASS.findall(chunks[0])) if chunks else 0
    views = chunks[1:] or [""]
    loudest = shared + max(len(ACCENT_CLASS.findall(chunk)) for chunk in views)
    if loudest > ACCENT_BUDGET:
        problems.append("index.html: %d accent-coloured elements (btn-primary, btn-ghost, "
                        "badge-accent) on one view's first screen, counting what sits "
                        "above the views - %d at most; filters are .chip, secondary "
                        "actions .btn-secondary" % (loudest, ACCENT_BUDGET))

    if "manaurum:ready" not in html:
        problems.append("index.html: no manaurum:ready - after 10s the shell covers the "
                        'app with "App is not responding"')
    if not applies_shell_appearance(html):
        problems.append("index.html: appearance from manaurum:init is never written onto "
                        "<html> - the app will sit in its own palette inside a dark desktop")
    if "dataset.device" not in html and "data-device" not in html:
        problems.append("index.html: device from the shell is never written - every "
                        "body[data-device=\"mobile\"] rule in app.css is dead")
    if "payload" not in html:
        problems.append("index.html: nothing reads `payload` - appearance and accent "
                        "arrive in e.data.payload, not on the message root")
    problems += applies_shell_language(html)
    problems += uncentred_cap(static_dir, html)
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

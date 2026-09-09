#!/usr/bin/env python3
"""Mechanical check that this plugin still describes itself accurately.

Every rule here corresponds to something that was actually wrong on `main`
and that nobody noticed, because nothing re-measures. A plugin whose whole
job is to keep an agent honest had no way to check itself: a version string
in four files with three different values, a reference stylesheet breaking
the rule its own table names, a README quoting a test count from two
releases ago, a "blocked on MAN-1393" that had been Done for months.

None of it is serious alone. Together it is the SDK lying about itself, and
an agent has no way to tell which sentence is the stale one.

Standard library only, no network. Run it from the repository root:

    python scripts/check_repo.py            # every check, exit 1 on findings
    python scripts/check_repo.py --tickets  # the ticket review list, exit 0

Exit code: 0 clean, 1 problems found, 2 could not run.

Findings are printed as `path:line: message` and ALWAYS name a file first,
because a red build that does not say where is a red build somebody reruns.

Output is deliberately ASCII: a Windows console renders anything else as
mojibake, and an unreadable finding is an ignored finding.

WHAT IS DELIBERATELY NOT HERE. Anything needing a browser (the screenshots
in Step 3.5) or a network (whether MAN-1393 is Done today). The ticket check
below is the compromise: a claim that some ticket is still open has to be
written down in `scripts/open-claims.txt` with the date it was last
verified, and CI prints the list every run so a human can re-check it.
"""

from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ── What counts as a live document ──────────────────────────────────────────
# CHANGELOG.md is history: it is SUPPOSED to say "19 tests" in the entry for
# the release that had 19 tests, and to name tickets that have since closed.
# Checking it for present-tense accuracy would be checking the past.
LIVE_DOCS = ["README.md"]

# ── Patterns ────────────────────────────────────────────────────────────────
VERSION = re.compile(r"(\d+\.\d+\.\d+)")
README_VERSION = re.compile(r"\*\*Version\s+(\d+\.\d+\.\d+)")
CHANGELOG_VERSION = re.compile(r"(?m)^#\s+(\d+\.\d+\.\d+)")
SKILL_VERSION = re.compile(r"This page is SDK\s+(\d+\.\d+\.\d+)")

# A repository path, as the docs write one: inside backticks, optionally
# prefixed with the `<plugin>/` placeholder the skill uses.
REPO_PATH = re.compile(
    r"`(?:<plugin>/)?((?:templates|skills|scripts|references|hooks)/[A-Za-z0-9._/-]+)`")

# `file.md` § "Heading" / `file.md` -> "Heading". Only the QUOTED form is
# checked: `v2-platform.md § 3` and `§ Manifest reference` are prose pointing
# at a numbered section, not a citation of a literal heading.
SECTION_REF = re.compile(
    r"`([A-Za-z0-9._/-]+\.md)`\s*(?:§|→|->)\s*(?:\"([^\"]+)\"|\*([^*]+)\*)")
SAME_FILE_SECTION = re.compile(r"(?:§|→)\s*\*([^*]+)\*")
STEP_REF = re.compile(r"\bStep (\d+(?:\.\d+)?)\b")
STEP_HEADING = re.compile(r"(?m)^#{1,4}\s+Step (\d+(?:\.\d+)?)\b")
HEADING = re.compile(r"(?m)^#{1,6}\s+(.*)$")

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}
WORD_OF = {value: word for word, value in NUMBER_WORDS.items()}
COUNT = r"(\d+|%s)" % "|".join(NUMBER_WORDS)

TEST_COUNT = re.compile(r"(?i)\b%s\s+tests\b" % COUNT)
# "fifteen checks", "Ten rules over your static files", "fails on nine of them".
# `the seven rules` is exempt here and checked against the list itself below:
# that one IS a list on the page, so the number is computable rather than
# merely asserted.
LINTER_COUNT = re.compile(
    r"(?i)(?<!the )\b%s\s+(?:checks|rules)\b|\b%s\s+of\s+(?:them|the)\b" % (COUNT, COUNT))
LINTER_NAME = re.compile(r"check_(?:ui|app)\.py")
RULES_HEADING = re.compile(r"(?i)^#{1,4}\s+The (\w+) rules an app gets sent back for")
RULES_PHRASE = re.compile(r"(?i)\bthe (\w+) rules\b")
NUMBERED_ITEM = re.compile(r"(?m)^(\d+)\.\s")

# `/tmp/ctx.tar` is a fixed path in a shared directory: two sessions
# deploying at the same moment overwrite each other's build context, and the
# second one ships the first one's app (MAN-2456).
TMP_PATH = re.compile(r"(?i)(?<!not )(?<!not `)/tmp/[A-Za-z0-9_.+-]+")

TICKET = re.compile(r"\bMAN-(\d+)\b")
# Deliberately narrow. A bare "deferred" or "still" catches a script bundle
# that is deferred and a version that still has an archive - noise, and noise
# is how a check gets switched off. These are the phrasings that actually
# assert something about the OUTSIDE world's state.
PENDING_CLAIM = re.compile(
    r"(?i)\b(not yet\b|not in any released\b|"
    r"still (?:open|pending|blocked|missing|unreleased|not\b|404s)|"
    r"open (?:decision|question)\b|once (?:it|the)\b|catches up\b|blocked on\b|"
    r"in review\b|(?:is|are|remains?) deferred\b|tracked (?:as|in)\b|"
    r"is being (?:rebuilt|ported|written)\b|has not (?:landed|shipped)\b)")
# A table row is its own claim: a "deferred" three rows up says nothing about
# the ticket on this one.
TABLE_ROW = re.compile(r"^\s*(?:\||>?\s*\|)")
SENTENCE_END = re.compile(r"(?<=[.!?;])\s+")

ADD_ARGUMENT = re.compile(r"""add_argument\(\s*["'](--[a-z][a-z0-9-]*)""")
# A documented invocation of one of this repo's own tools, in a shell block.
TOOL_CALL = re.compile(
    r"(?m)^\s*(?:py(?:thon)?3?)\s+\S*?((?:check_ui|check_app|preview|version_check)\.py)"
    r"([^\n]*)$")
LONG_FLAG = re.compile(r"(--[a-z][a-z0-9-]*)")

SKIP_DIRS = (".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
             "node_modules", ".venv", "venv")
# A control byte is invisible in every editor and in the diff. On 2026-09-09
# a shell heredoc turned the `\b` of a word-boundary regex into a literal
# 0x08 in a sibling module: the regex stopped matching, the file still looked
# right, and nothing failed - it just quietly checked nothing.
ALLOWED_CONTROL = {0x09, 0x0a, 0x0d}

# ── Facts that live in two files at once ────────────────────────────────────
# Each of these was measured once and written down twice. The failure mode is
# not that one copy is missing - it is that one copy says the OPPOSITE of the
# other, and the reader believes whichever one they opened. Step 3.5 told
# people to SHORTEN --virtual-time-budget to catch a loading state; Chrome
# pauses virtual time during a fetch, so no budget is short enough, and
# preview.py's own docstring said so.
PAIRED_CLAIMS = [
    ("--virtual-time-budget",
     ["templates/preview.py", "skills/manaurum-app/SKILL.md"],
     re.compile(r"(?i)(without\s+`?--virtual-time-budget|drop the flag)"),
     "must say the flag is DROPPED, not shortened, to photograph a loading "
     "state - Chrome pauses virtual time while a request is in flight"),
    ("headless viewport floor",
     ["templates/preview.py", "skills/manaurum-app/SKILL.md"],
     re.compile(r"(?i)floor[^.]{0,120}500px"),
     "must state the ~500px headless layout-viewport floor, or a reader will "
     "shrink the window instead of using ?width="),
]

# ── Artifacts that have to carry their own correction ───────────────────────
STARTER = "templates/v2-starter"
REQUIRED_IGNORES = {
    STARTER + "/.gitignore": [
        (".env.manaurum",
         "the token file the skill tells you to create - `.env` alone does not "
         "cover it, and there is no way to un-leak it"),
        ("__pycache__/x.pyc", "byte-code"),
    ],
    STARTER + "/.dockerignore": [
        (".env.manaurum", "credentials must never enter a local build context"),
        (".env", "credentials must never enter a local build context"),
    ],
}
DOCKERIGNORE_CAVEAT = re.compile(r"(?i)does not apply \.dockerignore")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def source_files() -> list:
    """Every file in the working tree that a human or a tool reads."""
    out = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(ROOT).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        out.append(path)
    return out


def live_docs() -> list:
    """The documents that make present-tense claims about this repository."""
    paths = [ROOT / name for name in LIVE_DOCS]
    paths += sorted((ROOT / "skills").rglob("*.md"))
    return [p for p in paths if p.is_file()]


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def normalise(title: str) -> str:
    """A heading and a citation of it, reduced to the same string.

    A citation wraps in a line, and both sides sprinkle backticks. Comparing
    them raw produced findings like `no heading matching "window\\nrules"`,
    which is the linter being wrong in public - the fastest way to teach
    everybody to ignore it.
    """
    return re.sub(r"\s+", " ", title.replace("`", "").replace("*", "")).strip().lower()


# ── Checks ──────────────────────────────────────────────────────────────────


def check_versions(problems: list) -> None:
    """One version, four files.

    2.8.0 shipped with `**Version 2.7.3**` in the README. Nobody reading the
    README could tell which of the two numbers was the lie, and the plugin
    cache is keyed on the real one.
    """
    sources = [
        (".claude-plugin/plugin.json", VERSION, '"version"'),
        ("README.md", README_VERSION, "**Version X.Y.Z**"),
        ("CHANGELOG.md", CHANGELOG_VERSION, "the newest `# X.Y.Z` heading"),
        ("skills/manaurum-app/SKILL.md", SKILL_VERSION, "This page is SDK X.Y.Z"),
    ]
    found = {}
    for name, pattern, what in sources:
        path = ROOT / name
        if not path.exists():
            problems.append("%s:1: missing - the version lives here too (%s)" % (name, what))
            continue
        text = read(path)
        if name == ".claude-plugin/plugin.json":
            match = re.search(r'"version"\s*:\s*"(\d+\.\d+\.\d+)"', text)
        else:
            match = pattern.search(text)
        if not match:
            problems.append("%s:1: no version found - expected %s" % (name, what))
            continue
        found[name] = (match.group(1), line_of(text, match.start()))

    if len(found) < 2:
        return
    authority = found.get(".claude-plugin/plugin.json")
    if authority is None:
        return
    for name, (version, line) in sorted(found.items()):
        if version != authority[0]:
            problems.append(
                "%s:%d: says version %s, but .claude-plugin/plugin.json says %s"
                % (name, line, version, authority[0]))


def check_doc_paths(problems: list) -> None:
    """A path a document names has to exist.

    The docs are the map an agent navigates by. A `templates/…` that is not
    there does not read as a stale document - it reads as a broken checkout,
    and the agent writes the file itself instead (which is how a stylesheet
    gets re-derived without its guards).
    """
    for doc in live_docs():
        text = read(doc)
        for match in REPO_PATH.finditer(text):
            target = match.group(1).rstrip("/")
            if any(ch in target for ch in "*<>…"):
                continue
            # The docs name files by a partial path and let the reader
            # resolve it: `references/design.md` from inside the references
            # directory, `manaurum-deploy/SKILL.md` from another skill.
            # These are the roots a reader would try.
            roots = [ROOT, doc.parent, doc.parent.parent, ROOT / "skills",
                     ROOT / "skills" / "manaurum-app"]
            if not any((root / target).exists() for root in roots):
                problems.append("%s:%d: `%s` does not exist"
                                % (rel(doc), line_of(text, match.start()), target))


def check_section_refs(problems: list) -> None:
    """A quoted section citation has to resolve to a real heading."""
    docs = {rel(p): read(p) for p in live_docs()}
    headings = {name: [normalise(h) for h in HEADING.findall(text)]
                for name, text in docs.items()}

    def resolve(target_name: str, from_doc: str):
        for name in headings:
            if name.endswith("/" + target_name) or name == target_name:
                return name
        return None

    for name, text in sorted(docs.items()):
        for match in SECTION_REF.finditer(text):
            target_file = match.group(1)
            title = normalise(match.group(2) or match.group(3) or "")
            resolved = resolve(target_file, name)
            if resolved is None:
                continue          # check_doc_paths owns a missing file
            if not any(title in h for h in headings[resolved]):
                problems.append('%s:%d: `%s` has no heading matching "%s"'
                                % (name, line_of(text, match.start()), target_file, title))


def check_step_refs(problems: list) -> None:
    """"See Step 3.5" has to have a Step 3.5 to see.

    The numbered steps ARE the contract - the whole reason 2.9.0 promoted the
    UI check into one. A dangling step reference is a mandatory step that no
    longer exists under the number people were told to look for.
    """
    app_skill = ROOT / "skills/manaurum-app/SKILL.md"
    if not app_skill.exists():
        problems.append("skills/manaurum-app/SKILL.md:1: missing")
        return
    canonical = set(STEP_HEADING.findall(read(app_skill)))
    for doc in live_docs():
        text = read(doc)
        own = set(STEP_HEADING.findall(text))
        for match in STEP_REF.finditer(text):
            step = match.group(1)
            if step in own or step in canonical:
                continue
            problems.append(
                "%s:%d: refers to Step %s, which is not a heading here or in "
                "skills/manaurum-app/SKILL.md"
                % (rel(doc), line_of(text, match.start()), step))


# NOTE: this file deliberately does NOT count the starter's tests. Counting
# `def test_` gives 25 where pytest collects 27, because two are parametrised
# - and a checker whose whole point is that quoted numbers drift has no
# business inventing a second number. CI prints `pytest --collect-only -q`.


def check_self_counts(problems: list) -> None:
    """A number the docs quote about this repository.

    README said "19 tests" when there were 24, then 27. SKILL.md said the
    linter checked "nine of the seven rules"; the CHANGELOG said ten; there
    were fifteen. Nobody was careless - the number was simply in a different
    file from the thing it counted.

    Two ways out, and this check enforces both: either the number is computed
    (the count of rules in the list right below it), or the sentence does not
    quote a number at all.
    """
    for doc in live_docs():
        text = read(doc)
        for match in TEST_COUNT.finditer(text):
            problems.append(
                "%s:%d: a hardcoded test count (\"%s\") - the suite grows every "
                "release and this sentence does not; say what the tests cover, "
                "and let CI print the number"
                % (rel(doc), line_of(text, match.start()), match.group(0).strip()))

        for line_no, line in enumerate(text.splitlines(), start=1):
            if not LINTER_NAME.search(line):
                continue
            for match in LINTER_COUNT.finditer(line):
                problems.append(
                    "%s:%d: a hardcoded count of what the linter checks (\"%s\") - "
                    "checks are added without touching this sentence; describe "
                    "what it covers instead"
                    % (rel(doc), line_no, match.group(0).strip()))

    # The seven rules, on the other hand, ARE a list on the page - so the
    # word in the heading is checkable against the list under it.
    skill = ROOT / "skills/manaurum-app/SKILL.md"
    if not skill.exists():
        return
    text = read(skill)
    lines = text.splitlines()
    declared = None
    for index, line in enumerate(lines):
        match = RULES_HEADING.match(line)
        if not match:
            continue
        declared = (match.group(1).lower(), index + 1)
        body = []
        for rest in lines[index + 1:]:
            if rest.startswith("#"):
                break
            body.append(rest)
        actual = len(NUMBERED_ITEM.findall("\n".join(body) + "\n"))
        want = NUMBER_WORDS.get(declared[0])
        if want is None:
            problems.append("skills/manaurum-app/SKILL.md:%d: heading says "
                            "\"%s rules\", which is not a number" % (declared[1], declared[0]))
        elif want != actual:
            problems.append(
                "skills/manaurum-app/SKILL.md:%d: heading says \"%s rules\" but %d "
                "are listed under it - rename the heading to \"%s\""
                % (declared[1], declared[0], actual, WORD_OF.get(actual, str(actual))))
        break

    if declared is None:
        return
    for doc in live_docs():
        body = read(doc)
        for match in RULES_PHRASE.finditer(body):
            word = match.group(1).lower()
            if word not in NUMBER_WORDS or word == declared[0]:
                continue
            problems.append(
                "%s:%d: says \"the %s rules\" while skills/manaurum-app/SKILL.md "
                "heads that list \"The %s rules an app gets sent back for\""
                % (rel(doc), line_of(body, match.start()), word, declared[0]))


def check_control_bytes(problems: list) -> None:
    """A byte no editor shows and no diff highlights.

    This is not hypothetical: a heredoc turned `\\b` into a literal 0x08
    inside a regex on 2026-09-09. The pattern silently stopped matching, the
    file looked correct on screen, and every test still passed - because the
    check the regex performed now matched nothing at all.
    """
    for path in source_files():
        if path.suffix in (".png", ".jpg", ".gif", ".ico", ".pyc", ".gz", ".tar"):
            continue
        data = path.read_bytes()
        for offset, byte in enumerate(data):
            if byte == 0x7f or (byte < 0x20 and byte not in ALLOWED_CONTROL):
                problems.append(
                    "%s:%d: control byte 0x%02x at offset %d - invisible in an "
                    "editor and in the diff; rewrite the file with a real editor, "
                    "not a shell heredoc"
                    % (rel(path), data.count(b"\n", 0, offset) + 1, byte, offset))
                break


def check_tmp_paths(problems: list) -> None:
    """A fixed path under /tmp is a collision waiting for a second session.

    Both skills taught `/tmp/ctx.tar` and `/tmp/deploy.json`. On 2026-09-08
    two sessions deploying at once crossed build contexts and one app was
    published over another (MAN-2456).
    """
    for doc in live_docs():
        text = read(doc)
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "mktemp" in line or "TMPDIR" in line:
                continue
            for match in TMP_PATH.finditer(line):
                problems.append(
                    "%s:%d: fixed path `%s` - /tmp is shared between sessions; "
                    "use a per-run `mktemp -d`"
                    % (rel(doc), line_no, match.group(0)))


def check_starter_hygiene(problems: list) -> None:
    """The starter is copied verbatim, so its ignore files are the rule.

    `.gitignore` listed `.env` and `.env.local` but not `.env.manaurum` - the
    one filename the skill instructs you to create, two paragraphs after
    explaining that a leaked deploy token cannot be un-leaked.
    """
    for name, required in sorted(REQUIRED_IGNORES.items()):
        path = ROOT / name
        if not path.exists():
            problems.append("%s:1: missing" % name)
            continue
        patterns = [line.strip().rstrip("/") for line in read(path).splitlines()
                    if line.strip() and not line.strip().startswith("#")]
        for filename, why in required:
            base = filename.rsplit("/", 1)[-1]
            covered = any(fnmatch.fnmatch(filename, pattern)
                          or fnmatch.fnmatch(base, pattern)
                          or fnmatch.fnmatch(filename, pattern + "/*")
                          for pattern in patterns)
            if not covered:
                problems.append("%s:1: nothing here matches `%s` - %s"
                                % (name, filename, why))

    dockerignore = ROOT / STARTER / ".dockerignore"
    if dockerignore.exists():
        text = read(dockerignore)
        if "migrations/" in text and not DOCKERIGNORE_CAVEAT.search(text):
            problems.append(
                "%s/.dockerignore:1: lists migrations/ without the note that a "
                "platform deploy never applies this file - a comment claiming an "
                "effect it does not have is worse than no comment" % STARTER)


def tool_flags(tool: str) -> set:
    """The long flags a tool in this repo actually accepts."""
    for candidate in (ROOT / "templates" / tool, ROOT / "scripts" / tool):
        if candidate.exists():
            return set(ADD_ARGUMENT.findall(read(candidate)))
    return set()


def check_documented_invocations(problems: list) -> None:
    """A command the docs print has to be one the tool accepts.

    Step 3.5 is a copy-paste step. A flag that no longer exists does not fail
    loudly - argparse exits 2 with a usage message, which reads like the app
    being checked is broken.
    """
    known = {}
    for doc in live_docs():
        text = read(doc)
        for match in TOOL_CALL.finditer(text):
            tool, rest = match.group(1), match.group(2)
            if tool not in known:
                known[tool] = tool_flags(tool)
            supported = known[tool]
            for flag in LONG_FLAG.findall(rest):
                if flag not in supported:
                    problems.append(
                        "%s:%d: `%s %s` - %s does not accept %s"
                        % (rel(doc), line_of(text, match.start()), tool, flag.strip(),
                           tool, flag))


def check_paired_claims(problems: list) -> None:
    """A measured fact written down twice has to say the same thing twice."""
    for label, files, required, why in PAIRED_CLAIMS:
        present = []
        for name in files:
            path = ROOT / name
            if not path.exists():
                problems.append("%s:1: missing - it is one of the two places that "
                                "carry the %s fact" % (name, label))
                continue
            present.append((name, read(path)))
        if not any(label.split()[0] in text or label in text for _, text in present):
            continue
        for name, text in present:
            if not required.search(text):
                problems.append("%s:1: %s - %s" % (name, label, why))


def open_claims_file() -> dict:
    """`scripts/open-claims.txt`, parsed. Empty if it is not there."""
    path = ROOT / "scripts" / "open-claims.txt"
    if not path.exists():
        return {}
    listed = {}
    for line_no, line in enumerate(read(path).splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = TICKET.match(line)
        if match:
            listed["MAN-" + match.group(1)] = (line, line_no)
    return listed


def claim_units(text: str):
    """Yield (sentence, offset) - the unit a ticket claim lives in.

    Not the paragraph: a manifest field table has no blank lines in it, so
    one row saying "the webhook gateway is deferred" made every ticket in the
    table read as pending. Not the line either: prose wraps at 80 columns and
    the marker is regularly on the line above the ticket.

    So: table rows stand alone, and everything else is joined per paragraph
    and split back into sentences.
    """
    offset = 0
    for block in re.split(r"(\n\s*\n)", text):
        if not block.strip():
            offset += len(block)
            continue
        if TABLE_ROW.match(block.lstrip("\n")):
            line_offset = offset
            for line in block.splitlines(keepends=True):
                yield line, line_offset
                line_offset += len(line)
        else:
            cursor = offset
            for piece in SENTENCE_END.split(block):
                index = text.find(piece, cursor)
                yield piece, index if index >= 0 else cursor
                cursor = (index if index >= 0 else cursor) + len(piece)
        offset += len(block)


def ticket_claims() -> tuple:
    """(pending claims, every mention) across the live docs.

    A claim is a sentence that both names a ticket and says something about
    it not being finished. That sentence is a promise about the outside
    world, and this repository has no way to re-check it - so it has to be
    written down where a human will look.
    """
    claims, mentions = {}, {}
    for doc in live_docs():
        text = read(doc)
        for unit, offset in claim_units(text):
            pending = PENDING_CLAIM.search(unit) is not None
            for match in TICKET.finditer(unit):
                ident = "MAN-" + match.group(1)
                where = (rel(doc), line_of(text, offset + match.start()))
                mentions.setdefault(ident, []).append(where)
                if pending:
                    claims.setdefault(ident, []).append(where)
    return claims, mentions


def check_tickets(problems: list) -> None:
    claims, mentions = ticket_claims()
    listed = open_claims_file()

    for ident, places in sorted(claims.items()):
        if ident in listed:
            continue
        doc, line = places[0]
        problems.append(
            "%s:%d: claims %s is still open - add it to "
            "scripts/open-claims.txt with the date you checked, so the claim "
            "has somewhere to be re-checked" % (doc, line, ident))

    for ident, (line, line_no) in sorted(listed.items()):
        if ident not in mentions:
            problems.append(
                "scripts/open-claims.txt:%d: %s is listed but no live document "
                "mentions it any more - drop the line" % (line_no, ident))


def print_tickets() -> None:
    """The review list. Nothing offline can tell you MAN-1393 closed."""
    claims, _ = ticket_claims()
    listed = open_claims_file()
    if not claims:
        print("No document claims a ticket is still open.")
        return
    print("Tickets the docs claim are still open - re-check these in Linear:")
    print("")
    for ident, places in sorted(claims.items()):
        note = listed.get(ident, (ident + "  (not listed)", 0))[0]
        print("  %s" % note.strip())
        for doc, line in sorted(set(places)):
            print("      %s:%d" % (doc, line))
    print("")
    print("MAN-1393 sat in README.md as \"blocked\" for months after it was Done.")


CHECKS = (
    check_versions,
    check_doc_paths,
    check_section_refs,
    check_step_refs,
    check_self_counts,
    check_control_bytes,
    check_tmp_paths,
    check_starter_hygiene,
    check_documented_invocations,
    check_paired_claims,
    check_tickets,
)


def main() -> int:
    if "--tickets" in sys.argv[1:]:
        print_tickets()
        return 0
    if not (ROOT / ".claude-plugin" / "plugin.json").exists():
        print("not a manaurum-dev-sdk checkout: %s" % ROOT)
        return 2

    problems = []
    for check in CHECKS:
        check(problems)
    problems = sorted(set(problems))
    for problem in problems:
        print("x %s" % problem)
    print("%d problem(s)" % len(problems) if problems else "clean")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

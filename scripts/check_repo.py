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
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ── What counts as a live document ──────────────────────────────────────────
# CHANGELOG.md is history: it is SUPPOSED to say "19 tests" in the entry for
# the release that had 19 tests, and to name tickets that have since closed.
# Checking it for present-tense accuracy would be checking the past.
LIVE_DOCS = ["README.md", "templates/v2-starter/README.md"]

# Two files quote the documents at people: the SessionStart hook prints its
# text into a session's context, and the UI linter's docstring names the rule
# list. Rename a heading and those strings rot with nothing watching them.
DOC_QUOTING_SOURCES = ["scripts/version_check.py", "templates/check_ui.py",
                       "templates/check_app.py"]

# ── Patterns ────────────────────────────────────────────────────────────────
PLUGIN_VERSION = re.compile(r'"version"\s*:\s*"(\d+\.\d+\.\d+)"')
README_VERSION = re.compile(r"\*\*Version\s+(\d+\.\d+\.\d+)")
CHANGELOG_VERSION = re.compile(r"(?m)^#\s+(\d+\.\d+\.\d+)")
SKILL_VERSION = re.compile(r"This page is SDK\s+(\d+\.\d+\.\d+)")
STARTER_CSS_VERSION = re.compile(r"manaurum-starter app\.css\s+(\d+\.\d+\.\d+)")

# A repository path, as the docs write one: inside backticks, optionally
# prefixed with the `<plugin>/` placeholder the skill uses.
REPO_PATH = re.compile(
    r"`(?:<plugin>/)?((?:templates|skills|scripts|references|hooks)/[A-Za-z0-9._/-]+)`")

# `file.md` § "Heading" / `file.md` -> "Heading". Only the QUOTED form is
# checked: `v2-platform.md § 3` and `§ Manifest reference` are prose pointing
# at a numbered section, not a citation of a literal heading.
SECTION_REF = re.compile(
    r"`([A-Za-z0-9._/-]+\.md)`\s*(?:§|→|->)\s*(?:\"([^\"]+)\"|\*([^*]+)\*)")
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

# "27 tests", but NOT "write two tests for every capability" - the rule is
# about a count of THIS suite, and an instruction to the reader is not one.
# Digits are always a claim; a spelled-out number only counts when the line is
# talking about the suite.
TEST_COUNT = re.compile(r"(?i)\b%s\s+(?:tests|passed)\b" % COUNT)
TEST_SUBJECT = re.compile(r"(?i)\b(starter|suite|pytest|offline|its)\b")
TEST_IMPERATIVE = re.compile(r"(?i)\b(write|writing|add|adding|one|two|three)\b")
# "fifteen checks", "Ten rules over your static files", "fails on nine of them".
# `the seven rules` and `all seven rules` are exempt here and checked against
# the list itself below: that one IS a list on the page, so the number is
# computable rather than merely asserted. `N of the` is NOT a pattern here -
# it matched "one of the two ways a hex reaches the markup" and produced a
# finding that read as nonsense, which is how a checker gets switched off.
LINTER_COUNT = re.compile(
    r"(?i)(?<!the )(?<!all )\b%s\s+(?:checks|rules)\b|\b%s\s+of\s+them\b"
    % (COUNT, COUNT))
LINTER_NAME = re.compile(r"check_(?:ui|app)\.py")
RULES_HEADING = re.compile(r"(?i)^#{1,4}\s+The (\w+) rules an app gets sent back for")
RULES_PHRASE = re.compile(r"(?i)\bthe (\w+) rules\b")
NUMBERED_ITEM = re.compile(r"(?m)^(\d+)\.\s")

# `/tmp/ctx.tar` is a fixed path in a shared directory: two sessions
# deploying at the same moment overwrite each other's build context, and the
# second one ships the first one's app (MAN-2456).
#
# A path with a `$` in it is per-run and is the FIX, not the defect
# (`/tmp/ctx-$$.tar`). And the sentence teaching the lesson has to remain
# writable: "never write it to /tmp/ctx.tar" is not an instruction to do so.
TMP_PATH = re.compile(r"/tmp/[A-Za-z0-9_.+${}()-]+")
NEGATION = re.compile(r"(?i)\b(not|never|don't|do not|avoid|instead of|rather than)\b")
OTHERS_PROJECT = re.compile(r"(?i)\b(your|YOUR|the reader's|a generated) (project|app|repo)\b")

TICKET = re.compile(r"\bMAN-(\d+)\b")
CLAIM_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# Deliberately narrow. A bare "deferred" or "still" catches a script bundle
# that is deferred and a version that still has an archive - noise, and noise
# is how a check gets switched off. These are the phrasings that actually
# assert something about the OUTSIDE world's state.
PENDING_CLAIM = re.compile(
    r"(?i)\b(not yet\b|not in any released\b|in no released\b|"
    r"still (?:open|pending|blocked|missing|unreleased|not\b|404s)|"
    r"open (?:decision|question)\b|catches up\b|blocked on\b|"
    r"once (?:it|a release|the \w+) (?:lands|ships|closes|carries|catches)\b|"
    r"in review\b|(?:is|are|remains?) deferred\b|tracked as\b|"
    r"is being (?:rebuilt|ported|written)\b|has not (?:landed|shipped)\b)")
# A sentence that says the work IS done vetoes the marker in it. "MAN-2532 is
# Done, but it was blocked on a runner for two days" is a history, not a
# claim - and a checker that demands a register entry for a closed ticket
# fills that register with closed tickets, which is the opposite of the point.
# The lookbehinds are the whole trick: without them "has not landed" vetoed
# itself on the word `landed` and the claim went unregistered - the check
# switched off by the sentence it exists to catch.
RESOLVED_CLAIM = re.compile(
    r"(?i)(?<!not )(?<!n't )(?<!never )\b(is Done|was (?:merged|shipped|closed|fixed)"
    r"|shipped|landed|merged|closed|was rebuilt)\b")
# A table row is its own claim: a "deferred" three rows up says nothing about
# the ticket on this one.
TABLE_ROW = re.compile(r"^\s*(?:\||>?\s*\|)")
# NOT `;` - "MAN-2439 landed; in review it turned out …" is one sentence, and
# splitting it hid the ticket from its own marker.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# The whole argument list, not just its first string: `add_argument("-p",
# "--port", …)` declares --port on its SECOND string, and reading only the
# first reported the documented --port as unsupported.
ADD_ARGUMENT = re.compile(r"add_argument\(([^)]*)")
# A documented invocation of one of this repo's own tools, in a shell block.
# `py -3.12 …` is how these are run on Windows, which is where they are
# maintained - a regex that only knew `python` missed every such line.
TOOL_CALL = re.compile(
    r"(?m)^\s*\$?\s*(?:py|python|python3)(?:\s+-3(?:\.\d+)?)?\s+\S*?"
    r"((?:check_ui|check_app|preview|version_check|check_repo|smoke_tools|"
    r"linter_mutations)\.py)([^\n]*)$")
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
     ["templates/preview.py", "skills/manaurum-app/SKILL.md",
      "skills/manaurum-app/references/checks.md"],
     re.compile(r"(?i)(without\s+`?--virtual-time-budget|drop the flag)"),
     "must say the flag is DROPPED, not shortened, to photograph a loading "
     "state - Chrome pauses virtual time while a request is in flight"),
    ("headless viewport floor",
     ["templates/preview.py", "skills/manaurum-app/SKILL.md",
      "skills/manaurum-app/references/checks.md"],
     re.compile(r"(?i)floor[^.]{0,120}500px"),
     "must state the ~500px headless layout-viewport floor, or a reader will "
     "shrink the window instead of using ?width="),
]

# ── Facts that were true once ───────────────────────────────────────────────
# Each was taught here, in up to twelve places at once, and kept being taught
# for weeks after Core changed (the 2026-10-02 audit, docs/audits/). Once a
# sentence like this has been wrong, it is not allowed back: the regex names
# the claim, the second string what is true now.
STALE_FACTS = [
    (re.compile(r"(?i)there is no readiness probe|no readiness probe (?:on|in|anywhere)"),
     "the deploy has a readiness probe (MAN-1369): a container that does not answer "
     "fails the deploy and is rolled back"),
    (re.compile(r"(?i)(?:green deploy|deploys? green)[^.\n]{0,60}502|every request 502s|"
                r"502s? on every (?:single )?request"),
     "a wrong port fails the readiness probe; it does not deploy green and 502"),
    (re.compile(r"(?i)\*not\* strict|`?runtime`?[^.\n]{0,30}\bnot strict"),
     "`runtime` is strict (additionalProperties: false) since MAN-1899"),
    (re.compile(r"(?i)/agent[^\n]{0,80}public internet|public internet[^\n]{0,80}/agent|"
                r"Traefik straight to (?:your|the|this) container"),
     "the gateway refuses /agent/* on the public host (MAN-1432); the reason to verify "
     "the JWT is the shared container network"),
    (re.compile(r"(?i)version still activates|migration[^.\n]{0,80}still activates"),
     "a failed migration stops the version from going live (MAN-2510)"),
    (re.compile(r"(?i)validated (?:only )?inside the job|only three things fail synchronously"),
     "POST /deploy refuses a bad manifest, slug, owner, version or archive synchronously"),
    (re.compile(r'"apps"\s*:\s*\[\s*"\*"\s*\]'),
     "a wildcard token scope is refused (MAN-1585); a new app needs an owner token"),
    (re.compile(r"(?i)gateway rejects (?:it|the user[_ ]?context)"),
     "the capability gateway requires the user context for os.drive.* and os.calendar.*"),
    (re.compile(r"DROP\[s\] everything else|(?i:egress[^.\n]{0,80}drops? everything else)"),
     "egress_allowed_hosts is enforced by os.http.fetch only"),
    (re.compile(r"(?i)(?:does not|doesn't) remove (?:a copy|one|the copy|the one) the client sent|"
                r"gateway adds its own copy;|client's header is passed through|"
                r"passes the request's headers through"),
     "the gateway drops a client-sent X-Manaurum-User-Context (MAN-3214)"),
    (re.compile(r"(?i)\bno `?workspace_id`? (?:claim|in the token)|"
                r"(?:token|user_context) (?:does not|doesn't|never) carr(?:y|ies) (?:a |one |the )?"
                r"`?workspace_id"),
     "the gateway mints user_context with workspace_id (v2_app_gateway.py, mint_user_context)"),
    (re.compile(r"(?i)cannot learn (?:it|the language)\b|"
                r"(?:language|locale)\b[^.\n]{0,60}\bnot in the `?(?:user_context|person pass)"),
     "the user_context and the person pass carry the person's language as locale / dir "
     "(Core MAN-3244); an app's server and the Assistant's calls read it from the token"),
    (re.compile(r"(?i)(?:first slice )?returns a stub"),
     "the logs endpoint returns a real tail"),
]
REPORTED_SPEECH = re.compile(r"(?i)\b(said|used to|earlier version|until \d|was wrong|"
                             r"is wrong|stale|no longer)\b")
# Text files under templates/ teach as much as the skills do, and the stale
# facts above lived in the starter's docstrings and README too.
TEMPLATE_TEXT = {".md", ".py", ".html", ".css", ".txt", ""}
CAPABILITY_NAME = re.compile(r"`(os\.[a-z_]+\.[a-z_]+)`")
SAYS_IT_DOES_NOT_EXIST = re.compile(r"(?i)\b(there is no|is no|nothing else exists|"
                                    r"does not exist|do not exist|no `)")
PERMISSIONS_ENUM = re.compile(r"(?i)\benum\b[^\n]*\bmicrophone\b")
CAPABILITY_COUNT = re.compile(r"All \*\*(\d+)\*\*")
CONTRACT = "templates/platform-contract.json"
STRINGS = "scripts/platform-strings.json"
SDK_API = "skills/manaurum-app/references/sdk-api.md"
# An error code as the documents write one: `404 route_not_declared`,
# `502 upstream_error:<provider>`, or the second cell of a status row,
# `| 409 | `slug_reserved` / `slug_owned_by_another_tenant` |`.
DOC_CODE = re.compile(r"`\"?(\d{3}) ([a-z][a-z0-9_]{3,})(?::[^`]*)?`")
STATUS_ROW = re.compile(r"^\|\s*\d{3}\s*\|([^|\n]*)\|", re.M)
ROW_CODE = re.compile(r"(?:^|/)\s*`\"?([a-z][a-z0-9_]{3,})(?::[^`]*)?\"?`\s*(?=/|$)")
SHELL_MESSAGE = re.compile(r"\bmanaurum:[a-z][a-z-]*")
SCHEMA = "templates/manifest_v2.schema.json"
REFERENCE = "skills/manaurum-app/references/capabilities-reference.md"

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
    """One version, seven files.

    2.8.0 shipped with `**Version 2.7.3**` in the README. Nobody reading the
    README could tell which of the two numbers was the lie, and the plugin
    cache is keyed on the real one.

    The starter's `app.css` carries it too, because that file is COPIED into
    apps and lives on in them: its version line is the only way to tell, from
    a deployed app's source, which template it was copied from (MAN-2849).
    """
    sources = [
        (".claude-plugin/plugin.json", PLUGIN_VERSION, '"version"'),
        # The Codex manifests (MAN-1439). PR #34 shipped them at 3.0.0 while
        # the plugin was already past it, because nothing here read them.
        (".codex-plugin/plugin.json", PLUGIN_VERSION, '"version"'),
        ("plugin.json", PLUGIN_VERSION, '"version"'),
        ("README.md", README_VERSION, "**Version X.Y.Z**"),
        ("CHANGELOG.md", CHANGELOG_VERSION, "the newest `# X.Y.Z` heading"),
        ("skills/manaurum-app/SKILL.md", SKILL_VERSION, "This page is SDK X.Y.Z"),
        ("templates/v2-starter/src/static/app.css", STARTER_CSS_VERSION,
         "manaurum-starter app.css X.Y.Z"),
    ]
    found = {}
    for name, pattern, what in sources:
        path = ROOT / name
        if not path.exists():
            problems.append("%s:1: missing - the version lives here too (%s)" % (name, what))
            continue
        text = read(path)
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
        lines = text.splitlines()
        for match in REPO_PATH.finditer(text):
            target = match.group(1).rstrip("/")
            if any(ch in target for ch in "*<>…"):
                continue
            line_no = line_of(text, match.start())
            # `scripts/deploy.sh in YOUR project` is a path in the reader's
            # app, not in this repository, and it shares its first segment
            # with ours. The reader's own words are the only signal.
            if OTHERS_PROJECT.search(lines[line_no - 1] if line_no <= len(lines) else ""):
                continue
            # The docs name files by a partial path and let the reader
            # resolve it: `references/design.md` from inside the references
            # directory, `manaurum-deploy/SKILL.md` from another skill.
            # Every root has to stay INSIDE the checkout - `doc.parent.parent`
            # for README.md is the directory above it, and a file there
            # satisfied this check while not existing in the repo at all.
            roots = [ROOT, doc.parent, doc.parent.parent, ROOT / "skills",
                     ROOT / "skills" / "manaurum-app"]
            roots = [root for root in roots if root == ROOT or ROOT in root.parents]
            if not any((root / target).exists() for root in roots):
                problems.append("%s:%d: `%s` does not exist" % (rel(doc), line_no, target))


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
    # version_check.py's STALE.md text names Step 3.5 and prints itself into a
    # session's context. Renumber the step and that string rots with nothing
    # watching it, because it is not a document.
    targets = live_docs() + [ROOT / name for name in DOC_QUOTING_SOURCES]
    for doc in targets:
        if not doc.is_file():
            continue
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
        lines = text.splitlines()
        for match in TEST_COUNT.finditer(text):
            line_no = line_of(text, match.start())
            line = lines[line_no - 1] if line_no <= len(lines) else ""
            spelled = not match.group(1).isdigit()
            # "Write two tests for every capability you use" is an instruction
            # to the reader, not a claim about this suite. Only a sentence
            # that is talking about the suite gets to be a claim about it.
            if spelled and not TEST_SUBJECT.search(line):
                continue
            before = text[max(0, match.start() - 30):match.start()]
            if TEST_IMPERATIVE.search(before) and not TEST_SUBJECT.search(line):
                continue
            problems.append(
                "%s:%d: a hardcoded test count (\"%s\") - the suite grows every "
                "release and this sentence does not; say what the tests cover, "
                "and let CI print the number"
                % (rel(doc), line_no, match.group(0).strip()))

        for line_no, line in enumerate(lines, start=1):
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
    for doc in live_docs() + [ROOT / name for name in DOC_QUOTING_SOURCES]:
        if not doc.is_file():
            continue
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
        data = path.read_bytes()
        # A NUL is the classic "this is not text" signal, and it is the only
        # honest one: a hardcoded list of binary extensions failed a build on
        # a .zip, a .dat and a .jpeg with a message telling the author to
        # stop using heredocs. A checker that is wrong in public is one
        # everybody learns to ignore.
        if b"\x00" in data:
            continue
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

    Two things are NOT this defect and must stay writable: a path carrying a
    shell expansion (`/tmp/ctx-$$.tar`) is per-run and is the fix; and a
    sentence teaching the lesson ("never write it to /tmp/ctx.tar") is not an
    instruction to do it.
    """
    for doc in live_docs():
        text = read(doc)
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "mktemp" in line or "TMPDIR" in line:
                continue
            for match in TMP_PATH.finditer(line):
                path = match.group(0)
                if "$" in path:
                    continue
                if NEGATION.search(line[:match.start()]):
                    continue
                problems.append(
                    "%s:%d: fixed path `%s` - /tmp is shared between sessions; "
                    "use a per-run `mktemp -d`" % (rel(doc), line_no, path))


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
            # gitignore semantics, not fnmatch's: a later `!pattern` UN-ignores
            # what an earlier line matched, and last match wins. Ignoring that
            # reported `.env*` as coverage while a `!.env.manaurum` two lines
            # down meant git would track the token file - the exact leak this
            # check exists to prevent.
            covered = False
            for pattern in patterns:
                negated = pattern.startswith("!")
                body = pattern[1:] if negated else pattern
                if (fnmatch.fnmatch(filename, body) or fnmatch.fnmatch(base, body)
                        or fnmatch.fnmatch(filename, body + "/*")):
                    covered = not negated
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
    """The long flags a tool in this repo actually accepts.

    Every option string in each `add_argument` call, not just the first:
    `add_argument("-p", "--port", …)` declares `--port` second, and reading
    only the first string reported a documented `--port` as unsupported.
    A tool with no argparse at all (check_ui.py, check_app.py) legitimately
    accepts no flags, and a documented one is then a real finding.
    """
    for candidate in (ROOT / "templates" / tool, ROOT / "scripts" / tool):
        if candidate.exists():
            text = read(candidate)
            flags = set()
            for arguments in ADD_ARGUMENT.findall(text):
                flags |= set(LONG_FLAG.findall(arguments))
            # A bare `sys.argv` tool can still document a flag it handles.
            flags |= set(re.findall(r'"(--[a-z][a-z0-9-]*)" in sys\.argv', text))
            flags |= set(re.findall(r'sys\.argv\[1:\][^\n]*"(--[a-z][a-z0-9-]*)"', text))
            return flags
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
            rest = rest.split("#", 1)[0]
            for flag in LONG_FLAG.findall(rest):
                if flag not in supported:
                    problems.append(
                        "%s:%d: `%s %s` - %s does not accept %s"
                        % (rel(doc), line_of(text, match.start()), tool, flag.strip(),
                           tool, flag))


def teaching_files() -> list:
    """Live documents plus every text file a reader copies from templates/."""
    paths = list(live_docs())
    for path in sorted((ROOT / "templates").rglob("*")):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in ("platform-contract.json", "manifest_v2.schema.json"):
            continue
        if path.suffix in TEMPLATE_TEXT or path.name == "Dockerfile":
            paths.append(path)
    return paths


def check_stale_facts(problems: list) -> None:
    """A fact that has been wrong once does not come back."""
    for path in teaching_files():
        text = read(path)
        for pattern, now in STALE_FACTS:
            for match in pattern.finditer(text):
                # The sentence, not the line: a Markdown paragraph is one line,
                # and one "earlier version" in it must not excuse the rest.
                line_start = text.rfind("\n", 0, match.start()) + 1
                line_end = text.find("\n", match.end())
                line_end = len(text) if line_end == -1 else line_end
                start = max(line_start, text.rfind(". ", line_start, match.start()) + 2)
                end = text.find(". ", match.end(), line_end)
                if REPORTED_SPEECH.search(text[start:line_end if end == -1 else end]):
                    continue        # "an earlier version said ..." is history
                problems.append("%s:%d: %r - %s" % (rel(path), line_of(text, match.start()),
                                                     match.group(0), now))


def load_contract():
    try:
        return (json.loads(read(ROOT / SCHEMA)), json.loads(read(ROOT / CONTRACT)))
    except (OSError, ValueError):
        return None, None


def check_contract(problems: list) -> None:
    """The documents and the linter against the copy of Core's contract.

    `scripts/sync_contract.py` refreshes the copy from the monorepo; this is
    what makes a refresh show every sentence it turned false. What it holds
    the repository to:

    * every registered capability is documented in the reference, and the
      reference's own count is the registry's;
    * every capability a document names in backticks is registered, unless
      the sentence says it does not exist;
    * every statement of the `permissions` enum lists the schema's values;
    * `check_app.py`'s fallback copy of the `runtime` keys is the schema's.
    """
    schema, contract = load_contract()
    if schema is None:
        problems.append("%s / %s: missing or not JSON - run scripts/sync_contract.py"
                        % (SCHEMA, CONTRACT))
        return
    names = set(contract.get("capabilities", []))
    reference = read(ROOT / REFERENCE)
    for name in sorted(names):
        if "`%s`" % name not in reference and "**`%s`**" % name not in reference:
            problems.append("%s:1: %s is registered on Core and documented nowhere here"
                            % (REFERENCE, name))
    for match in CAPABILITY_COUNT.finditer(reference):
        if int(match.group(1)) != len(names):
            problems.append("%s:%d: says All %s capabilities; Core registers %d"
                            % (REFERENCE, line_of(reference, match.start()),
                               match.group(1), len(names)))

    for path in live_docs():
        text = read(path)
        for number, line in enumerate(text.splitlines(), 1):
            if SAYS_IT_DOES_NOT_EXIST.search(line):
                continue
            for name in CAPABILITY_NAME.findall(line):
                if name not in names:
                    problems.append("%s:%d: `%s` is not a capability Core registers"
                                    % (rel(path), number, name))

    enum = (schema.get("properties", {}).get("permissions", {})
            .get("items", {}).get("enum", []))
    for path in live_docs():
        text = read(path)
        for number, line in enumerate(text.splitlines(), 1):
            if PERMISSIONS_ENUM.search(line):
                missing = [value for value in enum if value not in line]
                if missing:
                    problems.append("%s:%d: states the permissions enum without %s"
                                    % (rel(path), number, ", ".join(missing)))

    runtime = set(schema.get("properties", {}).get("runtime", {}).get("properties", {}))
    linter = read(ROOT / "templates" / "check_app.py")
    match = re.search(r"RUNTIME_KEYS = \{([^}]*)\}", linter)
    if not match:
        # Renamed or reshaped: say so, rather than compare nothing and pass.
        problems.append("templates/check_app.py:1: no `RUNTIME_KEYS = {...}` to hold "
                        "to the schema - update check_contract with it")
    else:
        copy = set(re.findall(r'"([a-z_]+)"', match.group(1)))
        if copy != runtime:
            problems.append("templates/check_app.py:1: RUNTIME_KEYS differs from the "
                            "schema's runtime keys (%s)"
                            % ", ".join(sorted(copy ^ runtime)))


def check_platform_codes(problems: list) -> None:
    """Every error code a document quotes is one Core still writes.

    `scripts/platform-strings.json` is every snake_case word in a string
    literal of the Core code a v2 developer's errors come from (the gateways,
    the deploy, the capability handlers). A documented code that is not in
    it was renamed or removed: a developer matching on it waits for a
    response that never comes. A code built from a prefix
    (`f"{prefix}_backslash"`) counts when its prefix is written somewhere.
    """
    try:
        data = json.loads(read(ROOT / STRINGS))
    except (OSError, ValueError):
        problems.append("%s: missing or not JSON - run scripts/sync_contract.py" % STRINGS)
        return
    strings, suffixes = set(data.get("strings", [])), data.get("suffixes", [])
    sha = data.get("source", {}).get("sha", "?")[:9]

    def written(code: str) -> bool:
        # A built code: the prefix is written somewhere, or is one plain word
        # filled in at run time (`f"{provider}_upstream_error"`).
        return code in strings or any(
            code.endswith(tail) and (code[:-len(tail)] in strings or
                                     re.fullmatch(r"[a-z]+", code[:-len(tail)]))
            for tail in suffixes)

    for path in live_docs():
        text = read(path)
        quoted = [(m.start(), m.group(2)) for m in DOC_CODE.finditer(text)]
        for row in STATUS_ROW.finditer(text):
            quoted += [(row.start(1), m.group(1)) for m in ROW_CODE.finditer(row.group(1))]
        for start, code in sorted(set(quoted)):
            if not written(code):
                problems.append("%s:%d: `%s` is not an error code Core writes (Core @ %s) "
                                "- renamed or gone; fix the document, or re-run "
                                "scripts/sync_contract.py if Core added it since"
                                % (rel(path), line_of(text, start), code, sha))


SECTION_HEADING = re.compile(r"^#{2,3} (.*)$", re.M)
INPUT_MARK = re.compile(r"\*\*Input:\*\*|the input is\b")
# What follows the mark: an inline `{ … }` on the same line, or the first
# fenced block below it (any language tag - `jsonc` is JSON too).
INLINE_EXAMPLE = re.compile(r"\A[^\n`]*\n?[^\n`]*`(\{[^`]*\})`")
BLOCK_EXAMPLE = re.compile(r"\A[^\n]*\n(?:[^\n`][^\n]*\n|\n){0,3}```[a-z]*\n(.*?)```", re.S)
FIELD_TABLE = re.compile(r"^\|\s*Field\s*\|(.*)\|[ \t]*\n\|[-| :]+\|[ \t]*\n"
                         r"((?:\|.*\|[ \t]*\n?)+)", re.M)
CELL_SPLIT = re.compile(r"(?<!\\)\|")


def example_keys(example: str) -> set:
    """Top-level keys of a JSON-ish example: `{ "key": "<anything>" }`, and
    the key-only form `{ "target_app_id", "since"? }`. A string after a
    colon is a value, whatever it looks like."""
    keys, depth, index, last = set(), 0, 0, ""
    while index < len(example):
        char = example[index]
        if char == '"':
            end = index + 1
            while end < len(example) and example[end] != '"':
                end += 2 if example[end] == "\\" else 1
            if end >= len(example):
                break
            if depth == 1 and last in ("{", ",") and \
                    re.match(r"\s*\??\s*[:,}]", example[end + 1:]):
                keys.add(example[index + 1:end])
            index, last = end + 1, '"'
            continue
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
        if not char.isspace():
            last = char
        index += 1
    return keys


def check_capability_inputs(problems: list) -> None:
    """Each capability's documented input is the one its handler validates.

    `capability_inputs` in the contract is every capability's input fields
    and `required`, read from its registration on Core. In the reference,
    under a heading that names one capability: the first **Input** example
    may name only fields the schema has and must name every required one,
    and a `| Field | … | Required |` table under it lists exactly the
    schema's fields, required where the schema requires them. The wrong
    field names of `os.files.upload` and `os.ocr.extract` (audit K2, K3)
    shipped because nothing compared the two.
    """
    _, contract = load_contract()
    inputs = (contract or {}).get("capability_inputs")
    if not inputs:
        problems.append("%s: no `capability_inputs` - run scripts/sync_contract.py" % CONTRACT)
        return
    text = read(ROOT / REFERENCE)
    headings = list(SECTION_HEADING.finditer(text))
    for index, heading in enumerate(headings):
        names = re.findall(r"`(os\.[a-z_.]+)`", heading.group(1))
        if len(names) != 1 or names[0] not in inputs:
            continue
        name = names[0]
        properties = set(inputs[name]["properties"])
        required = set(inputs[name]["required"])
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[heading.end():end]
        at = heading.end()
        mark = INPUT_MARK.search(body)
        example = None
        if mark:
            rest = body[mark.end():]
            example = INLINE_EXAMPLE.match(rest) or BLOCK_EXAMPLE.match(rest)
            if example is None:
                problems.append("%s:%d: the %s input example is in a shape this check "
                                "cannot read - write it as `{ … }` on the **Input:** line "
                                "or as the fenced block right below it"
                                % (REFERENCE, line_of(text, at + mark.start()), name))
        if example is not None:
            keys = example_keys(example.group(1))
            line = line_of(text, at + mark.start())
            for key in sorted(keys - properties):
                problems.append("%s:%d: the %s example sends `%s`, which its input "
                                "schema does not have (422 input_schema_violation)"
                                % (REFERENCE, line, name, key))
            for key in sorted(required - keys):
                problems.append("%s:%d: the %s example leaves out `%s`, which its "
                                "input schema requires" % (REFERENCE, line, name, key))
            alternatives = inputs[name].get("one_of_required") or []
            if alternatives and sum(1 for alt in alternatives if set(alt) <= keys) != 1:
                problems.append("%s:%d: the %s example must send exactly one of %s"
                                % (REFERENCE, line, name,
                                   " / ".join("+".join(alt) for alt in alternatives)))
            together = set(inputs[name].get("not_all_of") or [])
            if together and together <= keys:
                problems.append("%s:%d: the %s example sends %s together, which its "
                                "input schema refuses" % (REFERENCE, line, name,
                                                          " and ".join(sorted(together))))
        table = FIELD_TABLE.search(body)
        if not table:
            continue
        header = [cell.strip() for cell in CELL_SPLIT.split("Field|" + table.group(1))]
        if "Required" not in header:
            continue
        column = header.index("Required")
        line = line_of(text, at + table.start())
        documented, rows = {}, {}
        for row in table.group(2).strip().splitlines():
            cells = [cell.strip() for cell in CELL_SPLIT.split(row.strip().strip("|"))]
            if len(cells) <= column:
                continue
            flag = cells[column].replace("*", "").lower().startswith("yes")
            for field in re.findall(r"`([a-z_][a-z0-9_]*)`", cells[0]):
                documented[field] = flag
                rows[field] = " ".join(cells[1:])
        # A row that lists a field's allowed values lists all of them: the day
        # Core adds PATCH to os.http.fetch, the `method` row goes red here.
        for field, values in sorted((inputs[name].get("enums") or {}).items()):
            named = set(re.findall(r"`([^`]+)`", rows.get(field, "")))
            if named & set(values):
                for value in sorted(set(values) - named):
                    problems.append("%s:%d: the %s field table lists values of `%s` "
                                    "but not `%s`, which its input schema allows"
                                    % (REFERENCE, line, name, field, value))
        for field in sorted(set(documented) - properties):
            problems.append("%s:%d: the %s field table lists `%s`, which its input "
                            "schema does not have" % (REFERENCE, line, name, field))
        for field in sorted(properties - set(documented)):
            problems.append("%s:%d: the %s field table leaves out `%s`, which its "
                            "input schema accepts" % (REFERENCE, line, name, field))
        for field in sorted(set(documented) & properties):
            if documented[field] != (field in required):
                problems.append("%s:%d: the %s field table calls `%s` %s; its input "
                                "schema %s it" % (REFERENCE, line, name, field,
                                                  "required" if documented[field] else "optional",
                                                  "does not require" if documented[field]
                                                  else "requires"))


def check_shell_messages(problems: list) -> None:
    """The window protocol in the documents is the shell's.

    Every `manaurum:*` type a document or template names is one the shell
    handles, sends or refuses (`iframeHostPolicy.ts`, `IframeAppHost.tsx`,
    the session runtime), and every type a v2 app may send or will receive
    is described in the SDK reference.
    """
    _, contract = load_contract()
    messages = (contract or {}).get("messages")
    if not messages:
        problems.append("%s: no `messages` - run scripts/sync_contract.py" % CONTRACT)
        return
    exact = set(messages["app_to_shell"]) | set(messages["shell_to_app"]) | \
        set(messages["session"])
    prefixes = list(messages["rejected_prefixes"])

    def known(name: str) -> bool:
        # `manaurum:session-` and `manaurum:storage-*` name a family.
        return name in exact or any(name.startswith(p) for p in prefixes) or \
            any(e.startswith(name) for e in exact if name.endswith("-"))

    for path in teaching_files():
        text = read(path)
        for match in SHELL_MESSAGE.finditer(text):
            if not known(match.group(0)):
                problems.append("%s:%d: `%s` is not a message the shell handles, sends "
                                "or refuses" % (rel(path), line_of(text, match.start()),
                                                match.group(0)))
    reference = read(ROOT / SDK_API)
    for name in sorted(set(messages["app_to_shell"]) | set(messages["shell_to_app"])):
        if not re.search(re.escape(name) + r"(?![a-z-])", reference):
            problems.append("%s:1: `%s` is part of the shell's protocol and described "
                            "nowhere here" % (SDK_API, name))


SUMMARY_LINE = re.compile(r"(?m)^Summary:[ \t]*(\S.*)$")
SUMMARY_MAX = 200


def check_changelog_summary(problems: list) -> None:
    """The newest release says what changed in one plain sentence.

    The team's Telegram announcement of a release (MAN-3187) quotes this
    line. Its readers include people who build apps without reading code, and
    the headline is written for the people who made the change: 3.1.0 went
    out as "what the first app ported to v2 found missing (Planning Poker)",
    which tells a restaurant-app developer nothing about whether to update.
    """
    path = ROOT / "CHANGELOG.md"
    if not path.exists():
        return
    text = read(path)
    headings = list(CHANGELOG_VERSION.finditer(text))
    if not headings:
        return
    newest = headings[0]
    end = headings[1].start() if len(headings) > 1 else len(text)
    match = SUMMARY_LINE.search(text, newest.end(), end)
    line = line_of(text, newest.start())
    if not match:
        problems.append(
            "CHANGELOG.md:%d: release %s has no `Summary:` line - one plain "
            "sentence for someone who does not program; the release "
            "announcement quotes it" % (line, newest.group(1)))
    elif len(match.group(1)) > SUMMARY_MAX:
        problems.append(
            "CHANGELOG.md:%d: the `Summary:` of %s is %d characters - keep it "
            "to one sentence, at most %d"
            % (line_of(text, match.start()), newest.group(1),
               len(match.group(1)), SUMMARY_MAX))


def check_paired_claims(problems: list) -> None:
    """A measured fact written down twice has to say the same thing twice.

    The fact is REQUIRED in every listed file, not merely consistent where it
    happens to appear. An earlier version only fired when one copy
    contradicted the other, so deleting the paragraph from both files - or
    renaming the flag it is about - turned the check off silently, which is
    the same failure it exists to catch one level up.
    """
    for label, files, required, why in PAIRED_CLAIMS:
        for name in files:
            path = ROOT / name
            if not path.exists():
                problems.append("%s:1: missing - it is one of the places that "
                                "carry the %s fact" % (name, label))
                continue
            if not required.search(read(path)):
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


def claim_age_days(line: str):
    """How long since somebody last checked this claim, or None.

    The date is not a gate - a build that turns red because time passed is a
    build people learn to ignore, and nothing here can re-check Linear
    anyway. It is printed, because "last verified 143 days ago" is the one
    thing that makes a human open the ticket.
    """
    match = CLAIM_DATE.search(line)
    if not match:
        return None
    try:
        when = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None
    return (date.today() - when).days


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
            pending = (PENDING_CLAIM.search(unit) is not None
                       and RESOLVED_CLAIM.search(unit) is None)
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
        elif claim_age_days(line) is None:
            problems.append(
                "scripts/open-claims.txt:%d: %s has no readable YYYY-MM-DD - the "
                "date is the whole value of the line, because it is what says how "
                "stale the claim might be" % (line_no, ident))


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
        age = claim_age_days(note)
        stamp = "" if age is None else "   [last checked %d day%s ago]" % (
            age, "" if age == 1 else "s")
        print("  %s%s" % (note.strip(), stamp))
        for doc, line in sorted(set(places)):
            print("      %s:%d" % (doc, line))
    print("")
    print("MAN-1393 sat in README.md as \"blocked\" for months after it was Done.")


CHECKS = (
    check_versions,
    check_changelog_summary,
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
    check_stale_facts,
    check_contract,
    check_platform_codes,
    check_shell_messages,
    check_capability_inputs,
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
        # Findings quote the documents, and the documents are full of em
        # dashes. Forcing ASCII here is what keeps the promise at the top of
        # this file on a cp1252 console, where the alternative is a
        # UnicodeEncodeError instead of a finding.
        print("x %s" % problem.encode("ascii", "replace").decode("ascii"))
    print("%d problem(s)" % len(problems) if problems else "clean")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

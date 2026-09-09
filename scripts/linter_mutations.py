#!/usr/bin/env python3
"""Break the starter on purpose, one rule at a time, and demand a red.

A linter nobody has seen fail is a linter nobody has tested. `check_ui.py`
shipped with a hole exactly this shape: it read `.css` files for the tokens
they DECLARE and never for the tokens they USE, so the reference stylesheet
carried `var(--container-lg, 1024px)` with that name declared nowhere and the
linter said `clean` for a whole release.

So every rule in `templates/check_ui.py` and `templates/check_app.py` gets a
mutation here: a copy of the starter with that one rule broken, and an
assertion that the linter goes red AND names the thing. A rule with no
mutation below is a rule that has never been observed working.

Standard library only, no network. Run it from the repository root:

    python scripts/linter_mutations.py           # every mutation
    python scripts/linter_mutations.py routes    # only mutations matching a name

Exit code: 0 all mutations caught, 1 one or more survived.

A SURVIVING MUTATION IS THE FINDING. It does not mean the mutation was
harmless; it means the linter cannot see that class of defect, and every app
built with it is unchecked in that direction.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STARTER = ROOT / "templates" / "v2-starter"
CHECK_APP = ROOT / "templates" / "check_app.py"
CHECK_UI = ROOT / "templates" / "check_ui.py"


def edit(path: Path, old: str, new: str) -> None:
    """Replace exactly once, and refuse to pretend if the anchor moved."""
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError("anchor not found in %s: %r" % (path.name, old[:70]))
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_manifest(app: Path, mutate) -> None:
    path = app / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── The mutations ───────────────────────────────────────────────────────────
# (name, what to break, the text the finding must contain)


def undeclared_route(app: Path) -> None:
    edit(app / "src" / "main.py",
         '@app.get("/api/me")',
         '@app.get("/api/exports")\nasync def exports() -> dict:\n'
         '    return {}\n\n\n@app.get("/api/me")')


def glob_does_not_cover_the_prefix(app: Path) -> None:
    # The `/api/x/*` trap: the detail screen works and the list screen 404s.
    def mutate(data):
        for entry in data["runtime"]["api_routes"]:
            if entry["path"] == "/api/notes":
                entry["path"] = "/api/notes/*"
    patch_manifest(app, mutate)


def declared_but_never_served(app: Path) -> None:
    def mutate(data):
        data["runtime"]["api_routes"].append({"path": "/api/reports", "auth": "user"})
    patch_manifest(app, mutate)


def agent_handler_without_auth(app: Path) -> None:
    edit(app / "src" / "agent_routes.py",
         'async def read_my_note(claims: UserContextClaims = Depends(auth_claims)) -> dict:',
         'async def read_my_note() -> dict:\n    claims = None')


def entry_point_that_is_not_there(app: Path) -> None:
    patch_manifest(app, lambda data: data["frontend"].update(entry_point="/app.html"))


def port_disagreement(app: Path) -> None:
    patch_manifest(app, lambda data: data["runtime"].update(port=9000))


def expose_disagreement(app: Path) -> None:
    edit(app / "Dockerfile", "EXPOSE 8000", "EXPOSE 80")


def env_file_in_the_app(app: Path) -> None:
    (app / ".env.manaurum").write_text("MANAURUM_V2_TOKEN=mna_notreal\n", encoding="utf-8")


def undeclared_capability(app: Path) -> None:
    edit(app / "src" / "capability.py", '"os.kv.set"', '"os.kv.delete"')


def declared_capability_nobody_calls(app: Path) -> None:
    def mutate(data):
        data["requires_capabilities"].append({"name": "os.files.upload", "version": "1"})
    patch_manifest(app, mutate)


def destructive_migration(app: Path) -> None:
    directory = app / "migrations"
    directory.mkdir(exist_ok=True)
    (directory / "0001_init.sql").write_text(
        "CREATE TABLE note (id text primary key);\nDROP TABLE legacy_note;\n",
        encoding="utf-8")


def anonymous_do_block(app: Path) -> None:
    directory = app / "migrations"
    directory.mkdir(exist_ok=True)
    (directory / "0001_init.sql").write_text(
        "DO $$ BEGIN CREATE TABLE note (id text); END $$;\n", encoding="utf-8")


def migration_that_is_not_sql(app: Path) -> None:
    directory = app / "migrations"
    directory.mkdir(exist_ok=True)
    (directory / "0001_init.sql").write_text("CREATE TABLE note (id text);\n",
                                             encoding="utf-8")
    (directory / "0002_seed.py").write_text("# seeds\n", encoding="utf-8")


def migrations_out_of_order(app: Path) -> None:
    directory = app / "migrations"
    directory.mkdir(exist_ok=True)
    (directory / "0001_init.sql").write_text("CREATE TABLE note (id text);\n",
                                             encoding="utf-8")
    (directory / "9_later.sql").write_text("ALTER TABLE note ADD COLUMN body text;\n",
                                           encoding="utf-8")
    (directory / "10_latest.sql").write_text("ALTER TABLE note ADD COLUMN tag text;\n",
                                             encoding="utf-8")


APP_MUTATIONS = [
    ("routes: a path the manifest does not declare", undeclared_route,
     "no runtime.api_routes rule covers it"),
    ("routes: /api/x/* does not cover /api/x", glob_does_not_cover_the_prefix,
     "GET /api/notes is served but no runtime.api_routes rule covers it"),
    ("routes: declared and never served", declared_but_never_served,
     "nothing serves it"),
    ("agent: a handler with no user-context check", agent_handler_without_auth,
     "no user-context verification"),
    ("frontend: entry_point names nothing", entry_point_that_is_not_there,
     "frontend.entry_point"),
    ("port: the manifest and the CMD disagree", port_disagreement,
     "manifest.runtime.port is 9000"),
    ("port: EXPOSE disagrees", expose_disagreement,
     "EXPOSE 80 but manifest.runtime.port"),
    ("secrets: a .env inside the app directory", env_file_in_the_app,
     ".env file inside the app directory"),
    ("capabilities: called but not declared", undeclared_capability,
     "capability_not_granted"),
    ("capabilities: declared but not called", declared_capability_nobody_calls,
     "over-broad grant request"),
    ("migrations: destructive DDL, no migration.breaking", destructive_migration,
     "DROP without manifest.migration.breaking"),
    ("migrations: an anonymous DO $$ block", anonymous_do_block,
     "DO $$"),
    ("migrations: a file that is not .sql", migration_that_is_not_sql,
     "not a .sql file"),
    ("migrations: numbers of different widths", migrations_out_of_order,
     "zero-padded"),
]


# ── check_ui.py, over the same starter's static files ───────────────────────


def token_declared_nowhere(app: Path) -> None:
    # The 2.9.0 bug, verbatim: keep the var(), drop the declaration.
    edit(app / "src" / "static" / "app.css", "  --container-lg: 1024px;\n", "")


def hex_in_the_markup(app: Path) -> None:
    edit(app / "src" / "static" / "index.html", "<body", '<body data-x="#3355ff" ')


def a_tab_bar(app: Path) -> None:
    edit(app / "src" / "static" / "index.html", "<body", '<body><nav class="tabs">x</nav')


def a_native_modal(app: Path) -> None:
    edit(app / "src" / "static" / "index.html", "</body>",
         "<script>function go(){ confirm('sure?'); }</script></body>")


def a_media_query(app: Path) -> None:
    edit(app / "src" / "static" / "app.css", ":root {",
         "@media (max-width: 600px) { .card { padding: 0 } }\n:root {")


def the_handshake(app: Path) -> None:
    path = app / "src" / "static" / "index.html"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("manaurum:ready", "manaurum:almost-ready"),
                    encoding="utf-8")


UI_MUTATIONS = [
    ("ui: a var() whose token is declared nowhere", token_declared_nowhere,
     "declared nowhere"),
    ("ui: a hex in the markup", hex_in_the_markup, "in markup"),
    ("ui: a tab bar", a_tab_bar, "tab/tabs/sidebar class"),
    ("ui: confirm()", a_native_modal, "alert/confirm/prompt"),
    ("ui: @media max-width", a_media_query, "@media max-width"),
    ("ui: no manaurum:ready", the_handshake, "no manaurum:ready"),
]


def run(linter: Path, target: Path):
    return subprocess.run([sys.executable, str(linter), str(target)],
                          capture_output=True, text=True)


def sanity(problems: list) -> None:
    """The unmutated starter has to be clean, or every result below is noise."""
    for linter, target in ((CHECK_APP, STARTER),
                           (CHECK_UI, STARTER / "src" / "static")):
        done = run(linter, target)
        if done.returncode != 0:
            problems.append("%s is not clean on the untouched starter, so no "
                            "mutation result below means anything:\n%s"
                            % (linter.name, done.stdout.strip()))


def main() -> int:
    wanted = [arg.lower() for arg in sys.argv[1:]]
    problems = []
    sanity(problems)
    if problems:
        for problem in problems:
            print("x %s" % problem)
        return 1

    cases = ([(CHECK_APP, "app", *case) for case in APP_MUTATIONS]
             + [(CHECK_UI, "ui", *case) for case in UI_MUTATIONS])
    ran = 0
    for linter, kind, name, mutate, expected in cases:
        if wanted and not any(word in name.lower() for word in wanted):
            continue
        ran += 1
        workdir = Path(tempfile.mkdtemp(prefix="mutation-"))
        app = workdir / "my-app"
        try:
            shutil.copytree(STARTER, app,
                            ignore=shutil.ignore_patterns("__pycache__",
                                                          ".pytest_cache"))
            mutate(app)
            target = app if kind == "app" else app / "src" / "static"
            done = run(linter, target)
            if done.returncode == 0:
                problems.append("%s SURVIVED - %s said `clean` on it. That rule is "
                                "not being checked." % (name, linter.name))
            elif expected not in done.stdout:
                problems.append("%s: %s went red but did not say %r. It said:\n%s"
                                % (name, linter.name, expected, done.stdout.strip()))
            else:
                print("ok  %s" % name)
        except AssertionError as exc:
            problems.append("%s: could not apply the mutation - %s" % (name, exc))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    for problem in problems:
        print("x %s" % problem)
    print("%d of %d mutation(s) survived" % (len(problems), ran) if problems
          else "%d mutations, all caught" % ran)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

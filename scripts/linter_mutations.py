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


def a_typo_in_runtime(app: Path) -> None:
    # `runtime` is not strict, so this validates, deploys green and is
    # silently ignored - a debugging session rather than a 422.
    patch_manifest(app, lambda data: data["runtime"].update(prot=8000))


def agent_path_in_api_routes(app: Path) -> None:
    def mutate(data):
        data["runtime"]["api_routes"].append({"path": "/agent/*", "auth": "user"})
    patch_manifest(app, mutate)


def a_relative_icon(app: Path) -> None:
    patch_manifest(app, lambda data: data["frontend"].update(icon="icons/app.svg"))


def a_todo_description(app: Path) -> None:
    patch_manifest(app, lambda data: data["metadata"].update(
        description="TODO: describe my-app"))


def a_baked_deploy_token(app: Path) -> None:
    edit(app / "Dockerfile", "ENV PYTHONUNBUFFERED=1",
         "ENV MANAURUM_V2_TOKEN=mna_9f3c1de77a04b26e5c81\nENV PYTHONUNBUFFERED=1")


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
    ("manifest: a typo in runtime", a_typo_in_runtime,
     "runtime.prot is not a key the platform reads"),
    ("manifest: /agent/* declared in api_routes", agent_path_in_api_routes,
     "configures nothing while looking like it did"),
    ("manifest: a relative frontend.icon", a_relative_icon,
     "painted into the tile as that literal string"),
    ("manifest: the starter's TODO description", a_todo_description,
     "still the starter's placeholder"),
    ("secrets: a deploy token baked into the image", a_baked_deploy_token,
     "live mna_9f3c... token"),
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


# ── check_repo.py, over a copy of the whole repository ──────────────────────
# The checker that guards the documents had no negative test at all, and its
# own docstring tells the story of a regex silently disabled by one byte. So
# it gets the same treatment: break one check, demand red - and, just as
# importantly, write the prose a person would legitimately write and demand
# that it stays GREEN. Every false positive below was reproduced before it
# was fixed; each is now a test that it stays fixed.

CHECK_REPO = ROOT / "scripts" / "check_repo.py"
README = "README.md"
APP_SKILL = "skills/manaurum-app/SKILL.md"


def append(repo: Path, name: str, text: str) -> None:
    with (repo / name).open("a", encoding="utf-8") as handle:
        handle.write("\n" + text + "\n")


def version_drift(repo: Path) -> None:
    edit(repo / README, "**Version ", "**Version 1.0.0.** Once: **Version ")


def a_path_that_is_not_there(repo: Path) -> None:
    append(repo, README, "See `templates/ghost-helper.py` for the details.")


def a_heading_that_is_not_there(repo: Path) -> None:
    append(repo, README, 'Read `skills/manaurum-app/SKILL.md` -> "The Fourth Rule".')


def a_step_that_is_not_there(repo: Path) -> None:
    append(repo, README, "The screenshots are Step 9, and they are mandatory.")


def a_test_count(repo: Path) -> None:
    append(repo, README, "The starter suite is 27 tests and runs offline.")


def a_control_byte(repo: Path) -> None:
    path = repo / README
    data = path.read_bytes()
    path.write_bytes(data + b"\nA stray byte: \x08 right here.\n")


def a_fixed_tmp_path(repo: Path) -> None:
    append(repo, APP_SKILL, "```bash\ntar cf /tmp/ctx.tar .\n```")


def an_ungitignored_token_file(repo: Path) -> None:
    # gitignore's last-match-wins: `.env*` above, un-ignored here.
    append(repo, "templates/v2-starter/.gitignore", "!.env.manaurum")


def a_flag_that_does_not_exist(repo: Path) -> None:
    append(repo, README, "```bash\npython preview.py --app x --nope 1\n```")


def a_deleted_paired_claim(repo: Path) -> None:
    path = repo / APP_SKILL
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("drop the flag", "keep the flag"), encoding="utf-8")


def an_unregistered_open_ticket(repo: Path) -> None:
    append(repo, README, "The rewrite is blocked on MAN-9999 and has not landed.")


def a_stale_claims_line(repo: Path) -> None:
    path = repo / "scripts" / "open-claims.txt"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("2026-09-09", "not-a-date", 1), encoding="utf-8")


# The must-stay-green half.


def teaching_the_tmp_lesson(repo: Path) -> None:
    append(repo, README,
           "Never write the build context to `/tmp/ctx.tar` - /tmp is shared.\n"
           "Do not use /tmp/deploy.json either.")


def a_per_run_tmp_path(repo: Path) -> None:
    append(repo, README, "```bash\nrm -f /tmp/ctx-$$.tar\n```")


def an_instruction_to_write_tests(repo: Path) -> None:
    append(repo, README, "Write two tests for every capability you use.")


def a_ticket_that_is_done(repo: Path) -> None:
    append(repo, README,
           "MAN-2532 is Done, but it was blocked on a missing runner for two days.")


def a_path_in_the_readers_project(repo: Path) -> None:
    append(repo, README,
           "The scaffold lives in `scripts/deploy.sh` in YOUR project, not in this one.")


def a_binary_file(repo: Path) -> None:
    (repo / "templates" / "sample.bin").write_bytes(b"PK\x03\x04\x00\x01\x02\x03rest")


REPO_MUTATIONS = [
    ("repo: a version that disagrees", version_drift, "says version 1.0.0"),
    ("repo: a documented path that is not there", a_path_that_is_not_there,
     "ghost-helper.py` does not exist"),
    ("repo: a cited heading that is not there", a_heading_that_is_not_there,
     "no heading matching"),
    ("repo: a Step that does not exist", a_step_that_is_not_there, "Step 9"),
    ("repo: a hardcoded test count", a_test_count, "hardcoded test count"),
    ("repo: a control byte", a_control_byte, "control byte 0x08"),
    ("repo: a fixed /tmp path", a_fixed_tmp_path, "/tmp is shared between sessions"),
    ("repo: the token file un-gitignored", an_ungitignored_token_file,
     "nothing here matches `.env.manaurum`"),
    ("repo: a documented flag the tool rejects", a_flag_that_does_not_exist,
     "does not accept --nope"),
    ("repo: a paired claim contradicted", a_deleted_paired_claim,
     "--virtual-time-budget"),
    ("repo: an open ticket in no register", an_unregistered_open_ticket,
     "MAN-9999 is still open"),
    ("repo: a claims line with no date", a_stale_claims_line,
     "no readable YYYY-MM-DD"),
    ("repo-green: teaching the /tmp lesson", teaching_the_tmp_lesson, None),
    ("repo-green: a per-run /tmp path", a_per_run_tmp_path, None),
    ("repo-green: an instruction to write tests", an_instruction_to_write_tests, None),
    ("repo-green: a ticket that is Done", a_ticket_that_is_done, None),
    ("repo-green: a path in the reader's project", a_path_in_the_readers_project, None),
    ("repo-green: a binary file", a_binary_file, None),
]


def run(linter: Path, target: Path):
    return subprocess.run([sys.executable, str(linter), str(target)],
                          capture_output=True, text=True)


IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git",
                                ".venv", "venv", "*.pyc")


def sanity(problems: list) -> None:
    """The unmutated starter has to be clean, or every result below is noise."""
    for linter, target in ((CHECK_APP, STARTER),
                           (CHECK_UI, STARTER / "src" / "static")):
        done = run(linter, target)
        if done.returncode != 0:
            problems.append("%s is not clean on the untouched starter, so no "
                            "mutation result below means anything:\n%s"
                            % (linter.name, done.stdout.strip()))


def run_repo_mutation(name, mutate, expected, problems: list) -> None:
    """One mutation against a COPY of the whole repository.

    A copy, because check_repo.py resolves its root from its own `__file__` -
    which is also what makes this honest: the copy's checker reads the copy's
    documents, exactly as it would on a runner.
    """
    workdir = Path(tempfile.mkdtemp(prefix="mutation-repo-"))
    repo = workdir / "repo"
    try:
        shutil.copytree(ROOT, repo, ignore=IGNORE)
        mutate(repo)
        done = run_no_arg(repo / "scripts" / "check_repo.py")
        if expected is None:
            if done.returncode != 0:
                problems.append("%s: check_repo.py went RED on prose it should "
                                "accept. It said:\n%s" % (name, done.stdout.strip()))
            else:
                print("ok  %s" % name)
        elif done.returncode == 0:
            problems.append("%s SURVIVED - check_repo.py said `clean` on it. That "
                            "rule is not being checked." % name)
        elif expected not in done.stdout:
            problems.append("%s: check_repo.py went red but did not say %r. It "
                            "said:\n%s" % (name, expected, done.stdout.strip()))
        else:
            print("ok  %s" % name)
    except AssertionError as exc:
        problems.append("%s: could not apply the mutation - %s" % (name, exc))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run_no_arg(script: Path):
    return subprocess.run([sys.executable, str(script)],
                          capture_output=True, text=True)


def main() -> int:
    wanted = [arg.lower() for arg in sys.argv[1:]]
    problems = []
    sanity(problems)
    if problems:
        for problem in problems:
            print("x %s" % problem)
        return 1

    ran = 0
    for name, mutate, expected in REPO_MUTATIONS:
        if wanted and not any(word in name.lower() for word in wanted):
            continue
        ran += 1
        run_repo_mutation(name, mutate, expected, problems)

    cases = ([(CHECK_APP, "app", *case) for case in APP_MUTATIONS]
             + [(CHECK_UI, "ui", *case) for case in UI_MUTATIONS])
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

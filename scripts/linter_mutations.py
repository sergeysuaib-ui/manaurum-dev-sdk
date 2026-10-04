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
import os
import re
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


def concurrently_sharing_a_file(app: Path) -> None:
    # MAN-2624. The shape an author lands on by following the validator's own
    # advice: it refuses a plain CREATE INDEX and says "use CONCURRENTLY", so
    # they add the word to the file they already have. The deploy then refuses
    # THAT, because a CONCURRENTLY file has to run outside a transaction and
    # everything else in it needs one. Until this mutation existed the rule
    # had no local coverage in either checker.
    directory = app / "migrations"
    directory.mkdir(exist_ok=True)
    (directory / "0001_init.sql").write_text(
        "CREATE TABLE note (id text primary key);\n", encoding="utf-8")
    (directory / "0002_add_index.sql").write_text(
        "ALTER TABLE note ADD COLUMN body text;\n"
        "CREATE INDEX CONCURRENTLY note_body_idx ON note (body);\n",
        encoding="utf-8")


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
    # The deploy would 422 this (MAN-1899); the linter says so before upload.
    patch_manifest(app, lambda data: data["runtime"].update(prot=8000))


def guest_pages_and_a_health_path(app: Path) -> None:
    # Both keys are in the schema and both are read - the gateway reads
    # `public_paths`, the post-deploy probe reads `health_path`. check_app.py
    # 2.11.0-3.0.0 called them keys the platform does not read, so every app
    # with a guest page got a false red (Planning Poker, 2026-10).
    def mutate(data):
        data["runtime"]["public_paths"] = ["/g/*", "/invite"]
        data["runtime"]["health_path"] = "/healthz"
        data["runtime"]["resources"] = {"memory_mb": 256, "cpu_millicores": 250}
    patch_manifest(app, mutate)


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
    # The shape Core mints: mna_<12 hex>_<url-safe secret>. Until 3.2.0 this
    # mutation planted `mna_9f3c1de77a04b26e5c81`, a shape no token has, and
    # the rule it tested matched only that - so it never fired on a real one.
    edit(app / "Dockerfile", "ENV PYTHONUNBUFFERED=1",
         "ENV MANAURUM_V2_TOKEN=mna_3f9c1de77a04_Xq2p-8Wn_Lk4sVb0Rt7yUe1aZc9Md6Fh"
         "\nENV PYTHONUNBUFFERED=1")


def a_tenant_token_in_source(app: Path) -> None:
    # mnu_<env>_<32 url-safe>: the tenant token for MCP clients and Drive upload.
    edit(app / "src" / "main.py", "app = FastAPI(",
         'DRIVE_TOKEN = "mnu_prod_Hk3-Pq8_vB2nM5xL0wZ7rT4yC1eD6gJ9"\n\napp = FastAPI(')


# ── 3.7.0: the gateway's own matching, routers, the contract ────────────────


def a_rule_with_a_parameter(app: Path) -> None:
    # The gateway matches a rule literally: `{note_id}` is not a parameter.
    edit(app / "src" / "main.py", '@app.get("/api/me")',
         '@app.get("/api/notes/{note_id}")\nasync def one_note(note_id: str) -> dict:\n'
         '    return {}\n\n\n@app.get("/api/me")')
    patch_manifest(app, lambda data: data["runtime"]["api_routes"].append(
        {"path": "/api/notes/{note_id}", "auth": "user"}))


def a_rule_with_a_bare_star(app: Path) -> None:
    def mutate(data):
        for entry in data["runtime"]["api_routes"]:
            if entry["path"] == "/api/notes":
                entry["path"] = "/api/notes*"
    patch_manifest(app, mutate)


def a_router_mounted_with_a_prefix(app: Path) -> None:
    # Served at /api/extra/items: the router's prefix plus the route's path.
    (app / "src" / "extra.py").write_text(
        "from fastapi import APIRouter\n\nrouter: APIRouter = APIRouter(prefix=\"/api/extra\")\n\n\n"
        "@router.get(\"/items\")\nasync def items() -> dict:\n    return {}\n",
        encoding="utf-8")
    edit(app / "src" / "main.py", "from src import agent_routes",
         "from src import agent_routes, extra")
    edit(app / "src" / "main.py", "app.include_router(agent_routes.router)",
         "app.include_router(agent_routes.router)\napp.include_router(extra.router)")


def a_router_mounted_and_declared(app: Path) -> None:
    a_router_mounted_with_a_prefix(app)
    patch_manifest(app, lambda data: data["runtime"]["api_routes"].append(
        {"path": "/api/extra/items", "auth": "user"}))


def an_auth_check_only_in_a_comment(app: Path) -> None:
    edit(app / "src" / "agent_routes.py",
         'async def read_my_note(claims: UserContextClaims = Depends(auth_claims)) -> dict:',
         'async def read_my_note() -> dict:  # auth_claims, verify_user_context\n'
         '    claims = None')


def an_optional_claims_parameter(app: Path) -> None:
    edit(app / "src" / "agent_routes.py",
         'async def read_my_note(claims: UserContextClaims = Depends(auth_claims)) -> dict:',
         'async def read_my_note(claims: UserContextClaims | None = None) -> dict:')


def auth_on_the_router(app: Path) -> None:
    # The idiomatic FastAPI form: one dependency on the router covers all.
    edit(app / "src" / "agent_routes.py",
         'router = APIRouter(prefix="/agent", tags=["agent"])',
         'router = APIRouter(prefix="/agent", tags=["agent"], '
         'dependencies=[Depends(auth_claims)])')
    edit(app / "src" / "agent_routes.py",
         'async def read_my_note(claims: UserContextClaims = Depends(auth_claims)) -> dict:',
         'async def read_my_note() -> dict:\n    claims = None')


def a_capability_that_does_not_exist(app: Path) -> None:
    def mutate(data):
        data["requires_capabilities"].append({"name": "os.kv.list", "version": "1"})
    patch_manifest(app, mutate)
    edit(app / "src" / "capability.py", "def note_key(user_id: str) -> str:",
         'LIST = "os.kv.list"\n\n\ndef note_key(user_id: str) -> str:')


def a_capability_called_by_url(app: Path) -> None:
    edit(app / "src" / "capability.py", "def note_key(user_id: str) -> str:",
         'def list_files(base: str) -> str:\n'
         '    return f"{base}/api/capability/os.files.list"\n\n\n'
         'def note_key(user_id: str) -> str:')


def an_optional_capability_that_is_called(app: Path) -> None:
    def mutate(data):
        data["optional_capabilities"] = [
            entry for entry in data["requires_capabilities"]
            if entry.get("name") == "os.kv.get"]
        data["requires_capabilities"] = [
            entry for entry in data["requires_capabilities"]
            if entry.get("name") != "os.kv.get"]
    patch_manifest(app, mutate)


def a_capability_named_in_the_readme(app: Path) -> None:
    readme = app / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8")
                      + "\nLater this may call `\"os.files.upload\"`.\n", encoding="utf-8")


def a_root_key_typo(app: Path) -> None:
    patch_manifest(app, lambda data: data.update(description="Notes"))


def a_reserved_slug(app: Path) -> None:
    patch_manifest(app, lambda data: data.update(app_id="api"))


def a_slug_the_deploy_refuses(app: Path) -> None:
    patch_manifest(app, lambda data: data.update(app_id="My_App"))


def a_write_verb_declared_read(app: Path) -> None:
    def mutate(data):
        for entry in data["agent_capabilities"]:
            if entry["name"] == "save_my_note":
                entry["is_write"] = False
    patch_manifest(app, mutate)


def a_tool_name_too_long(app: Path) -> None:
    def mutate(data):
        for entry in data["agent_capabilities"]:
            if entry["name"] == "read_my_note":
                entry["name"] = "read_my_note_with_every_detail_the_user_ever_wrote_x"
    patch_manifest(app, mutate)


def an_entrypoint_on_a_hosted_app(app: Path) -> None:
    patch_manifest(app, lambda data: data["runtime"].update(
        entrypoint="https://example.com/"))


def a_transaction_in_a_migration(app: Path) -> None:
    directory = app / "migrations"
    directory.mkdir(exist_ok=True)
    (directory / "0001_init.sql").write_text(
        "BEGIN;\nCREATE TABLE note (id text primary key);\nCOMMIT;\n", encoding="utf-8")


def an_extension_in_a_migration(app: Path) -> None:
    directory = app / "migrations"
    directory.mkdir(exist_ok=True)
    (directory / "0001_init.sql").write_text(
        "CREATE EXTENSION IF NOT EXISTS vector;\n", encoding="utf-8")


def an_uppercase_sql_suffix(app: Path) -> None:
    directory = app / "migrations"
    directory.mkdir(exist_ok=True)
    (directory / "0001_init.SQL").write_text(
        "CREATE TABLE note (id text primary key);\n", encoding="utf-8")


def migrations_over_64_kib(app: Path) -> None:
    directory = app / "migrations"
    directory.mkdir(exist_ok=True)
    rows = "".join("INSERT INTO note VALUES ('%06d');\n" % i for i in range(2500))
    (directory / "0001_init.sql").write_text(
        "CREATE TABLE note (id text primary key);\n" + rows, encoding="utf-8")


def a_migration(app: Path, sql: str, name: str = "0001_init.sql") -> None:
    directory = app / "migrations"
    directory.mkdir(exist_ok=True)
    (directory / name).write_text(sql, encoding="utf-8")


def a_set_in_a_migration(app: Path) -> None:
    a_migration(app, "CREATE TABLE note (id text primary key);\nSET search_path = public;\n")


def a_copy_in_a_migration(app: Path) -> None:
    a_migration(app, "CREATE TABLE note (id text primary key);\nCOPY note FROM stdin;\n")


def a_rename_in_a_migration(app: Path) -> None:
    a_migration(app, "CREATE TABLE note (id text primary key);\nALTER TABLE note RENAME TO notes;\n")


def a_drop_index_in_a_migration(app: Path) -> None:
    a_migration(app, "CREATE TABLE note (id text primary key);\nDROP INDEX note_idx;\n")


def a_plpgsql_trigger_function(app: Path) -> None:
    # MUST STAY GREEN. The `updated_at` trigger every CRUD app has. Split on
    # `;`, its `END IF;` and `END;` read as transaction control; the deploy
    # parses the body as one CREATE FUNCTION in a trusted language and accepts.
    a_migration(app, (
        "CREATE TABLE note (id text primary key, updated_at timestamptz);\n"
        "CREATE OR REPLACE FUNCTION touch() RETURNS trigger AS $$\n"
        "BEGIN\n  IF NEW.updated_at IS NULL THEN\n    NEW.updated_at := now();\n"
        "  END IF;\n  RETURN NEW;\nEND;\n$$ LANGUAGE plpgsql;\n"
        "CREATE TRIGGER note_touch BEFORE UPDATE ON note\n"
        "  FOR EACH ROW EXECUTE FUNCTION touch();\n"))


def a_string_that_says_rename(app: Path) -> None:
    # MUST STAY GREEN. Words in a string literal are data, not statements.
    a_migration(app, "CREATE TABLE note (id text primary key, body text);\n"
                     "INSERT INTO note VALUES ('1', 'Rename it, truncate it, revoke it');\n")


def a_drop_extension_marked_breaking(app: Path) -> None:
    # MUST STAY GREEN. A DropStmt, so destructive, which `breaking` allows -
    # not forbidden like CREATE/ALTER EXTENSION.
    a_migration(app, "DROP EXTENSION IF EXISTS vector;\n")
    patch_manifest(app, lambda data: data.update(migration={"breaking": True}))


def a_subdirectory_under_migrations(app: Path) -> None:
    # MUST STAY GREEN. The deploy skips subdirectories; a note, not a failure.
    a_migration(app, "CREATE TABLE note (id text primary key);\n")
    (app / "migrations" / "archive").mkdir()
    (app / "migrations" / "archive" / "0000_old.sql").write_text(
        "CREATE TABLE old (id text);\n", encoding="utf-8")


def a_byo_app_with_permissions(app: Path) -> None:
    def mutate(data):
        data["runtime"].update(mode="byo", entrypoint="https://example.com/")
        data["permissions"] = ["camera"]
    patch_manifest(app, mutate)


def a_typo_under_data(app: Path) -> None:
    patch_manifest(app, lambda data: data["data"].update(shard=True))


def a_typo_under_offline(app: Path) -> None:
    patch_manifest(app, lambda data: data.update(offline={"featrues": ["save"]}))


def a_uuid_for_a_slug(app: Path) -> None:
    # Starts with a letter and fits the slug pattern: only the UUID rule sees it.
    patch_manifest(app, lambda data: data.update(app_id="a0b6f6d2-1c1a-4c9e-9a7e-3f0e9d5b2a11"))


def a_prefix_on_the_include(app: Path) -> None:
    # Served at /api/extra/items: the prefix is on include_router, not the router.
    (app / "src" / "extra.py").write_text(
        "from fastapi import APIRouter\n\nrouter: APIRouter = APIRouter()\n\n\n"
        "@router.get(\"/items\")\nasync def items() -> dict:\n    return {}\n",
        encoding="utf-8")
    edit(app / "src" / "main.py", "from src import agent_routes",
         "from src import agent_routes, extra")
    edit(app / "src" / "main.py", "app.include_router(agent_routes.router)",
         "app.include_router(agent_routes.router)\n"
         "app.include_router(extra.router, prefix=\"/api/extra\")")


def auth_on_the_decorator(app: Path) -> None:
    # MUST STAY GREEN. `dependencies=` on the route decorator.
    edit(app / "src" / "agent_routes.py", '@router.post("/read_my_note")',
         '@router.post("/read_my_note", dependencies=[Depends(auth_claims)])')
    edit(app / "src" / "agent_routes.py",
         'async def read_my_note(claims: UserContextClaims = Depends(auth_claims)) -> dict:',
         'async def read_my_note() -> dict:\n    claims = None')


def auth_on_the_include(app: Path) -> None:
    # MUST STAY GREEN. `dependencies=` on the include_router that mounts it.
    edit(app / "src" / "main.py", "from src import agent_routes",
         "from fastapi import Depends\nfrom src.auth import auth_claims\n"
         "from src import agent_routes")
    edit(app / "src" / "main.py", "app.include_router(agent_routes.router)",
         "app.include_router(agent_routes.router, dependencies=[Depends(auth_claims)])")
    edit(app / "src" / "agent_routes.py",
         'async def read_my_note(claims: UserContextClaims = Depends(auth_claims)) -> dict:',
         'async def read_my_note() -> dict:\n    claims = None')


def an_auth_mode_that_does_not_exist(app: Path) -> None:
    patch_manifest(app, lambda data: data["runtime"]["api_routes"][0].update(auth="maybe"))


def an_optional_route(app: Path) -> None:
    # MUST STAY GREEN. MAN-3200's third mode: the enum comes from the contract.
    patch_manifest(app, lambda data: data["runtime"]["api_routes"][0].update(auth="optional"))


def an_oauth2_scheme_on_an_agent_handler(app: Path) -> None:
    # It has "auth" in its name and verifies nothing: it reads Authorization,
    # which the gateway strips and the runtime never sends to /agent/*.
    edit(app / "src" / "agent_routes.py",
         'router = APIRouter(prefix="/agent", tags=["agent"])',
         'router = APIRouter(prefix="/agent", tags=["agent"])\n'
         'from fastapi.security import OAuth2PasswordBearer\n'
         'oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")')
    edit(app / "src" / "agent_routes.py",
         'async def read_my_note(claims: UserContextClaims = Depends(auth_claims)) -> dict:',
         'async def read_my_note(token: str = Depends(oauth2_scheme)) -> dict:\n'
         '    claims = None')


def a_begin_atomic_function(app: Path) -> None:
    # MUST STAY GREEN. A SQL-standard body: its `;` and END are inside one
    # CreateFunctionStmt, not transaction control.
    a_migration(app, "CREATE TABLE note (id text primary key);\n"
                     "CREATE FUNCTION note_count() RETURNS bigint LANGUAGE sql\n"
                     "BEGIN ATOMIC\n  SELECT count(*) FROM note;\nEND;\n")


def a_migration_with_a_bom(app: Path) -> None:
    directory = app / "migrations"
    directory.mkdir(exist_ok=True)
    (directory / "0001_init.sql").write_bytes(
        b"\xef\xbb\xbfCREATE TABLE note (id text primary key);\n")


def a_drop_extension_not_marked_breaking(app: Path) -> None:
    a_migration(app, "DROP EXTENSION IF EXISTS vector;\n")


def an_annotated_oauth2_scheme(app: Path) -> None:
    # Annotated, in a try, and imported under a name that says "auth": still a
    # scheme, still verifies nothing on /agent/*.
    (app / "src" / "security.py").write_text(
        "from fastapi.security import OAuth2PasswordBearer\n\ntry:\n"
        "    oauth2_scheme: OAuth2PasswordBearer = OAuth2PasswordBearer(tokenUrl=\"t\")\n"
        "except Exception:\n    raise\n", encoding="utf-8")
    edit(app / "src" / "agent_routes.py",
         'router = APIRouter(prefix="/agent", tags=["agent"])',
         'router = APIRouter(prefix="/agent", tags=["agent"])\n'
         'from src.security import oauth2_scheme as auth_scheme')
    edit(app / "src" / "agent_routes.py",
         'async def read_my_note(claims: UserContextClaims = Depends(auth_claims)) -> dict:',
         'async def read_my_note(token: str = Depends(auth_scheme)) -> dict:\n'
         '    claims = None')


# ── Rules older than the mutation suite (audit Н1) ──────────────────────────


def a_module_that_does_not_parse(app: Path) -> None:
    (app / "src" / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")


def no_dockerfile(app: Path) -> None:
    (app / "Dockerfile").unlink()


def a_migration_with_no_number(app: Path) -> None:
    a_migration(app, "CREATE TABLE note (id text primary key);\n", name="init.sql")


def two_migrations_with_one_number(app: Path) -> None:
    a_migration(app, "CREATE TABLE note (id text primary key);\n", name="0001_init.sql")
    a_migration(app, "ALTER TABLE note ADD COLUMN body text;\n", name="0001_body.sql")


def a_manifest_that_does_not_parse(app: Path) -> None:
    path = app / "manifest.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n,", encoding="utf-8")


# ── The Postgres recipe's rules (3.13.0, from PR #27) ───────────────────────

RECIPE = ROOT / "templates" / "recipes" / "postgres"


def a_generated_column_on_array_to_string(app: Path) -> None:
    # The obvious way to index tags, and Postgres refuses it at apply time,
    # per tenant, after the deploy's validator has passed the file.
    a_migration(app, (
        "CREATE TABLE doc (id text primary key, tags text[] NOT NULL DEFAULT '{}',\n"
        "  search tsvector GENERATED ALWAYS AS (\n"
        "    to_tsvector('english', array_to_string(tags, ' '))) STORED);\n"))


def a_generated_column_without_a_configuration(app: Path) -> None:
    # One argument reads default_text_search_config, so it is STABLE. Judged
    # with the deploy's validator importable too: this rule is not one the
    # validator makes, so deferring to it must not switch this one off.
    a_migration(app, (
        "CREATE TABLE doc (id text primary key, title text);\n"
        "ALTER TABLE doc ADD COLUMN search tsvector\n"
        "  GENERATED ALWAYS AS (to_tsvector(coalesce(title, ''))) STORED;\n"))


def a_generated_column_with_a_configuration_column(app: Path) -> None:
    # MUST STAY GREEN. Two arguments is the IMMUTABLE form, whatever the
    # first one is - a regconfig column included. A rule that only looked for
    # a quote after the bracket went red here.
    a_migration(app, (
        "CREATE TABLE doc (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,\n"
        "  lang regconfig NOT NULL DEFAULT 'english', body text,\n"
        "  search tsvector GENERATED ALWAYS AS (\n"
        "    to_tsvector(lang, coalesce(body, ''))) STORED);\n"))


def the_postgres_recipe_copied_in(app: Path) -> None:
    # MUST STAY GREEN. What the skill tells an agent to copy: the recipe's
    # db.py, search.py and migrations, in an app that dropped the starter's
    # `"data": {"none": true}`. Holds the recipe to the linter it ships with.
    patch_manifest(app, lambda data: data.pop("data"))
    shutil.copy(RECIPE / "db.py", app / "src" / "db.py")
    shutil.copy(RECIPE / "search.py", app / "src" / "search.py")
    shutil.copytree(RECIPE / "migrations", app / "migrations")


SET_IN_INIT = '''"""Database pool."""
import os

import asyncpg

_pool = None


async def _on_connect(conn):
    await conn.execute(f'SET search_path TO "{os.environ["MANAURUM_TARGET_SCHEMA"]}", public')


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], init=_on_connect)
    return _pool
'''


def search_path_set_in_pool_init(app: Path) -> None:
    patch_manifest(app, lambda data: data.pop("data"))
    (app / "src" / "db.py").write_text(SET_IN_INIT, encoding="utf-8")


def search_path_set_in_pool_setup(app: Path) -> None:
    # MUST STAY GREEN. MAN-1443's fix in libi and family-space-v2: codecs in
    # init=, the SET in setup=, which runs on every acquire. `init=` and
    # `SET search_path` in one file is not the bug; the SET inside init is.
    patch_manifest(app, lambda data: data.pop("data"))
    (app / "src" / "db.py").write_text(
        SET_IN_INIT.replace(
            "    await conn.execute(f'SET search_path",
            "    await conn.set_type_codec('jsonb', encoder=str, decoder=str,\n"
            "                              schema='pg_catalog')\n\n\n"
            "async def _on_acquire(conn):\n"
            "    await conn.execute(f'SET search_path").replace(
            "init=_on_connect)",
            "init=_on_connect,\n"
            "                                         setup=_on_acquire)"),
        encoding="utf-8")


def a_generated_column_on_concat(app: Path) -> None:
    # concat() looks like || and is STABLE: it formats arguments of any type.
    a_migration(app, (
        "CREATE TABLE person (id text primary key, first text, last text,\n"
        "  full_name text GENERATED ALWAYS AS (concat_ws(' ', first, last)) STORED);\n"))


def a_generated_column_on_now(app: Path) -> None:
    # "When was this last touched" as a generated column. The fix is a
    # trigger, and the finding has to say so rather than "wrap it".
    a_migration(app, (
        "CREATE TABLE note (id text primary key, body text,\n"
        "  touched_at timestamptz GENERATED ALWAYS AS (now()) STORED);\n"))


def search_path_in_init_and_in_server_settings(app: Path) -> None:
    # MUST STAY GREEN. Redundant, not broken: server_settings is what RESET
    # ALL restores, so the SET in init= loses nothing.
    patch_manifest(app, lambda data: data.pop("data"))
    (app / "src" / "db.py").write_text(SET_IN_INIT.replace(
        "init=_on_connect)",
        "init=_on_connect,\n"
        "            server_settings={\"search_path\": "
        "os.environ[\"MANAURUM_TARGET_SCHEMA\"]})"), encoding="utf-8")


def set_local_inside_a_transaction(app: Path) -> None:
    # MUST STAY GREEN. init= registers codecs and runs a one-off check in a
    # transaction with SET LOCAL, which ends with that transaction by design
    # - nothing for RESET ALL to take away.
    patch_manifest(app, lambda data: data.pop("data"))
    anchor = ("    await conn.execute(f'SET search_path TO "
              "\"{os.environ[\"MANAURUM_TARGET_SCHEMA\"]}\", public')\n")
    if anchor not in SET_IN_INIT:
        raise AssertionError("anchor not found in SET_IN_INIT")
    (app / "src" / "db.py").write_text(SET_IN_INIT.replace(
        anchor,
        "    await conn.set_type_codec('jsonb', encoder=str, decoder=str,\n"
        "                              schema='pg_catalog')\n"
        "    async with conn.transaction():\n"
        "        await conn.execute(\"SET LOCAL statement_timeout = '5s'\")\n"
        "        await conn.fetchval('SELECT 1')\n"), encoding="utf-8")


def database_url_named_in_a_comment(app: Path) -> None:
    # MUST STAY GREEN. Under data.none, saying that the app does NOT read
    # the variable is not reading it.
    edit(app / "src" / "capability.py", '"""',
         '"""We never read os.environ["DATABASE_URL"] here: data.none injects none.\n\n')
    path = app / "src" / "capability.py"
    path.write_text(path.read_text(encoding="utf-8")
                    + '\n# os.getenv("DATABASE_URL") would be None under data.none.\n',
                    encoding="utf-8")


def database_url_with_no_database(app: Path) -> None:
    # The starter's manifest says `"data": {"none": true}`; the app grew a
    # database anyway. Deploys green, and the first query has no DSN.
    (app / "src" / "db.py").write_text(SET_IN_INIT.replace(
        "init=_on_connect", "server_settings={'search_path': 'x'}"), encoding="utf-8")


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
    # Two acceptable wordings per rule: `check_app.py` defers to the deploy's
    # own AST validator when a usable `manaurum-cli` is importable and falls
    # back to its built-in pattern list when it is not (MAN-2624), and the two
    # phrase the same verdict differently. Either is a pass; silence is not.
    ("migrations: destructive DDL, no migration.breaking", destructive_migration,
     ("DROP without manifest.migration.breaking", "destructive - DROP")),
    ("migrations: an anonymous DO $$ block", anonymous_do_block,
     "a DO block"),
    # The fourth element: this rule cannot be decided from the text - the word
    # appears in comments, string literals and quoted identifiers, and every
    # text test gets at least one of those wrong in both directions (the
    # executor learned that in MAN-2510). `check_app.py` therefore asks the
    # real validator or reports the rule unchecked, so the mutation runs
    # against a stub validator rather than against a guess.
    ("migrations: CONCURRENTLY sharing a file", concurrently_sharing_a_file,
     "must contain nothing else", True),
    ("migrations: a file that is not .sql", migration_that_is_not_sql,
     "not a .sql file"),
    ("migrations: numbers of different widths", migrations_out_of_order,
     "zero-padded"),
    ("manifest: a typo in runtime", a_typo_in_runtime,
     "runtime.prot is not a key the platform reads"),
    ("manifest: public_paths, health_path and resources are real keys",
     guest_pages_and_a_health_path, None),
    ("manifest: /agent/* declared in api_routes", agent_path_in_api_routes,
     "configures nothing while looking like it did"),
    ("manifest: a relative frontend.icon", a_relative_icon,
     "painted into the tile as that literal string"),
    ("manifest: the starter's TODO description", a_todo_description,
     "still the starter's placeholder"),
    ("secrets: a deploy token baked into the image", a_baked_deploy_token,
     "live mna_3f9c... token"),
    ("secrets: a tenant token in the source", a_tenant_token_in_source,
     "live mnu_prod... token"),
    ("routes: a {param} in a rule is matched literally", a_rule_with_a_parameter,
     "matches it literally"),
    ("routes: a bare trailing * is not a wildcard", a_rule_with_a_bare_star,
     "matches it literally"),
    ("routes: a router mounted with a prefix", a_router_mounted_with_a_prefix,
     "GET /api/extra/items is served but no runtime.api_routes rule covers it"),
    ("routes: a router mounted with a prefix, declared", a_router_mounted_and_declared,
     None),
    ("agent: the auth name only in a comment", an_auth_check_only_in_a_comment,
     "no user-context verification"),
    ("agent: an Optional claims parameter with no Depends", an_optional_claims_parameter,
     "no user-context verification"),
    ("agent: auth on the router stays green", auth_on_the_router, None),
    ("capabilities: a name the platform does not register",
     a_capability_that_does_not_exist, "not a capability the platform registers"),
    ("capabilities: called through a URL", a_capability_called_by_url,
     "calls os.files.list but"),
    ("capabilities: an optional capability that is called",
     an_optional_capability_that_is_called, None),
    ("capabilities: a name in the README is not a call",
     a_capability_named_in_the_readme, None),
    ("manifest: a key that is not a root key", a_root_key_typo,
     "description is not a root key"),
    ("manifest: a reserved slug", a_reserved_slug, "is reserved for the platform"),
    ("manifest: a slug the deploy refuses", a_slug_the_deploy_refuses,
     "not a slug the deploy accepts"),
    ("manifest: a write verb declared is_write false", a_write_verb_declared_read,
     "write verb in its name"),
    ("manifest: an Assistant tool name too long", a_tool_name_too_long,
     "silently drops it"),
    ("manifest: runtime.entrypoint on a hosted app", an_entrypoint_on_a_hosted_app,
     "runtime.entrypoint on a hosted app"),
    ("migrations: BEGIN/COMMIT in a file", a_transaction_in_a_migration,
     ("transaction control - forbidden", "BEGIN/COMMIT/SAVEPOINT")),
    ("migrations: CREATE EXTENSION", an_extension_in_a_migration,
     ("an extension (use data.extensions) - forbidden", "CREATE EXTENSION —")),
    ("migrations: an uppercase .SQL suffix", an_uppercase_sql_suffix,
     "case-sensitive"),
    ("migrations: more than 64 KiB in all", migrations_over_64_kib, "64 KiB"),
    ("migrations: SET", a_set_in_a_migration, ("SET - forbidden", "SET — session")),
    ("migrations: COPY", a_copy_in_a_migration, ("COPY - forbidden", "COPY — file")),
    ("migrations: ALTER TABLE ... RENAME", a_rename_in_a_migration,
     ("RENAME without manifest.migration.breaking", "destructive - RENAME")),
    ("migrations: DROP INDEX", a_drop_index_in_a_migration,
     ("DROP without manifest.migration.breaking", "destructive - DROP")),
    ("migrations: a plpgsql trigger function stays green", a_plpgsql_trigger_function, None),
    ("migrations: RENAME inside a string stays green", a_string_that_says_rename, None),
    ("migrations: DROP EXTENSION with breaking stays green",
     a_drop_extension_marked_breaking, None),
    ("migrations: a subdirectory stays green", a_subdirectory_under_migrations, None),
    ("manifest: permissions on a byo app", a_byo_app_with_permissions,
     "permissions on a byo app"),
    ("manifest: a key data does not have", a_typo_under_data,
     "data.shard is not a key the schema allows"),
    ("manifest: a key offline does not have", a_typo_under_offline,
     "offline.featrues is not a key the schema allows"),
    ("manifest: a UUID for a slug", a_uuid_for_a_slug, "not a slug the deploy accepts"),
    ("routes: a prefix on include_router", a_prefix_on_the_include,
     "GET /api/extra/items is served but no runtime.api_routes rule covers it"),
    ("agent: auth on the decorator stays green", auth_on_the_decorator, None),
    ("agent: auth on the include stays green", auth_on_the_include, None),
    ("agent: an OAuth2 scheme is not a user-context check",
     an_oauth2_scheme_on_an_agent_handler, "no user-context verification"),
    ("manifest: an auth mode the schema does not have", an_auth_mode_that_does_not_exist,
     "runtime.api_routes[0].auth is 'maybe'"),
    ("manifest: auth optional stays green", an_optional_route, None),
    ("migrations: a BEGIN ATOMIC body stays green", a_begin_atomic_function, None),
    ("migrations: a UTF-8 BOM", a_migration_with_a_bom, "starts with a UTF-8 BOM"),
    ("migrations: DROP EXTENSION, no migration.breaking",
     a_drop_extension_not_marked_breaking,
     ("DROP without manifest.migration.breaking", "DROP EXTENSION")),
    ("agent: an annotated scheme imported under another name",
     an_annotated_oauth2_scheme, "no user-context verification"),
    ("python: a module that does not parse", a_module_that_does_not_parse,
     "does not parse"),
    ("image: no Dockerfile", no_dockerfile, "Dockerfile: missing"),
    ("migrations: a file with no number", a_migration_with_no_number, "no leading number"),
    ("migrations: two files with one number", two_migrations_with_one_number,
     "share the number 1"),
    ("manifest: manifest.json does not parse", a_manifest_that_does_not_parse,
     "manifest.json: does not parse"),
    ("migrations: a generated column on array_to_string()",
     a_generated_column_on_array_to_string, "uses array_to_string()"),
    ("migrations: a generated to_tsvector() without a configuration",
     a_generated_column_without_a_configuration, "to_tsvector() without a configuration",
     True),
    ("migrations: a generated to_tsvector(lang, ...) stays green",
     a_generated_column_with_a_configuration_column, None),
    ("postgres: the recipe copied into the starter stays green",
     the_postgres_recipe_copied_in, None),
    ("postgres: SET search_path in create_pool(init=...)", search_path_set_in_pool_init,
     "src/db.py:16: SET search_path inside create_pool(init=...)"),
    ("postgres: SET search_path in create_pool(setup=...) stays green",
     search_path_set_in_pool_setup, None),
    ("data: DATABASE_URL under data.none", database_url_with_no_database,
     "src/db.py: reads DATABASE_URL"),
    ("data: DATABASE_URL named in a comment and a docstring stays green",
     database_url_named_in_a_comment, None),
    ("migrations: a generated column on concat_ws()", a_generated_column_on_concat,
     "join with || and wrap each nullable part in coalesce"),
    ("migrations: a generated column on now()", a_generated_column_on_now,
     "BEFORE UPDATE trigger - never an IMMUTABLE wrapper"),
    ("postgres: SET in init= with server_settings stays green",
     search_path_in_init_and_in_server_settings, None),
    ("postgres: SET LOCAL in a transaction stays green",
     set_local_inside_a_transaction, None),
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


CENTRED = "  max-width: var(--container-lg, 1024px);\n  margin-inline: auto;\n"
CAPPED = "  max-width: var(--container-lg, 1024px);\n"


def a_cap_nothing_centres(app: Path) -> None:
    # MAN-2849, verbatim: the starter's `.app` as four apps copied it.
    edit(app / "src" / "static" / "app.css", CENTRED, CAPPED)


def a_cap_in_a_style_block(app: Path) -> None:
    # The same defect where an app keeps its layout inline, not in app.css.
    edit(app / "src" / "static" / "app.css", CENTRED, "")
    edit(app / "src" / "static" / "index.html", "</head>",
         "<style>.app { max-width: 960px; margin: 0; }</style></head>")


def a_fixed_toast_with_a_cap(app: Path) -> None:
    # MUST STAY GREEN. zapiski's toast: `max-width: 80%`, centred by
    # `left: 50%` + `translateX(-50%)`, not by margin. It is not the page
    # root, and a rule that flags it is the naive rule MAN-2849 warned about.
    path = app / "src" / "static" / "app.css"
    path.write_text(path.read_text(encoding="utf-8") + (
        "\n.toast { position: fixed; left: 50%; bottom: var(--space-6);\n"
        "  transform: translateX(-50%); max-width: 80%; }\n"), encoding="utf-8")


def the_zapiski_workaround(app: Path) -> None:
    # MUST STAY GREEN. The defective rule left in place and a fix block
    # appended further down - which is what an app patched by hand looks like.
    a_cap_nothing_centres(app)
    path = app / "src" / "static" / "app.css"
    path.write_text(path.read_text(encoding="utf-8") + (
        "\n/* SDK template fix */\n.app { width: 100%; margin-inline: auto; }\n"),
        encoding="utf-8")


def a_body_that_centres(app: Path) -> None:
    # MUST STAY GREEN. The parent centres the root instead of the root itself.
    a_cap_nothing_centres(app)
    path = app / "src" / "static" / "app.css"
    path.write_text(path.read_text(encoding="utf-8") + (
        "\nbody { display: flex; flex-direction: column; align-items: center; }\n"),
        encoding="utf-8")


def a_colour_set_from_script(app: Path) -> None:
    edit(app / "src" / "static" / "index.html", "</body>",
         "<script>document.body.style.color = 'red';</script></body>")


def a_width_set_from_script(app: Path) -> None:
    # A progress bar: geometry, not colour. Must stay green.
    edit(app / "src" / "static" / "index.html", "</body>",
         "<script>const bar = document.body; bar.style.width = 42 + '%';"
         " bar.style.setProperty('--progress', '42%');</script></body>")


def an_in_app_confirm(app: Path) -> None:
    # The fix the skill teaches: an in-app dialog called confirm. Must stay green.
    edit(app / "src" / "static" / "index.html", "</body>",
         "<p>Ask before deleting: a prompt (in the page) is fine.</p>"
         "<script>const ui = { confirm: async () => true };"
         " async function remove() { await ui.confirm('Delete?'); }</script></body>")


def the_shell_appearance_never_applied(app: Path) -> None:
    # The function stays; nothing calls it. The old substring check passed this.
    path = app / "src" / "static" / "index.html"
    text = path.read_text(encoding="utf-8")
    if "applyShellTheme(payload);" not in text:
        raise AssertionError("anchor not found in index.html: applyShellTheme(payload);")
    path.write_text(text.replace("applyShellTheme(payload);", ""), encoding="utf-8")


def an_inline_onclick_confirm(app: Path) -> None:
    edit(app / "src" / "static" / "index.html", "</body>",
         "<button onclick=\"return confirm('Delete?')\">Delete</button></body>")


def the_appearance_destructured(app: Path) -> None:
    # MUST STAY GREEN. The value read off the payload first, then written.
    edit(app / "src" / "static" / "index.html",
         "if (payload.appearance) root.dataset.appearance = payload.appearance;",
         "const { appearance } = payload;\n"
         "      if (appearance) root.dataset.appearance = appearance;")


def the_theme_function_passed_by_name(app: Path) -> None:
    # MUST STAY GREEN. Passed, not called, as a message handler would be.
    path = app / "src" / "static" / "index.html"
    text = path.read_text(encoding="utf-8")
    if "applyShellTheme(payload);" not in text:
        raise AssertionError("anchor not found in index.html: applyShellTheme(payload);")
    path.write_text(text.replace("applyShellTheme(payload);",
                                 "[payload].forEach(applyShellTheme);"), encoding="utf-8")


def a_fallback_that_reads_itself(app: Path) -> None:
    # The shell's value never applied; the fallback reads the document's own
    # `dataset.appearance`, which is not the payload's.
    the_shell_appearance_never_applied(app)
    edit(app / "src" / "static" / "index.html",
         "root.dataset.appearance = media.matches ? 'dark' : 'light';",
         "if (!root.dataset.appearance || root.dataset.appearance === 'auto')"
         " root.dataset.appearance = media.matches ? 'dark' : 'light';")


def the_appearance_as_a_destructured_parameter(app: Path) -> None:
    # MUST STAY GREEN.
    edit(app / "src" / "static" / "index.html",
         "function applyShellTheme(payload) {\n"
         "      if (payload.appearance) root.dataset.appearance = payload.appearance;",
         "function applyShellTheme(payload) { applyLook(payload); applyAccent(payload); }\n"
         "    function applyLook({ appearance }) {\n"
         "      if (appearance) root.dataset.appearance = appearance;\n"
         "    }\n"
         "    function applyAccent(payload) {")


def a_named_handler_written_in_place(app: Path) -> None:
    # MUST STAY GREEN. A named function expression passed where it is
    # written: its only "use" is its definition.
    the_shell_appearance_never_applied(app)
    edit(app / "src" / "static" / "index.html", "</body>",
         "<script>window.addEventListener('message', function onShellMessage(e) {"
         " var p = (e.data || {}).payload || {};"
         " if (p.appearance) document.documentElement.dataset.appearance = p.appearance;"
         " });</script></body>")


# ── Rules older than the mutation suite (audit Н1) ──────────────────────────


def html_edit(app: Path, old: str, new: str) -> None:
    edit(app / "src" / "static" / "index.html", old, new)


def html_replace_all(app: Path, old: str, new: str) -> None:
    path = app / "src" / "static" / "index.html"
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError("anchor not found in index.html: %r" % old)
    path.write_text(text.replace(old, new), encoding="utf-8")


# ── The person's language (3.16.0) ──────────────────────────────────────────


def the_shell_language_never_applied(app: Path) -> None:
    # The function stays, the message branches stay; nothing calls it. The
    # standalone guess from navigator.languages still writes lang and dir,
    # which is exactly why the rule cannot be "is lang written somewhere".
    html_edit(app, "        applyShellLocale(payload);\n", "")
    html_edit(app, "if (applyShellLocale(payload)) window.dispatchEvent",
              "if (true) window.dispatchEvent")


def only_the_lang_applied(app: Path) -> None:
    # The locale reaches <html lang>, the direction never does: a Hebrew
    # screen laid out left to right.
    html_edit(app, "      root.lang = locale;\n      root.dir = dir;\n",
              "      root.lang = locale;\n")


def no_live_language_switch(app: Path) -> None:
    # Applied on init, and a switch while the window is open never heard.
    html_edit(app, "data.type === 'manaurum:locale-change'",
              "data.type === 'manaurum:language'")


def the_language_destructured(app: Path) -> None:
    # MUST STAY GREEN. Read off the payload by destructuring, then written.
    path = app / "src" / "static" / "index.html"
    text = path.read_text(encoding="utf-8")
    text, n = re.subn(r"function applyShellLocale\(payload\) \{.*?\n    \}",
                      "function applyShellLocale(payload) {\n"
                      "      const { locale, dir } = payload;\n"
                      "      if (!LOCALE_DIR.hasOwnProperty(locale)) return false;\n"
                      "      root.lang = locale;\n"
                      "      root.dir = dir || LOCALE_DIR[locale];\n"
                      "      window.__manaurum.locale = locale;\n"
                      "      window.__manaurum.dir = root.dir;\n"
                      "      return true;\n"
                      "    }", text, count=1, flags=re.S)
    if not n:
        raise AssertionError("anchor not found in index.html: function applyShellLocale")
    path.write_text(text, encoding="utf-8")


def a_language_handler_written_in_place(app: Path) -> None:
    # MUST STAY GREEN. Another app's shape: setAttribute and documentElement,
    # in a named handler passed where it is written, and the direction taken
    # from the locale rather than from `dir`.
    the_shell_language_never_applied(app)
    html_edit(app, "</body>",
              "<script>window.addEventListener('message', function onShellMessage(e) {"
              " var p = (e.data || {}).payload || {};"
              " if (!p.locale) return;"
              " document.documentElement.setAttribute('lang', p.locale);"
              " document.documentElement.dir = p.locale === 'he' ? 'rtl' : 'ltr';"
              " });</script></body>")


def a_language_helper(app: Path, arrow: bool = False) -> None:
    # MUST STAY GREEN. The write sits in a helper and the read is at the call:
    # `setLanguage(p.locale, p.dir)`. Found red by the review of 3.16.0.
    the_shell_language_never_applied(app)
    helper = ("const setLanguage = (l, d) => {" if arrow else "function setLanguage(l, d) {")
    html_edit(app, "</body>",
              "<script>" + helper +
              " document.documentElement.lang = l; document.documentElement.dir = d; }"
              " window.addEventListener('message', function (e) {"
              " var p = (e.data || {}).payload || {};"
              " if (e.data.type === 'manaurum:init' || e.data.type === 'manaurum:locale-change')"
              " setLanguage(p.locale, p.dir); });</script></body>")


def a_language_helper_as_an_arrow(app: Path) -> None:
    # MUST STAY GREEN. The same, bound to a name with an arrow.
    a_language_helper(app, arrow=True)


def a_helper_called_with_constants(app: Path) -> None:
    # The helper exists and is called - with English, never with the payload.
    the_shell_language_never_applied(app)
    html_edit(app, "</body>",
              "<script>function setLanguage(l, d) {"
              " document.documentElement.lang = l; document.documentElement.dir = d; }"
              " setLanguage('en', 'ltr');</script></body>")


def one_language_on_purpose(app: Path) -> None:
    # MUST STAY GREEN. An app written in Hebrew only, and saying so.
    the_shell_language_never_applied(app)
    html_edit(app, '<html lang="en">', '<html lang="he" dir="rtl" data-languages="he">')


def one_language_that_its_root_contradicts(app: Path) -> None:
    # Declared Hebrew-only, and still laid out left to right.
    the_shell_language_never_applied(app)
    html_edit(app, '<html lang="en">', '<html lang="he" data-languages="he">')


def css_edit(app: Path, old: str, new: str) -> None:
    edit(app / "src" / "static" / "app.css", old, new)


def css_append(app: Path, text: str) -> None:
    path = app / "src" / "static" / "app.css"
    path.write_text(path.read_text(encoding="utf-8") + "\n" + text + "\n", encoding="utf-8")


def a_padding_left(app: Path) -> None:
    css_edit(app, ".prose ol { padding-inline-start:", ".prose ol { padding-left:")


def a_text_align_left(app: Path) -> None:
    css_edit(app, "  text-align: start;\n", "  text-align: left;\n")


def a_border_right_in_a_style_block(app: Path) -> None:
    # Stylesheets inside the page count too.
    html_edit(app, "</head>",
              "<style>.aside { border-right: 1px solid var(--border-hairline); }</style></head>")


def a_float_left(app: Path) -> None:
    css_append(app, ".avatar { float: left; }")


def a_four_value_shorthand(app: Path) -> None:
    # What `.pull` was in 3.15.0: the left padding hidden in the fourth value.
    css_append(app, ".quote { padding: var(--space-1) 0 var(--space-1) var(--space-5); }")


def a_physical_corner_and_position(app: Path) -> None:
    css_append(app, ".tab-end { position: absolute; right: 0; top: 0;"
                    " border-top-left-radius: 8px; }")


def sides_that_mirror_anyway(app: Path) -> None:
    # MUST STAY GREEN. Both sides the same mirror trivially, and positioning
    # is not reading direction: a toast centred with left: 50% stays put.
    css_append(app, ".narrow { max-width: 40ch; margin-left: auto; margin-right: auto;\n"
                    "  padding-left: var(--space-4); padding-right: var(--space-4); }\n"
                    ".toast { position: fixed; left: 50%; bottom: var(--space-6);\n"
                    "  transform: translateX(-50%); }\n"
                    ".close { position: absolute; inset-inline-end: var(--space-2); top: 0; }\n"
                    ".box { margin: 0 auto; padding: 4px 8px 4px 8px; border-radius: 4px 4px;\n"
                    "  inset: 0; }\n"
                    ".cover { position: absolute; left: 0; right: 0; }")


def a_short_hex_in_the_markup(app: Path) -> None:
    html_edit(app, "</body>", '<svg><path fill="#f00"/></svg></body>')


def an_rgba_in_the_markup(app: Path) -> None:
    html_edit(app, "</body>", '<svg><path fill="rgba(0,0,0,.5)"/></svg></body>')


def a_colour_in_a_style_attribute(app: Path) -> None:
    html_edit(app, "</body>", '<p style="color: red">x</p></body>')


def a_button_row(app: Path) -> None:
    html_edit(app, "</body>", '<button class="row">x</button></body>')


def a_clickable_row_without_is_interactive(app: Path) -> None:
    html_edit(app, "</body>", '<ul><li class="row" data-id="1">x</li></ul></body>')


def no_index_html(app: Path) -> None:
    (app / "src" / "static" / "index.html").unlink()


def two_primary_buttons_in_one_view(app: Path) -> None:
    html_edit(app, '<div data-view="overview">',
              '<div data-view="overview"><button class="btn btn-primary">One</button>'
              '<button class="btn btn-primary">Two</button>')


def the_device_never_written(app: Path) -> None:
    html_replace_all(app, "dataset.device", "dataset.dev")


def nothing_reads_the_payload(app: Path) -> None:
    html_replace_all(app, "payload", "pl")


# ── Accent is a pointer (3.14.0, from PR #27) ───────────────────────────────


def accent_handed_out_in_a_loop(app: Path) -> None:
    # Thirteen categories, thirteen blue buttons, and not one rule broken.
    html_edit(app, "</body>",
              "<script>for (const topic of topics) {\n"
              "  const b = document.createElement('button');\n"
              "  b.className = 'btn btn-ghost';\n  bar.append(b);\n}</script></body>")


def accent_badges_mapped_in_a_script_file(app: Path) -> None:
    # The same thing as a `.map()` callback, in a .js file of its own.
    (app / "src" / "static" / "list.js").write_text(
        "export const render = (rows) => rows.map((r) =>\n"
        "  `<li class=\"row\"><span class=\"badge badge-accent\">${r.state}</span></li>`);\n",
        encoding="utf-8")


def too_much_accent_in_one_view(app: Path) -> None:
    ghosts = "".join('<button class="btn btn-ghost" type="button">%d</button>' % i
                     for i in range(5))
    html_edit(app, '<div data-view="overview">',
              '<div data-view="overview"><div class="toolbar">%s</div>' % ghosts)


def chips_toggled_in_a_loop(app: Path) -> None:
    # MUST STAY GREEN. The right way to do the thing above: every chip is
    # visited, only the chosen one ends up accent.
    html_edit(app, "</body>",
              "<script>group.querySelectorAll('.chip').forEach(function (c) {\n"
              "  c.setAttribute('aria-pressed', c === chip ? 'true' : 'false');\n"
              "  c.classList.toggle('is-on', c === chip);\n});</script></body>")


def four_accent_things_in_one_view(app: Path) -> None:
    # MUST STAY GREEN. The budget is four, and four is within it: the cap
    # view's back link plus three more.
    ghosts = "".join('<a class="btn btn-ghost" href="#overview">%d</a>' % i for i in range(3))
    html_edit(app, '<div data-view="cap" hidden>', '<div data-view="cap" hidden>' + ghosts)


def accent_in_the_header_and_the_view(app: Path) -> None:
    # Three ghosts in the page header are on screen with every view: with the
    # overview's primary and one more ghost, the first screen holds five,
    # though neither part alone is over four.
    ghost = '<button class="btn btn-ghost" type="button">x</button>'
    html_edit(app, '<div class="header-actions">', '<div class="header-actions">' + ghost * 3)
    html_edit(app, '<div data-view="overview">', '<div data-view="overview">' + ghost)


def accent_added_in_a_loop(app: Path) -> None:
    html_edit(app, "</body>",
              "<script>rows.forEach(function (r) { r.classList.add('badge-accent'); });"
              "</script></body>")


def a_style_block_naming_the_accent_classes(app: Path) -> None:
    # MUST STAY GREEN. A stylesheet that styles the classes puts none of them
    # on the screen.
    html_edit(app, "</head>",
              "<style>.btn-primary, .btn-ghost, .badge-accent, .btn-primary:active,"
              " .btn-ghost:active { letter-spacing: 0.01em; }</style></head>")


def accent_markup_inside_a_script(app: Path) -> None:
    # MUST STAY GREEN. A template string in a script is not the static markup
    # of the view it happens to sit in; the loop rule covers what a script
    # renders per item.
    ghosts = "".join('<a class=\"btn btn-ghost\" href=\"#overview\">%d</a>' % i for i in range(5))
    html_edit(app, '<div data-view="overview">',
              "<div data-view=\"overview\"><script>const TEMPLATE = '%s';</script>" % ghosts)


def an_accent_toggled_by_a_condition(app: Path) -> None:
    # MUST STAY GREEN. Every row is visited; the condition puts the class on
    # the one that is current.
    html_edit(app, "</body>",
              "<script>rows.forEach(function (r) {\n"
              "  r.classList.toggle('btn-primary', r.dataset.id === current);\n"
              "});</script></body>")


def accent_selectors_and_removal_in_a_loop(app: Path) -> None:
    # MUST STAY GREEN. A selector names the class; remove() takes it away.
    html_edit(app, "</body>",
              "<script>for (const b of document.querySelectorAll('.btn-ghost')) {\n"
              "  b.classList.remove('btn-ghost');\n}</script></body>")


def for_in_running_text(app: Path) -> None:
    # MUST STAY GREEN. "for (" in a sentence is not a loop. PR #27's version
    # read loops out of the whole page, and this paragraph - followed by the
    # cap view's ghost link - read as a loop handing out accent.
    html_edit(app, '<div data-view="cap" hidden>',
              '<div data-view="cap" hidden><p class="muted">Good for (most) teams.</p>')


UI_MUTATIONS = [
    ("ui: a width cap nothing centres", a_cap_nothing_centres,
     "caps its width"),
    ("ui: a width cap in a <style> block", a_cap_in_a_style_block,
     "caps its width (max-width: 960px)"),
    ("ui: a fixed toast with a cap stays green", a_fixed_toast_with_a_cap, None),
    ("ui: a cap fixed by an appended block stays green", the_zapiski_workaround, None),
    ("ui: a cap centred by body stays green", a_body_that_centres, None),
    ("ui: a var() whose token is declared nowhere", token_declared_nowhere,
     "declared nowhere"),
    ("ui: a hex in the markup", hex_in_the_markup, "in markup"),
    ("ui: a tab bar", a_tab_bar, "tab/tabs/sidebar class"),
    ("ui: confirm()", a_native_modal, "alert/confirm/prompt"),
    ("ui: @media max-width", a_media_query, "@media max-width"),
    ("ui: no manaurum:ready", the_handshake, "no manaurum:ready"),
    ("ui: a colour set through element.style", a_colour_set_from_script,
     "a colour set through element.style"),
    ("ui: a width set through element.style stays green", a_width_set_from_script,
     None),
    ("ui: an in-app confirm stays green", an_in_app_confirm, None),
    ("ui: the shell's appearance never applied", the_shell_appearance_never_applied,
     "appearance from manaurum:init is never written"),
    ("ui: confirm() in an inline onclick", an_inline_onclick_confirm,
     "alert/confirm/prompt"),
    ("ui: the appearance destructured stays green", the_appearance_destructured, None),
    ("ui: the theme function passed by name stays green",
     the_theme_function_passed_by_name, None),
    ("ui: a fallback that reads its own value", a_fallback_that_reads_itself,
     "appearance from manaurum:init is never written"),
    ("ui: the appearance as a destructured parameter stays green",
     the_appearance_as_a_destructured_parameter, None),
    ("ui: a named handler written in place stays green",
     a_named_handler_written_in_place, None),
    ("ui: a short hex in the markup", a_short_hex_in_the_markup, "hex #f00 in markup"),
    ("ui: rgba() in the markup", an_rgba_in_the_markup, "rgba() in markup"),
    ("ui: a colour in a style= attribute", a_colour_in_a_style_attribute,
     "a colour in a style= attribute"),
    ("ui: <button class=\"row\">", a_button_row, '<button class="row">'),
    ("ui: a clickable row without is-interactive", a_clickable_row_without_is_interactive,
     "no is-interactive"),
    ("ui: no index.html", no_index_html, "index.html is missing"),
    ("ui: two primary buttons in one view", two_primary_buttons_in_one_view,
     "primary buttons in one view"),
    ("ui: the device never written", the_device_never_written,
     "device from the shell is never written"),
    ("ui: nothing reads the payload", nothing_reads_the_payload, "nothing reads `payload`"),
    ("ui: an accent class handed out in a loop", accent_handed_out_in_a_loop,
     "accent class (btn-ghost) set inside a loop"),
    ("ui: accent badges from a .map() in a .js file", accent_badges_mapped_in_a_script_file,
     "list.js: an accent class (badge-accent) set inside a loop"),
    ("ui: more than four accent classes in one view", too_much_accent_in_one_view,
     "6 accent-coloured elements"),
    ("ui: chips toggled in a loop stay green", chips_toggled_in_a_loop, None),
    ("ui: four accent things in one view stay green", four_accent_things_in_one_view, None),
    ("ui: \"for (\" in running text stays green", for_in_running_text, None),
    ("ui: accent in the header and the view, over budget together",
     accent_in_the_header_and_the_view, "5 accent-coloured elements"),
    ("ui: an accent class added in a loop", accent_added_in_a_loop,
     "accent class (badge-accent) set inside a loop"),
    ("ui: a <style> block naming the accent classes stays green",
     a_style_block_naming_the_accent_classes, None),
    ("ui: accent markup inside a script stays green", accent_markup_inside_a_script, None),
    ("ui: an accent toggled by a condition stays green", an_accent_toggled_by_a_condition,
     None),
    ("ui: accent selectors and remove() in a loop stay green",
     accent_selectors_and_removal_in_a_loop, None),
    ("ui: the shell's language never applied", the_shell_language_never_applied,
     "language from manaurum:init is never written onto <html lang dir>"),
    ("ui: the locale applied, the direction not", only_the_lang_applied,
     "never written onto <html dir>"),
    ("ui: no live language switch", no_live_language_switch, "no manaurum:locale-change"),
    ("ui: the language destructured stays green", the_language_destructured, None),
    ("ui: a language handler written in place stays green",
     a_language_handler_written_in_place, None),
    ("ui: padding-left in app.css", a_padding_left,
     "`padding-left` in `.prose ul, .prose ol` does not mirror"),
    ("ui: text-align: left in app.css", a_text_align_left, "use text-align: start / end"),
    ("ui: border-right in a <style> block", a_border_right_in_a_style_block,
     "index.html: `border-right` in `.aside` does not mirror"),
    ("ui: float: left", a_float_left, "use float: inline-start / inline-end"),
    ("ui: symmetric sides and positioning stay green", sides_that_mirror_anyway, None),
    ("ui: a four-value shorthand with a left of its own", a_four_value_shorthand,
     "`padding: var(--space-1) 0 var(--space-1) var(--space-5)` in `.quote`"),
    ("ui: a physical corner and right: 0", a_physical_corner_and_position,
     "use border-start-start-radius"),
    ("ui: right: 0 positioning", a_physical_corner_and_position,
     "`right: 0` in `.tab-end` does not mirror"),
    ("ui: a language helper stays green", a_language_helper, None),
    ("ui: a language helper as an arrow stays green", a_language_helper_as_an_arrow, None),
    ("ui: a language helper called with constants", a_helper_called_with_constants,
     "language from manaurum:init is never written"),
    ("ui: one language on purpose stays green", one_language_on_purpose, None),
    ("ui: one language its root contradicts", one_language_that_its_root_contradicts,
     'data-languages="he" says the app speaks only he'),
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
    # Whatever date the first line carries: a fixed one went stale the day the
    # register was re-verified, and the mutation then changed nothing.
    mutated = re.sub(r"(?m)^(MAN-\d+\s+.+?\s+)\d{4}-\d{2}-\d{2}", r"\1not-a-date", text, count=1)
    if mutated == text:
        raise AssertionError("no dated line in open-claims.txt to break")
    path.write_text(mutated, encoding="utf-8")


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


def a_stale_fact_comes_back(repo: Path) -> None:
    append(repo, "README.md", "There is no readiness probe on the hosted path.")


def a_stale_fact_reported_as_history(repo: Path) -> None:
    append(repo, "README.md",
           "An earlier version of this page said there is no readiness probe.")


def a_stale_fact_in_the_starter(repo: Path) -> None:
    append(repo, "templates/v2-starter/README.md",
           "Get the port wrong and every request 502s.")


def a_capability_that_is_not_registered(repo: Path) -> None:
    append(repo, "README.md", "Enumerate keys with `os.kv.list`.")


def a_capability_said_not_to_exist(repo: Path) -> None:
    append(repo, "README.md", "There is no `os.kv.list`; keep an index key.")


def a_permissions_enum_without_camera(repo: Path) -> None:
    append(repo, "README.md", 'The permissions enum is `["microphone"]`.')


def a_wrong_capability_count(repo: Path) -> None:
    path = repo / "skills" / "manaurum-app" / "references" / "capabilities-reference.md"
    text = path.read_text(encoding="utf-8")
    if "All **32**" not in text:
        raise AssertionError("anchor not found: All **32**")
    path.write_text(text.replace("All **32**", "All **31**", 1), encoding="utf-8")


def runtime_keys_drift(repo: Path) -> None:
    path = repo / "templates" / "check_app.py"
    text = path.read_text(encoding="utf-8")
    if '"replicas", "image"}' not in text:
        raise AssertionError("anchor not found: RUNTIME_KEYS tail")
    path.write_text(text.replace('"replicas", "image"}', '"replicas"}', 1),
                    encoding="utf-8")


def the_gateway_forwards_the_clients_copy(repo: Path) -> None:
    append(repo, README, "The gateway adds its own copy but does not remove one the "
                         "client sent.")


def the_old_gateway_reported_as_history(repo: Path) -> None:
    append(repo, README, "An earlier version said the gateway does not remove a copy "
                         "the client sent.")


def a_stale_fact_beside_some_history(repo: Path) -> None:
    # One paragraph (one line): history in one sentence, the stale claim in
    # the next. The history must not excuse the claim.
    append(repo, README, "An earlier version had no probe at all. There is no readiness "
                         "probe on the hosted path.")


def runtime_keys_renamed(repo: Path) -> None:
    path = repo / "templates" / "check_app.py"
    text = path.read_text(encoding="utf-8")
    if "RUNTIME_KEYS = {" not in text:
        raise AssertionError("anchor not found: RUNTIME_KEYS = {")
    path.write_text(text.replace("RUNTIME_KEYS = {", "RUNTIME_KEY_SET = {", 1)
                    .replace("or RUNTIME_KEYS", "or RUNTIME_KEY_SET"), encoding="utf-8")


def no_workspace_id_in_the_token(repo: Path) -> None:
    append(repo, README, "The user_context token does not carry a workspace_id.")


def the_server_cannot_learn_the_language(repo: Path) -> None:
    append(repo, README, "Your server and the Assistant's calls cannot learn the language "
                         "the person chose.")


def an_error_code_core_does_not_write(repo: Path) -> None:
    append(repo, README, "A second deploy of the slug answers `409 slug_gone_forever`.")


def a_code_built_from_a_prefix(repo: Path) -> None:
    # MUST STAY GREEN. Core writes it as f"{detail_prefix}_backslash".
    append(repo, README, "A key with a backslash answers `400 invalid_file_key_backslash`.")


def a_message_the_shell_does_not_know(repo: Path) -> None:
    append(repo, README, "Post `manaurum:open-url` to open a link in a new tab.")


def a_refused_v1_message_named(repo: Path) -> None:
    # MUST STAY GREEN. A v1 verb the shell refuses for v2 is part of the story.
    append(repo, README, "A v2 app that posts `manaurum:storage-get` gets an error back.")


def a_protocol_message_the_reference_omits(repo: Path) -> None:
    path = repo / "templates" / "platform-contract.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["messages"]["app_to_shell"].append("manaurum:clipboard-write")
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def a_second_code_in_a_status_row(repo: Path) -> None:
    append(repo, README, "| Status | Code |\n|---|---|\n"
                         "| 409 | `slug_reserved` / `slug_gone_forever` |")


def a_provider_filled_code(repo: Path) -> None:
    # MUST STAY GREEN. Core writes it as f"{provider}_upstream_error:{status}".
    append(repo, README, "A provider failure answers `502 openai_upstream_error:429`.")


def a_truncated_message_family(repo: Path) -> None:
    # A fragment of a refused family is not a family.
    append(repo, README, "Post `manaurum:st` to read storage.")


def edit_inputs(repo: Path, change) -> None:
    """Change Core's side, as a sync after a Core change would."""
    path = repo / "templates" / "platform-contract.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data["capability_inputs"])
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def core_renames_a_field(repo: Path) -> None:
    # The K3 shape: the reference sends `key`, Core now wants `file_key`.
    edit_inputs(repo, lambda inputs: inputs["os.kv.get"].update(
        properties=["file_key"], required=["file_key"]))


def core_drops_a_documented_field(repo: Path) -> None:
    edit_inputs(repo, lambda inputs: inputs["os.ai.complete"]["properties"].remove("log_prompt"))


def core_adds_a_field(repo: Path) -> None:
    edit_inputs(repo, lambda inputs: inputs["os.ai.complete"]["properties"].append("top_p"))


def core_requires_what_the_example_leaves_out(repo: Path) -> None:
    edit_inputs(repo, lambda inputs: inputs["os.ai.complete"]["required"].append("provider"))


def core_makes_a_field_optional(repo: Path) -> None:
    edit_inputs(repo, lambda inputs: inputs["os.kv.set"]["required"].remove("value"))


def core_makes_a_field_required(repo: Path) -> None:
    edit_inputs(repo, lambda inputs: inputs["os.ai.complete"]["required"].append("temperature"))


def newest_summary(repo: Path, change) -> None:
    path = repo / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    start = text.index("\nSummary:")
    end = text.index("\n", start + 1)
    path.write_text(text[:start] + change(text[start:end]) + text[end:], encoding="utf-8")


def a_release_without_a_summary(repo: Path) -> None:
    newest_summary(repo, lambda line: "")


def a_summary_that_is_a_paragraph(repo: Path) -> None:
    newest_summary(repo, lambda line: line + " And then" * 40 + ".")


def manifest_left_behind(repo: Path, name: str) -> None:
    # PR #34's shape: a Codex manifest kept the version it was written at.
    path = repo / name
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = "3.0.0"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def a_codex_manifest_left_behind(repo: Path) -> None:
    manifest_left_behind(repo, ".codex-plugin/plugin.json")


def a_portable_manifest_left_behind(repo: Path) -> None:
    manifest_left_behind(repo, "plugin.json")


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
    ("repo: a stale fact comes back", a_stale_fact_comes_back,
     "has a readiness probe (MAN-1369)"),
    ("repo-green: a stale fact reported as history", a_stale_fact_reported_as_history,
     None),
    ("repo: a stale fact in the starter's README", a_stale_fact_in_the_starter,
     "fails the readiness probe"),
    ("repo: a capability Core does not register", a_capability_that_is_not_registered,
     "is not a capability Core registers"),
    ("repo-green: a capability said not to exist", a_capability_said_not_to_exist, None),
    ("repo: the permissions enum without camera", a_permissions_enum_without_camera,
     "states the permissions enum without camera"),
    ("repo: the reference's capability count", a_wrong_capability_count,
     "Core registers 32"),
    ("repo: RUNTIME_KEYS drifts from the schema", runtime_keys_drift,
     "RUNTIME_KEYS differs from the schema"),
    ("repo: the gateway said to forward the client's copy",
     the_gateway_forwards_the_clients_copy, "drops a client-sent X-Manaurum-User-Context"),
    ("repo-green: the old gateway reported as history",
     the_old_gateway_reported_as_history, None),
    ("repo: a stale fact beside some history", a_stale_fact_beside_some_history,
     "has a readiness probe (MAN-1369)"),
    ("repo: RUNTIME_KEYS renamed", runtime_keys_renamed,
     "no `RUNTIME_KEYS = {...}` to hold"),
    ("repo: no workspace_id in the token", no_workspace_id_in_the_token,
     "mints user_context with workspace_id"),
    ("repo: the server said to have no language", the_server_cannot_learn_the_language,
     "carry the person's language as locale / dir"),
    ("repo: an error code Core does not write", an_error_code_core_does_not_write,
     "`slug_gone_forever` is not an error code Core writes"),
    ("repo-green: a code built from a prefix", a_code_built_from_a_prefix, None),
    ("repo: a message the shell does not know", a_message_the_shell_does_not_know,
     "`manaurum:open-url` is not a message the shell handles"),
    ("repo-green: a refused v1 message named", a_refused_v1_message_named, None),
    ("repo: a protocol message the reference omits", a_protocol_message_the_reference_omits,
     "`manaurum:clipboard-write` is part of the shell's protocol and described nowhere"),
    ("repo: a second code in a status row", a_second_code_in_a_status_row,
     "`slug_gone_forever` is not an error code Core writes"),
    ("repo-green: a provider-filled code", a_provider_filled_code, None),
    ("repo: a truncated message family", a_truncated_message_family,
     "`manaurum:st` is not a message the shell handles"),
    ("repo: Core renames an input field", core_renames_a_field,
     "the os.kv.get example sends `key`, which its input schema does not have"),
    ("repo: Core drops a documented input field", core_drops_a_documented_field,
     "the os.ai.complete field table lists `log_prompt`"),
    ("repo: Core adds an input field", core_adds_a_field,
     "the os.ai.complete field table leaves out `top_p`"),
    ("repo: Core makes an input field required", core_makes_a_field_required,
     "calls `temperature` optional; its input schema requires it"),
    ("repo: Core requires what the example leaves out",
     core_requires_what_the_example_leaves_out,
     "the os.ai.complete example leaves out `provider`"),
    ("repo: Core makes an input field optional", core_makes_a_field_optional,
     "calls `value` required; its input schema does not require it"),
    ("repo: a release without a Summary line", a_release_without_a_summary,
     "has no `Summary:` line"),
    ("repo: a Summary that is a paragraph", a_summary_that_is_a_paragraph,
     "keep it to one sentence"),
    ("repo: a Codex manifest left behind", a_codex_manifest_left_behind,
     ".codex-plugin/plugin.json:3: says version 3.0.0"),
    ("repo: the portable manifest left behind", a_portable_manifest_left_behind,
     "x plugin.json:4: says version 3.0.0"),
]


def run(linter: Path, target: Path, env=None):
    return subprocess.run([sys.executable, str(linter), str(target)],
                          capture_output=True, text=True, env=env)


# A stand-in for `manaurum_cli.migrations`, written into the mutation's own
# temp directory. MAN-2624: `check_app.py` defers its migration rule to the
# deploy's real AST validator when one is importable, and CI installs no
# Python packages - so without a double, the branch this repo added is the
# one branch nothing ever runs.
#
# It is a DOUBLE, not a second opinion: it exists to prove check_app.py calls
# the validator once per file, renders its `errors` rows, and does not skip
# the other rules. The real verdicts live in the monorepo, behind pglast.
# Nothing here should ever be treated as the rule.
STUB_VALIDATOR = '''"""Test double for manaurum_cli.migrations - NOT the real rules."""


class MigrationValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(
            "%s: %s" % (e["classification"], e["reason"]) for e in errors))


def validate_migration(sql, *, breaking_allowed=False):
    statements = [s for s in sql.split(";") if s.strip()]
    concurrent = [s for s in statements if "CONCURRENTLY" in s.upper()]
    if concurrent and len(concurrent) != len(statements):
        raise MigrationValidationError([{
            "statement": concurrent[0].strip(),
            "classification": "mixed_transaction",
            "reason": ("a migration file that uses CONCURRENTLY must contain "
                       "nothing else - CONCURRENTLY cannot run inside a "
                       "transaction, and the rest of the file needs one."),
        }])
    return None
'''


def with_stub_validator(workdir: Path):
    """An environment in which `check_app.py` finds a usable validator."""
    package = workdir / "stub" / "manaurum_cli"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "migrations.py").write_text(STUB_VALIDATOR, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(workdir / "stub")
    return env


def said(output: str, expected) -> bool:
    """Did the linter name the thing?

    ``expected`` is one substring, or several of which ANY will do. The
    plural form exists because one rule can be reported by two different
    engines - `check_app.py` uses the deploy's AST validator when it is
    importable and its own pattern list when it is not - and the point of
    the assertion is that the rule FIRED, not that a particular sentence
    was printed. It is still a substring match, so a mutation cannot pass
    on a linter saying something unrelated.
    """
    if isinstance(expected, str):
        expected = (expected,)
    return any(item in output for item in expected)


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
        elif not said(done.stdout, expected):
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

    cases = ([(CHECK_APP, "app", case) for case in APP_MUTATIONS]
             + [(CHECK_UI, "ui", case) for case in UI_MUTATIONS])
    for linter, kind, case in cases:
        # A mutation may carry a fourth element: needs_validator, for a rule
        # `check_app.py` can only decide by asking the deploy's own validator.
        name, mutate, expected = case[0], case[1], case[2]
        needs_validator = case[3] if len(case) > 3 else False
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
            env = with_stub_validator(workdir) if needs_validator else None
            done = run(linter, target, env=env)
            if expected is None:
                # A legitimate pattern the rule must NOT flag - the other half
                # of trusting a linter.
                if done.returncode != 0:
                    problems.append("%s: %s went RED on a pattern it should accept. "
                                    "It said:\n%s" % (name, linter.name,
                                                      done.stdout.strip()))
                else:
                    print("ok  %s" % name)
            elif done.returncode == 0:
                problems.append("%s SURVIVED - %s said `clean` on it. That rule is "
                                "not being checked." % (name, linter.name))
            elif not said(done.stdout, expected):
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

#!/usr/bin/env python3
"""Mechanical check of a v2 app against its own manifest, before you deploy it.

The backend sibling of `check_ui.py`. Same shape, same reason: the rules
below are all described in the skill, in prose, three times over - and an
agent treats as contract what sits in a numbered step marked mandatory, and
treats prose as reference material for if there is time left.

Every rule here is decidable from the app's own files, and every one of them
otherwise fails LATER and in a way that does not look like its cause:

    route not declared      the gateway answers 404 and your handler never
                            runs. Looks like a backend bug with silent logs.
    port disagreement       green deploy, then 502 on every request.
    an /agent/ handler with
    no user-context check   an open endpoint on the public internet, which
                            nothing will ever tell you about.
    an undeclared
    capability              403 capability_not_granted at the first call, in
                            production, from a user.
    a .env* in the app dir  packed into the build context, baked into an
                            image layer, retained per version in object
                            storage. There is no way to un-leak it.

Standard library only, with one optional upgrade: if `manaurum-cli` happens
to be importable, the migration rule defers to the deploy's own AST
validator instead of its built-in pattern list, and says so when it cannot.
Nothing needs installing for the script to run.

Run it on the directory that holds `manifest.json` - the same directory the
deploy packs:

    python check_app.py my-app

Exit code: 0 clean, 1 problems found, 2 could not run.

WHAT IT CANNOT SEE. Route and handler discovery reads **Python** with `ast`,
because that is the starter's stack and a decorator is the only honest place
to find a route without importing the app. For any other language it says so
and skips those two rules rather than guessing - the manifest, port,
capability, `.env` and migration rules still run, because those read files
rather than code. A capability name assembled at run time
(`f"os.kv.{verb}"`) is invisible to the capability rule for the same reason.

Output is deliberately ASCII: a Windows console renders anything else as
mojibake, and an unreadable finding is an ignored finding.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options",
                "api_route", "route")
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", "dist",
             "build", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
STATIC_ROOTS = ("", "src/static", "static", "public", "www", "dist", "build",
                "src/public", "frontend/dist")

# A capability is always a quoted dotted name: "os.kv.get". Matching the
# STRING and not the expression is deliberate - `os.path.join(...)` is an
# attribute access on the stdlib and has nothing to do with the gateway.
CAPABILITY = re.compile(r"""["'](os\.[a-z_]+(?:\.[a-z_]+)+)["']""")
# A FastAPI path parameter, an Express one, and a Flask one.
PATH_PARAM = re.compile(r"\{[^}]+\}|:[A-Za-z_][A-Za-z0-9_]*|<[^>]+>")
EXPOSE = re.compile(r"(?mi)^\s*EXPOSE\s+(\d+)")
# `--port 8000`, `--port=8000`, `-p 8000`, `0.0.0.0:8000`.
PORT_IN_COMMAND = re.compile(r"--port[=\s]+(\d+)|\s-p[=\s]+(\d+)|0\.0\.0\.0:(\d+)")
DOCKER_RUNLINE = re.compile(r"(?mi)^\s*(?:CMD|ENTRYPOINT)\s+(.*)$")
MIGRATION_NUMBER = re.compile(r"^(\d+)")
# The manifest's root object is strict, so a typo up there is a 422 that finds
# itself. `runtime` is not, which is why this list has to exist here.
RUNTIME_KEYS = {"mode", "port", "api_routes", "egress_allowed_hosts",
                "replicas", "sandbox"}
# Long enough not to match `mna_*`, `mna_<...>` or `mna_…` in a comment that is
# telling you not to do this.
TOKEN_LITERAL = re.compile(r"\bmn[au]_[A-Za-z0-9]{16,}")
SQL_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
DOLLAR_BLOCK = re.compile(r"(?i)\bDO\s*\$\$")
CONCURRENTLY = re.compile(r"(?i)\bCONCURRENTLY\b")
DESTRUCTIVE = (
    (re.compile(r"(?i)\bDROP\s+(TABLE|SCHEMA|DATABASE|TYPE|SEQUENCE)\b"), "DROP"),
    (re.compile(r"(?i)\bDROP\s+COLUMN\b"), "DROP COLUMN"),
    (re.compile(r"(?i)\bTRUNCATE\b"), "TRUNCATE"),
    (re.compile(r"(?i)\bALTER\s+COLUMN\s+\w+\s+TYPE\b"), "ALTER COLUMN ... TYPE"),
    (re.compile(r"(?i)\bDROP\s+CONSTRAINT\b"), "DROP CONSTRAINT"),
)
# What makes an /agent/ handler safe: a verified caller. Any of these names
# in the handler's own signature or body counts.
USER_CONTEXT_MARKERS = ("auth_claims", "verify_user_context", "user_context",
                        "UserContextClaims", "X-Manaurum-User-Context",
                        "USER_CONTEXT_HEADER", "require_user")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def source_files(root: Path, suffixes=None) -> list:
    out = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if suffixes and path.suffix not in suffixes:
            continue
        out.append(path)
    return out


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


# ── Reading routes out of the source ────────────────────────────────────────


class RouteFinder(ast.NodeVisitor):
    """Every HTTP route a Python module registers, with its prefix.

    Decorators, not an import: importing the app would need its dependencies
    installed and would run its module-level code. `ast` needs neither, and
    a route that is not on a decorator is not a route this check can see -
    which it says out loud rather than pretending.
    """

    def __init__(self, module: str):
        self.module = module
        self.prefixes = {}        # variable name -> prefix ("" for app)
        self.routes = []          # (method, path, function node, line)

    def visit_Assign(self, node: ast.Assign) -> None:
        # router = APIRouter(prefix="/agent")   /   app = FastAPI()
        if isinstance(node.value, ast.Call):
            prefix = ""
            for keyword in node.value.keywords:
                if keyword.arg in ("prefix", "url_prefix") and isinstance(
                        keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    prefix = keyword.value.value
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.prefixes[target.id] = prefix
        self.generic_visit(node)

    def _handle(self, node) -> None:
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not isinstance(func, ast.Attribute) or func.attr not in HTTP_METHODS:
                continue
            if not isinstance(func.value, ast.Name):
                continue
            owner = func.value.id
            if not decorator.args:
                continue
            first = decorator.args[0]
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                continue
            prefix = self.prefixes.get(owner, "")
            path = prefix.rstrip("/") + first.value
            self.routes.append((func.attr.upper(), path, node, decorator.lineno))
        self.generic_visit(node)

    visit_FunctionDef = _handle
    visit_AsyncFunctionDef = _handle


def find_routes(root: Path, problems: list, notes: list) -> list:
    """[(method, path, module, line, handler_source)] across the app."""
    modules = [p for p in source_files(root, {".py"})
               if not p.name.startswith("test_") and p.parent.name != "tests"]
    if not modules:
        notes.append("no Python modules here - the route, /agent/ and capability "
                     "rules read Python decorators with `ast` and were skipped. "
                     "Check `runtime.api_routes` against your routes by hand.")
        return []

    routes = []
    for module in modules:
        text = read(module)
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            problems.append("%s:%s: does not parse (%s) - the deploy will build an "
                            "image that cannot start"
                            % (rel(module, root), exc.lineno or 1, exc.msg))
            continue
        finder = RouteFinder(rel(module, root))
        finder.visit(tree)
        for method, path, node, line in finder.routes:
            routes.append((method, path, rel(module, root), line,
                           ast.get_source_segment(text, node) or ""))
    return routes


# ── Rules ───────────────────────────────────────────────────────────────────


def normalise_path(path: str) -> str:
    """A route path with its parameters reduced to one opaque segment."""
    return PATH_PARAM.sub("_", path)


def covered_by(path: str, rules: list) -> bool:
    """Does any `runtime.api_routes` entry cover this path?

    The `/api/x/*` case is the one worth spelling out: a glob covers what is
    UNDER the prefix and not the prefix itself, so declaring `/api/items/*`
    and serving `/api/items` is a 404 on the list screen while every detail
    screen works.
    """
    target = normalise_path(path).rstrip("/") or "/"
    for rule in rules:
        rule = normalise_path(rule)
        if rule.endswith("/*"):
            prefix = rule[:-1]                 # keep the trailing slash
            if target.startswith(prefix) and len(target) > len(prefix):
                return True
        elif rule.endswith("*"):
            if target.startswith(rule[:-1]):
                return True
        elif rule.rstrip("/") == target:
            return True
    return False


def check_routes(manifest: dict, routes: list, problems: list) -> None:
    """Rule 1 - the code and `runtime.api_routes` describe the same surface.

    The single most expensive v2 failure, and the one this whole file exists
    for: `/api/*` is default-deny at the gateway, so an undeclared path is a
    404 the container never sees and the logs never mention.
    """
    declared = [entry.get("path", "") for entry in
                manifest.get("runtime", {}).get("api_routes", [])
                if isinstance(entry, dict)]

    served = []
    for method, path, module, line, _ in routes:
        if not path.startswith("/api/") and path != "/api":
            continue
        served.append(path)
        if not covered_by(path, declared):
            problems.append(
                "%s:%d: %s %s is served but no runtime.api_routes rule covers it - "
                "the gateway answers 404 route_not_declared and this handler never "
                "runs" % (module, line, method, path))

    for rule in declared:
        if rule.endswith("*"):
            prefix = normalise_path(rule).rstrip("*")
            if any(normalise_path(p).startswith(prefix) for p in served):
                continue
        elif any(normalise_path(p).rstrip("/") == normalise_path(rule).rstrip("/")
                 for p in served):
            continue
        problems.append(
            "manifest.json: runtime.api_routes declares %s and nothing serves it - "
            "either the path moved and the manifest did not, or the app is asking "
            "the gateway to forward traffic it will 404 itself" % rule)


def check_agent_handlers(routes: list, problems: list) -> None:
    """Rule 2 - every `/agent/*` handler verifies the caller.

    `/agent/<name>` bypasses the gateway but NOT the network:
    `<slug>.apps.manaurum.com` is Traefik straight to the container, so an
    unauthenticated POST from anywhere on the internet reaches this code.
    The dependency is the only thing stopping it, and "only the runtime calls
    this" is how it gets left out.
    """
    for method, path, module, line, source in routes:
        if not path.startswith("/agent/") and path != "/agent":
            continue
        if any(marker in source for marker in USER_CONTEXT_MARKERS):
            continue
        problems.append(
            "%s:%d: %s %s has no user-context verification - this path is on the "
            "public internet with no gateway in front of it; add the same "
            "Depends(auth_claims) your /api/* routes use" % (module, line, method, path))


def check_entry_point(root: Path, manifest: dict, problems: list) -> None:
    """Rule 3 - `frontend.entry_point` names a file that exists."""
    entry = manifest.get("frontend", {}).get("entry_point")
    if not entry:
        return
    relative = entry.lstrip("/")
    if not relative:
        return
    for base in STATIC_ROOTS:
        if (root / base / relative).is_file():
            return
    problems.append(
        "manifest.json: frontend.entry_point is %s and no such file is in this app "
        "(looked under %s) - the window opens on a 404"
        % (entry, ", ".join(x or "." for x in STATIC_ROOTS)))


def command_ports(text: str) -> set:
    """Ports named in CMD / ENTRYPOINT, in either Docker form.

    The exec form is JSON — `CMD ["uvicorn", …, "--port", "8000"]` — so the
    flag and its value are separate array elements with quotes and a comma
    between them. Flattening the punctuation to spaces first is what makes
    one regex read both forms; without it the check silently found no port at
    all and downgraded itself to a note, on the starter, which is the exact
    shape of a check that is not checking.
    """
    ports = set()
    for line in DOCKER_RUNLINE.findall(text):
        flat = re.sub(r"""["'\[\],]+""", " ", line)
        for match in PORT_IN_COMMAND.finditer(flat):
            ports.add(int(next(group for group in match.groups() if group)))
    return ports


def check_port(root: Path, manifest: dict, problems: list, notes: list) -> None:
    """Rule 4 - one port, in the manifest, in the CMD and in EXPOSE.

    Traefik targets `manifest.runtime.port` (default 80) and never parses
    `EXPOSE`. The deploy goes green either way; every request 502s.
    """
    declared = manifest.get("runtime", {}).get("port", 80)
    dockerfile = root / "Dockerfile"
    if not dockerfile.is_file():
        problems.append("Dockerfile: missing - a v2 app is an image, and the "
                        "platform builds it from this file")
        return
    text = read(dockerfile)

    bound = command_ports(text)
    if bound and declared not in bound:
        problems.append(
            "Dockerfile: the run command binds %s but manifest.runtime.port is %s - "
            "Traefik routes to the manifest's port, so this deploys green and 502s "
            "on every request"
            % (", ".join(str(port) for port in sorted(bound)), declared))
    elif not bound:
        notes.append("Dockerfile: could not read a port out of CMD/ENTRYPOINT, so "
                     "the manifest's port %s was only checked against EXPOSE. Bind "
                     "0.0.0.0:%s inside the container." % (declared, declared))

    exposed = [int(port) for port in EXPOSE.findall(text)]
    for port in exposed:
        if port != declared:
            problems.append(
                "Dockerfile: EXPOSE %d but manifest.runtime.port is %s. EXPOSE is "
                "decoration - the platform never parses it - but a decoration that "
                "disagrees is what the next reader will believe" % (port, declared))


def check_manifest_shape(manifest: dict, problems: list) -> None:
    """Rules the skill states and nothing enforced.

    The root object is strict - `additionalProperties: false` over 23 keys -
    so a typo up there is a 422 and finds itself. `runtime` is NOT: an
    invented key, or `"prot": 8000`, validates, deploys green and is silently
    ignored. That costs a debugging session rather than a rejection, which is
    the worse of the two.
    """
    runtime = manifest.get("runtime", {})
    if isinstance(runtime, dict):
        for key in sorted(set(runtime) - RUNTIME_KEYS):
            problems.append(
                "manifest.json: runtime.%s is not a key the platform reads. The "
                "runtime object is not strict, so this validates, deploys green "
                "and does nothing - check the spelling against %s"
                % (key, ", ".join(sorted(RUNTIME_KEYS))))

    for entry in runtime.get("api_routes", []) if isinstance(runtime, dict) else []:
        if isinstance(entry, dict) and str(entry.get("path", "")).startswith("/agent"):
            problems.append(
                "manifest.json: runtime.api_routes declares %s - /agent/* is "
                "dispatched straight to your container and is not a gateway route, "
                "so listing it here configures nothing while looking like it did"
                % entry["path"])

    icon = manifest.get("frontend", {}).get("icon")
    if isinstance(icon, str) and icon and not icon.startswith(("/", "http://", "https://")):
        if "/" in icon or "." in icon:
            problems.append(
                "manifest.json: frontend.icon is %r, a relative path - it is not "
                "resolved, it is painted into the tile as that literal string. Use "
                "an emoji, an absolute URL, or omit the field for a clean "
                "placeholder" % icon)

    description = manifest.get("metadata", {}).get("description", "")
    if isinstance(description, str) and description.strip().upper().startswith("TODO"):
        problems.append(
            "manifest.json: metadata.description is still the starter's "
            "placeholder (%r) - it is what a tenant admin reads on the install "
            "screen" % description)


def check_secret_literals(root: Path, problems: list) -> None:
    """A deploy token baked into the image.

    Your `mna_*` token is a laptop credential for `POST /api/dev/v2/deploy`.
    An image containing it hands every future reader your deploy rights, and
    the build context is retained per version in object storage.
    """
    for path in source_files(root):
        if path.suffix in (".png", ".jpg", ".gif", ".ico", ".woff", ".woff2"):
            continue
        for match in TOKEN_LITERAL.finditer(read(path)):
            problems.append(
                "%s: what looks like a live %s... token - never bake one into the "
                "build context; the platform injects MANAURUM_RUNTIME_TOKEN at run "
                "time" % (rel(path, root), match.group(0)[:8]))
            break


def note_missing_tests(root: Path, notes: list) -> None:
    """Nothing here makes you write tests. This at least says so out loud.

    The starter ships a suite that covers the wiring rather than the pieces,
    and it is meant to be copied. An app with no tests at all is the common
    shape, and the only signal today is prose in a section nobody re-reads.
    """
    for path in source_files(root):
        name = path.name
        if name.startswith("test_") or name.endswith("_test.py") or ".test." in name:
            return
        if path.parent.name in ("tests", "test", "__tests__"):
            return
    notes.append("no tests in this app. The starter's suite covers the wiring - "
                 "remove an auth dependency from a route and a test goes red - and "
                 "it is there to be copied. Start with your routes against your "
                 "manifest, which is what this linter automates.")


def check_env_files(root: Path, problems: list) -> None:
    """Rule 5 - no `.env*` anywhere inside the deployed directory.

    The packer's exclusion list is exact names with no globs and no `.env*`
    entry. A `.env.manaurum` beside the Dockerfile is packed verbatim, baked
    into an image layer, retained per version in object storage and committed
    to a per-app git history. There is no practical way to un-leak it.
    """
    for path in source_files(root):
        if path.name.startswith(".env"):
            problems.append(
                "%s: a .env file inside the app directory - the packer has no "
                "`.env*` exclusion, so this is uploaded, baked into a layer and "
                "retained per version. Move it one level up, beside the app "
                "directory rather than inside it" % rel(path, root))


def check_capabilities(root: Path, manifest: dict, problems: list) -> None:
    """Rule 6 - called and declared are the same set.

    An undeclared call is 403 `capability_not_granted` at the first real use.
    A declared call that never happens is an over-broad grant the tenant
    admin is asked to approve for nothing - and grants are the one place a
    person outside your team reads your manifest.
    """
    declared = set()
    for entry in manifest.get("requires_capabilities", []):
        if isinstance(entry, dict) and entry.get("name"):
            declared.add(entry["name"])
        elif isinstance(entry, str):
            declared.add(entry)

    called = {}
    for path in source_files(root):
        if path.suffix in (".png", ".jpg", ".gif", ".ico", ".svg", ".woff", ".woff2"):
            continue
        if path.name == "manifest.json":
            continue
        try:
            text = read(path)
        except OSError:                                        # pragma: no cover
            continue
        for name in CAPABILITY.findall(text):
            called.setdefault(name, rel(path, root))

    for name, where in sorted(called.items()):
        if name not in declared:
            problems.append(
                "%s: calls %s but manifest.requires_capabilities does not declare it "
                "- the gateway answers 403 capability_not_granted at the first call"
                % (where, name))
    for name in sorted(declared - set(called)):
        problems.append(
            "manifest.json: requires_capabilities asks for %s and nothing in this "
            "app calls it - an over-broad grant request, and the install screen is "
            "where a tenant admin reads it" % name)


def real_validator():
    """The deploy's own AST validator, when the author has the CLI installed.

    MAN-2624. The regex list below is a subset of the real rules and always
    will be: it cannot see the two context-sensitive ones (a plain
    `CREATE INDEX` is additive on a table created earlier in the same file
    and destructive on a pre-existing one; likewise `SET NOT NULL` on a
    fresh column), and it cannot see the transactionality rule at all.
    Core is explicit that regexes are the wrong instrument here -
    "regex-based detection is explicitly rejected: the AST is the contract".

    So: when `manaurum-cli` is importable, defer to it and report exactly
    what the deploy will say. When it is not, fall back to the subset and
    SAY SO, rather than letting "clean" mean two different things.

    This keeps the script's stdlib-only promise: nothing here is required,
    and the import failing is an ordinary outcome, not an error.
    """
    try:
        from manaurum_cli.migrations import (  # noqa: PLC0415
            MigrationValidationError,
            validate_migration,
        )
    except Exception:  # noqa: BLE001 - not installed is the common case
        return None
    return validate_migration, MigrationValidationError


def check_migrations(root: Path, manifest: dict, problems: list,
                     notes: list) -> None:
    """Rule 7 - `*.sql` only, ordered, and nothing the deploy will refuse.

    Migrations run once per (app, tenant) in filename order, and the DDL is
    AST-validated at deploy, PER FILE. Two things follow that the packaging
    rules cannot tell you on their own: a destructive statement without
    `migration.breaking` is a 422, and a file that uses `CONCURRENTLY` may
    contain nothing else, because `CREATE INDEX CONCURRENTLY` cannot run
    inside a transaction block and the rest of the file needs one.
    """
    directory = root / "migrations"
    if not directory.is_dir():
        return
    breaking = bool(manifest.get("migration", {}).get("breaking"))
    validator = real_validator()
    if validator is None:
        notes.append(
            "migrations/: checked with the built-in pattern list, which is a "
            "subset of the deploy's rules. `pip install manaurum-cli` (or "
            "`manaurum app validate-migration migrations/`) to run the same "
            "AST validator the deploy runs")

    numbers = {}
    for path in sorted(directory.iterdir()):
        if path.is_dir():
            problems.append("migrations/%s: a directory - migrations are flat "
                            "`*.sql` files" % path.name)
            continue
        if path.suffix.lower() != ".sql":
            problems.append("migrations/%s: not a .sql file - the pipeline runs "
                            "plain SQL and ignores everything else, so this will "
                            "silently never run" % path.name)
            continue
        match = MIGRATION_NUMBER.match(path.name)
        if not match:
            problems.append("migrations/%s: no leading number - they run in "
                            "filename order, so the order has to be visible "
                            "(0001_init.sql)" % path.name)
        else:
            numbers.setdefault(int(match.group(1)), []).append(path.name)

        if validator is not None:
            # The authority. One file at a time, exactly as the deploy reads
            # them - handing it several concatenated would answer a different
            # question for the two context-sensitive rules.
            validate_migration, MigrationValidationError = validator
            try:
                validate_migration(read(path), breaking_allowed=breaking)
            except MigrationValidationError as exc:
                for err in getattr(exc, "errors", []):
                    problems.append("migrations/%s: %s - %s" % (
                        path.name, err.get("classification", "rejected"),
                        err.get("reason", "")))
            except Exception as exc:  # noqa: BLE001 - unparseable SQL
                problems.append("migrations/%s: the deploy's validator could "
                                "not parse this - %s" % (path.name, exc))
            continue

        body = SQL_COMMENT.sub(" ", read(path))
        # MAN-2624, the subset version. `CREATE INDEX CONCURRENTLY` cannot run
        # inside a transaction block and the rest of the file needs one, so the
        # deploy runs a CONCURRENTLY-only file outside a transaction and
        # refuses one that mixes. Without this the rule had no local coverage
        # at all: the author hit it for the first time in production, having
        # arrived there by following the "use CONCURRENTLY" advice literally.
        # Comments are already stripped above, so the word in a comment does
        # not count; a string literal still would, which is one of the reasons
        # the real validator above is preferred when it is available.
        statements = [s for s in body.split(";") if s.strip()]
        concurrent = [s for s in statements if CONCURRENTLY.search(s)]
        if concurrent and len(concurrent) != len(statements):
            problems.append(
                "migrations/%s: CONCURRENTLY shares the file with %d other "
                "statement(s) - a file that uses CONCURRENTLY must contain "
                "nothing else, because CONCURRENTLY cannot run inside a "
                "transaction and the rest of the file needs one. Put the "
                "index in its own file" % (
                    path.name, len(statements) - len(concurrent)))
        if DOLLAR_BLOCK.search(body):
            problems.append("migrations/%s: a DO $$ ... $$ block - the DDL "
                            "validator cannot analyse an anonymous PL/pgSQL body "
                            "and refuses the deploy; expand it into plain "
                            "statements" % path.name)
        for pattern, label in DESTRUCTIVE:
            if pattern.search(body) and not breaking:
                problems.append(
                    "migrations/%s: %s without manifest.migration.breaking - the "
                    "validator rejects the deploy, and if it did not this would "
                    "drop tenant data" % (path.name, label))

    for number, names in sorted(numbers.items()):
        if len(names) > 1:
            problems.append("migrations/: %s share the number %d - filename order "
                            "decides which runs first, and it is not the order you "
                            "meant" % (", ".join(sorted(names)), number))

    widths = {len(MIGRATION_NUMBER.match(name).group(1))
              for names in numbers.values() for name in names
              if MIGRATION_NUMBER.match(name)}
    if len(widths) > 1:
        problems.append("migrations/: the numbers are not zero-padded to the same "
                        "width, so 10_ sorts before 9_ and the migrations run in "
                        "the wrong order")


def load_manifest(root: Path, problems: list):
    path = root / "manifest.json"
    if not path.is_file():
        print("no manifest.json in %s - pass the directory the deploy packs" % root)
        return None
    try:
        data = json.loads(read(path))
    except ValueError as exc:
        problems.append("manifest.json: does not parse - %s" % exc)
        return None
    if not isinstance(data, dict):
        problems.append("manifest.json: is not an object")
        return None
    return data


def check(root: Path) -> tuple:
    problems, notes = [], []
    manifest = load_manifest(root, problems)
    if manifest is None:
        return problems, notes

    routes = find_routes(root, problems, notes)
    check_routes(manifest, routes, problems)
    check_agent_handlers(routes, problems)
    check_entry_point(root, manifest, problems)
    check_port(root, manifest, problems, notes)
    check_env_files(root, problems)
    check_capabilities(root, manifest, problems)
    check_migrations(root, manifest, problems, notes)
    check_manifest_shape(manifest, problems)
    check_secret_literals(root, problems)
    note_missing_tests(root, notes)
    return problems, notes


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    if not target.is_dir():
        print("not a directory: %s - pass the directory that holds manifest.json"
              % target)
        return 2
    if not (target / "manifest.json").is_file():
        print("no manifest.json in %s - pass the directory the deploy packs, not "
              "the workspace above it" % target)
        return 2

    problems, notes = check(target)
    for note in notes:
        print("- %s" % note)
    for problem in sorted(set(problems)):
        print("x %s" % problem)
    print("%d problem(s)" % len(set(problems)) if problems else "clean")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

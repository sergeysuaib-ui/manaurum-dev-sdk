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
    port disagreement       a build and push, then a failed readiness probe.
    an /agent/ handler with
    no user-context check   an endpoint any other app's container can
                            call, which nothing will ever tell you about.
    an undeclared
    capability              403 capability_not_granted at the first call, in
                            production, from a user.
    a .env* in the app dir  packed into the build context, baked into an
                            image layer, retained per version in object
                            storage. There is no way to un-leak it.

The platform's own lists are not copied into this file. The manifest schema,
the registered capabilities, the reserved slugs and the write-verb rule come
from `manifest_v2.schema.json` and `platform-contract.json` beside it, which
`scripts/sync_contract.py` refreshes from Core and `scripts/check_repo.py`
holds the documents to.

Standard library only, with one optional upgrade: if a usable `manaurum-cli`
is importable, the migration rule defers to the deploy's own AST validator
instead of its built-in pattern list. Nothing needs installing for the
script to run - and whatever a run could NOT check, it says so in a note,
so `clean` means one thing rather than two.

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

HERE = Path(__file__).resolve().parent

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
# The same name inside a URL: f"{core}/api/capability/os.kv.get". The shift
# checklist called the gateway this way and the quoted-name rule never saw it.
CAPABILITY_URL = re.compile(r"/api/capability/(os\.[a-z_]+(?:\.[a-z_]+)+)")
# The stdlib's, in a string: `"os.path.join"` in a docstring is not a call.
STDLIB_OS = ("os.path.", "os.environ", "os.getenv", "os.sep", "os.linesep")
# What reads as code for the capability rule. A name in a README, a CHANGELOG
# or a test is not a call the deployed app makes.
CODE_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go",
                 ".rb", ".java", ".kt", ".rs", ".php", ".cs", ".sh"}
# A FastAPI path parameter, an Express one (a whole segment, so `/a:b` is
# a literal), and a Flask one.
PATH_PARAM = re.compile(r"\{[^}]+\}|(?<=/):[A-Za-z_][A-Za-z0-9_]*|<[^>]+>")
EXPOSE = re.compile(r"(?mi)^\s*EXPOSE\s+(\d+)")
# `--port 8000`, `--port=8000`, `-p 8000`, `0.0.0.0:8000`.
PORT_IN_COMMAND = re.compile(r"--port[=\s]+(\d+)|\s-p[=\s]+(\d+)|0\.0\.0\.0:(\d+)")
DOCKER_RUNLINE = re.compile(r"(?mi)^\s*(?:CMD|ENTRYPOINT)\s+(.*)$")
MIGRATION_NUMBER = re.compile(r"^(\d+)")
# The keys `runtime.properties` declares, used only when the vendored schema
# is missing. `runtime` has been strict since MAN-1899 (2026-08-23), so a key
# outside this set is a 422 at deploy. A key the platform reads that is
# missing from it is worse than no check at all: every app that uses it gets a
# red it does not deserve (`public_paths` and `health_path` did, until 3.1.0).
# `check_repo.py` fails the build if this copy and the schema disagree.
RUNTIME_KEYS = {"mode", "port", "api_routes", "public_paths", "health_path",
                "egress_allowed_hosts", "resources", "sandbox", "entrypoint",
                "replicas", "image"}
UUID_SHAPED = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# Names an Assistant tool reads with. Omitting `is_write` on one of these makes
# every call ask the user for approval.
READ_VERB_PREFIXES = ("list_", "get_", "read_", "find_", "search_", "show_",
                      "count_", "lookup_", "describe_")
# The shapes Core mints. An `mna_*` is `mna_<12 hex>_<32 url-safe>`
# (routes/developer/v2_credentials.py: token_hex(6), token_urlsafe(24)) and an
# `mnu_*` is `mnu_<prod|staging|dev>_<32 url-safe>`
# (services/tenant_developer_api_token.py). Both have an underscore after the
# prefix part and may have `-`/`_` in the secret. Until 3.2.0 this pattern was
# `mn[au]_[A-Za-z0-9]{16,}`, which matches neither, so the rule never fired on
# a real token; it stays as the third branch. The first two are exact rather
# than loose so an identifier like `mna_token_from_the_environment` is not a
# "token". None of them matches `mna_*`, `mna_<keyid>_<secret>` or `mna_…` in
# a comment that is telling you not to do this.
TOKEN_LITERAL = re.compile(
    r"\bmna_[0-9a-f]{12}_[A-Za-z0-9_-]{32}"
    r"|\bmnu_(?:prod|staging|dev)_[A-Za-z0-9_-]{32}"
    r"|\bmn[au]_[A-Za-z0-9]{16,}")
# `$$`, `$body$`: the opening of a dollar-quoted string.
DOLLAR_TAG = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")
# The one string worth keeping: `LANGUAGE 'plpgsql'`.
PLAIN_WORD = re.compile(r"[A-Za-z0-9_]{1,24}")
AFTER_LANGUAGE = re.compile(r"(?i)\bLANGUAGE\s*$")
# `BEGIN ATOMIC` up to the END that starts a statement (or an empty body).
BEGIN_ATOMIC = re.compile(r"(?is)\bBEGIN\s+ATOMIC\b(?:\s*END\b|.*?;\s*END\b)")
# An anonymous block, whatever quotes its body: DO $$, DO $x$, DO '...'.
DOLLAR_BLOCK = re.compile(r"(?i)\bDO\s*(?:LANGUAGE\s+\w+\s*)?(?:\$BODY\$|E?'')")
DESTRUCTIVE = (
    (re.compile(r"(?i)\bDROP\s+(TABLE|SCHEMA|TYPE|SEQUENCE|INDEX|VIEW|"
                r"MATERIALIZED\s+VIEW|FUNCTION|PROCEDURE|TRIGGER|POLICY|DOMAIN|EXTENSION)\b"),
     "DROP"),
    (re.compile(r"(?i)\bDROP\s+COLUMN\b"), "DROP COLUMN"),
    # `ALTER TABLE t DROP c` - COLUMN is optional.
    (re.compile(r"(?is)\bALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?[\w.\"]+\s+"
                r"(?:[^;]*?,\s*)?DROP\s+(?!COLUMN\b|CONSTRAINT\b|DEFAULT\b|NOT\b|"
                r"IDENTITY\b|EXPRESSION\b)(?:IF\s+EXISTS\s+)?[\w\"]"), "DROP COLUMN"),
    (re.compile(r"(?i)\bTRUNCATE\b"), "TRUNCATE"),
    (re.compile(r"(?i)\bALTER\s+(?:COLUMN\s+)?[\w\"]+\s+(?:SET\s+DATA\s+)?TYPE\b"),
     "ALTER COLUMN ... TYPE"),
    (re.compile(r"(?i)\bDROP\s+CONSTRAINT\b"), "DROP CONSTRAINT"),
    (re.compile(r"(?i)\bRENAME\b"), "RENAME"),
    (re.compile(r"(?i)\bREVOKE\b"), "REVOKE"),
)
# Refused whatever `migration.breaking` says. Matched at the start of a
# statement, which is where the deploy's validator classifies them.
FORBIDDEN = (
    (re.compile(r"(?i)^(BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE|START\s+TRANSACTION|"
                r"END)\b"), "transaction control"),
    (re.compile(r"(?i)^(SET|RESET)\b"), "SET"),
    (re.compile(r"(?i)^COPY\b"), "COPY"),
    # DROP EXTENSION is a DropStmt, which the deploy calls destructive (above).
    (re.compile(r"(?i)^(CREATE|ALTER)\s+EXTENSION\b"), "an extension (use data.extensions)"),
    (re.compile(r"(?i)^(CREATE|ALTER|DROP)\s+(ROLE|USER|GROUP|DATABASE|TABLESPACE)\b"),
     "role or database DDL"),
    (re.compile(r"(?i)^ALTER\s+SYSTEM\b"), "ALTER SYSTEM"),
    (re.compile(r"(?is)^GRANT\b(?!.*\bON\b)"), "GRANT of a role"),
    # Only sql and plpgsql are trusted, and a function that names no
    # LANGUAGE is refused too.
    (re.compile(r"(?is)^CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\b"
                r"(?!.*\bLANGUAGE\s+'?(?:sql|plpgsql)\b)"),
     "a function language other than sql or plpgsql"),
)
# All migration files together, as the deploy measures them (MAN-2622).
MAX_MIGRATION_BYTES = 64 * 1024
# What makes an /agent/ handler safe: a verified caller, as code. One of these
# called directly, or passed to Depends()/Security() on the handler, its route
# decorator, its router or the include_router that mounts it.
AUTH_FUNCTIONS = ("auth_claims", "verify_user_context", "require_user",
                  "get_user_context", "user_context_claims")
# A `Depends` on a function the app does not define, named for what it does.
# A name that says user context, claims or verify is taken at its word. One
# that only says auth/user/token is taken too, but out loud, as a note: this
# linter cannot read it, and the usual thing behind such a name reads a
# header the gateway never forwards.
EXTERNAL_VERIFIER_NAME = re.compile(r"(?i)user_?context|claims")
EXTERNAL_AUTH_NAME = re.compile(r"(?i)auth|user|token|verif|caller|principal|identity")
# FastAPI's own security schemes read `Authorization`, a cookie or an API-key
# header. The gateway strips the first two and the runtime sends none of
# them, so a `Depends` on one of these verifies nothing here.
SECURITY_SCHEMES = {"OAuth2PasswordBearer", "OAuth2AuthorizationCodeBearer", "OAuth2",
                    "HTTPBearer", "HTTPBasic", "HTTPDigest", "APIKeyHeader",
                    "APIKeyCookie", "APIKeyQuery", "OpenIdConnect"}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def sql_code(text: str) -> str:
    """The SQL with everything that is not code blanked out.

    A pattern run over the raw text finds `DROP TABLE` inside a string, a
    comment or a function body, and loses the rest of a line to `--` inside
    `'a -- b'`. So: comments (nested `/* */` too) become a space, a string
    becomes `''` (kept after LANGUAGE, for `LANGUAGE 'c'`), a
    quoted identifier `"q"`, and a dollar-quoted body - a function's or a DO
    block's - `$BODY$`. What is left splits safely on `;`.
    """
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("--", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
            out.append(" ")
        elif text.startswith("/*", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if text.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif text.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            out.append(" ")
        elif c == "'":
            escapes = i > 0 and text[i - 1] in "eE" and \
                (i < 2 or not (text[i - 2].isalnum() or text[i - 2] == "_"))
            j, content = i + 1, []
            while j < n:
                if escapes and text[j] == "\\":
                    content.append(text[j:j + 2])
                    j += 2
                elif text.startswith("''", j):
                    content.append("'")
                    j += 2
                elif text[j] == "'":
                    break
                else:
                    content.append(text[j])
                    j += 1
            word = "".join(content)
            keep = PLAIN_WORD.fullmatch(word) and \
                AFTER_LANGUAGE.search("".join(out[-64:]).rstrip())
            out.append("'%s'" % (word if keep else ""))
            i = j + 1
        elif c == '"':
            j = i + 1
            while j < n:
                if text.startswith('""', j):
                    j += 2
                elif text[j] == '"':
                    break
                else:
                    j += 1
            out.append('"q"')
            i = j + 1
        elif c == "$" and not (i > 0 and (text[i - 1].isalnum() or text[i - 1] == "_")) \
                and DOLLAR_TAG.match(text, i):
            tag = DOLLAR_TAG.match(text, i).group(0)
            end = text.find(tag, i + len(tag))
            i = n if end < 0 else end + len(tag)
            out.append(" $BODY$ ")
        else:
            out.append(c)
            i += 1
    # A SQL-standard function body, `BEGIN ATOMIC ... END`, is one statement
    # to the deploy (a CreateFunctionStmt); its inner `;` and `END` are not.
    return BEGIN_ATOMIC.sub(" $BODY$ ", "".join(out))


def load_contract(notes: list):
    """(schema, contract) from the files beside this script, or (None, None).

    A copy of this script without them still runs every rule that needs no
    platform list, and says which ones it skipped.
    """
    try:
        schema = json.loads(read(HERE / "manifest_v2.schema.json"))
        contract = json.loads(read(HERE / "platform-contract.json"))
        return schema, contract
    except (OSError, ValueError):
        notes.append("manifest_v2.schema.json / platform-contract.json are not "
                     "beside this script, so the root-key, slug, capability-name "
                     "and Assistant-tool rules were skipped. Run the copy in the "
                     "plugin's templates/ directory.")
        return None, None


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
#
# When this cannot trace where a router is mounted (a loop, a factory call, a
# computed prefix, `app.mount`), it keeps the router's routes at the router's
# own prefix and says less, never more: a false red teaches people to ignore
# the linter, and a route dropped from the /agent rule is worse.


def _name_of(node) -> str:
    """`auth_claims` for `auth_claims`, `auth.auth_claims` or `src.auth.auth_claims`."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _keyword(call: ast.Call, *names):
    for keyword in call.keywords:
        if keyword.arg in names:
            return keyword.value
    return None


def _own_nodes(node):
    """Everything under `node` except the inside of nested defs and lambdas.

    A verifier called only in a helper the handler defines and never calls is
    not a check.
    """
    stack = list(ast.iter_child_nodes(node))
    while stack:
        current = stack.pop()
        yield current
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                                ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(current))


class Verifiers:
    """The names that verify a user context, across the whole app.

    Starts from the SDK's own and grows to a fixpoint: a function whose
    parameters or own body call one, or `Depends`/`Security` on one, is one
    (`current_user` wrapping `verify_user_context` - the shape of the CLI
    scaffold), and so is a module-level alias such as
    `Claims = Annotated[UserContextClaims, Depends(auth_claims)]`. A `Depends`
    on a function the app does not define (a library's) counts when its name
    says what it is for: this linter cannot read it, and guessing red there
    is the false alarm that gets a linter switched off. A name that only says
    auth/user/token is reported as a note, and FastAPI's own security schemes
    (`OAuth2PasswordBearer` and the rest) never count: they read headers the
    gateway strips.
    """

    def __init__(self, trees: list):
        self.names = set(AUTH_FUNCTIONS)
        self.defined = set()
        self.schemes = set()      # oauth2_scheme = OAuth2PasswordBearer(...)
        self.assumed = set()      # external names taken at their word
        functions, aliases = [], []
        for tree in trees:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(node)
                    self.defined.add(node.name)
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and \
                        isinstance(node.targets[0], ast.Name):
                    aliases.append((node.targets[0].id, node.value))
                elif isinstance(node, ast.AnnAssign) and \
                        isinstance(node.target, ast.Name) and node.value is not None:
                    aliases.append((node.target.id, node.value))
        # Security schemes wherever they are assigned (annotated, inside an
        # `if`/`try`), then under whatever name another module imports them.
        imports, classes = [], set(SECURITY_SCHEMES)
        for tree in trees:
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    classes.update(a.asname for a in node.names
                                   if a.asname and a.name in SECURITY_SCHEMES)
        for tree in trees:
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AnnAssign)) and \
                        isinstance(node.value, ast.Call) and \
                        _name_of(node.value.func) in classes:
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    self.schemes.update(t.id for t in targets if isinstance(t, ast.Name))
                elif isinstance(node, ast.ImportFrom):
                    imports.extend((a.name, a.asname) for a in node.names if a.asname)
        for name, asname in imports:
            if name in self.schemes:
                self.schemes.add(asname)
        self.schemes |= classes - SECURITY_SCHEMES      # Depends(Bearer())
        changed = True
        while changed:
            changed = False
            for function in functions:
                if function.name not in self.names and self.guards_function(function):
                    self.names.add(function.name)
                    changed = True
            for name, value in aliases:
                if name not in self.names and self.guards(value):
                    self.names.add(name)
                    changed = True

    def is_verifier(self, name: str) -> bool:
        return name in self.names or name.startswith("verify_user_context")

    def _dependency(self, name: str) -> bool:
        if self.is_verifier(name):
            return True
        if name in self.defined or name in self.schemes or name in SECURITY_SCHEMES:
            return False
        if EXTERNAL_VERIFIER_NAME.search(name):
            return True
        if EXTERNAL_AUTH_NAME.search(name):
            self.assumed.add(name)
            return True
        return False

    def guards(self, node, own: bool = False) -> bool:
        """Does this expression, or a statement under it, verify the caller?

        Read from the AST, not the text: a name in a comment or a docstring
        is not a check, and `claims: UserContextClaims | None = None` without
        a `Depends` is an open handler however it is annotated.
        """
        if node is None:
            return False
        for sub in (_own_nodes(node) if own else ast.walk(node)):
            if isinstance(sub, ast.Call):
                called = _name_of(sub.func)
                if self.is_verifier(called):
                    return True
                if called in ("Depends", "Security") and sub.args and \
                        self._dependency(_name_of(sub.args[0])):
                    return True
            elif isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load) and \
                    sub.id in self.names and sub.id not in AUTH_FUNCTIONS:
                # `claims: Claims`, an alias defined above.
                return True
        return False

    def guards_function(self, function) -> bool:
        return self.guards(function.args) or self.guards(function, own=True)


def module_key(root: Path, path: Path) -> tuple:
    """(`src.agent_routes`, False) for src/agent_routes.py, (`src.agent`, True)
    for src/agent/__init__.py."""
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        return ".".join(parts[:-1]), True
    return ".".join(parts), False


class RouteFinder(ast.NodeVisitor):
    """Every HTTP route a Python module registers, and how its routers mount.

    Decorators, `add_api_route` and `include_router`, read with `ast`: no
    import, so no dependencies installed and no module-level code run.
    """

    def __init__(self, key: str, package: bool, module: str):
        self.key = key            # dotted module key
        self.package = package    # an __init__.py
        self.module = module      # path, for messages
        self.constants = {}       # NAME -> "string", for prefix=PREFIX
        self.prefixes = {}        # variable assigned from a call -> its own prefix
        self.router_deps = {}     # variable -> its dependencies= node
        self.routes = []          # (method, path, owner, handler, line, deps node)
        self.includes = []        # (owner, target expr, prefix or None, deps node)
        self.imports = {}         # local name -> "pkg.mod" or "pkg.mod:name"
        self.functions = {}       # name -> node
        self.untraced = []        # mounts it does not follow

    def _string(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return self.constants.get(node.id)
        return None

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = node.module or ""
        if node.level:
            package = self.key.split(".") if self.key else []
            if not self.package:
                package = package[:-1]
            if node.level > 1:
                package = package[:max(0, len(package) - (node.level - 1))]
            base = ".".join(package + ([base] if base else []))
        for alias in node.names:
            self.imports[alias.asname or alias.name] = "%s:%s" % (base, alias.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.asname:
                self.imports[alias.asname] = alias.name
            else:
                head = alias.name.split(".")[0]
                self.imports[head] = head
        self.generic_visit(node)

    def _assign(self, targets, value) -> None:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for target in targets:
                if isinstance(target, ast.Name):
                    self.constants[target.id] = value.value
            return
        if not isinstance(value, ast.Call):
            return
        # router = APIRouter(prefix="/agent") / app = FastAPI() / bp = Blueprint(...)
        prefix = self._string(_keyword(value, "prefix", "url_prefix")) or ""
        for target in targets:
            if isinstance(target, ast.Name):
                self.prefixes[target.id] = prefix
                self.router_deps[target.id] = _keyword(value, "dependencies")

    def visit_Assign(self, node: ast.Assign) -> None:
        self._assign(node.targets, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._assign([node.target], node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            owner = func.value.id
            if func.attr in ("include_router", "register_blueprint"):
                target = node.args[0] if node.args else _keyword(node, "router", "blueprint")
                prefix = _keyword(node, "prefix", "url_prefix")
                self.includes.append((owner, target,
                                      "" if prefix is None else self._string(prefix),
                                      _keyword(node, "dependencies")))
            elif func.attr == "mount":
                path = self._string(node.args[0]) if node.args else None
                # Static files under / or /static are not routes the gateway
                # forwards; a sub-app under /api or /agent is.
                if path is None or path.startswith(("/api", "/agent")):
                    self.untraced.append("%s.mount(...)" % owner)
            elif func.attr == "add_api_route":
                path = self._string(node.args[0] if node.args else _keyword(node, "path"))
                if path is not None:
                    methods = _keyword(node, "methods")
                    names = [(self._string(m) or "GET").upper()
                             for m in getattr(methods, "elts", [])] or ["GET"]
                    handler = node.args[1] if len(node.args) > 1 else _keyword(node, "endpoint")
                    for method in names:
                        self.routes.append((method, path, owner, handler, node.lineno,
                                            _keyword(node, "dependencies")))
        elif _name_of(func) in ("Route", "Mount", "WebSocketRoute", "Host") and \
                node.args and self._string(node.args[0]) is not None:
            # A Starlette route table: served, and not read here.
            self.untraced.append("%s(%r)" % (_name_of(func), self._string(node.args[0])))
        self.generic_visit(node)

    def _handle(self, node) -> None:
        self.functions[node.name] = node
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not isinstance(func, ast.Attribute) or func.attr not in HTTP_METHODS:
                continue
            if not isinstance(func.value, ast.Name):
                continue
            path = self._string(decorator.args[0] if decorator.args
                                else _keyword(decorator, "path"))
            if path is None:
                continue
            method = func.attr.upper()
            if method == "ROUTE":            # Flask: methods=[...], GET by default
                methods = _keyword(decorator, "methods")
                names = [elt.value for elt in getattr(methods, "elts", [])
                         if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
                method = "/".join(name.upper() for name in names) or "GET"
            self.routes.append((method, path, func.value.id, node,
                                decorator.lineno, _keyword(decorator, "dependencies")))
        self.generic_visit(node)

    visit_FunctionDef = _handle
    visit_AsyncFunctionDef = _handle


def find_routes(root: Path, problems: list, notes: list) -> tuple:
    """([(method, path, module, line, handler_source, verifies_caller)], traced).

    A route's path is what the gateway sees: the prefix of every router that
    mounts it, outermost first, then its own router's, then its own. `traced`
    is False when some mount could not be followed; `check_routes` then only
    notes a declared rule nothing seems to serve.
    """
    modules = [p for p in source_files(root, {".py"})
               if not p.name.startswith("test_") and p.parent.name != "tests"]
    if not modules:
        notes.append("no Python modules here - the route, /agent/ and capability "
                     "rules read Python decorators with `ast` and were skipped. "
                     "Check `runtime.api_routes` against your routes by hand.")
        return [], False

    finders, texts, trees = {}, {}, []
    for module in modules:
        text = read(module)
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            problems.append("%s:%s: does not parse (%s) - the deploy will build an "
                            "image that cannot start"
                            % (rel(module, root), exc.lineno or 1, exc.msg))
            continue
        key, package = module_key(root, module)
        finder = RouteFinder(key, package, rel(module, root))
        finder.visit(tree)
        finders[key] = finder
        texts[key] = text
        trees.append(tree)
    verifiers = Verifiers(trees)

    def module_named(name: str):
        # `src.agent_routes` from the app directory, or `agent_routes` when the
        # app runs with src/ on the path.
        if name in finders:
            return name
        matches = [key for key in finders if key.endswith("." + name)]
        return matches[0] if len(matches) == 1 else None

    def variable(module, name, depth=0):
        """Follow re-exports to the module that assigns `name`."""
        finder = finders.get(module) if module is not None else None
        if finder is None or depth > 5:
            return None
        if name in finder.prefixes:
            return (module, name)
        imported = finder.imports.get(name)
        if imported and ":" in imported:
            source, original = imported.split(":", 1)
            return variable(module_named(source), original, depth + 1)
        return None

    def lookup(finder, target):
        if isinstance(target, ast.Name):
            return variable(finder.key, target.id)
        if isinstance(target, ast.Attribute):
            chain, node = [], target
            while isinstance(node, ast.Attribute):
                chain.insert(0, node.attr)
                node = node.value
            if not isinstance(node, ast.Name):
                return None
            head = finder.imports.get(node.id, node.id).replace(":", ".")
            return variable(module_named(".".join([head] + chain[:-1])), chain[-1])
        return None

    traced = True
    parents = {}                  # (module, var) -> [((module, var), prefix, deps)]
    for key, finder in finders.items():
        for what in finder.untraced:
            traced = False
            notes.append("%s: %s is not followed - what it serves is not checked "
                         "against runtime.api_routes" % (finder.module, what))
        for owner, target, prefix, deps in finder.includes:
            child = lookup(finder, target)
            if child is None or prefix is None:
                traced = False
                notes.append("%s: an include this linter cannot follow (a loop, a "
                             "call or a computed prefix) - routes under it are "
                             "checked at their own router's prefix only"
                             % finder.module)
                continue
            parents.setdefault(child, []).append(((key, owner), prefix, deps))

    def mounts(router, seen=()):
        """[(prefix above the router's own, guarded by something above)]."""
        if router not in parents or router in seen:
            return [("", False)]
        out = []
        for parent, prefix, deps in parents[router]:
            finder = finders[parent[0]]
            above = finder.prefixes.get(parent[1], "").rstrip("/") + prefix.rstrip("/")
            guard = verifiers.guards(deps) or \
                verifiers.guards(finder.router_deps.get(parent[1]))
            for outer, outer_guard in mounts(parent, seen + (router,)):
                out.append((outer.rstrip("/") + above, guard or outer_guard))
        return out

    routes = []
    for key, finder in finders.items():
        for method, path, owner, node, line, deps in finder.routes:
            if isinstance(node, ast.Name):           # add_api_route(path, handler)
                node = finder.functions.get(node.id, node)
            own = finder.prefixes.get(owner, "")
            guard = verifiers.guards(deps) or \
                verifiers.guards(finder.router_deps.get(owner))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                guard = guard or verifiers.guards_function(node)
            elif isinstance(node, (ast.Name, ast.Attribute)):
                guard = guard or verifiers.is_verifier(_name_of(node))
            source = (ast.get_source_segment(texts[key], node) or "") \
                if node is not None else ""
            for outer, mount_guard in mounts((key, owner)):
                full = outer.rstrip("/") + own.rstrip("/") + path \
                    if (outer or own) else path
                routes.append((method, full, finder.module, line, source,
                               guard or mount_guard))
    if verifiers.assumed:
        notes.append(
            "taken on its name as a user-context check, not read: %s. If it reads "
            "Authorization or a cookie it verifies nothing here - the gateway strips "
            "both, and the runtime calls /agent/* with X-Manaurum-User-Context only"
            % ", ".join(sorted(verifiers.assumed)))
    return routes, traced


# ── Rules ───────────────────────────────────────────────────────────────────


def normalise_path(path: str) -> str:
    """A served path with its parameters reduced to one opaque segment."""
    return PATH_PARAM.sub("_", path)


def gateway_match(rule: str, path: str) -> bool:
    """The gateway's own rule (`api_route_matcher.py`), and nothing kinder.

    A trailing `/*` matches anything BELOW the prefix and not the prefix
    itself. Every other rule is an exact, literal string: `{id}` in a rule is
    not a parameter and a `*` anywhere else is not a wildcard. An earlier
    version of this check treated both as patterns, so a manifest the gateway
    404s linted clean.
    """
    if rule.endswith("/*"):
        prefix = rule[:-1]                     # keep the trailing slash
        return path.startswith(prefix) and len(path) > len(prefix)
    return path == rule


def covered_by(path: str, rules: list) -> bool:
    """Does any `runtime.api_routes` entry cover this served path?

    The `/api/x/*` case is the one worth spelling out: a glob covers what is
    UNDER the prefix and not the prefix itself, so declaring `/api/items/*`
    and serving `/api/items` is a 404 on the list screen while every detail
    screen works. A trailing slash is part of the path to the gateway too:
    `/api/items` does not cover a handler served at `/api/items/`.
    """
    return any(gateway_match(rule, normalise_path(path)) for rule in rules)


def check_routes(manifest: dict, routes: list, problems: list, notes: list,
                 traced: bool = True) -> None:
    """Rule 1 - the code and `runtime.api_routes` describe the same surface.

    The single most expensive v2 failure, and the one this whole file exists
    for: `/api/*` is default-deny at the gateway, so an undeclared path is a
    404 the container never sees and the logs never mention.
    """
    declared = [str(entry.get("path", "")) for entry in
                manifest.get("runtime", {}).get("api_routes", [])
                if isinstance(entry, dict)]

    for rule in declared:
        body = rule[:-2] if rule.endswith("/*") else rule
        if "*" in body or PATH_PARAM.search(body):
            problems.append(
                "manifest.json: runtime.api_routes declares %s - the gateway "
                "matches it literally ({param} is not a parameter, and * is a "
                "wildcard only as a trailing /*), so no real request matches it; "
                "declare the collection and `%s/*`"
                % (rule, PATH_PARAM.split(body.rstrip("*"))[0].rstrip("/")))

    served = []
    for method, path, module, line, _source, _guarded in routes:
        if not path.startswith("/api/") and path != "/api":
            continue
        served.append(normalise_path(path))
        if not covered_by(path, declared):
            problems.append(
                "%s:%d: %s %s is served but no runtime.api_routes rule covers it - "
                "the gateway answers 404 route_not_declared and this handler never "
                "runs" % (module, line, method, path))

    for rule in declared:
        if any(gateway_match(rule, path) for path in served):
            continue
        if not traced:
            # Something mounts routes this linter could not follow; they may
            # well serve it.
            notes.append("manifest.json: runtime.api_routes declares %s and no route "
                         "this linter could trace serves it - check it by hand" % rule)
            continue
        problems.append(
            "manifest.json: runtime.api_routes declares %s and nothing serves it - "
            "either the path moved and the manifest did not, or the app is asking "
            "the gateway to forward traffic it will 404 itself" % rule)


def check_agent_handlers(routes: list, problems: list) -> None:
    """Rule 2 - every `/agent/*` handler verifies the caller.

    `/agent/<name>` bypasses the gateway. The public host refuses it
    (MAN-1432), but every app's container shares one network, so another
    app's container can POST here directly. The dependency is the only thing
    stopping it, and "only the runtime calls this" is how it gets left out.
    """
    for method, path, module, line, _source, guarded in routes:
        if not path.startswith("/agent/") and path != "/agent":
            continue
        if guarded:
            continue
        problems.append(
            "%s:%d: %s %s has no user-context verification - no gateway sits in "
            "front of it and any app's container can call it; add the same "
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

    The platform reaches the container on `manifest.runtime.port` (default 80)
    and never parses `EXPOSE`. A mismatch builds and pushes, then fails the
    readiness probe and rolls back.
    """
    declared = manifest.get("runtime", {}).get("port", 80)
    if not isinstance(declared, int) or isinstance(declared, bool):
        problems.append("manifest.json: runtime.port is %r - an integer, or the "
                        "deploy rejects the manifest with a 422" % (declared,))
        return
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
            "the platform reaches the container on the manifest's port, so the "
            "deploy builds, then fails its readiness probe"
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


def check_manifest_shape(manifest: dict, problems: list, notes: list,
                         schema=None, contract=None) -> None:
    """Rules the deploy enforces, answered offline, before the upload.

    The root object, `runtime`, `data` and `offline` are strict -
    `additionalProperties: false` - so a typo in any of them is a 422. Until
    MAN-1899 `runtime` was not, and `"prot": 8000` deployed green and did
    nothing. The slug, the reserved names and the write-verb rule are the
    deploy's own (MAN-2500, MAN-2358), read from the contract files.
    """
    properties = (schema or {}).get("properties", {})
    runtime_keys = set(properties.get("runtime", {}).get("properties", {})) or RUNTIME_KEYS
    for key in sorted(set(manifest) - set(properties)) if properties else []:
        problems.append(
            "manifest.json: %s is not a root key of the v2 manifest, and the deploy "
            "rejects it with 422 manifest_validation_failed (description and "
            "category go under metadata, icon under frontend)" % key)
    for section in ("data", "offline"):
        block, allowed = manifest.get(section), properties.get(section, {}).get("properties")
        if isinstance(block, dict) and allowed:
            for key in sorted(set(block) - set(allowed)):
                problems.append("manifest.json: %s.%s is not a key the schema allows - "
                                "422 at deploy (allowed: %s)"
                                % (section, key, ", ".join(sorted(allowed))))

    runtime = manifest.get("runtime", {})
    if isinstance(runtime, dict):
        if runtime.get("mode", "hosted") in ("hosted", "dev") and "entrypoint" in runtime:
            problems.append("manifest.json: runtime.entrypoint on a %s app - the URL "
                            "is the platform's, and the deploy rejects the manifest "
                            "with a 422" % runtime.get("mode", "hosted"))
        if runtime.get("mode") == "byo" and manifest.get("permissions"):
            problems.append("manifest.json: permissions on a byo app - refused at "
                            "deploy (MAN-1922); the shell delegates nothing to a frame "
                            "whose address the manifest chose")
        modes = (properties.get("runtime", {}).get("properties", {})
                 .get("api_routes", {}).get("items", {}).get("properties", {})
                 .get("auth", {}).get("enum"))
        routes = runtime.get("api_routes")
        for index, rule in enumerate(routes if isinstance(routes, list) else []):
            if modes and isinstance(rule, dict) and rule.get("auth") not in modes:
                problems.append("manifest.json: runtime.api_routes[%d].auth is %r - the "
                                "deploy accepts only %s (422)"
                                % (index, rule.get("auth"), ", ".join(modes)))
        for key in sorted(set(runtime) - runtime_keys):
            problems.append(
                "manifest.json: runtime.%s is not a key the platform reads, and "
                "the deploy rejects the manifest with a 422 over it - check the "
                "spelling against %s"
                % (key, ", ".join(sorted(runtime_keys))))

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

    if contract:
        check_slug_and_tools(manifest, contract, problems, notes)


def check_slug_and_tools(manifest: dict, contract: dict, problems: list,
                         notes: list) -> None:
    """The deploy's slug rule, and what the Assistant does with tool names."""
    slug = manifest.get("app_id")
    if isinstance(slug, str):
        if slug.strip().casefold() in contract.get("reserved_slugs", []):
            problems.append("manifest.json: app_id %r is reserved for the platform "
                            "- 422 manifest_validation_failed" % slug)
        elif UUID_SHAPED.match(slug) or not re.match(contract.get("slug_pattern", ".*"), slug):
            problems.append("manifest.json: app_id %r is not a slug the deploy accepts "
                            "(3-40 chars of a-z, 0-9 and -, starting with a letter, not "
                            "a UUID) - 422 app_id_invalid" % slug)

    tool = contract.get("agent_tool", {})
    verbs = tuple(contract.get("write_verb_prefixes", []))
    for entry in manifest.get("agent_capabilities", []) or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        name = entry["name"]
        if isinstance(slug, str) and tool:
            full = len(tool.get("prefix", "")) + len(slug) + \
                len(tool.get("separator", "")) + len(name)
            if full > tool.get("max_length", 64):
                problems.append(
                    "manifest.json: agent_capabilities %s - the Assistant names this "
                    "tool %s%s%s%s (%d chars, max %d) and silently drops it; keep "
                    "slug + name within %d" % (
                        name, tool.get("prefix", ""), slug, tool.get("separator", ""),
                        name, full, tool.get("max_length", 64),
                        tool.get("max_length", 64) - len(tool.get("prefix", ""))
                        - len(tool.get("separator", ""))))
        if verbs and name.startswith(verbs) and entry.get("is_write") is False:
            problems.append(
                "manifest.json: agent_capabilities %s declares is_write: false with a "
                "write verb in its name - the deploy refuses it (MAN-2358); set "
                "is_write: true or rename it" % name)
        if "is_write" not in entry and name.startswith(READ_VERB_PREFIXES):
            notes.append(
                "manifest.json: agent_capabilities %s has no is_write - an omitted "
                "flag counts as a write, so every call asks the user for approval. "
                "Declare \"is_write\": false on a reader." % name)


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


def check_capabilities(root: Path, manifest: dict, problems: list,
                       contract=None) -> None:
    """Rule 6 - called and declared are the same set, and every name exists.

    An undeclared call is 403 `capability_not_granted` at the first real use.
    A required capability that is never called is an over-broad grant the
    tenant admin is asked to approve for nothing. `optional_capabilities` are
    granted at install too, so a call to one is declared. A name that is not
    registered on Core is `404 capability_not_found` however it is declared -
    the deploy does not check that, so this does, against the contract.
    """
    required, optional = set(), set()
    for key, into in (("requires_capabilities", required),
                      ("optional_capabilities", optional)):
        for entry in manifest.get(key, []) or []:
            if isinstance(entry, dict) and entry.get("name"):
                into.add(entry["name"])
            elif isinstance(entry, str):
                into.add(entry)
    declared = required | optional

    called = {}
    for path in source_files(root, CODE_SUFFIXES):
        parts = path.relative_to(root).parts
        if path.name.startswith("test_") or path.name.endswith("_test.py") or \
                any(part in ("tests", "test", "__tests__") for part in parts):
            continue
        text = read(path)
        for name in CAPABILITY.findall(text) + CAPABILITY_URL.findall(text):
            if not name.startswith(STDLIB_OS):
                called.setdefault(name, rel(path, root))

    known = set((contract or {}).get("capabilities", []))
    for name in sorted(declared | set(called)):
        if known and name not in known:
            where = called.get(name, "manifest.json")
            problems.append(
                "%s: %s is not a capability the platform registers - the gateway "
                "answers 404 capability_not_found (see "
                "references/capabilities-reference.md)" % (where, name))

    for name, where in sorted(called.items()):
        if name not in declared:
            problems.append(
                "%s: calls %s but manifest.requires_capabilities does not declare it "
                "- the gateway answers 403 capability_not_granted at the first call"
                % (where, name))
    for name in sorted(required - set(called)):
        problems.append(
            "manifest.json: requires_capabilities asks for %s and nothing in this "
            "app calls it - an over-broad grant request, and the install screen is "
            "where a tenant admin reads it" % name)


# A file the deploy refuses and a validator that predates the rule accepts:
# ADD COLUMN is additive, CREATE INDEX CONCURRENTLY is additive, and only a
# validator that knows about transactionality rejects the two together.
MIXED_PROBE = ("ALTER TABLE probe ADD COLUMN c text;\n"
               "CREATE INDEX CONCURRENTLY probe_c_idx ON probe (c);")


def real_validator():
    """The deploy's own AST validator, when the author has a usable CLI.

    MAN-2624. This script cannot decide the migration rules itself. Two of
    them depend on what came earlier in the same file, and one - a file
    using CONCURRENTLY may contain nothing else - cannot be decided from
    the text at all. Core says so in as many words: "regex-based detection
    is explicitly rejected: the AST is the contract". A text test gets
    `'a -- b'` inside a string literal wrong (it eats the rest of the
    line), `DETACH PARTITION "m_2024--old" CONCURRENTLY` wrong, and the
    word inside a string or a nested block comment wrong - in both
    directions. So this script does not guess: it either asks the real
    validator or says the rule went unchecked.

    Returns `(validate, error_class, knows_the_transactionality_rule)`, or
    None when there is no usable copy. The capability is PROBED, not read
    off a version: the rule landed in the CLI without a version bump, and
    the wheel authors can actually install predates it. A copy that cannot
    answer the probe at all is not trusted for anything.

    The stdlib-only promise is intact - nothing here is required, and the
    import failing is an ordinary outcome, not an error.
    """
    try:
        from manaurum_cli.migrations import (  # noqa: PLC0415
            MigrationValidationError,
            validate_migration,
        )
    except Exception:  # noqa: BLE001 - not installed is the common case
        return None
    try:
        validate_migration(MIXED_PROBE, breaking_allowed=False)
    except MigrationValidationError as exc:
        # Require the verdict to be THIS rule. Treating any refusal as "knows
        # it" would let a copy that refuses the probe for an unrelated reason
        # suppress the note while the rule is in fact unchecked - which is the
        # silent-coverage failure this whole probe exists to remove.
        knows_mixing = any(
            err.get("classification") == "mixed_transaction"
            for err in getattr(exc, "errors", [])
        )
    except Exception:  # noqa: BLE001 - wrong signature, broken install
        return None
    else:
        knows_mixing = False
    return validate_migration, MigrationValidationError, knows_mixing


UNCHECKED_RULES = (
    "migrations/: the built-in pattern list ran, not the deploy's AST "
    "validator. It catches the forbidden and destructive statements by "
    "pattern; what needs a parse tree went UNCHECKED here - a plain CREATE "
    "INDEX or SET NOT NULL against something an earlier file created, a "
    "statement the validator does not recognise (forbidden by default), and "
    "a file mixing CONCURRENTLY with other statements. Run `manaurum app "
    "validate-migration migrations/` for those")

UNCHECKED_MIXING = (
    "migrations/: this copy of the deploy's validator predates the rule "
    "that a file using CONCURRENTLY may contain nothing else, so that one "
    "went unchecked. Everything else was checked against the real "
    "validator. Update manaurum-cli to close the gap")


def check_migrations(root: Path, manifest: dict, problems: list,
                     notes: list) -> None:
    """Rule 7 - `*.sql` only, ordered, and nothing the deploy will refuse.

    Migrations run once per (app, tenant) in filename order, and the DDL is
    AST-validated at deploy, PER FILE. Two things follow that the packaging
    rules cannot tell you on their own: a destructive statement without
    `migration.breaking` is a 422, and a file that uses `CONCURRENTLY` may
    contain nothing else, because `CREATE INDEX CONCURRENTLY` cannot run
    inside a transaction block and the rest of the file needs one.

    Which engine decided that is never left implicit: whatever this run
    could not check, it says so in a note. `clean` has to mean one thing.
    """
    directory = root / "migrations"
    if not directory.is_dir():
        return
    breaking = bool(manifest.get("migration", {}).get("breaking"))
    validator = real_validator()
    if validator is None:
        notes.append(UNCHECKED_RULES)
    elif not validator[2]:
        notes.append(UNCHECKED_MIXING)

    numbers, total = {}, 0
    for path in sorted(directory.iterdir(), key=lambda p: p.name):
        if path.is_dir():
            # The deploy skips it (`bundle_migrations.py`): not an error, but
            # nothing in it will ever run.
            notes.append("migrations/%s/: a directory - the deploy ignores it, so "
                         "nothing in it ever runs; migrations are flat `*.sql` "
                         "files" % path.name)
            continue
        if path.suffix != ".sql":
            problems.append("migrations/%s: not a .sql file - any other file "
                            "directly under migrations/ fails the deploy, and the "
                            "check is case-sensitive (.SQL is not .sql)" % path.name)
            continue
        raw = path.read_bytes()
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            problems.append("migrations/%s: not valid UTF-8 - the deploy refuses "
                            "it" % path.name)
            continue
        if raw.startswith(b"\xef\xbb\xbf"):
            # The deploy decodes `utf-8`, not `utf-8-sig`: the BOM stays, and
            # the parser stops at `﻿CREATE`. Windows PowerShell 5.1's
            # Out-File writes one by default.
            problems.append("migrations/%s: starts with a UTF-8 BOM - the deploy's "
                            "parser reads it as part of the first word and refuses the "
                            "file; save it as UTF-8 without BOM" % path.name)
        # Measured as the deploy builds it (`concat_migration_sql`): a marker,
        # the file right-stripped, a newline, files joined by a newline.
        total += len(("%s-- file: %s\n%s\n" % ("\n" if total else "", path.name,
                                                 decoded.rstrip())).encode("utf-8"))
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
            validate_migration, MigrationValidationError, _ = validator
            try:
                validate_migration(read(path), breaking_allowed=breaking)
            except MigrationValidationError as exc:
                before = len(problems)
                for err in getattr(exc, "errors", []):
                    problems.append("migrations/%s: %s - %s" % (
                        path.name, err.get("classification", "rejected"),
                        err.get("reason", "")))
                if len(problems) == before:
                    # Refused without a per-statement breakdown. Never let a
                    # rejection turn into silence in the one function whose
                    # job is that `clean` means one thing.
                    problems.append("migrations/%s: the deploy's validator "
                                    "refused this - %s" % (path.name, exc))
            except Exception as exc:  # noqa: BLE001 - unparseable SQL
                problems.append("migrations/%s: the deploy's validator could "
                                "not parse this - %s" % (path.name, exc))
            continue

        body = sql_code(read(path))
        for statement in (part.strip() for part in body.split(";")):
            for pattern, label in FORBIDDEN:
                if statement and pattern.search(statement):
                    problems.append(
                        "migrations/%s: %s - forbidden in a migration whatever "
                        "migration.breaking says; the deploy refuses it"
                        % (path.name, label))
        if DOLLAR_BLOCK.search(body):
            problems.append("migrations/%s: a DO block - the DDL "
                            "validator cannot analyse an anonymous PL/pgSQL body "
                            "and refuses the deploy; expand it into plain "
                            "statements" % path.name)
        for pattern, label in DESTRUCTIVE:
            if pattern.search(body) and not breaking:
                problems.append(
                    "migrations/%s: %s without manifest.migration.breaking - the "
                    "validator rejects the deploy, and if it did not this would "
                    "drop tenant data" % (path.name, label))

    if total > MAX_MIGRATION_BYTES:
        problems.append("migrations/: %d bytes of migrations in all - the deploy "
                        "refuses more than %d (64 KiB) for all files together, and "
                        "splitting them does not help" % (total, MAX_MIGRATION_BYTES))

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
    schema, contract = load_contract(notes)
    for key in ("runtime", "frontend", "migration", "data"):
        if key in manifest and not isinstance(manifest[key], dict):
            problems.append("manifest.json: %s is not an object - 422 "
                            "manifest_validation_failed" % key)
            manifest = dict(manifest, **{key: {}})

    routes, traced = find_routes(root, problems, notes)
    check_routes(manifest, routes, problems, notes, traced)
    check_agent_handlers(routes, problems)
    check_entry_point(root, manifest, problems)
    check_port(root, manifest, problems, notes)
    check_env_files(root, problems)
    check_capabilities(root, manifest, problems, contract)
    check_migrations(root, manifest, problems, notes)
    check_manifest_shape(manifest, problems, notes, schema, contract)
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

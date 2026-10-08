#!/usr/bin/env python3
"""Refresh the copy of the platform contract this plugin checks itself against.

Every fact the 2026-10-02 audit found stale had the same history: Core
changed, and nothing here noticed, because nothing here held a copy of what
Core says. `templates/manifest_v2.schema.json`,
`templates/platform-contract.json` and `scripts/platform-strings.json` are
that copy. `check_app.py` reads them
instead of keeping its own lists, and `scripts/check_repo.py` holds the
documents to them. This script is how they are refreshed: from a Manaurum
monorepo checkout, at a ref you name, read-only (`git show`, no checkout).

    python scripts/sync_contract.py --monorepo ../Manaurum [--ref origin/main]

Run `git -C <monorepo> fetch origin main` first. Then run `check_repo.py`:
whatever it now reports is a document that disagrees with the platform.

Standard library only. It is never run in CI - CI has no monorepo - which is
why its output is committed and carries the SHA it came from.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_OUT = ROOT / "templates" / "manifest_v2.schema.json"
CONTRACT_OUT = ROOT / "templates" / "platform-contract.json"
STRINGS_OUT = ROOT / "scripts" / "platform-strings.json"

SCHEMA_SRC = "backend/app/services/_schemas/manifest_v2.schema.json"
CAPABILITIES_DIR = "backend/app/services/capabilities/"
RESERVED_SRC = "backend/app/services/v2_apps/reserved_slugs.py"
SLUG_SRC = "backend/app/services/v2_apps/traefik_yaml.py"
VALIDATOR_SRC = "backend/app/services/manifest_v2_validator.py"
TOOLS_SRC = "backend/app/agent/sdk_capability_tools.py"
SHELL_POLICY_SRC = "frontend/src/components/window/iframeHostPolicy.ts"
SHELL_HOST_SRC = "frontend/src/components/window/IframeAppHost.tsx"
SESSION_SRC = "backend/app/services/v2_apps/session_runtime.js"
# Where the error codes a v2 developer meets are written: the gateways, the
# deploy and credential routes, the capability handlers, the Assistant's
# dispatch. Every string literal in them, docstrings aside, is kept - a code
# is often built (`f"{prefix}_leading_slash"`) or returned from a helper,
# so "the strings after detail=" would miss real ones.
STRING_DIRS = ["backend/app/routes/", "backend/app/auth/", "backend/app/services/v2_apps/",
               "backend/app/services/capabilities/", "backend/app/services/builtin_rpc/",
               "backend/app/services/app_studio/", "backend/app/agent/"]
CODE_TOKEN = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


def git(monorepo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(monorepo), *args], check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout


def show(monorepo: Path, ref: str, path: str) -> str:
    return git(monorepo, "show", "%s:%s" % (ref, path))


def capability_names(monorepo: Path, ref: str) -> list:
    out = git(monorepo, "grep", "-h", "-o", r'name="os\.[a-z_.]*"', ref, "--",
              CAPABILITIES_DIR)
    names = sorted({line.split('"')[1] for line in out.splitlines() if '"' in line})
    if len(names) < 20:
        raise SystemExit("found only %d capability registrations - the layout "
                         "changed; fix capability_names()" % len(names))
    return names


def reserved_slugs(text: str) -> list:
    block = re.search(r"RESERVED_SLUGS[^=]*=\s*frozenset\(\{(.*?)\}\)", text, re.S)
    if not block:
        raise SystemExit("RESERVED_SLUGS not found in %s" % RESERVED_SRC)
    return sorted(set(re.findall(r'"([a-z0-9-]+)"', block.group(1))))


def slug_pattern(text: str) -> str:
    match = re.search(r"_VALID_SLUG_RE\s*=\s*re\.compile\(r\"([^\"]+)\"\)", text)
    if not match:
        raise SystemExit("_VALID_SLUG_RE not found in %s" % SLUG_SRC)
    return match.group(1)


def write_verbs(text: str) -> list:
    block = re.search(r"_WRITE_VERB_PREFIXES\s*=\s*\((.*?)\)", text, re.S)
    if not block:
        raise SystemExit("_WRITE_VERB_PREFIXES not found in %s" % VALIDATOR_SRC)
    return sorted(set(re.findall(r'"([a-z_]+)"', block.group(1))))


def tool_name_prefix(text: str) -> str:
    # The Assistant names a hosted app's tool `sdk__<slug>__<name>`.
    match = re.search(r'f"(sdk__)\{', text)
    if not match:
        raise SystemExit("the sdk__ tool-name format was not found in %s" % TOOLS_SRC)
    return match.group(1)


class Unknown(Exception):
    """An expression this reader does not evaluate."""


def literal(node, consts: dict):
    """A schema literal, with module constants and `**` merges followed.

    Values it cannot work out (an imported limit, arithmetic) become None:
    what the documents are held to is each schema's field names, its
    `required` and its top-level `oneOf`/`not`, and `capability_inputs()`
    refuses a schema where any of those came back None.
    """
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in consts:
            return consts[node.id]
        raise Unknown(node.id)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        out = []
        for element in node.elts:
            if isinstance(element, ast.Starred):
                out.extend(literal(element.value, consts))
            else:
                out.append(literal(element, consts))
        return out
    if isinstance(node, ast.Dict):
        out = {}
        for key, value in zip(node.keys, node.values):
            if key is None:
                out.update(literal(value, consts))
                continue
            try:
                out[literal(key, consts)] = literal(value, consts)
            except Unknown:
                out[literal(key, consts)] = None
        return out
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and \
            node.func.id in ("list", "sorted", "tuple", "set", "frozenset") and len(node.args) == 1:
        return sorted(literal(node.args[0], consts)) if node.func.id == "sorted" \
            else list(literal(node.args[0], consts))
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.BitOr)):
        left, right = literal(node.left, consts), literal(node.right, consts)
        return {**left, **right} if isinstance(left, dict) else left + right
    raise Unknown(type(node).__name__)


def capability_inputs(monorepo: Path, ref: str, names: list) -> dict:
    """{capability: {"properties": [...], "required": [...]}} from each handler's
    registration (`name="os.x.y", input_schema=...`)."""
    out = {}
    for path in git(monorepo, "ls-tree", "--name-only", ref, CAPABILITIES_DIR).split():
        if not path.endswith(".py"):
            continue
        tree = ast.parse(show(monorepo, ref, path))
        consts = {}
        for node in tree.body:
            target = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and \
                    isinstance(node.targets[0], ast.Name):
                target = node.targets[0].id
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                    and node.value is not None:
                target = node.target.id
            if target:
                try:
                    consts[target] = literal(node.value, consts)
                except Unknown:
                    pass
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            keywords = {k.arg: k.value for k in node.keywords if k.arg}
            name = keywords.get("name")
            if not (isinstance(name, ast.Constant) and str(name.value).startswith("os.")
                    and "input_schema" in keywords):
                continue
            try:
                schema = literal(keywords["input_schema"], consts)
            except Unknown:
                schema = None
            properties = schema.get("properties", {}) if isinstance(schema, dict) else None
            required = schema.get("required", []) if isinstance(schema, dict) else None
            if not isinstance(properties, dict) or not isinstance(required, list):
                raise SystemExit("cannot read the input schema of %s in %s - fix "
                                 "capability_inputs()" % (name.value, path))
            entry = {"properties": sorted(properties), "required": sorted(required)}
            # A field limited to a fixed list: `os.http.fetch`'s `method` has no
            # PATCH, and check_app.py reports an app that sends one.
            enums = {field: sorted(spec["enum"]) for field, spec in properties.items()
                     if isinstance(spec, dict) and isinstance(spec.get("enum"), list)
                     and all(isinstance(value, str) for value in spec["enum"])}
            if enums:
                entry["enums"] = dict(sorted(enums.items()))
            # Required-ness outside `required`: `oneOf` alternatives (exactly one
            # set present) and `not` (never all together). Anything else at the
            # top would make "required" mean something this copy cannot say.
            unknown = {"anyOf", "allOf", "if", "then", "else", "dependentRequired",
                       "dependentSchemas"} & set(schema)
            if unknown:
                raise SystemExit("%s in %s uses %s at the top of its input schema - "
                                 "extend capability_inputs()" % (name.value, path,
                                                                 ", ".join(sorted(unknown))))
            if "oneOf" in schema:
                entry["one_of_required"] = [sorted((alt or {}).get("required") or [])
                                            for alt in schema["oneOf"]]
            if "not" in schema:
                entry["not_all_of"] = sorted(((schema["not"] or {}).get("required")) or [])
            out[name.value] = entry
    missing = sorted(set(names) - set(out))
    if missing:
        raise SystemExit("no input schema found for %s" % ", ".join(missing))
    return dict(sorted(out.items()))


def shell_messages(policy: str, host: str, session: str) -> dict:
    """The window protocol: what a v2 app may post, what the shell posts back."""
    allowed = re.search(r"V2_ALLOWED_MESSAGES[^=]*=\s*new Set\(\[(.*?)\]\)", policy, re.S)
    rejected = re.search(r"V2_REJECTED_MESSAGE_PREFIXES[^=]*=\s*\[(.*?)\];", policy, re.S)
    if not allowed or not rejected:
        raise SystemExit("V2_ALLOWED_MESSAGES / V2_REJECTED_MESSAGE_PREFIXES not found in %s"
                         % SHELL_POLICY_SRC)
    to_app = set(re.findall(r"type: '(manaurum:[a-z-]+)'", host))
    to_app |= set(re.findall(r"postToIframe\('(manaurum:[a-z-]+)'", host))
    if "manaurum:init" not in to_app:
        raise SystemExit("manaurum:init not found in %s - the layout changed; fix "
                         "shell_messages()" % SHELL_HOST_SRC)
    return {
        "app_to_shell": sorted(set(re.findall(r"'(manaurum:[a-z-]+)'", allowed.group(1)))),
        "shell_to_app": sorted(to_app),
        "rejected_prefixes": sorted(set(re.findall(r"'(manaurum:[a-z-]+)'",
                                                   rejected.group(1)))),
        "session": sorted(set(re.findall(r"['\"](manaurum:session-[a-z-]+)['\"]", session))),
    }


def platform_strings(monorepo: Path, ref: str) -> dict:
    """Every snake_case word in a string literal under STRING_DIRS.

    `check_repo.py` refuses a documented error code that is not in here: a
    code Core no longer writes anywhere is a code no developer will see.
    `suffixes` are the literal tails of the f-strings an error is made of -
    a `detail=`, an `"error"`/`"code"` value, an `HTTPException` argument
    (`f"{prefix}_backslash"`) - so a code built from a prefix still counts
    as written. Tails of other f-strings (SQL, index names) would let
    almost any `<word>_<tail>` pass, so they are not collected.
    """
    strings, suffixes = set(), set()

    def tails(joined) -> None:
        for before, part in zip(joined.values, joined.values[1:]):
            if isinstance(before, ast.FormattedValue) and \
                    isinstance(part, ast.Constant) and isinstance(part.value, str):
                tail = re.match(r"_[a-z0-9_]+", part.value)
                if tail:
                    suffixes.add(tail.group(0))

    files = [f for d in STRING_DIRS
             for f in git(monorepo, "ls-tree", "-r", "--name-only", ref, d).split()
             if f.endswith(".py")]
    for path in files:
        try:
            tree = ast.parse(show(monorepo, ref, path))
        except SyntaxError:
            continue
        docstrings = {id(node.value) for node in ast.walk(tree)
                      if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in docstrings:
                strings.update(CODE_TOKEN.findall(node.value))
            elif isinstance(node, ast.keyword) and node.arg in ("detail", "error", "code") \
                    and isinstance(node.value, ast.JoinedStr):
                tails(node.value)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value in ("error", "code", "detail") \
                            and isinstance(value, ast.JoinedStr):
                        tails(value)
            elif isinstance(node, ast.Call) and getattr(node.func, "id", "") == "HTTPException":
                for arg in node.args:
                    if isinstance(arg, ast.JoinedStr):
                        tails(arg)
    if len(strings) < 1000:
        raise SystemExit("found only %d strings under %s - the layout changed"
                         % (len(strings), ", ".join(STRING_DIRS)))
    return {"suffixes": sorted(suffixes), "strings": sorted(strings)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--monorepo", required=True, type=Path)
    parser.add_argument("--ref", default="origin/main")
    args = parser.parse_args()

    sha = git(args.monorepo, "rev-parse", args.ref).strip()
    date = git(args.monorepo, "show", "-s", "--format=%cs", args.ref).strip()
    schema_text = show(args.monorepo, args.ref, SCHEMA_SRC)
    json.loads(schema_text)                       # refuse to vendor a broken file

    contract = {
        "_comment": "Generated by scripts/sync_contract.py from the Manaurum monorepo. "
                    "Do not edit by hand; re-run the script.",
        "source": {"ref": args.ref, "sha": sha, "date": date},
        "capabilities": capability_names(args.monorepo, args.ref),
        "reserved_slugs": reserved_slugs(show(args.monorepo, args.ref, RESERVED_SRC)),
        "slug_pattern": slug_pattern(show(args.monorepo, args.ref, SLUG_SRC)),
        "write_verb_prefixes": write_verbs(show(args.monorepo, args.ref, VALIDATOR_SRC)),
        "agent_tool": {
            "prefix": tool_name_prefix(show(args.monorepo, args.ref, TOOLS_SRC)),
            "separator": "__",
            "max_length": 64,
        },
        "capability_inputs": capability_inputs(args.monorepo, args.ref,
                                               capability_names(args.monorepo, args.ref)),
        "messages": shell_messages(show(args.monorepo, args.ref, SHELL_POLICY_SRC),
                                   show(args.monorepo, args.ref, SHELL_HOST_SRC),
                                   show(args.monorepo, args.ref, SESSION_SRC)),
    }
    strings = {
        "_comment": "Generated by scripts/sync_contract.py: every snake_case word in a "
                    "string literal of the Core code a v2 developer's errors come from. "
                    "check_repo.py refuses a documented error code that is not here.",
        "source": {"ref": args.ref, "sha": sha, "date": date},
        **platform_strings(args.monorepo, args.ref),
    }

    SCHEMA_OUT.write_text(schema_text, encoding="utf-8", newline="\n")
    CONTRACT_OUT.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8",
                            newline="\n")
    STRINGS_OUT.write_text(json.dumps(strings, indent=0) + "\n", encoding="utf-8",
                           newline="\n")
    print("wrote %s, %s and %s from %s @ %s (%s): %d capabilities, %d strings"
          % (SCHEMA_OUT.relative_to(ROOT).as_posix(),
             CONTRACT_OUT.relative_to(ROOT).as_posix(),
             STRINGS_OUT.relative_to(ROOT).as_posix(), args.ref, sha[:9], date,
             len(contract["capabilities"]), len(strings["strings"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())

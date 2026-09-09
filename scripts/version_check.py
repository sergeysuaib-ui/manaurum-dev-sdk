#!/usr/bin/env python3
"""SessionStart hook: tell the session when this plugin copy is out of date.

A plugin install caches one directory per version. A session that has already
loaded a skill keeps reading the directory it started with, so an update that
lands mid-session reaches nobody: on 2026-09-08 a session loaded SDK 2.7.2,
2.8.0 appeared in the cache 51 minutes later, and that session went on reading
2.7.2 paths for another day - building an app the newer rules existed to
prevent.

Nothing here blocks or slows a session. When this copy is current it prints
nothing at all. When it is not, it prints one paragraph into the session's
context and leaves a STALE.md behind for the next reader, because SKILL.md
teaches agents to find the plugin root by walking the filesystem, and two
directories that differ only by a hidden marker are indistinguishable.

Every failure path here is a silent success: a hook that breaks a session is
worse than a session that misses a version bump.
"""

import json
import os
import re
import sys
from pathlib import Path

VERSION_DIR = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

STALE_NOTE = """# This copy of manaurum-dev-sdk is out of date

Version {mine} lives here; {newest} is installed alongside it at

    {newest_path}

Read that one. Anything you built from this directory was built against
superseded instructions - re-check it, in particular the UI contract in
`skills/manaurum-app/SKILL.md` (the seven rules and Step 3.5).

Written automatically by scripts/version_check.py.
"""


def version_key(name):
    match = VERSION_DIR.match(name)
    return tuple(int(part) for part in match.groups()) if match else None


def declared_version(root):
    """The version this copy says it is, per its own manifest."""
    try:
        data = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        return str(data.get("version") or "")
    except Exception:
        return ""


def write_if_changed(path, text):
    try:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return
        path.write_text(text, encoding="utf-8")
    except Exception:
        pass          # a read-only cache is not our problem to solve


def main():
    root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[1])
    mine_key = version_key(root.name)
    if mine_key is None:
        return        # a checkout or a local install, not a versioned cache dir

    parent = root.parent
    try:
        siblings = {d.name: d for d in parent.iterdir() if d.is_dir() and version_key(d.name)}
    except Exception:
        return

    newest_name = max(siblings, key=lambda name: version_key(name))
    newest_path = siblings[newest_name]
    orphaned = (root / ".orphaned_at").exists()
    stale = version_key(newest_name) > mine_key or orphaned

    if not stale:
        # We are the current copy: leave a pointer for anyone resolving the
        # plugin root by hand, and mark the copies that are not.
        write_if_changed(parent / "current", newest_name + "\n")
        for name, path in siblings.items():
            if name == newest_name:
                continue
            write_if_changed(path / "STALE.md", STALE_NOTE.format(
                mine=name, newest=newest_name, newest_path=newest_path))
        return

    write_if_changed(root / "STALE.md", STALE_NOTE.format(
        mine=root.name, newest=newest_name, newest_path=newest_path))

    detail = ("its directory is marked orphaned" if orphaned
              else "a newer version is installed alongside it")
    message = (
        "manaurum-dev-sdk: the skill files in this session come from version {mine}, and {detail}"
        " ({newest}, at {path}).\n\n"
        "The instructions already in your context are the old ones. Before you build or deploy"
        " anything for ManAurum, re-invoke the `manaurum-app` skill and read it from the newer"
        " directory - and if you have already built something in this session, re-check it"
        " against the newer SKILL.md (the UI contract and Step 3.5 changed in 2.9.0)."
    ).format(mine=declared_version(root) or root.name, detail=detail,
             newest=newest_name, path=newest_path)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": message,
        }
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass          # never let this hook be the reason a session starts badly
    sys.exit(0)

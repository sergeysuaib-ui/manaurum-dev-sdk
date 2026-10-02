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

Sibling directories are not enough on their own. On 2026-10-02 a machine was
still running 2.7.2, six weeks and a major version behind, with nothing newer
in its cache to compare against and a marketplace clone that had stopped
updating at 2.7.3 - so this hook, which only looked at siblings, never said a
word. It now also reads the marketplace clone's version, and at most once a
day asks GitHub for the released one (2 s timeout, nothing sent but the GET;
set MANAURUM_SDK_NO_UPDATE_CHECK=1 to switch that off).
"""

import json
import os
import re
import sys
import threading
import time
import urllib.request
from pathlib import Path

RELEASED_MANIFEST = ("https://raw.githubusercontent.com/sergeysuaib-ui/"
                     "manaurum-dev-sdk/main/.claude-plugin/plugin.json")
CHECK_EVERY_SECONDS = 24 * 3600
FETCH_DEADLINE_SECONDS = 2
UPDATE_HOW = ("Update it: in Claude Code run `/plugin`, update the `manaurum-sdk` "
              "marketplace and then the `manaurum-dev-sdk` plugin (or `claude plugin "
              "marketplace update manaurum-sdk` followed by `claude plugin update "
              "manaurum-dev-sdk@manaurum-sdk`), and start a new session. To stop falling behind, turn on auto-update for the marketplace: `/plugin` → Marketplaces → manaurum-sdk → Enable auto-update.")

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


def semver(text):
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", str(text or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def marketplace_version():
    """The version in the local marketplace clone, if there is one."""
    base = os.environ.get("MANAURUM_SDK_MARKETPLACE_DIR")
    path = Path(base) if base else Path.home() / ".claude" / "plugins" / "marketplaces" / "manaurum-sdk"
    return declared_version(path)


def released_version(cache_dir):
    """The version on GitHub's main, asked at most once a day.

    `MANAURUM_SDK_LATEST_VERSION` stands in for the network in tests; the
    opt-out wins over everything.
    """
    if os.environ.get("MANAURUM_SDK_NO_UPDATE_CHECK"):
        return ""
    if os.environ.get("MANAURUM_SDK_LATEST_VERSION"):
        return os.environ["MANAURUM_SDK_LATEST_VERSION"]
    stamp = cache_dir / ".released-version.json"
    known = ""
    try:
        cached = json.loads(stamp.read_text(encoding="utf-8"))
        known = str(cached.get("version") or "")
        if time.time() - float(cached.get("checked_at", 0)) < CHECK_EVERY_SECONDS:
            return known
    except Exception:
        pass
    # In a daemon thread with one deadline for all of it: `urlopen`'s timeout
    # covers the socket, not the DNS lookup before it, and this runs on every
    # session start. A failure is stamped too, with the last version we knew,
    # or an unreachable network would pay the wait on every start, not daily.
    result = {}

    def fetch():
        try:
            with urllib.request.urlopen(RELEASED_MANIFEST, timeout=2) as response:
                result["version"] = str(
                    json.loads(response.read().decode("utf-8")).get("version") or "")
        except Exception:
            pass

    worker = threading.Thread(target=fetch, daemon=True)
    worker.start()
    worker.join(FETCH_DEADLINE_SECONDS)
    version = result.get("version", known)
    write_if_changed(stamp, json.dumps({"checked_at": time.time(), "version": version}))
    return version


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
        # Nothing newer on disk. Is there something newer anywhere else?
        newest_seen = max(
            (v for v in (marketplace_version(), released_version(parent)) if semver(v)),
            key=semver, default="")
        if newest_seen and semver(newest_seen) > max(mine_key, version_key(newest_name)):
            message = (
                "manaurum-dev-sdk: this session runs version {mine} of the plugin, and "
                "{newest} has been released. The skill files already in your context "
                "may teach things the platform no longer does. {how}"
            ).format(mine=declared_version(root) or root.name, newest=newest_seen,
                     how=UPDATE_HOW)
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "SessionStart", "additionalContext": message}}))
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

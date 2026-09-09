#!/usr/bin/env python3
"""Start the tools this plugin ships and check they still work.

`check_ui.py` has the starter to run against, so CI exercises it directly.
The other two have nothing: `preview.py` is a server an agent is told to
start in a MANDATORY step, and `version_check.py` is a SessionStart hook
whose every failure path is a deliberate silent success - which means a hook
that raises on line 3 looks exactly like a hook with nothing to report.

Both are stdlib-only by design, so this file is too: no pytest, no requests,
nothing to install. Run it from the repository root.

    python scripts/smoke_tools.py

Exit code: 0 clean, 1 something is broken.

WHAT IS CHECKED, and why each one is here rather than left to a human:

* preview serves the app (`/index.html`, `/app.css`) and the framed page
  (`/__shell`) - the three URLs Step 3.5 tells you to open.
* the fixture matcher: an exact path, a `/prefix/*` glob (the detail screen
  at `/api/items/42` is unreachable without it), a method-qualified key, and
  the `{"status": 500}` envelope. Those four are what make the failed and
  empty states photographable, and a silent regression in any of them turns
  a screenshot of a broken state into a screenshot of an empty one.
* an unlisted `/api/*` still answers, because that is what lets you find a
  route your manifest never declared.
* version_check prints NOTHING when the copy is current, and exactly one
  line of JSON when a newer version sits beside it. Printing on the happy
  path would put a paragraph into every session's context forever.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STARTER_STATIC = ROOT / "templates" / "v2-starter" / "src" / "static"
PORT = int(os.environ.get("SMOKE_PORT", "8766"))
BASE = "http://127.0.0.1:%d" % PORT

FIXTURES = {
    "/api/me": {"user_id": "u-1"},
    "/api/items": [{"id": 1}],
    "/api/items/*": {"id": 1, "title": "detail"},
    "/api/broken": {"status": 500},
    "PUT /api/items/*": {"ok": True},
}


def fetch(path: str, method: str = "GET"):
    """(status, body bytes). A 4xx/5xx is an answer here, not an error."""
    request = urllib.request.Request(BASE + path, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def wait_for_server(process, seconds: float = 20.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(BASE + "/__shell", timeout=1):
                return True
        except Exception:
            time.sleep(0.2)
    return False


def smoke_preview(problems: list) -> None:
    workdir = Path(tempfile.mkdtemp(prefix="smoke-preview-"))
    fixtures = workdir / "fixtures.json"
    fixtures.write_text(json.dumps(FIXTURES), encoding="utf-8")

    process = subprocess.Popen(
        [sys.executable, str(ROOT / "templates" / "preview.py"),
         "--app", str(STARTER_STATIC), "--fixtures", str(fixtures),
         "--port", str(PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        if not wait_for_server(process):
            err = b""
            if process.poll() is not None and process.stderr:
                err = process.stderr.read()[:400]
            problems.append("templates/preview.py: did not come up on %s %s"
                            % (BASE, err.decode("utf-8", "replace")))
            return

        for path in ("/__shell", "/__shell?appearance=dark&width=900",
                     "/index.html", "/app.css", "/"):
            status, body = fetch(path)
            if status != 200:
                problems.append("templates/preview.py: GET %s -> %d, expected 200"
                                % (path, status))
            elif not body:
                problems.append("templates/preview.py: GET %s answered empty" % path)

        shell = fetch("/__shell?appearance=dark&accent=lavender")[1].decode("utf-8")
        for needle in ('data-appearance="dark"', "lavender", "manaurum:init"):
            if needle not in shell:
                problems.append("templates/preview.py: /__shell does not contain %r - "
                                "the framed page is what makes a theme bug visible"
                                % needle)

        expectations = [
            ("/api/me", "GET", 200, {"user_id": "u-1"}),
            ("/api/items", "GET", 200, [{"id": 1}]),
            # The detail screen. Without prefix matching this answers {} and
            # you photograph an empty card.
            ("/api/items/42", "GET", 200, {"id": 1, "title": "detail"}),
            # `{"status": 500}` is an envelope, not a body.
            ("/api/broken", "GET", 500, {}),
            # A write is answered by its own key, not by the GET fixture.
            ("/api/items/42", "PUT", 200, {"ok": True}),
            # Nothing declared: still answered, and logged, which is how you
            # find a route the manifest is missing.
            ("/api/never-declared", "GET", 200, {}),
        ]
        for path, method, want_status, want_body in expectations:
            status, body = fetch(path, method)
            if status != want_status:
                problems.append("templates/preview.py: %s %s -> %d, expected %d"
                                % (method, path, status, want_status))
                continue
            try:
                got = json.loads(body.decode("utf-8"))
            except ValueError:
                problems.append("templates/preview.py: %s %s did not answer JSON"
                                % (method, path))
                continue
            if got != want_body:
                problems.append("templates/preview.py: %s %s -> %r, expected %r"
                                % (method, path, got, want_body))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def run_hook(plugin_root: Path):
    """version_check.py as the harness runs it: CLAUDE_PLUGIN_ROOT, no args."""
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin_root))
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "version_check.py")],
        env=env, capture_output=True, text=True, timeout=30)


def plugin_cache(base: Path, version: str) -> Path:
    """A directory shaped the way a plugin install shapes one."""
    root = base / version
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "manaurum-dev-sdk", "version": version}), encoding="utf-8")
    return root


def smoke_version_check(problems: list) -> None:
    cache = Path(tempfile.mkdtemp(prefix="smoke-cache-")) / "manaurum-dev-sdk"
    current = plugin_cache(cache, "2.9.0")

    result = run_hook(current)
    if result.returncode != 0:
        problems.append("scripts/version_check.py: exit %d on a current copy - a "
                        "SessionStart hook must never fail a session (stderr: %s)"
                        % (result.returncode, result.stderr.strip()[:200]))
    if result.stdout.strip():
        problems.append("scripts/version_check.py: printed on a CURRENT copy (%r) - "
                        "the happy path is silence, or every session carries a "
                        "paragraph it does not need" % result.stdout.strip()[:120])

    plugin_cache(cache, "2.10.0")
    result = run_hook(current)
    if result.returncode != 0:
        problems.append("scripts/version_check.py: exit %d when superseded"
                        % result.returncode)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        problems.append("scripts/version_check.py: printed %d lines when superseded, "
                        "expected exactly one JSON object" % len(lines))
        return
    try:
        payload = json.loads(lines[0])
    except ValueError:
        problems.append("scripts/version_check.py: output is not JSON: %r" % lines[0][:160])
        return
    context = payload.get("hookSpecificOutput", {}).get("additionalContext", "")
    if "2.10.0" not in context:
        problems.append("scripts/version_check.py: the message does not name the newer "
                        "version - the whole point is telling the session where to read")
    if not (current / "STALE.md").exists():
        problems.append("scripts/version_check.py: no STALE.md left in the old copy - "
                        "two directories differing only by a hidden marker are "
                        "indistinguishable to an agent resolving the plugin root")


def smoke_json(problems: list) -> None:
    """Every JSON file this plugin ships has to parse.

    `hooks/hooks.json` is read by the harness, not by us: a trailing comma in
    it does not break a test, it breaks the version hook for every install.
    """
    for name in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
                 "hooks/hooks.json", "templates/preview-fixtures.json",
                 "templates/v2-starter/manifest.json", "templates/legacy-v1/manifest.json"):
        path = ROOT / name
        if not path.exists():
            problems.append("%s: missing" % name)
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            problems.append("%s: does not parse - %s" % (name, exc))


def main() -> int:
    problems = []
    smoke_json(problems)
    smoke_preview(problems)
    smoke_version_check(problems)
    for problem in problems:
        print("x %s" % problem)
    print("%d problem(s)" % len(problems) if problems else "clean")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

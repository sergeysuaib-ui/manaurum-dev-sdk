"""The manifest and the code have to describe the same app.

`manifest.json` is not documentation — it is the contract the gateway
enforces, and every mismatch below deploys green and fails later as something
that does not look like its cause:

* an `/api/*` path missing from `runtime.api_routes` is a 404 at the gateway,
  so your handler never runs and your own logs say nothing;
* a capability you call but did not declare is a 403 at the first real use,
  in production, from a user;
* `/agent/<name>` reached without a verified caller is an open endpoint on
  the public internet.

The first test is the one worth copying into your own app: it is the check
that made the SDK ship `check_app.py`, and an app that keeps it can never
drift its routes away from its manifest without a red test.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.main import app

_APP_DIR = Path(__file__).resolve().parents[1]
_MANIFEST = json.loads((_APP_DIR / "manifest.json").read_text(encoding="utf-8"))


def _declared() -> list[str]:
    return [entry["path"] for entry in _MANIFEST["runtime"]["api_routes"]]


def _covers(rule: str, path: str) -> bool:
    """`/api/x/*` covers what is UNDER /api/x, and not /api/x itself."""
    if rule.endswith("/*"):
        prefix = rule[:-1]
        return path.startswith(prefix) and len(path) > len(prefix)
    return rule == path


def test_every_api_route_is_declared():
    """The most expensive v2 mistake, as a test you own.

    Held deliberately independent of `check_app.py`: this one asks the
    running app for its routes, so it also covers a route registered
    somewhere a decorator scan would never look.
    """
    served = sorted({route.path for route in app.routes
                     if getattr(route, "path", "").startswith("/api/")})
    assert served, "no /api/* routes found — this test is not testing anything"
    for path in served:
        assert any(_covers(rule, path) for rule in _declared()), (
            "%s is served but no runtime.api_routes rule covers it — the gateway "
            "answers 404 route_not_declared and this handler never runs" % path)


def test_no_agent_route_is_declared_in_api_routes():
    """`/agent/*` is dispatched straight to the container, not proxied.

    Declaring it does nothing at all — which is the problem: it looks like
    you configured something.
    """
    for rule in _declared():
        assert not rule.startswith("/agent"), (
            "%s is in runtime.api_routes — /agent/* is not a gateway route, and "
            "listing it there configures nothing" % rule)


def test_every_agent_capability_has_a_handler():
    """A declared capability with no handler 404s at dispatch.

    The Assistant does not then say "that app is broken" — it answers from
    guesswork, so the user gets a confident statement about data nothing read.
    """
    served = {route.path for route in app.routes}
    for capability in _MANIFEST.get("agent_capabilities", []):
        expected = "/agent/%s" % capability["name"]
        assert expected in served, (
            "%s is declared in agent_capabilities and nothing serves %s"
            % (capability["name"], expected))


def test_read_only_capabilities_say_so():
    """`is_write` omitted is not `is_write: false`.

    Since MAN-1425/MAN-1872 the manifest value is persisted and read, but the
    column is nullable and NULL falls back to the dispatch-derived value —
    and every v2 hosted app dispatches `backend`, which means `True`. So a
    reader that says nothing is journalled as a mutation, gated by the
    confirmation flow, and excluded from cross-app insight.
    """
    for capability in _MANIFEST.get("agent_capabilities", []):
        assert "is_write" in capability, (
            "%s does not declare is_write — omitting it is not the same as false, "
            "and a silent reader is treated as a write" % capability["name"])


def test_the_app_linter_is_clean():
    """`templates/check_app.py`, run against this app.

    Skipped in a copied app that did not take the linter along; in the SDK
    repo it guards the starter itself, which is what every app is copied from.
    """
    linter = _APP_DIR.parent / "check_app.py"
    if not linter.exists():                                   # pragma: no cover
        pytest.skip("check_app.py not alongside this template — copy it from the "
                    "plugin's templates/")
    done = subprocess.run([sys.executable, str(linter), str(_APP_DIR)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr

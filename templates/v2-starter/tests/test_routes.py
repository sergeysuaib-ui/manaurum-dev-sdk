"""The wiring, not the pieces.

`test_auth.py` proves the verifier rejects a bad token; `test_agent.py`
calls the handlers directly. Neither one proves the handlers are actually
WIRED to that verifier — delete `Depends(auth_claims)` and both suites
stay green while the route goes open to every other app's container.

That is not hypothetical. The dispatch skips the gateway, and every app's
container shares one network, so the dependency in each handler is the
only thing standing between another app and your data.
A test suite that stays green when you remove it is teaching you that the
code is covered when it is not.

These drive real HTTP through the app, which is the only place that
wiring exists. No database: this app is `data: {"none": true}`, and
`httpx` is already a runtime dependency, so `TestClient` costs nothing.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.capability import note_key
from src.main import app

client = TestClient(app)

_AGENT_ROUTES = ("/agent/read_my_note", "/agent/save_my_note")


@pytest.mark.parametrize("path", _AGENT_ROUTES)
def test_agent_route_refuses_a_caller_with_no_user_context(path):
    """No gateway sits in front of the agent surface. `Depends(auth_claims)`
    is the only thing between another app's container and this handler."""
    response = client.post(path, json={"text": "x"})
    assert response.status_code == 401
    assert response.json()["detail"] == "missing_user_context"


def test_api_route_refuses_a_caller_with_no_user_context():
    response = client.get("/api/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "missing_user_context"


@pytest.mark.parametrize("path", _AGENT_ROUTES)
def test_agent_route_accepts_a_minted_user_context(path, user_context, fake_kv):
    response = client.post(
        path,
        json={"text": "x"},
        headers={"X-Manaurum-User-Context": user_context("u-1")},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_a_second_user_context_header_is_refused(user_context):
    """The gateway adds its own `X-Manaurum-User-Context` and does not strip
    one the client sent, so a request can reach the container carrying two -
    and `headers.get()` returns the client's. One header, or a 401."""
    response = client.get(
        "/api/me",
        headers=[
            ("x-manaurum-user-context", user_context("u-attacker")),
            ("X-Manaurum-User-Context", user_context("u-1")),
        ],
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "user_context_ambiguous"


def test_api_route_accepts_one_minted_user_context(user_context):
    response = client.get(
        "/api/me", headers={"X-Manaurum-User-Context": user_context("u-1")},
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == "u-1"


def test_api_me_returns_the_persons_language(user_context):
    """The token's language reaches the response; without one, `locale` and
    `dir` are null and `language` falls back to the browser, then English."""
    chose = client.get("/api/me", headers={
        "X-Manaurum-User-Context": user_context("u-1", locale="he", dir="rtl"),
        "Accept-Language": "ru-RU,ru;q=0.9",
    }).json()
    assert (chose["locale"], chose["dir"], chose["language"]) == ("he", "rtl", "he")

    no_choice = client.get("/api/me", headers={
        "X-Manaurum-User-Context": user_context("u-1"),
        "Accept-Language": "ru-RU,ru;q=0.9",
    }).json()
    assert (no_choice["locale"], no_choice["dir"], no_choice["language"]) == (None, None, "ru")

    nothing = client.get("/api/me", headers={"X-Manaurum-User-Context": user_context("u-1")})
    assert nothing.json()["language"] == "en"


def test_storage_keys_are_namespaced_per_user():
    """`os.kv` is scoped per (app, tenant), NOT per user — namespacing is
    this app's job, and the `fake_kv` fixture cannot prove it does it,
    because the fixture does the namespacing itself."""
    assert note_key("u-1") != note_key("u-2")
    assert "u-1" in note_key("u-1")

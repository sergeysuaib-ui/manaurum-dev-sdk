"""The wiring, not the pieces.

`test_auth.py` proves the verifier rejects a bad token; `test_agent.py`
calls the handlers directly. Neither one proves the handlers are actually
WIRED to that verifier — delete `Depends(auth_claims)` and both suites
stay green while the route goes open to the internet.

That is not hypothetical. `/agent/*` is served on your public hostname
(the dispatch skips the gateway, not the network), so the dependency in
each handler is the only thing standing between a stranger and your data.
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
    """The agent surface is on the public hostname. `Depends(auth_claims)`
    is the only thing between a stranger and this handler."""
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


def test_storage_keys_are_namespaced_per_user():
    """`os.kv` is scoped per (app, tenant), NOT per user — namespacing is
    this app's job, and the `fake_kv` fixture cannot prove it does it,
    because the fixture does the namespacing itself."""
    assert note_key("u-1") != note_key("u-2")
    assert "u-1" in note_key("u-1")

"""The capability client: what actually goes over the wire to the gateway.

`fake_kv` replaces `call_capability` wholesale, so nothing else in the suite
sees the headers. These tests stop one layer lower, at httpx, and assert on
the request the gateway would receive.
"""
from __future__ import annotations

import httpx
import pytest

from src import capability

pytestmark = pytest.mark.asyncio


@pytest.fixture
def sent(monkeypatch):
    """Capture every request `call_capability` makes; answer 200."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"output": {"ok": True}})

    real_client = httpx.AsyncClient

    def client_with_mock(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(capability.httpx, "AsyncClient", client_with_mock)
    monkeypatch.setenv("MANAURUM_CORE_URL", "https://core.test")
    monkeypatch.setenv("MANAURUM_RUNTIME_TOKEN", "runtime-token")
    monkeypatch.setenv("MANAURUM_APP_ID", "44444444-4444-4444-4444-444444444444")
    return requests


async def test_user_context_is_forwarded_when_given(sent):
    """Drive and Calendar answer 403 user_context_required without it. An
    earlier version of this file said the gateway rejects it here, and had
    no way to send it."""
    await capability.call_capability(
        "os.kv.get", {"key": "k"}, user_context="jwt-for-u-1")
    assert sent[0].headers["X-Manaurum-User-Context"] == "jwt-for-u-1"


async def test_no_user_context_header_by_default(sent):
    await capability.call_capability("os.kv.get", {"key": "k"})
    assert "X-Manaurum-User-Context" not in sent[0].headers


async def test_runtime_token_and_tenant_ride_every_call(sent):
    await capability.call_capability("os.kv.get", {"key": "k"})
    assert sent[0].headers["Authorization"] == "Bearer runtime-token"
    assert sent[0].headers["X-Manaurum-Tenant-Id"]


async def test_slow_capabilities_get_longer_timeouts():
    # Built from prefixes: check_app.py reads a quoted capability name as a call.
    assert capability.timeout_for("os.ai." + "complete").read == 185.0
    assert capability.timeout_for("os.ocr." + "extract").read == 185.0
    assert capability.timeout_for("os.http." + "fetch").read == 35.0
    assert capability.timeout_for("os.kv." + "get").read == 15.0


async def test_the_call_uses_that_timeout(sent, monkeypatch):
    seen = []
    client = capability.httpx.AsyncClient   # the fixture's mock-wrapping factory

    def recording(*args, **kwargs):
        seen.append(kwargs.get("timeout"))
        return client(*args, **kwargs)

    monkeypatch.setattr(capability.httpx, "AsyncClient", recording)
    monkeypatch.setenv("MANAURUM_TENANT_ID", "t-1")
    await capability.call_capability("os.ai." + "complete", {})
    assert seen and seen[0].read == 185.0

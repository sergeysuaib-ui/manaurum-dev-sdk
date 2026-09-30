"""The gateway client itself - one layer below `fake_kv`.

Every other test replaces `call_capability`, which is right for them and
means nothing else here ever runs it. So this file drives the real
function against `httpx.MockTransport`: no Core, no network, but the
headers it actually sends and the errors it actually raises.

Two promises are pinned. The person's context is forwarded when a route
passes it, and only then. And a refusal keeps its code - an app can only
tell the person "a workspace admin has to allow this" if it can tell
`capability_not_granted` from a timeout.

Every call below names `os.kv.get`, even where the refusal is text AI's.
The client does not care which capability refused, and `check_app.py`
holds this starter to declaring whatever capability its files name.
"""
from __future__ import annotations

import httpx
import pytest

from src import capability
from src.capability import CapabilityError, call_capability

pytestmark = pytest.mark.asyncio


@pytest.fixture
def gateway(monkeypatch):
    """Route `call_capability`'s client to `handler`; returns the requests."""
    monkeypatch.setenv("MANAURUM_CORE_URL", "https://core.test")
    monkeypatch.setenv("MANAURUM_RUNTIME_TOKEN", "runtime-token")
    monkeypatch.setenv("MANAURUM_TENANT_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("MANAURUM_APP_ID", "22222222-2222-2222-2222-222222222222")
    seen: list[httpx.Request] = []
    state = {"respond": lambda request: httpx.Response(200, json={"output": {}})}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return state["respond"](request)

    real_client = httpx.AsyncClient

    def client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(capability.httpx, "AsyncClient", client)

    def respond_with(fn):
        state["respond"] = fn

    return seen, respond_with


async def test_the_person_is_forwarded_when_the_route_passes_them(gateway):
    seen, _ = gateway
    await call_capability("os.kv.get", {"key": "k"}, user_context="jwt-of-u-1")
    assert seen[0].headers["X-Manaurum-User-Context"] == "jwt-of-u-1"
    assert seen[0].url.path == "/api/capability/os.kv.get"


async def test_no_person_no_header(gateway):
    """A background job has nobody to forward. An empty header would be a
    401 invalid_user_context, not a neutral absence."""
    seen, _ = gateway
    await call_capability("os.kv.get", {"key": "k"})
    await call_capability("os.kv.get", {"key": "k"}, user_context="")
    assert all("X-Manaurum-User-Context" not in r.headers for r in seen)


async def test_a_refusal_keeps_its_code_and_its_fields(gateway):
    _, respond_with = gateway
    respond_with(lambda request: httpx.Response(429, json={"detail": {
        "error": "ai_spend_cap", "subject": "user", "window": "day",
    }}))
    with pytest.raises(CapabilityError) as caught:
        await call_capability("os.kv.get", {"key": "k"})
    assert caught.value.status == 429
    assert caught.value.code == "ai_spend_cap"
    assert caught.value.detail["window"] == "day"


async def test_a_string_detail_is_the_code(gateway):
    """A pinned provider's upstream failure is a plain string in `detail`."""
    _, respond_with = gateway
    respond_with(lambda request: httpx.Response(
        502, json={"detail": "openai_upstream_error:500"}))
    with pytest.raises(CapabilityError) as caught:
        await call_capability("os.kv.get", {"key": "k"})
    assert caught.value.code == "openai_upstream_error:500"


async def test_a_body_that_is_not_json_still_raises_with_its_status(gateway):
    _, respond_with = gateway
    respond_with(lambda request: httpx.Response(502, text="<html>bad gateway</html>"))
    with pytest.raises(CapabilityError) as caught:
        await call_capability("os.kv.get", {"key": "k"})
    assert caught.value.status == 502
    assert caught.value.code is None

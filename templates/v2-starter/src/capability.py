"""Storage — the capability gateway client.

manifest.json declares ``data: {"none": true}``, so this app gets no
Postgres schema and no DATABASE_URL: ``os.kv`` is the whole persistence
layer. os.kv is scoped per (app, tenant) and is NOT user-aware, so we
namespace keys by the verified user_id ourselves.

Split out of main.py for the same reason as auth.py — the `/api/*`
routes and the `/agent/*` handlers both need it.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

#: Per-call timeout. Generous on connect, because the gateway is a hop
#: away inside the swarm and a cold service can take a moment.
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class CapabilityError(Exception):
    """The runtime env is missing, the gateway is unreachable, or it
    returned a non-2xx.

    One exception type on purpose, so callers have exactly one thing to
    map to a user-visible error (this starter maps it to a 503).
    """


def _gateway() -> tuple[str, dict[str, str]]:
    """Return ``(base_url, headers)`` for a capability call.

    All four values are injected by the deploy. Never hard-code or bake
    them into the image — the token is minted per deploy and rotates.

    Returns:
        ``(base_url, headers)`` ready to POST with.

    Raises:
        CapabilityError: If any of the four env vars is missing, which
            means the container is not running under the platform.
    """
    base = (os.environ.get("MANAURUM_CORE_URL") or "").rstrip("/")
    token = os.environ.get("MANAURUM_RUNTIME_TOKEN") or ""
    tenant_id = os.environ.get("MANAURUM_TENANT_ID") or ""
    # X-Manaurum-App-Id takes the app UUID for os.kv.* and
    # os.events.emit, and the SLUG for every other capability.
    # MANAURUM_APP_ID is already the UUID, which is what os.kv wants —
    # a slug here is rejected with 412 `app_id_must_be_uuid`.
    app_uuid = os.environ.get("MANAURUM_APP_ID") or ""
    if not (base and token and tenant_id and app_uuid):
        raise CapabilityError(
            "capability env not fully injected (MANAURUM_CORE_URL / "
            "MANAURUM_RUNTIME_TOKEN / MANAURUM_TENANT_ID / MANAURUM_APP_ID)"
        )
    return base, {
        "Authorization": f"Bearer {token}",
        "X-Manaurum-Tenant-Id": tenant_id,
        "X-Manaurum-App-Id": app_uuid,
        "Content-Type": "application/json",
    }


async def call_capability(name: str, payload: dict[str, Any]) -> Any:
    """POST one capability call and return its ``output``.

    Every capability goes through this one door:
    ``POST {MANAURUM_CORE_URL}/api/capability/{name}``. Do NOT forward
    the user_context header here — the gateway rejects it on this path.

    Args:
        name: Dotted capability name, e.g. ``os.kv.get``.
        payload: The call's input object. Most capability schemas set
            ``additionalProperties: false``, so one extra key is a 422.

    Returns:
        The reply's ``output`` field, or the whole body when it has none.

    Raises:
        CapabilityError: On transport failure or any non-200. 403
            ``capability_not_granted`` is the usual first one: the
            manifest asks for the capability but this install's grants do
            not include it yet, and redeploying does not fix that.
    """
    base, headers = _gateway()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{base}/api/capability/{name}", json=payload, headers=headers,
            )
    except httpx.HTTPError as exc:
        # Core unreachable / DNS / TLS / timeout. Surface it as the same
        # error type as a non-2xx so a gateway blip degrades to a clean
        # 503 instead of a 500 traceback.
        raise CapabilityError(f"{name} transport failure: {exc}") from exc
    if response.status_code != 200:
        # 403 capability_not_granted is the usual first failure: the
        # manifest asks for the capability but the tenant admin has not
        # granted it on this install yet.
        raise CapabilityError(f"{name} -> {response.status_code}: {response.text[:200]}")
    body = response.json()
    return body.get("output", body) if isinstance(body, dict) else body


def note_key(user_id: str) -> str:
    """One namespaced key per user.

    os.kv is scoped per (app, tenant) and is NOT user-aware, so the
    namespacing has to happen here. Return a constant and every user in
    the tenant shares one note — which is the failure `test_routes.py`
    is written to catch.

    Args:
        user_id: The VERIFIED user id, from `claims.user_id`. Never a
            value taken from a request body.

    Returns:
        The os.kv key for that user's note.
    """
    return f"notes:{user_id}"


async def read_note(user_id: str) -> str:
    """Read one user's note out of os.kv.

    Args:
        user_id: The verified user id.

    Returns:
        The stored text, or ``""`` when the user has never saved one —
        a first-time reader and an emptied note are the same thing here,
        deliberately, so the UI has one empty state instead of two.

    Raises:
        CapabilityError: The gateway refused or was unreachable.
    """
    output = await call_capability("os.kv.get", {"key": note_key(user_id)})
    value = output.get("value") if isinstance(output, dict) else None
    return value.get("text", "") if isinstance(value, dict) else ""


async def write_note(user_id: str, text: str) -> str:
    """Write one user's note into os.kv.

    Args:
        user_id: The verified user id.
        text: The note. Truncated to 10,000 characters — the same cap the
            manifest's ``input_schema`` declares, enforced again here
            because a published schema is a contract, not a guarantee
            about the process on the other end.

    Returns:
        The text as actually stored, so the caller echoes back the
        truncated value rather than the one it sent.

    Raises:
        CapabilityError: The gateway refused or was unreachable.
    """
    text = text[:10_000]
    await call_capability(
        "os.kv.set", {"key": note_key(user_id), "value": {"text": text}}
    )
    return text

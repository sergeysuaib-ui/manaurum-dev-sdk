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

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)

# The manifest's `app_id`. The setup step's `sed` renames it with everything
# else, and tests/test_manifest.py fails if the two ever disagree.
APP_SLUG = "my-app"

# `X-Manaurum-App-Id` is stored AS SENT - the gateway does not normalise it -
# and two families key by different forms. os.kv.* and os.events.emit key by
# the app UUID and answer 412 `app_id_must_be_uuid` to a slug. Everything else
# that stores something keys by the slug: os.secrets.* (which is where
# `manaurum app set-secret` writes) and os.files.*. Send the UUID there and the
# call succeeds against an empty namespace - a secret set from the CLI reads
# back as 404, and a file uploaded before the switch is not found after it.
# Prefixes, not names: `check_app.py` reads a quoted capability name as a
# call, and this module calls neither of the events ones.
_UUID_KEYED = ("os.kv.", "os.events.")


def app_id_header(name: str) -> str:
    """The `X-Manaurum-App-Id` value capability `name` is keyed by."""
    if name.startswith(_UUID_KEYED):
        return os.environ.get("MANAURUM_APP_ID") or ""
    return APP_SLUG


class CapabilityError(Exception):
    """The runtime env is missing, the gateway is unreachable, or it
    returned a non-2xx. One exception type so callers have one thing to
    map to a user-visible error."""


def _gateway(name: str) -> tuple[str, dict[str, str]]:
    """Return ``(base_url, headers)`` for a call to capability ``name``.

    The URL, token, tenant and UUID are injected by the deploy. Never
    hard-code or bake them into the image — the token is minted per deploy
    and rotates. Only the slug is yours, because it is your manifest's.
    """
    base = (os.environ.get("MANAURUM_CORE_URL") or "").rstrip("/")
    token = os.environ.get("MANAURUM_RUNTIME_TOKEN") or ""
    tenant_id = os.environ.get("MANAURUM_TENANT_ID") or ""
    if not (base and token and tenant_id and os.environ.get("MANAURUM_APP_ID")):
        raise CapabilityError(
            "capability env not fully injected (MANAURUM_CORE_URL / "
            "MANAURUM_RUNTIME_TOKEN / MANAURUM_TENANT_ID / MANAURUM_APP_ID)"
        )
    return base, {
        "Authorization": f"Bearer {token}",
        "X-Manaurum-Tenant-Id": tenant_id,
        "X-Manaurum-App-Id": app_id_header(name),
        "Content-Type": "application/json",
    }


async def call_capability(name: str, payload: dict[str, Any]) -> Any:
    """POST one capability call and return its ``output``.

    Every capability goes through this one door:
    ``POST {MANAURUM_CORE_URL}/api/capability/{name}``. Do NOT forward
    the user_context header here — the gateway rejects it on this path.
    """
    base, headers = _gateway(name)
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
    """One namespaced key per user. os.kv is per (app, tenant) only."""
    return f"notes:{user_id}"


async def read_note(user_id: str) -> str:
    output = await call_capability("os.kv.get", {"key": note_key(user_id)})
    value = output.get("value") if isinstance(output, dict) else None
    return value.get("text", "") if isinstance(value, dict) else ""


async def write_note(user_id: str, text: str) -> str:
    text = text[:10_000]
    await call_capability(
        "os.kv.set", {"key": note_key(user_id), "value": {"text": text}}
    )
    return text

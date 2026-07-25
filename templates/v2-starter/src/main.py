"""my-app — Manaurum Platform v2 hosted app.

Everything a v2 app must do, in one readable file. Deploy it unchanged
first (it works), then replace the note-taking bits with your own.

The four moving parts, in the order the platform exercises them:

1. ``GET /healthz`` — anonymous. Non-``/api/`` paths are proxied
   straight to this container without consulting ``runtime.api_routes``,
   so /healthz needs no manifest declaration.
2. ``src/static/index.html`` — the UI the desktop shell frames. It has
   to answer the ``manaurum:ready`` handshake; see that file.
3. ``GET /api/me`` — an ``auth: "user"`` route. The gateway mints a
   60-second RS256 JWT and injects it as ``X-Manaurum-User-Context``;
   this container verifies it against ``CORE_USER_CONTEXT_PUBLIC_KEY_PEM``.
   The end user's own bearer is NEVER forwarded here — that header is
   the only trustworthy caller identity you get.
4. ``GET/PUT /api/notes`` — the same auth, plus a real capability call:
   ``os.kv`` through the capability gateway, server-side, with the
   container's runtime token.

Two rules that are easy to get wrong and expensive to debug:

* Every ``/api/*`` path is **default-deny**. A path missing from
  ``manifest.runtime.api_routes`` returns 404 ``route_not_declared`` at
  the gateway and never reaches this file. Add a route here → add it
  there.
* ``X-Manaurum-App-Id`` takes the app **UUID** for ``os.kv.*`` and
  ``os.events.emit``, and the **slug** for every other capability. The
  container's ``MANAURUM_APP_ID`` env var is already the UUID, which is
  exactly what the kv client below sends.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

app = FastAPI(
    title="my-app",
    version=os.environ.get("MANAURUM_VERSION", "0.1.0"),
)

_STATIC_DIR = Path(__file__).parent / "static"


# ── Identity: verify the gateway's user_context JWT ───────────────────
#
# Mirrors Core's own verifier
# (``app/services/v2_apps/user_context_jwt.py::verify_user_context``).
# These four constants are the contract — change one and every
# authenticated request 401s.

_USER_CONTEXT_HEADER = "X-Manaurum-User-Context"
_JWT_ALGORITHM = "RS256"
_JWT_ISSUER = "manaurum-core"
_JWT_AUDIENCE = "manaurum-app"


def current_user(request: Request) -> dict[str, str]:
    """Return the verified caller, or raise the right HTTP error.

    Claims the gateway signs: ``sub`` (user id), ``tenant_id``,
    ``app_id``, ``app_version``. There is deliberately no
    ``workspace_id`` — the token does not carry one.
    """
    token = request.headers.get(_USER_CONTEXT_HEADER)
    if not token:
        # Either the route is declared `auth: "anonymous"`, or the
        # request did not come through the Manaurum gateway.
        raise HTTPException(status_code=401, detail="missing_user_context")

    pem = (os.environ.get("CORE_USER_CONTEXT_PUBLIC_KEY_PEM") or "").strip()
    if not pem:
        # Fail closed: an unprovisioned key must never read as "trusted".
        raise HTTPException(
            status_code=503,
            detail="core_user_context_public_key_not_provisioned",
        )

    from jose import jwt
    from jose.exceptions import ExpiredSignatureError, JWTError

    try:
        claims = jwt.decode(
            token,
            pem,
            algorithms=[_JWT_ALGORITHM],
            issuer=_JWT_ISSUER,
            audience=_JWT_AUDIENCE,
        )
    except ExpiredSignatureError:
        # 60s TTL. The gateway mints a fresh one per request, so this
        # normally means the token was stored and replayed.
        raise HTTPException(status_code=401, detail="user_context_expired")
    except JWTError:
        raise HTTPException(status_code=401, detail="user_context_invalid")

    user_id = str(claims.get("sub") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="user_context_no_subject")
    return {
        "user_id": user_id,
        "tenant_id": str(claims.get("tenant_id", "")),
        "app_id": str(claims.get("app_id", "")),
        "app_version": str(claims.get("app_version", "")),
    }


# ── Storage: the os.kv capability, called server-side ─────────────────
#
# manifest.json declares `data: {"none": true}`, so this app gets no
# Postgres schema and no DATABASE_URL — os.kv is the whole persistence
# layer. os.kv is scoped per (app, tenant) and is NOT user-aware, so we
# namespace keys by the verified user_id ourselves.

_KV_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class CapabilityError(Exception):
    """The runtime env is missing, the gateway is unreachable, or it
    returned a non-2xx. One exception type so callers have one thing to
    map to a user-visible error."""


def _gateway() -> tuple[str, dict[str, str]]:
    """Return ``(base_url, headers)`` for a capability call.

    All four values are injected by the deploy. Never hard-code or bake
    them into the image — the token is minted per deploy and rotates.
    """
    base = (os.environ.get("MANAURUM_CORE_URL") or "").rstrip("/")
    token = os.environ.get("MANAURUM_RUNTIME_TOKEN") or ""
    tenant_id = os.environ.get("MANAURUM_TENANT_ID") or ""
    # Already the UUID (see the module docstring) — os.kv rejects a slug
    # with 412 `app_id_must_be_uuid`.
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
    """
    base, headers = _gateway()
    try:
        async with httpx.AsyncClient(timeout=_KV_TIMEOUT) as client:
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


async def kv_get(key: str) -> Any:
    output = await call_capability("os.kv.get", {"key": key})
    return output.get("value") if isinstance(output, dict) else None


async def kv_set(key: str, value: Any) -> None:
    await call_capability("os.kv.set", {"key": key, "value": value})


# ── API — every path here is declared in manifest.runtime.api_routes ──


@app.get("/api/me")
async def read_me(request: Request) -> dict[str, str]:
    """Who is calling. The smallest possible `auth: "user"` route."""
    return current_user(request)


@app.get("/api/notes")
async def read_notes(request: Request) -> dict[str, Any]:
    """Read this user's note out of os.kv."""
    user = current_user(request)
    try:
        stored = await kv_get(f"notes:{user['user_id']}")
    except CapabilityError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"text": (stored or {}).get("text", "") if isinstance(stored, dict) else ""}


@app.put("/api/notes")
async def write_notes(request: Request) -> dict[str, Any]:
    """Write this user's note into os.kv."""
    user = current_user(request)
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("text"), str):
        raise HTTPException(status_code=422, detail="expected_json_text_string")
    text = body["text"][:10_000]
    try:
        await kv_set(f"notes:{user['user_id']}", {"text": text})
    except CapabilityError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"text": text}


# ── Health + static UI (anonymous; not declared in api_routes) ────────


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness. Keep it dependency-free — no DB, no gateway calls."""
    return {"status": "ok", "version": os.environ.get("MANAURUM_VERSION", "")}


@app.get("/{full_path:path}")
async def serve_static(full_path: str, request: Request) -> FileResponse:
    """Serve src/static, falling back to index.html for *routes* only.

    The fallback is deliberately narrow. An app that answers 200 to
    every path answers 200 to ``/secrets.json``, ``/.bash_history`` and
    to the random canary paths scanners use — which both trips those
    scanners and makes a real finding on this host unreadable, since
    every 200 is noise. It also turns a typo'd asset (``/styls.css``)
    into a silent HTML page instead of an error.

    So index.html is served only when the request plausibly names a
    client-side route: no file extension in the last segment, and the
    caller accepts HTML (a browser navigating always does; a scanner
    sending ``Accept: */*`` does not). Everything else gets a 404.
    """
    if full_path.startswith("api/"):
        # Only reachable for a path the manifest declared but this file
        # does not implement — don't hand it an HTML page.
        raise HTTPException(status_code=404, detail="not_found")
    candidate = (_STATIC_DIR / (full_path or "index.html")).resolve()
    if candidate.is_file() and candidate.is_relative_to(_STATIC_DIR.resolve()):
        return FileResponse(candidate)

    looks_like_a_file = "." in full_path.rsplit("/", 1)[-1]
    wants_html = "text/html" in request.headers.get("accept", "")
    if looks_like_a_file or not wants_html:
        raise HTTPException(status_code=404, detail="not_found")

    index = _STATIC_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="not_found")

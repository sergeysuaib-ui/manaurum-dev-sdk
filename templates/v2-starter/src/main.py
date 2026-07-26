"""my-app — Manaurum Platform v2 hosted app.

Deploy it unchanged first (it works), then replace the note-taking bits
with your own.

THE FILE LAYOUT IS THE LESSON. A v2 app is a project, not a page:

    src/auth.py           verify the gateway's user_context JWT
    src/capability.py     call the capability gateway (os.kv here)
    src/main.py           this file — the HTTP surface
    src/agent_routes.py   the OS Assistant surface
    tests/                pytest, incl. a JWT fixture — see tests/conftest.py

`auth` and `capability` are shared infrastructure; `main` and
`agent_routes` are the two surfaces built on them. Real apps grow by
adding surfaces (`routes_items.py`, `routes_invites.py`, …) over that
same thin core — see `references/reference-apps.md`.

The five moving parts, in the order the platform exercises them:

1. ``GET /healthz`` — anonymous. Non-``/api/`` paths are proxied
   straight to this container without consulting ``runtime.api_routes``,
   so /healthz needs no manifest declaration.
2. ``src/static/index.html`` — the UI the desktop shell frames. It has
   to answer the ``manaurum:ready`` handshake; see that file.
3. ``GET /api/me`` — an ``auth: "user"`` route. The gateway mints a
   60-second RS256 JWT and injects it as ``X-Manaurum-User-Context``.
   The end user's own bearer is NEVER forwarded — that header is the
   only trustworthy caller identity you get.
4. ``GET/PUT /api/notes`` — the same auth, plus a real capability call.
5. ``POST /agent/*`` — the OS Assistant, dispatched server-to-server.
   Not a gateway route. See src/agent_routes.py.

Two rules that are easy to get wrong and expensive to debug:

* Every ``/api/*`` path is **default-deny**. A path missing from
  ``manifest.runtime.api_routes`` returns 404 ``route_not_declared`` at
  the gateway and never reaches this file. Add a route here → add it
  there. (``/agent/*`` is the exception: never declare it.)
* Every capability you call must appear in
  ``manifest.requires_capabilities`` AND be granted on the install, or
  it is 403 ``capability_not_granted``.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from src import agent_routes
from src.auth import UserContextClaims, auth_claims
from src.capability import CapabilityError, read_note, write_note

app = FastAPI(
    title="my-app",
    version=os.environ.get("MANAURUM_VERSION", "0.1.0"),
)

# The OS Assistant surface. Mount it or your capabilities 404 on
# dispatch and the app stays invisible to the Assistant.
app.include_router(agent_routes.router)

_STATIC_DIR = Path(__file__).parent / "static"


# ── API — every path here is declared in manifest.runtime.api_routes ──


@app.get("/api/me")
async def read_me(claims: UserContextClaims = Depends(auth_claims)) -> dict[str, str]:
    """Who is calling. The smallest possible `auth: "user"` route."""
    return {
        "user_id": claims.user_id,
        "tenant_id": claims.tenant_id,
        "app_id": claims.app_id,
        "app_version": claims.app_version,
    }


@app.get("/api/notes")
async def get_notes(claims: UserContextClaims = Depends(auth_claims)) -> dict[str, Any]:
    """Read this user's note out of os.kv."""
    try:
        return {"text": await read_note(claims.user_id)}
    except CapabilityError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.put("/api/notes")
async def put_notes(
    request: Request,
    claims: UserContextClaims = Depends(auth_claims),
) -> dict[str, Any]:
    """Write this user's note into os.kv."""
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("text"), str):
        raise HTTPException(status_code=422, detail="expected_json_text_string")
    try:
        return {"text": await write_note(claims.user_id, body["text"])}
    except CapabilityError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


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

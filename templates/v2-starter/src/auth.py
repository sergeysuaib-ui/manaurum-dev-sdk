"""Identity — verify the gateway's `user_context` JWT.

Split out of main.py because two different surfaces need it: the
`/api/*` routes (gateway-proxied) and the `/agent/*` handlers (dispatched
server-to-server by the OS Assistant). Both get the SAME token, minted
with the same key, so they get the same verifier. Every real v2 app ends
up with this file.

Mirrors Core's own verifier
(``app/services/v2_apps/user_context_jwt.py::verify_user_context``) and
then does the two checks Core's helper leaves to you.

A valid signature is NOT enough. Core signs one token per request with
one key and one audience (``manaurum-app``) for EVERY app, so a token
minted for some other app — or for this app in some other tenant —
verifies here just as well. Whoever runs that other app sees its users'
tokens, and has 60 seconds to present one to you. So this module also
checks that the token names THIS app and THIS tenant, and refuses a
request that carries the header twice (the gateway adds its own copy;
a second one came from the client).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import HTTPException, Request

from src.capability import APP_SLUG

USER_CONTEXT_HEADER = "X-Manaurum-User-Context"
_JWT_ALGORITHM = "RS256"
_JWT_ISSUER = "manaurum-core"
_JWT_AUDIENCE = "manaurum-app"
# Core refuses a token without these, so a token without them was not
# minted by the gateway or the Assistant for anybody.
_REQUIRED_CLAIMS = ("sub", "tenant_id", "app_id", "app_version")


@dataclass(frozen=True)
class UserContextClaims:
    """The verified caller.

    Claims the gateway signs: ``sub`` (user id), ``tenant_id``, ``app_id``
    (your manifest's slug, not the UUID), ``app_version``, and
    ``workspace_id`` — the workspace the user opened the app from. The
    Assistant's dispatch omits ``workspace_id`` when it has none, so it can
    be empty.

    ``token`` is the raw JWT, kept so a handler can forward it to the
    capability gateway (``call_capability(..., user_context=claims.token)``).
    It expires 60 seconds after the gateway minted it: use it inside the
    request, never store it.
    """

    user_id: str
    tenant_id: str
    app_id: str
    app_version: str
    workspace_id: str = ""
    token: str = ""


def verify_user_context(token: str) -> UserContextClaims:
    """Verify a raw JWT string, or raise the right HTTPException.

    Kept separate from the request so it is directly unit-testable —
    see tests/test_auth.py, which signs tokens with a throwaway keypair.
    """
    pem = (os.environ.get("CORE_USER_CONTEXT_PUBLIC_KEY_PEM") or "").strip()
    if not pem:
        # Fail closed: an unprovisioned key must never read as "trusted".
        raise HTTPException(
            status_code=503,
            detail="core_user_context_public_key_not_provisioned",
        )
    tenant_id = (os.environ.get("MANAURUM_TENANT_ID") or "").strip()
    if not tenant_id:
        # Same reasoning: without our own tenant there is nothing to bind
        # the token to, and skipping the check would accept any tenant's.
        raise HTTPException(status_code=503, detail="manaurum_tenant_id_not_injected")

    from jose import jwt
    from jose.exceptions import ExpiredSignatureError, JWTError

    try:
        claims = jwt.decode(
            token,
            pem,
            algorithms=[_JWT_ALGORITHM],
            issuer=_JWT_ISSUER,
            audience=_JWT_AUDIENCE,
            options={"require_exp": True, "require_iat": True},
        )
    except ExpiredSignatureError:
        # 60s TTL. The gateway mints a fresh one per request, so this
        # normally means the token was stored and replayed.
        raise HTTPException(status_code=401, detail="user_context_expired")
    except JWTError:
        raise HTTPException(status_code=401, detail="user_context_invalid")

    if any(not str(claims.get(name) or "") for name in _REQUIRED_CLAIMS):
        raise HTTPException(status_code=401, detail="user_context_incomplete")

    # The two checks Core's helper does not do for you. The gateway mints
    # `app_id` as the slug for both the browser and the Assistant, and
    # `tenant_id` as the tenant the app was deployed into — the same value
    # the deploy injects as MANAURUM_TENANT_ID.
    if str(claims["app_id"]) != APP_SLUG:
        raise HTTPException(status_code=401, detail="user_context_wrong_app")
    if str(claims["tenant_id"]) != tenant_id:
        raise HTTPException(status_code=401, detail="user_context_wrong_tenant")

    return UserContextClaims(
        user_id=str(claims["sub"]),
        tenant_id=str(claims["tenant_id"]),
        app_id=str(claims["app_id"]),
        app_version=str(claims["app_version"]),
        workspace_id=str(claims.get("workspace_id") or ""),
        token=token,
    )


def auth_claims(request: Request) -> UserContextClaims:
    """FastAPI dependency: the verified caller for this request.

    Use it on every `auth: "user"` route AND on every `/agent/*` handler:
    ``claims: UserContextClaims = Depends(auth_claims)``.

    Never on an `auth: "anonymous"` route. The gateway mints nothing
    there and passes the request's headers through, so any
    `X-Manaurum-User-Context` an anonymous route sees was written by the
    client.
    """
    tokens = request.headers.getlist(USER_CONTEXT_HEADER)
    if not tokens:
        # Either the route is declared `auth: "anonymous"`, or the
        # request did not come through the Manaurum gateway.
        raise HTTPException(status_code=401, detail="missing_user_context")
    if len(tokens) > 1:
        # The gateway sets exactly one. A second copy was sent by the
        # client alongside it, and headers.get() would have returned the
        # client's — so refuse rather than guess which one is Core's.
        raise HTTPException(status_code=401, detail="user_context_ambiguous")
    return verify_user_context(tokens[0])

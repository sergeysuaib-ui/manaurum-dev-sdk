"""Identity — verify the gateway's `user_context` JWT.

Split out of main.py because two different surfaces need it: the
`/api/*` routes (gateway-proxied) and the `/agent/*` handlers (dispatched
server-to-server by the OS Assistant). Both get the SAME token, minted
with the same key, so they get the same verifier. Every real v2 app ends
up with this file.

Mirrors Core's own verifier
(``app/services/v2_apps/user_context_jwt.py::verify_user_context``).
These four constants are the contract — change one and every
authenticated request 401s.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import HTTPException, Request

#: Request header the gateway puts the freshly minted JWT in.
USER_CONTEXT_HEADER = "X-Manaurum-User-Context"
#: Core signs with RS256; we verify with the matching public key only.
_JWT_ALGORITHM = "RS256"
#: Expected ``iss``. Rejecting anything else stops a token minted for
#: another system being replayed at us.
_JWT_ISSUER = "manaurum-core"
#: Expected ``aud``. Every v2 app shares this audience value.
_JWT_AUDIENCE = "manaurum-app"


@dataclass(frozen=True)
class UserContextClaims:
    """The verified caller.

    Claims the gateway signs: ``sub`` (user id), ``tenant_id``,
    ``app_id``, ``app_version``. There is deliberately no
    ``workspace_id`` — the token does not carry one, so do not key your
    data on a workspace.

    Attributes:
        user_id: The token's ``sub``. Never empty on a verified instance;
            `verify_user_context` 401s instead of constructing one.
        tenant_id: Which tenant the caller belongs to. Empty string, not
            None, when the claim is absent.
        app_id: The app the gateway minted this token for.
        app_version: The app version it was minted for — useful when an
            old iframe is still open in someone's desktop.
    """

    user_id: str
    tenant_id: str = ""
    app_id: str = ""
    app_version: str = ""


def verify_user_context(token: str) -> UserContextClaims:
    """Verify a raw JWT string, or raise the right HTTPException.

    Kept separate from the request so it is directly unit-testable —
    see tests/test_auth.py, which signs tokens with a throwaway keypair.

    Args:
        token: The raw compact JWT from the request header.

    Returns:
        The verified claims.

    Raises:
        HTTPException: 503 ``core_user_context_public_key_not_provisioned``
            when the container has no public key — fail closed, an
            unprovisioned key must never read as "trusted". 401
            ``user_context_expired`` (tokens live 60s, so this normally
            means one was stored and replayed),
            ``user_context_invalid`` (bad signature, issuer or audience),
            or ``user_context_no_subject``.
    """
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
    return UserContextClaims(
        user_id=user_id,
        tenant_id=str(claims.get("tenant_id", "")),
        app_id=str(claims.get("app_id", "")),
        app_version=str(claims.get("app_version", "")),
    )


def auth_claims(request: Request) -> UserContextClaims:
    """FastAPI dependency: the verified caller for this request.

    Use it on every `auth: "user"` route AND on every `/agent/*` handler:
    ``claims: UserContextClaims = Depends(auth_claims)``.

    Args:
        request: Injected by FastAPI.

    Returns:
        The verified caller for this request.

    Raises:
        HTTPException: 401 ``missing_user_context`` when the header is
            absent — either the route is declared `auth: "anonymous"`, or
            the request did not come through the Manaurum gateway. Plus
            anything `verify_user_context` raises.
    """
    token = request.headers.get(USER_CONTEXT_HEADER)
    if not token:
        # Either the route is declared `auth: "anonymous"`, or the
        # request did not come through the Manaurum gateway.
        raise HTTPException(status_code=401, detail="missing_user_context")
    return verify_user_context(token)

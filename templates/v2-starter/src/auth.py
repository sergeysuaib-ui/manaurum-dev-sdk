"""Identity — verify the gateway's `user_context` JWT.

Split out of main.py because two different surfaces need it: the
`/api/*` routes (gateway-proxied) and the `/agent/*` handlers (dispatched
server-to-server by the OS Assistant). Both get the SAME token, minted
with the same key, so they get the same verifier. Every real v2 app ends
up with this file.

Binds the token the way Core's own bundled verifier does
(``backend/app/services/v2_apps/_manaurum_runtime.py::verify_token``).

A valid signature is NOT enough. Core signs every app's tokens with one
key, and every token still carries the shared audience ``manaurum-app``,
so a token minted for some other app — or for this app in some other
tenant — has a perfectly good signature here. Whoever runs that other app
sees its users' tokens, and has 60 seconds to present one to you. Since
MAN-3231 Core also names the app in ``aud`` (``["manaurum-app", "<the
app's v2_apps id>"]``), and the deploy injects that id as
``MANAURUM_APP_ID``. So this module requires THIS app's id as the
audience, THIS tenant (``MANAURUM_TENANT_ID``), this app's slug in
``app_id``, and no ``typ`` or ``scope``: a person pass and a system token
also name this app in their audience, and neither is a user context. It
refuses a request that carries the header twice, too. Since MAN-3214 the
gateway drops a copy the client sent; an earlier version added its own
and forwarded the client's too, and this check costs nothing to keep.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import HTTPException, Request

from src.capability import APP_SLUG

USER_CONTEXT_HEADER = "X-Manaurum-User-Context"
_JWT_ALGORITHM = "RS256"
_JWT_ISSUER = "manaurum-core"
# Every token carries the shared audience "manaurum-app" as well, so it is
# NOT what this module checks: it proves nothing about which app a token is
# for. The audience checked is this app's own id, from the deploy's env.
_APP_ID_ENV = "MANAURUM_APP_ID"
_TENANT_ID_ENV = "MANAURUM_TENANT_ID"
# Claims only Core's OTHER tokens carry: a person pass has `typ`, a system
# token (cron) has `scope`. Both name this app in their audience too.
_OTHER_TOKEN_KIND_CLAIMS = ("typ", "scope")
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

    ``locale`` (``"en"`` | ``"ru"`` | ``"he"``) and ``dir`` (``"ltr"`` |
    ``"rtl"``) are the language the person picked in ManAurum, on routes
    and on the Assistant's calls alike (Core MAN-3244). Both are ``None``
    when they made no explicit choice: pick the language with
    :func:`server_language` rather than reading them raw.

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
    locale: str | None = None
    dir: str | None = None


# ── The person's language (Core MAN-3244) ──────────────────────────────────
#
# Core reads `user_profiles.preferred_language` and adds `locale` + `dir` to
# the user_context (and to the person pass) when it is one of these. The
# table is Core's `LOCALE_DIRECTION` and the reading is Core's
# `read_locale_claims` (backend/app/services/v2_apps/user_context_jwt.py:84
# and :102-113 at origin/main 1256064): a supported language with its OWN
# direction counts, anything else reads as absent. The language is a hint,
# not identity, so a bad pair never refuses the caller and never raises.

LOCALE_DIRECTION = {"en": "ltr", "ru": "ltr", "he": "rtl"}


def locale_pair(claims: dict) -> tuple[str | None, str | None]:
    """``(locale, dir)`` from verified claims, or ``(None, None)``.

    Exact match, as Core reads it: ``"HE"``, ``"fr"``, or ``"he"`` with
    ``"ltr"`` are all absent, so the app falls back instead of meeting a
    language it has no strings for. An unknown locale with no ``dir`` at all
    is absent too, as in Core's ``read_locale_claims``.
    """
    locale = claims.get("locale")
    expected = LOCALE_DIRECTION.get(locale) if isinstance(locale, str) else None
    if expected is not None and claims.get("dir") == expected:
        return locale, expected
    return None, None


def server_language(
    request: Request, claims: UserContextClaims | PersonClaims | None = None,
) -> str:
    """The language this server should write text in: ``en``, ``ru`` or ``he``.

    1. ``claims.locale`` — the person's choice in ManAurum, from the
       user_context or the person pass. It can trail a switch by up to 60 s
       (Core caches it); inside the window the page hears the switch at once
       (``manaurum:locale-change``), so text the page renders should follow
       the page, not this.
    2. The request's ``Accept-Language`` (the gateway forwards it): the first
       of en / ru / he, in the order the browser sent them. The Assistant's
       calls to ``/agent/*`` carry none.
    3. English.

    Use the direction with it: ``LOCALE_DIRECTION[server_language(...)]``.
    """
    locale = getattr(claims, "locale", None)
    if locale in LOCALE_DIRECTION:
        return locale
    for part in request.headers.get("accept-language", "").split(","):
        base = part.split(";")[0].strip().lower().split("-")[0]
        if base in LOCALE_DIRECTION:
            return base
    return "en"


def verify_user_context(token: str) -> UserContextClaims:
    """Verify a raw JWT string, or raise the right HTTPException.

    503 when the key, ``MANAURUM_APP_ID`` or ``MANAURUM_TENANT_ID`` is not
    set (fail closed). 401 ``user_context_wrong_app`` for a token whose
    audience does not name this app (or names none) or whose ``app_id`` is
    not this slug, ``user_context_wrong_tenant``, ``user_context_wrong_kind``
    for a person pass or a system token, ``user_context_expired``,
    ``user_context_incomplete``, and ``user_context_invalid`` for the rest.

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
    # Same reasoning for the two ids: without them nothing says which app
    # and tenant a token has to be for, and skipping either check would
    # accept a token minted for any app, or any tenant.
    app_id = (os.environ.get(_APP_ID_ENV) or "").strip()
    if not app_id:
        raise HTTPException(status_code=503, detail="manaurum_app_id_not_injected")
    tenant_id = (os.environ.get(_TENANT_ID_ENV) or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=503, detail="manaurum_tenant_id_not_injected")

    from jose import jwt
    from jose.exceptions import ExpiredSignatureError, JWTError

    try:
        claims = jwt.decode(
            token,
            pem,
            algorithms=[_JWT_ALGORITHM],
            issuer=_JWT_ISSUER,
            # This app's id, not the shared "manaurum-app" every token has.
            audience=app_id,
            # python-jose skips the audience check for a token with no `aud`
            # at all, and the expiry check for one with no `exp`: require
            # them (and `iss` and `iat`, which Core always mints), or the
            # token is bound to no app and never expires.
            options={"require_aud": True, "require_iss": True,
                     "require_exp": True, "require_iat": True},
        )
    except ExpiredSignatureError:
        # 60s TTL. The gateway mints a fresh one per request, so this
        # normally means the token was stored and replayed.
        raise HTTPException(status_code=401, detail="user_context_expired")
    except JWTError as exc:
        # A foreign or missing audience ("Invalid audience", or 'missing
        # required key "aud"'): minted for another app, or naming none.
        # Anything else (signature, issuer, another missing claim) is simply
        # not a token Core made for us.
        if "aud" in str(exc):
            raise HTTPException(status_code=401, detail="user_context_wrong_app")
        raise HTTPException(status_code=401, detail="user_context_invalid")

    # Before the required claims: a person pass or a system token lacks
    # `app_version`, and "incomplete" would hide what it really is.
    if any(name in claims for name in _OTHER_TOKEN_KIND_CLAIMS):
        raise HTTPException(status_code=401, detail="user_context_wrong_kind")
    if any(not str(claims.get(name) or "") for name in _REQUIRED_CLAIMS):
        raise HTTPException(status_code=401, detail="user_context_incomplete")

    # The audience already named this app by its id. The gateway also
    # mints `app_id` as the slug, for both the browser and the Assistant,
    # and `tenant_id` as the tenant the app was deployed into — the same
    # value the deploy injects as MANAURUM_TENANT_ID.
    if str(claims["app_id"]) != APP_SLUG:
        raise HTTPException(status_code=401, detail="user_context_wrong_app")
    if str(claims["tenant_id"]) != tenant_id:
        raise HTTPException(status_code=401, detail="user_context_wrong_tenant")

    locale, direction = locale_pair(claims)
    return UserContextClaims(
        user_id=str(claims["sub"]),
        tenant_id=str(claims["tenant_id"]),
        app_id=str(claims["app_id"]),
        app_version=str(claims["app_version"]),
        workspace_id=str(claims.get("workspace_id") or ""),
        token=token,
        locale=locale,
        dir=direction,
    )


def auth_claims(request: Request) -> UserContextClaims:
    """FastAPI dependency: the verified caller for this request.

    Use it on every `auth: "user"` route AND on every `/agent/*` handler:
    ``claims: UserContextClaims = Depends(auth_claims)``.

    Never on an `auth: "anonymous"` route. The gateway mints nothing
    there and drops a copy the client sent (MAN-3214), so any
    `X-Manaurum-User-Context` an anonymous route sees did not come
    through the gateway and was not written by Core for this request.
    """
    tokens = request.headers.getlist(USER_CONTEXT_HEADER)
    if not tokens:
        # Either the route is declared `auth: "anonymous"`, or the
        # request did not come through the Manaurum gateway.
        raise HTTPException(status_code=401, detail="missing_user_context")
    if len(tokens) > 1:
        # The gateway sets exactly one and, since MAN-3214, drops the
        # client's. An earlier version forwarded the client's alongside
        # it, and headers.get() returned the client's — so refuse rather
        # than guess which one is Core's.
        raise HTTPException(status_code=401, detail="user_context_ambiguous")
    return verify_user_context(tokens[0])


# ── Person pass on `auth: "optional"` routes (Core MAN-3200) ───────────────
#
# On an `optional` route a signed-in member of your tenant arrives with the
# usual `X-Manaurum-User-Context` (for capability calls on their behalf) AND
# with `X-Manaurum-Person`, which says who they are. A guest — or a member
# of another tenant, which the gateway makes look exactly like a guest —
# arrives with neither.
#
# Like the user_context, the pass is bound to one app: its audience is your
# `MANAURUM_APP_ID` (the v2_apps UUID the deploy injects), so a pass minted
# for another app fails here on the audience check. `require_aud` matters:
# python-jose skips the audience check for a token with no `aud`. The two
# kinds cannot stand in for each other: a pass carries `typ: "person"`,
# which this verifier requires and `verify_user_context` refuses, and a
# user context or a system token carries no `typ` at all.

PERSON_HEADER = "X-Manaurum-Person"
_PERSON_TYP = "person"


@dataclass(frozen=True)
class PersonClaims:
    """Who is asking. ``kind`` is ``"member"`` today; ``"external"`` arrives
    with App people (invited outsiders). ``name`` is the profile name or
    empty — never the email. ``is_tenant_admin`` / ``workspace_role`` are
    facts, not roles: turn them into a permission yourself. ``locale`` /
    ``dir`` are the person's language, read as on :class:`UserContextClaims`
    (Core ``person_pass.py:169``)."""

    kind: str
    sub: str
    tenant_id: str
    email: str = ""
    name: str = ""
    role: str = ""
    is_tenant_admin: bool = False
    workspace_role: str = ""
    locale: str | None = None
    dir: str | None = None


def verify_person_pass(token: str) -> PersonClaims:
    """Verify a raw `X-Manaurum-Person` JWT for THIS app, or raise."""
    pem = (os.environ.get("CORE_USER_CONTEXT_PUBLIC_KEY_PEM") or "").strip()
    app_id = (os.environ.get(_APP_ID_ENV) or "").strip()
    tenant_id = (os.environ.get(_TENANT_ID_ENV) or "").strip()
    if not pem:
        raise HTTPException(status_code=503, detail="core_user_context_public_key_not_provisioned")
    if not app_id:
        # The audience IS the check. Without it any app's pass would pass.
        raise HTTPException(status_code=503, detail="manaurum_app_id_not_injected")
    if not tenant_id:
        raise HTTPException(status_code=503, detail="manaurum_tenant_id_not_injected")

    from jose import jwt
    from jose.exceptions import ExpiredSignatureError, JWTError

    try:
        claims = jwt.decode(
            token,
            pem,
            algorithms=[_JWT_ALGORITHM],
            issuer=_JWT_ISSUER,
            audience=app_id,
            options={"require_exp": True, "require_iat": True, "require_aud": True,
                     "require_iss": True},
        )
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="person_pass_expired")
    except JWTError:
        # Wrong key, wrong issuer, or minted for another app (audience).
        raise HTTPException(status_code=401, detail="person_pass_invalid")

    if claims.get("typ") != _PERSON_TYP or claims.get("kind") not in ("member", "external"):
        raise HTTPException(status_code=401, detail="person_pass_invalid")
    if not str(claims.get("sub") or ""):
        raise HTTPException(status_code=401, detail="person_pass_incomplete")
    if str(claims.get("tenant_id") or "") != tenant_id:
        raise HTTPException(status_code=401, detail="person_pass_wrong_tenant")

    facts = claims.get("facts") if isinstance(claims.get("facts"), dict) else {}
    locale, direction = locale_pair(claims)
    return PersonClaims(
        kind=str(claims["kind"]),
        sub=str(claims["sub"]),
        tenant_id=tenant_id,
        email=str(claims.get("email") or ""),
        name=str(claims.get("name") or ""),
        role=str(claims.get("role") or ""),
        is_tenant_admin=bool(facts.get("is_tenant_admin")),
        workspace_role=str(facts.get("workspace_role") or ""),
        locale=locale,
        dir=direction,
    )


def optional_person(request: Request) -> PersonClaims | None:
    """FastAPI dependency for `auth: "optional"` routes: the person, or
    ``None`` for a guest.

    ``person: PersonClaims | None = Depends(optional_person)``

    A pass that is present but does not verify is a 401, not a guest: it
    is either an attack or a broken deploy, and treating it as "no pass"
    would hide both.
    """
    tokens = request.headers.getlist(PERSON_HEADER)
    if not tokens:
        return None
    if len(tokens) > 1:
        raise HTTPException(status_code=401, detail="person_pass_ambiguous")
    return verify_person_pass(tokens[0])

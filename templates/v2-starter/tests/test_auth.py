"""The user_context verifier — the one piece of security code every v2
app owns. If these pass, an attacker cannot hand your container a
self-signed token and become somebody else.

Each negative test names a real way the check can be silently wrong. A
verifier that decodes without checking `iss`/`aud`/`exp` passes the
happy-path test and fails all of these.

The last group is the one a signature check cannot do: Core signs every
app's tokens with the same key and the same audience, so a token minted
for another app, or for this app in another tenant, has a perfectly good
signature. Only the `app_id` and `tenant_id` checks stop it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from src.auth import verify_user_context
from src.capability import APP_SLUG
from tests.conftest import TENANT_ID


def test_valid_token_is_accepted(user_context):
    token = user_context(user_id="u-sergey")
    claims = verify_user_context(token)
    assert claims.user_id == "u-sergey"
    assert claims.tenant_id == TENANT_ID
    assert claims.app_id == APP_SLUG
    assert claims.workspace_id == "33333333-3333-3333-3333-333333333333"
    # Kept so a handler can forward it to the capability gateway.
    assert claims.token == token


def test_expired_token_is_rejected(user_context):
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    with pytest.raises(HTTPException) as exc:
        verify_user_context(user_context(exp=past))
    assert exc.value.status_code == 401
    assert exc.value.detail == "user_context_expired"


def test_wrong_issuer_is_rejected(user_context):
    """A token signed by the right key but issued by something else."""
    with pytest.raises(HTTPException) as exc:
        verify_user_context(user_context(iss="not-manaurum"))
    assert exc.value.status_code == 401


def test_wrong_audience_is_rejected(user_context):
    """Stops a token minted for a different audience being replayed here."""
    with pytest.raises(HTTPException) as exc:
        verify_user_context(user_context(aud="manaurum-something-else"))
    assert exc.value.status_code == 401


def test_token_without_subject_is_rejected(user_context):
    """No `sub` means no caller identity — must never read as anonymous-ok."""
    with pytest.raises(HTTPException) as exc:
        verify_user_context(user_context(sub=""))
    assert exc.value.status_code == 401


def test_garbage_is_rejected():
    with pytest.raises(HTTPException) as exc:
        verify_user_context("not-a-jwt")
    assert exc.value.status_code == 401


def test_missing_public_key_fails_closed(monkeypatch, user_context):
    """An unprovisioned key must 503, never 'trusted by default'."""
    token = user_context()
    monkeypatch.setenv("CORE_USER_CONTEXT_PUBLIC_KEY_PEM", "")
    with pytest.raises(HTTPException) as exc:
        verify_user_context(token)
    assert exc.value.status_code == 503


def test_token_signed_by_a_different_key_is_rejected(user_context, monkeypatch):
    """The whole point: a well-formed token this app did not trust."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attacker_public = (
        attacker.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    # App now trusts only the attacker's key; our legitimately signed
    # token must stop verifying.
    monkeypatch.setenv("CORE_USER_CONTEXT_PUBLIC_KEY_PEM", attacker_public)
    with pytest.raises(HTTPException) as exc:
        verify_user_context(user_context())
    assert exc.value.status_code == 401


# -- Binding: the checks a valid signature cannot make -----------------


def test_token_minted_for_another_app_is_rejected(user_context):
    """Every app's users carry tokens with this exact signature, issuer and
    audience. The developer of any app they open sees them, and has 60
    seconds to present one here."""
    with pytest.raises(HTTPException) as exc:
        verify_user_context(user_context(app_id="some-other-app"))
    assert exc.value.status_code == 401
    assert exc.value.detail == "user_context_wrong_app"


def test_token_carrying_the_app_uuid_is_rejected(user_context):
    """The gateway mints the slug. A UUID here was not minted by it."""
    with pytest.raises(HTTPException) as exc:
        verify_user_context(user_context(app_id="22222222-2222-2222-2222-222222222222"))
    assert exc.value.detail == "user_context_wrong_app"


def test_token_for_another_tenant_is_rejected(user_context):
    with pytest.raises(HTTPException) as exc:
        verify_user_context(user_context(tenant_id="99999999-9999-9999-9999-999999999999"))
    assert exc.value.status_code == 401
    assert exc.value.detail == "user_context_wrong_tenant"


@pytest.mark.parametrize("claim", ["tenant_id", "app_id", "app_version"])
def test_token_missing_a_required_claim_is_rejected(user_context, claim):
    """Core refuses these too. Defaulting a missing `app_id` to "" and then
    not comparing it is how a verifier ends up accepting anything."""
    with pytest.raises(HTTPException) as exc:
        verify_user_context(user_context(**{claim: ""}))
    assert exc.value.status_code == 401
    assert exc.value.detail == "user_context_incomplete"


@pytest.mark.parametrize("dropped", ["exp", "iat"])
def test_token_without_exp_or_iat_is_rejected(keypair, dropped):
    """Core always mints both. Without `exp` python-jose would accept the
    token forever."""
    from jose import jwt

    now = datetime.now(timezone.utc)
    claims = {"sub": "u-1", "tenant_id": TENANT_ID, "app_id": APP_SLUG,
              "app_version": "0.1.0", "iss": "manaurum-core", "aud": "manaurum-app",
              "iat": now, "exp": now + timedelta(seconds=60)}
    del claims[dropped]
    token = jwt.encode(claims, keypair[0], algorithm="RS256")
    with pytest.raises(HTTPException) as exc:
        verify_user_context(token)
    assert exc.value.status_code == 401


def test_missing_tenant_env_fails_closed(monkeypatch, user_context):
    """No MANAURUM_TENANT_ID means nothing to bind to: 503, never 'any'."""
    token = user_context()
    monkeypatch.setenv("MANAURUM_TENANT_ID", "")
    with pytest.raises(HTTPException) as exc:
        verify_user_context(token)
    assert exc.value.status_code == 503


# ── Person pass (`auth: "optional"`, Core MAN-3200) ────────────────────────

APP_UUID = "44444444-4444-4444-4444-444444444444"
OTHER_APP_UUID = "55555555-5555-5555-5555-555555555555"


@pytest.fixture
def person_pass(keypair, monkeypatch):
    """Mint the pass the gateway sends a member on an `optional` route.
    Its audience is the app's UUID, so the test env needs MANAURUM_APP_ID."""
    from jose import jwt

    monkeypatch.setenv("MANAURUM_APP_ID", APP_UUID)

    def mint(**overrides) -> str:
        now = datetime.now(timezone.utc)
        claims = {
            "iss": "manaurum-core", "aud": APP_UUID, "typ": "person",
            "kind": "member", "sub": "u-ann", "tenant_id": TENANT_ID,
            "app_id": APP_UUID, "app_slug": APP_SLUG,
            "email": "ann@example.com", "name": "Ann",
            "facts": {"is_tenant_admin": True, "workspace_role": "member"},
            "iat": now, "exp": now + timedelta(seconds=60),
        }
        claims.update(overrides)
        return jwt.encode(claims, keypair[0], algorithm="RS256")

    return mint


def test_person_pass_for_this_app_is_accepted(person_pass):
    from src.auth import verify_person_pass

    p = verify_person_pass(person_pass())
    assert (p.kind, p.sub, p.email, p.name) == ("member", "u-ann", "ann@example.com", "Ann")
    assert p.is_tenant_admin is True and p.workspace_role == "member"


def test_person_pass_for_another_app_is_rejected(person_pass):
    """The whole point of the pass: bound to one app by its audience."""
    from src.auth import verify_person_pass

    with pytest.raises(HTTPException) as exc:
        verify_person_pass(person_pass(aud=OTHER_APP_UUID))
    assert exc.value.detail == "person_pass_invalid"


def test_user_context_is_not_a_person_pass(person_pass, user_context):
    from src.auth import verify_person_pass

    with pytest.raises(HTTPException):
        verify_person_pass(user_context())


def test_person_pass_from_another_tenant_is_rejected(person_pass):
    from src.auth import verify_person_pass

    with pytest.raises(HTTPException) as exc:
        verify_person_pass(person_pass(tenant_id="99999999-9999-9999-9999-999999999999"))
    assert exc.value.detail == "person_pass_wrong_tenant"


def test_person_pass_needs_the_app_id_env(person_pass, monkeypatch):
    from src.auth import verify_person_pass

    token = person_pass()
    monkeypatch.delenv("MANAURUM_APP_ID")
    with pytest.raises(HTTPException) as exc:
        verify_person_pass(token)
    assert exc.value.status_code == 503


def test_optional_person_is_none_for_a_guest_and_401_for_a_bad_pass(person_pass):
    from starlette.requests import Request

    from src.auth import optional_person

    def request(*headers):
        raw = [(b"x-manaurum-person", h.encode()) for h in headers]
        return Request({"type": "http", "headers": raw})

    assert optional_person(request()) is None
    assert optional_person(request(person_pass())).sub == "u-ann"
    for bad in (("garbage",), (person_pass(), person_pass())):
        with pytest.raises(HTTPException) as exc:
            optional_person(request(*bad))
        assert exc.value.status_code == 401


def test_person_pass_without_any_audience_is_rejected(person_pass, keypair):
    """python-jose skips the audience check for a token with no `aud` at
    all; the verifier must require the claim."""
    from jose import jwt

    from src.auth import verify_person_pass

    claims = jwt.get_unverified_claims(person_pass())
    del claims["aud"]
    no_aud = jwt.encode(claims, keypair[0], algorithm="RS256")
    with pytest.raises(HTTPException) as exc:
        verify_person_pass(no_aud)
    assert exc.value.detail == "person_pass_invalid"


# ── The person's language (`locale` / `dir`, Core MAN-3244) ────────────────
#
# Core adds both claims when the person picked a language, and reads only a
# supported language with its own direction (`read_locale_claims`). A bad
# pair is absent, never a 401: the language is a hint, not identity.

_LANGUAGES = [("en", "ltr"), ("ru", "ltr"), ("he", "rtl")]
_NOT_A_LANGUAGE = [
    {"locale": "he", "dir": "ltr"},        # not Hebrew's direction
    {"locale": "en", "dir": "rtl"},
    {"locale": "he", "dir": "up"},
    {"locale": "ar", "dir": "rtl"},        # a language ManAurum does not offer
    {"locale": "HE", "dir": "rtl"},        # Core compares exactly
    {"locale": "fr"},                      # an unknown language with no dir
    {"locale": 5, "dir": "rtl"},
    {"locale": None, "dir": None},
    {"dir": "rtl"},
]


@pytest.mark.parametrize("locale,direction", _LANGUAGES)
def test_the_persons_language_is_read(user_context, locale, direction):
    claims = verify_user_context(user_context(locale=locale, dir=direction))
    assert (claims.locale, claims.dir) == (locale, direction)


@pytest.mark.parametrize("pair", _NOT_A_LANGUAGE, ids=repr)
def test_a_language_that_is_not_one_reads_as_absent(user_context, pair):
    """Accepted, with no language: a 401 here would lock the person out of
    the app over a hint."""
    claims = verify_user_context(user_context(user_id="u-bad-pair", **pair))
    assert claims.user_id == "u-bad-pair"
    assert (claims.locale, claims.dir) == (None, None)


def test_a_token_without_the_language_still_verifies(user_context):
    """What Core mints when the person made no explicit choice, and what
    every token minted before MAN-3244 looked like."""
    from jose import jwt

    token = user_context()
    assert "locale" not in jwt.get_unverified_claims(token)
    claims = verify_user_context(token)
    assert claims.user_id == "u-test"
    assert (claims.locale, claims.dir) == (None, None)


def test_the_person_pass_carries_the_language_too(person_pass):
    from src.auth import verify_person_pass

    p = verify_person_pass(person_pass(locale="he", dir="rtl"))
    assert (p.locale, p.dir) == ("he", "rtl")
    for pair in _NOT_A_LANGUAGE:
        p = verify_person_pass(person_pass(**pair))
        assert (p.sub, p.locale, p.dir) == ("u-ann", None, None), pair
    p = verify_person_pass(person_pass())
    assert (p.locale, p.dir) == (None, None)


@pytest.mark.parametrize("locale,header,expected", [
    ("he", "ru-RU,ru;q=0.9", "he"),        # the choice in ManAurum wins
    (None, "fr-FR,ru;q=0.8,en;q=0.5", "ru"),  # else the browser's first en/ru/he
    (None, "fr-FR,de", "en"),              # else English
    (None, "", "en"),
])
def test_server_language_is_the_claim_then_accept_language_then_english(
        locale, header, expected):
    from starlette.requests import Request

    from src.auth import LOCALE_DIRECTION, UserContextClaims, server_language

    request = Request({"type": "http",
                       "headers": [(b"accept-language", header.encode())] if header else []})
    claims = UserContextClaims(user_id="u", tenant_id="t", app_id="a", app_version="1",
                               locale=locale, dir=LOCALE_DIRECTION.get(locale or ""))
    assert server_language(request, claims) == expected


def test_server_language_without_claims_reads_the_header():
    """An `anonymous` route has no token: `Accept-Language` is all there is."""
    from starlette.requests import Request

    from src.auth import server_language

    request = Request({"type": "http", "headers": [(b"accept-language", b"he-IL,en;q=0.5")]})
    assert server_language(request) == "he"

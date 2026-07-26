"""The user_context verifier — the one piece of security code every v2
app owns. If these pass, an attacker cannot hand your container a
self-signed token and become somebody else.

Each negative test names a real way the check can be silently wrong. A
verifier that decodes without checking `iss`/`aud`/`exp` passes the
happy-path test and fails all of these.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from src.auth import verify_user_context


def test_valid_token_is_accepted(user_context):
    claims = verify_user_context(user_context(user_id="u-sergey"))
    assert claims.user_id == "u-sergey"
    assert claims.tenant_id == "11111111-1111-1111-1111-111111111111"


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

"""Pytest fixtures for a v2 hosted app.

THE FIXTURE THAT MATTERS is `user_context` — it mints the RS256
`X-Manaurum-User-Context` JWT the gateway injects on every
`auth: "user"` route and every `/agent/*` dispatch. Without it you
cannot test an authenticated route at all, which is why most v2 apps
end up with no tests.

You do NOT need Core running, and you must not copy a real token: the
verifier only checks a signature against whatever public key is in
`CORE_USER_CONTEXT_PUBLIC_KEY_PEM`. So we generate a throwaway keypair
per test session, point the app at the public half, and sign with the
private half. Same algorithm, same issuer, same audience, no network.

This starter declares `data: {"none": true}` and persists through
`os.kv`, so there is no database fixture here. If your app uses the
managed Postgres mode instead, the DB fixture to copy is in
`references/reference-apps.md` § Testing — it applies your
`migrations/*.sql` into a throwaway schema and skips cleanly when no
DSN is configured.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Must match src/auth.py — and src/auth.py must match Core.
_ISSUER = "manaurum-core"
_AUDIENCE = "manaurum-app"


@pytest.fixture(scope="session")
def keypair() -> tuple[str, str]:
    """A throwaway RSA keypair as (private_pem, public_pem)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


@pytest.fixture(autouse=True)
def _core_public_key(keypair, monkeypatch):
    """Point src.auth at the test public key for every test.

    autouse, because forgetting it produces a 503
    `core_user_context_public_key_not_provisioned` that reads like a
    bug in the app rather than a missing fixture.
    """
    monkeypatch.setenv("CORE_USER_CONTEXT_PUBLIC_KEY_PEM", keypair[1])


@pytest.fixture
def user_context(keypair):
    """Return `mint(user_id=..., **overrides)` -> a signed JWT string.

    The overrides are what make the negative tests possible: pass
    `iss="somebody-else"` or `exp=<past>` to prove the verifier actually
    rejects a token instead of merely decoding one.
    """
    from jose import jwt

    private_pem = keypair[0]

    def mint(user_id: str = "u-test", **overrides) -> str:
        now = datetime.now(timezone.utc)
        claims = {
            "sub": user_id,
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "app_id": "22222222-2222-2222-2222-222222222222",
            "app_version": "0.1.0",
            "iss": _ISSUER,
            "aud": _AUDIENCE,
            "iat": now,
            # The real gateway mints these with a 60-second TTL.
            "exp": now + timedelta(seconds=60),
        }
        claims.update(overrides)
        return jwt.encode(claims, private_pem, algorithm="RS256")

    return mint


@pytest.fixture
def fake_kv(monkeypatch):
    """Replace the capability gateway with an in-memory dict.

    Unit tests must not depend on Core being reachable. Capability calls
    are patched where they are USED (src.capability's own helpers), so a
    test exercises your logic, not httpx.
    """
    store: dict[str, str] = {}

    async def _read(user_id: str) -> str:
        return store.get(user_id, "")

    async def _write(user_id: str, text: str) -> str:
        store[user_id] = text[:10_000]
        return store[user_id]

    monkeypatch.setattr("src.agent_routes.read_note", _read)
    monkeypatch.setattr("src.agent_routes.write_note", _write)
    return store

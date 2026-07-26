"""The OS Assistant surface.

Agent handlers are plain async functions over your own data — no LLM, no
network. So test them by calling them directly with the claims your
`Depends(auth_claims)` would have produced, exactly as `libi` does. You
do not need to mint a JWT here; JWT verification is covered once, in
test_auth.py.

The assertion that keeps an app honest is the LAST one: two users must
not see each other's data. The runtime mints a valid token for any user
with the app installed, so per-user scoping is the app's job, not the
platform's.
"""
from __future__ import annotations

import pytest

from src.agent_routes import SaveNoteInput, read_my_note, save_my_note
from src.auth import UserContextClaims

pytestmark = pytest.mark.asyncio


def _claims(user_id: str) -> UserContextClaims:
    return UserContextClaims(user_id=user_id, tenant_id="t", app_id="my-app")


async def test_read_is_empty_before_anything_is_saved(fake_kv):
    result = await read_my_note(claims=_claims("u-1"))
    assert result == {"ok": True, "output": {"text": ""}}


async def test_save_then_read_round_trips(fake_kv):
    saved = await save_my_note(SaveNoteInput(text="Buy milk"), claims=_claims("u-1"))
    assert saved["ok"] is True

    read = await read_my_note(claims=_claims("u-1"))
    assert read["output"]["text"] == "Buy milk"


async def test_save_overwrites_rather_than_appends(fake_kv):
    """The manifest description promises overwrite — prove it does."""
    await save_my_note(SaveNoteInput(text="first"), claims=_claims("u-1"))
    await save_my_note(SaveNoteInput(text="second"), claims=_claims("u-1"))

    read = await read_my_note(claims=_claims("u-1"))
    assert read["output"]["text"] == "second"


async def test_capability_failure_is_a_failed_tool_call_not_a_crash(monkeypatch):
    """`{"ok": false}` is what the model can read and react to. A 500
    surfaces as an opaque tool error and the Assistant just gives up."""
    from src.capability import CapabilityError

    async def _boom(user_id: str) -> str:
        raise CapabilityError("os.kv.get -> 403: capability_not_granted")

    monkeypatch.setattr("src.agent_routes.read_note", _boom)

    result = await read_my_note(claims=_claims("u-1"))
    assert result["ok"] is False
    assert "capability_not_granted" in result["error"]


async def test_one_user_cannot_read_another_users_note(fake_kv):
    """Identity comes from the verified claims, never from the input —
    so there is no argument an attacker could set to reach u-1's data."""
    await save_my_note(SaveNoteInput(text="private"), claims=_claims("u-1"))

    other = await read_my_note(claims=_claims("u-2"))
    assert other["output"]["text"] == ""

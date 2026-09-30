"""The recipe against a fake gateway, and against the checker that polices it.

What is pinned here is the protocol, not the plumbing: the default call names
no provider and no model, it always carries `max_tokens` and the person's
context, every setup state comes back as a sentence, and every bug stays an
exception. The last two tests hold the recipe and `check_app.py` to each
other - the deliberate pin has to pass the rule, and the same code with its
marker stripped has to fail it.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import ai
import check_app
from src.capability import CapabilityError

RECIPE = Path(__file__).resolve().parents[1]
MESSAGES = [{"role": "user", "content": "Summarise: the delivery is late."}]


@pytest.fixture
def gateway(monkeypatch):
    """Replace the one seam that is infrastructure, as the starter's fake_kv does."""
    calls = []
    state = {"answer": {"content": "Late delivery.", "provider": "manaurum"}}

    async def _call(name, payload, *, user_context=None):
        calls.append((name, payload, user_context))
        if isinstance(state["answer"], Exception):
            raise state["answer"]
        return state["answer"]

    monkeypatch.setattr("src.capability.call_capability", _call)

    def answer(value):
        state["answer"] = value

    return calls, answer


def refused(status, detail):
    code = detail.get("error") if isinstance(detail, dict) else detail
    return CapabilityError("refused", status=status, code=code, detail=detail)


async def test_the_default_call_names_no_provider_and_no_model(gateway):
    calls, _ = gateway
    text = await ai.complete(MESSAGES, max_tokens=200, user_context="jwt-u-1")
    assert text == "Late delivery."
    name, payload, user_context = calls[0]
    assert name == "os.ai.complete"
    assert set(payload) == {"messages", "max_tokens"}
    assert user_context == "jwt-u-1"


async def test_max_tokens_cannot_be_forgotten():
    with pytest.raises(TypeError):
        await ai.complete(MESSAGES, user_context="jwt-u-1")      # type: ignore[call-arg]


async def test_private_text_stays_out_of_the_call_log(gateway):
    calls, _ = gateway
    await ai.complete(MESSAGES, max_tokens=50, user_context="j", log_prompt=False)
    assert calls[0][1]["log_prompt"] is False


@pytest.mark.parametrize("status, detail, expected", [
    (403, {"error": "capability_not_granted", "capability": "os.ai.complete"},
     "workspace admin has to allow it"),
    (403, {"error": "ai_disabled", "message": "Text AI is off for this app in Settings"},
     "switched off for this app"),
    (412, {"error": "ai_backend_unavailable",
           "message": "The workspace backend credentials need attention in Settings"},
     "credentials need attention"),
    (403, {"error": "workspace_context_unavailable"}, "not available in this workspace"),
    (429, {"error": "ai_spend_cap", "subject": "user", "window": "day"},
     "today's AI allowance"),
    (429, {"error": "ai_spend_cap", "subject": "tenant", "window": "month"},
     "This workspace has used this month's"),
    (412, {"error": "integration_not_configured", "provider": "anthropic"},
     "your own anthropic key"),
    (412, {"error": "no_ai_provider_configured"}, "your own AI provider key"),
    (502, {"error": "ai_upstream_error", "attempts": [
        {"provider": "manaurum", "reason": "reasoning_only"}]}, "ran out of room"),
    (502, {"error": "ai_upstream_error", "attempts": [
        {"provider": "openai", "reason": "invalid_credential", "status": 401}]},
     "refused the key"),
])
async def test_every_setup_state_is_a_sentence(gateway, status, detail, expected):
    _, answer = gateway
    answer(refused(status, detail))
    with pytest.raises(ai.AIUnavailable) as caught:
        await ai.complete(MESSAGES, max_tokens=50, user_context="j")
    assert expected in caught.value.message
    assert caught.value.status == status
    assert caught.value.retryable is False


@pytest.mark.parametrize("detail", [
    {"error": "ai_upstream_error", "attempts": [{"reason": "upstream_error"}]},
    "anthropic_upstream_error:529",
    "upstream_error:openai",
])
async def test_an_upstream_hiccup_is_worth_retrying(gateway, detail):
    _, answer = gateway
    answer(refused(502, detail))
    with pytest.raises(ai.AIUnavailable) as caught:
        await ai.complete(MESSAGES, max_tokens=50, user_context="j")
    assert caught.value.retryable is True


@pytest.mark.parametrize("status, detail", [
    (412, {"error": "workspace_context_required"}),
    (403, {"error": "workspace_context_mismatch"}),
    (422, {"error": "input_schema_violation"}),
    (403, {"error": "app_installation_required"}),
])
async def test_a_bug_in_the_app_stays_an_exception(gateway, status, detail):
    """Nobody but the author can fix these, so they must not be softened
    into a sentence the person reads and can do nothing about."""
    _, answer = gateway
    answer(refused(status, detail))
    with pytest.raises(CapabilityError):
        await ai.complete(MESSAGES, max_tokens=50, user_context="j")


@pytest.mark.parametrize("output, expected", [
    ({"completion": {"available": True, "selection_source": "managed_default",
                     "display_name": "ManAurum AI"}, "platform_fallback": True},
     {"available": True, "included": True, "label": "ManAurum AI, included"}),
    ({"completion": {"available": True, "selection_source": "workspace_default",
                     "display_name": "Team Claude"}, "platform_fallback": False},
     {"available": True, "included": False, "label": "Team Claude"}),
    ({"completion": {"available": False, "unavailable_reason": "ai_disabled"},
      "platform_fallback": False},
     {"available": False, "included": False, "label": None}),
])
async def test_status_reads_os_ai_providers(gateway, output, expected):
    calls, answer = gateway
    answer(output)
    result = await ai.status(user_context="j")
    assert calls[0][:2] == ("os.ai.providers", {})
    assert {key: result[key] for key in expected} == expected
    assert (result["message"] is None) == result["available"]


async def test_status_when_it_is_not_granted_itself(gateway):
    """`os.ai.providers` is gated too; a status screen must not crash on it."""
    _, answer = gateway
    answer(refused(403, {"error": "capability_not_granted",
                         "capability": "os.ai.providers"}))
    result = await ai.status(user_context="j")
    assert result["available"] is False
    assert "workspace admin" in result["message"]


async def test_the_deliberate_pin_sends_both_fields(gateway):
    calls, _ = gateway
    await ai.complete_with_tenant_key(
        MESSAGES, provider="anthropic", model="claude-sonnet-4-6",
        max_tokens=100, user_context="j")
    payload = calls[0][1]
    assert payload["provider"] == "anthropic"
    assert payload["model"] == "claude-sonnet-4-6"


def _check(directory: Path) -> list:
    problems: list = []
    check_app.check_ai_payloads(directory, problems)
    return problems


def test_the_recipe_passes_the_rule_it_teaches(tmp_path):
    shutil.copy(RECIPE / "ai.py", tmp_path / "ai.py")
    assert _check(tmp_path) == []


def test_without_its_marker_the_pin_is_caught(tmp_path):
    source = (RECIPE / "ai.py").read_text(encoding="utf-8")
    (tmp_path / "ai.py").write_text(source.replace("manaurum:byok", "(unmarked)"),
                                    encoding="utf-8")
    problems = _check(tmp_path)
    assert problems and all("os.ai.complete names `provider`" in p for p in problems)

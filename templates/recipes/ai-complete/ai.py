"""Text AI for a v2 app: the call the platform pays for, and what to say when it can't run.

Copy into `src/ai.py` of an app built on the starter - it uses the starter's
`src/capability.py` - and declare the two capabilities it calls:

    "requires_capabilities": [
      {"name": "os.ai.complete",  "version": "1"},
      {"name": "os.ai.providers", "version": "1"}
    ]

THE CALL TO WRITE IS THE ONE WITH THE FEWEST FIELDS

`complete()` sends `messages` and `max_tokens`, and nothing else. With no
`provider` and no `model`, the workspace's AI answers: the backend the
workspace chose in Settings, or - when it chose none - the managed ManAurum
model, which the platform pays for. Nobody pastes a key, and the app works
on the day it is installed.

Naming a provider or a model moves the call to the tenant's OWN key, and it
is `412` wherever there is none. That is `complete_with_tenant_key()` at the
bottom, kept apart and marked `manaurum:byok` so `check_app.py` lets it
through. Use it only when the person asked for that provider. The SDK's own
reference taught the pinned form as the default until 2.13.0, and an app
built from it told its owner to go and buy a key they never needed.

THREE THINGS THIS FILE DOES THAT A ONE-LINER DOES NOT

1. It forwards the person's user context. The platform reads the workspace
   out of it - whose AI settings apply, whose allowance pays. Without it a
   call works while one workspace has the app installed, and answers
   `412 workspace_context_required` from the day a second one does.
2. It makes `max_tokens` a required argument. The platform reserves each
   call's worst case against the spending allowance before it runs: the
   input at one token per UTF-8 byte, the output at `max_tokens` - or at
   the model's whole ceiling when it is missing. Size it to the answer.
3. It turns setup states into sentences. `capability_not_granted`,
   `ai_disabled`, `ai_spend_cap`, `integration_not_configured` each mean a
   person has to do something. `AIUnavailable.message` is that something,
   in words - render it; never let it become a 500. What is a bug in YOUR
   code (`workspace_context_required`, a field the schema refuses) is not
   caught here, so it stays loud.

In a route:

    @app.post("/api/summary")
    async def summary(request: Request,
                      claims: UserContextClaims = Depends(auth_claims)) -> dict:
        body = await request.json()
        try:
            text = await ai.complete(
                [{"role": "user", "content": body["text"]}],
                max_tokens=400, user_context=claims.token, log_prompt=False,
            )
        except ai.AIUnavailable as exc:
            raise HTTPException(exc.status, detail={
                "error": exc.code, "message": exc.message,
                "retryable": exc.retryable})
        return {"summary": text}

The sentences are English; translate `SETUP_MESSAGES` into your app's
language rather than inventing new ones. The contract behind every code:
`references/capabilities-reference.md`, "Text AI - who pays".
"""
from __future__ import annotations

from typing import Any

from src import capability
from src.capability import CapabilityError

# What to tell a PERSON. Every one is a state somebody can change; the
# codes that mean "the app is wrong" are deliberately absent.
SETUP_MESSAGES = {
    "capability_not_granted":
        "AI is not enabled for this app yet. A workspace admin has to allow it.",
    "ai_disabled":
        "AI is switched off for this app. It can be switched back on in Settings.",
    "ai_backend_unavailable":
        "The workspace's AI is not available right now. An admin can check it "
        "in Settings.",
    "workspace_context_unavailable":
        "AI is not available in this workspace.",
    "integration_not_configured":
        "This feature uses your own {provider} key. Add it in Settings, "
        "under Integrations.",
    "no_ai_provider_configured":
        "This feature uses your own AI provider key. Add one in Settings, "
        "under Integrations.",
    "upstream":
        "The AI service did not answer. Try again in a moment.",
    "invalid_credential":
        "The AI provider refused the key saved in Settings. An admin can "
        "replace it there.",
    "reasoning_only":
        "The AI ran out of room before it answered. Try a shorter request.",
}

SPEND_CAP_MESSAGES = {
    ("user", "day"): "You have used today's AI allowance. It renews at "
                     "midnight UTC.",
    ("user", "month"): "You have used this month's AI allowance.",
    ("tenant", "day"): "This workspace has used today's AI allowance. It "
                       "renews at midnight UTC.",
    ("tenant", "month"): "This workspace has used this month's AI allowance.",
}


class AIUnavailable(Exception):
    """A setup state: somebody has to do something, and `message` says what.

    `message` is for the person, as it is. `code` is the gateway's, for your
    logs and for branching. `retryable` is whether trying the same call again
    later can help - true for an upstream hiccup, false for everything a
    person has to change first.
    """

    def __init__(self, code: str, message: str, *, status: int,
                 retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable


def explain(exc: CapabilityError) -> AIUnavailable | None:
    """The sentence for a refused call, or None when the refusal is a bug."""
    code = exc.code or ""
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    status = exc.status or 502

    if code == "ai_spend_cap":
        window = (detail.get("subject"), detail.get("window"))
        message = SPEND_CAP_MESSAGES.get(window, SPEND_CAP_MESSAGES[("user", "day")])
        return AIUnavailable(code, message, status=status)
    if code == "ai_backend_unavailable":
        # The platform's own sentence names the fix ("the workspace backend
        # credentials need attention in Settings") - better than ours.
        message = detail.get("message") or SETUP_MESSAGES[code]
        return AIUnavailable(code, message, status=status)
    if code == "integration_not_configured":
        provider = str(detail.get("provider") or "AI provider")
        return AIUnavailable(
            code, SETUP_MESSAGES[code].format(provider=provider), status=status)
    if code in SETUP_MESSAGES:
        return AIUnavailable(code, SETUP_MESSAGES[code], status=status)
    if code == "ai_upstream_error":
        reasons = {attempt.get("reason") for attempt in detail.get("attempts") or []}
        for reason in ("invalid_credential", "reasoning_only"):
            if reason in reasons:
                return AIUnavailable(code, SETUP_MESSAGES[reason], status=status)
        return AIUnavailable(code, SETUP_MESSAGES["upstream"], status=status,
                             retryable=True)
    if code.startswith("upstream_error:") or "_upstream_error:" in code:
        # A pinned provider failing: plain strings, not objects.
        return AIUnavailable(code, SETUP_MESSAGES["upstream"], status=status,
                             retryable=True)
    return None


async def complete(
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    user_context: str | None,
    temperature: float | None = None,
    log_prompt: bool = True,
) -> str:
    """Ask the workspace's AI. Returns the answer's text.

    `user_context` is `claims.token` in a route or an `/agent/*` handler.
    `None` only for a call no person is behind - and then the platform can
    tell which workspace is meant only while exactly one has the app.

    `log_prompt=False` keeps the text and the answer out of the platform's
    call log (tokens and cost are still recorded). Pass it for anything the
    person wrote for themselves.
    """
    payload: dict[str, Any] = {"messages": messages, "max_tokens": max_tokens}
    if temperature is not None:
        payload["temperature"] = temperature
    if not log_prompt:
        payload["log_prompt"] = False
    try:
        output = await capability.call_capability(
            "os.ai.complete", payload, user_context=user_context)
    except CapabilityError as exc:
        unavailable = explain(exc)
        if unavailable is None:
            raise
        raise unavailable from exc
    return output["content"]


async def status(*, user_context: str | None) -> dict[str, Any]:
    """What `complete()` would use right now - for a settings or empty screen.

    Spends nothing. Returns `{"available", "included", "label", "message"}`:
    `included` is true when the platform pays; `message` is the sentence to
    show when `available` is false. Advisory only - the call right after can
    still meet the spending allowance.
    """
    try:
        output = await capability.call_capability(
            "os.ai.providers", {}, user_context=user_context)
    except CapabilityError as exc:
        unavailable = explain(exc)
        if unavailable is None:
            raise
        return {"available": False, "included": False, "label": None,
                "message": unavailable.message}
    completion = output.get("completion") or {}
    if completion.get("available"):
        included = bool(output.get("platform_fallback"))
        label = ("ManAurum AI, included" if included
                 else completion.get("display_name") or "Your workspace's AI")
        return {"available": True, "included": included, "label": label,
                "message": None}
    reason = completion.get("unavailable_reason") or "ai_backend_unavailable"
    return {"available": False, "included": False, "label": None,
            "message": SETUP_MESSAGES.get(reason, SETUP_MESSAGES["ai_backend_unavailable"])}


async def complete_with_tenant_key(
    messages: list[dict[str, str]],
    *,
    provider: str,
    model: str,
    max_tokens: int,
    user_context: str | None,
) -> str:
    """The deliberate opt-out: this provider, this model, the tenant's key.

    Only when the person asked for this provider - "use my Claude key" - and
    never as the default. It fails `412 integration_not_configured` for any
    tenant with no key for `provider`, which `explain()` turns into "add your
    key in Settings". The platform never falls back to its own model here,
    and the workspace's AI never falls back to this: a failure does not
    change who pays.
    """
    payload: dict[str, Any] = {"messages": messages, "max_tokens": max_tokens}
    payload["provider"] = provider  # manaurum:byok - the person chose this provider
    payload["model"] = model        # manaurum:byok
    try:
        output = await capability.call_capability(
            "os.ai.complete", payload, user_context=user_context)
    except CapabilityError as exc:
        unavailable = explain(exc)
        if unavailable is None:
            raise
        raise unavailable from exc
    return output["content"]

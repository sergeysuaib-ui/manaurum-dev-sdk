"""OS-Assistant agent capabilities — one handler per manifest entry.

WHY THIS FILE EXISTS AT ALL: an app that declares no `agent_capabilities`
is invisible to the OS Assistant. The Assistant does not then say "I
can't see that app" — it answers from guesswork, so the user gets
confident statements about data nothing ever read. Declaring at least one
capability is what makes an app part of the platform rather than a page
inside it.

DISPATCH. The agent runtime mints a 60s `user_context` JWT — the same
token, same key, same header the gateway puts on your `auth: "user"`
routes — and POSTs it **straight to this container** at
`/agent/<name>`, with the validated tool arguments as the JSON body.

Two consequences that trip people up:

* `/agent/<name>` is NOT a gateway route and must NOT appear in
  `manifest.runtime.api_routes` — declaring it there does nothing. But
  that removes the GATEWAY, not the network: `<slug>.apps.manaurum.com`
  is Traefik straight to this container, so anyone on the internet can
  POST `/agent/<name>`. The `Depends(auth_claims)` below is the only
  thing stopping them. Never omit it "because only the runtime calls
  this".
* A valid user_context JWT is AUTHENTICATION, not AUTHORIZATION. The
  runtime will mint one for any user who has the app installed. So every
  handler still runs its own in-container access check — exactly the
  same one the equivalent `/api/*` route runs. This starter is
  single-user-scoped (keys are namespaced by `claims.user_id`), so the
  scoping IS the guard; an app with shared objects must check membership.

REPLY CONTRACT: `{"ok": true, "output": <any>}` on success,
`{"ok": false, "error": "<short>"}` on failure — a failed tool call the
model can read and react to, not a 500.

Handlers hold NO LLM. The model already decided what to call; this file
just does it, safely.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.auth import UserContextClaims, auth_claims
from src.capability import CapabilityError, read_note, write_note

router = APIRouter(prefix="/agent", tags=["agent"])


def _ok(output) -> dict:
    return {"ok": True, "output": output}


def _fail(error: str) -> dict:
    return {"ok": False, "error": error[:300]}


class SaveNoteInput(BaseModel):
    """Mirrors the manifest's `input_schema`.

    The runtime already validates the model's arguments against that
    schema, but re-validate here anyway: the schema is a contract you
    published, not a guarantee about the process on the other end.
    """

    text: str = Field(min_length=1, max_length=10_000)


@router.post("/read_my_note")
async def read_my_note(claims: UserContextClaims = Depends(auth_claims)) -> dict:
    """No input — the caller's identity comes from the JWT, never the body.

    A capability that took a `user_id` argument would let the model read
    somebody else's note by passing a different one. Identity is not an
    argument.
    """
    try:
        return _ok({"text": await read_note(claims.user_id)})
    except CapabilityError as exc:
        return _fail(str(exc))


@router.post("/save_my_note")
async def save_my_note(
    data: SaveNoteInput,
    claims: UserContextClaims = Depends(auth_claims),
) -> dict:
    try:
        return _ok({"text": await write_note(claims.user_id, data.text)})
    except CapabilityError as exc:
        return _fail(str(exc))

# my-app

A Manaurum Platform v2 app. It deploys green as-is — build on top of a
working app rather than debugging an empty one.

```bash
manaurum app validate
manaurum app deploy
curl https://my-app.apps.manaurum.com/healthz    # {"status":"ok",...}
```

Then open it from your Manaurum desktop. You should see your user id
and a note box that survives a reload.

## What you got

```
my-app/
├── manifest.json        # what the platform is allowed to do for you
├── Dockerfile           # python:3.12-slim + uvicorn on :8000
├── .dockerignore        # keeps .env, tests and friends out of the image
├── requirements.txt     # pinned runtime deps
├── requirements-dev.txt # pytest — not installed into the image
├── pytest.ini
├── src/
│   ├── auth.py          # verify the gateway's user_context JWT
│   ├── capability.py    # call the capability gateway (os.kv here)
│   ├── main.py          # /healthz, /api/me, /api/notes, static serving
│   ├── agent_routes.py  # /agent/* — the OS Assistant surface
│   └── static/
│       └── index.html   # the UI, incl. the manaurum:ready handshake
└── tests/
    ├── conftest.py      # the user_context JWT fixture + a fake os.kv
    ├── test_auth.py     # the verifier, incl. every way it can be wrong
    ├── test_agent.py    # the handlers: identity comes from claims, never the body
    └── test_routes.py   # the wiring: real HTTP, so an open route fails a test
```

There is no `migrations/` directory: this starter persists through `os.kv`
(see § Storage), and the platform rejects a non-`.sql` file sitting in
`migrations/`, so there is no placeholder that could hold the folder open.
Create it when you have your first `.sql` file and not before.

`auth.py` and `capability.py` are shared infrastructure; `main.py` and
`agent_routes.py` are the two surfaces built on them. Apps grow by adding
surfaces over that same thin core, not by growing one file.

## Run the tests first

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest                      # 19 passed
```

They need no database, no Manaurum account and no network: `conftest.py`
generates a throwaway RSA keypair and signs its own `user_context` tokens,
so the auth path is testable offline. Break something on purpose and watch
them fail — that is the fastest way to learn the contract.

Try these three, because each one is a way a real v2 app has shipped broken:
make `note_key()` return a constant, drop `Depends(auth_claims)` from an
`/agent/*` handler, drop it from a route in `main.py`. All three go red.
That last pair is why `test_routes.py` exists at all: unit-testing the
verifier and unit-testing the handler both stay green when the two are no
longer wired together, and the route is open in production.

## The five things that make it work

**1. The port is a contract between two files.** The gateway proxies to
`manifest.runtime.port` (80 when the field is absent). `EXPOSE` in the
Dockerfile is documentation — the platform never parses it. So the
Dockerfile's `CMD` port and `runtime.port` must agree or every request
502s `upstream_unreachable`. This starter uses **8000** in both, like
every hosted v2 app in production; 8000 is unprivileged, so the
container's non-root user can always bind it.

**2. `runtime.api_routes` is default-deny.** A `/api/*` path missing
from that list returns 404 `route_not_declared` at the gateway and
never reaches your code. Add a route in `src/main.py` → add it to
`manifest.json`. Non-API paths (`/`, `/healthz`, assets) are always
anonymous and are never declared.

**3. The `manaurum:ready` handshake.** The desktop shell frames your app
and waits 10 seconds for a `manaurum:ready` reply. No reply → the user
sees *"App is not responding"* instead of your UI. `index.html` answers
it inline, before loading anything else, so a slow CDN cannot cost you
the window. **This is invisible on the standalone URL** — always check
the app inside the Manaurum desktop before calling a deploy good.

**4. Identity comes from a header, not a token.** On an `auth: "user"`
route the gateway mints a 60-second RS256 JWT and injects it as
`X-Manaurum-User-Context`. Your container verifies it against
`CORE_USER_CONTEXT_PUBLIC_KEY_PEM` (see `verify_user_context()` in
`src/auth.py`). The end user's own bearer never reaches you.

**5. `agent_capabilities` is what makes the app part of the OS.** The two
entries in `manifest.json` are served by `src/agent_routes.py` and let the
OS Assistant read and write your note on the user's behalf. Declare none
and the Assistant cannot see the app at all — and rather than saying so it
will answer from guesswork. Dispatch goes **straight to the container** at
`POST /agent/<name>`, so those paths must **not** be listed in
`runtime.api_routes`. That skips the *gateway*, not the network — the path is
still served on your public hostname, so the JWT check in every handler is the
only thing protecting it. And a valid JWT is authentication, not
authorization: every handler still scopes to `claims.user_id`.

## Storage

This starter declares `data: {"none": true}` — no managed Postgres
schema, no `DATABASE_URL`, and the deploy needs no DDL-capable DSN on
Core. It persists through the `os.kv` capability instead, which is why
there is no `migrations/` directory at all.

Want a real per-tenant schema? Delete the `data` block, create
`migrations/` and put additive-only SQL in it (`.sql` files only — any
other file directly inside that directory fails the deploy), set
`migrate_command` in the manifest, and connect with `DATABASE_URL` (the
platform sets the `search_path` to your tenant's schema for you).
Validate before you push:

```bash
manaurum app validate-migration migrations/0001_init.sql
```

## Calling capabilities

Server-side only, through one door:

```
POST {MANAURUM_CORE_URL}/api/capability/<name>
Authorization: Bearer {MANAURUM_RUNTIME_TOKEN}
X-Manaurum-Tenant-Id: {MANAURUM_TENANT_ID}
X-Manaurum-App-Id:    UUID for os.kv.* and os.events.emit, slug otherwise
```

Every one of those values is injected into the container at deploy —
never bake a credential into the image. `MANAURUM_APP_ID` is already
the UUID, which is what `call_capability()` in `src/capability.py` sends.

Add a capability by listing it in `requires_capabilities` and
redeploying; a tenant admin then grants it on the install. Until they
do, calls return 403 `capability_not_granted`.

## Notes

- `app_id` is `my-app`. It is globally unique and cannot be changed
  after the first deploy.
- `version` is strict semver and must increase on every deploy.
- The manifest schema is published at
  <https://manaurum.com/sdk/manifest_v2.schema.json>; `manaurum app
  validate` checks against the same copy.
- The client SDK is <https://manaurum.com/sdk/manaurum-v2.mjs> —
  `app.fetch()` and `app.device`. It is optional: `index.html` falls
  back to plain `fetch()` if it cannot load.

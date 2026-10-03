# Platform v2 reference

Long-form companion to `manaurum-app/SKILL.md`. Covers:

1. Manifest v2 — every field, with examples
2. Runtime modes (`hosted`, `byo`, `dev`)
3. Capabilities — gateway contract, error codes, headers
4. Tokens (`mna_*`) — issuance, scope, revocation
5. Deploy lifecycle (build → push → swarm → traefik)
6. Rollback + version history
7. Migrations + dedicated app schemas
8. Visibility + App Store v2

The canonical JSON Schema lives at `https://manaurum.com/sdk/manifest_v2.schema.json` (and the source at `docs/standards/manifest_v2.schema.json` in the manaurum repo). Validate locally with `jsonschema` if you want fast feedback before the deploy round-trip.

---

## 1. Manifest v2 — full field reference

The manifest is one JSON object. Top-level required fields: `manifest_version`, `manaurum_sdk_version`, `app_id`, `name`, `version`, `runtime`. Everything else is optional.

> **The root object is strict.** `"additionalProperties": false` at the top level — the 23 keys below are the complete set. Anything else fails manifest validation; there is no forward-compatible ignore. In particular `description`, `icon` and `category` are **not** root keys: they live at `metadata.description`, `frontend.icon` and `metadata.category`.
>
> `runtime` is strict too (MAN-1899): a key outside the eleven in § 2 is a `422`. So are `data`, `offline`, and each entry of `agent_capabilities`, `webhooks` and `schedules`. The other objects (`frontend`, `platforms`, `visibility`, `migration`, `metadata`, …) accept keys they do not declare, which is how a typo there passes and does nothing.

```json
{
  "manifest_version":     "2",
  "manaurum_sdk_version": "2",
  "app_id":               "my-app",
  "name":                 "My App",
  "version":              "1.0.0",
  "runtime": {
    "mode":                  "hosted",
    "port":                  8000,
    "api_routes": [
      { "path": "/api/items/*",     "auth": "user" },
      { "path": "/api/kiosk/today", "auth": "anonymous" }
    ],
    "egress_allowed_hosts":  ["api.openai.com", "api.stripe.com"]
  },
  "frontend": {
    "entry_point": "/index.html",
    "icon":        "🧾"
  },
  "visibility": {
    "mode":    "public",
    "tenants": []
  },
  "requires_capabilities": [
    { "name": "os.kv.get",     "version": "1" },
    { "name": "os.files.upload","version": "1" }
  ],
  "permissions": ["microphone"],
  "migration": {
    "breaking":          false,
    "reason":            "add invoice.line_items table",
    "rollback_strategy": "drop new table"
  },
  "metadata": {
    "category":      "productivity",
    "tags":          ["invoicing"],
    "description":   "Short description shown in the App Store.",
    "homepage":      "https://example.com",
    "support_email": "dev@example.com"
  }
}
```

That example omits `data`, so it gets the default **managed** Postgres schema (which is what the `migration` block implies). A stateless app that persists only through `os.kv` / `os.files` must say `"data": {"none": true}` — see the table below.

Validate before every deploy — `manaurum app validate` uses a byte-identical copy of the backend schema, so it is a true pre-flight.

### Required fields

| Field | Type | Notes |
|---|---|---|
| `manifest_version` | string `"2"` | Pinned. |
| `manaurum_sdk_version` | string `"2"` | Pinned. |
| `app_id` | string | Your slug: the DNS label (`<app_id>.apps.manaurum.com`), the Swarm service name and the Postgres schema name. The deploy refuses anything but 3–40 chars of `a-z`, `0-9` and `-`, starting with a letter and not ending with `-` (`422 app_id_invalid`), anything shaped like a UUID, and the reserved names `app`, `apps`, `www`, `landing`, `staging`, `mcp`, `api`, `registry`, `library`, `turn`, `burgerlab`, `wildcard-anchor`, `dokploy`, `traefik` (`422 manifest_validation_failed`). |
| `name` | string | Human-readable. Used in App Store + windowing. |
| `version` | string | Semver `MAJOR.MINOR.PATCH`. Bump on every redeploy. No pre-release / build metadata. |
| `runtime` | object | See § 2. |

### Optional top-level

These 17 keys plus the 6 required ones are the complete root surface. Anything else is a validation failure.

| Field | Type | Notes |
|---|---|---|
| `data` | object | Storage mode. **Omit it and you get managed mode**, which provisions a Postgres schema + login role per (app, tenant) and needs `MANAURUM_DDL_DSN` on Core — a deploy that fails at `swarm_applying` if it isn't set. A stateless app (persists only via `os.kv` / `os.files`) must declare `{"none": true}`. Other modes: `{"byo": true}` (your own DSN, no isolation guarantees). `{"shared": true}` and `connection_cap` are accepted and do nothing today: `shared` provisions exactly what managed mode does (one schema per app and tenant), and nothing reads `connection_cap`: your container connects with its own DSN, so its pool is whatever your driver opens. `extensions` requests Postgres extensions (`vector`, `pg_trgm` only); each needs a platform operator's approval, and until it has one the deploy goes on without it and a migration that uses the type fails. `additionalProperties: false` on this sub-object. |
| `frontend` | object | `entry_point` (the URL the desktop shell loads in the app's window — normally `/index.html`; without it your app has a live URL but no desktop window, and declaring it is what makes the `manaurum:ready` handshake apply to you), `icon`, `bundle_path`, `window: {default_width, default_height}`. `frontend.icon` is an unconstrained string: an emoji works (Libi ships `"🍼"`), so does an absolute URL or `/api/catalog/media/...` path. A **relative** path (`icons/app.svg`) is painted as literal text in the tile. Omit it entirely and the launcher serves a generic placeholder. |
| `visibility` | object | `mode: "private" \| "public" \| "allow_list"`, optional `tenants: [uuid…]`. Default `private`. |
| `platforms` | object | `desktop: {supported}` and `mobile: {supported, optimized, entrypoint, supportLevel, navigationPattern}`. Declare both explicitly. On a phone, `mobile.supportLevel: "none"` blocks the app and a missing level shows it with a "best on desktop" banner. `platforms.mobile.entrypoint` is read only for v1 manifests: a hosted v2 app always loads its own `https://<app_id>.apps.manaurum.com/` on mobile too (a `byo` app loads `runtime.entrypoint`). |
| `requires_capabilities` | array | `[{name, version, quota_per_tenant_per_day?}]` — the capabilities your app cannot work without. |
| `optional_capabilities` | array | Same shape as `requires_capabilities`, for capabilities you use if granted but don't require. App Store v2 reads this to compute the optional grant set the tenant admin sees at install time. |
| `agent_capabilities` | array | Tools this app exposes to the **OS Assistant** — see the subsection below. Each entry `{name, description, input_schema, …}`; `name` is snake_case `^[a-z][a-z0-9_]*$`. **Slug length plus name length must be at most 57** (the Assistant names the tool `sdk__<slug>__<name>`, capped at 64): a longer one deploys green and the tool silently never appears. A tool whose name starts with a write verb (`add_`, `create_`, `save_`, `update_`, `delete_`, `set_`, …) and declares `"is_write": false` is refused at deploy (MAN-2358). |
| `provides` | object | Inter-app contracts you expose: `{rpc: [...], events: [...]}`. Informational today: `os.apps.call` reaches only built-in apps, so no other app can call a method you list here. |
| `consumes` | object | Inter-app contracts you depend on: `{rpc: [...], events: [...]}`. Nothing reads it today: listing an event here subscribes you to nothing, because no hosted app can receive events (MAN-133). |
| `webhooks` | array | `[{name, path, signature}]`. **Validated for shape; Core does nothing with it in v2.x** — the platform webhook gateway is deferred. Expose your own handler via `runtime.api_routes` with `auth: "anonymous"` and verify the signature yourself. |
| `schedules` | array | `[{name, cron, handler_path, timezone?}]`. **Validated for shape; Core does not invoke the handler in v2.x** — platform cron is deferred. Run an in-container scheduler and keep the declaration as documentation of intent. |
| `tenant_config` | object | `{schema, required_at_install}` — per-tenant config collected at install time. Note: install-time values land in `v2_app_installs.config`, which the `os.tenant_config.get` capability does **not** currently read. Don't build on the round-trip yet. |
| `offline` | object | Manaurum Edge declaration: `features`, `reference_data`, `streams`. **It does nothing for a v2 hosted app today:** the on-site box's configuration is built from v1 apps only. (The shell still copies the block into `manaurum:init`.) |
| `permissions` | string[] | BROWSER features the OS shell delegates to the app iframe via the `allow` attribute (Permissions-Policy). Enum today: `microphone` (MAN-1316) and `camera` (MAN-1920); `uniqueItems`. Required for a LIVE `getUserMedia` stream inside the shell iframe — without it `getUserMedia` is blocked in the iframe, while your standalone `<app_id>.apps.manaurum.com` URL is unaffected. A still photo through `<input type="file" accept="image/*" capture="environment">` hands off to the device's camera app, is not gated and needs no declaration, so declare `camera` only for a stream you decode or render yourself (a barcode scanner, video capture). The user still sees the browser's own prompt. Refused when `runtime.mode` is `byo` (MAN-1922), and the shell delegates nothing to a frame whose address the manifest chose. Unrelated to `requires_capabilities` — a voice app needs both this AND `os.ai.transcribe`. |
| `migrate_command` | string[] | In the schema, but **Core never executes it** — there is no call site (`production.py:49-52`, "reserved"). An app whose schema depends on it deploys green with no tables. Use `migrations/*.sql` instead — see § 7. |
| `migration` | object | `{breaking, reason, rollback_strategy}`. `breaking: true` lets the DDL validator through *destructive* statements (and only those — see § 7). Default `false`. |
| `metadata` | object | App Store rendering: `category`, `tags`, `description`, `homepage`, `support_email`, `source_url`. **This is where a root-level `description` belongs.** |

Grant enforcement applies to every capability call from an app with an install row in the calling tenant (every deployed hosted app, in its own tenant): the call is checked against the install's `granted_capabilities` before dispatch and audit. An app id with no install row there skips the check today (MAN-2199). A capability absent from the list — **or an install whose list is empty** — is `403 capability_not_granted`. There is no wildcard grant (MAN-1585). Only dev-mode apps and active BYO hosts short-circuit the check. Operational consequence: adding a capability to your manifest and redeploying is **not** enough — the tenant's install grant set has to be extended too, or every call 403s.

### `agent_capabilities[]` — expose your app to the OS Assistant

Each entry registers one tool the OS Assistant can call on the user's behalf. On deploy, Core upserts one `agent_capabilities` row per entry; at request time the agent runtime builds a tool per row (for apps the user has installed) and dispatches **server-to-server** — `POST http://<container>/agent/<name>` with the tool arguments as the JSON body and a freshly minted `user_context` JWT in `X-Manaurum-User-Context`, the same header and the same key your `auth: "user"` routes already verify. Reply `{"ok": true, "output": …}` (a bare JSON object also works; `{"ok": false, "error": …}` surfaces as a failed tool call).

This dispatch goes **straight to your container**, not through the gateway — so `/agent/<name>` does **not** need a `runtime.api_routes` entry, and declaring one there does nothing.

> ⚠️ **Verify the JWT in every `/agent/*` handler, and bind it.** On your public hostname the gateway refuses `/agent/*` (`404 route_not_declared`, MAN-1432 — before 2026-07-27 it did not). But every app's container sits on one network, so another app's container can call yours directly, and the token it presents may be one minted for some other app. The check in `templates/v2-starter/src/auth.py` — signature, then `app_id` and `tenant_id` — is what stands between that container and your data.

**Declare at least one.** An app with no `agent_capabilities` is invisible to the Assistant — and the Assistant does not say "I can't see that app", it *guesses*, so the user gets confident answers about data it never read. This is the platform's differentiator; treat the field as required, not optional.

#### The manifest entry

The three required keys are `name`, `description`, `input_schema`. What separates a usable tool from a decorative one is the `description`, which is **prompt text for a model, not documentation for a human** — say what the capability does, when to reach for it, and when not to. Hard cap 400 chars (`manifest_v2.schema.json`, matching the runtime's `Tool` validator, `app/agent/types.py:117`); longer is rejected at deploy.

```json
"agent_capabilities": [
  {
    "name": "create_family_space_item",
    "description": "Create an Item (task/doc/note/event/contact) in a specific Space. Use for household to-dos, documents, events and contacts the family shares. Resolve the target Space with list_family_spaces first — do NOT guess a space_id. For dated tasks pass deadline_at; for events pass event_date. Not for personal reminders unrelated to a Space.",
    "input_schema": {
      "type": "object",
      "properties": {
        "space_id": {"type": "string", "description": "Target Space UUID (from list_family_spaces)."},
        "kind": {"type": "string", "enum": ["task", "doc", "note", "event", "contact"]},
        "title": {"type": "string", "description": "Short title (<=200 chars)."},
        "deadline_at": {"type": "string", "format": "date-time", "description": "ISO-8601, for kind=task."}
      },
      "required": ["space_id", "kind", "title"],
      "additionalProperties": false
    },
    "is_write": true,
    "routing_hints": ["family", "add task", "create", "добавь"],
    "example": {"space_id": "…", "kind": "task", "title": "Book the vet"}
  }
]
```

Note the shape of that description: a positive trigger ("use for household to-dos…"), an ordering constraint ("resolve the Space first — do NOT guess"), and a negative ("not for personal reminders"). A description like *"Creates an item."* parses fine and routes badly.

`routing_hints` are informational: today nothing matches against them. `example` is surfaced to the model as a usage hint. The model picks a tool by its `name`, `description` and `input_schema`, so **write the `description` with the words your user actually uses**, in their language as well as English: an app whose people type «сколько осталось» should say so in the description.

**Shape a write's input for the approval card.** A write pauses on a card the user approves first. The card names the call by the record's id and title and shows the arguments, at most 10 keys per level. So an update takes **only the fields that change** (omitted means unchanged), the record's id is a **required, top-level** key named after the tool's noun (`update_order` → `order_id`), and every key is declared in `properties`.

**Timeouts and retries.** The Assistant waits **30 seconds** for your handler, then reports the call as failed — but your handler keeps running. It does not pass you an idempotency key. So a write that can take longer than that must be idempotent on its own inputs (an upsert keyed by something in the request), or the user's retry writes twice. What the model sees of a failure is short: `{"ok": false, "error": …}` passes the first 300 characters of `error`, a non-2xx response the first 200 of its body, and the whole message is capped at 400.

> **`is_write` is load-bearing, and omitting it is not the same as `false`.** Since MAN-1425/MAN-1872 (merged 2026-08-21) the manifest value is persisted on `agent_capabilities` and read at request time — but the column is nullable and **NULL is not `false`**: a capability that omits the key falls back to the dispatch-derived value, and every v2 hosted app dispatches `backend`, which means `is_write=True`. So a reader that says nothing is treated as a mutation — journalled as an AgentAction row, gated by the confirmation flow, deduped for idempotency, and excluded from cross-app insight (which filters on `not is_write`). **Write `"is_write": false` explicitly on every read-only capability.** The fallback errs toward "write" on purpose: over-protecting a reader beats letting a mutation through unannounced.

#### The handler side

`/agent/<name>` is dispatched **straight to your container** and is *not* a gateway route, so it needs no `runtime.api_routes` entry. Serve it with the same JWT verification your `auth: "user"` routes use (see the warning above):

```python
# src/agent_routes.py — one router, one handler per manifest entry.
router = APIRouter(prefix="/agent", tags=["agent"])

def _ok(output):     return {"ok": True, "output": output}
def _fail(error):    return {"ok": False, "error": error[:300]}

class CreateItemInput(BaseModel):          # mirrors input_schema; the runtime
    space_id: str                          # validates against the manifest, but
    kind: str                              # re-validate here — never trust shape.
    title: str = Field(min_length=1, max_length=500)

@router.post("/create_family_space_item")
async def create_item(
    data: CreateItemInput,
    claims: UserContextClaims = Depends(auth_claims),   # same verifier as /api/*
    db: asyncpg.Connection = Depends(get_db),
):
    # A valid user_context JWT is AUTHENTICATION, not AUTHORIZATION. The
    # runtime will happily mint one for any installed user, so every
    # handler still runs its own in-container access guard.
    await assert_membership(db, data.space_id, claims.user_id)
    ...
    return _ok({"id": str(new_id)})
```

Then mount it — `app.include_router(agent_routes.router)` — and remember the handlers hold no LLM: they are plain reads and writes over your own data. The model already decided what to call; your job is to do it safely.

Full contract: `docs/handoff/AGENT_TOOLS_INTEGRATION.md` (Path C) in the manaurum repo. Working example: `family-space-v2/src/agent_routes.py` — see `references/reference-apps.md`.

---

## 2. Runtime modes

```json
"runtime": {
  "mode": "hosted" | "byo" | "dev",
  "port": 8000,
  "api_routes": [ { "path": "/api/items/*", "auth": "user" } ],
  "public_paths": [ "/g/*" ],
  "health_path": "/healthz",
  "egress_allowed_hosts": [...]
}
```

`runtime` is **strict** (`additionalProperties: false`, since MAN-1899 on 2026-08-23): a key outside the eleven below is a `422` at deploy, and `templates/check_app.py` says so before you upload.

| Key | Read by |
|---|---|
| `mode`, `port`, `api_routes`, `public_paths` | the gateway |
| `health_path` | the readiness probe after a deploy |
| `egress_allowed_hosts` | the deploy pipeline and `os.http.fetch` |
| `resources` | Swarm, as the container's limits |
| `sandbox` | the shell (see below — leave it out) |
| `entrypoint` | the shell, for `mode: "byo"` only |
| `replicas`, `image` | nothing. Accepted so old manifests keep deploying: the replica count is the operator's, and the image tag is derived from (registry, `app_id`, `version`). |

Leave `runtime.sandbox` alone. Its enum is the default triple (`allow-scripts allow-forms allow-same-origin`), and the shell keeps only what you declare, so declaring it can only take tokens away — `["allow-forms"]` costs you `allow-scripts` and the app renders blank.

### `runtime.port`

The port your container listens on. **Default 80.** The Core gateway resolves the upstream as `<swarm-service>:<port>` where `port` is `runtime.port` if present and 80 otherwise, and the post-deploy probe dials the same port. Nothing in Core parses your Dockerfile's `EXPOSE` line — it is documentation only. An integer from 1 to 65535; `libi/manifest.json` ships `"port": 8000`.

Two ways to get it wrong, and both produce the same symptom — a deploy that fails its readiness probe and is rolled back (`readiness_failed`), because the platform probes exactly that port:

- **Wrong or missing `runtime.port`.** If your framework listens on 8000 and your manifest says nothing, the gateway dials port 80 and finds nobody. Either bind 80, or declare the port you actually use.
- **Bound to `127.0.0.1`.** Many frameworks default to loopback, which is unreachable from outside the container. Bind `0.0.0.0` explicitly — `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]`, with `"port": 8000` in the manifest to match. `app.listen(80)` in Node binds all interfaces by default, but `app.listen(80, 'localhost')` does not.

Traffic path: `https://<slug>.apps.manaurum.com` → Traefik → **Core backend** (which adds the `/apps/<slug>` prefix) → Core gateway → your container. Traefik never talks to your container directly, so publishing ports in the Dockerfile changes nothing.

### `runtime.public_paths`

Pages a browser tab may open **without a session**. Without the key every page is private: a top-level navigation by someone not signed in is redirected to the Manaurum login and comes back afterwards. Same glob syntax as `api_routes.path`, with the same trap — `/*` does not match `/`, so a fully public app declares `["/", "/*"]`.

It covers document navigations only. It never touches `api_routes`, and it never says who is asking: a member who opens a public page reaches your container exactly as a guest does, with no `user_context`. See "Pages that guests and members both open" below.

### `runtime.health_path`

The path the platform polls after a deploy, straight to your container at `runtime.port` over the internal network. It needs no `api_routes` entry, and like every non-`/api` path it is also served publicly through the gateway, so keep it free of anything secret. Declared, it is strict: a `5xx` on it fails the deploy. Left out, the probe only needs something to answer HTTP on the port. Either way a container that never answers is rolled back to the previous version and the deploy is reported failed.

### What else the gateway answers

Besides `404 route_not_declared`, a request can come back from the gateway, not your container:

| HTTP | `detail` | When |
|---|---|---|
| 404 | `app_not_found` | No such app; or it is not serving; or the caller is signed in to another tenant (on `auth: "user"` routes). |
| 503 | `app_disabled` | The app was switched off (`/api/*` gets this code; a page gets an HTML 503). |
| 400 | `path_traversal_rejected` | The path contains a `..` or `.` segment, or an encoding of one. |
| 502 | `upstream_unreachable` | Nothing answered on your container's port (it crashed, or is restarting). |
| 504 | `upstream_timeout` | Your container took longer than **30 s** to answer a non-streaming route. Long work goes in a background job the page polls, or on a `streaming: true` route. |

Core answers `POST /__manaurum/runtime-errors` on your hostname; do not serve that path.

**Don't set your own framing headers.** Core force-assigns the CSP `frame-ancestors` and deletes `X-Frame-Options` on every `/apps/*` response, so setting either is pointless. On a page it serves (a `GET` answered `200 text/html`) it also rewrites `script-src` / `script-src-elem` (adding a nonce for the session-renewal script it injects) and `frame-src`, in headers and `<meta>` tags alike, and serves it with `Cache-Control: no-store`. Everything else in your CSP is kept, so a `connect-src 'self'` that forgets your API origin will still break your app inside the shell.

**Don't write to host paths.** Volumes aren't mounted into v2 apps. Use `os.files.upload` (R2) for any persistent files.

**Your container may be made read-only.** Off by default, a platform operator can switch an app to a hardened runtime, applied from its next deploy: a read-only root filesystem, uid 10001 whatever your image's `USER` says, no Linux capabilities, and only `/tmp` writable (a 128 MiB tmpfs counted against your memory; `HOME` points inside it). Write temporary files under `/tmp`, and anything that must last through `os.files` or your database, and the switch will not break you.

### `runtime.resources`

`{"memory_mb": 64–2048, "cpu_millicores": 50–2000}`, default 512 MiB and 500 millicores. A value above the ceiling is a `422`, not a quiet clamp. Over its memory the container is OOM-killed and restarted; over its CPU it is throttled.

### `runtime.api_routes` — default-deny

The declaration table for every `/api/*` path your container serves. **A path that is not declared returns `404 route_not_declared` from the gateway and never reaches your container** — the app just looks broken.

| Key | Notes |
|---|---|
| `path` | Required. Must start with `/`. Trailing `*` is a wildcard (`/api/orders/*`); anything else is an exact match. `/api/tasks/*` does **not** match the bare `/api/tasks` — declare both if you serve both. |
| `auth` | Required: `"user"`, `"anonymous"` or `"optional"`. `user`: the gateway mints a 60s RS256 `user_context` JWT and injects it as `X-Manaurum-User-Context`; the end user's own bearer token is **never** forwarded. `anonymous`: proxied with no user context (kiosk / public endpoints — explicit declaration required, there is no implicit anonymous fallback). `optional` (Core MAN-3200): a signed-in member of your tenant as on `user`, plus `X-Manaurum-Person`; anyone else as on `anonymous`, never a `401` — see "Pages that guests and members both open". |
| `streaming` | Optional bool, default false. Proxy in SSE / chunked passthrough mode instead of buffering the upstream response. Orthogonal to `auth`. Emit SSE heartbeats, honour `Last-Event-ID`, and do not hold a DB connection for the stream's lifetime. Limits below. |

There is no `method` field — one rule covers every verb, so you cannot declare `/api/items` anonymous for reads and `user` for writes: enforce that inside your app. Precedence: the longer literal prefix wins, ties break by declaration order. That lets you carve one path out of a wildcard — `{"path": "/api/orders/*", "auth": "user"}` plus `{"path": "/api/orders/public", "auth": "anonymous"}` does what it looks like. Adding a route to your code is not enough: a new endpoint needs a new manifest entry and a redeploy, and until then it 404s while your logs stay silent, because nothing reached you. Static assets (HTML/JS/CSS, `/healthz`) are **not** declared here; they always reach your container anonymously, and a page navigation without a session is sent to log in unless `runtime.public_paths` lists it.

The gateway strips `Cookie` and `Authorization` from every request it proxies, `/api/*` or not. Since MAN-3214 it also drops every header through which Core asserts who is calling: `X-Manaurum-User-Context`, `X-Manaurum-Person`, and the system-call headers (`X-Manaurum-Caller-System`, `-Tenant-Id`, `-Workspace-Id`, `-App-Id`, `-Event-Id`, `-Source-App-Id`, `-Subscriber-App-Id`), whatever the route's `auth`, on pages and streams alike. Through the gateway, the only `X-Manaurum-User-Context` your container sees is one the gateway minted for a signed-in caller. Whatever identity you need arrives as that header, or in a header of your own, which carries whatever the client put in it.

**Verifying `X-Manaurum-User-Context`, all of it.** Check, in this order:

1. The signature: RS256 against `CORE_USER_CONTEXT_PUBLIC_KEY_PEM`, issuer `manaurum-core`, audience `manaurum-app`, `exp` and `iat` present and `exp` in the future. A missing key is a `503`, never "trusted".
2. The claims Core always mints: `sub`, `tenant_id`, `app_id`, `app_version`. A token without one was not minted by the gateway.
3. **That it is yours.** `app_id` must equal your manifest's slug, and `tenant_id` must equal `MANAURUM_TENANT_ID`. Core signs every app's tokens with the same key and the same audience, so step 1 accepts a token minted for any app, and the developer of any app a user opens sees that user's tokens. Without step 3 they have 60 seconds to present one to you. The capability gateway makes this check on its own surface (`401 invalid_user_context`, "app mismatch"); in your container it is yours to make.
4. **Exactly one header.** Until Core MAN-3214 (deployed 2026-10-02) the gateway added its own copy under a different letter case and did not remove a copy the client sent, so a request could reach your container with two (Starlette's `headers.get()` returned the client's). It now drops the client's copy. Keep counting the raw headers anyway — one header, or `401` — against an older Core or a proxy in front of you. (Node joins two copies with `", "`, which then fails JWT parsing, so it fails closed.)

Never read the header on an `anonymous` route. Nothing is minted there, so a copy that does arrive did not come through the gateway, which drops the client's. `templates/v2-starter/src/auth.py` implements all four steps (it reads your slug as `APP_SLUG` from `src/capability.py`; copy both, or set it where you keep it) and `tests/test_auth.py` tests each one. `MANAURUM_TENANT_ID` is injected into `hosted` containers; on a `byo` host, set it yourself to the tenant you deploy into.

### Pages that guests and members both open

A share link, a voting room, an invite page: the same page, opened by people with a Manaurum session and by people without one. Declare its API routes `optional` (Core MAN-3200):

```jsonc
{ "path": "/api/room/*", "auth": "optional" }
```

**The published CLI does not know this mode yet.** `cli-v0.3.0` (2026-09-03) was cut before MAN-3200, and its schema allows only `user` and `anonymous`: `manaurum app validate` and the preflight of `manaurum app deploy` refuse an `optional` route the server accepts. Deploy with `manaurum app deploy --skip-preflight` (run `python check_app.py` first, which knows the mode), or through the API as in `manaurum-deploy`. A release that knows it is tracked as MAN-3235.

* **A signed-in member of your tenant** arrives exactly as on `user` — `X-Manaurum-User-Context`, which you forward to capabilities — and also with **`X-Manaurum-Person`**, a pass that says who they are: `sub` (the same user id), `email`, `name` (the profile name, or empty — never the email), `facts.is_tenant_admin`, `facts.workspace_role`, `kind: "member"`.
* **Anyone else** arrives with neither header. That includes a member of another tenant: the gateway makes them look exactly like a guest, so the route cannot be used to find out who belongs where. There is no `401`.
* **Verify the pass for your app.** Its `aud` is your `MANAURUM_APP_ID` (the v2_apps UUID the deploy injects), so a pass minted for another app fails the audience check — unlike the `user_context`, whose audience is shared. `templates/v2-starter/src/auth.py` → `optional_person` returns `None` for a guest, the person for a member, and a `401` for a pass that is present but bad (an attack or a broken deploy — never treat it as a guest).
* **Decide deliberately what a request without a pass may do.** That is the guest's whole permission set: what the link was for (see the board, vote under a typed name), nothing a member's identity would unlock.
* **Sessions.** A member whose session lapsed is served as a guest; the response carries `X-Manaurum-Session: stale`, and the platform script injected into your pages renews and repeats a GET/HEAD once. A POST is not repeated — it already reached you as a guest — so after a stale POST, ask the person to try again.

Guests still need your own mechanism if a guest must be recognised across requests (a seat in a room, a typed name): keep a short-lived pass of your own, HMAC over what it grants with the key in `os.secrets`, in a header of your own (`X-App-Pass`; not `Authorization`, the gateway strips it). Members no longer need it.

**Names and roles.** The `user_context` carries ids only: no name, no email, no role. On an `optional` route the person pass carries the name, the email and the facts a role is made of (`is_tenant_admin`, `workspace_role`); on a `user` route there is still none of it, so an app that needs admins there keeps its own list (say, user ids in `os.secrets` or your schema). Inside the desktop window `manaurum:init` carries `user.nickname`.

### Streaming routes — the limits

Defaults in Core's `v2_gateway_streaming.py`, each one overridable by the operator:

| Limit | Default | Past it |
|---|---|---|
| Concurrent streams per (app, tenant), per Core process | 50 | `429 stream_concurrency_exceeded` |
| Concurrent streams per Core process, all apps | 200 | `429 stream_concurrency_exceeded` |
| Lifetime of one stream | 15 minutes | closed cleanly |
| Silence from your container | 60 seconds | closed |

Plan your capacity on 50: Core runs more than one process, but nothing lets you choose which one a stream lands on. Send a heartbeat comment (`:\n\n`) well inside 60 seconds — every 20 is plenty — and expect the 15-minute close: it is the point where a reconnect re-runs authentication, so the client reconnects with `Last-Event-ID` and the server resumes from it.

On a `user` route the stream is authenticated once, at connect. `EventSource` cannot send headers and is not covered by session renewal; in a standalone tab a reconnect after the session lapsed is a `401` that `EventSource` gives up on. Read such a stream with `fetch` and a body reader, which renewal does cover.

### `hosted` (default — what 99% of apps want)

The platform builds a Docker image from your `Dockerfile`, runs it as a Swarm service on the shared app network (one overlay for every app, which Core and the main Postgres are on too), and routes `<app_id>.apps.manaurum.com` to it via Traefik with a Let's Encrypt cert.

Required files in your project:

- `Dockerfile` at the build context root
- `manifest.json`
- Whatever else your `Dockerfile` `COPY`s in

The `Dockerfile` is anything that produces a runnable image. The smallest possible one, a static page on nginx:

```dockerfile
FROM nginx:1.27-alpine
COPY index.html /usr/share/nginx/html/index.html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null || exit 1
```

A dynamic one (Node, uvicorn) and the port it must bind: `manaurum-app/SKILL.md` → Step 2, and "`runtime.port`" above.

**What the deploy packs — and why the token file lives one level up.** The packager tars the directory containing your `manifest.json`, excluding only these exact names:

```
__pycache__  .venv  venv  .git  .pytest_cache  .ruff_cache  .mypy_cache  node_modules  dist  build
```

That is an exact-name match list with **no glob support and no `.env*` entry** — a `.env.manaurum` sitting next to your `Dockerfile` is packed verbatim into the build context, baked into an image layer by any `COPY . .`, retained per-version in object storage, downloadable later via `manaurum app fetch-source`, and committed to a per-app append-only git history. There is no practical way to un-leak it. Keep every `.env*` outside the deployed directory. A `.dockerignore` does not help here: the platform builds with Docker's classic builder (`POST /build`, `version=1`), which does not apply it to the uploaded context, and the file is in the stored tar either way — a `.dockerignore` only affects a local `docker build`. What keeps a file out of the *image* is a Dockerfile that `COPY`s only what it needs, as the starter's does.

Env vars the platform sets on every task:

| Env var | Use |
|---|---|
| `MANAURUM_TENANT_ID` | UUID of the installed tenant. |
| `MANAURUM_APP_ID` | UUID of your app in `v2_apps`. The `X-Manaurum-App-Id` for `os.kv.*` and `os.events.emit` only; send your slug everywhere else. |
| `MANAURUM_VERSION` | Currently-running semver. |
| `MANAURUM_TARGET_SCHEMA` | Your per-(app, tenant) Postgres schema: `app_<slug>__<tenant_hex>`. |
| `MANAURUM_RUNTIME_TOKEN` | The `mna_*` credential to call the capability gateway with. Minted fresh on every deploy, scoped to this one app. **Never bake your own developer token into the image.** |
| `MANAURUM_CORE_URL` | Base URL for capability calls: `{MANAURUM_CORE_URL}/api/capability/<name>`. |
| `CORE_USER_CONTEXT_PUBLIC_KEY_PEM` | RS256 public key for verifying the `X-Manaurum-User-Context` JWT the gateway injects on `auth: "user"` routes. |
| `DATABASE_URL` | Postgres DSN for your dedicated schema. Injected **only** when a managed schema was provisioned — absent under `data.none` / `data.byo`. A per-(app, tenant) login role, `NOSUPERUSER NOBYPASSRLS`, scoped to your one schema, with **no CREATE** — so no DDL at runtime, including `CREATE TABLE IF NOT EXISTS` on boot. |

That is every `MANAURUM_*` variable the platform sets. Two names that are **not** in it, and that older guidance told people to read:

- **`MANAURUM_V2_TOKEN`** — the name these skills use for *your own* deploy credential in `.env.manaurum` on your machine. The platform never injects it; code that reads it at runtime finds nothing. The runtime credential is `MANAURUM_RUNTIME_TOKEN`.
- **`MANAURUM_BROKER_URL`** — never injected: MAN-163 removed it because the shared broker DSN had grants on every app schema. Do not build anything on it.

`MANAURUM_TENANT_ID` is for display ("welcome to <tenant>", per-tenant branding), never a security filter: capability calls are scoped to the calling tenant (the gateway binds every handler's session to it), and your schema is already per tenant. Don't try to talk to other tenants: capabilities are tenant-scoped at the gateway level, and you would get a `403` anyway. Within a tenant, not everything is private to your app — see `os.compliance.audit_query` and `os.tenant_config.*` in `capabilities-reference.md`.

### `byo` (bring your own — advanced)

You host the app yourself; the platform proxies signed requests to your endpoint. Useful when you have legacy infra you can't move. Requires a `byo_hosts` row registered via Workspace Admin → Integrations.

Manifest looks the same plus **`runtime.entrypoint`** — the absolute HTTPS URL of your endpoint. The shell honours it only for `mode: "byo"`; for `hosted` apps the URL is platform-derived (`https://<slug>.apps.manaurum.com/`), and a `hosted` manifest that sets `entrypoint` is a `422`.

> Do **not** write `runtime.byo_endpoint_url`. That spelling appears nowhere in Core, and since `runtime` became strict it is a `422`. The field is `entrypoint`.

Your endpoint must implement the BYO health-check contract (`GET /.well-known/manaurum-byo-health` → 200) and verify the platform's HMAC signature on capability dispatch. See R-5 documentation in the manaurum repo if you really need this; most apps shouldn't.

### `dev` (platform-internal prototyping runtime)

> **No editor ships for this mode.** It was driven by an in-browser Monaco editor called *App Builder*, removed from the product on 2026-08-07 — Aurum Studio is the only builder Manaurum ships, and it publishes straight to `hosted`. The mode, its tables and its routes still exist, so the description below stays accurate, but you cannot reach it from the OS and **you should not target it**. Use `hosted`.

Files live in `dev_apps` / `dev_app_files` tables; output served via `/api/dev/v2/dev-apps/<id>/serve/...`. Capability allow-list: `os.kv.*`, `os.files.*`, `os.tenant_config.*`, `os.secrets.*` and `os.compliance.audit_query`; everything else is `403 capability_denied_in_dev_mode`.

### `egress_allowed_hosts`

List of external hostnames your app may reach via the `os.http.fetch` capability. **Empty (or absent) list = default deny** → `412 egress_not_declared`; a host outside the list → `412 host_not_in_allow_list`. The deploy pipeline copies the list onto the version row and the `os.http.fetch` handler reads it there, so this is the real enforcement point.

The schema declares it, as an array of strings; a host there is not checked for shape until `os.http.fetch` compares it with a URL, and the comparison is an exact hostname match, case aside: write `api.example.com` — no scheme, no path, no wildcard — and list a redirect's host separately.

> **The list is enforced by `os.http.fetch` and nothing else.** Your container's own outbound connections are not filtered today: a raw `fetch()` reaches any host, declared or not (the `0.0.0.0` trick that used to break declared hosts was removed in MAN-2263). Route external HTTP through `os.http.fetch` anyway: it already enforces the list, it is audited, and it never follows a redirect for you. Nothing enforces the list at the container level yet.

---

## 3. Capabilities — the contract

Every capability call is a `POST ${MANAURUM_CORE_URL}/api/capability/<name>` from your
container, with `Authorization: Bearer ${MANAURUM_RUNTIME_TOKEN}`, `X-Manaurum-Tenant-Id`
and `X-Manaurum-App-Id` (the UUID for `os.kv.*` and `os.events.emit`, your slug for
everything else), the user's `X-Manaurum-User-Context` when you act for them, and the
capability's input as the JSON body. Success is `{ "output": …, "correlation_id": … }`.

The full contract — the header rules, every gate the gateway runs before your capability
and its error code, and each capability's input, output and errors — is in
`references/capabilities-reference.md`, and lives only there.

### Audit + quota

Every call (success or failure) lands in `capability_audit_log` (FORCE-RLS by tenant). Read it via `os.compliance.audit_query` — the whole tenant's, unless you pass `app_filter`. Daily counts in `capability_quota_daily`.

---

## 4. Tokens — `mna_*` issuance, scope, revocation

The format is `mna_<keyid>_<secret>`: a 12-hex key id and a 32-char url-safe secret, stored as
a bcrypt hash. Mint it in Dev Hub → Credentials (or `POST /api/developer/v2-credentials` with your
signed-in session); the raw token is returned once. Two scopes:

- `{"scope_kind": "owner"}` — every app you own in this tenant, including ones you create
  later. Default 90 days. **The only kind that can deploy a brand-new app.**
- `{"scope_kind": "apps", "apps": ["my-app"]}` — only the listed apps, and only while you own
  them and are a tenant member. Default 365 days. `"*"` is `400 apps_wildcard_not_allowed`;
  an app you do not own, or that does not exist yet, is `403 apps_not_owned`.

At most 20 active per person per tenant; revoke with `DELETE /api/developer/v2-credentials/<id>`
(soft). A token is bound to the tenant that was active when it was minted, and nothing reports
it later (MAN-3199). The capability gateway refuses an `owner` token
(`403 owner_scoped_credential_not_accepted`); containers use their injected runtime token.
Everything about using a token for a deploy is in `manaurum-deploy/SKILL.md` → Prereqs.

Your own `mna_*` is a deploy-time credential for `POST /api/dev/v2/deploy` from your laptop
and nothing else. Don't bake it into the image, and don't pass one at deploy: you don't need
to, because the platform injects `MANAURUM_RUNTIME_TOKEN`, and an image containing your token
hands every future reader your deploy rights. (`os.secrets.get` is not an alternative here —
it is itself a capability call that needs the runtime token first.) And don't try to deploy
with an `mnu_*` token: an `mnu_*` is a tenant token for MCP clients and Drive upload, not a
deploy credential. Deploys use `mna_*` exclusively.

---

## 5. Deploy lifecycle

`POST /api/dev/v2/deploy` checks the credential, manifest, slug, ownership and archive
synchronously, then returns `202 {"deploy_job_id", "status": "pending"}` and builds, pushes,
migrates, swaps the container and probes it in the background. The contract — every synchronous
refusal, the job and its phases, what `succeeded` means (the migration gate and the readiness
probe), version immutability, and the failure table — lives in one place:
`manaurum-deploy/SKILL.md`.

Two facts this page's other sections depend on: migrations run **after the image push and
before the new container replaces the old one**, and a migration that fails in **any** tenant
stops the version from going live (MAN-2510).

In order, a deploy:

1. Takes your build context, tarred and uploaded as base64 in the request body.
2. Builds your image from the `Dockerfile` inside the backend container.
3. Pushes the image to a tenant-private Docker registry.
4. Creates a Swarm service (or updates it, for a redeploy).
5. Exposes `https://<slug>.apps.manaurum.com` through a Traefik route with a Let's Encrypt
   cert.

Build the archive in a per-run `mktemp -d`, never under a fixed name in a shared `/tmp`: on
2026-09-08 two sessions collided on one, and one shipped the other's archive and reported
`activated` for an app it never touched (MAN-2456). Echo the slug before you trust a green
deploy.

End-to-end deploy time for a small app: **~8 seconds**. There is **no Core PR** for any of
this, and the platform team does not need to be in the loop: you are not modifying ManAurum
OS, you are deploying an independent containerized app onto it.

---

## 6. Rollback + version history

`POST /api/dev/v2/apps/<slug>/rollback` with `{"version_label": "…"}` re-points
`v2_apps.current_version_id`, Swarm and Traefik at that version. It reverts no schema, runs no
readiness probe or migration gate, and does not re-sync the Assistant's tools. Versions:
`GET /api/dev/v2/apps/<slug>/versions`. Details: `manaurum-deploy/SKILL.md` → Rollback.

---

## 7. Migrations + dedicated app schemas

### The contract

Put plain `.sql` files in a top-level `migrations/` directory of your build context:

```
my-app/
  Dockerfile
  manifest.json
  migrations/
    0001_init.sql
    0002_add_line_items.sql
```

The deploy extracts them and runs each file **once per (app, tenant)** in lexical filename order, recording `(app_id, tenant_id, filename, sha256)` in `v2_app_migrations` so later deploys skip what is already applied.

Packaging rules:

- **SQL-only.** A non-`.sql` file *directly* under `migrations/` fails the deploy — a stray `README.md` there is an error, not a silent skip. The extension check is case-sensitive: `0001.SQL` counts as non-SQL.
- Subdirectories under `migrations/` are silently ignored. So are symlinks. Keep the directory flat.
- No `migrations/` directory at all is fine — frontend-only and kiosk-only apps skip migrations entirely.
- **Never edit an applied file.** The runner re-hashes each file and a sha256 mismatch fails that tenant, and the migration gate then stops the whole version from going live. Add `0002_*.sql` instead.

You do **not** open your own connection and there is no `MANAURUM_BROKER_URL` to read — that variable is never injected. The runner opens the session, `SET ROLE`s to a per-(app, tenant) `appddl_*` NOLOGIN migrator role, and positions `search_path` on your schema — `app_<slug>__<tenant_hex>`, which is also handed to your container as `MANAURUM_TARGET_SCHEMA`. Write plain unqualified SQL: no schema-qualified names.

### DDL rules — three tiers

Every statement is parsed with `pglast` and classified. Getting the tiers wrong is the fastest way to write a migration that gets rejected at deploy time.

| Tier | Meaning | Does `migration.breaking: true` override it? |
|---|---|---|
| `additive` | passes by default | n/a |
| `neutral` | passes by default (data DML / read-only) | n/a |
| `destructive` | rejected by default | **yes** |
| `forbidden` | rejected **always** — this is a security boundary | **no** |

**additive (passes):** `CREATE TABLE` · `CREATE TABLE AS` · `CREATE INDEX CONCURRENTLY` · `CREATE VIEW` · `CREATE SEQUENCE` · `CREATE SCHEMA` · `CREATE TYPE AS ENUM` · `ALTER TYPE ADD VALUE` · `CREATE TYPE` (composite) · `CREATE DOMAIN` · `CREATE TRIGGER` · `CREATE POLICY` · `COMMENT ON` · `GRANT` (object privilege) · `ALTER TABLE ADD COLUMN` · `ALTER TABLE ENABLE ROW LEVEL SECURITY` · `ALTER TABLE FORCE ROW LEVEL SECURITY` · `CREATE FUNCTION` **only** with `LANGUAGE sql` or `LANGUAGE plpgsql`.

Two additives are context-sensitive — **each file** is analysed as a whole, and one file is all the validator ever sees at once. That matters more than it sounds: `0001_init.sql` creating the table does not make a plain `CREATE INDEX` in `0002_add_index.sql` additive, because by the time `0002` runs the table exists and has rows. Judge each file the way the tenant's database will meet it — on its own, in order.

- plain `CREATE INDEX` **on a table created earlier in the same file** → additive. On a pre-existing table → **destructive** ("locks the table; use CONCURRENTLY").
- `ALTER COLUMN … SET NOT NULL` **on a column added earlier in the same file** → additive. On an existing column → **destructive**. The rule is *fresh column*, not "has a default".

**neutral (passes):** `INSERT` · `UPDATE` · `DELETE` · `SELECT`.

**destructive (rejected unless `migration.breaking: true`):** `DROP …` of any object (TABLE, COLUMN, INDEX, CONSTRAINT, …) · `RENAME` · `TRUNCATE` · `ALTER COLUMN … TYPE` · `REVOKE` · plain `CREATE INDEX` on a pre-existing table · `SET NOT NULL` on a pre-existing column.

**forbidden (rejected even with `migration.breaking: true`):** `DO $$ … $$` · `COPY` · `CREATE EXTENSION` · `BEGIN` / `COMMIT` / `SAVEPOINT` · `SET` (any `VariableSetStmt` — so no `SET search_path`) · `CREATE` / `ALTER` / `DROP ROLE` · `GRANT` / `REVOKE ROLE` · `CREATE` / `DROP` / `ALTER DATABASE` · `ALTER SYSTEM` · `CREATE FUNCTION` in any language other than `sql` / `plpgsql`.

**The master rule is default-deny.** Any statement type not on the recognised lists above is treated as `forbidden` — rejected even under `breaking: true`. This is the rule you will actually hit, so reach for boring, explicit DDL.

Consequences worth planning around:

- **No `CREATE EXTENSION`** — you cannot install `pgcrypto` or `uuid-ossp`. Generate UUIDs in your app, not in Postgres.
- **No `DO $$ … $$`** — expand the block into plain statements. This bites real apps: the first-party app Libi shipped a `DO $$` block in `migrations/0002` and needed a follow-up commit to drop it (MAN-1327).
- **No `BEGIN` / `COMMIT`** — the runner owns the transaction.
- An `ALTER TABLE` carrying several subcommands takes the **strictest** verdict across them: one destructive subcommand poisons the whole statement.

For genuinely destructive work, set `migration.breaking: true` with a written `reason` — and remember it buys you the `destructive` tier only, never the `forbidden` one.

### A file that uses `CONCURRENTLY` may contain nothing else

This is the rule you meet immediately after the one above, because the remedy for "plain `CREATE INDEX` locks the table; use `CONCURRENTLY`" walks straight into it.

`CREATE INDEX CONCURRENTLY` cannot run inside a transaction block — Postgres refuses it outright (`25001`). Everything else in a migration needs that transaction, because the promise is that a failure rolls your file back. Both cannot be true of one file, so the platform resolves it the only way that keeps the promise: **a file whose statements are all `CONCURRENTLY` runs outside a transaction; a file that mixes is refused.**

`migration.breaking: true` does not open this gate. It answers "yes, this shrinks the schema"; it is not a way to ask Postgres for something it will not do.

So the second migration is **two** files, not one:

```
migrations/
  0001_init.sql          CREATE TABLE …
  0002_add_body.sql      ALTER TABLE note ADD COLUMN body text;
  0003_index_body.sql    CREATE INDEX CONCURRENTLY note_body_idx ON note (body);
```

Not this — the same two statements in ONE file, which is refused:

```sql
-- 0002_add_body.sql  ✗
ALTER TABLE note ADD COLUMN body text;
CREATE INDEX CONCURRENTLY note_body_idx ON note (body);
```

Several `CONCURRENTLY` statements may share a file, since the whole file then runs outside a transaction. The platform decides this from the parse tree, so the word in a comment, in a string literal or inside a quoted identifier is not a request.

**If you already shipped a file that mixes.** A migration is run once per (app, tenant) and never re-run, so a file your tenants have already applied is skipped by name and checksum — the deploy will not refuse it, and you must **not** edit it: changing an applied file is refused for every tenant that ran it, which is worse than the original problem. `manaurum app validate-migration` still flags it, because it judges the files in front of it rather than what any tenant has applied. Treat that as a warning about **new installs** — a tenant installing the app for the first time reaches that file, is refused at it, and blocks the whole deploy for every tenant. There is no clean fix for that tenant from the app side: the offending file is still the first one it must apply. Adding new files ahead of it does not help. If you need the app installable again, that is an operator conversation, not a migration you can write.

Validate locally before you deploy:

```bash
manaurum app validate-migration migrations/                       # whole dir, same order as the deploy
manaurum app validate-migration migrations/0002_add_line_items.sql
manaurum app validate-migration migrations/ --breaking            # mirrors migration.breaking: true
```

It runs the exact same validator the deploy pipeline runs, file by file in the same order, so green here means green there.

`check_app.py` uses that validator too, when a copy that knows this rule is importable. With no usable copy it does **not** guess — no text test can decide these rules — so it leaves them unchecked; with a copy too old to know the `CONCURRENTLY` rule, it checks everything else against the real validator and leaves that one. Either way it prints a note naming exactly what went unchecked. A `clean` from `check_app.py` alone is not the same statement as a green from the command above.

### Runtime is read/write, not DDL

At runtime your container reads `DATABASE_URL` — a per-(app, tenant) `appusr_*` **login** role, `NOSUPERUSER NOBYPASSRLS`, granted `USAGE` on exactly one schema plus `SELECT/INSERT/UPDATE/DELETE` on its objects. It holds **no `CREATE`**, so runtime DDL is impossible: a `CREATE TABLE IF NOT EXISTS` on boot — a common framework default — dies with `permission denied for schema app_<slug>__<hex>`. Schema changes happen only through `migrations/*.sql`.

The role's default `search_path` is your schema, then one `ext_<name>` schema per granted extension, then `pg_temp` — no `public` — so write plain unqualified SQL. Your schema is already per-tenant, so there is no `tenant_id` column to filter on and no RLS to satisfy.

**Sequences: your container can draw from them, not move them.** The runtime role holds `USAGE, SELECT` on sequences — enough for `nextval`, not for `setval` or `ALTER SEQUENCE … RESTART`. That bites when you bring rows over with their original ids, moving an app here from somewhere else: the inserts succeed, the sequence is still at 1, and the next ordinary insert collides with an imported id. The migrator role created the sequence, so it owns it, and the realignment belongs in a migration that runs after the import:

```sql
-- 0004_realign_ids.sql: the import kept the source ids
SELECT setval(pg_get_serial_sequence('item', 'id'),
              COALESCE((SELECT max(id) FROM item), 0) + 1, false);
```

A `SELECT` is `neutral`, so the validator passes it. Like every migration it runs once per tenant, so a second import later needs a second file. If the data can travel inside the migration itself as `INSERT`s, put this line at the end of the same file.

**Your container serves exactly one tenant.** The platform runs one Swarm service, for the tenant that deployed the app — the service DNS name is derived from both — and injects a fixed `MANAURUM_TENANT_ID` that never changes for the life of that container. So process-local state (in-memory caches, module globals, connection pools) is already single-tenant: you do **not** need to key caches by tenant, and doing so adds complexity that buys nothing. What you must still not assume is that `sub` is stable-shaped — treat it as opaque TEXT (see the user-context section).

### Your database can come up after your container

Postgres and your app are separate Swarm services, restarted in no particular order. After a host stall Swarm recreates many of them at once, and your app can start first. On 2026-09-25 the apps were up 50 seconds before Postgres accepted connections.

**Never remember a failed connection.** Open the pool on first use. If opening it fails, raise and leave nothing behind, so the next request tries again. Do not warm the pool up in `lifespan`.

```python
_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _pool_lock:          # concurrent first requests share one pool
            if _pool is None:
                _pool = await asyncpg.create_pool(
                    os.environ["DATABASE_URL"],
                    min_size=1, max_size=8,
                    timeout=10,         # connect: under the gateway's 30 s
                    command_timeout=25,
                )
    return _pool
```

Two shapes look careful and are not:

- **Connect once in `lifespan` and swallow the failure** (`except Exception: _pool = None`). Every query helper then answers "no database" with an empty result. The app serves 200s with no data and `/healthz` stays green. Postgres logs nothing, because the app stopped asking. It stays that way until someone restarts it. Five hosted apps sat like this for 43 hours.
- **Connect once in `lifespan` and let the process crash.** Swarm restarts it every few seconds, so it does come back. Until then, though, the UI, `/healthz` and every route are down too, not only the ones that need data. The operator sees a crash loop rather than its cause.

The same goes for anything else you fetch once at boot from Core, such as a secret from `os.secrets.get`. Core can be down while you start too. Fetch it when you first need it, and fetch it again if you do not have it yet.

### Connecting from the container

Copy `templates/recipes/postgres/db.py`. It is the pool above plus the one decision that apps keep getting wrong:

```python
_pool = await asyncpg.create_pool(
    dsn=os.environ["DATABASE_URL"],
    min_size=1, max_size=8, timeout=10, command_timeout=25,
    server_settings={
        "search_path": search_path(schema),   # '"app_…", pg_temp' - survives RESET ALL
        "statement_timeout": "25s",
    },
    init=configure_connection,                # json/jsonb codecs only
)
```

**Why `search_path` is a connection parameter and not a `SET`.** asyncpg's pool runs `RESET ALL` on every connection it takes back — that is asyncpg's behaviour (`Connection.get_reset_query()`), not the platform's. `init=` runs once, when a connection is created, so anything it `SET`s is gone after the first release and the session falls back to the *role's* default. A pool that does `SET search_path` in `init=` answers the first request on a fresh connection and can fail the next one with `relation "…" does not exist`.

On the platform this usually hides, because the role's default `search_path` is already your schema and the reset lands back on it. On a plain local Postgres the default is `"$user", public`, so the bug fires exactly where you run the app by hand, and reads as "the platform is broken". Several first-party apps shipped it until MAN-1443 moved them to `setup=`, which runs a `SET` on every acquire and pays a round trip per request. A value in `server_settings` costs nothing: it travels in the connection's startup packet, and `RESET ALL` restores it instead of removing it. `check_app.py` fails on a session `SET` inside `init=`.

**The value is the platform's own:** your schema, one `ext_<name>` schema per granted extension in `data.extensions` (only `vector` and `pg_trgm` exist), then `pg_temp`. Because `server_settings` *replaces* the role's default, an extension you use must be in the recipe's `EXTENSIONS` tuple, or its types stop resolving. Naming one that is not granted yet costs nothing — Postgres skips a schema the role cannot use. `public` is not on the path, and nothing an app needs lives there: `gen_random_uuid()` and the text search configurations are in `pg_catalog`, which Postgres always searches.

Type codecs are not session state — they live in the asyncpg connection object — so `init=` is the right place for them. The recipe's tests (`templates/recipes/postgres/tests/`) run against a real Postgres and include the failing `init=` version, so the lesson cannot quietly rot. Point them at any local server:

```bash
pip install -r templates/recipes/postgres/requirements-test.txt
MANAURUM_TEST_PG_DSN=postgresql://postgres:postgres@localhost:5432/postgres \
  pytest templates/recipes/postgres
```

### Full-text search

A content app needs search on its second day, and the obvious query makes the app look broken: `websearch_to_tsquery` joins words with AND, so a question typed the way people type — "why do clients leave after the first month" — needs every content word in one document and returns nothing. The recipe (`templates/recipes/postgres/search.py` and its `migrations/`) is Postgres built-ins only — no extension to request — and does four things:

1. **A generated, weighted `tsvector` column.** `setweight(…, 'A')` for the title, `'B'` for tags, `'D'` for the body, so a title hit ranks first. A generated column accepts only IMMUTABLE functions, and two that look harmless are not: `array_to_string()` is STABLE (wrap it in a one-line `LANGUAGE sql IMMUTABLE` function — honest for `text[]`), and so is the one-argument `to_tsvector(text)`, which reads `default_text_search_config` (write `to_tsvector('russian', …)`). Postgres refuses both with `generation expression is not immutable`; the deploy's validator does not look, so `check_app.py` does.
2. **A GIN index.** In the same file as `CREATE TABLE`, a plain `CREATE INDEX … USING gin`. On a table an earlier migration created, `CREATE INDEX CONCURRENTLY` in a file of its own (above).
3. **Strict, then relaxed.** The query as typed first. If it finds nothing, the same words joined with `or` — still `websearch_to_tsquery`, which never raises on odd input — ranked by `ts_rank_cd`, so documents matching more of the words come first. The response says which one answered (`mode`), and the screen should too: "no post has all of these words — these have some of them". Paging passes the mode back, so page two answers page one's question.
4. **A snippet that is safe to insert.** `ts_headline` returns the document's own text with markers around the hits, and that text came from people. It is not a sanitiser: it drops what its parser takes for a whole tag and passes a fragment like `<img src=x onerror=alert` straight through. The recipe uses control characters as markers, HTML-escapes the snippet, and only then turns the markers into `<mark>` — and runs `ts_headline` on the returned page only, because it re-parses every document it is given.

`russian`, `english` and `simple` are built into Postgres and live in `pg_catalog`. The configuration in the query must be the one the column was built with, or query words are stemmed differently from indexed ones. Adding a `STORED` column to an existing table rewrites it under an exclusive lock, inside the migration's 30 s `statement_timeout` and after waiting at most 5 s for that lock (`lock_timeout`) — fine for thousands of rows on a quiet table, worth a thought for millions or for a table the app is writing to all the time.

### `migrate_command` does nothing

`migrate_command` is in the manifest schema, but Core has **no call site for it** — nothing executes it. An app whose schema depends on it deploys green and its tables simply never exist. Use `migrations/*.sql`.

---

## 8. Visibility + App Store v2

```json
"visibility": { "mode": "private" | "public" | "allow_list", "tenants": [...] }
```

- `private` (default) — only the home tenant sees the app. The deploy installs it there: on every workspace of a team tenant, on each owner's own desktop in a personal one.
- `public` — listed in `/api/app-store/v2/catalogue` for every tenant. Tenant admins can `POST /api/app-store/v2/install` to install.
- `allow_list` — listed only for tenants in `tenants[]` (UUIDs).

Install rows live in `v2_app_installs`. Uninstall is soft (sets `tombstoned_at`). The capability gateway gates capability calls on whether the calling app is installed in the calling tenant.

A tenant admin installs from the App Store, or through the API. An app installed in a tenant other than the one that deployed it does **not** serve that tenant's users today: its `auth: "user"` routes answer them `404 app_not_found` (`manaurum-deploy/SKILL.md` → "Who gets the app after a deploy").

```bash
curl -sS -X POST https://manaurum.com/api/app-store/v2/install \
  -H "Authorization: Bearer $SESSION_JWT" \
  -H "Content-Type: application/json" \
  -d '{"app_id": "<uuid>", "granted_capabilities": [...], "config": {...}}'
```

---

## See also

- `manaurum-app/SKILL.md` — quick build guide.
- `manaurum-deploy/SKILL.md` — deploy script + rejection codes.
- `manaurum-setup/SKILL.md` — project scaffolding.
- `references/capabilities-reference.md` — input/output schemas for every capability.

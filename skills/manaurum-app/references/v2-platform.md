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
> The `runtime` and `metadata` **sub**-objects are *not* strict. Unknown keys there validate silently — which is how `runtime.port` and `runtime.egress_allowed_hosts` work (real, read by Core, just undeclared) and also how a typo like `runtime.byo_endpoint_url` passes validation and does nothing.

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
| `app_id` | string | Schema only enforces `minLength: 1` — but it becomes your DNS label (`<app_id>.apps.manaurum.com`), the Swarm service name and the Postgres schema name, so keep it `^[a-z][a-z0-9-]*[a-z0-9]$` and under ~40 chars in practice. Also `v2_apps.app_slug`. |
| `name` | string | Human-readable. Used in App Store + windowing. |
| `version` | string | Semver `MAJOR.MINOR.PATCH`. Bump on every redeploy. No pre-release / build metadata. |
| `runtime` | object | See § 2. |

### Optional top-level

These 17 keys plus the 6 required ones are the complete root surface. Anything else is a validation failure.

| Field | Type | Notes |
|---|---|---|
| `data` | object | Storage mode. **Omit it and you get managed mode**, which provisions a Postgres schema + login role per (app, tenant) and needs `MANAURUM_DDL_DSN` on Core — a deploy that fails at `swarm_applying` if it isn't set. A stateless app (persists only via `os.kv` / `os.files`) must declare `{"none": true}`. Other modes: `{"byo": true}` (your own DSN, no isolation guarantees), `{"shared": true}` (one cross-tenant schema — you own every `WHERE tenant_id`), `connection_cap`. `additionalProperties: false` on this sub-object. |
| `frontend` | object | `entry_point` (the URL the desktop shell loads in the app's window — normally `/index.html`; without it your app has no desktop window), `icon`, `bundle_path`, `window: {default_width, default_height}`. `frontend.icon` is an unconstrained string: an emoji works, so does an absolute URL or `/api/catalog/media/...` path. A **relative** path (`icons/app.svg`) is painted as literal text in the tile. Omit it entirely and the launcher serves a generic placeholder. |
| `visibility` | object | `mode: "private" \| "public" \| "allow_list"`, optional `tenants: [uuid…]`. Default `private`. |
| `platforms` | object | `desktop: {supported}` and `mobile: {supported, optimized, entrypoint, supportLevel, navigationPattern}`. Declare both explicitly. `platforms.mobile.entrypoint` is a separate HTTPS URL the shell loads on mobile devices. |
| `requires_capabilities` | array | `[{name, version, quota_per_tenant_per_day?}]` — the capabilities your app cannot work without. |
| `optional_capabilities` | array | Same shape as `requires_capabilities`, for capabilities you use if granted but don't require. App Store v2 reads this to compute the optional grant set the tenant admin sees at install time. |
| `agent_capabilities` | array | Tools this app exposes to the **OS Assistant** — see the subsection below. Each entry `{name, description, input_schema, …}`; `name` is snake_case `^[a-z][a-z0-9_]*$`, ≤64 chars. |
| `provides` | object | Inter-app contracts you expose: `{rpc: [...], events: [...]}`. Another app calling you via `os.apps.call` must find the method here. |
| `consumes` | object | Inter-app contracts you depend on: `{rpc: [...], events: [...]}`. **Declare every RPC you call with `os.apps.call` and every event you subscribe to.** |
| `webhooks` | array | `[{name, path, signature}]`. **Validated for shape; Core does nothing with it in v2.x** — the platform webhook gateway is deferred. Expose your own handler via `runtime.api_routes` with `auth: "anonymous"` and verify the signature yourself. |
| `schedules` | array | `[{name, cron, handler_path, timezone?}]`. **Validated for shape; Core does not invoke the handler in v2.x** — platform cron is deferred. Run an in-container scheduler and keep the declaration as documentation of intent. |
| `tenant_config` | object | `{schema, required_at_install}` — per-tenant config collected at install time. Note: install-time values land in `v2_app_installs.config`, which the `os.tenant_config.get` capability does **not** currently read. Don't build on the round-trip yet. |
| `offline` | object | Manaurum Edge declaration: `features` (operations that stay usable during a WAN outage), `reference_data` (cloud-owned datasets replicated read-only to the on-site box), `streams` (`[{name, type: "ledger" \| "state"}]`). |
| `permissions` | string[] | BROWSER features the OS shell delegates to the app iframe via the `allow` attribute (Permissions-Policy). Enum today: `["microphone"]` (MAN-1316). Required to record audio inside the shell iframe; the user still sees the browser's own mic prompt. Unrelated to `requires_capabilities` — a voice app needs both this AND `os.ai.transcribe`. |
| `migrate_command` | string[] | In the schema, but **Core never executes it** — there is no call site (`production.py:40-43`, "reserved"). An app whose schema depends on it deploys green with no tables. Use `migrations/*.sql` instead — see § 7. |
| `migration` | object | `{breaking, reason, rollback_strategy}`. `breaking: true` lets the DDL validator through *destructive* statements (and only those — see § 7). Default `false`. |
| `metadata` | object | App Store rendering: `category`, `tags`, `description`, `homepage`, `support_email`, `source_url`. **This is where a root-level `description` belongs.** |

Grant enforcement is **unconditional**, not aspirational: every hosted-app capability call is checked against the install's `granted_capabilities` before quota, dispatch and audit. A capability absent from the list — **or an install whose list is empty** — is `403 capability_not_granted`. Wildcard `"*"` grants everything. Only dev-mode apps and active BYO hosts short-circuit the check. Operational consequence: adding a capability to your manifest and redeploying is **not** enough — the tenant's install grant set has to be extended too, or every call 403s.

### `agent_capabilities[]` — expose your app to the OS Assistant

Each entry registers one tool the OS Assistant can call on the user's behalf. On deploy, Core upserts one `agent_capabilities` row per entry; at request time the agent runtime builds a tool per row (for apps the user has installed) and dispatches **server-to-server** — `POST http://<container>/agent/<name>` with the tool arguments as the JSON body and a freshly minted `user_context` JWT in `X-Manaurum-User-Context`, the same header and the same key your `auth: "user"` routes already verify. Reply `{"ok": true, "output": …}` (a bare JSON object also works; `{"ok": false, "error": …}` surfaces as a failed tool call).

This dispatch goes **straight to your container**, not through the `/apps/<slug>` gateway — so `/agent/<name>` does **not** need a `runtime.api_routes` entry, and declaring one there does nothing.

> ⚠️ **`/agent/*` is not private. Verify the JWT in every handler.** Skipping `api_routes` removes the *gateway*, not the network: `https://<slug>.apps.manaurum.com` is Traefik straight to your container, so anyone on the internet can POST `/agent/<name>` and reach your code. Verified 2026-07-26 against a live deploy — an unauthenticated `POST /agent/<name>` on the public host is answered by the container, not the gateway. The user_context check is therefore the **only** thing standing between a stranger and your handler, and it must be load-bearing, not belt-and-braces.

**Declare at least one.** An app with no `agent_capabilities` is invisible to the Assistant — and the Assistant does not say "I can't see that app", it *guesses*, so the user gets confident answers about data it never read. This is the platform's differentiator; treat the field as required, not optional.

#### The manifest entry

The three required keys are `name`, `description`, `input_schema`. What separates a usable tool from a decorative one is the `description`, which is **prompt text for a model, not documentation for a human** — say what the capability does, when to reach for it, and when not to. Hard cap 400 chars (`manifest_v2.schema.json`, matching the runtime's `Tool` validator, `app/agent/types.py:108`); longer is rejected at deploy.

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

`routing_hints` are informational keywords; `example` is surfaced to the model as a usage hint. Both are optional and both help.

> **`is_write` is declarative only — the runtime ignores it for hosted apps.** Declare it truthfully anyway (it is the honest statement of intent, and it is what the field will mean once the gap closes), but do not build on it. There is no `is_write` column on `agent_capabilities`, the deploy-time sync never reads the key, and at request time the runtime *derives* it: `dispatch == "backend"` — which is what every v2 hosted app gets, since the manifest cannot set `dispatch` — forces `is_write=True` for **every** capability, readers included. Two consequences today: your read-only capabilities still take the write path (AgentAction rows, confirmation, idempotency dedup), and they are excluded from cross-app insight, which filters on `not is_write`. Tracked as MAN-1425.

#### The handler side

`/agent/<name>` is dispatched **straight to your container** and is *not* a gateway route, so it needs no `runtime.api_routes` entry — but see the warning above: it is still exposed on your public hostname. Serve it with the same JWT verification your `auth: "user"` routes use:

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
  "egress_allowed_hosts": [...]
}
```

Only `mode` and `api_routes` are declared in `manifest_v2.schema.json`. `port`, `egress_allowed_hosts`, `replicas` and `sandbox` are **not** — they validate only because the `runtime` sub-object omits `additionalProperties: false`. Some of those undeclared keys are read by Core (`port`, `egress_allowed_hosts`); others are read by nothing at all (`replicas`). The practical rule: a misspelled `runtime` key never errors, it just silently does nothing.

Leave `runtime.sandbox` alone. The shell takes it **verbatim, replacing** the whole default token list (`allow-scripts allow-forms allow-same-origin`), so `"sandbox": ["allow-modals"]` costs you `allow-scripts` and your app renders blank. Whether the `runtime` sub-object should become strict — which would also invalidate `port` and `egress_allowed_hosts` — is an open design question; this section documents what the platform does today, not where it is going.

### `runtime.port`

The port your container listens on. **Default 80.** The Core gateway resolves the upstream as `<swarm-service>:<port>` where `port` is `runtime.port` if present and 80 otherwise. Nothing in Core parses your Dockerfile's `EXPOSE` line — it is documentation only. `runtime.port` is in production use (`libi/manifest.json` ships `"port": 8000`), so it is safe; just know it is schema-undeclared. It is also **untyped**: `"port": "abc"` passes validation and produces a broken upstream host, so write an integer.

### `runtime.api_routes` — default-deny

The declaration table for every `/api/*` path your container serves. **A path that is not declared returns `404 route_not_declared` from the gateway and never reaches your container** — the app just looks broken.

| Key | Notes |
|---|---|
| `path` | Required. Must start with `/`. Trailing `*` is a wildcard (`/api/orders/*`); anything else is an exact match. `/api/tasks/*` does **not** match the bare `/api/tasks` — declare both if you serve both. |
| `auth` | Required, `"user"` or `"anonymous"`. `user`: the gateway mints a 60s RS256 `user_context` JWT and injects it as `X-Manaurum-User-Context`; the end user's own bearer token is **never** forwarded. `anonymous`: proxied with no user context (kiosk / public endpoints — explicit declaration required, there is no implicit anonymous fallback). |
| `streaming` | Optional bool, default false. Proxy in SSE / chunked passthrough mode instead of buffering the upstream response. Orthogonal to `auth`. Emit SSE heartbeats, honour `Last-Event-ID`, and do not hold a DB connection for the stream's lifetime. |

There is no `method` field — one rule covers every verb. Static assets (HTML/JS/CSS, `/healthz`) are **not** declared here; they are always anonymous on `<slug>.apps.manaurum.com`.

### `hosted` (default — what 99% of apps want)

The platform builds a Docker image from your `Dockerfile`, runs it as a Swarm service on `dokploy-network`, and routes `<app_id>.apps.manaurum.com` to it via Traefik with a Let's Encrypt cert.

Required files in your project:

- `Dockerfile` at the build context root
- `manifest.json`
- Whatever else your `Dockerfile` `COPY`s in

Env vars the platform sets on every task:

| Env var | Use |
|---|---|
| `MANAURUM_TENANT_ID` | UUID of the installed tenant. |
| `MANAURUM_APP_ID` | UUID of your app in `v2_apps`. |
| `MANAURUM_VERSION` | Currently-running semver. |
| `MANAURUM_TARGET_SCHEMA` | Your per-(app, tenant) Postgres schema: `app_<slug>__<tenant_hex>`. |
| `MANAURUM_RUNTIME_TOKEN` | The `mna_*` credential to call the capability gateway with. Minted fresh on every deploy, scoped to this one app. **Never bake your own developer token into the image.** |
| `MANAURUM_CORE_URL` | Base URL for capability calls: `{MANAURUM_CORE_URL}/api/capability/<name>`. |
| `CORE_USER_CONTEXT_PUBLIC_KEY_PEM` | RS256 public key for verifying the `X-Manaurum-User-Context` JWT the gateway injects on `auth: "user"` routes. |
| `DATABASE_URL` | Postgres DSN for your dedicated schema. Injected **only** when a managed schema was provisioned — absent under `data.none` / `data.byo`. |

`MANAURUM_BROKER_URL` is **not** in that list and is never injected: MAN-163 removed it because the shared broker DSN had grants on every app schema. Do not build anything on it.

### `byo` (bring your own — advanced)

You host the app yourself; the platform proxies signed requests to your endpoint. Useful when you have legacy infra you can't move. Requires a `byo_hosts` row registered via Workspace Admin → Integrations.

Manifest looks the same plus **`runtime.entrypoint`** — the absolute HTTPS URL of your endpoint. The shell honours it only for `mode: "byo"`; for `hosted` apps the URL is platform-derived (`https://<slug>.apps.manaurum.com/`) and any `entrypoint` you write is ignored.

> Do **not** write `runtime.byo_endpoint_url`. That spelling appears nowhere in Core — and because the `runtime` sub-object is not strict, it **validates cleanly and is silently ignored**, leaving your app with no URL at all. The field is `entrypoint`.

Your endpoint must implement the BYO health-check contract (`GET /.well-known/manaurum-byo-health` → 200) and verify the platform's HMAC signature on capability dispatch. See R-5 documentation in the manaurum repo if you really need this; most apps shouldn't.

### `dev` (in-browser App Builder v2)

For rapid prototyping in the Monaco editor inside the OS itself. Files live in `dev_apps` / `dev_app_files` tables; output served via `/api/dev/v2/dev-apps/<id>/serve/...`. Limited capability allow-list (no `os.payments.*`, no `os.http.fetch`, no `os.notifications.send_to_user`, no `os.cron.*`, no `os.events.emit`, no `os.apps.call`). Graduate to `hosted` for production.

### `egress_allowed_hosts`

List of external hostnames your app may reach via the `os.http.fetch` capability. **Empty (or absent) list = default deny** → `412 egress_not_declared`; a host outside the list → `412 host_not_in_allow_list`. The deploy pipeline copies the list onto the version row and the `os.http.fetch` handler reads it there, so this is the real enforcement point.

Like `runtime.port`, the field is schema-undeclared (`runtime` accepts extra keys) but genuinely read by Core. Don't be alarmed when a schema dump doesn't show it.

> **Unresolved — current behaviour is not the intended behaviour.** The deploy also writes each declared host into the container's Swarm `Hosts` entries as `0.0.0.0 <host>`, which means a raw `fetch()` from inside the container to a host you **declared** resolves to `0.0.0.0` and fails, while an *undeclared* host resolves normally. That is the opposite of an allow-list, and it is a live monorepo bug rather than a designed boundary. Until it is resolved, do not write code that depends on either reading of container-level egress: route all external HTTP through `os.http.fetch`, which is enforced, audited, and unaffected.

---

## 3. Capabilities — the contract

Every capability call is:

```
POST https://manaurum.com/api/capability/<name>
Authorization: Bearer mna_<keyid>_<secret>
X-Manaurum-Tenant-Id: <uuid>
X-Manaurum-App-Id:    <uuid>
Content-Type: application/json

<body matching the capability's input schema>
```

Successful response shape:

```json
{
  "output": { /* capability-specific */ },
  "correlation_id": "<uuid>"
}
```

Streaming capabilities (`os.apps.bulk_export`) return `application/x-ndjson` instead.

### Universal error codes

| HTTP | `detail` | Why |
|---|---|---|
| 401 | `invalid_credential` | Bad/expired/revoked `mna_*`. |
| 401 | `missing_authorization` | No `Authorization` header. |
| 403 | `app_id_out_of_scope` | Token's `apps` array doesn't include the requested `X-Manaurum-App-Id`. Wildcard `*` is honored. |
| 404 | (none) | Capability name not registered. |
| 412 | `missing_tenant_id_header` | `X-Manaurum-Tenant-Id` not set. |
| 412 | `missing_app_id_header` | `X-Manaurum-App-Id` not set. |
| 412 | `app_id_must_be_uuid` | App-id header is a slug, not a UUID. Use `MANAURUM_APP_ID` env var. |
| 412 | `egress_not_declared` | (`os.http.fetch` only) host not in manifest egress. |
| 422 | `input_schema_violation` | Body fails the capability's JSON Schema. Read `path` + `message`. |
| 429 | `quota_exceeded` | Per-(app, capability) daily quota tripped. |
| 500 | `handler_exception` | Server-side failure. Logged with `correlation_id`. |
| 502 | `upstream_5xx` | (BYOK / external) provider returned 5xx. |

### Audit + quota

Every call (success or failure) lands in `capability_audit_log` (FORCE-RLS by tenant). Read your own via `os.compliance.audit_query`. Daily counts in `capability_quota_daily`.

---

## 4. Tokens — `mna_*` issuance, scope, revocation

The format is `mna_<keyid>_<secret>` where keyid is 12 hex chars and secret is 32+ url-safe chars. The secret is hashed with bcrypt and stored in `developer_credentials`.

### Issuance — UI

Manaurum desktop → **Dev Hub → "v2 Tokens (Beta)" tab → Generate**. The UI is gated on the per-tenant `platform.v2.enabled` flag — only tenants opted into v2 see the tab. Today: `seregaos`. Future: every tenant after rollout.

The form lets you pick:
- **Apps scope**: comma-separated slugs, or blank for `*` (all apps owned by the developer in this tenant).
- **Expiry**: 90 / 180 / 365 days.

The token is shown ONCE. Save it.

### Issuance — API

```bash
curl -sS -X POST https://manaurum.com/api/developer/v2-credentials \
  -H "Authorization: Bearer $SESSION_JWT" \
  -H "Content-Type: application/json" \
  -d '{"apps": ["*"]}'
```

Same response shape as the UI: `{ id, key_prefix, raw_token, apps, issued_at, expires_at }`. `raw_token` is the bearer; everything else is also retrievable later. Cap: 5 active per (user, tenant).

### Revocation

```bash
# list (no raw_token returned)
curl -sS https://manaurum.com/api/developer/v2-credentials \
  -H "Authorization: Bearer $SESSION_JWT"

# revoke (soft — sets revoked_at)
curl -sS -X DELETE https://manaurum.com/api/developer/v2-credentials/<id> \
  -H "Authorization: Bearer $SESSION_JWT"
```

Soft-deletes via `revoked_at`. The audit trail of issued tokens is preserved.

### Scope semantics

The `apps` array on the token is checked against the `X-Manaurum-App-Id` header on every capability call:

- `["*"]` (default) → any app owned by the developer in this tenant.
- `["my-app", "other-app"]` → only those two app UUIDs.

Scope is per-tenant. A token issued in tenant A cannot call any capability in tenant B (the resolver returns the row's tenant_id; cross-tenant access is structurally impossible).

---

## 5. Deploy lifecycle

`POST /api/dev/v2/deploy` is **asynchronous**. It returns `202` with `{"deploy_job_id": "<uuid>", "status": "pending"}` and runs the pipeline on a background task — so a manifest or migration rejection does **not** come back as a synchronous 422; it surfaces as `status: "failed"` on the job. Poll `GET /api/dev/v2/deploy/{job_id}` or follow `GET /api/dev/v2/deploy/{job_id}/stream` (NDJSON, terminated by `{"terminal": true, "status": …}`). Run `manaurum app validate` first if you want fast feedback.

The background job does these steps in order:

1. **Manifest validation** — JSON Schema + cross-field rules.
2. **Migration validation** — the AST validator classifies every statement in `migrations/*.sql`. See § 7 for the exact rules.
3. **Image build** — Docker Engine API `POST /build` with the tarball as the body. Errors here → `result.error` with the daemon's stderr.
4. **Image push** — to `manaurum-registry:5000/v2-app-<slug>:<version>`.
5. **DB writes** — upsert `v2_apps` (in home tenant) + insert `v2_app_versions` (FORCE-RLS).
6. **Swarm service** — create or update `v2-app-<slug>-<tenant_short>` on `dokploy-network`. Image rewritten to overlay-pull URL so workers on any node can pull.
7. **Traefik dynamic config** — write `/etc/dokploy/traefik/dynamic/v2-app-<slug>.yml`. Traefik reloads automatically.
8. **Per-tenant migrations** — fan out to every install of this app and run each unapplied `migrations/*.sql` file in that tenant's app schema. Per-tenant failures isolate to that tenant; other tenants continue. (Nothing here invokes `migrate_command`.)

End-to-end ~7–10s for a small app.

Redeploying the same `(app_id, version)` is **not** a DB no-op: the pipeline runs a plain `INSERT INTO v2_app_versions` with no uniqueness constraint on `(app_id, version_label)`, so every redeploy of `1.0.0` adds another version row. It is effectively idempotent for the *running service* (swarm-service-update + image-pull, useful for dev iteration) but it clutters version history and rollback. Bump the semver for anything you intend to keep.

---

## 6. Rollback + version history

```bash
# describe an app
GET  /api/dev/v2/apps/<app_id>

# all versions
GET  /api/dev/v2/apps/<app_id>/versions

# rollback to previous version
POST /api/dev/v2/apps/<app_id>/rollback
```

Rollback flips `v2_app_installs.installed_version_id` to the prior `v2_app_versions.id` and updates the swarm service's image. URL stays the same.

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
- **Never edit an applied file.** The runner re-hashes each file and a sha256 mismatch fails that tenant. It does not currently fail the *deploy* (the new version still activates), so the app goes live with one tenant stuck. Add `0002_*.sql` instead.

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

Two additives are context-sensitive — the script is analysed as a whole:

- plain `CREATE INDEX` **on a table created earlier in the same script** → additive. On a pre-existing table → **destructive** ("locks the table; use CONCURRENTLY").
- `ALTER COLUMN … SET NOT NULL` **on a column added earlier in the same script** → additive. On an existing column → **destructive**. The rule is *fresh column*, not "has a default".

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

Validate locally before you deploy:

```bash
manaurum app validate-migration migrations/                       # whole dir, same order as the deploy
manaurum app validate-migration migrations/0002_add_line_items.sql
manaurum app validate-migration migrations/ --breaking            # mirrors migration.breaking: true
```

It runs the exact same validator the deploy pipeline runs, so green here means green there.

### Runtime is read/write, not DDL

At runtime your container reads `DATABASE_URL` — a per-(app, tenant) `appusr_*` **login** role, `NOSUPERUSER NOBYPASSRLS`, granted `USAGE` on exactly one schema plus `SELECT/INSERT/UPDATE/DELETE` on its objects. It holds **no `CREATE`**, so runtime DDL is impossible: a `CREATE TABLE IF NOT EXISTS` on boot — a common framework default — dies with `permission denied for schema app_<slug>__<hex>`. Schema changes happen only through `migrations/*.sql`.

The role's `search_path` is locked to your schema, so write plain unqualified SQL. Your schema is already per-tenant, so there is no `tenant_id` column to filter on and no RLS to satisfy.

**Your container serves exactly one tenant.** The platform runs a separate Swarm service per (app, tenant) — the service DNS name is derived from both — and injects a fixed `MANAURUM_TENANT_ID` that never changes for the life of that container. So process-local state (in-memory caches, module globals, connection pools) is already single-tenant: you do **not** need to key caches by tenant, and doing so adds complexity that buys nothing. What you must still not assume is that `sub` is stable-shaped — treat it as opaque TEXT (see the user-context section).

### `migrate_command` does nothing

`migrate_command` is in the manifest schema, but Core has **no call site for it** — nothing executes it. An app whose schema depends on it deploys green and its tables simply never exist. Use `migrations/*.sql`.

---

## 8. Visibility + App Store v2

```json
"visibility": { "mode": "private" | "public" | "allow_list", "tenants": [...] }
```

- `private` (default) — only the home tenant sees the app. Auto-installed implicitly.
- `public` — listed in `/api/app-store/v2/catalogue` for every tenant. Tenant admins can `POST /api/app-store/v2/install` to install.
- `allow_list` — listed only for tenants in `tenants[]` (UUIDs).

Install rows live in `v2_app_installs`. Uninstall is soft (sets `tombstoned_at`). The capability gateway gates capability calls on whether the calling app is installed in the calling tenant.

App Store v2 is a separate frontend slice (A-1 backend shipped 2026-05-07; UI pending). Until the UI ships, install via the API directly:

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

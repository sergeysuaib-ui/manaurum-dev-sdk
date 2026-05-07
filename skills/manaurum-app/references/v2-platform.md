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

```json
{
  "manifest_version":     "2",
  "manaurum_sdk_version": "2",
  "app_id":               "my-app",
  "name":                 "My App",
  "version":              "1.0.0",
  "description":          "Short description shown in the App Store.",
  "runtime": {
    "mode":                  "hosted",
    "egress_allowed_hosts":  ["api.openai.com", "api.stripe.com"]
  },
  "visibility": {
    "mode":    "public",
    "tenants": []
  },
  "requires_capabilities": [
    { "name": "os.kv.get",     "version": "1" },
    { "name": "os.files.upload","version": "1" }
  ],
  "migrate_command": ["python", "-m", "myapp.migrate"],
  "migration": {
    "breaking":          false,
    "reason":            "add invoice.line_items table",
    "rollback_strategy": "drop new table"
  },
  "metadata": {
    "category":  "productivity",
    "icon_url":  "https://...",
    "support":   "mailto:dev@example.com"
  }
}
```

### Required fields

| Field | Type | Notes |
|---|---|---|
| `manifest_version` | string `"2"` | Pinned. |
| `manaurum_sdk_version` | string `"2"` | Pinned. |
| `app_id` | string | `^[a-z][a-z0-9-]{1,38}[a-z0-9]$`. Becomes the URL slug + `v2_apps.app_slug`. |
| `name` | string | Human-readable. Used in App Store + windowing. |
| `version` | string | Semver `MAJOR.MINOR.PATCH`. Bump on every redeploy. No pre-release / build metadata. |
| `runtime` | object | See § 2. |

### Optional top-level

| Field | Type | Notes |
|---|---|---|
| `description` | string | Shown in App Store listings. |
| `visibility` | object | `mode: "private" \| "public" \| "allow_list"`, optional `tenants: [uuid…]`. Default `private`. |
| `requires_capabilities` | array | Manifest-declared capability scope. The gateway can enforce this (when wired); also useful for App Store install prompts. |
| `migrate_command` | string[] | argv invoked once per `(app, tenant)` install/upgrade. The platform runs this with `MANAURUM_TARGET_SCHEMA` + broker DSN pre-set so your migrations land in the per-tenant app schema. |
| `migration.breaking` | bool | If `true`, the R-1.5 SQL validator allows destructive DDL (drop table, drop column, alter type). Default `false`. |
| `metadata` | object | Free-form for App Store rendering: `category`, `icon_url`, `support`, screenshots, etc. |

---

## 2. Runtime modes

```json
"runtime": { "mode": "hosted" | "byo" | "dev", "egress_allowed_hosts": [...] }
```

### `hosted` (default — what 99% of apps want)

The platform builds a Docker image from your `Dockerfile`, runs it as a Swarm service on `dokploy-network`, and routes `<app_id>.apps.manaurum.com` to it via Traefik with a Let's Encrypt cert.

Required files in your project:

- `Dockerfile` at the build context root
- `manifest_v2.json`
- Whatever else your `Dockerfile` `COPY`s in

Env vars the platform sets on every task:

| Env var | Use |
|---|---|
| `MANAURUM_TENANT_ID` | UUID of the installed tenant. |
| `MANAURUM_APP_ID` | UUID of your app in `v2_apps`. |
| `MANAURUM_VERSION` | Currently-running semver. |
| `MANAURUM_BROKER_URL` / `DATABASE_URL` | Postgres DSN for your dedicated schema (when `migrate_command` is set). |

### `byo` (bring your own — advanced)

You host the app yourself; the platform proxies signed requests to your endpoint. Useful when you have legacy infra you can't move. Requires a `byo_hosts` row registered via Workspace Admin → Integrations.

Manifest looks the same plus a `runtime.byo_endpoint_url`. Your endpoint must implement the BYO health-check contract (`GET /.well-known/manaurum-byo-health` → 200) and verify the platform's HMAC signature on capability dispatch. See R-5 documentation in the manaurum repo if you really need this; most apps shouldn't.

### `dev` (in-browser App Builder v2)

For rapid prototyping in the Monaco editor inside the OS itself. Files live in `dev_apps` / `dev_app_files` tables; output served via `/api/dev/v2/dev-apps/<id>/serve/...`. Limited capability allow-list (no `os.payments.*`, no `os.http.fetch`, no `os.notifications.send_to_user`, no `os.cron.*`, no `os.events.emit`, no `os.apps.call`). Graduate to `hosted` for production.

### `egress_allowed_hosts`

List of external hostnames your app may reach via the `os.http.fetch` capability. **Empty list = default deny.** Anything else returns `412 egress_not_declared`.

The list is application-layer enforcement (gateway-checked). A future slice may add network-layer DROP rules; until then, raw container egress is unfiltered. Use `os.http.fetch` for any external HTTP you want auditable.

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

`POST /api/dev/v2/deploy` does these steps in order, all inside a single request:

1. **Manifest validation** — JSON Schema + cross-field rules.
2. **Migration validation** — R-1.5 AST validator checks SQL is additive-only (unless `migration.breaking: true`).
3. **Image build** — Docker Engine API `POST /build` with the tarball as the body. Errors here → `result.error` with the daemon's stderr.
4. **Image push** — to `manaurum-registry:5000/v2-app-<slug>:<version>`.
5. **DB writes** — upsert `v2_apps` (in home tenant) + insert `v2_app_versions` (FORCE-RLS).
6. **Swarm service** — create or update `v2-app-<slug>-<tenant_short>` on `dokploy-network`. Image rewritten to overlay-pull URL so workers on any node can pull.
7. **Traefik dynamic config** — write `/etc/dokploy/traefik/dynamic/v2-app-<slug>.yml`. Traefik reloads automatically.
8. **Per-tenant migrations** (if `migrate_command` set) — fan out to every install of this app, run the migration in that tenant's broker schema. Per-tenant failures isolate to that tenant; other tenants continue.

End-to-end ~7–10s for a small app.

The deploy is idempotent on the same `(app_id, version)`: redeploying the same version is a no-op for the DB but triggers a swarm-service-update + image-pull (useful for dev iteration).

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

If your app needs a Postgres schema:

1. Add `migrate_command: ["python", "-m", "myapp.migrate"]` (or whatever runs your migrations) to the manifest.
2. The platform sets `MANAURUM_TARGET_SCHEMA=app_<app_hex>__<tenant_hex>` and `MANAURUM_BROKER_URL=postgresql+asyncpg://manaurum_broker:...@db/webdesktop` as env when the command runs.
3. Your migrate-command script connects via `MANAURUM_BROKER_URL`, sets `search_path = '<MANAURUM_TARGET_SCHEMA>'`, and runs migrations.
4. The R-1.5 AST validator pre-scans your SQL and rejects destructive operations unless `migration.breaking: true`.

The broker role (`manaurum_broker`) has no access to Core tables. It can `CREATE TABLE` / `INSERT` etc. only inside the per-tenant app schema. RLS on Core tables further enforces this.

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

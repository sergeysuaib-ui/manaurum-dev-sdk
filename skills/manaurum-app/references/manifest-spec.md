# ManAurum App Manifest v1 (frozen)

This is the exact contract validated by `POST /api/dev/apps/deploy`. It mirrors `https://manaurum.com/standards/manifest_v1.schema.json`. Anything not in this document will be rejected by the deploy validator.

## Minimal manifest

```json
{
  "manifest_version": "1",
  "manaurum_sdk_version": "1",
  "slug": "my-app",
  "name": "My App",
  "version": "1.0.0",
  "entry_point": "index.html"
}
```

## Full manifest

```json
{
  "manifest_version": "1",
  "manaurum_sdk_version": "1",
  "slug": "my-notes",
  "name": "Notes",
  "version": "1.2.3",
  "icon": "icons/app.svg",
  "entry_point": "index.html",

  "window": {
    "default_width": 800,
    "default_height": 600
  },

  "permissions": [
    "auth.read_user",
    "db.read_own_entities",
    "db.write_own_entities"
  ],

  "entities": [
    {
      "type": "note",
      "storage": "shared",
      "fields": {
        "title":   { "type": "string",    "required": true },
        "body":    { "type": "string" },
        "tags":    { "type": "json" },
        "created": { "type": "timestamp", "indexed": true }
      }
    }
  ],

  "integrations": [
    { "name": "stripe", "kind": "external_service", "url": "https://js.stripe.com/v3/" }
  ],

  "metadata": {
    "category": "productivity",
    "tags": ["notes", "journal"]
  }
}
```

## Field reference

### Required

| Field | Rule |
|---|---|
| `manifest_version` | The literal string `"1"`. (Numeric `1` will be rejected.) |
| `manaurum_sdk_version` | The literal string `"1"`. |
| `slug` | URL-safe id, regex `^[a-z][a-z0-9-]{2,49}$`. 3–50 chars. Must start with a letter. |
| `name` | Human-readable, max 100 chars. |
| `version` | Semver `MAJOR.MINOR.PATCH`. No pre-release / build metadata in v1. |
| `entry_point` | Path to the entry HTML inside the bundle (e.g. `"index.html"`). NOT a URL. |

### Optional

| Field | Notes |
|---|---|
| `icon` | Either an emoji or a path inside the bundle (e.g. `"icons/app.svg"`). |
| `window.default_width` | Integer, 320–4000. |
| `window.default_height` | Integer, 240–4000. |
| `permissions` | Array of strings, unique. Only values from the v1 enum (below). |
| `entities` | Declared data shapes (below). |
| `integrations` | External dependencies (below). |
| `metadata.category` | Free string. |
| `metadata.tags` | Array of strings. |

## Permissions enum (v1)

Only these are accepted by the validator. Anything else → `400 rejected_manifest_invalid`.

| Permission | Grants |
|---|---|
| `auth.read_user` | Read the current user's identity from `manaurum:init` payload |
| `auth.read_workspace_members` | List members of the current workspace |
| `navigation.open_app` | Programmatically open another app |
| `navigation.close_self` | Close own iframe |
| `events.subscribe` | Subscribe to platform event streams |
| `db.read_own_entities` | Read declared entities |
| `db.write_own_entities` | Create / update / delete declared entities |
| `ai.use` | Call `manaurum.ai.complete` / `.vision` against the workspace's configured LLM (added v1.7) |

> **Note on `ai.use`:** in v1 the runtime does **not** enforce this permission — calls to `manaurum.ai.*` work whether you declare it or not. The declaration is for **transparency** (visible at install time, audit trails) and **forward compatibility** (when per-tier limits or a formal install-prompt are added, `ai.use` is the discriminator). Declare it if you call AI; the workspace admin's gate lives in Settings → Agents (`mode='disabled'` for an app surfaces as `AI_DISABLED` regardless of manifest).

## Entities

A declared schema for your app's persistent data. The platform stores rows in a tenant-scoped table (`app_records`) with RLS — your data is automatically isolated per tenant. You only see your own entities (filtered by `application_id` server-side).

```json
{
  "type": "note",
  "storage": "shared",
  "fields": {
    "title":   { "type": "string",    "required": true },
    "body":    { "type": "string" },
    "tags":    { "type": "json" },
    "created": { "type": "timestamp", "indexed": true }
  }
}
```

Entity rules:
- `type`: lowercase snake_case, `^[a-z][a-z0-9_]*$`.
- `storage`: only `"shared"` is allowed in v1. (`"dedicated"` is reserved.)
- `fields`: object of field name → `{type, indexed?, required?}`.
- Field types: `string`, `uuid`, `timestamp`, `integer`, `decimal`, `boolean`, `json`.
- `indexed: true` makes a field queryable for equality, range, and IN (slice 2.1+).
- `required: true` makes a field non-null.
- `immutable: true` (slice 2.2+) — every UPDATE on this entity is rejected with `405 EntityImmutable`. Use for append-only journals (e.g. `stock_movement`).
- `no_soft_delete: true` (slice 2.2+) — every soft-delete is rejected with `405 EntityNotSoftDeletable`. Combine with `immutable: true` for a strict append-only entity. Default false (deletable).

```json
{
  "entities": [{
    "type": "stock_movement",
    "immutable": true,
    "no_soft_delete": true,
    "fields": {
      "qty":         { "type": "decimal", "required": true },
      "occurred_at": { "type": "timestamp", "indexed": true, "required": true }
    }
  }]
}
```

## Integrations

Declares external runtime dependencies. The bundle scanner uses this list to allow CDN imports (`jsdelivr`, `unpkg`, `cdnjs` are platform-allowed without declaration; everything else must appear here).

```json
{
  "name": "stripe",
  "kind": "external_service",
  "url": "https://js.stripe.com/v3/"
}
```

- `name`: free string identifier.
- `kind`: `"cdn"` or `"external_service"`.
- `url`: optional URI.

If your bundle imports `@stripe/stripe-js` or fetches from `js.stripe.com` without declaring this, the scanner returns `422 rejected_bundle_url_disallowed` or `422 rejected_bundle_sdk_undeclared`.

## What's not in v1

These were in v0 / legacy docs but are NOT part of v1:

- `runtime.entrypoint` (URL) — replaced by bundle-relative `entry_point`.
- `runtime.sandbox` — sandbox attributes are set by the shell, not the manifest.
- `description.short` / `description.long` — moved to `metadata` only as free fields, no validation.
- `compatibility.min_shell_version` — not validated in v1.
- Permissions like `theme.read`, `storage.read`, `storage.write`, `files.read`, `files.write`, `toast.send`, `notifications.send`, `window.manage`, `tasks.suggest` — runtime SDK methods may still work but are NOT covered by v1 manifest validation. Use `db.*` for data; treat the rest as evolving.

## Connecting `entities[]` to `manaurum.db.*`

Declaring an entity in the manifest is the ONLY way to enable runtime CRUD against it. The deploy pipeline registers each declared entity in `application_data_models`, which the runtime checks on every `manaurum.db.create` / `update` call.

```json
{
  "entities": [
    {
      "type": "note",
      "fields": {
        "title":   { "type": "string",    "required": true },
        "body":    { "type": "string" },
        "created": { "type": "timestamp", "indexed": true }
      }
    }
  ]
}
```

At runtime:
- `app.db.create('note', { title: '…', body: '…', created: '…' })` — works.
- `app.db.create('todo', …)` — `422 EntityTypeNotDeclared` (no `todo` entity in manifest).
- `app.db.list('note', { sort_by: 'created' })` — works (`created` is `indexed: true`).
- `app.db.list('note', { sort_by: 'body' })` — `422 FieldNotIndexedError`.

See `sdk-api.md` → "Database API" for the full runtime contract.

> **Index trade-off.** Each `indexed: true` field writes a row into `app_record_indexes` on every `create` / `update` (the create response returns `index_rows_written`). Index only fields you actually sort or filter on.

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
- `storage`: `"shared"` (default, EAV-pivot) or `"dedicated"` (real PG table — see below).
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

## Dedicated storage (`storage: "dedicated"`)

`shared` storage (the default) writes every entity row into a single platform-wide `app_records` table — fast to set up, but every read/write goes through an EAV pivot. Fine for low-volume CRUD.

`dedicated` storage gives your entity a real PostgreSQL table — real columns, real indexes, real foreign keys, real `UNIQUE` constraints, all under the same RLS-FORCE tenant isolation as the rest of the platform. You declare it in the manifest; the deploy pipeline issues the DDL automatically. **No Alembic. No Core PR.**

Use `dedicated` when one of these is true:
- You'll write more than ~10k rows per tenant for this entity.
- You need a foreign key to another one of your entities.
- You need a per-tenant `UNIQUE` constraint (e.g. invoice numbers).
- You need a compound index (sort by `(vendor_id, issued_at)`).

Stick with `shared` if you're just storing a handful of rows of config-like data — the EAV path has zero migration cost.

### Full dedicated example

```json
{
  "entities": [
    {
      "type": "vendor",
      "storage": "dedicated",
      "fields": {
        "name":   { "type": "string", "required": true, "unique": true },
        "tax_id": { "type": "string", "indexed": true }
      }
    },
    {
      "type": "invoice",
      "storage": "dedicated",
      "fields": {
        "number":    { "type": "string",    "required": true, "unique": true, "indexed": true },
        "vendor_id": {
          "type": "uuid",
          "required": true,
          "indexed": true,
          "references": { "entity": "vendor", "on_delete": "restrict" }
        },
        "amount":    { "type": "decimal",   "required": true },
        "issued_at": { "type": "timestamp", "required": true, "indexed": true },
        "notes":     { "type": "string" }
      },
      "indexes": [
        { "on": ["vendor_id", "issued_at"] },
        { "on": ["issued_at", "number"], "unique": true }
      ]
    }
  ]
}
```

### Field-level extras (dedicated only)

| Property | Meaning |
|---|---|
| `unique: true` | Per-tenant `UNIQUE` (the platform always scopes uniqueness to `tenant_id` — your invoice numbers don't have to be unique against other tenants). Rejected on `shared`. |
| `references` | Foreign key to another entity in the same manifest. Object: `{ "entity": "<other_type>", "on_delete": "restrict" \| "cascade" \| "set_null" }`. Target entity must also be `dedicated`. Rejected on `shared`. |

### Entity-level `indexes[]` (dedicated only)

Compound (multi-column) indexes for sort and filter combinations:

```json
"indexes": [
  { "on": ["vendor_id", "issued_at"] },
  { "on": ["issued_at", "number"], "unique": true }
]
```

Each entry: `on` (array of field names) + optional `unique` (default false). Field names must exist on the same entity. Compound `unique` is also tenant-scoped.

### Cross-field rules (R1–R7)

These are checked by the validator post-schema; violations come back as `400 rejected_manifest_invalid`:

| Rule | What it enforces |
|---|---|
| R1 | `unique: true` only on `dedicated` entities. |
| R2 | `references` only on `dedicated` entities. |
| R3 | Entity-level `indexes[]` only on `dedicated` entities. |
| R4 | `references.entity` must point to a `dedicated` entity declared in the same manifest. |
| R5 | `references.on_delete: "set_null"` requires the FK field to be `required: false` (you can't null a NOT NULL column). |
| R6 | Every field listed in a compound `indexes[]` entry must exist on the entity. |
| R7 | No FK cycles between dedicated entities (self-FK is allowed for tree-shaped data like `parent_id`). |

### What you cannot change after first deploy

The diff engine classifies operations as **additive** or **destructive**. Additive = applied automatically on redeploy. Destructive = rejected with `rejected_destructive_change` unless you opt in (and even then, you'll lose data — they exist for development, not for production):

| Change | Class | Result |
|---|---|---|
| Add a new entity | additive | applied |
| Add a new field | additive | applied (if `required: true`, your existing rows must allow NULL — the platform will reject the deploy if there's data) |
| Add an index / unique / FK | additive | applied |
| Drop an entity | destructive | rejected |
| Drop a field | destructive | rejected |
| Drop / loosen a constraint | destructive | rejected |
| Change `storage` between `shared` and `dedicated` | always rejected | both directions |

Plan your schema before the first deploy. Storage tier is a one-way decision per entity.

### Runtime is the same

You access dedicated entities through the **exact same** SDK methods as shared ones — `app.db.create / get / list / update / delete`. The platform routes the call to the right backend behind the unchanged interface. Your bundle never knows the difference.

```js
// Looks identical whether `invoice` is shared or dedicated.
await app.db.create('invoice', { number: 'INV-001', vendor_id: vendorId, amount: 1234.56, issued_at: new Date().toISOString() });
const recent = await app.db.list('invoice', { sort_by: 'issued_at', order: 'desc', limit: 20 });
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

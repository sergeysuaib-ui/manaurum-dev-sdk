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
- `indexed: true` makes a field queryable for equality/range. v1 supports equality only.
- `required: true` makes a field non-null.

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

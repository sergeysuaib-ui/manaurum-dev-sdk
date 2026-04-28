# ManAurum SDK API Reference

## Protocol

All communication uses postMessage. Message format: `{ type: "manaurum:<event>", payload: { ... } }`

## Shell → App Events

### `manaurum:init` (sent once after iframe loads)

The exact payload depends on which shell loads the iframe:

- **Main desktop shell** (`IframeAppHost.tsx`) sends the rich payload below (theme, device, screen, etc.).
- **Tenant shell** (`/t/<slug>/apps/<slug>`, hosted bundle) sends a tenant-aware payload with the `tenant` block (NEW in v1.5).

**Tenant shell payload (v1.5+):**
```json
{
  "type": "manaurum:init",
  "payload": {
    "tenant":     { "id": "<uuid>", "slug": "<slug>" },
    "workspace":  { "id": "<uuid>" },
    "user":       { "id": "<id>", "nickname": "<id>" },
    "app":        { "slug": "<slug>", "version_id": "<uuid>" },
    "permissions": [],
    "windowId":    "<app_slug>"
  }
}
```

**Main-desktop shell payload (legacy + still in use):**
```json
{
  "type": "manaurum:init",
  "payload": {
    "theme": "smoothie",
    "device": "desktop",
    "platform": "desktop",
    "screen": { "width": 1920, "height": 1080 },
    "safeAreaInsets": { "top": 0, "bottom": 0, "left": 0, "right": 0 },
    "navigationMode": "window",
    "shell": {
      "hasTabBar": false,
      "hasBackButton": false,
      "tabBarHeight": 0
    },
    "user": { "nickname": "User Name" },
    "permissions": ["theme.read", "window.manage"],
    "windowId": "win_42"
  }
}
```

Your app MUST respond with `manaurum:ready` within 10 seconds in both cases.

To read the `tenant` block (only present in the tenant-shell variant), register a generic message callback — the SDK's `onReady(ctx)` does not yet expose `tenant`:

```javascript
app.onMessage(function (type, payload) {
  if (type === 'manaurum:init' && payload.tenant) {
    console.log('Tenant slug:', payload.tenant.slug);
    console.log('Workspace id:', payload.workspace.id);
    console.log('App version:', payload.app.version_id);
  }
});
```

Use `payload.tenant` for B2B kustomization (per-tenant branding, copy, config). Do NOT use it as a security filter — RLS already enforces tenant isolation server-side.

**Platform fields:**
| Field | Desktop | Mobile |
|-------|---------|--------|
| `platform` | `"desktop"` | `"mobile"` |
| `device` | `"desktop"` | `"mobile"` (legacy, prefer `platform`) |
| `safeAreaInsets` | All zeros | Device notch/home indicator insets |
| `navigationMode` | `"window"` | App's declared `navigationPattern` |
| `shell.hasTabBar` | `false` | `false` (tab bar hidden when app is open) |
| `shell.hasBackButton` | `false` | `true` |
| `shell.tabBarHeight` | `0` | `0` (tab bar hidden when app is open) |

### `manaurum:theme` (when user switches theme)
```json
{ "type": "manaurum:theme", "payload": { "theme": "xp" } }
```

## App → Shell Events

### `manaurum:ready` (required, no permission needed)
```json
{ "type": "manaurum:ready", "payload": {} }
```

### `manaurum:set-title` (requires `window.manage`)
```json
{ "type": "manaurum:set-title", "payload": { "title": "New Title" } }
```

### `manaurum:resize` (requires `window.manage`)
```json
{ "type": "manaurum:resize", "payload": { "width": 900, "height": 700 } }
```

### `manaurum:close` (requires `window.manage`)
```json
{ "type": "manaurum:close", "payload": {} }
```

### `manaurum:toast` (requires `toast.send`)
```json
{ "type": "manaurum:toast", "payload": { "type": "success", "message": "Saved!" } }
```
Types: `success`, `error`, `info`

### `manaurum:notification` (requires `notifications.send`)
```json
{
  "type": "manaurum:notification",
  "payload": {
    "event_type": "informational",
    "title": "Export ready",
    "body": "Your CSV export is ready to download",
    "priority": "normal",
    "interruption_level": "active",
    "deep_link": { "action": "open-export", "payload": { "id": "123" } }
  }
}
```
Types: `informational` (no action needed), `actionable` (requires deep_link.action)

### `manaurum:reminder` (requires `notifications.schedule`)
```json
{
  "type": "manaurum:reminder",
  "payload": {
    "title": "Follow up with client",
    "message": "Re: proposal discussion",
    "remind_at": "2026-04-10T14:00:00Z"
  }
}
```

### `manaurum:task-suggestion` (requires `tasks.suggest`)
```json
{
  "type": "manaurum:task-suggestion",
  "payload": {
    "title": "Review Q2 budget",
    "description": "Budget spreadsheet needs final review",
    "due_date": "2026-04-12",
    "priority": "high"
  }
}
```

## Storage API (App → Shell → Server)

Apps can persist data server-side. Data is scoped per app per user — each user has their own storage, synced across devices.

### `manaurum:storage-set` (requires `storage.write`)
```json
{
  "type": "manaurum:storage-set",
  "payload": {
    "key": "tasks",
    "value": [{"title": "Buy milk", "done": false}],
    "_reqId": "1"
  }
}
```
Key: string, max 200 chars. Value: any JSON (max 100KB). `_reqId` is optional — used to match async responses.

### `manaurum:storage-get` (requires `storage.read`)
```json
{
  "type": "manaurum:storage-get",
  "payload": { "key": "tasks", "_reqId": "2" }
}
```

### `manaurum:storage-delete` (requires `storage.write`)
```json
{
  "type": "manaurum:storage-delete",
  "payload": { "key": "tasks", "_reqId": "3" }
}
```

### `manaurum:storage-list` (requires `storage.read`)
```json
{
  "type": "manaurum:storage-list",
  "payload": { "prefix": "task", "_reqId": "4" }
}
```
Returns all keys matching the prefix. Omit prefix to list all keys.

### `manaurum:storage-response` (Shell → App)
All storage operations return an async response:
```json
{
  "type": "manaurum:storage-response",
  "payload": {
    "ok": true,
    "key": "tasks",
    "value": [{"title": "Buy milk", "done": false}],
    "_reqId": "2"
  }
}
```
On error: `{ "ok": false, "error": "Key not found", "_reqId": "2" }`

### Storage Limits
| Limit | Value |
|-------|-------|
| Max keys per app per user | 500 |
| Max value size | 100 KB |
| Max total per app per user | 5 MB |
| Key length | 1-200 chars |

### Storage Usage Pattern

```javascript
// Helper to promisify storage calls
function storageGet(key) {
  return new Promise((resolve) => {
    const reqId = Math.random().toString(36);
    const handler = (e) => {
      if (e.data?.type === 'manaurum:storage-response' && e.data.payload?._reqId === reqId) {
        window.removeEventListener('message', handler);
        resolve(e.data.payload);
      }
    };
    window.addEventListener('message', handler);
    window.parent.postMessage({
      type: 'manaurum:storage-get',
      payload: { key, _reqId: reqId }
    }, '*');
  });
}

function storageSet(key, value) {
  return new Promise((resolve) => {
    const reqId = Math.random().toString(36);
    const handler = (e) => {
      if (e.data?.type === 'manaurum:storage-response' && e.data.payload?._reqId === reqId) {
        window.removeEventListener('message', handler);
        resolve(e.data.payload);
      }
    };
    window.addEventListener('message', handler);
    window.parent.postMessage({
      type: 'manaurum:storage-set',
      payload: { key, value, _reqId: reqId }
    }, '*');
  });
}

// Usage
const data = await storageGet('tasks');
if (data.ok) {
  console.log(data.value); // [{title: 'Buy milk', done: false}]
}

await storageSet('tasks', [{title: 'Buy milk', done: true}]);
```

## Database API (App → Shell → Server)

Apps with declared `entities[]` in their manifest get a typed-record CRUD API at `manaurum.db.*`. Records live in the platform's `app_records` table with RLS FORCE on `tenant_id` — your app sees only its own records inside the current tenant. Cross-tenant access is structurally impossible (RLS, not just route filtering).

**Permission gating:** every method below requires `db.read_own_entities` (read paths) or `db.write_own_entities` (write paths) in the manifest.

**Pre-condition:** the `entity_type` you pass at runtime must appear in `manifest.entities[]`. Write paths (`create`, `update`) reject undeclared types with `422 EntityTypeNotDeclared`. Read paths (`get`, `list`, `delete`) tolerate a missing manifest entry but return empty / 404.

### `manaurum.db.create(entity_type, data)`

Creates one record.

```javascript
var note = await app.db.create('note', {
  title: 'Shopping list',
  body: 'Milk, eggs, bread',
});
// { id: '<uuid>', index_rows_written: <int> }
```

Returns the new `id` plus the count of secondary-index rows written (one per `indexed: true` field in your manifest).

### `manaurum.db.get(entity_type, record_id)`

Reads one record by id.

```javascript
var record = await app.db.get('note', noteId);
// { id, entity_type, data, created_at, updated_at }
```

`404` if the id does not exist (or has been soft-deleted, or belongs to another tenant).

### `manaurum.db.list(entity_type, options?)`

Paginated list. Soft-deleted rows are hidden.

```javascript
var page = await app.db.list('note', {
  page: 1,
  page_size: 50,
  sort_by: 'created',  // must be an `indexed: true` field, OR omit for default order
  sort_dir: 'desc',
  where: {
    status: 'open',                                  // scalar = equality
    created: { gte: '2026-04-01', lt: '2026-05-01' }, // range, single JOIN per field
    supplier_id: { in: ['uuid-1', 'uuid-2'] }         // IN list (max 100)
  },
});
// { rows: [...], page, page_size, total }
```

`options` fields:
| Field | Default | Notes |
|---|---|---|
| `page` | `1` | 1-indexed |
| `page_size` | server default | bounded by server cap |
| `sort_by` | none | must reference an `indexed: true` field; else `422 FieldNotIndexedError` |
| `sort_dir` | `'asc'` | `'asc'` or `'desc'`; else `422 InvalidSortDirectionError` |
| `where` | `none` | structured filter map (v1.5+, see below) |

**Filters (v1.5+, slice 2.1).** `where` is a map of `{field: <value-or-ops>}`.

- `{field: scalar}` — equality (back-compat shape).
- `{field: {op: value, ...}}` — one or more operators on that field. Multiple operators on the same field are AND-combined (e.g. `{date: {gte, lt}}` → range).
- Filtered fields **must** be declared `indexed: true` in the manifest, just like `sort_by`.

| Operator | Value type | Notes |
|---|---|---|
| `eq` | scalar | identical to the scalar shape; rare to use explicitly |
| `gt`, `gte`, `lt`, `lte` | scalar | range; combine with another op on the same field for bounded ranges |
| `in` | list | non-empty, max **100** items; each item coerces to the field's type |

Anything outside that enum (e.g. `between`, `like`, `not_eq`) returns `422 FilterOperatorError`. `null` values are not allowed (no `IS NULL` operator in v1).

### `manaurum.db.aggregate(entity_type, options)` (v1.6+, slice 2.3)

Single-round-trip GROUP BY over an indexed field. Built for dashboards (sums by supplier, counts by status, etc.) where the alternative would be `db.list` + client-side reduce over many pages.

```javascript
const r = await app.db.aggregate('reception_line', {
  metrics: ['COUNT(*)', 'SUM(qty)', 'SUM(line_total)'],
  group_by: 'canonical_item_id',
  where: { date: { gte: '2026-04-01' } }
});
// {
//   groups: [
//     { key: '<uuid>', metrics: { count: 12, sum_qty: '450.00', sum_line_total: '12345.67' } },
//     ...
//   ]
// }
```

`options` fields:
| Field | Notes |
|---|---|
| `metrics` | Required. Non-empty list (max **8**) of strings. v1 grammar: `COUNT(*)`, `SUM(<field>)`, `AVG(<field>)`. |
| `group_by` | Required. Field name; must be `indexed: true`. |
| `where` | Same shape as `db.list` (eq / gt / gte / lt / lte / in). |

Rules:
- `SUM` and `AVG` fields must be `indexed: true` AND numeric (`integer` or `decimal`).
- `COUNT(field)` is **not** in v1 — use `COUNT(*)`.
- `MIN`/`MAX` are deferred (will arrive once we have planner data on the JSONB-backed pivot path).
- Hard cap of **1000 distinct groups**. Overflow rejects with `422 AggregateCardinalityExceeded` — refine your `where` or pre-bucket the data app-side.
- Numeric metric values come back as **strings** (Decimal-safe, no float precision loss). Coerce with `Number(...)` or a Decimal lib if needed.
- Group keys for UUID / timestamp fields come back as strings; numeric and string keys pass through as-is.

Wire format: `GET /api/app-data/{slug}/{entity}/_aggregate?metrics=<json>&group_by=<field>&where=<json>`. The SDK and bridge handle URL encoding.

### `manaurum.db.update(entity_type, record_id, data)`

**Full-replace** of the record's `data` field. Pass the entire object you want stored — fields you omit will be lost.

```javascript
await app.db.update('note', noteId, {
  title: 'Shopping list (updated)',
  body: 'Milk, eggs, bread, butter',
});
// { id, index_rows_written }
```

There is no partial-update endpoint in v1. Read with `get`, mutate locally, write back the full object.

### `manaurum.db.delete(entity_type, record_id)`

Soft-delete (sets `deleted_at`; the row stays in the database, hidden from `get` and `list`).

```javascript
await app.db.delete('note', noteId);
// { ok: true }
```

There is no hard-delete from the SDK in v1.

### Wire format

The SDK posts these messages; the shell forwards to `/api/app-data/...` under the parent's auth credentials. Iframe apps never see the user's bearer token.

| SDK method | postMessage `type` | HTTP route |
|---|---|---|
| `db.create` | `manaurum:db-create` | `POST /api/app-data/{app_slug}/{entity_type}` |
| `db.get` | `manaurum:db-get` | `GET /api/app-data/{app_slug}/{entity_type}/{record_id}` |
| `db.list` | `manaurum:db-list` | `GET /api/app-data/{app_slug}/{entity_type}?page=&page_size=&sort_by=&sort_dir=&where=<URL-encoded JSON>` |
| `db.aggregate` | `manaurum:db-aggregate` | `GET /api/app-data/{app_slug}/{entity_type}/_aggregate?metrics=<URL-encoded JSON>&group_by=&where=<URL-encoded JSON>` |
| `db.update` | `manaurum:db-update` | `PUT /api/app-data/{app_slug}/{entity_type}/{record_id}` |
| `db.delete` | `manaurum:db-delete` | `DELETE /api/app-data/{app_slug}/{entity_type}/{record_id}` |

Responses come back as `manaurum:db-response` with the SDK matching `_reqId` automatically — your app code only sees the resolved Promise.

### Errors

All errors arrive as a rejected Promise. The SDK surfaces the raw HTTP error text; the most common cases:

| HTTP | Cause | Fix |
|---|---|---|
| `404 application_not_found` | App slug not in this tenant | Confirm the user is in the tenant the app was deployed to |
| `404 record_not_found` | Record id unknown / soft-deleted / wrong tenant | Treat as not found |
| `422 EntityTypeNotDeclared` | `entity_type` not in `manifest.entities[]` (write paths only) | Add the entity to the manifest, redeploy with bumped semver |
| `422 FieldNotIndexedError` | `sort_by` references a field without `indexed: true` | Add `"indexed": true` to that field in the manifest, redeploy |
| `422 InvalidSortDirectionError` | `sort_dir` is not `'asc'` / `'desc'` | Use one of the two values |
| `422 InvalidPageError` | `page < 1` or non-integer | Send a positive integer |
| `422 FilterOperatorError` | Unknown operator in `where` (e.g. `between`), `in:[]`, or `in` over 100 items | Use one of `eq/gt/gte/lt/lte/in`; cap IN lists |
| `422 IndexValueCoercionError` | Value in `where` cannot coerce to the field's declared type (e.g. non-uuid for a uuid field) | Coerce client-side before sending |
| `400 where_must_be_json` / `where_must_be_object` | `where=` query param is not valid JSON, or is an array/scalar | Pass a JSON object |
| `405 EntityImmutable` | `update` on an entity declared `immutable: true` | Append a new record instead; do not mutate journal entries |
| `405 EntityNotSoftDeletable` | `delete` on an entity declared `no_soft_delete: true` | Reverse the journal with a compensating record instead |
| `422 InvalidMetricError` | Unknown function (`MEDIAN`/`MIN`/`MAX`), `COUNT(field)`, `SUM(*)`, malformed string, or duplicate metric in `db.aggregate` | Use `COUNT(*)` / `SUM(field)` / `AVG(field)`; field must be indexed numeric |
| `422 AggregateCardinalityExceeded` | `db.aggregate` produced > 1000 groups | Tighten `where`, or pre-bucket app-side |
| `400 metrics_must_be_json` / `metrics_must_be_array` | `metrics=` query param is not a JSON array | SDK handles encoding; this means a hand-rolled HTTP call sent the wrong shape |

### Tenant isolation reminder

`manaurum.db.*` is automatically tenant-scoped server-side via RLS. You do not — and cannot — pass a `tenant_id` in your queries. The current tenant is bound by the platform from the user's session. If you need the tenant identifier for display (B2B kustomization), read `payload.tenant` from the `manaurum:init` message instead.

## AI API — `manaurum.ai.*` (v1.7+, workspace LLM)

Apps call the workspace's configured LLM through `manaurum.ai`. The platform resolves the right provider+model from the workspace's agent profile (Settings → Agents), runs the call server-side, and writes a `llm_token_usage` row attributed to your app's `application_id` so admins see per-app spend in Workspace Admin → Apps. The iframe never sees the LLM API key.

If the workspace has no agent profile configured, calls reject with code `AI_NOT_CONFIGURED` so your app can prompt the user to set up AI in Settings. If the resolved provider doesn't support vision (e.g. Gemini in v1), `vision()` rejects with `VISION_UNSUPPORTED`.

No manifest permission is required for `manaurum.ai` in v1; the gate already lives in Settings → Agents (a workspace admin can set `mode='disabled'` for an app there to block all AI calls — surfaces as `AI_DISABLED`). A formal `ai.use` manifest permission is on the roadmap and will be additive.

### `manaurum.ai.complete({ prompt, system? })`

```javascript
const r = await app.ai.complete({
  prompt: 'Summarise: ' + entryText,
  system: 'Reply in one sentence.',
});
// r.text = "..."
// r.prompt_tokens, r.completion_tokens — token counts
// r.model, r.provider — what was actually used
```

### `manaurum.ai.vision({ prompt, image, system? })`

`image` is one of:

```javascript
// (a) reference an already-uploaded file in your app's stored_files
{ file_id: 'f_abc123' }

// (b) inline data URL (jpeg/png/gif/webp; max ~6 MB raw)
{ data_url: 'data:image/jpeg;base64,/9j/4AAQ...' }
```

```javascript
const draft = await app.ai.vision({
  prompt: 'Extract supplier and items as JSON. Schema: {"supplier_name": str, "lines": [{"name": str, "qty": num, "price": num}]}.',
  image: { file_id: uploadedFileId },
});
// draft.text — model output (often JSON to parse)
```

When using `file_id`, the platform verifies the file's `app_id` matches your app's slug — app A cannot OCR app B's images.

Provider support for `vision` in v1: openai (gpt-4o family), openrouter, anthropic (claude-3 family), deepseek, glm. Other providers reject with `VISION_UNSUPPORTED`.

### Wire format

| SDK method | postMessage `type` | HTTP route |
|---|---|---|
| `ai.complete` | `manaurum:ai-complete` | `POST /api/app-ai/{app_slug}/complete` |
| `ai.vision` | `manaurum:ai-vision` | `POST /api/app-ai/{app_slug}/vision` |

Responses come back as `manaurum:ai-response` with `_reqId` matched automatically. Default timeout is 90 seconds (provider round-trip).

### Errors

| Code | When |
|------|------|
| `AI_NOT_CONFIGURED` | Workspace has no agent profile and no legacy fallback |
| `AI_DISABLED` | Admin set `mode='disabled'` for this app in Settings → Agents |
| `VISION_UNSUPPORTED` | Resolved provider doesn't support vision in v1 |
| `IMAGE_INVALID` | `vision()` got malformed `image` (missing both fields, bad data URL, oversized) |
| `IMAGE_MIME_UNSUPPORTED` | Image is not jpeg/png/gif/webp |
| `NOT_FOUND` | Slug not active in this tenant, or `file_id` doesn't belong to this app |
| `TIMEOUT` | Provider didn't respond within 90s |
| `NOT_READY` | Called before `onReady` fired |

## SDK Methods (wraps postMessage)

### Lifecycle
| Method | Description |
|--------|------------|
| `ManaurumSDK.init()` | Create SDK instance. Call once. |
| `app.onReady(callback)` | Called with context when init completes |
| `app.onThemeChange(callback)` | Called when user switches theme |
| `app.isReady()` | Returns true if handshake completed |
| `app.getContext()` | Returns `{ theme, user, permissions, windowId }` |

### User (requires `user.profile.read`)
| Method | Returns |
|--------|---------|
| `app.getUserProfile()` | `{ nickname }` or null |
| `app.getTheme()` | `"smoothie"` or `"xp"` or null |

### Window (requires `window.manage`)
| Method | Description |
|--------|------------|
| `app.setTitle(title)` | Change window title |
| `app.resize(width, height)` | Resize window |
| `app.close()` | Close window |

### Toast (requires `toast.send`)
| Method | Description |
|--------|------------|
| `app.toast(type, message)` | Show toast |
| `app.toastSuccess(message)` | Success toast |
| `app.toastError(message)` | Error toast |
| `app.toastInfo(message)` | Info toast |

### Permissions
| Method | Description |
|--------|------------|
| `app.hasPermission(perm)` | Check if granted |
| `app.getPermissions()` | Get all granted |

## Permissions List

| ID | Label | Sensitive |
|----|-------|-----------|
| `user.profile.read` | Read display name | No |
| `theme.read` | Detect current theme | No |
| `window.manage` | Window title/resize/close | No |
| `toast.send` | Show toast notifications | No |
| `notifications.send` | Persistent notifications | No |
| `notifications.schedule` | Schedule reminders | Yes |
| `tasks.suggest` | Suggest tasks | Yes |
| `storage.read` | Read stored data | No |
| `storage.write` | Save and delete stored data | No |

> **Note (v1.5):** the table above lists *runtime SDK capabilities* that may be available depending on the shell and platform. The **manifest validator** in v1 only accepts a smaller set (see `manifest-spec.md` for the canonical list: `auth.read_user`, `auth.read_workspace_members`, `navigation.open_app`, `navigation.close_self`, `events.subscribe`, `db.read_own_entities`, `db.write_own_entities`). The legacy "public App Store + admin review" model is not part of v1 — apps deploy to a tenant catalog only.

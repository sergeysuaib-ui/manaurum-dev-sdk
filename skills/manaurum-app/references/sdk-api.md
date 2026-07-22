# ManAurum SDK API Reference

## Which runtime is this? (read first)

Two runtimes ship today with **different client SDKs on different transports**. Most of this file is v1. Pick your half before writing a line of code.

| | **Platform v2** (default for new apps) | **Legacy v1** (frozen) |
|---|---|---|
| Client SDK | `https://manaurum.com/sdk/manaurum-v2.mjs` — ES module, exports `ManaurumV2`, internal `VERSION = '2.2.0'` | `https://manaurum.com/sdk/manaurum.js` — classic script, global `ManaurumSDK` |
| Where the app runs | your own container, served at `https://<app_id>.apps.manaurum.com` | static bundle uploaded to Core, served same-origin |
| Data + capabilities | HTTP only: browser → your backend → `POST {MANAURUM_CORE_URL}/api/capability/<name>` | postMessage bridge (`manaurum:storage-*`, `db-*`, `file-*`, `ai-*`) |
| postMessage is used for | the ready handshake, window framing, and the Drive picker — **nothing else** | everything |

Section map:

| Section | Runtime |
|---|---|
| `manaurum:ready` — the shell handshake | **v1 and v2** (mandatory for both) |
| Platform v2 — frontend SDK (`manaurum-v2.mjs`) | v2 |
| Everything below the *Legacy v1* divider — Protocol, Shell → App Events, Storage, Database, AI, MUL, SDK Methods, Permissions List | v1 |

---

## `manaurum:ready` — the shell handshake (v1 AND v2, mandatory)

**If your app never replies `manaurum:ready`, it is unusable as a desktop window.** This is enforced by `frontend/src/components/window/IframeAppHost.tsx`, which hosts *both* runtimes — there is no `isV2` branch on this path.

### What the shell sends

The desktop renders `<iframe src="<entrypoint>">` and, on the iframe's `load` event, posts `manaurum:init` into it (`IframeAppHost.tsx:316-371`, `:699-702`) with `targetOrigin` set to the exact origin of your entrypoint.

For a v2 app the entrypoint is **derived by the platform**, not read from your manifest: `https://<app_id>.apps.manaurum.com/` (`lib/v2/deriveEntrypoint.ts:31-42`; the domain comes from `NEXT_PUBLIC_MANAURUM_APPS_DOMAIN`, default `apps.manaurum.com`). The one exception is `runtime.mode: "byo"`, where the manifest's `runtime.entrypoint` is used verbatim.

The payload as actually posted today (v1 and v2 share `sendInit`):

```json
{
  "type": "manaurum:init",
  "payload": {
    "theme": "smoothie",
    "appearance": "light",
    "accent": "core-blue",
    "device": "desktop",
    "platform": "desktop",
    "screen": { "width": 1440, "height": 900 },
    "safeAreaInsets": { "top": 0, "bottom": 0, "left": 0, "right": 0 },
    "navigationMode": "window",
    "shell": { "hasTabBar": false, "hasBackButton": false, "tabBarHeight": 0 },
    "user": { "nickname": "User" },
    "permissions": ["microphone"],
    "appId": "my-app",
    "offline_token": "",
    "granted_capabilities": ["os.kv.set", "os.kv.get"],
    "windowId": "win_42"
  }
}
```

- `theme` is **always** `"smoothie"` inside an iframe — the XP easter egg stops at the window frame (MAN-235). Style off `appearance` (`light` / `dark`) and `accent` instead.
- `granted_capabilities` is sent **only to v2 apps** — the install's admin-approved grant list. `permissions` carries the manifest's `permissions[]` array (v2: browser features such as `microphone`; v1: the platform-permission enum).
- `offline` appears only when the manifest declares an `offline` block; `deepLink` only when the window was opened from a notification.

### What your app must reply

```js
window.parent.postMessage({ type: 'manaurum:ready' }, '*');
```

**Within 10 seconds of the window opening** — `READY_TIMEOUT_MS = 10_000` (`IframeAppHost.tsx:24`), timer at `:682-696`. Miss it and the shell paints an overlay across your UI: *"App is not responding — No `manaurum:ready` received within 10s"* (`:814-836`). Your app is still running underneath; the user just cannot see or use it.

For the shell to accept the reply, all of these must hold (`:394-409`):

1. `event.origin` equals the origin the shell derived for your entrypoint. Serve from the host the platform expects; a BYO app on a host that doesn't match `runtime.entrypoint` has every message silently dropped.
2. `event.source` is the iframe's own `contentWindow`. Post from your top-level document — a message relayed from a nested iframe or a worker is rejected.
3. `data.type` is a string starting with `manaurum:`.

A `payload` is optional; the shell reads none. (The v2 SDK sends `{ sdk_version: '2.2.0' }`.)

### The pattern that actually shipped

An SPA whose bundle is deferred can miss `manaurum:init` entirely — the listener does not exist yet when the shell posts. The fix that landed for the first-party app **Libi** (MAN-1321) is belt-and-braces: an inline listener in `<head>`, plus one proactive announcement after mount.

```html
<!-- index.html <head> — alive before the deferred module bundle loads -->
<script>
  window.addEventListener('message', function (e) {
    if (e.data && e.data.type === 'manaurum:init') {
      window.parent.postMessage({ type: 'manaurum:ready' }, '*');
    }
  });
</script>
```

```ts
// main.tsx — after ReactDOM.createRoot(...).render(...)
try {
  window.parent.postMessage({ type: 'manaurum:ready' }, '*');
} catch {
  /* not embedded in the shell */
}
```

A proactive `manaurum:ready` is safe: the shell registers its listener when the host component mounts, before it sends `init`.

If you load `manaurum-v2.mjs` (v2) or `manaurum.js` (v1) and call `init()`, the SDK answers for you — but only *after* `manaurum:init` arrives, because it replies to `event.origin`. Keep the inline listener anyway if your bundle is deferred.

> **The trap.** Your standalone URL `https://<slug>.apps.manaurum.com/` works perfectly without the handshake — no shell, no timeout, no overlay. The failure appears *only* inside the desktop window and the mobile home screen, which is where your users are. Libi shipped this way and needed a follow-up release (MAN-1321). Test from the desktop, not just from the tab.

### Cross-origin rules (v2 specifically)

A v2 app served from `<slug>.apps.manaurum.com` is a **different origin** from the shell at `manaurum.com`. Consequences:

- postMessage is the only channel. No shared DOM, no shared `localStorage`, no `document.domain` tricks.
- You cannot read the shell's origin from inside the frame. Either reply with `'*'` (fine — `manaurum:ready` carries nothing secret), or capture `event.origin` off `manaurum:init` and reply to exactly that, which is what both SDKs do.
- The shell posts `manaurum:init` with your origin as `targetOrigin`, so no other embedder can receive it.
- The iframe sandbox is `allow-scripts allow-forms allow-same-origin` (`IframeAppHost.tsx:211`). `allow-modals` is never emitted — `alert()` / `confirm()` / `prompt()` are dead in the shell (and work fine on your standalone URL, so "it worked in my browser" proves nothing).
- Browser features are delegated through the iframe `allow` attribute only when your manifest declares them in `permissions[]` (`:210`, `:218-222`, `:919`). See `references/v2-platform.md`.

### Which messages a v2 app may send

Window framing only. `V2_ALLOWED_MESSAGES` (`IframeAppHost.tsx:71-85`):

| Type | Effect |
|---|---|
| `manaurum:ready` | the handshake above |
| `manaurum:set-title` | `{ title }` — rename the window |
| `manaurum:resize` | `{ width, height }` — resize the window |
| `manaurum:close` | close the window |
| `manaurum:toast` | `{ type: 'success' \| 'error' \| 'info', message }` |
| `manaurum:active-record` | `{ entity_type, record_id, record_title? }` — tell the OS which record the user is looking at (camelCase also tolerated) |
| `manaurum:drive-pick` | open the shell's Drive picker — see `app.pickFromDrive()` below |

None of these are permission-gated for v2 — they are framing, not data access.

**Rejected outright** — every type starting with `manaurum:storage-`, `manaurum:file-`, `manaurum:db-`, `manaurum:share-`, `manaurum:shared-`, `manaurum:notification`, `manaurum:reminder`, `manaurum:task-suggestion` (`:93-102`). Those are the v1 bridge. From a v2 iframe the shell refuses them and, when the message carried a `_reqId`, replies on the matching `*-response` channel with:

```json
{ "ok": false, "error": "v2 apps call capabilities via app.fetch() to their own backend, not via postMessage. (manaurum:storage-get)" }
```

`manaurum:notification` / `reminder` / `task-suggestion` have no response channel, so they are dropped with nothing sent back — the call just never resolves. Do the equivalent work over HTTP: your container calls the capability gateway.

`manaurum:ai-complete` / `manaurum:ai-vision` are in neither list, so from a v2 frame they fall through to the v1 bridge. That is an accident of the routing, not a contract — use `os.ai.*` through the gateway instead.

---

## Platform v2 — frontend SDK (`manaurum-v2.mjs`)

An ES module served from `https://manaurum.com/sdk/manaurum-v2.mjs` (also at `/sdk/manaurum-v2.mjs` on any Manaurum host). It is **thin on purpose**: it does the handshake, exposes the shell's theme/device context, wraps `fetch` with sane defaults, and opens the Drive picker. It has **no** capability client — v2 capabilities are called by your *container*, not by your page.

```js
import { ManaurumV2 } from 'https://manaurum.com/sdk/manaurum-v2.mjs';

const app = ManaurumV2.init();   // singleton; safe to call repeatedly

app.onReady((ctx) => {
  document.documentElement.dataset.appearance = ctx.appearance; // 'light' | 'dark'
  render(ctx.user?.nickname);
});

const res    = await app.fetch('/api/orders');
const orders = await res.json();
```

`ManaurumV2.init()` constructs the app instance on first call and returns the same instance thereafter. The constructor immediately registers the `message` listener, so calling `init()` early (before your UI mounts) is what makes the handshake land in time.

### Exported surface

`ManaurumV2` (the module's only export) has exactly two members: `init()` and the `version` getter.

**Callbacks** — all fire-and-forget; a throwing callback is caught and logged as `[ManaurumV2]`, it does not break the SDK.

| Method | Fires |
|---|---|
| `app.onReady(cb)` | once `manaurum:init` arrives, with the context object. **If init already arrived, `cb` runs immediately** — registering late is safe. |
| `app.onThemeChange(cb)` | on `manaurum:theme-change`, with the theme name. Note: the SDK listens for `manaurum:theme-change`, not the legacy `manaurum:theme`. |
| `app.onDeviceChange(cb)` | on `manaurum:device-change`, with `{ device, platform, screen, safeAreaInsets, navigationMode }`. The shell fires it only when the mobile/desktop classification or the safe-area insets actually change — a same-class resize is a no-op. |
| `app.onAuthFailure(cb)` | when an `app.fetch(...)` response has status **401**, with the `Response`. The SDK does **not** redirect — you own the "session expired, reload to log in" UX. The caller still receives the Response. |

**Context and getters**

| Member | Value |
|---|---|
| `app.context` | the whole context object, or `null` before init |
| `app.theme` | `'smoothie'` (always, inside the shell) or `null` |
| `app.appearance` | `'light'` / `'dark'` or `null` |
| `app.accent` | e.g. `'core-blue'` or `null` |
| `app.device` | `'mobile'` / `'desktop'` — defaults to `'desktop'` before init |
| `app.platform` | `'mobile'` / `'desktop'` — mirrors `device` today, kept separate for a future native/web split |
| `app.isMobile` | `true` only when `device === 'mobile'`; `false` before init |
| `ManaurumV2.version` | the SDK version string — useful in diagnostic logs |

`app.context` is built from the init payload with defaults: `{ theme, appearance, accent, user, permissions, windowId, appId, device, platform, screen, safeAreaInsets, navigationMode, shell }`.

Two gaps worth knowing:

- **`granted_capabilities` is not in `app.context`.** The shell sends it; SDK 2.2.0 does not read it. Same for `offline` and `deepLink`. If you need them, add your own `window.addEventListener('message', …)` for `manaurum:init` / `manaurum:deep-link` alongside the SDK.
- `appId` falls back to parsing `<slug>.apps.manaurum.com` out of `window.location.hostname` when the shell omits it — so a hand-loaded test page on any other host gets `appId: null`.

### `app.fetch(path, init?)`

Calls your own backend through the Core gateway. Returns a normal `Response`, so `.json()` / `.text()` / `.blob()` all work.

```js
const res = await app.fetch('/api/orders', {
  method: 'POST',
  body: JSON.stringify({ sku: 'A1' }),
  headers: { 'Content-Type': 'application/json' },
});
```

- `path` must be a `/`-rooted relative path (stays same-origin, so Traefik routes it to Core → your container) **or** an absolute `https://` URL (passes through unchanged; external hosts are still subject to the gateway's egress rules). Anything else throws `TypeError`.
- Defaults applied: `credentials: 'include'` so the Manaurum session cookie reaches Core, and `Accept: application/json` unless you set it. Pass `{ credentials: 'omit' }` for an explicit anonymous probe.
- **Your relative path must be declared in `manifest.runtime.api_routes`** or the gateway answers `404 route_not_declared` and your container never sees the request. Routes declared `auth: "user"` get a 60s `user_context` JWT minted by Core and injected as `X-Manaurum-User-Context`; `auth: "anonymous"` routes are proxied with none. The end user's own bearer is never forwarded to your container.
- **Retries are off by default.** Opt in per call with an SDK-specific `retry` key, which is stripped before the init dict reaches `window.fetch`:

  ```js
  await app.fetch('/api/report', { retry: { attempts: 3, baseDelayMs: 200 } });
  ```

  Only `GET` / `HEAD` / `OPTIONS` retry unless you pass `retry: { …, force: true }` — replaying a POST without an idempotency key risks a double write. Only 5xx and 429 are treated as transient; other 4xx return immediately. Backoff is exponential with full jitter (`200ms`, `400ms`, `800ms`…), capped at 5s per wait. A thrown network error is re-thrown on the last attempt.
- On a 401 the `onAuthFailure` callbacks fire before the Response is returned.

### `app.pickFromDrive({ accept? })`

Opens the OS file picker over the **user's** Drive (MAN-608 B3). The *shell* renders the picker and the *user* chooses; your app never enumerates the Drive and never needs a Drive-listing capability for this path.

```js
const res = await app.pickFromDrive({ accept: ['image/', 'application/pdf'] });
if (!res.cancelled) {
  const bytes = await fetch(res.files[0].download_url);
}
```

- `accept` is an optional list of MIME types or prefixes ending in `/`. The shell truncates it to 20 entries.
- Resolves to `{ cancelled: true }` if the user cancels, if another pick is already open (`picker_busy`), or if nothing answers within **120 s**. Otherwise `{ files: [...] }`.
- Each handle is `{ file_id, filename, mime_type, size_bytes, download_url, expires_at }`. `download_url` is attachment-pinned and short-lived (~5 min) — fetch it promptly and ask again rather than caching it.
- Wire: the SDK posts `manaurum:drive-pick` with a `_reqId` and awaits `manaurum:drive-pick-response`. It only works inside the shell — outside it there is no shell to post to and the promise resolves `{ cancelled: true }` after the timeout.

### What this SDK deliberately does not do

- **No capability client.** There is no `app.capability(...)`. Capabilities are called server-side by your container with `Authorization: Bearer ${MANAURUM_RUNTIME_TOKEN}` against `{MANAURUM_CORE_URL}/api/capability/<name>`. See `references/capabilities-reference.md`.
- **No storage / db / files / ai bridge.** Every `manaurum:storage-*`, `manaurum:db-*`, `manaurum:file-*` message documented below is v1 and is rejected for v2 frames.
- **No window-framing helpers.** `set-title` / `resize` / `close` / `toast` are allowed for v2 apps, but SDK 2.2.0 exposes no methods for them — post them yourself with `window.parent.postMessage({ type, payload }, shellOrigin)`.

---

## Legacy v1 — `manaurum.js` postMessage SDK

> Everything from here to the end of the file — **Protocol**, **Shell → App Events**, **App → Shell Events**, **Storage API**, **Database API**, **AI API**, **Component Library**, **SDK Methods**, **Permissions List** — describes **v1 only**. v1 is feature-frozen for existing apps. The `manaurum:ready` handshake and the window-framing messages are the only parts that also apply to v2, and they are documented above.

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

Your app MUST respond with `manaurum:ready` within 10 seconds in both cases — see "`manaurum:ready` — the shell handshake" above for the enforced contract. The main-desktop sample above is the v1-era shape; the shell has added `appearance`, `accent`, `appId`, `offline_token` and (for v2) `granted_capabilities` since, and the authoritative payload is the one listed in that section.

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
Required for v2 too — full contract in "`manaurum:ready` — the shell handshake" above.

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
| `include` | `none` | array of child entity names (v1.7+, see "Child-fetch" below) |

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

**Child-fetch (v1.7+, slice 2.4).** `include` hydrates each parent record with its children in one round-trip:

```javascript
const r = await app.db.list('reception', {
  page_size: 50,
  sort_by: 'created_at',
  sort_dir: 'desc',
  include: ['reception_line']
});
// r.rows[0].includes.reception_line = [{ id, data: { qty, reception_id }, ... }, ...]
```

Rules:
- **Shared entities (default):** convention-based FK — the child entity must declare a UUID field named `<parent_entity>_id` with `indexed: true`.
- **Dedicated entities (v1.13+):** explicit FK via the manifest's `references` declaration. The child entity must have exactly one field with `references: { entity: "<parent>" }` — ambiguity (two FKs to the same parent) is rejected with `400 invalid_include`. Dedicated `include` runs as **one** indexed `IN(...)` query per child type — no N+1.
- `include` is a non-empty list of distinct child-entity strings, max **4** entries.
- Up to **100 children per parent** are returned. If a parent has more, the extras are silently dropped — surface a server-side aggregate or paginate child-side instead.
- Nested includes are not supported. The hydrated child records always have `includes: null`.

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

### `manaurum.db.batch(ops)` (v1.8+, slice 3.1)

Run **multiple writes in one transaction**. All ops succeed together or all roll back together — there is no partial commit. Use this when an app-level invariant spans more than one record (e.g. flipping a header to `confirmed` AND inserting the matching stock movements; multi-step status transitions; bulk import).

```javascript
const { results } = await app.db.batch([
  { op: 'update', entity_type: 'reception',      record_id: rid, data: { status: 'confirmed' } },
  { op: 'create', entity_type: 'stock_movement', data: { reception_id: rid, sku: 'A1', qty: 5 } },
  { op: 'create', entity_type: 'stock_movement', data: { reception_id: rid, sku: 'B2', qty: 3 } },
]);
// results: [
//   { op: 'update', id: rid,         index_rows_written: 2 },
//   { op: 'create', id: '<new-id>',  index_rows_written: 3 },
//   { op: 'create', id: '<new-id>',  index_rows_written: 3 },
// ]
```

Op shapes:

| op | required | forbidden |
|---|---|---|
| `create` | `entity_type`, `data` | `record_id` |
| `update` | `entity_type`, `record_id`, `data` | — |
| `delete` | `entity_type`, `record_id` | `data` |

`update` is **full-replace** (same as `db.update`). `delete` is soft-delete.

**Cap: 50 ops per call.** Larger workloads must chunk; chunks are atomic individually but not collectively. For Receptions Confirm and similar workflows the cap is generous (typical = 1 header update + N line movements where N ≪ 50).

**Atomicity model.** All ops share one tenant-bound DB session — `commit()` runs once at the end. If any op fails (validation, EntityImmutable, RecordNotFound, etc.) the whole transaction rolls back; nothing you sent in that batch is persisted.

**Error shape.** Errors carry the failing op's index so your app can surface a precise message:

```json
{ "detail": { "at": 2, "error": "EntityImmutable: entity 'journal' is immutable" } }
```

Status codes match the underlying single-op error: `400` for shape problems, `404` for record-not-found, `405` for immutable / no-soft-delete, `422` for entity / field validation.

### Wire format

The SDK posts these messages; the shell forwards to `/api/app-data/...` under the parent's auth credentials. Iframe apps never see the user's bearer token.

| SDK method | postMessage `type` | HTTP route |
|---|---|---|
| `db.create` | `manaurum:db-create` | `POST /api/app-data/{app_slug}/{entity_type}` |
| `db.get` | `manaurum:db-get` | `GET /api/app-data/{app_slug}/{entity_type}/{record_id}` |
| `db.list` | `manaurum:db-list` | `GET /api/app-data/{app_slug}/{entity_type}?page=&page_size=&sort_by=&sort_dir=&where=<JSON>&include=<JSON>` |
| `db.aggregate` | `manaurum:db-aggregate` | `GET /api/app-data/{app_slug}/{entity_type}/_aggregate?metrics=<URL-encoded JSON>&group_by=&where=<URL-encoded JSON>` |
| `db.update` | `manaurum:db-update` | `PUT /api/app-data/{app_slug}/{entity_type}/{record_id}` |
| `db.delete` | `manaurum:db-delete` | `DELETE /api/app-data/{app_slug}/{entity_type}/{record_id}` |
| `db.batch` | `manaurum:db-batch` | `POST /api/app-data/{app_slug}/_batch` (body `{ops: [...]}`) |

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
| `400 include_must_be_json` / `include_must_be_array` | `include=` query param is not a JSON array | SDK handles encoding; means a hand-rolled HTTP call sent the wrong shape |
| `422 InvalidIncludeError` | unknown child entity, missing/non-uuid/non-indexed `<parent>_id` field, duplicate or over-cap (>4) entries | Add the FK field to the child entity in the manifest, redeploy |
| `400 batch_empty` | `db.batch([])` | Send at least one op |
| `400 batch_too_large` | `db.batch` over 50 ops | Chunk client-side; chunks are atomic individually |
| `400 invalid_op` / `missing_entity_type` / `missing_record_id` / `missing_data` / `record_id_forbidden_on_create` / `invalid_record_id` | Bad op shape — error includes `at: <index>` | Fix the offending op |

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

## Component Library (MUL) — `manaurum.mul.*`

manaurumOS ships a curated component library — 100 vanilla HTML/CSS/JS components (atoms, blocks, screens, patterns) sharing the Aurora-lite token vocabulary used by the OS shell. The SDK exposes thin read-only helpers (v1.9.0+) that wrap the public HTTP endpoints under `/api/library/*`.

Browse the catalogue: <https://manaurum.com/library>.

### `manaurum.mul.list()`

Returns the full compact registry (~40 KB) — array of `{id, level, category, tags, priority, status, use_when, avoid_when, supports, path}`.

```js
const all = await app.mul.list();
console.log(all.length); // 100
```

### `manaurum.mul.search(query, filters?)`

Client-side filter over the registry. `query` matches case-insensitively against id, category, tags, and `use_when`. `filters.level` narrows to one of `'atom' | 'block' | 'screen' | 'pattern'`; `filters.priority` narrows to `'P0' | 'P1' | 'P2' | 'P3'`.

```js
const cards   = await app.mul.search('card', { level: 'block' });
const buttons = await app.mul.search('button', { level: 'atom', priority: 'P0' });
```

### `manaurum.mul.get(id)`

Returns one component's manifest plus its single-file HTML.

```js
const c = await app.mul.get('button-primary-01');
// c.id, c.manifest, c.html (single-file HTML, paste-ready)
```

### Wire format

| SDK call | HTTP request |
|----------|--------------|
| `app.mul.list()` | `GET /api/library/registry` |
| `app.mul.get(id)` | `GET /api/library/components/{id}` |
| `app.mul.search(...)` | `GET /api/library/registry` then client-side filter |

### Build-time vs runtime

These helpers are unauthenticated same-origin fetches with no postMessage hop. **Use them at build time** (skill plugin / tenant-dev tooling) and inline the chosen component HTML into your bundle. Iframe apps with strict CSP `connect-src` won't be able to reach `/api/library/*` at runtime — that's by design; the library is curated and immutable per deploy, so a build-time bake gives you a smaller, faster, offline-tolerant app.

### Token rule

Component CSS uses `var(--token)` exclusively. Load the design tokens once at the top of your app to inherit the active theme automatically:

```html
<link rel="stylesheet" href="/api/library/tokens.css">
```

### Permissions

None. The library is curated and read-only — no permission needed in the v1 manifest enum.

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

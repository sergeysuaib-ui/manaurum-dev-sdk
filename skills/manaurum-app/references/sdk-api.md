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

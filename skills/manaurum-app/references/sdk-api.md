# ManAurum SDK API Reference

## Protocol

All communication uses postMessage. Message format: `{ type: "manaurum:<event>", payload: { ... } }`

## Shell → App Events

### `manaurum:init` (sent once after iframe loads)
```json
{
  "type": "manaurum:init",
  "payload": {
    "theme": "smoothie",
    "device": "desktop",
    "screen": { "width": 1920, "height": 1080 },
    "user": { "nickname": "User Name" },
    "permissions": ["theme.read", "window.manage"],
    "windowId": "win_42"
  }
}
```
Your app MUST respond with `manaurum:ready` within 10 seconds.

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

Sensitive permissions require admin review when the app is published to the public App Store.

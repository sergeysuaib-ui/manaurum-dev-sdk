---
name: manaurum-app
description: Build apps for ManAurum OS — a browser-based virtual desktop. Use this skill whenever the user wants to create, build, generate, or develop an app for ManAurum OS, SeregaOS, or mentions building iframe apps for a virtual desktop. Also triggers when user mentions ManAurum SDK, manaurum.js, or postMessage bridge apps. Covers app generation from prompts, manifest creation, SDK integration, theme support, and testing guidance.
---

# Build ManAurum OS Apps

You are helping the user build an app that runs inside ManAurum OS — a browser-based virtual desktop. Every app is a standalone HTML/JS page loaded in an iframe. The OS provides the window frame, theme, and user context via a postMessage bridge.

**You are NOT modifying ManAurum OS itself.** You are building an independent app that runs inside it.

## How ManAurum Apps Work

1. Your app is a regular web page (HTML + CSS + JS, any framework)
2. ManAurum loads it in a sandboxed iframe inside a desktop window
3. The OS sends `manaurum:init` with theme, user info, and permissions
4. Your app responds with `manaurum:ready` within 10 seconds
5. After that, your app can use SDK methods for window management, toasts, etc.

## SDK Integration

Add the SDK via script tag:
```html
<script src="https://manaurum.com/sdk/manaurum.js"></script>
```

Or as ES module:
```javascript
import { ManaurumSDK } from 'https://manaurum.com/sdk/manaurum.mjs';
```

Initialize and handle the handshake:
```javascript
var app = ManaurumSDK.init();

app.onReady(function(ctx) {
  // ctx.theme = "smoothie" or "xp"
  // ctx.user.nickname = user's display name
  // ctx.permissions = granted permissions array
  console.log('Connected to ManAurum OS!');
});

app.onThemeChange(function(theme) {
  // Adapt your UI to the new theme
  document.body.style.background = theme === 'xp' ? '#ece9d8' : '#f9f9ff';
});
```

## Available SDK Methods

Read `references/sdk-api.md` for the complete SDK reference including all methods, permissions, and event types.

## When Building an App

Follow this process:

### Step 1: Generate the app code

Create a single HTML file (or multi-file app) that:
- Includes the ManAurum SDK via script tag
- Calls `ManaurumSDK.init()` on load
- Handles `onReady` callback
- Handles `onThemeChange` for theme-aware styling
- Sends `manaurum:ready` (the SDK does this automatically)

### Step 2: Apply design guidelines

Read `references/design.md` for:
- Two themes: **Smoothie** (macOS-like: Inter font, #f9f9ff background) and **XP** (Windows XP: Tahoma font, #ece9d8 background)
- The app should adapt to both themes
- The OS provides the window title bar — do NOT render your own window chrome
- Be responsive to window resizing

### Step 3: Create the manifest

Read `references/manifest-spec.md` for the full manifest specification. The minimum manifest:

```json
{
  "manifest_version": 1,
  "app_id": "my-app-slug",
  "name": "My App Name",
  "version": "1.0.0",
  "runtime": {
    "type": "iframe",
    "entrypoint": "https://your-app-url.com",
    "sandbox": ["allow-scripts", "allow-forms", "allow-same-origin"]
  },
  "window": {
    "default_size": { "width": 800, "height": 600 },
    "min_size": { "width": 400, "height": 300 },
    "title": "My App Name"
  },
  "permissions": [],
  "description": { "short": "What your app does (max 160 chars)" }
}
```

### Step 4: Test locally

Tell the user:
1. Serve the HTML file with any local server (e.g. `python -m http.server 8000`)
2. Open the ManAurum Test Harness: `https://manaurum.com/sdk/test-harness.html`
3. Paste `http://localhost:8000` into the URL field and click "Load App"
4. Check: green dot = handshake succeeded, event log shows init→ready

### Step 5: Deploy

Read `references/publishing.md` for the full publishing flow. Quick summary:
1. Host the app at an HTTPS URL (Vercel, Netlify, Cloudflare Pages, etc.)
2. Go to ManAurum OS → Developer Console → Create App
3. Set the entrypoint URL to your hosted app
4. Click "Preview in SeregaOS" to test inside the real OS
5. The app auto-publishes as Private — visible only to you

## Permissions

Only request permissions your app actually needs:

| Permission | What it does |
|-----------|-------------|
| `user.profile.read` | Access user's display name |
| `theme.read` | Detect current theme (smoothie/xp) |
| `window.manage` | Change title, resize, close the window |
| `toast.send` | Show toast notifications |
| `notifications.send` | Send persistent notifications to Notification Center |
| `notifications.schedule` | Schedule reminders |
| `tasks.suggest` | Suggest tasks to Work Assistant |
| `storage.read` | Read stored data (server-side, per user) |
| `storage.write` | Save and delete stored data (server-side, 5MB per app) |

## Validation Rules

Your app will be validated before publishing:
- `app_id`: lowercase a-z, 0-9, hyphens only, 3-50 chars
- `version`: semver format (X.Y.Z)
- `entrypoint`: HTTPS URL (or localhost for draft testing)
- `window.default_size`: width 300-2000, height 200-1500
- `permissions`: only from the allowed list above
- `category`: one of productivity, utility, lifestyle, entertainment, dev_tools, other

Optional (recommended but not required to publish):
- `description.short`: 1-160 characters
- App icon (PNG, 256x256)
- Screenshots

**No review or approval needed.** Publishing is direct and immediate.

## Debugging Failed Apps

If a user's app doesn't work, use these APIs to diagnose:

### Probe the entrypoint (server-side HTTP check)
```bash
curl -s "https://manaurum.com/api/developer/apps/{slug}/probe-entrypoint" \
  -H "Authorization: Bearer $MANAURUM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://manaurum.com/hosted/{slug}/index.html"}'
```
Returns: `reachable`, `status_code`, `content_type`, `iframe_blocked`, `response_time_ms`

### Get diagnostic logs (from failed preview sessions)
```bash
curl -s "https://manaurum.com/api/developer/apps/{slug}/diagnostics" \
  -H "Authorization: Bearer $MANAURUM_TOKEN"
```
Returns: array of recent sessions with `status`, `events` timeline, `probe_result`

### Common failures
| Symptom | Cause | Fix |
|---------|-------|-----|
| Timeout, init sent but no ready | SDK not loaded or init() not called | Add `<script src="manaurum.js">` and call `ManaurumSDK.init()` |
| Error, no events | Entrypoint unreachable | Check URL, verify hosting works |
| Probe: iframe_blocked | X-Frame-Options: DENY | Remove header or set ALLOWALL |
| Probe: content_type is JSON | Wrong URL points to API | Change entrypoint to HTML page |

## Using Server-Side Storage

If the app needs to persist data (tasks, settings, notes, etc.), use the Storage API instead of localStorage. Storage is server-side, per user, and syncs across devices.

Add permissions to manifest:
```json
{ "permissions": ["storage.read", "storage.write"] }
```

Use this pattern in your app code:
```javascript
// Promise wrapper for storage
function storage(type, payload) {
  return new Promise((resolve) => {
    const _reqId = Math.random().toString(36);
    const handler = (e) => {
      if (e.data?.type === 'manaurum:storage-response' && e.data.payload?._reqId === _reqId) {
        window.removeEventListener('message', handler);
        resolve(e.data.payload);
      }
    };
    window.addEventListener('message', handler);
    window.parent.postMessage({ type, payload: { ...payload, _reqId } }, '*');
  });
}

// Save data
await storage('manaurum:storage-set', { key: 'tasks', value: myTasks });

// Load data
const result = await storage('manaurum:storage-get', { key: 'tasks' });
if (result.ok) {
  myTasks = result.value;
}

// Delete
await storage('manaurum:storage-delete', { key: 'old-data' });

// List all keys
const keys = await storage('manaurum:storage-list', {});
```

**Important:** Always include this storage helper when building apps that need persistence. Do NOT use `localStorage` as the primary store — it doesn't sync between devices and is cleared when the user clears browser data.

Read `references/sdk-api.md` for full Storage API reference with limits and error handling.

## What NOT to Do

- Do NOT try to access the parent window or break out of the iframe
- Do NOT render your own window title bar or controls
- Do NOT use permissions you don't need
- Do NOT hardcode theme colors — adapt to both themes
- Do NOT forget to handle `manaurum:init` — the app will show "not responding" after 10s

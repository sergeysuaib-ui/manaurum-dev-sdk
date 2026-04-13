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

## AI Assistant Integration (Optional)

ManAurum OS has an OS-level AI Assistant that can route user input to apps. When a user types "Spent $15 at doctor" into the Assistant, the AI splits it into actions and sends them to the right apps (Finance, Parent Space, Work Assistant, etc.).

**Third-party apps can participate.** Add an `agent` section to your manifest:

```json
{
  "agent": {
    "enabled": true,
    "capabilities": [
      {
        "name": "create_todo",
        "description": "Create a to-do item in the app",
        "input_schema": {
          "title": { "type": "string", "required": true, "description": "Task title" },
          "due_date": { "type": "date", "required": false, "description": "Due date YYYY-MM-DD" },
          "priority": { "type": "string", "required": false, "enum": ["low", "medium", "high"] }
        },
        "routing_hints": ["todo", "task", "remind", "need to", "buy"],
        "trust_default": "suggest",
        "example": { "title": "Buy groceries", "due_date": "2026-04-15" }
      }
    ],
    "emitted_events": ["todo.created", "todo.completed"],
    "subscribed_events": []
  }
}
```

**How it works:**
1. User types natural language (or speaks via voice) into the Assistant (sparkle icon in dock)
2. AI reads all registered app capabilities and decides where to route
3. Your app's capability is matched based on `description` + `routing_hints`
4. AI fills `input_schema` fields from the user's message
5. User sees a proposal with confidence score and confirms
6. OS sends `manaurum:agent-preview` to your iframe with `{ request_id, capability, fields }`
7. Your app validates, executes, and responds with `manaurum:agent-result`

**Handle agent messages in your app:**
```javascript
app.on('agent-preview', function(data) {
  // data.request_id — unique ID for this request
  // data.capability — "create_todo" (matches your manifest)
  // data.fields — { title: "Buy groceries", due_date: "2026-04-15" }

  var result = myApp.createTodo(data.fields);

  app.send('agent-result', {
    request_id: data.request_id,
    success: true,
    record_id: result.id
  });
});
```

**Key points:**
- `description` is what the AI reads — be specific and clear
- `routing_hints` are keywords that trigger matching — more is better
- `trust_default: "suggest"` means user must confirm; `"auto_save"` allows auto-execution for high confidence
- `input_schema` fields use the same types as manifest window/permissions
- `emitted_events` / `subscribed_events` enable cross-app automations (e.g. "when todo.completed, notify via calendar")
- Capabilities are registered in the OS when your app is installed — no extra setup needed

**System apps already registered:** Work Assistant (tasks, reminders), Parent Space (health events, notes), Finance (transactions). Your app joins the same routing engine.

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

## Mobile Platform Support

ManAurum OS runs on both desktop and mobile. Every app must explicitly declare platform support.

### Declaring Platform Support

Add a `platforms` section to the manifest:
```json
{
  "platforms": {
    "desktop": { "supported": true },
    "mobile": {
      "supported": true,
      "optimized": false,
      "supportLevel": "adaptive",
      "navigationPattern": "stack"
    }
  }
}
```

### Support Levels

| Level | Behavior |
|-------|----------|
| `full` | Dedicated mobile UI — app renders without banners, mobile entrypoint used if set |
| `adaptive` | Responsive design — renders without banners |
| `fallback` | Desktop UI shown with "Designed for desktop" warning banner |
| `none` | Launch blocked — "Desktop only" message shown |

### Navigation Patterns

Declare how the app navigates on mobile: `stack`, `tabs`, `list-detail`, `single-view`, or `composer-first`.

### Mobile Entrypoint

Set `platforms.mobile.entrypoint` to serve a completely different URL on mobile devices.

### Runtime Detection

The `manaurum:init` payload includes platform context:
```javascript
app.onReady(function(ctx) {
  if (ctx.platform === 'mobile') {
    // Mobile-specific layout
    // ctx.safeAreaInsets = { top, bottom, left, right }
    // ctx.navigationMode = "stack" (from your manifest)
    // ctx.shell.hasTabBar = true
    // ctx.shell.tabBarHeight = 72
  }
});
```

### App Store Badges

- `mobile.optimized = true` → "Optimized for Mobile" (green badge)
- `mobile.supported = true` → "Mobile" (blue badge)
- `mobile.supported = false` → "Desktop Only" (gray badge)

Apps with `mobile.supported = false` don't appear on mobile home screens.

### Mobile Best Practices

- Always declare `platforms` explicitly — the system never assumes
- Use viewport-relative units for layouts
- Test at 390x844px (common mobile viewport)
- Read `shell.tabBarHeight` to avoid content behind the system tab bar
- One primary job per screen on mobile
- No floating windows or desktop sidebars on mobile

## What NOT to Do

- Do NOT try to access the parent window or break out of the iframe
- Do NOT render your own window title bar or controls
- Do NOT use permissions you don't need
- Do NOT hardcode theme colors — adapt to both themes
- Do NOT forget to handle `manaurum:init` — the app will show "not responding" after 10s

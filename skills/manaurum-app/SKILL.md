---
name: manaurum-app
description: Build apps for ManAurum OS — a multi-tenant browser-based virtual desktop. Use this skill whenever the user wants to create, build, generate, or develop an app for ManAurum OS, SeregaOS, or mentions building iframe apps for a virtual desktop. Also triggers when user mentions ManAurum SDK, manaurum.js, or postMessage bridge apps. Covers app generation from prompts, manifest creation, SDK integration, theme support, multi-tenant context, and the new manifest+bundle Deploy API.
---

# Build ManAurum OS Apps (v1.5+ tenant-aware)

You are helping the user build an app that runs inside ManAurum OS — a **multi-tenant** browser-based virtual desktop. Each app is a standalone HTML/JS bundle loaded in a sandboxed iframe inside a tenant's workspace. The OS provides the window frame, theme, user info, and **tenant context** via a postMessage bridge.

**You are NOT modifying ManAurum OS itself.** You are building an independent app that runs inside one or more tenants.

## How ManAurum Apps Work in v1.5

1. Your app is a regular web bundle (HTML + CSS + JS, any framework, single `index.html` at the root).
2. A tenant developer deploys the bundle via the **Deploy API** (`POST /api/dev/apps/deploy`) using a tenant-scoped `mnu_*` token. The bundle becomes a versioned application in that tenant's catalog.
3. A workspace owner installs the app from their tenant's AppStore.
4. End users open the app at `/t/<tenant_slug>/apps/<app_slug>`. ManAurum loads the bundle in a sandboxed iframe.
5. The shell sends `manaurum:init` with theme, user info, permissions, **and a `tenant` block** so the app knows which operator it's rendering inside.
6. Your app responds with `manaurum:ready` within 10 seconds.
7. After that, your app uses SDK methods (window, toast, storage, files, etc.).

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

app.onReady(function (ctx) {
  // ctx.theme         = "smoothie" or "xp"
  // ctx.user.nickname = user's display name
  // ctx.permissions   = granted permissions array
  console.log('Connected to ManAurum OS');
});

app.onThemeChange(function (theme) {
  document.body.style.background = theme === 'xp' ? '#ece9d8' : '#f9f9ff';
});

// Multi-tenant: read tenant identity from the raw init message.
// (The SDK's ctx object doesn't yet expose `tenant` — read the raw payload.)
app.onMessage(function (type, payload) {
  if (type === 'manaurum:init' && payload.tenant) {
    console.log('Running inside tenant', payload.tenant.slug, payload.tenant.id);
    // payload.workspace.id, payload.app.slug, payload.app.version_id also present
  }
});
```

## Available SDK Methods

Read `references/sdk-api.md` for the complete SDK reference.

### Quick overview (v1.5 SDK):

**Tenant context (NEW in v1.5)** — read from `manaurum:init` payload:
- `payload.tenant.id`, `payload.tenant.slug` — which operator the user is in
- `payload.workspace.id` — which workspace
- `payload.app.slug`, `payload.app.version_id` — which version of which app

**Window, Toast, Notifications** — see `references/sdk-api.md`.

**Database (v1.6+)** — typed CRUD against entities declared in your manifest. Backed by `app_records` with RLS FORCE on `tenant_id`; cross-tenant access is structurally impossible. Methods: `app.db.create / get / list / update / delete`. Requires `db.read_own_entities` / `db.write_own_entities` permissions. See `references/sdk-api.md` → "Database API" for the full contract.

**AI (v1.7+)** — workspace-scoped LLM via `app.ai.complete({prompt, system?})` and `app.ai.vision({prompt, image, system?})`. The platform picks the configured provider+model from the workspace's agent profile, runs the call server-side, and bills tokens to your `application_id`. Your app **never** sees the API key. If no agent is configured, calls reject with `AI_NOT_CONFIGURED`. See `references/sdk-api.md` → "AI API" for the full contract.

**Legacy runtime APIs** (`storage.*`, `files.*`, `collections.*`, `toast.*`, `window.*`, `notifications.*`) — still callable from the SDK; not gated by the v1 manifest permission system. Use `db.*` for new persistent data; treat the rest as evolving.

**Deep Links** — `app.onDeepLink(callback)` fires with `{ action, payload }` when the app is opened from a notification.

## When Building a Tenant App

Follow this process:

### Step 1: Generate the app code

Create a single `index.html` (or multi-file bundle) that:
- Includes the ManAurum SDK via script tag
- Calls `ManaurumSDK.init()` on load
- Handles `onReady` callback and `onThemeChange`
- Reads `payload.tenant` from `manaurum:init` if you need tenant-aware behaviour (B2B kustomization, per-tenant branding, per-tenant config)
- Sends `manaurum:ready` (the SDK does this automatically)
- For data-backed apps: declare your entities in `manifest.entities[]` and call `app.db.create / get / list / update / delete` at runtime. See `references/sdk-api.md` → "Database API".
- For AI-driven apps (summarisation, OCR, classification, vision): call `app.ai.complete(...)` or `app.ai.vision(...)`. No API key handling needed — the platform resolves it from the workspace's agent profile. See `references/sdk-api.md` → "AI API".

### Step 2: Apply design guidelines

Read `references/design.md` for theme details. Two themes: **Smoothie** (Inter font, `#f9f9ff`) and **XP** (Tahoma font, `#ece9d8`). Adapt to both. The OS provides the window title bar — do NOT render your own window chrome.

### Step 3: Write the manifest (v1 schema)

Read `references/manifest-spec.md` for the full v1 schema. The minimum manifest:

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

Adding declared entities + permissions for data:

```json
{
  "manifest_version": "1",
  "manaurum_sdk_version": "1",
  "slug": "my-notes",
  "name": "Notes",
  "version": "1.0.0",
  "entry_point": "index.html",
  "permissions": ["db.read_own_entities", "db.write_own_entities", "auth.read_user"],
  "entities": [
    {
      "type": "note",
      "fields": {
        "title":   { "type": "string", "required": true },
        "body":    { "type": "string" },
        "created": { "type": "timestamp", "indexed": true }
      }
    }
  ]
}
```

Validation rules (key ones):
- `slug`: `^[a-z][a-z0-9-]{2,49}$`
- `version`: semver `X.Y.Z`
- `permissions`: only from the v1 enum (see manifest-spec.md)
- `entities[].type`: lowercase snake_case

### Step 4: Bundle and deploy

Read `manaurum-deploy/SKILL.md` for the full deploy flow. Quick form:

```bash
# bundle
cd my-app && zip -r bundle.zip .

# get a token from the platform: Developer Console → Tokens → Issue
# stored as MANAURUM_TENANT_TOKEN=mnu_prod_<32>

# deploy
B64=$(base64 -w0 bundle.zip)
jq -n --arg b "$B64" --slurpfile m manifest.json '{manifest: $m[0], bundle: $b}' \
  | curl -X POST https://manaurum.com/api/dev/apps/deploy \
      -H "Authorization: Bearer $MANAURUM_TENANT_TOKEN" \
      -H "Content-Type: application/json" \
      -d @-
```

Response on success:
```json
{
  "application_id": "...",
  "version_id": "...",
  "version_number": "1.0.0",
  "deployed_at": "2026-04-27T19:00:00Z",
  "url": "/t/<your-tenant-slug>/apps/my-app"
}
```

### Step 5: Install in workspace + open

A workspace owner inside the same tenant installs the app via AppStore. After install, any member of that workspace opens it at `/t/<tenant_slug>/apps/<app_slug>`. The shell loads the iframe and sends `manaurum:init` with tenant context.

## Tenant Context — what your app receives

On `manaurum:init`, the `payload` includes (NEW in v1.5):

```json
{
  "tenant":     { "id": "<uuid>", "slug": "<slug>" },
  "workspace":  { "id": "<uuid>" },
  "user":       { "id": "<id>", "nickname": "<id>" },
  "app":        { "slug": "<slug>", "version_id": "<uuid>" },
  "permissions": [...],
  "windowId":    "<app_slug>"
}
```

For B2B apps, use `payload.tenant.slug` (or `id`) to:
- Render tenant-branded UI (logo, accent colour, copy)
- Fetch tenant-specific configuration
- Distinguish telemetry across operators

Your data is **automatically tenant-scoped** by the platform's RLS — you do not need to filter by tenant in your queries; the platform does it server-side. `payload.tenant` is for *display* and *kustomization*, not for security.

> **Important on tokens.** A `mnu_*` token is bound to ONE tenant. Deploying the same app to a second tenant requires a separate token issued from THAT tenant's Developer Console.

## Permissions (v1 manifest enum)

Only these values are accepted by the manifest validator in v1. Anything else → deploy rejection (`rejected_manifest_invalid`).

| Permission | What it grants |
|---|---|
| `auth.read_user` | Read the current user's basic identity from `payload.user` |
| `auth.read_workspace_members` | List members of the current workspace |
| `navigation.open_app` | Programmatically open another app |
| `navigation.close_self` | Close own iframe |
| `events.subscribe` | Subscribe to platform event streams |
| `db.read_own_entities` | Read your declared entities (per `manifest.entities[]`) |
| `db.write_own_entities` | Create / update / delete your declared entities |

## Validation Rules (v1)

- `slug`: 3–50 chars, `^[a-z][a-z0-9-]{2,49}$`
- `version`: semver MAJOR.MINOR.PATCH
- `entry_point`: path inside the bundle (e.g. `index.html`), not a URL
- `window.default_width` / `default_height`: 320–4000 / 240–4000
- `entities[].type`: lowercase snake_case
- `entities[].storage`: `"shared"` (only allowed value in v1)
- Bundle: max 50 MB, zip with `index.html` at the root

## Common Failures

| Symptom | Cause | Fix |
|---|---|---|
| Deploy returns `401 rejected_token_invalid` | Bad / expired / revoked token | Issue a fresh `mnu_*` from Developer Console |
| Deploy returns `403 rejected_insufficient_scope` | Token lacks `app.deploy` scope | Issue a token with `app.deploy` (default) |
| Deploy returns `400 rejected_manifest_invalid` | Manifest fails v1 schema | Read `findings` array; fix and retry |
| Deploy returns `413 rejected_bundle_too_large` | Bundle > 50 MB | Trim assets / split / use external CDN |
| Deploy returns `422 rejected_bundle_*` | Anti-Lovable scanner caught a credential / undeclared SDK / disallowed URL | Remove the credential or declare via `integrations[]` |
| App opens but no `manaurum:ready` | SDK not loaded or `init()` not called | Add SDK script tag and call `ManaurumSDK.init()` |
| App URL returns `404` for a different tenant's user | Wrong tenant — install must exist in the user's workspace | Ask workspace owner of the user's tenant to install |

## What NOT to Do

- Do NOT try to access the parent window or break out of the iframe.
- Do NOT render your own window title bar or controls.
- Do NOT request permissions you don't need.
- Do NOT hardcode theme colors — adapt to both Smoothie and XP.
- Do NOT forget to handle `manaurum:init` — the app will show "not responding" after 10s.
- Do NOT include credentials, API keys, or undeclared 3rd-party SDKs in your bundle — the deploy scanner will reject.
- Do NOT use `tenant_id` from `payload.tenant` as a security filter in your client code — RLS already enforces. Use it only for display.

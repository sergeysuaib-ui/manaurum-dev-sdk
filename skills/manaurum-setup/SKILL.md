---
name: manaurum-setup
description: Set up a ManAurum OS development environment for tenant-aware apps (v1.5+). Use when user wants to start building for ManAurum/SeregaOS, needs to set up their project, scaffold an app, or initialize a new ManAurum app project from scratch.
---

# Set Up ManAurum OS App Project (v1.5+)

Help the user scaffold a new ManAurum OS app project from scratch, ready to deploy to a specific tenant via the Deploy API.

## Quick Setup

Create a minimal project structure:

```
my-manaurum-app/
├── index.html         ← Your app (loaded in ManAurum iframe)
├── manifest.json      ← v1 manifest (REQUIRED for deploy)
├── style.css          ← Optional
├── app.js             ← Optional
├── deploy.sh          ← Optional CLI helper (see /manaurum-deploy)
├── .env.manaurum      ← Token (gitignored)
└── .gitignore
```

## Starter `index.html`

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>My App</title>
  <script src="https://manaurum.com/sdk/manaurum.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { padding: 24px; transition: all 0.2s; }
    body.smoothie { font-family: 'Inter', -apple-system, sans-serif; background: #f9f9ff; color: #181c23; font-size: 14px; }
    body.xp { font-family: Tahoma, sans-serif; background: #ece9d8; color: #000; font-size: 12px; }
    h1 { margin-bottom: 12px; }
    .tenant-badge { font-size: 12px; opacity: 0.6; margin-top: 8px; }
  </style>
</head>
<body class="smoothie">
  <h1 id="title">Loading…</h1>
  <p id="info"></p>
  <p class="tenant-badge" id="tenant-badge"></p>

  <script>
    var app = ManaurumSDK.init();

    app.onReady(function (ctx) {
      document.body.className = ctx.theme;
      document.getElementById('title').textContent = 'Hello, ' + ctx.user.nickname + '!';
      document.getElementById('info').textContent = 'Theme: ' + ctx.theme;
    });

    app.onThemeChange(function (theme) {
      document.body.className = theme;
      document.getElementById('info').textContent = 'Theme: ' + theme;
    });

    // v1.5: read tenant context from raw init payload (B2B kustomization)
    app.onMessage(function (type, payload) {
      if (type === 'manaurum:init' && payload.tenant) {
        document.getElementById('tenant-badge').textContent =
          'Tenant: ' + payload.tenant.slug;
      }
    });
  </script>
</body>
</html>
```

## Starter `manifest.json`

Use this v1 schema as the baseline. Read `manaurum-app/references/manifest-spec.md` for the full reference.

```json
{
  "manifest_version": "1",
  "manaurum_sdk_version": "1",
  "slug": "my-app",
  "name": "My App",
  "version": "1.0.0",
  "entry_point": "index.html",
  "window": { "default_width": 800, "default_height": 600 },
  "permissions": []
}
```

To use server-side data, declare entities and add `db.*` permissions:

```json
{
  "manifest_version": "1",
  "manaurum_sdk_version": "1",
  "slug": "my-notes",
  "name": "Notes",
  "version": "1.0.0",
  "entry_point": "index.html",
  "permissions": ["db.read_own_entities", "db.write_own_entities"],
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

Manifest validation rules:
- `manifest_version` must be the literal `"1"` (string, not number)
- `slug`: 3–50 chars, `^[a-z][a-z0-9-]{2,49}$`
- `version`: semver `MAJOR.MINOR.PATCH`
- `permissions`: only the v1 enum (see manifest-spec.md)

## `.gitignore`

```
.env*
node_modules/
*.zip
.DS_Store
```

## `.env.manaurum`

```
MANAURUM_TENANT_TOKEN=mnu_prod_<32-chars>
```

Get the token at `https://manaurum.com` → Developer Console → Tokens → "Issue new token". Token is shown ONCE and bound to your active tenant.

## Local Development

```bash
# Serve locally
python -m http.server 8000
# or
npx serve .
```

Open `http://localhost:8000` in a browser to verify the page renders without errors. The SDK won't fully initialise outside the ManAurum shell — `onReady` won't fire — but you'll see syntax errors / asset 404s here.

For full handshake testing, use the Test Harness:
```
https://manaurum.com/sdk/test-harness.html?url=http://localhost:8000
```

## Multi-tenant context (v1.5+)

The shell sends a `tenant` block inside `manaurum:init`. Read it via `app.onMessage()`:

```javascript
app.onMessage(function (type, payload) {
  if (type === 'manaurum:init' && payload.tenant) {
    // payload.tenant.id, payload.tenant.slug
    // payload.workspace.id
    // payload.app.slug, payload.app.version_id
  }
});
```

Use it for B2B branding (per-tenant logo, copy, theme overrides). Do NOT use it as a security filter — RLS already enforces tenant isolation server-side.

## Using Frameworks

ManAurum apps work with any framework. Just load the SDK and follow the protocol.

### React / Vue / Svelte / vanilla JS

Same pattern: load `manaurum.js`, call `init()`, wire `onReady` / `onThemeChange` / `onMessage`. Bundle with whatever toolchain you like; just make sure `index.html` is at the root of your `bundle.zip`.

## Deploy Setup

To deploy directly from CLI:

1. Issue a tenant token (see `manaurum-deploy/SKILL.md` Step 1).
2. Save it in `.env.manaurum` as `MANAURUM_TENANT_TOKEN=...`.
3. Run `/manaurum-deploy`.

## Next Steps

After setup:
1. Build your app features.
2. Test locally / in the Test Harness.
3. Use `/manaurum-deploy` to deploy to your tenant.
4. Have a workspace owner install the app from AppStore so end users can open it.

---
name: manaurum-setup
description: Scaffold a new ManAurum OS app project. As of 2026-05, the default flow is Platform v2 (containerized hosted apps); v1 (iframe bundles) is supported for legacy apps. Use when the user wants to start building a new ManAurum/SeregaOS app, scaffold a project from scratch, or initialize a fresh app directory.
---

# Set Up a ManAurum App Project

> ## ⚡ v2 is the new default (2026-05)
>
> This skill scaffolds **v2 (containerized hosted)** projects by default. For legacy v1 (iframe bundle) projects, jump to the "Legacy v1 setup" section at the bottom.

---

## v2 setup (default)

### Project structure

```
my-app/
├── manifest_v2.json    ← REQUIRED — v2 manifest schema
├── Dockerfile          ← REQUIRED — produces the runtime image
├── index.html          ← (or whatever your runtime serves)
├── deploy.sh           ← Optional CLI helper (see /manaurum-deploy)
├── .env.manaurum       ← Token (gitignored)
└── .gitignore
```

### Starter `manifest_v2.json` (minimal)

```json
{
  "manifest_version": "2",
  "manaurum_sdk_version": "2",
  "app_id": "my-app",
  "name": "My App",
  "version": "1.0.0",
  "runtime": {
    "mode": "hosted",
    "egress_allowed_hosts": []
  },
  "visibility": {
    "mode": "private"
  }
}
```

Validation rules:

- `app_id`: slug `^[a-z][a-z0-9-]{1,38}[a-z0-9]$`. Becomes `<app_id>.apps.manaurum.com`.
- `version`: semver `MAJOR.MINOR.PATCH`. Bump on every redeploy.
- `runtime.mode`: `hosted` for default; `byo` (you host elsewhere, platform proxies) and `dev` (in-browser editor) are advanced.
- `runtime.egress_allowed_hosts`: list of external hosts your app may reach via `os.http.fetch`. Default-deny.

To use AI / declare a dedicated DB schema / migrations, see `manaurum-app/SKILL.md` and `references/v2-platform.md`.

### Starter `Dockerfile` (static page on nginx)

```dockerfile
FROM nginx:1.27-alpine
COPY index.html /usr/share/nginx/html/index.html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null || exit 1
```

For a Node app:

```dockerfile
FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
EXPOSE 8080
CMD ["node", "server.js"]
```

For a Python (FastAPI):

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

The platform reads your `EXPOSE` line and routes Traefik to that port. Port 80 is conventional for static sites; pick whatever your runtime listens on.

### Starter `index.html` (for a static `nginx` app)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>My App</title>
  <style>
    body { font-family: -apple-system, sans-serif; padding: 24px; }
  </style>
</head>
<body>
  <h1>My App</h1>
  <p>Running on Manaurum Platform v2.</p>
</body>
</html>
```

### Calling capabilities (for dynamic apps)

If your app needs to call the OS (KV, files, AI, etc.), the platform passes these env vars to your container at startup:

| Env var | Use it for |
|---|---|
| `MANAURUM_TENANT_ID` | `X-Manaurum-Tenant-Id` header on capability calls. |
| `MANAURUM_APP_ID` | `X-Manaurum-App-Id` header on capability calls. |
| `MANAURUM_VERSION` | (optional) which version is running. |
| `MANAURUM_BROKER_URL` / `DATABASE_URL` | Postgres broker DSN for dedicated app schemas. |

You also need a developer-credential token (`mna_*`) — set it as a v2 secret via `os.secrets.set` after first deploy, or pass it as an env var via `manifest.runtime.env_secrets`.

```javascript
// inside your container
const RESP = await fetch('https://manaurum.com/api/capability/os.kv.set', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${process.env.MANAURUM_V2_TOKEN}`,
    'X-Manaurum-Tenant-Id': process.env.MANAURUM_TENANT_ID,
    'X-Manaurum-App-Id':    process.env.MANAURUM_APP_ID,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ key: 'foo', value: { bar: 1 } }),
});
```

Full capability list + input schemas: `references/capabilities-reference.md`.

### `.env.manaurum`

```
MANAURUM_V2_TOKEN=mna_<keyid>_<secret>
```

Get the token via Manaurum desktop → **Dev Hub → "v2 Tokens (Beta)" → Generate**. Shown ONCE — save immediately. Bound to the tenant of whoever issued it (today: typically `seregaos` while v2 is being rolled out).

### `.gitignore`

```
.env*
node_modules/
*.zip
*.tar
.DS_Store
__pycache__/
.venv/
```

### `deploy.sh`

See `manaurum-deploy/SKILL.md` § "deploy.sh template (v2)" for the canonical version.

### Local testing

For static apps, just `python -m http.server 8000` in the project dir and open `http://localhost:8000`.

For Dockerized apps, build and run locally:

```bash
docker build -t my-app:dev .
docker run --rm -p 8080:80 \
  -e MANAURUM_TENANT_ID=00000000-0000-0000-0000-000000000000 \
  -e MANAURUM_APP_ID=00000000-0000-0000-0000-000000000000 \
  my-app:dev
```

The platform-set env vars are placeholder UUIDs in dev; capability calls will fail with `412 app_id_must_be_uuid` if the placeholder isn't a real registered app — that's fine for offline UI work, just keep capability calls behind feature checks.

For full handshake testing on the platform, deploy with `manaurum-deploy/SKILL.md` and inspect at `https://<slug>.apps.manaurum.com`.

### After scaffolding

1. Build your app (any language, any framework — anything Docker can build).
2. Deploy with `/manaurum-deploy`. ~7–10s end-to-end.
3. Visit `https://<slug>.apps.manaurum.com`.
4. Iterate: bump `manifest_v2.json.version`, redeploy. Same URL, new version.

---

## Legacy v1 setup (iframe — for existing apps only)

> Don't use this for new apps. v1 is for maintaining existing iframe-based apps.

```
my-v1-app/
├── manifest.json       ← v1 schema (manifest_version: "1")
├── index.html          ← MUST be at the bundle root
├── style.css / app.js  ← optional
└── .env.manaurum       ← MANAURUM_TENANT_TOKEN=mnu_…
```

### Starter v1 `manifest.json`

```json
{
  "manifest_version": "1",
  "manaurum_sdk_version": "1",
  "slug": "my-app",
  "name": "My App",
  "version": "1.0.0",
  "entry_point": "index.html",
  "permissions": []
}
```

### Starter v1 `index.html`

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>My App</title>
  <script src="https://manaurum.com/sdk/manaurum.js"></script>
</head>
<body>
  <h1 id="title">Loading…</h1>
  <script>
    var app = ManaurumSDK.init();
    app.onReady(function (ctx) {
      document.getElementById('title').textContent = 'Hello, ' + ctx.user.nickname + '!';
    });
  </script>
</body>
</html>
```

### v1 deploy

`/manaurum-deploy` → "Legacy v1 deploy" section. Token is `mnu_*` (not `mna_*`), endpoint is `/api/dev/apps/deploy`, body is a manifest+zip.

For the full v1 surface (SDK API, theming, design rules, App Store submission), see `references/sdk-api.md`, `references/design.md`, `references/manifest-spec.md`, `references/publishing.md`. Those references describe v1 only.

---

## Next

- `/manaurum-app` — full v2 app development guide (capability list, manifest reference, common patterns).
- `/manaurum-deploy` — deploy contract, rollback, version listing.
- For deeper v2 platform docs: `references/v2-platform.md` (this skill's plugin) covers manifest fields, capability schemas, deploy ops.

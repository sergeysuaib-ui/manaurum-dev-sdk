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
├── src/                ← your app (the only thing the Dockerfile COPYs)
│   └── index.html      ← (or whatever your runtime serves)
├── migrations/         ← Optional — plain *.sql only, run once per (app, tenant)
├── .dockerignore       ← Keeps .env* / .git out of the build context
├── deploy.sh           ← Optional CLI helper (see /manaurum-deploy)
├── .env.manaurum       ← Deploy-time token (gitignored) — never read by your container
└── .gitignore
```

`migrations/` is SQL-only and flat: a non-`.sql` file sitting directly in it fails the
deploy, and subdirectories are silently ignored. The DDL is parsed and additive-only —
see `manaurum-app/SKILL.md` before you write one. Omitting the directory entirely is fine.

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
    "port": 80,
    "api_routes": [
      { "path": "/api/items/*", "auth": "user" }
    ],
    "egress_allowed_hosts": []
  },
  "data": {
    "none": true
  },
  "frontend": {
    "entry_point": "/index.html",
    "icon": "📦"
  },
  "visibility": {
    "mode": "private"
  }
}
```

Validation rules:

- `app_id`: no regex in the schema, but it becomes your DNS label and your Postgres
  schema/role name — keep it `^[a-z][a-z0-9-]*[a-z0-9]$` and under ~40 chars.
  Becomes `<app_id>.apps.manaurum.com`.
- `version`: semver `MAJOR.MINOR.PATCH`. Bump on every redeploy.
- `runtime.mode`: `hosted` for default; `byo` (you host elsewhere, platform proxies) and `dev` (in-browser editor) are advanced.
- `runtime.port`: the port your process actually listens on. The gateway resolves your
  container as `<swarm-service>:<port>`, using `runtime.port` if present and **80**
  otherwise. Nothing in the platform parses your Dockerfile's `EXPOSE` line. Set this
  value and your `CMD` from the same number, or every request 502s.
- `runtime.api_routes`: **default-deny declaration of every `/api/*` path your container
  serves.** A path that matches no rule returns `404 route_not_declared` from the gateway
  and never reaches your container. `path` must start with `/`; a trailing `/*` matches
  anything *below* that prefix — `/api/items/*` does **not** match bare `/api/items`, so
  declare both if you serve both. There is no `method` field; one rule covers all verbs.
  `auth: "user"` makes the gateway mint a 60s `user_context` JWT and inject it as
  `X-Manaurum-User-Context` (the end user's bearer is never forwarded);
  `auth: "anonymous"` proxies with no user context (kiosk). Add `"streaming": true` for
  `text/event-stream` routes. Static assets (HTML/JS/CSS, `/healthz`) are **not**
  declared here and are always anonymous. If your app serves no API at all, drop the key.
- `data`: your storage mode. **If your app has no Postgres of its own — which includes
  every app that persists only via `os.kv` / `os.files` — declare `"data": {"none": true}`.**
  Omitting the block selects managed mode, which tries to provision a schema + login role
  and fails the deploy at `swarm_applying` with `MANAURUM_DDL_DSN is not set`. Other
  modes: `{"byo": true}` (your own connection string, no isolation guarantees) and
  `{"shared": true}` (one cross-tenant schema — you own every `WHERE tenant_id`).
- `frontend.entry_point`: the URL the desktop shell loads in the app's window, normally
  `/index.html`. Without it your app is reachable at its URL but has no desktop window.
  `frontend.icon` takes an emoji, an absolute URL, or an absolute
  `/api/catalog/media/...` path — a **relative** path renders as literal text on the tile.
- `runtime.egress_allowed_hosts`: list of external hosts your app may reach via `os.http.fetch`. Default-deny.
- `permissions` (optional top-level array): BROWSER features the OS shell
  delegates to your iframe (Permissions-Policy `allow`). Enum today:
  `["microphone"]`. **If the app records audio, scaffold this in from the
  start** — without it the mic is blocked inside the shell iframe and the
  app ships broken. Voice apps also declare `os.ai.transcribe` in
  `requires_capabilities` (that part is the platform STT; `permissions`
  is only the browser side).

To use AI / declare a dedicated DB schema / migrations, see `manaurum-app/SKILL.md` and `references/v2-platform.md`.

### Starter `Dockerfile` (static page on nginx)

```dockerfile
FROM nginx:1.27-alpine
# COPY only what the image needs. `COPY . .` would bake .env* and any other
# stray file in the build context into a layer.
COPY src/ /usr/share/nginx/html/
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null || exit 1
```

nginx listens on 80, which matches `"port": 80` in the starter manifest.

For a Node app (listens on 8080 → set `"runtime": {"port": 8080}`):

```dockerfile
FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY src/ ./src/
EXPOSE 8080
# Bind 0.0.0.0, not localhost — the gateway reaches you over the overlay network.
ENV HOST=0.0.0.0 PORT=8080
CMD ["node", "src/server.js"]
```

For a Python (FastAPI) app (listens on 8000 → set `"runtime": {"port": 8000}`):

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**`EXPOSE` is documentation only — nothing in the platform parses it.** The gateway
routes to `manifest.runtime.port` (default 80). The three numbers that must agree are
`runtime.port`, your `CMD`'s `--port`/`PORT`, and `EXPOSE`. Always bind `0.0.0.0`: a
server bound to `127.0.0.1` starts fine, passes its own healthcheck, and 502s from
outside the container.

### Starter `.dockerignore`

```
.env*
.git
node_modules
```

The CLI packager already drops `.git`, `node_modules`, `dist`, `build`, `__pycache__`
and `.venv` from the deploy tarball — but **not** `.env*`, and the tarball is streamed
straight into Docker's build endpoint, which does not apply `.dockerignore` server-side.
So `.dockerignore` protects your **local** `docker build`, and the narrow `COPY src/`
above is what protects the deployed image. Keep real secrets outside the app directory.

### Starter `src/index.html` (for a static `nginx` app)

The `manaurum:ready` reply is **mandatory, v2 included** — scaffold it in, never bolt it
on later. When the desktop opens your app it loads your URL in an iframe and posts
`manaurum:init`; if you do not post `manaurum:ready` back within 10 seconds the shell
replaces your UI with "App is not responding". The trap: your app still works when you
open `https://<slug>.apps.manaurum.com` directly, so the failure is invisible until
someone opens it on the desktop — which is where your users are. The first-party app
Libi shipped broken for exactly this reason (MAN-1321).

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>My App</title>
  <!-- REQUIRED — replies manaurum:ready to the shell's manaurum:init.
       Inline in <head> so the listener exists before any deferred bundle loads. -->
  <script>
    window.addEventListener('message', function (e) {
      if (e.data && e.data.type === 'manaurum:init') {
        window.parent.postMessage({ type: 'manaurum:ready' }, '*');
      }
    });
  </script>
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

For an SPA, keep that inline listener in `index.html` **and** post one proactive
`manaurum:ready` after mount — the shell tolerates both, and the inline copy covers the
window between iframe load and bundle execution.

The `manaurum:init` payload carries `granted_capabilities`. The postMessage channel is
for window framing and this handshake only — v2 data flows over your own `/api` routes
to the capability gateway, never over postMessage.

Also: **no native dialogs.** The shell's iframe sandbox has no `allow-modals`, so
`alert()`, `confirm()` and `prompt()` are dead inside the desktop (they work on the
standalone URL, so "it worked in my browser" proves nothing). Use in-app DOM instead.

### Calling capabilities (for dynamic apps)

If your app needs to call the OS (KV, files, AI, etc.), the platform passes these env vars to your container at startup:

| Env var | Use it for |
|---|---|
| `MANAURUM_CORE_URL` | Base URL of the capability gateway. Never hardcode a host. |
| `MANAURUM_RUNTIME_TOKEN` | `Authorization: Bearer …`. An `mna_*` credential scoped to this one app, minted fresh on every deploy. |
| `MANAURUM_TENANT_ID` | `X-Manaurum-Tenant-Id` header on capability calls. |
| `MANAURUM_APP_ID` | `X-Manaurum-App-Id` header (the UUID form — required by `os.kv.*` and `os.events.emit`). |
| `MANAURUM_VERSION` | (optional) which version is running. |
| `MANAURUM_TARGET_SCHEMA` | Your Postgres schema name, `app_<slug>__<tenant_hex>`. |
| `DATABASE_URL` | Injected **only** in the managed schema modes (the default, and `data.shared`). Absent under `data.none` / `data.byo`. |
| `CORE_USER_CONTEXT_PUBLIC_KEY_PEM` | RSA public key for verifying the `X-Manaurum-User-Context` JWT on `auth: "user"` routes. |

**You ship no token.** The platform injects `MANAURUM_RUNTIME_TOKEN` for you — never bake
a credential into the image and never use your `mna_*` developer token at runtime.
(`runtime.env_secrets` does not exist: it is not in the schema, Core never reads it, and
because the `runtime` sub-object is not strict it validates and then silently does
nothing. `MANAURUM_BROKER_URL` is likewise never injected — MAN-163 removed it because
the shared broker DSN could reach every tenant's schema.)

```javascript
// inside your container
const RESP = await fetch(`${process.env.MANAURUM_CORE_URL}/api/capability/os.kv.set`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${process.env.MANAURUM_RUNTIME_TOKEN}`,
    'X-Manaurum-Tenant-Id': process.env.MANAURUM_TENANT_ID,
    'X-Manaurum-App-Id':    process.env.MANAURUM_APP_ID,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ key: 'foo', value: { bar: 1 } }),
});
```

For a capability whose `auth_mode` is `user` (`os.drive.*`, `os.calendar.*`), also forward
the `X-Manaurum-User-Context` header exactly as your route received it — omitting it is
`403 user_context_required`.

Full capability list + input schemas: `references/capabilities-reference.md`.

### `.env.manaurum`

```
# DEPLOY-TIME ONLY — read by deploy.sh / the CLI on your machine.
# Your container never sees this; it gets MANAURUM_RUNTIME_TOKEN instead.
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

For static apps, just `python -m http.server 8000` inside `src/` and open `http://localhost:8000`.

For Dockerized apps, build and run locally:

```bash
docker build -t my-app:dev .
docker run --rm -p 8080:80 \
  -e MANAURUM_TENANT_ID=00000000-0000-0000-0000-000000000000 \
  -e MANAURUM_APP_ID=00000000-0000-0000-0000-000000000000 \
  my-app:dev
```

Two things you **cannot** exercise locally:

- **Capability calls.** There is no `MANAURUM_RUNTIME_TOKEN` outside a real deploy, and
  the placeholder UUIDs above are not a registered app — calls fail with
  `412 app_id_must_be_uuid`. Fine for offline UI work; keep capability calls behind a
  feature check.
- **The `manaurum:ready` handshake and the no-dialogs rule.** Both only bite inside the
  desktop shell. `http://localhost:8080` and the standalone
  `https://<slug>.apps.manaurum.com` URL both look healthy either way.

So after deploying, open the app **as a desktop window**, not just at its URL — that is
the only test that covers the shell contract.

### After scaffolding

1. Build your app (any language, any framework — anything Docker can build).
2. Deploy with `/manaurum-deploy`. The deploy endpoint is **asynchronous** — it returns a
   job id, not a result; poll until `succeeded` or `failed`.
3. Hit `https://<slug>.apps.manaurum.com` **and** open the app as a desktop window.
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

For the full v1 surface (SDK API, theming, design rules, App Store submission), see `references/sdk-api.md`, `references/design.md`, `references/manifest-spec.md`, `references/publishing.md`. Those references describe v1 only — with one carve-out: the `manaurum:init` / `manaurum:ready` handshake documented in `sdk-api.md` applies to **v2 apps too**. Everything else in the postMessage protocol (`manaurum:storage-*`, `manaurum:file-*`, `manaurum:notification`) is v1-only and is rejected for a v2 app.

---

## Next

- `/manaurum-app` — full v2 app development guide (capability list, manifest reference, common patterns).
- `/manaurum-deploy` — deploy contract, rollback, version listing.
- For deeper v2 platform docs: `references/v2-platform.md` (this skill's plugin) covers manifest fields, capability schemas, deploy ops.

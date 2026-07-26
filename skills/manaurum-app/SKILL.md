---
name: manaurum-app
description: Build apps for ManAurum OS — a multi-tenant browser-based virtual desktop. As of 2026-05, the default flow is Platform v2 (containerized hosted apps with capability gateway). Use whenever the user wants to create, build, generate, or develop a ManAurum app, or mentions ManAurum SDK / SeregaOS / iframe app / capability gateway. Covers v2 manifests, Dockerfiles, capabilities, deploy API, and the legacy v1 (iframe + manaurum.js) path for older apps.
---

# Build ManAurum Apps

> ## ⚡ Platform v2 is the new default (2026-05)
>
> ManAurum now has two runtime models:
>
> - **v2 (default for ALL new apps)** — your app is a Docker container. The manifest declares which capabilities it needs (KV, files, AI, events, HTTP egress, …). One `POST /api/dev/v2/deploy` and the app is live at `https://<slug>.apps.manaurum.com` with TLS. **This skill teaches v2 first.**
>
> - **v1 (legacy)** — your app is a static HTML+JS bundle in an iframe, talking to the OS over `postMessage` via `manaurum.js`. Still works for existing apps; **don't migrate unless asked**. New work goes on v2.
>
> If the user already has a v1 app and just wants to update it, stay on v1 — jump to the "Legacy v1 (iframe)" section at the bottom. Everything else: v2.

---

## What a v2 app is

A v2 app is a Docker image that:

- Listens on **port 80, bound to `0.0.0.0`** — or on whatever port it declares in `runtime.port`. Nothing else is routable (see Step 2).
- Serves only the `/api/*` paths it declared in `runtime.api_routes`. Undeclared API paths never reach the container (see Step 1).
- Receives `MANAURUM_TENANT_ID`, `MANAURUM_APP_ID`, `MANAURUM_VERSION`, `MANAURUM_TARGET_SCHEMA`, and the runtime credential pair `MANAURUM_RUNTIME_TOKEN` + `MANAURUM_CORE_URL` as env vars at startup (plus `DATABASE_URL` when it uses the default managed DB mode).
- Calls back to the OS via the **capability gateway** at `POST ${MANAURUM_CORE_URL}/api/capability/<name>` for everything: KV storage, files (R2), AI, notifications, events, audit, etc.
- Answers the shell's `manaurum:ready` handshake, or it has no usable desktop window (see Step 2.5).

When you deploy:
1. Your build context is tarred + uploaded as base64 in the request body.
2. The platform builds your image from the `Dockerfile` inside the backend container.
3. The image is pushed to a tenant-private Docker registry.
4. A swarm service is created (or updated for redeploys).
5. A Traefik route exposes `https://<slug>.apps.manaurum.com` with a Let's Encrypt cert.

End-to-end deploy time for a small app: **~8 seconds**.

There is **no Core PR** for any of this. The platform team does not need to be in the loop. You are not modifying ManAurum OS — you are deploying an independent containerized app onto it.

## Before you write anything — read a real one

`references/reference-apps.md` walks three production v2 apps and what each is
worth reading for: **`shift-checklist`** (22 files — a complete app you can read
whole, `src/api/` split by surface, both auth levels), **`family-space-v2`** (the
ceiling, and the manifest + `agent_capabilities` reference), and **`libi`** (the
only tested one — copy its `conftest.py`). Copying the shape of a working app
beats reconstructing it from this page.

## Required project structure

```
workspace/
├── .env.manaurum      ← (gitignored) MANAURUM_V2_TOKEN=mna_… — OUTSIDE the deployed dir, on purpose
└── my-app/            ← this is what you deploy; everything below is packed and uploaded
    ├── manifest.json   ← REQUIRED — see below
    ├── Dockerfile         ← REQUIRED — produces the runtime image
    ├── .dockerignore      ← strongly recommended — keep .env*, .git, node_modules out of the image
    ├── migrations/        ← optional — plain *.sql, run once per (app, tenant) in filename order
    │   └── 0001_init.sql
    └── ... your source files (any language, any framework) ...
```

**The token file lives one level up, and that placement is the point.** The packager tars the directory containing your `manifest.json`, excluding only these exact names:

```
__pycache__  .venv  venv  .git  .pytest_cache  .ruff_cache  .mypy_cache  node_modules  dist  build
```

That is an exact-name match list with **no glob support and no `.env*` entry** — a `.env.manaurum` sitting next to your `Dockerfile` is packed verbatim into the build context, baked into an image layer, retained per-version in object storage, downloadable later via `manaurum app fetch-source`, and committed to a per-app append-only git history. There is no practical way to un-leak it. Keep every `.env*` outside the deployed directory, and ship a `.dockerignore` as a second line of defence.

## Step 1 — Manifest v2 (minimal)

```json
{
  "manifest_version": "2",
  "manaurum_sdk_version": "2",
  "app_id": "my-app",
  "name": "My App",
  "version": "1.0.0",
  "runtime": {
    "mode": "hosted",
    "port": 8000,
    "api_routes": [
      { "path": "/api/items/*", "auth": "user" },
      { "path": "/api/items",   "auth": "user" },
      { "path": "/api/kiosk/today", "auth": "anonymous" }
    ],
    "egress_allowed_hosts": []
  },
  "data": { "none": true },
  "frontend": {
    "entry_point": "/index.html",
    "icon": "📋"
  },
  "visibility": {
    "mode": "private"
  }
}
```

Validation rules (key ones):

- `app_id`: slug `^[a-z][a-z0-9-]{1,38}[a-z0-9]$`. Becomes the URL: `<app_id>.apps.manaurum.com`.
- `version`: semver MAJOR.MINOR.PATCH (no pre-release, no build metadata). Each redeploy must be a NEW version.
- `runtime.mode`: `hosted` (the platform runs the container — what this skill teaches), `byo` (you host your own and the platform proxies — advanced), or `dev` (in-browser Monaco editor — App Builder v2 internal).
- `runtime.port`: the port your container listens on. Default **80**. This is the *only* thing that decides where the gateway sends traffic — see Step 2.
- **`runtime.api_routes`: the default-deny declaration of every `/api/*` path your container serves.** Get this wrong and your app is broken in a way that looks like a backend bug. Details below.
- `runtime.egress_allowed_hosts`: list of external hosts your app may reach via `os.http.fetch`. Default-deny for everything else.
- `data`: your storage mode. If your app has **no Postgres of its own** — which includes every app that persists only through `os.kv` / `os.files` — declare `"data": {"none": true}`. Omitting the block selects managed mode, which tries to provision a per-(app, tenant) schema + login role and needs a DDL-capable DSN on Core. Other modes: `{"byo": true}` (your own connection string, no isolation guarantees), `{"shared": true}` (one cross-tenant schema — you own every `WHERE tenant_id`, and tenant admins see an isolation warning at install).
- `frontend.entry_point`: the URL the **desktop shell** loads in your app's window, normally `/index.html`. Without it your app has a live URL but no window on the desktop. Declaring it is also what makes the `manaurum:ready` handshake (Step 2.5) apply to you.
- `frontend.icon`: an emoji (`"📋"`, and Libi ships `"🍼"`), a full URL, or an absolute `/api/catalog/media/...` path. Omit it and the launcher serves a generic placeholder. A **relative** path such as `"icons/app.svg"` is not resolved — it is painted into the tile as literal text.
- `visibility.mode`: `private` (this tenant only), `public` (any tenant can install via App Store v2), or `allow_list` with a `tenants` array.
- `permissions`: optional top-level array of BROWSER features the OS shell
  delegates to your iframe via the `allow` attribute (Permissions-Policy).
  Enum today: `["microphone"]`. **Required for any app that records audio
  inside the shell** — without it `getUserMedia` is blocked in the iframe
  (your standalone `<app_id>.apps.manaurum.com` URL is unaffected). The user
  still sees the normal browser mic prompt. This is separate from
  capabilities: a voice app declares BOTH `"permissions": ["microphone"]`
  and `os.ai.transcribe` in `requires_capabilities`.

### `runtime.api_routes` — read this before you write a single route

Every request to `https://<slug>.apps.manaurum.com` goes through the Core gateway. For any path starting with `/api/`, the gateway looks the path up in `runtime.api_routes` **before** touching your container. No match → **`404 route_not_declared`**, and your container never sees the request. There is no implicit fallback, not even to anonymous.

Each entry is `{ "path": …, "auth": … }`:

- `path` must start with `/`. A trailing `/*` matches anything **below** that prefix.
- `auth` is `"user"` or `"anonymous"` — both required, both explicit.
  - `"user"`: the gateway mints a 60-second RS256 `user_context` JWT and injects it as `X-Manaurum-User-Context`. The end user's own bearer token is **never** forwarded to you.
  - `"anonymous"`: proxied with no user context. This is how you expose a kiosk/public endpoint, and it must be declared — a route you forget is unreachable, not open.
- Optional `"streaming": true` for `text/event-stream` routes, so the gateway passes chunks through instead of buffering the response.
- **There is no `method` field.** One rule covers GET, POST, PATCH, DELETE alike. You cannot declare `/api/items` anonymous for reads and `user` for writes — enforce that inside your app.

The two failure modes that will actually catch you:

1. **`/api/tasks/*` does NOT match the bare `/api/tasks`.** The wildcard means "everything below `/api/tasks/`" and requires at least one more character. A collection endpoint plus its item endpoints needs **both** rules:
   ```json
   { "path": "/api/tasks",   "auth": "user" },
   { "path": "/api/tasks/*", "auth": "user" }
   ```
2. **Adding a route to your code is not enough.** New endpoint → new manifest entry → redeploy. Otherwise it 404s while your logs stay silent, because nothing reached you.

Precedence: the longer literal prefix wins, ties break by declaration order. That lets you carve one path out of a wildcard — `{"path": "/api/orders/*", "auth": "user"}` plus `{"path": "/api/orders/public", "auth": "anonymous"}` does what it looks like.

Static assets (HTML/JS/CSS, `/healthz`, anything not under `/api/`) are **not** declared here and are always served anonymously.

For declaring custom capabilities, secrets, migrations, see `references/v2-platform.md` § Manifest reference.

## Step 2 — Dockerfile

Anything that produces a runnable image. Smallest possible (static page on nginx):

```dockerfile
FROM nginx:1.27-alpine
COPY index.html /usr/share/nginx/html/index.html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null || exit 1
```

Smallest dynamic (Node):

```dockerfile
FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
EXPOSE 80
CMD ["node", "server.js"]   # server.js must listen on 0.0.0.0:80
```

### The port rule

**`EXPOSE` is never parsed.** Nothing in Core reads it; it is documentation for humans. The gateway resolves your upstream as `<swarm-service>:<port>` where `port` is `manifest.runtime.port` if present and **80** otherwise. That is the only input.

Two consequences, both of which produce the same symptom — a deploy that reports `succeeded` and then 502s on every single request:

- **Wrong or missing `runtime.port`.** If your framework listens on 8000 and your manifest says nothing, the gateway dials port 80 and finds nobody. Either bind 80, or declare the port you actually use. Reference apps declare it: `libi/manifest.json` ships `"runtime": {"mode": "hosted", "port": 8000, …}`.
- **Bound to `127.0.0.1`.** Many frameworks default to loopback, which is unreachable from outside the container. Bind `0.0.0.0` explicitly:
  ```dockerfile
  CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```
  and set `"port": 8000` in the manifest to match. `app.listen(80)` in Node binds all interfaces by default, but `app.listen(80, 'localhost')` does not.

Note `runtime.port` validates because the `runtime` sub-object is not strict — which cuts both ways. Unknown `runtime` keys (`replicas`, anything you invent) also validate and are then **silently ignored**, so a typo'd `"prot": 8000` deploys green and 502s.

Traffic path: `https://<slug>.apps.manaurum.com` → Traefik → **Core backend** (which adds the `/apps/<slug>` prefix) → Core gateway → your container. Traefik never talks to your container directly, so publishing ports in the Dockerfile changes nothing.

## Step 2.5 — The `manaurum:ready` handshake (MANDATORY)

If your app declares `frontend.entry_point` — i.e. it has a window on the desktop — this is not optional.

When the desktop opens your app it loads your URL in an iframe and posts `manaurum:init` into it. **Your page must post `manaurum:ready` back within 10 seconds.** If it doesn't, the shell covers your UI with "App is not responding — no `manaurum:ready` received within 10s". This is enforced for v2 exactly as for v1; there is no version branch on this path.

**The trap:** opening `https://<slug>.apps.manaurum.com` directly works perfectly without the handshake. There is no parent frame, so nothing times out. Your app looks fine in every browser tab you test it in and is unusable in the only place your users open it. This is not hypothetical — the first-party app *Libi* shipped exactly this way and needed a follow-up release (MAN-1321: "Libi's SPA never replied, making the app unusable as a desktop window or from the mobile home screen").

Minimal correct answer, inline in `<head>` of your entry point:

```html
<script>
  window.addEventListener('message', function (e) {
    if (e.data && e.data.type === 'manaurum:init') {
      window.parent.postMessage({ type: 'manaurum:ready' }, '*');
    }
  });
</script>
```

Inline in `<head>` matters: for an SPA with a deferred module bundle, `manaurum:init` can arrive before your bundle has parsed. Put the listener in the HTML **and** fire one proactive `manaurum:ready` after mount — that belt-and-braces pair is what MAN-1321 landed:

```js
// src/main.tsx, after render
try { window.parent.postMessage({ type: 'manaurum:ready' }, '*'); } catch { /* not embedded */ }
```

The `manaurum:init` payload carries the app's `granted_capabilities`. **For a v2 app, postMessage is for this handshake and window framing only.** Never send the v1 data verbs (`manaurum:storage-*`, `manaurum:file-*`, `manaurum:notification`) from a v2 app — v2 data flows from your own `/api` routes to the capability gateway, server-side.

Full message contract: `references/sdk-api.md` § "`manaurum:ready` — the shell handshake".

## Step 3 — Use capabilities (from inside your container)

Your container calls the gateway at `${MANAURUM_CORE_URL}/api/capability/<name>` (singular `capability`). **The platform injects the credential for you.** You never mint one, never bake one into the image, and never use your own `mna_*` developer token at runtime — that token is for `POST /api/dev/v2/deploy` from your laptop and nothing else.

Headers:

- `Authorization: Bearer ${MANAURUM_RUNTIME_TOKEN}` — an app-scoped `mna_*` runtime credential the platform mints fresh on every deploy and injects as an env var. It is scoped to this one app; it is not your developer token.
- `X-Manaurum-Tenant-Id: ${MANAURUM_TENANT_ID}`.
- `X-Manaurum-App-Id` — the **UUID** (`MANAURUM_APP_ID`) for `os.kv.*` and `os.events.emit`; the slug is rejected there with `412 app_id_must_be_uuid`.
- `X-Manaurum-User-Context` — forward it **unchanged** for user-scoped capabilities (`os.drive.*`, `os.calendar.*`), exactly as your `auth: "user"` route received it. Omitting it is `403 user_context_required`. It is optional on app-scoped capabilities, where it only enriches the audit log.

Body shape: a JSON object matching the capability's input schema (no wrapper). Read `references/capabilities-reference.md` for the canonical input/output for every capability.

**Working with the user's Drive (Files app):** `os.files.*` is your app's PRIVATE scratch — the user never sees it. To put a document into the USER's file system, read a user-picked file, or work in a folder the user granted you, use the `os.drive.*` capabilities plus the browser-side `app.pickFromDrive()` picker — all consent-gated and requiring the forwarded `X-Manaurum-User-Context` header. Gateway contract in `references/capabilities-reference.md` § os.drive; the browser-side picker is in `references/sdk-api.md` § "Platform v2 — frontend SDK (`manaurum-v2.mjs`)".

```javascript
// inside your container — Node example
const CORE = process.env.MANAURUM_CORE_URL;

async function setKV(key, value) {
  const resp = await fetch(`${CORE}/api/capability/os.kv.set`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${process.env.MANAURUM_RUNTIME_TOKEN}`,
      'X-Manaurum-Tenant-Id': process.env.MANAURUM_TENANT_ID,
      'X-Manaurum-App-Id':    process.env.MANAURUM_APP_ID,
      'Content-Type':         'application/json',
    },
    body: JSON.stringify({ key, value }),
  });
  if (!resp.ok) throw new Error(`os.kv.set failed: ${resp.status}`);
  return resp.json();  // { output: { ok: true }, correlation_id: "…" }
}
```

Capabilities available today:

| Capability | Purpose |
|---|---|
| `os.kv.set` / `os.kv.get` | Per-app KV in Postgres (FORCE-RLS by tenant). |
| `os.tenant_config.get` | Read tenant feature flags / config. |
| `os.secrets.set` / `os.secrets.get` | Per-app encrypted secrets. |
| `os.files.upload` / `.download` / `.delete` | R2 (presigned URLs). |
| `os.ai.complete` / `os.ai.embed` | LLM (BYOK — tenant configures keys in Settings → Интеграции). |
| `os.ai.transcribe` | Speech-to-text (BYOK — needs the tenant's **OpenAI** key). ≤ 25 MB decoded audio. Pair with manifest `"permissions": ["microphone"]` to record in the shell iframe. |
| `os.ocr.extract` | OCR via vision LLM (BYOK). |
| `os.notifications.send_to_user` | In-app / Resend / Twilio. |
| `os.events.emit` | Inter-app events (transactional outbox). |
| `os.http.fetch` | External HTTP. Hosts must be in `manifest.runtime.egress_allowed_hosts`. Binary payloads via `body_base64` / `response_format: "base64"` (~5 MB each way). |
| `os.compliance.audit_query` | Read your own capability call audit log. |
| `os.apps.call` | Sync RPC to another v2 app. |
| `os.drive.stage` / `.publish` / `.list` / `.read` / `.write` | The USER's file system (Files app), consent-gated. **User-scoped — forward `X-Manaurum-User-Context`.** |
| `os.calendar.list_events` / `os.calendar.create_event` | The user's calendar. **User-scoped — forward `X-Manaurum-User-Context`.** |

See `references/capabilities-reference.md` for input/output schemas, error codes, and quotas.

## Step 4 — Deploy

You need a `mna_*` token. Get it via the desktop UI: **Dev Hub → "v2 Tokens (Beta)" → Generate**. Shown once, save to `.env.manaurum`:

```
MANAURUM_V2_TOKEN=mna_<keyid>_<secret>
```

This is a **deploy-time** credential only. Your container never sees it and must never contain it — at runtime it uses the injected `MANAURUM_RUNTIME_TOKEN` (Step 3).

The deploy is one API call plus a poll. Bundle the build context, base64-encode, post:

```bash
cd my-app
tar cf /tmp/ctx.tar \
  --exclude='.env*' --exclude='.git' --exclude='node_modules' \
  --exclude='.venv' --exclude='venv' --exclude='__pycache__' \
  --exclude='.pytest_cache' --exclude='dist' --exclude='build' \
  --exclude='deploy.sh' --exclude='*.tar' --exclude='*.zip' \
  .

# Base64 into a FILE and read it with --rawfile / --slurpfile. Passing it
# as `jq --arg b "$B64"` puts the whole archive on the command line and
# fails with "Argument list too long" on any real project.
base64 < /tmp/ctx.tar | tr -d '\n' > /tmp/ctx.b64
jq -n --rawfile b /tmp/ctx.b64 --slurpfile m manifest.json \
  '{manifest_json: $m[0], archive_b64: $b}' > /tmp/deploy.json

curl -sS -X POST https://manaurum.com/api/dev/v2/deploy \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/deploy.json | jq .
```

**The deploy endpoint is asynchronous.** It always returns HTTP **202** with `status: "pending"` — never `succeeded`. Build, push, swarm, Traefik and migrations all run on a background job:

```json
{
  "deploy_job_id": "<uuid>",
  "status": "pending"
}
```

So a 202 tells you nothing except that the request was accepted; the manifest has not even been validated yet. Poll the job until it reaches `succeeded` or `failed`:

```bash
curl -sS https://manaurum.com/api/dev/v2/deploy/<deploy_job_id> \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN" | jq .
```

```json
{
  "status": "succeeded",
  "result": {
    "app_id":      "<uuid>",
    "version_id":  "<uuid>",
    "image_tag":   "manaurum-registry:5000/v2-app-my-app:1.0.0",
    "url":         "https://my-app.apps.manaurum.com"
  }
}
```

**`succeeded` does not mean "serving".** It means Docker accepted the service spec. There is no readiness probe on the hosted path, so the job can go green while your container is crash-looping or listening on the wrong port. Always finish a deploy by hitting the app yourself:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://my-app.apps.manaurum.com/healthz
```

A `deploy.sh` template with the polling loop, the live NDJSON progress stream, and the failure-triage table: see `manaurum-deploy/SKILL.md`.

## Step 5 — Update + rollback

- **New version**: bump `manifest.json.version` (semver), retar, redeploy. Same endpoint. The platform records a new `v2_app_versions` row and updates the swarm service in-place.
- **Rollback**: `POST /api/dev/v2/apps/<app_id>/rollback` — flips the install back to the previous version.
- **List versions**: `GET /api/dev/v2/apps/<app_id>/versions`.
- **Inspect**: `GET /api/dev/v2/apps/<app_id>`.
- **Stream logs**: `GET /api/dev/v2/apps/<app_id>/logs` (first slice returns a stub; full log streaming is planned).

## Common rejection codes (v2 deploy)

| HTTP | Meaning | Fix |
|---|---|---|
| 401 `invalid_credential` | Bad/expired/revoked `mna_*`, or not an `mna_*` token. | Mint a fresh one in Dev Hub. |
| 412 `app_id_must_be_uuid` | A capability call was sent with a slug for `X-Manaurum-App-Id`. | Use the UUID from `process.env.MANAURUM_APP_ID`. |
| 422 `manifest validation failed` | Manifest fails the v2 schema. | Read `errors[]`; fix and retry. |
| 422 `migration_validation_failed` | Migration SQL contains destructive DDL and `migration.breaking` is not set. | Either set `migration.breaking: true` (deliberate), or rewrite to additive-only. |
| 422 `egress_not_declared` | App tried `os.http.fetch` to a host not in `runtime.egress_allowed_hosts`. | Add the host to the manifest, redeploy. |
| 404 `route_not_declared` | An `/api/*` path is missing from `runtime.api_routes`. Default-deny — the container never saw the request. | Declare the path. Remember `/api/x/*` does not cover `/api/x`. |
| 403 `user_context_required` | A user-scoped capability (`os.drive.*`, `os.calendar.*`) was called without `X-Manaurum-User-Context`. | Forward the header your `auth: "user"` route received. |
| 403 `capability_not_granted` | The capability is in your manifest but not in the install's grant set. | Redeploying is not enough — the tenant's install grants must be extended. |
| 502 (serving, after a green deploy) | Nothing is listening where the gateway dials. | Bind `0.0.0.0` on port 80, or set `runtime.port` to the port you actually listen on. |
| 502 (during deploy) | Image build failed. | Look at `result.error` for the Docker stderr. Common: `COPY` source doesn't exist, dependency install failed. |

## Tenant context inside the container

The platform sets these env vars on every task:

| Env var | Value |
|---|---|
| `MANAURUM_TENANT_ID` | UUID of the tenant your app is installed in. |
| `MANAURUM_APP_ID` | UUID of your app in `v2_apps`. Use as `X-Manaurum-App-Id`. |
| `MANAURUM_VERSION` | The semver of the running version. |
| `MANAURUM_TARGET_SCHEMA` | Your Postgres schema, `app_<slug>__<tenant_hex>`. |
| `MANAURUM_RUNTIME_TOKEN` | App-scoped `mna_*` credential for the capability gateway. Minted fresh every deploy. |
| `MANAURUM_CORE_URL` | Base URL of the capability gateway. Build your call URLs from it, don't hardcode. |
| `CORE_USER_CONTEXT_PUBLIC_KEY_PEM` | RSA public key for verifying the `X-Manaurum-User-Context` JWT. |
| `DATABASE_URL` | Present **only** in the default managed data mode. A per-(app, tenant) login role, `NOSUPERUSER NOBYPASSRLS`, scoped to your one schema, with **no CREATE** — so no DDL at runtime, including `CREATE TABLE IF NOT EXISTS` on boot. Write plain unqualified SQL. Absent under `data.none` / `data.byo`. |

That table is the complete set. Two names that are **not** in it and that older guidance wrongly told you to read:

- **`MANAURUM_V2_TOKEN`** — this is the name these skills use for *your own* deploy credential in `.env.manaurum` on your machine, and it is a plain shell variable in the `curl` examples. The platform never injects it into your container. If your app code reads `MANAURUM_V2_TOKEN` at runtime it will find nothing; the runtime credential is `MANAURUM_RUNTIME_TOKEN`.
- **`MANAURUM_BROKER_URL`** — never injected. MAN-163 removed it because the shared broker DSN carried grants on every app's schema, so any container holding it could read other tenants' data. Anything built on it will fail.

Your data is **automatically tenant-scoped** by the platform's RLS policies on `app_kv`, `app_secrets`, audit log, etc. You don't need to filter by `tenant_id` in your queries — the platform does it server-side. Use `MANAURUM_TENANT_ID` only for display/branding ("welcome to <tenant>", per-tenant theming, etc.), never as a security filter.

## What NOT to do

- **Don't bake your developer `mna_*` token into the image, and don't pass one at deploy.** You don't need to: the platform injects `MANAURUM_RUNTIME_TOKEN`. Your own token is a laptop credential for `POST /api/dev/v2/deploy`; an image containing it hands every future reader your deploy rights. (`os.secrets.get` is not an alternative here — it is itself a capability call that needs the runtime token first.)
- **Don't write to host paths.** Volumes aren't mounted into v2 apps. Use `os.files.upload` (R2) for any persistent files.
- **Don't run DDL at runtime.** Your `DATABASE_URL` role has no CREATE. Schema changes go in `migrations/*.sql`, which the pipeline runs once per (app, tenant).
- **Don't expect side-channel network access.** `egress_allowed_hosts` controls outbound; DROP everything else. If you need a third-party API, declare it.
- **Don't use the v1 `mnu_*` token format.** v2 uses `mna_*` exclusively. The two are different surfaces.
- **Don't try to talk to other tenants.** Capabilities are tenant-scoped at the gateway level — you'd get 403 anyway.

## What will bite you

Everything here shares one property: it works when you open `https://<slug>.apps.manaurum.com` in a tab, and breaks inside the desktop — or breaks silently with a green deploy. Testing the standalone URL is not evidence.

**No native dialogs.** The shell's iframe sandbox is `allow-scripts allow-forms allow-same-origin`. `allow-modals` is not granted anywhere on the platform, so `alert()`, `confirm()`, `prompt()`, `window.print()` and `beforeunload` prompts are dead — Chrome returns `undefined` / `false` / `null` and logs a warning. A `confirm()`-gated delete button becomes a button that does nothing. Use an in-app modal for confirm, an in-app input for prompt, a toast for alert.

**Don't set your own framing headers.** Core force-assigns the CSP `frame-ancestors` and deletes `X-Frame-Options` on every `/apps/*` response, so setting either is pointless. But only the *framing* directives are rewritten: the rest of your CSP survives verbatim, so a `connect-src 'self'` that forgets your API origin will still break your app inside the shell.

**`frontend.icon` takes an emoji, a full URL, or an absolute `/api/catalog/media/...` path.** A relative path like `icons/app.svg` is not resolved — it renders as that literal string in the tile. Omit the field entirely and you get a clean generic placeholder, which is better than a broken one.

**Keep `.env*` out of the app directory.** The packager excludes `node_modules`, `.git`, `dist`, `build`, `__pycache__`, `.venv` — not `.env*`. Anything else you don't want in the image needs a `.dockerignore`.

**Unknown `runtime` keys validate and do nothing.** The `runtime` sub-object isn't strict, so `"prot": 8000` or an invented `env_secrets` passes the schema, deploys green, and is silently ignored. Typos here cost you a debugging session, not a 422.

**A capability in your manifest is not a capability you may call.** Grants are enforced per-install ahead of dispatch; an empty grant list is a deny, not a pass. Adding a capability and redeploying still 403s until the tenant's install grants are extended.

---

## Legacy v1 (iframe) — for existing apps only

> **Don't use this for new apps.** v1 is feature-frozen for existing builtins (Receptions, Finance, Radio, etc.) and tenant-scoped iframe apps already in production. New work goes on v2.

A v1 app is a static HTML+JS bundle loaded in a sandboxed iframe by the OS shell. The bundle is uploaded as a zip via `POST /api/dev/apps/deploy` with an `mnu_*` (NOT `mna_*`) token. The bundle communicates with the OS over `postMessage` via the `manaurum.js` SDK.

If you genuinely need to update a v1 app, see:
- `references/sdk-api.md` § "Legacy v1" — the v1 SDK surface (storage, files, db, ai, mul, …). Note that the same file's `manaurum:ready` and "Platform v2 — frontend SDK" sections are **not** v1-only; they apply to v2 apps too.
- `references/manifest-spec.md` — v1 manifest schema
- `references/design.md` — Smoothie + XP themes
- `references/publishing.md` — App Store v1 submission

Quick v1 reminder for porting context:

```html
<script src="https://manaurum.com/sdk/manaurum.js"></script>
<script>
  var app = ManaurumSDK.init();
  app.onReady(function (ctx) { /* … */ });
</script>
```

```json
{ "manifest_version": "1", "slug": "my-app", "version": "1.0.0", "entry_point": "index.html" }
```

The full v1 surface is in the references. If the user is on v1 and wants to ship, use `manaurum-deploy/SKILL.md` § "Legacy v1 deploy".

---

## Next: deploy

For the deploy step in detail, see `manaurum-deploy/SKILL.md`. For project scaffolding (gitignore, deploy.sh template, tenant token issuance), see `manaurum-setup/SKILL.md`.

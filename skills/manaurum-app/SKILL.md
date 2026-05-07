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

- Listens on a port (typically `:80`) — that port serves whatever HTTP your app needs.
- Receives `MANAURUM_TENANT_ID`, `MANAURUM_APP_ID`, `MANAURUM_VERSION` (and `MANAURUM_BROKER_URL` if you opted into a dedicated DB schema) as env vars at startup.
- Calls back to the OS via the **capability gateway** at `POST https://manaurum.com/api/capability/<name>` for everything: KV storage, files (R2), AI, notifications, events, audit, etc.

When you deploy:
1. Your build context is tarred + uploaded as base64 in the request body.
2. The platform builds your image from the `Dockerfile` inside the backend container.
3. The image is pushed to a tenant-private Docker registry.
4. A swarm service is created (or updated for redeploys).
5. A Traefik route exposes `https://<slug>.apps.manaurum.com` with a Let's Encrypt cert.

End-to-end deploy time for a small app: **~8 seconds**.

There is **no Core PR** for any of this. The platform team does not need to be in the loop. You are not modifying ManAurum OS — you are deploying an independent containerized app onto it.

## Required project structure

```
my-app/
├── manifest_v2.json   ← REQUIRED — see below
├── Dockerfile         ← REQUIRED — produces the runtime image
├── ... your source files (any language, any framework) ...
└── .env.manaurum      ← (gitignored) MANAURUM_V2_TOKEN=mna_…
```

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
    "egress_allowed_hosts": []
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
- `runtime.egress_allowed_hosts`: list of external hosts your app may reach via `os.http.fetch`. Default-deny for everything else.
- `visibility.mode`: `private` (this tenant only), `public` (any tenant can install via App Store v2), or `allow_list` with a `tenants` array.

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
EXPOSE 8080
CMD ["node", "server.js"]
```

Whatever you pick: **the container must serve HTTP on the port you EXPOSE**. The platform doesn't care which port — it reads `EXPOSE` and routes Traefik to it. Default is 80.

## Step 3 — Use capabilities (from inside your container)

Your container can call the capability gateway at `https://manaurum.com/api/capability/<name>`. Three required headers:

- `Authorization: Bearer <mna_*>` — your developer credential.
- `X-Manaurum-Tenant-Id: <uuid>` — `process.env.MANAURUM_TENANT_ID`.
- `X-Manaurum-App-Id: <uuid>` — `process.env.MANAURUM_APP_ID`.

Body shape: a JSON object matching the capability's input schema (no wrapper). Read `references/capabilities-reference.md` for the canonical input/output for every capability.

```javascript
// inside your container — Node example
async function setKV(key, value) {
  const resp = await fetch('https://manaurum.com/api/capability/os.kv.set', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${process.env.MANAURUM_V2_TOKEN}`,
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
| `os.ocr.extract` | OCR via vision LLM (BYOK). |
| `os.notifications.send_to_user` | In-app / Resend / Twilio. |
| `os.events.emit` | Inter-app events (transactional outbox). |
| `os.http.fetch` | External HTTP. Hosts must be in `manifest.runtime.egress_allowed_hosts`. |
| `os.compliance.audit_query` | Read your own capability call audit log. |
| `os.apps.call` | Sync RPC to another v2 app. |

See `references/capabilities-reference.md` for input/output schemas, error codes, and quotas.

## Step 4 — Deploy

You need a `mna_*` token. Get it via the desktop UI: **Dev Hub → "v2 Tokens (Beta)" → Generate**. Shown once, save to `.env.manaurum`:

```
MANAURUM_V2_TOKEN=mna_<keyid>_<secret>
```

The deploy is a single API call. Bundle the build context, base64-encode, post:

```bash
cd my-app
tar cf /tmp/ctx.tar \
  --exclude='.env*' --exclude='.git' --exclude='node_modules' \
  --exclude='deploy.sh' --exclude='*.tar' --exclude='*.zip' \
  .

B64=$(base64 -w0 /tmp/ctx.tar)
jq -n --arg b "$B64" --argjson m "$(cat manifest_v2.json)" \
  '{manifest_json: $m, archive_b64: $b}' > /tmp/deploy.json

curl -sS -X POST https://manaurum.com/api/dev/v2/deploy \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/deploy.json | jq .
```

Response on success (returned synchronously when the deploy finishes — usually ~7-10s):

```json
{
  "deploy_job_id": "<uuid>",
  "status": "succeeded"
}
```

Then poll the job for the URL:

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

A `deploy.sh` template for the project: see `manaurum-deploy/SKILL.md`.

## Step 5 — Update + rollback

- **New version**: bump `manifest_v2.json.version` (semver), retar, redeploy. Same endpoint. The platform records a new `v2_app_versions` row and updates the swarm service in-place.
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
| 502 (during deploy) | Image build failed. | Look at `result.error` for the Docker stderr. Common: `EXPOSE` missing, `COPY` source doesn't exist. |

## Tenant context inside the container

The platform sets these env vars on every task:

| Env var | Value |
|---|---|
| `MANAURUM_TENANT_ID` | UUID of the tenant your app is installed in. |
| `MANAURUM_APP_ID` | UUID of your app in `v2_apps`. Use as `X-Manaurum-App-Id`. |
| `MANAURUM_VERSION` | The semver of the running version. |
| `MANAURUM_BROKER_URL` / `DATABASE_URL` | Postgres broker DSN (only meaningful when you opt into a dedicated app schema). |

Your data is **automatically tenant-scoped** by the platform's RLS policies on `app_kv`, `app_secrets`, audit log, etc. You don't need to filter by `tenant_id` in your queries — the platform does it server-side. Use `MANAURUM_TENANT_ID` only for display/branding ("welcome to <tenant>", per-tenant theming, etc.), never as a security filter.

## What NOT to do

- **Don't bake the `mna_*` token into the image.** Pass it via env at deploy time or as a v2 secret (`os.secrets.set` once, `os.secrets.get` at runtime).
- **Don't write to host paths.** Volumes aren't mounted into v2 apps. Use `os.files.upload` (R2) for any persistent files.
- **Don't expect side-channel network access.** `egress_allowed_hosts` controls outbound; DROP everything else. If you need a third-party API, declare it.
- **Don't use the v1 `mnu_*` token format.** v2 uses `mna_*` exclusively. The two are different surfaces.
- **Don't try to talk to other tenants.** Capabilities are tenant-scoped at the gateway level — you'd get 403 anyway.

---

## Legacy v1 (iframe) — for existing apps only

> **Don't use this for new apps.** v1 is feature-frozen for existing builtins (Receptions, Finance, Radio, etc.) and tenant-scoped iframe apps already in production. New work goes on v2.

A v1 app is a static HTML+JS bundle loaded in a sandboxed iframe by the OS shell. The bundle is uploaded as a zip via `POST /api/dev/apps/deploy` with an `mnu_*` (NOT `mna_*`) token. The bundle communicates with the OS over `postMessage` via the `manaurum.js` SDK.

If you genuinely need to update a v1 app, see:
- `references/sdk-api.md` — full v1 SDK reference (storage, files, db, ai, mul, …)
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

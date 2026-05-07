---
name: manaurum-deploy
description: Deploy a ManAurum OS app. As of 2026-05, the default flow is Platform v2 (containerized — `POST /api/dev/v2/deploy` with an `mna_*` token). Legacy v1 (iframe bundle — `POST /api/dev/apps/deploy` with an `mnu_*` token) is supported for existing apps. Use whenever the user wants to deploy, publish, host, upload, or release their ManAurum/SeregaOS app. Covers token issuance, build context preparation, deploy contract, rejection codes, rollback, and the post-deploy install/open flow.
---

# Deploy ManAurum App

> ## ⚡ v2 is the default (2026-05)
>
> Two paths exist. Pick by **token format the user has**:
>
> - **`mna_*`** → v2 hosted runtime. `POST /api/dev/v2/deploy`. Builds a Docker image from a tarball, pushes to a private registry, runs as a Swarm service, exposes at `https://<slug>.apps.manaurum.com`. **Default for all new work.**
> - **`mnu_*`** → v1 iframe runtime. `POST /api/dev/apps/deploy`. Uploads a zip bundle, served in an iframe at `/t/<tenant>/apps/<slug>`. **Legacy — only for existing v1 apps.**
>
> If unsure or the user has neither, ask them to mint an `mna_*` from Dev Hub → "v2 Tokens (Beta)" → Generate. **The two surfaces are not interchangeable** — a `mnu_*` token will be rejected by the v2 endpoint and vice versa.

---

## v2 deploy (default)

### Prereqs

- An `mna_*` token in `.env.manaurum` as `MANAURUM_V2_TOKEN=...`. Mint one in Dev Hub → "v2 Tokens (Beta)" → Generate. Shown ONCE, save immediately.
- A project directory containing `manifest_v2.json` + `Dockerfile` + your source files. See `manaurum-app/SKILL.md` for the full manifest reference.

### Quickstart

```bash
cd my-app
tar cf /tmp/ctx.tar Dockerfile $(ls -A | grep -v '^\.env')

B64=$(base64 -w0 /tmp/ctx.tar)
jq -n \
  --arg b "$B64" \
  --argjson m "$(cat manifest_v2.json)" \
  '{manifest_json: $m, archive_b64: $b}' > /tmp/deploy.json

curl -sS -X POST https://manaurum.com/api/dev/v2/deploy \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/deploy.json | jq .
```

Successful response (sync — usually returns in ~7–10s):

```json
{ "deploy_job_id": "...", "status": "succeeded" }
```

If `status: pending` (rare for hosted runtime), poll the job:

```bash
curl -sS https://manaurum.com/api/dev/v2/deploy/<deploy_job_id> \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN" | jq .
```

Final response carries the URL:

```json
{
  "status": "succeeded",
  "result": {
    "app_id":     "<uuid>",
    "version_id": "<uuid>",
    "image_tag":  "manaurum-registry:5000/v2-app-my-app:1.0.0",
    "url":        "https://my-app.apps.manaurum.com"
  }
}
```

The URL is live with a Let's Encrypt cert within seconds of the deploy completing.

### What the platform does on v2 deploy

1. Validates the manifest against the v2 JSON Schema.
2. Validates any migration SQL via the R-1.5 AST validator (additive-only unless `migration.breaking: true`).
3. Builds the Docker image **inside the backend container** from your tar (`POST /build` to the engine API).
4. Pushes the image to the local `manaurum-registry`.
5. Inserts/updates `v2_apps` + `v2_app_versions` rows under the home tenant (FORCE-RLS).
6. Creates or updates the swarm service `v2-app-<slug>-<tenant_short>` on `dokploy-network`.
7. Writes a Traefik dynamic-config YAML at `/etc/dokploy/traefik/dynamic/v2-app-<slug>.yml` so the URL routes to the service.

### Bump version + redeploy

```bash
jq '.version = "1.0.1"' manifest_v2.json > /tmp/m && mv /tmp/m manifest_v2.json
# rerun the curl above — the platform updates the swarm service in-place
```

The URL stays the same. Existing connections drain; new requests hit the new version.

### Rollback

```bash
curl -sS -X POST https://manaurum.com/api/dev/v2/apps/<app_id>/rollback \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN"
```

Restores the previous version's image. Same URL, no traffic interruption.

### List versions / inspect / logs

```bash
# describe
curl -sS https://manaurum.com/api/dev/v2/apps/<app_id> -H "Authorization: Bearer $MANAURUM_V2_TOKEN"

# version history
curl -sS https://manaurum.com/api/dev/v2/apps/<app_id>/versions -H "Authorization: Bearer $MANAURUM_V2_TOKEN"

# tail logs (stub — full streaming TBD)
curl -sS https://manaurum.com/api/dev/v2/apps/<app_id>/logs -H "Authorization: Bearer $MANAURUM_V2_TOKEN"
```

### v2 rejection codes

| HTTP | `error` | Meaning | Fix |
|---|---|---|---|
| 401 | `invalid_credential` | Bad/expired/revoked `mna_*` token, or not an `mna_*`. | Mint a fresh one in Dev Hub. |
| 401 | `missing_authorization` | No `Authorization` header. | Add `-H "Authorization: Bearer $MANAURUM_V2_TOKEN"`. |
| 412 | `missing_tenant_id_header` | (capability calls only) `X-Manaurum-Tenant-Id` not set. | Set it from `process.env.MANAURUM_TENANT_ID`. |
| 422 | `manifest validation failed` | Manifest fails v2 JSON Schema. | Read `errors[]`. Common: bad `app_id` slug, non-semver `version`. |
| 422 | `migration_validation_failed` | Destructive DDL without `migration.breaking: true`. | Make additive-only or set `breaking: true`. |
| 422 | `invalid_archive_b64` | Bundle isn't valid base64. | Use `base64 -w0` (no line wrapping). |
| 502 | (in `result.error`) | Image build failed. | Inspect the error string — usually a Dockerfile issue (`COPY src not found`, missing `EXPOSE`, etc.). |

### Multi-tenant deploys (v2 visibility)

The v2 manifest's `visibility.mode` controls which tenants can install the app:

- `private` (default) — only the home tenant (the one tied to your `mna_*` token) sees it.
- `public` — any tenant can install it via App Store v2.
- `allow_list` with a `tenants` array — explicit list of tenant UUIDs.

For `public` / `allow_list`, the install itself is initiated by a **tenant admin** in the consuming tenant via `POST /api/app-store/v2/install`. The deploy is a separate operation done once by the developer.

This is fundamentally different from v1, where each tenant requires its own deploy. v2 has a global app registry; v1 had per-tenant catalogs.

---

## v1 deploy (legacy — iframe apps only)

> **Don't use this for new apps.** v1 is for maintaining existing iframe-based builtins.

### v1 prereqs

- An `mnu_*` token (NOT `mna_*`). Mint via:
  ```bash
  curl -sS -X POST https://manaurum.com/api/developer/tenant-tokens \
    -H "Authorization: Bearer $SESSION_JWT" \
    -H "Content-Type: application/json" \
    -d '{"name": "ci-deploy"}'
  ```
  Or via Dev Hub → "API Tokens" tab in the UI. Default scopes `["app.deploy", "app.read"]`.
- A `manifest.json` (v1 schema — `manifest_version: "1"`) + a zip bundle with `index.html` at the root.

### v1 quickstart

```bash
cd my-app
zip -r bundle.zip . -x "*.DS_Store" "node_modules/*" ".git/*" ".env*"

B64=$(base64 -w0 bundle.zip)
jq -n --arg b "$B64" --slurpfile m manifest.json '{manifest: $m[0], bundle: $b}' \
  | curl -sS -X POST https://manaurum.com/api/dev/apps/deploy \
      -H "Authorization: Bearer $MANAURUM_TENANT_TOKEN" \
      -H "Content-Type: application/json" \
      -d @- | jq .
```

Success body:
```json
{
  "application_id": "...",
  "version_id":     "...",
  "version_number": "1.0.0",
  "url": "/t/<tenant_slug>/apps/<app_slug>"
}
```

After deploy, a workspace owner inside the same tenant must install the app via the AppStore desktop app. Members can then open `/t/<tenant_slug>/apps/<app_slug>` and the iframe loads.

### v1 hard limits

- Max bundle: 50 MB.
- Allowed extensions: `.html .htm .js .mjs .jsx .ts .tsx .css .svg .png .jpg .jpeg .gif .webp .ico .avif .woff .woff2 .ttf .otf .eot .txt .md .map .webmanifest`.
- The bundle scanner rejects credential patterns (`sk_live_`, `AKIA`, `ghp_`, …), undeclared 3rd-party SDKs, disallowed URLs.

### v1 rejection codes

| HTTP | `rejection` | Fix |
|---|---|---|
| 401 | `rejected_token_invalid` | Issue a fresh `mnu_*`. |
| 403 | `rejected_insufficient_scope` | Token needs `app.deploy`. |
| 400 | `rejected_manifest_invalid` | Read `findings[]`; fix manifest. |
| 400 | `rejected_version_conflict` | Bump semver. |
| 413 | `rejected_bundle_too_large` | > 50 MB — trim. |
| 422 | `rejected_bundle_credential_detected` | Remove the credential. |
| 422 | `rejected_bundle_sdk_undeclared` | Declare in `manifest.integrations[]`. |

### v1 multi-tenant

A `mnu_*` token is bound to ONE tenant. Deploying the same app to a second tenant requires a separate `mnu_*` from THAT tenant.

### v1 token housekeeping

```bash
# list (no raw_token returned)
curl -sS https://manaurum.com/api/developer/tenant-tokens \
  -H "Authorization: Bearer $SESSION_JWT"

# revoke
curl -sS -X DELETE "https://manaurum.com/api/developer/tenant-tokens/<token_id>" \
  -H "Authorization: Bearer $SESSION_JWT"
```

Cap: 5 active tokens per (user, tenant). Revoke an old one if you hit `409 max_active_tokens_reached`.

---

## `deploy.sh` template (v2)

When scaffolding a new project, drop this in:

```bash
#!/bin/bash
# Deploy a v2 ManAurum app — POST /api/dev/v2/deploy
set -e

if [ -f .env.manaurum ]; then
  set -a; source .env.manaurum; set +a
fi

if [ -z "$MANAURUM_V2_TOKEN" ]; then
  echo "Error: MANAURUM_V2_TOKEN not set. Mint one at https://manaurum.com (Dev Hub → v2 Tokens)."
  echo "Save as MANAURUM_V2_TOKEN=mna_<...> in .env.manaurum"
  exit 1
fi

if [ ! -f manifest_v2.json ]; then
  echo "Error: manifest_v2.json missing. See manaurum-app/SKILL.md."
  exit 1
fi
if [ ! -f Dockerfile ]; then
  echo "Error: Dockerfile missing. v2 apps build images."
  exit 1
fi

echo "Bundling build context…"
tar cf /tmp/ctx.tar \
  Dockerfile \
  $(ls -A | grep -vE '^(\.env|\.git|node_modules|deploy\.sh)')

echo "Deploying…"
B64=$(base64 -w0 /tmp/ctx.tar)
RESP=$(jq -n --arg b "$B64" --argjson m "$(cat manifest_v2.json)" \
  '{manifest_json: $m, archive_b64: $b}' \
  | curl -sS -X POST https://manaurum.com/api/dev/v2/deploy \
      -H "Authorization: Bearer $MANAURUM_V2_TOKEN" \
      -H "Content-Type: application/json" \
      -d @-)

JOB_ID=$(echo "$RESP" | jq -r .deploy_job_id)
STATUS=$(echo "$RESP" | jq -r .status)
echo "Job: $JOB_ID — status: $STATUS"

if [ "$STATUS" != "succeeded" ]; then
  curl -sS https://manaurum.com/api/dev/v2/deploy/$JOB_ID \
    -H "Authorization: Bearer $MANAURUM_V2_TOKEN" | jq .
  exit 1
fi

curl -sS https://manaurum.com/api/dev/v2/deploy/$JOB_ID \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN" \
  | jq -r '.result | "✓ Live at \(.url)"'

rm -f /tmp/ctx.tar
```

Make executable: `chmod +x deploy.sh`.

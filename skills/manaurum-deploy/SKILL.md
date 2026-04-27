---
name: manaurum-deploy
description: Deploy a ManAurum OS app to a tenant via the Deploy API (manifest+bundle). Use when the user wants to deploy, publish, host, upload, or release their ManAurum/SeregaOS app. Covers tenant API-token issuance, manifest+bundle.zip preparation, the POST /api/dev/apps/deploy contract, rejection codes, and post-deploy install/open flow.
---

# Deploy ManAurum OS App (v1.5+ tenant-aware)

Help the user deploy their ManAurum OS app to a specific **tenant** via the Deploy API.

In v1.5 there is one canonical deploy path: a tenant-scoped `mnu_*` token authorises a `POST /api/dev/apps/deploy` request carrying a manifest object and a base64-encoded bundle. The same payload format is used for first deploy and every subsequent version.

> **One token = one tenant.** A `mnu_*` token is bound to the tenant of the user who issued it. To deploy the same app to another tenant, get a separate token from THAT tenant's Developer Console.

## Quickstart (assuming you already have `MANAURUM_TENANT_TOKEN`)

```bash
cd my-app
zip -r bundle.zip .

B64=$(base64 -w0 bundle.zip)
jq -n --arg b "$B64" --slurpfile m manifest.json '{manifest: $m[0], bundle: $b}' \
  | curl -sS -X POST https://manaurum.com/api/dev/apps/deploy \
      -H "Authorization: Bearer $MANAURUM_TENANT_TOKEN" \
      -H "Content-Type: application/json" \
      -d @- | jq .
```

Success response:
```json
{
  "application_id": "...",
  "version_id": "...",
  "version_number": "1.0.0",
  "deployed_at": "2026-04-27T19:00:00Z",
  "url": "/t/<your-tenant-slug>/apps/<your-app-slug>"
}
```

The app is now in your tenant's catalog. To make it visible to users, a workspace owner must install it (see "After Deploy — Install in Workspace" below).

---

## Step 1 — Issue a tenant token

The user needs a `mnu_*` token. Two ways:

### A) Self-serve via API (recommended)

The user is signed in to the platform (has a SESSION_JWT). They mint a token bound to their active tenant:

```bash
curl -sS -X POST https://manaurum.com/api/developer/tenant-tokens \
  -H "Authorization: Bearer $SESSION_JWT" \
  -H "Content-Type: application/json" \
  -d '{"name": "ci-deploy"}'
```

Default scopes are `["app.deploy", "app.read"]`. To customise:

```bash
curl -sS -X POST https://manaurum.com/api/developer/tenant-tokens \
  -H "Authorization: Bearer $SESSION_JWT" \
  -H "Content-Type: application/json" \
  -d '{"name": "deploy-only", "scopes": ["app.deploy"]}'
```

Response is shown ONCE:
```json
{
  "token_id": "...",
  "name": "ci-deploy",
  "prefix": "mnu_",
  "raw_token": "mnu_prod_<32-chars>",
  "scopes": ["app.deploy", "app.read"],
  "expires_at": null,
  "created_at": "..."
}
```

Save the `raw_token` immediately. Cap is 5 active tokens per user per tenant; revoke an old one first if you hit `409 max_active_tokens_reached`.

### B) Through the Developer Console UI

Sign in → Developer Console → Tokens → "Issue new token". The UI calls the same endpoint and shows `raw_token` once.

### Token housekeeping

```bash
# List active tokens (no raw_token returned)
curl -sS https://manaurum.com/api/developer/tenant-tokens \
  -H "Authorization: Bearer $SESSION_JWT"

# Revoke a token
curl -sS -X DELETE "https://manaurum.com/api/developer/tenant-tokens/<token_id>" \
  -H "Authorization: Bearer $SESSION_JWT"
```

## Step 2 — Store the token locally

```bash
# .env.manaurum (already gitignored if you used /manaurum-setup)
MANAURUM_TENANT_TOKEN=mnu_prod_<32-chars>

# or in shell
export MANAURUM_TENANT_TOKEN=mnu_prod_<32-chars>
```

## Step 3 — Prepare the bundle

Bundle is a single zip file with `index.html` at the root.

```
my-app/
├── manifest.json
├── index.html        ← MUST be at the root of the zip
├── style.css         ← optional
├── app.js            ← optional
└── assets/           ← optional
```

```bash
cd my-app
zip -r bundle.zip . -x "*.DS_Store" "node_modules/*" ".git/*" ".env*"
```

Hard limits:
- **Max bundle size:** 50 MB
- **File extensions whitelist:** `.html .htm .js .mjs .jsx .ts .tsx .css .svg .png .jpg .jpeg .gif .webp .ico .avif .woff .woff2 .ttf .otf .eot .txt .md .map .webmanifest`
- **Anti-Lovable scanner** rejects bundles containing credentials (`sk_live_`, `AKIA`, `ghp_`, etc.), undeclared 3rd-party SDKs (Supabase, Firebase, Auth0, Clerk, Stripe...), or disallowed URLs.

To use a 3rd-party SDK legitimately, declare it in `manifest.integrations[]` (see manifest-spec.md).

## Step 4 — Deploy

```bash
B64=$(base64 -w0 bundle.zip)
jq -n --arg b "$B64" --slurpfile m manifest.json '{manifest: $m[0], bundle: $b}' \
  | curl -sS -X POST https://manaurum.com/api/dev/apps/deploy \
      -H "Authorization: Bearer $MANAURUM_TENANT_TOKEN" \
      -H "Content-Type: application/json" \
      -d @- | jq .
```

Note the response `url` — that's where users in your tenant will open the app once installed.

## Step 5 — Bump and redeploy

To ship a new version, bump `manifest.json` `version` (semver) and rerun the same `POST /api/dev/apps/deploy`. The platform creates a new `application_versions` row and atomically updates `current_version_id` to the new one. Existing users get the new version on next iframe load.

```bash
# bump version
jq '.version = "1.0.1"' manifest.json > /tmp/m && mv /tmp/m manifest.json

# rebuild + redeploy
zip -r bundle.zip . -x "*.DS_Store" ".git/*" ".env*"
# ... same curl as Step 4
```

## After Deploy — Install in workspace

Deploy puts the app in your tenant's **catalog**. It is NOT yet visible to end users. A workspace owner inside the same tenant must install it via AppStore:

1. Sign in as a workspace owner of any workspace in your tenant.
2. Open AppStore.
3. Find your app, click "Install".
4. The install creates a `workspace_app_installs` row that grants the app to that workspace's members.

Members can now open `/t/<tenant_slug>/apps/<app_slug>`.

## Rejection Codes

| HTTP | `rejection` | Meaning | Fix |
|---|---|---|---|
| 401 | `rejected_missing_bearer` | No `Authorization` header | Add `-H "Authorization: Bearer $MANAURUM_TENANT_TOKEN"` |
| 401 | `rejected_token_invalid` | Bad / expired / revoked token | Issue a fresh token |
| 403 | `rejected_insufficient_scope` | Token lacks `app.deploy` | Issue with scopes including `app.deploy` |
| 400 | `rejected_manifest_invalid` | Manifest fails v1 schema | Read `findings`; fix and retry |
| 400 | `rejected_bundle_not_base64` | `bundle` field is not valid base64 | Use `base64 -w0` (no line wrapping) |
| 400 | `rejected_version_conflict` | A version with this `version` already exists | Bump semver |
| 413 | `rejected_bundle_too_large` | > 50 MB | Trim assets |
| 422 | `rejected_bundle_extension_blocked` | File with disallowed extension in bundle | Remove or convert |
| 422 | `rejected_bundle_credential_detected` | Scanner found a credential pattern | Remove the credential |
| 422 | `rejected_bundle_sdk_undeclared` | Undeclared 3rd-party SDK import | Declare in `manifest.integrations[]` |
| 422 | `rejected_bundle_url_disallowed` | URL outside platform CDN whitelist | Use `jsdelivr`/`unpkg`/`cdnjs` or declare integration |

The response body always carries:
```json
{
  "rejection": "<code>",
  "message": "<human description>",
  "findings": [...optional details...]
}
```

## Verify the live app

After deploy + install, sanity-check the app loads in the shell:

```bash
# Replace <session_jwt> with a logged-in user's token
curl -sS -I https://manaurum.com/t/<tenant_slug>/apps/<app_slug> \
  -H "Authorization: Bearer <session_jwt>"
```

Expected:
- `200 OK` if user is in the right tenant + workspace install exists
- `401` / `403` if user not authenticated
- `404` if user is in a different tenant, or the workspace doesn't have the app installed (uniform 404 — no info leak)

Open the URL in a browser to load the iframe and verify `manaurum:init` arrives in your app (use devtools → Console).

## Multi-tenant deploys

If the same app must be available in multiple tenants, **deploy it independently to each tenant** with a token from THAT tenant. The platform does not support cross-tenant publishing — each tenant has its own catalog.

```bash
# tenant 1
export MANAURUM_TENANT_TOKEN=mnu_prod_<acme-token>
# ...deploy

# tenant 2
export MANAURUM_TENANT_TOKEN=mnu_prod_<beta-token>
# ...deploy (same bundle, different tenant)
```

## Deploy script helper

When generating an app, also create a `deploy.sh`:

```bash
#!/bin/bash
# Deploy to ManAurum OS — tenant-scoped manifest+bundle Deploy API
set -e

if [ -f .env.manaurum ]; then
  set -a; source .env.manaurum; set +a
fi

if [ -z "$MANAURUM_TENANT_TOKEN" ]; then
  echo "Error: MANAURUM_TENANT_TOKEN not set."
  echo "Issue one at https://manaurum.com (Developer Console → Tokens)."
  echo "Save as MANAURUM_TENANT_TOKEN=mnu_prod_<32> in .env.manaurum"
  exit 1
fi

echo "Bundling..."
zip -r /tmp/bundle.zip . -x "*.DS_Store" "node_modules/*" ".git/*" ".env*" "deploy.sh" >/dev/null

echo "Deploying..."
B64=$(base64 -w0 /tmp/bundle.zip)
jq -n --arg b "$B64" --slurpfile m manifest.json '{manifest: $m[0], bundle: $b}' \
  | curl -sS -X POST https://manaurum.com/api/dev/apps/deploy \
      -H "Authorization: Bearer $MANAURUM_TENANT_TOKEN" \
      -H "Content-Type: application/json" \
      -d @- | jq .

rm -f /tmp/bundle.zip
```

When creating an app, generate this script with the right name set in `manifest.json`.

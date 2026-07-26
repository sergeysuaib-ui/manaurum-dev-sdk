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
- A project directory containing `manifest.json` + `Dockerfile` + your source files. See `manaurum-app/SKILL.md` for the full manifest reference.

### Quickstart

```bash
cd my-app
tar cf /tmp/ctx.tar \
  --exclude='.env*' --exclude='.git' --exclude='node_modules' \
  --exclude='.venv' --exclude='venv' --exclude='__pycache__' \
  --exclude='.pytest_cache' --exclude='dist' --exclude='build' \
  --exclude='deploy.sh' --exclude='*.tar' --exclude='*.zip' \
  .

# Base64 into a FILE, and read it with --rawfile / --slurpfile.
# Do NOT do `B64=$(base64 …)` + `jq --arg b "$B64"`: that puts the whole
# archive on the command line and dies with "Argument list too long" on
# any real project (Windows caps argv at 32 KB; a 60 KB tar is already
# 80 KB of base64). `tr -d '\n'` leaves no trailing newline, which the
# archive must not have.
base64 < /tmp/ctx.tar | tr -d '\n' > /tmp/ctx.b64
jq -n --rawfile b /tmp/ctx.b64 --slurpfile m manifest.json \
  '{manifest_json: $m[0], archive_b64: $b}' > /tmp/deploy.json

curl -sS -X POST https://manaurum.com/api/dev/v2/deploy \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/deploy.json | jq .

rm -f /tmp/ctx.tar /tmp/ctx.b64
```

The `.venv` / `__pycache__` excludes are not cosmetic: without them a Python
project that has been `pip install`ed locally ships its whole virtualenv —
measured at **58 MB instead of 60 KB** on a 20-file app.

### The deploy is asynchronous — always

`POST /api/dev/v2/deploy` returns HTTP **202** and *always* this body. It never returns
`succeeded`:

```json
{ "deploy_job_id": "<uuid>", "status": "pending" }
```

Build, registry push, Swarm, Traefik and migrations all run on a background task (the route is
`@router.post("/deploy", status_code=202)` and its single `return` is
`{"deploy_job_id": job_id, "status": "pending"}`). A Docker build gets up to 300s server-side.
**Never read success off the POST response** — a script that does reports failure on 100% of
successful deploys.

Poll until the job reaches a terminal status:

```bash
curl -sS https://manaurum.com/api/dev/v2/deploy/<deploy_job_id> \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN" | jq .
```

`status` stays `pending` until the job settles, then becomes exactly one of **`succeeded`** or
**`failed`**. `result` is populated only on `succeeded`; `error` carries the reason on `failed`:

```json
{
  "job_id":     "<uuid>",
  "status":     "succeeded",
  "created_at": "2026-07-22T10:04:11+00:00",
  "result": {
    "app_id":     "<uuid>",
    "version_id": "<uuid>",
    "image_tag":  "manaurum-registry:5000/v2-app-my-app:1.0.0",
    "url":        "https://my-app.apps.manaurum.com"
  },
  "error":  null,
  "events": []
}
```

A `deploy_job_id` read by any other identity (another tenant, a sibling user, a credential
narrowed to a different app) returns `404 job_not_found` — never 403.

### Follow progress live

```bash
curl -sSN https://manaurum.com/api/dev/v2/deploy/<deploy_job_id>/stream \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN"
```

`application/x-ndjson` — one JSON object per line in `seq` order, terminated by a
`{"terminal": true, "status": "succeeded"|"failed"}` line once the job settles. On disconnect,
re-open and skip lines whose `seq` you have already seen.

### Only three things fail synchronously

The POST checks the credential, the credential's app scope, and the base64 — nothing else:

- `401 invalid_credential` / `401 missing_authorization`
- `403 app_id_out_of_scope` — the `mna_*` credential isn't authorised for this `app_id`
- `422 invalid_archive_b64`

**Manifest schema, migration DDL, the `migrations/` layout and the Docker build are all
validated inside the job** and surface as `status: "failed"` with the reason in `error`. So the
CLI deploy path gives you no synchronous manifest feedback — run `manaurum app validate` before
you deploy.

### `succeeded` does NOT mean the app works

There is **no readiness probe anywhere in the hosted deploy path.** `succeeded` means: the image
built and pushed, the Swarm service spec was accepted, the Traefik dynamic config was written,
and the per-tenant migration fan-out ran. It does **not** mean a process is listening, that the
container survived boot, or that the URL answers 200. A container that crash-loops or binds the
wrong interface still produces a `succeeded` job.

Two more things `succeeded` does not cover: a **per-tenant migration failure does not fail the
job** — it is recorded per install and the version still activates; and the app has no desktop
window until `frontend.entry_point` is declared and the page answers the `manaurum:ready`
handshake.

**Check it yourself after every deploy.** Serve a `/healthz` on your container and hit it — this
is a required step, not a nicety:

```bash
for _ in $(seq 1 15); do
  if curl -fsS https://my-app.apps.manaurum.com/healthz >/dev/null; then
    echo "serving"; break
  fi
  sleep 2
done
```

`/healthz` is not an `/api/*` path, so it needs no `runtime.api_routes` entry and is proxied
anonymously. A plain `curl` sends no `Sec-Fetch-Dest: document` and an `Accept: */*`, so the
gateway does not treat it as a browser navigation and will not 302 it to login even though
pages are default-private. Give Swarm ~30s to place the new task before you call it a failure.
Once it serves, the URL has a Let's Encrypt cert.

### What the platform does on v2 deploy

All of this runs **inside the background job**, after the 202 has already gone back to you:

1. Validates the manifest against the v2 JSON Schema.
2. Validates any migration SQL via the R-1.5 AST validator (additive-only unless `migration.breaking: true`).
3. Builds the Docker image **inside the backend container** from your tar (`POST /build` to the engine API).
4. Pushes the image to the local `manaurum-registry`.
5. Inserts/updates `v2_apps` + `v2_app_versions` rows under the home tenant (FORCE-RLS).
6. Creates or updates the swarm service `v2-app-<slug>-<tenant_short>` on `dokploy-network`.
7. Writes a Traefik dynamic-config YAML at `/etc/dokploy/traefik/dynamic/v2-app-<slug>.yml` so the URL routes to the service.
8. **Retains the build context** (your uploaded tar) in object storage, per version (MAN-990). Your source is no longer single-copy on your machine, and a version stays rebuildable even after its image is pruned. A rolling window is kept (newest ~10 per app + the live one); download any retained version's source via the route below or `manaurum app fetch-source` (see "Source retention").

### Bump version + redeploy

```bash
jq '.version = "1.0.1"' manifest.json > /tmp/m && mv /tmp/m manifest.json
# rerun the curl above — the platform updates the swarm service in-place
```

The URL stays the same. Existing connections drain; new requests hit the new version.

### Migrations across redeploys

Schema changes ship as plain `.sql` files directly under a top-level `migrations/` directory of
your build context. Each file runs **once per (app, tenant)** in lexical filename order; applied
files are recorded so redeploys skip them.

**Never edit a migration that has already been applied.** Every applied file is pinned by sha256
per `(app_id, tenant_id, filename)`. Re-uploading `0001_init.sql` with different bytes does not
re-run it — it marks that tenant's migration run `failed`, and the new version still activates,
so the app goes live against a schema that was never migrated. To change schema, **add
`0002_<what>.sql`.** Same rule for a file you only reformatted: different bytes, same failure.

The DDL is parsed with `pglast` and is additive-only by default. `migration.breaking: true`
unlocks *destructive* statements (`DROP …`, `RENAME`, `TRUNCATE`, `ALTER COLUMN … TYPE`); it does
**not** unlock *forbidden* ones (`DO $$ … $$`, `COPY`, `CREATE EXTENSION`, `BEGIN`/`COMMIT`,
any `SET`, role/database DDL). Anything the validator does not recognise is forbidden by default.
Full classification: `manaurum-app/SKILL.md`.

### Rollback

```bash
curl -sS -X POST https://manaurum.com/api/dev/v2/apps/<app_id>/rollback \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"version_label": "1.0.0"}'
```

`version_label` is required — name the already-published version you want live. Rollback
re-points Swarm, Traefik and `v2_apps.current_version_id` at that version's image. It is **not**
a schema revert: the migration contract is additive-only and applied migrations stay applied.

Same async shape as deploy — **202 + `{"deploy_job_id", "status": "pending"}`** — so poll
`GET /api/dev/v2/deploy/{job_id}` exactly as above, and re-check `/healthz` afterwards. Same
URL, no traffic interruption.

### List versions / inspect / logs

```bash
# describe
curl -sS https://manaurum.com/api/dev/v2/apps/<app_id> -H "Authorization: Bearer $MANAURUM_V2_TOKEN"

# version history
curl -sS https://manaurum.com/api/dev/v2/apps/<app_id>/versions -H "Authorization: Bearer $MANAURUM_V2_TOKEN"

# tail logs (stub — full streaming TBD)
curl -sS https://manaurum.com/api/dev/v2/apps/<app_id>/logs -H "Authorization: Bearer $MANAURUM_V2_TOKEN"
```

### Source retention (recover a version's source)

Every deploy's build context is retained per version (MAN-990), so you can
recover the exact source a version was built from. `…/versions` flags which
versions still have a retained archive (`has_source`).

```bash
# returns a short-TTL signed download URL: {available, url, sha256, size_bytes, expires_in}
curl -sS https://manaurum.com/api/dev/v2/apps/<app_id>/versions/<version>/source \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN"
```

`404 source_not_retained` means the version predates retention or its archive
aged out of the rolling window (newest ~10 per app + the live version are kept).
The archive is scoped to your tenant — never exposed to tenants that install your
app. From the CLI this is `manaurum app fetch-source <version> --app-id <slug>`;
in DevHub it's the per-version "Download source" button.

Every deploy is **also** committed to a per-`(tenant, app)` bare git repo — one commit plus a
`v<version>` tag — readable via `GET /api/dev/v2/apps/<app_id>/history` and
`…/diff`. That history is append-only and is **not** pruned by the tarball window above: a
version whose archive has aged out still has its files in the git history.

> **Whatever you ship, you ship forever.** The CLI packager excludes `__pycache__`, `.venv`,
> `.git`, the `*_cache` dirs, `node_modules`, `dist` and `build` — it does **not** exclude
> `.env`, `.env.local`, `.env.manaurum` or any other dotfile. A secret that lands in the tar is
> downloadable by anyone who can call `fetch-source` for your tenant, and is permanently in the
> git history even after the tarball is pruned. **Keep secrets out of the app directory
> entirely** (put `.env.manaurum` in the parent dir or your shell profile), and ship a
> `.dockerignore` as a second line of defence. Rotating the credential is the only remedy after
> the fact.

### v2 rejection codes (synchronous, from the POST)

| HTTP | `detail` | Meaning | Fix |
|---|---|---|---|
| 401 | `invalid_credential` | Bad/expired/revoked `mna_*` token, or not an `mna_*`. | Mint a fresh one in Dev Hub. |
| 401 | `missing_authorization` | No `Authorization` header. | Add `-H "Authorization: Bearer $MANAURUM_V2_TOKEN"`. |
| 403 | `app_id_out_of_scope` | The credential's `apps` list doesn't cover the manifest's `app_id`. | Use a credential scoped to this app (or `*`). |
| 422 | `invalid_archive_b64` | Archive isn't valid base64. | Encode with `base64 < file | tr -d '\n'` — the archive must be one unwrapped line. (`base64 -w0` is GNU-only and fails on macOS.) |
| 412 | `missing_tenant_id_header` | (capability calls only, not deploy) `X-Manaurum-Tenant-Id` not set. | Set it from `process.env.MANAURUM_TENANT_ID`. |

Everything else is a **job failure**, not an HTTP error — see below.

### Failures you'll actually hit (job `failed`, or after the deploy is green)

| Symptom | Cause | Fix |
|---|---|---|
| `404 route_not_declared` from one of your API paths | `runtime.api_routes` is **default-deny**. A path that matches no rule is rejected by the gateway and never reaches your container. | Declare it. `/api/tasks/*` does **not** match the bare `/api/tasks` — declare both. There is no `method` field; one rule covers every verb. |
| `502` on the app URL right after a `succeeded` deploy | Nothing is listening where the gateway proxies. The upstream is `<swarm-service>:<port>`, where `port` is `manifest.runtime.port` if present and **80** otherwise. `EXPOSE` in your Dockerfile is never parsed by anything in Core. Also fires when the process bound `127.0.0.1` instead of `0.0.0.0`. | Bind `0.0.0.0` on port 80, or declare `runtime.port` to match what you bind: `CMD ["uvicorn","main:app","--host","0.0.0.0","--port","80"]`. |
| Job `failed`, error contains `non-SQL file in migrations/` | A non-`.sql` **regular file directly under** `migrations/` — a `README.md`, a `.gitkeep`, or `0001.SQL` (the extension check is case-sensitive). | Move it elsewhere in the bundle. Subdirectories under `migrations/` are ignored, not rejected. **This is a job `failed`, NOT a 422 from the POST** — the layout is checked inside the job. |
| Job `failed`, error contains `DO $$ … $$ — arbitrary PL/pgSQL body is not analysable` | The DDL validator classifies anonymous `DO` blocks as **forbidden**: it cannot AST-check the body. `migration.breaking: true` does **not** override this — `breaking` only unlocks *destructive* statements. | Expand the block into plain statements (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE … ADD COLUMN IF NOT EXISTS`, …). A first-party app shipped this exact bug (MAN-1327). |
| Job `failed`, `manifest v2 validation failed (1 error): <root>: Additional properties are not allowed ('description' was unexpected)` | The manifest root is `additionalProperties: false`. `description`, `icon` and `category` are **not** root keys. | `description` → `metadata.description`; `icon` → `frontend.icon`; `category` → `metadata.category`. There is no forward-compatible ignore — validate before deploying. |
| Job `failed`, error names a destructive statement (`DROP`, `RENAME`, `TRUNCATE`, `ALTER COLUMN … TYPE`) | Destructive DDL without `migration.breaking: true`. | Make the migration additive, or set `migration.breaking: true` — which is recorded on the version row and fans the migration out to every install as usual. There is no undo: rollback re-points the image, not the schema. |
| Job `failed`, error is a Docker build/push error string | The image build inside the backend failed. | Read the error verbatim — usually `COPY <src> not found` (path outside the tar root) or a failing `RUN`. |

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

# Via a file, not `--arg`: the bundle is far larger than the argv limit.
base64 < bundle.zip | tr -d '\n' > /tmp/bundle.b64
jq -n --rawfile b /tmp/bundle.b64 --slurpfile m manifest.json '{manifest: $m[0], bundle: $b}' \
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
# Deploy a v2 ManAurum app — POST /api/dev/v2/deploy (async: 202 + poll).
set -euo pipefail

BASE_URL="${MANAURUM_BASE_URL:-https://manaurum.com}"
APP_URL="${APP_URL:-}"   # optional: set to https://<slug>.apps.manaurum.com for the health check

if [ -f .env.manaurum ]; then
  set -a; . ./.env.manaurum; set +a
fi

if [ -z "${MANAURUM_V2_TOKEN:-}" ]; then
  echo "Error: MANAURUM_V2_TOKEN not set. Mint one at https://manaurum.com (Dev Hub → v2 Tokens)."
  echo "Save as MANAURUM_V2_TOKEN=mna_<...> in .env.manaurum"
  exit 1
fi

if [ ! -f manifest.json ]; then
  echo "Error: manifest.json missing. See manaurum-app/SKILL.md."
  exit 1
fi
if [ ! -f Dockerfile ]; then
  echo "Error: Dockerfile missing. v2 apps build images."
  exit 1
fi

echo "Bundling build context…"
# Excluding .venv/__pycache__ is not cosmetic: a locally pip-installed
# project otherwise ships its whole virtualenv (58 MB vs 60 KB measured).
tar cf /tmp/ctx.tar \
  --exclude='.env*' \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='.venv' \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='dist' \
  --exclude='build' \
  --exclude='deploy.sh' \
  --exclude='*.tar' \
  --exclude='*.zip' \
  .

echo "Deploying…"
# Portable single-line base64: GNU accepts `-w0`, BSD/macOS does not.
# Write it to a FILE and read it with --rawfile. Passing it as
# `jq --arg b "$B64"` puts the entire archive on the command line and
# dies with "Argument list too long" on any real project (Windows caps
# argv at 32 KB; a 60 KB tar is already 80 KB of base64).
base64 < /tmp/ctx.tar | tr -d '\n' > /tmp/ctx.b64
RESP=$(jq -n --rawfile b /tmp/ctx.b64 --slurpfile m manifest.json \
  '{manifest_json: $m[0], archive_b64: $b}' \
  | curl -sS -X POST "$BASE_URL/api/dev/v2/deploy" \
      -H "Authorization: Bearer $MANAURUM_V2_TOKEN" \
      -H "Content-Type: application/json" \
      -d @-)
rm -f /tmp/ctx.tar /tmp/ctx.b64

# The POST is 202 + {"deploy_job_id": ..., "status": "pending"} — ALWAYS.
# Never treat its "status" as the outcome; poll the job instead.
JOB_ID=$(printf '%s' "$RESP" | jq -r '.deploy_job_id // empty' 2>/dev/null || true)
if [ -z "$JOB_ID" ]; then
  echo "Deploy not accepted:"
  printf '%s\n' "$RESP" | jq . 2>/dev/null || printf '%s\n' "$RESP"
  exit 1
fi

echo "Job: $JOB_ID — polling…"
STATUS="pending"
JOB=""
for _ in $(seq 1 120); do          # 120 × 3s = 6 min; a build may take up to 300s
  JOB=$(curl -sS "$BASE_URL/api/dev/v2/deploy/$JOB_ID" \
          -H "Authorization: Bearer $MANAURUM_V2_TOKEN")
  STATUS=$(printf '%s' "$JOB" | jq -r '.status // "pending"' 2>/dev/null || echo pending)
  case "$STATUS" in
    succeeded|failed) break ;;
  esac
  sleep 3
done

if [ "$STATUS" = "failed" ]; then
  echo "✗ Deploy failed:"
  printf '%s\n' "$JOB" | jq -r '.error // "(no error recorded)"'
  exit 1
fi
if [ "$STATUS" != "succeeded" ]; then
  echo "✗ Timed out waiting for job $JOB_ID (last status: $STATUS)"
  exit 1
fi

URL=$(printf '%s' "$JOB" | jq -r '.result.url // empty')
echo "✓ Build accepted — $URL"

# "succeeded" only means Docker accepted the spec. There is NO readiness
# probe on the platform side, so verify the app actually serves.
[ -n "$APP_URL" ] || APP_URL="$URL"
if [ -n "$APP_URL" ]; then
  for _ in $(seq 1 15); do
    if curl -fsS "$APP_URL/healthz" >/dev/null 2>&1; then
      echo "✓ Live at $APP_URL"
      exit 0
    fi
    sleep 2
  done
  echo "⚠ Deploy succeeded but $APP_URL/healthz is not answering."
  echo "  Check: container listening on 0.0.0.0:80 (or your runtime.port)?"
  exit 1
fi
```

Make executable: `chmod +x deploy.sh`.

Requires `jq` and `curl`. The `base64 | tr -d` form above is portable; `base64 -w0` is GNU-only and errors on stock macOS.

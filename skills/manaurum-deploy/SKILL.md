---
name: manaurum-deploy
description: Deploy a ManAurum OS app on Platform v2 (containerized — `manaurum app deploy` or `POST /api/dev/v2/deploy` with an `mna_*` token). Use whenever the user wants to deploy, publish, host, upload, or release their ManAurum/SeregaOS app. Covers token issuance, build context preparation, deploy contract, rejection codes, rollback, and the post-deploy install/open flow.
---

# Deploy ManAurum App

> ## ⚡ One deploy path: Platform v2
>
> Every app deploys with an **`mna_*`** credential through `manaurum app deploy` or `POST /api/dev/v2/deploy`. The platform builds a Docker image from a tarball, pushes it to a private registry, runs it as a Swarm service and exposes it at `https://<slug>.apps.manaurum.com`.
>
> If the user has no `mna_*`, ask them to mint one from Dev Hub → Credentials → Create token. An **`mnu_*`** token is **not** a deploy token: it is a tenant token for MCP clients and Drive upload (Settings → Team → Keys & tokens), and the deploy endpoint rejects it.

---

## v2 deploy

### Prereqs

- **An `mna_*` token.** Mint it in Dev Hub → Credentials → Create token. It is shown ONCE;
  save it immediately. Two kinds, chosen in that dialog:
  - **All my apps** (`scope_kind: "owner"`, the dialog's default; 90 days unless you pick 180 or 365): every app
    you own in this tenant, including ones you create later. **A brand-new app can only be
    deployed with this kind** — an app-list token cannot name an app that does not exist
    yet (`403 apps_not_owned` at issuance).
  - **Chosen apps** (`scope_kind: "apps"`; 365 days by default): only the apps you list, and only
    while you still own them and are a member of the tenant. There is no `*`
    (`400 apps_wildcard_not_allowed`).

  If Credentials is missing or creating a token answers a bare `404`, Platform v2 is not
  switched on for your workspace (or, in the shared public tenant, you have no developer
  entitlement yet): ask the platform team. At most 20 active tokens per person per tenant (`409 max_active_tokens_reached`). There
  is no rotate: create a new token, then revoke the old one. The container never uses
  this token; it gets its own `MANAURUM_RUNTIME_TOKEN`, which cannot deploy
  (`403 runtime_credential_not_allowed`).
- **Where the token lives.** `manaurum auth login` stores it in `~/.manaurum/config.json`;
  the CLI reads nothing else (no env var, no `.env.manaurum`). For `curl` and `deploy.sh`,
  keep it in `.env.manaurum` as `MANAURUM_V2_TOKEN=...` in the directory **above** the app
  (beside it, never inside it: the packager does not exclude `.env*`).
- **The token decides the tenant, not the manifest.** An `mna_*` is bound to one tenant: the
  tenant of the workspace that was active in Dev Hub when it was minted. Every deploy with
  it lands in that tenant, and nothing in `manifest.json` chooses it. The deploy response
  does not name the tenant and no endpoint answers "which tenant is this token" (MAN-3199),
  so check before the first deploy. The Create dialog names the tenant it is about to bind
  to (and refuses with `409 tenant_changed` if another tab switched it meanwhile). Dev Hub →
  Credentials lists your tokens for the current tenant only, each with its `key_prefix`: if
  your token's prefix is not in the list, it belongs to another tenant. zb-analytics was
  deployed into a personal tenant this way.
- **The first person to deploy a slug owns the app, alone.** There is no way to add a
  co-owner; another developer's deploy of the same slug in your tenant is
  `403 app_id_out_of_scope`, and in another tenant `409 slug_owned_by_another_tenant`.
- A project directory containing `manifest.json` + `Dockerfile` + your source files. See
  `manaurum-app/references/v2-platform.md` § 1 for the full manifest reference.

### Pre-flight: two linters, then a small window with a lot of data

**Run both linters before you pack anything.** They take a second between them
and each one catches something that otherwise deploys green and fails later as
something that does not look like its cause:

```bash
python <plugin>/templates/check_app.py my-app            # manifest vs code
python <plugin>/templates/check_ui.py my-app/src/static  # the UI contract
```

`check_app.py` is `manaurum-app/SKILL.md` → **Step 3.6**: an `/api/*` route the
manifest never declared (`404 route_not_declared`, silent logs), a port that
disagrees with the `CMD` (a deploy that fails its readiness probe), an `/agent/*` handler with no
user-context check, a capability you call but did not declare, and a `.env`
inside the directory you are about to upload — that last one gets baked into an
image layer and retained per version, and there is no way to un-leak it.

### The window: a small one with a lot of data

One check, every deploy, because it is the one the developer never runs and the
user always does. **Open the app at the smallest window you support, with enough
data to overflow it, and watch the browser console.**

An OS window cannot scroll an iframe — your app is `height: 100%` of the window's
content area, so the shell's scrollbar can never appear and your document has to
own the scrolling. A root with `overflow: hidden` and a fixed `height`, with no
scroller under it, ships with the bottom of every long view cut off. It looks
perfect in a full-screen tab with three rows.

The console is the observable, not your eyes: since `manaurum-v2.mjs` 2.3.0
the SDK measures this at run time and logs

```
content is clipped and nothing scrolls: <div.your-root> is 600px tall and hides 1106px below it.
```

naming the element. Nothing in the console and a reachable page bottom is the
pass. The rule and the fix: `manaurum-app/references/design.md` → "Window
rules". Note the guard arms on the `manaurum:init` handshake, so a standalone
dev-server tab never reports — check inside the desktop, or call
`app.checkLayout()` yourself.

And if you have not looked at the app at all yet, do that first: two headless
screenshots, light and dark, through `<plugin>/templates/preview.py`. The
procedure is `manaurum-app/SKILL.md` → **Step 3.5**. Deploying an interface
nobody has seen is how a technically flawless app gets rejected on sight.

### Quickstart

```bash
cd my-app

# Say out loud what you are about to deploy, and get it from the manifest
# rather than from memory. /tmp is shared: two sessions building two apps on
# one machine collide on any fixed filename, and the loser's deploy reports
# `activated` for someone else's app while its own never went out (MAN-2456).
SLUG=$(jq -r .app_id manifest.json)
VERSION=$(jq -r .version manifest.json)
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT   # per-run, cleaned on every exit
echo "deploying $SLUG $VERSION"        # if that is not your app, stop here

tar cf "$WORK/ctx.tar" \
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
base64 < "$WORK/ctx.tar" | tr -d '\n' > "$WORK/ctx.b64"
jq -n --rawfile b "$WORK/ctx.b64" --slurpfile m manifest.json \
  '{manifest_json: $m[0], archive_b64: $b}' > "$WORK/deploy.json"

curl -sS -X POST https://manaurum.com/api/dev/v2/deploy \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN" \
  -H "Content-Type: application/json" \
  -d @"$WORK/deploy.json" | jq .

rm -rf "$WORK"
```

**Never write the build context, the base64 or the request body to a fixed
path** — not `/tmp/ctx.tar`, and not a shared helper script on a server. It
happened on 2026-09-08: a second session overwrote the operator's deploy script
and the next run shipped *their* archive, phases streaming healthily for an app
nobody meant to touch, while the app the operator was deploying stayed on its
old version. A run that reports success for the wrong app is worse than one that
fails, so check the echoed slug before you trust the result.

The `.venv` / `__pycache__` excludes are not cosmetic: without them a Python
project that has been `pip install`ed locally ships its whole virtualenv —
measured at **58 MB instead of 60 KB** on a 20-file app.

### The deploy is asynchronous — always

When the POST is accepted it returns HTTP **202** and *always* this body. It never returns
`succeeded`:

```json
{ "deploy_job_id": "<uuid>", "status": "pending" }
```

Build, registry push, migrations, Swarm, Traefik and the readiness probe all run on a
background task. **Never read success off the POST response** — a script that does reports
failure on 100% of successful deploys.

Poll until the job reaches a terminal status (the CLI polls every 2 s for up to 10 minutes):

```bash
curl -sS https://manaurum.com/api/dev/v2/deploy/<deploy_job_id> \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN" | jq .
```

`status` stays `pending` until the job settles, then becomes exactly one of **`succeeded`**
or **`failed`**:

```json
{
  "job_id":     "<uuid>",
  "status":     "succeeded",
  "created_at": "2026-10-02T10:04:11+00:00",
  "result": {
    "app_id":     "<uuid>",
    "version_id": "<uuid>",
    "version":    "1.0.1",
    "image_tag":  "manaurum-registry:5000/v2-app-my-app-1a2b3c4d:1.0.1",
    "image_digest": "sha256:…",
    "manifest_fingerprint": "…", "migration_fingerprint": "…",
    "per_tenant_status": { "<tenant uuid>": "applied" },
    "ui_warnings": [],
    "url":        "https://my-app.apps.manaurum.com"
  },
  "error":  null,
  "events": [ … ]
}
```

- **On `failed`**, `error` carries the reason and `result` is either `{}` or
  `{ "log_kind": "build" | "container", "log_tail": [ … ] }`: the build output or the new
  container's last lines, secrets redacted. Read both.
- **`ui_warnings`** are the advisory UI lint (`templates/check_ui.py` finds the same things
  first). They never block a deploy.
- **`per_tenant_status`** is the migration outcome per installed tenant: `applied`,
  `skipped` (nothing new to run) or `failed`.
- A `deploy_job_id` read by any other identity (another tenant, a sibling user, a credential
  narrowed to a different app) returns `404 job_not_found` — never 403.

### Follow progress live

```bash
curl -sSN https://manaurum.com/api/dev/v2/deploy/<deploy_job_id>/stream \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN"
```

`application/x-ndjson` — one JSON object per line in `seq` order, an empty heartbeat line
every 30 s, terminated by a `{"terminal": true, "status": …, "error": …, "result": …}` line
once the job settles. On disconnect, re-open and skip lines whose `seq` you have already
seen. The phases, in order:

`manifest_validated` → `migrations_extracted` → `image_pushing` → (`migration_failed` per
failing tenant) → `image_pushed` → (`migration_gate_blocked`) → `swarm_applying` →
`swarm_applied` → `traefik_written` → `readiness_probing` → `readiness_ok` |
`readiness_failed` → `agent_capabilities_synced` → `activated`

Migrations run **after the image is pushed and before the new container replaces the old
one**: a migration failure leaves the running version untouched.

### What fails synchronously, from the POST

The POST validates the credential, the manifest, the slug, ownership and the archive before
it starts anything. In the order it checks:

| HTTP | `detail` | Meaning | Fix |
|---|---|---|---|
| 401 | `invalid_credential` | No `Authorization: Bearer`, not an `mna_*` (an `mnu_*` lands here), or revoked/expired. | Mint a fresh one in Dev Hub → Credentials. |
| 403 | `runtime_credential_not_allowed` | You used the container's `MANAURUM_RUNTIME_TOKEN`. | Use your own `mna_*`. |
| 422 | `{"error":"slug_reserved","hint":…}` | `app_id` starts with `draft-`: those addresses are Aurum Studio's private drafts. Merged in Core on 2026-10-04 (sergeysuaib-ui/manaurum#2368). | Rename the app. CLI 0.3.1 and `check_app.py` refuse it already. |
| 422 | `{"error":"manifest_validation_failed","errors":[{path, message}]}` | The manifest fails the schema, names a reserved slug, declares a write-named agent capability `is_write: false`, or gives a `byo` app `permissions`. | Fix each listed path. `manaurum app validate` finds the same errors locally. |
| 422 | `{"error":"app_id_invalid","hint":…}` | `app_id` is not 3–40 characters of lowercase letters, digits and hyphens, starting with a letter and ending with a letter or digit, or it is shaped like a UUID. | Rename the app. CLI 0.3.1 refuses it locally. |
| 403 | `{"error":"app_id_out_of_scope","token_scope":…,"hint":…}` | The token does not reach this app: an app-list token that does not name it, an app someone else in this tenant owns, or an owner you no longer are. | Read the `hint`. For a new app, use an "all my apps" token. |
| 413 | `archive_too_large` | The base64 is over 88 MiB of characters. | Exclude what the image does not need. |
| 422 | `invalid_archive_b64` | Not base64. | Encode with `base64 < file \| tr -d '\n'` — one unwrapped line. (`base64 -w0` is GNU-only.) |
| 409 | `slug_owned_by_another_tenant` | Another tenant has this slug, held it within the last 30 days, or is deploying it right now. | Rename the app. |
| 409 | `version_already_published` | This `version` already exists for the app, including one whose deploy failed. | Bump `version`. |
| 409 | `slug_reserved` | Someone else in this tenant deleted this slug less than 30 days ago, or is deploying it right now. | Wait, or rename. |

A body without `manifest_json` or `archive_b64` is FastAPI's own `422` before any of these.
`403 app_id_out_of_scope` can also come after the `409`s, when another developer claimed the
slug a moment earlier. Everything else is a **job failure**: `status: "failed"`, reason in `error`.

### What `succeeded` means

`succeeded` means the new container **answered**. Before activating a version the platform:

1. **Runs the migration gate (MAN-2510).** If a migration failed for **any** installed
   tenant, the job fails with `not activated: the migration failed for N tenant(s) …`: no
   container is replaced and the running version keeps serving. Tenants where it applied
   keep the change, so fix forward with a new migration file. The reason is in `error`
   (`result` is `{}`).
2. **Probes the new container (readiness probe, MAN-1369).** It waits until Swarm runs the
   new image, then calls `http://<service>:<runtime.port or 80><runtime.health_path or
   /healthz>` until it answers, for up to 90 s. With `health_path` **declared**, only a
   2xx–4xx answer passes and a 5xx fails; with it **undeclared**, any HTTP answer passes and
   only "nothing is listening" fails. On failure the service is rolled back to the previous
   version (on a first deploy there is none, so the app is simply not serving), the job
   fails, and `result.log_tail` holds the container's last lines. Migrations have already
   run by then: the new schema stays applied under the old code, and the version label is
   used up.

So a wrong port, a process bound to `127.0.0.1`, or a crash on boot fails the deploy instead
of shipping a `502`. **Declare `runtime.health_path`** and make it check what the app needs
to serve (but not Postgres, which can come up after you — `manaurum-app/SKILL.md`).

`succeeded` still does not cover two things: the window (the app has no desktop window until
`frontend.entry_point` is declared and the page answers `manaurum:ready`), and every
`/api/*` route (the probe calls one path).

### Versions are immutable

Every deploy needs a new `version`. A version label is used up by the first deploy whose
image **push completes**, even if that deploy then fails (the migration gate, the readiness
probe, an ownership check after the build): the next deploy with the same label is
`409 version_already_published`. Failures before the push completes (manifest, archive,
migration validation, a Docker build error, usually a failed push) do not use it up. Images are named `v2-app-<slug>-<first 8 hex of the tenant id>:<version>` and
run pinned by digest.

```bash
jq '.version = "1.0.1"' manifest.json > manifest.json.new && mv manifest.json.new manifest.json
# rerun the deploy — the platform updates the swarm service in place
```

The URL stays the same. Existing connections drain; new requests hit the new version.

### Migrations across redeploys

Schema changes ship as plain `.sql` files directly under a top-level `migrations/` directory
of your build context. Each file runs **once per (app, tenant)** in lexical filename order;
applied files are recorded so redeploys skip them.

**Never edit a migration that has already been applied.** Every applied file is pinned by
sha256 per `(app, tenant, filename)`. Re-uploading `0001_init.sql` with different bytes
does not re-run it: that tenant's migration fails, and the migration gate stops the
version from going live. To change schema, **add `0002_<what>.sql`**. Same rule for a file
you only reformatted: different bytes, same failure.

Limits the validator applies before anything is built:

- **64 KiB for all migration files together**, measured on their concatenation. Splitting
  files does not help (the platform's own error suggests it; ignore that); a long-lived app
  eventually needs fewer, smaller migrations.
- **`.sql` files only, in UTF-8.** Any other file directly under `migrations/` fails the
  deploy (`non-SQL file in migrations/`; the check is case-sensitive, so `0001.SQL` is not
  SQL), and so does a `.sql` file that is not UTF-8 (`not valid UTF-8`).
- **Additive by default.** `migration.breaking: true` unlocks *destructive* statements
  (`DROP …`, `RENAME`, `TRUNCATE`, `ALTER COLUMN … TYPE`, `REVOKE`); it never unlocks
  *forbidden* ones (`DO $$ … $$`, `COPY`, `CREATE EXTENSION`, `BEGIN`/`COMMIT`, any `SET`,
  role/database DDL, anything unrecognised). **The flag applies to every file in
  `migrations/`, old ones included,** so once a destructive file ships the flag has to stay
  `true` for as long as that file does, and it switches the destructive check off for every
  later migration too. Full classification: `manaurum-app/references/v2-platform.md` §7.
And when each tenant runs it, after the image is pushed: **a 30 s statement timeout and a
5 s lock timeout.** A long backfill or an index on a big, busy table fails there; split the
work.

### Rollback

```bash
curl -sS -X POST https://manaurum.com/api/dev/v2/apps/<slug>/rollback \
  -H "Authorization: Bearer $MANAURUM_V2_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"version_label": "1.0.0"}'
```

`version_label` is required — name the already-published version you want live. Rollback
re-points Swarm, Traefik and `v2_apps.current_version_id` at that version's image and its
stored manifest. Same async shape as deploy — **202 + `{"deploy_job_id", "status":
"pending"}`** — so poll `GET /api/dev/v2/deploy/{job_id}`. A rollback while any deploy or
rollback job for the app is pending is `409 deploy_in_progress` (a deploy is not refused
that way: do not start two). In the job: `version_not_found`, `already_current`,
`image_unavailable`, `slug_released`, `app_not_found`.

What rollback does **not** do:

- **No schema revert.** Applied migrations stay applied; the older code runs against the
  newer schema.
- **No readiness probe and no migration gate.** It does not check that the target version
  ever served, and it will activate a version whose own deploy failed. Check `/healthz`
  yourself afterwards.
- **No Assistant re-sync.** The OS Assistant keeps the newer version's `agent_capabilities`
  until the next deploy; tools the older code lacks answer 404.

### List versions / inspect / logs

```bash
# describe
curl -sS https://manaurum.com/api/dev/v2/apps/<slug> -H "Authorization: Bearer $MANAURUM_V2_TOKEN"

# version history
curl -sS https://manaurum.com/api/dev/v2/apps/<slug>/versions -H "Authorization: Bearer $MANAURUM_V2_TOKEN"

# the running container's log: the last N lines (default 200, max 1000), with timestamps
curl -sS "https://manaurum.com/api/dev/v2/apps/<slug>/logs?tail=500" -H "Authorization: Bearer $MANAURUM_V2_TOKEN"
```

The logs answer `{"lines": [ … ]}` straight from Docker and are **not redacted**: whatever
your app prints, including a token, is readable by anyone with a token for the app.
`404 service_not_found` means the app has no Swarm service at all; a crash-looping container still returns its lines. From the CLI: `manaurum app logs
--app-id <slug> --tail 500`.

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
> `venv`, `.git`, the `*_cache` dirs, `node_modules`, `dist` and `build` — it does **not** exclude
> `.env`, `.env.local`, `.env.manaurum` or any other dotfile. A secret that lands in the tar is
> downloadable by anyone who can call `fetch-source` for your tenant, and is permanently in the
> git history even after the tarball is pruned. **Keep secrets out of the app directory
> entirely** (put `.env.manaurum` in the parent dir or your shell profile). A `.dockerignore`
> is no defence on a platform deploy: the classic builder Core uses (`POST /build`,
> `version=1`) does not apply it, and the tar is stored as uploaded. Rotating the credential
> is the only remedy after the fact.

### Failures you'll actually hit (job `failed`, or after a green deploy)

| Symptom | Cause | Fix |
|---|---|---|
| `404 route_not_declared` from one of your API paths | `runtime.api_routes` is **default-deny**. A path that matches no rule is rejected by the gateway and never reaches your container. | Declare it. `/api/tasks/*` does **not** match the bare `/api/tasks` — declare both. There is no `method` field; one rule covers every verb. |
| Job `failed` at `readiness_failed`, `rolled back to the previous version` (or `the app is not serving` on a first deploy) | Nothing answered on `<service>:<runtime.port or 80><health_path>`: the process binds another port or `127.0.0.1`, crashed on boot, or `health_path` answered 5xx. `EXPOSE` in your Dockerfile is never read. | Read `result.log_tail`. Bind `0.0.0.0` on the port `runtime.port` declares (80 if absent): `CMD ["uvicorn","main:app","--host","0.0.0.0","--port","80"]`. |
| Job `failed`, `not activated: the migration failed for N tenant(s)` | A migration failed in at least one tenant (an edited applied file, a statement that failed, a timeout). | The message names the tenant, file and reason. Add a new migration that fixes it forward and bump the version. |
| Job `failed`, `migration validation failed (…)` | A forbidden or (without `migration.breaking`) destructive statement, or more than 64 KiB of migrations. | Reword it as additive DDL; `manaurum app validate-migration migrations/` shows the same verdict locally. |
| Job `failed`, error contains `DO $$ … $$ — arbitrary PL/pgSQL body is not analysable` | Anonymous `DO` blocks are **forbidden**: the body cannot be AST-checked. `migration.breaking: true` does not override it. | Expand the block into plain statements (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE … ADD COLUMN IF NOT EXISTS`, …). A first-party app shipped this exact bug (MAN-1327). |
| Job `failed`, `non-SQL file in migrations/` / `not valid UTF-8` | A non-`.sql` **regular file directly under** `migrations/` — a `README.md`, a `.gitkeep`, or `0001.SQL` (the check is case-sensitive). | Move it elsewhere in the bundle. Subdirectories under `migrations/` are ignored. |
| Job `failed`, `version_already_published: … already exists in the registry` | The image tag exists with no version record: a deleted app redeployed with an old label, or a push that completed but was never recorded. (A recorded version is refused by the POST.) | Bump `version`. |
| Job `failed`, `docker build failed: …` (with `result.log_tail`) | The image build failed. | Read the tail — usually `COPY <src> not found` (path outside the tar root) or a failing `RUN`. |
| Job `failed`, `deploy archive rejected (…)` | The archive is not gzip or plain tar, expands past 64 MiB, or holds more than 20,000 entries. | Use `tar cf` (or `czf`); exclude dependencies the Dockerfile installs anyway. |
| Job `failed`, `build context failed validation (N finding(s))`, e.g. `file-too-large` | Only where the platform runs its build-context scan in `enforce` mode (`v2_build_scan_mode`; off by default, and `audit` only logs): a file over 32 MB, a base image not on the allow-list, or another finding the scan names. | Fix what the finding names; keep large data out of the image. |

### Who gets the app after a deploy

A deploy installs the app **only into your own tenant** (the token's):

- **A team tenant** (a company or pilot tenant the platform onboarded) gets it on **every
  workspace's** desktop.
- **The shared public tenant** (where self-signup accounts live) gets it only on each
  owner's own desktop.

Other tenants get it only through the App Store, and only if `visibility.mode` allows:
`private` (default, home tenant only), `public` (any tenant), or `allow_list` with a
`tenants` array. A tenant admin installs it there.

**Do not promise an app to another tenant yet.** Today the gateway serves `auth: "user"`
routes only to users of the tenant that deployed the app: a user of a tenant that installed
it from the App Store gets `404 app_not_found` on every one of them, and the container runs
only for the home tenant. Static pages still load; nothing behind a login does.

### Deleting an app

Uninstalling (a tenant admin in App Store, or a person removing it from a workspace) only
hides the app. All data stays.

**Deleting** is `DELETE /api/developer/apps/<slug>`, from Dev Hub with your signed-in
session (an `mna_*` token is not accepted). It stops the container and removes the
versions, installs, `os.kv` data, `os.secrets`, the record of applied migrations, deploy
jobs, runtime tokens and the retained source archives (`fetch-source` stops working; the
git history stays). It **keeps** the app's Postgres schema, its stored files and its
images. The slug is then held for its owners for 30 days.

**Redeploying a deleted slug is a trap.** The new app starts with no record of applied
migrations but finds the old schema, so every migration runs again against tables that
exist: a plain `CREATE TABLE` fails and the migration gate blocks the deploy; with
`IF NOT EXISTS` everywhere the old data quietly comes back. And every old `version` label is
still used up. Before you delete, decide whether the data should survive; if you redeploy,
make every migration idempotent and continue the version numbering.

---

## `deploy.sh` template (v2)

When scaffolding a new project, drop this in:

```bash
#!/bin/bash
# Deploy a v2 ManAurum app — POST /api/dev/v2/deploy (async: 202 + poll).
set -euo pipefail

BASE_URL="${MANAURUM_BASE_URL:-https://manaurum.com}"
APP_URL="${APP_URL:-}"   # optional: set to https://<slug>.apps.manaurum.com for the health check

# The token file lives one level up, beside the app directory. Inside it,
# `manaurum app deploy` would upload it with the source: the packager does not
# exclude .env*. This script excludes it from its own tar, but refuses anyway,
# so the layout that is safe for one tool is the only layout.
if [ -f .env.manaurum ]; then
  echo "Error: .env.manaurum is inside the app directory. Move it one level up: mv .env.manaurum .."
  exit 1
fi
if [ -f ../.env.manaurum ]; then
  set -a; . ../.env.manaurum; set +a
fi

if [ -z "${MANAURUM_V2_TOKEN:-}" ]; then
  echo "Error: MANAURUM_V2_TOKEN not set. Mint one at https://app.manaurum.com (Dev Hub → Credentials)."
  echo "Save as MANAURUM_V2_TOKEN=mna_<...> in ../.env.manaurum (beside the app directory)"
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
# A per-run directory, cleaned on every exit path. NOT /tmp/ctx.tar: /tmp is
# shared, and on 2026-09-08 two sessions deploying at the same moment crossed
# build contexts — one app was published over another (MAN-2456).
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
# Excluding .venv/__pycache__ is not cosmetic: a locally pip-installed
# project otherwise ships its whole virtualenv (58 MB vs 60 KB measured).
tar cf "$WORK/ctx.tar" \
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
base64 < "$WORK/ctx.tar" | tr -d '\n' > "$WORK/ctx.b64"
RESP=$(jq -n --rawfile b "$WORK/ctx.b64" --slurpfile m manifest.json \
  '{manifest_json: $m[0], archive_b64: $b}' \
  | curl -sS -X POST "$BASE_URL/api/dev/v2/deploy" \
      -H "Authorization: Bearer $MANAURUM_V2_TOKEN" \
      -H "Content-Type: application/json" \
      -d @-)
rm -f "$WORK/ctx.tar" "$WORK/ctx.b64"

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

# "succeeded" means the platform's readiness probe got an answer from the new
# container. Check the public URL too: it goes through the gateway and TLS.
[ -n "$APP_URL" ] || APP_URL="$URL"
if [ -n "$APP_URL" ]; then
  for _ in $(seq 1 15); do
    if curl -fsS "$APP_URL/healthz" >/dev/null 2>&1; then
      echo "✓ Live at $APP_URL"
      exit 0
    fi
    sleep 2
  done
  echo "⚠ Deploy succeeded but $APP_URL/healthz is not answering through the gateway."
  echo "  The container answered the platform's probe; check TLS, DNS and that /healthz exists."
  exit 1
fi
```

Make executable: `chmod +x deploy.sh`.

Requires `jq` and `curl`. The `base64 | tr -d` form above is portable; `base64 -w0` is GNU-only and errors on stock macOS.

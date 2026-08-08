# Publishing ManAurum OS Apps

Two publish paths exist and they fail in different ways. Pick the one that matches your runtime.

- **Platform v2** (the default) — § *Publishing on Platform v2*, below.
- **v1 tenant catalog** (legacy iframe bundles) — § *Legacy: v1 tenant catalog*, at the bottom.

---

## Publishing on Platform v2

### Publish vs deploy — two endpoints, two failure shapes

| Endpoint | Auth | Response | Where a bad manifest surfaces |
|---|---|---|---|
| `POST /api/dev/v2/dev-apps/<dev_app_id>/publish` | session cookie (dev mode — **no UI client since 2026-08-07**) | `202 {deploy_job_id, status:"pending"}` | **synchronously — `422`**, before any job exists |
| `POST /api/dev/v2/deploy` | `mna_*` bearer (CLI) | `202 {deploy_job_id, status:"pending"}` | **asynchronously** — the job settles as `status: "failed"` |

Both return `202` and both hand back a `deploy_job_id` to poll. The difference is *when* the manifest
is checked:

- **Dev-mode publish** (the App Builder editor drove this until it was removed on 2026-08-07; the route is still mounted but no UI calls it — use the CLI path) runs the v2 schema validation inside the request. A schema failure is
  `422 {"error": "manifest_validation_failed", "errors": [{"path": "...", "message": "..."}, …]}` —
  one entry per failing assertion, so the editor renders them all at once. Nothing is built.
- **CLI deploy** validates only the request envelope in-band: a non-base64 `archive_b64` is
  `422 invalid_archive_b64`. The manifest itself is validated inside the background job. Do **not**
  expect a `422` from `/deploy` for a bad manifest — poll and read `status` + `error`.

Poll surfaces:

- CLI / `mna_*` token → `GET /api/dev/v2/deploy/<job_id>` (and `/stream` for progress events).
- Dev mode / session cookie → `GET /api/dev/v2/dev-apps/<dev_app_id>/publish-status/<job_id>`.
  Same job store, stricter ownership — you must own both the dev app and the job. Everyone else
  gets `404 job_not_found`.

Two more dev-mode-only preconditions:

- The tenant needs `experiment.platform_v2_hosted_runtime`, otherwise the publish is
  `501 hosted_runtime_not_ready`.
- The manifest that gets validated is **not byte-for-byte what you typed**. Publish backfills the
  v2-required defaults and auto-declares the capabilities your code actually calls (so the gateway
  doesn't default-deny them at runtime). Validation errors can therefore cite paths you never wrote.

A `succeeded` job means Docker accepted the spec, not that the app is serving. There is no readiness
probe in the hosted path — hit `/healthz` yourself afterwards.

### What the manifest validator rejects

`manifest_v2.schema.json` sets `additionalProperties: false` at the root, so an unknown key is a hard
rejection, not a warning. The 23 root keys:

`agent_capabilities` · `app_id` · `consumes` · `data` · `frontend` · `manaurum_sdk_version` ·
`manifest_version` · `metadata` · `migrate_command` · `migration` · `name` · `offline` ·
`optional_capabilities` · `permissions` · `platforms` · `provides` · `requires_capabilities` ·
`runtime` · `schedules` · `tenant_config` · `version` · `visibility` · `webhooks`

The three that catch people out, because they look like they must be root fields:

| You wrote | Result | Where it actually goes |
|---|---|---|
| `"description"` at root | rejected | `metadata.description` |
| `"icon"` at root | rejected | `frontend.icon` |
| `"category"` at root | rejected | `metadata.category` |

`permissions` at the root **is** valid. It is the browser-feature delegation list the shell passes to
the app iframe via `allow=` (Permissions-Policy); the enum is `["microphone"]` today. It is not a
capability grant — `requires_capabilities` is a separate axis.

### Icons — three separate rules, don't mix them

1. **`frontend.icon` in the manifest** is a plain `{"type": "string"}` with no schema constraint. An
   emoji, an absolute URL, or an absolute `/api/catalog/media/...` path all validate. What breaks is
   a **relative** path (`icons/app.svg`) — it passes validation and then paints as literal text in
   the tile.
2. **The Dev Hub listing edit** (`PUT /api/developer/apps/<slug>`) writes `body.icon` into
   `manifest.frontend.icon` but applies its own check first: anything longer than **8 characters** is
   `400 "Icon must be a short emoji glyph"`, unless it starts with `/api/catalog/media/`. So an
   `https://...` icon URL the manifest schema accepts is rejected by this route. That 8-char rule is
   a listing-metadata constraint only — it does not apply to the manifest you deploy.
3. **Uploads** go through `POST /api/developer/apps/<slug>/media` (image content type, ≤ 5 MB, else
   `400` / `413`). For a v2 app the upload writes `frontend.icon` for you when the current icon is
   still the emoji/empty default; later uploads land in `metadata.screenshots`. You do not need a
   follow-up `PUT`.

The same listing route also enforces `short_description` ≤ 160 chars (stored as
`metadata.description`) and a fixed category set — `productivity`, `utility`, `lifestyle`,
`entertainment`, `dev_tools`, `other` (stored as `metadata.category`). Anything else is `400`.

Listing edits are written straight into the stored manifest, so **the next CLI deploy overwrites
them** with your repo's `manifest.json`. Update the repo manifest too, or the edit is temporary.

---

## Legacy: v1 tenant catalog

Everything below describes the v1 iframe-bundle flow (`mnu_*` deploy token, `manifest_v1.schema.json`).
Ignore it unless you are maintaining a pre-v2 app.

### Release model

In v1 the release model is **per-tenant catalog**. There is no global App Store, no Private/Unlisted/Public review track. The flow is:

1. **Deploy** — `POST /api/dev/apps/deploy` with `mnu_*` token, manifest, bundle. Creates a row in your tenant's `applications` table and a versioned `application_versions` row. The new version becomes the `current_version_id` immediately.
2. **Install** — a workspace owner inside the same tenant installs the app via AppStore. Creates a `workspace_app_installs` row.
3. **Open** — workspace members open the app at `/t/<tenant_slug>/apps/<app_slug>`.

### App + version states

| State | Meaning |
|---|---|
| **active** (application) | App is in the tenant catalog and installable. Default after first deploy. |
| **archived** (application) | App removed from catalog. Existing workspace installs continue to work; no new installs. |
| **published** (version) | Version is the `current_version_id` for the app. Users get it on next iframe load. |
| **archived** (version) | Older version, no longer current; bundle still readable for audit. |

There is no manual "publish" step in v1 — the deploy IS the publish. To roll back, deploy a new version with a fixed bundle (semver bump). True rollback (re-promoting an older version) is not exposed via the Deploy API in v1.

### Versioning

- Each `POST /api/dev/apps/deploy` requires a unique `version` (semver) for the same `slug`. Re-using a version returns `409 rejected_version_conflict`.
- The platform sets `current_version_id` to the newly-deployed version atomically.
- Existing iframe sessions continue serving the version they loaded with (immutable URL); they pick up the new version on next page load.

### Multi-tenant publishing

A `mnu_*` token is bound to ONE tenant. To publish the same app to multiple tenants:

1. Get a separate token from each tenant's Developer Console.
2. Run the same deploy script with each token (env var rotation).

There is no cross-tenant publish in v1. Each tenant has its own catalog and its own version history for the same app.

### Workspace install

End users do NOT see the app until a workspace owner installs it:

1. Workspace owner opens AppStore inside their workspace.
2. Locates the app in the tenant catalog.
3. Clicks "Install" → `workspace_app_installs` row created.
4. App appears in the dock / launcher for all members of that workspace.

To remove: workspace owner uninstalls from AppStore. Existing in-browser sessions stay live until the user closes them.

### URL structure

- **Catalog open URL:** `/t/<tenant_slug>/apps/<app_slug>` — auth-guarded; returns the iframe shell. 404 if user not in this tenant or workspace lacks the install.
- **Bundle file URL:** `/api/hosted/<version_id>/<path>?t=<bundle_token>` — short-lived signed token, issued by the shell. Not meant to be used directly; the shell injects the iframe with the right URL.

### Versioning checklist

Before each deploy:
- [ ] Bump `manifest.json` `version` (semver).
- [ ] `index.html` is at the root of `bundle.zip`.
- [ ] Bundle < 50 MB — over that is `413 rejected_bundle_too_large`; every other scanner rejection is `422`.
- [ ] No credentials / unauthorised SDK imports / disallowed URLs (the deploy scanner will reject otherwise).
- [ ] Manifest validates against the v1 schema (`manifest_v1.schema.json`).

### What's not in v1

- App Store / public marketplace
- Private / Unlisted / Public visibility tiers
- Review / approval workflow
- Cross-tenant publishing
- Manual rollback to previous version (must re-deploy)
- Per-app token scoping at the issuance UI (the model supports `application_id` but the self-serve route mints tenant-wide tokens only in v1)

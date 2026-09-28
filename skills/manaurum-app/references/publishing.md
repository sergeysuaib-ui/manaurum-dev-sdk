# Publishing ManAurum OS Apps

Every app publishes through Platform v2. This page covers the endpoints that put a version live
(they fail in different ways), what the manifest validator rejects, icons, and the store listing.

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

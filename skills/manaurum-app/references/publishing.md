# Publishing ManAurum OS Apps

Every app publishes through Platform v2. This page covers the endpoint that puts a version live,
what the manifest validator rejects, icons, and the store listing.

---

## Publishing on Platform v2

### One endpoint puts a version live

| Endpoint | Auth | Response | Where a bad manifest surfaces |
|---|---|---|---|
| `POST /api/dev/v2/deploy` | `mna_*` bearer (CLI) | `202 {deploy_job_id, status:"pending"}` | **synchronously — `422`**, before any job exists |

It answers a bad manifest with
`422 {"error": "manifest_validation_failed", "errors": [{"path": "...", "message": "..."}, …]}`
(MAN-2597) — one entry per failing assertion — and refuses an invalid slug, a slug you do not own,
a used version or a bad archive before building anything. Migrations and the build are checked in
the job. The full list: `manaurum-deploy/SKILL.md`. Poll `GET /api/dev/v2/deploy/<job_id>` (and
`/stream` for progress events).

Do not use the in-browser App Builder's browser-session publish route under
`/api/dev/v2/dev-apps`: it is retired. Core sergeysuaib-ui/manaurum#2296 deleted it and the dev
runtime behind it (merged 2026-10-04). Aurum Studio publishes
`hosted` apps under the same owner rule as this endpoint.

A `succeeded` deploy means the new container answered the platform's readiness probe on
`runtime.port` and `runtime.health_path`; a failed probe rolls back and fails the job.

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
the app iframe via `allow=` (Permissions-Policy); the enum is `["microphone", "camera"]` today. It is not a
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

# Publishing ManAurum OS Apps (v1.5+ tenant model)

## Release Model

In v1.5 the release model is **per-tenant catalog**. There is no global App Store, no Private/Unlisted/Public review track. The flow is:

1. **Deploy** — `POST /api/dev/apps/deploy` with `mnu_*` token, manifest, bundle. Creates a row in your tenant's `applications` table and a versioned `application_versions` row. The new version becomes the `current_version_id` immediately.
2. **Install** — a workspace owner inside the same tenant installs the app via AppStore. Creates a `workspace_app_installs` row.
3. **Open** — workspace members open the app at `/t/<tenant_slug>/apps/<app_slug>`.

## App + Version States

| State | Meaning |
|---|---|
| **active** (application) | App is in the tenant catalog and installable. Default after first deploy. |
| **archived** (application) | App removed from catalog. Existing workspace installs continue to work; no new installs. |
| **published** (version) | Version is the `current_version_id` for the app. Users get it on next iframe load. |
| **archived** (version) | Older version, no longer current; bundle still readable for audit. |

There is no manual "publish" step in v1 — the deploy IS the publish. To roll back, deploy a new version with a fixed bundle (semver bump). True rollback (re-promoting an older version) is not exposed via the Deploy API in v1.

## Versioning

- Each `POST /api/dev/apps/deploy` requires a unique `version` (semver) for the same `slug`. Re-using a version returns `400 rejected_version_conflict`.
- The platform sets `current_version_id` to the newly-deployed version atomically.
- Existing iframe sessions continue serving the version they loaded with (immutable URL); they pick up the new version on next page load.

## Multi-tenant publishing

A `mnu_*` token is bound to ONE tenant. To publish the same app to multiple tenants:

1. Get a separate token from each tenant's Developer Console.
2. Run the same deploy script with each token (env var rotation).

There is no cross-tenant publish in v1. Each tenant has its own catalog and its own version history for the same app.

## Workspace install

End users do NOT see the app until a workspace owner installs it:

1. Workspace owner opens AppStore inside their workspace.
2. Locates the app in the tenant catalog.
3. Clicks "Install" → `workspace_app_installs` row created.
4. App appears in the dock / launcher for all members of that workspace.

To remove: workspace owner uninstalls from AppStore. Existing in-browser sessions stay live until the user closes them.

## URL structure

- **Catalog open URL:** `/t/<tenant_slug>/apps/<app_slug>` — auth-guarded; returns the iframe shell. 404 if user not in this tenant or workspace lacks the install.
- **Bundle file URL:** `/api/hosted/<version_id>/<path>?t=<bundle_token>` — short-lived signed token, issued by the shell. Not meant to be used directly; the shell injects the iframe with the right URL.

## Versioning checklist

Before each deploy:
- [ ] Bump `manifest.json` `version` (semver).
- [ ] `index.html` is at the root of `bundle.zip`.
- [ ] Bundle < 50 MB.
- [ ] No credentials / unauthorised SDK imports / disallowed URLs (the deploy scanner will reject otherwise).
- [ ] Manifest validates against the v1 schema (`manifest_v1.schema.json`).

## What's not in v1

- App Store / public marketplace
- Private / Unlisted / Public visibility tiers
- Review / approval workflow
- Cross-tenant publishing
- Manual rollback to previous version (must re-deploy)
- Per-app token scoping at the issuance UI (the model supports `application_id` but the self-serve route mints tenant-wide tokens only in v1)

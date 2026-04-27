# Changelog

## 1.5.0 (2026-04-27) — BREAKING: tenant-aware Deploy API

### Changed (BREAKING)

- **`manaurum-deploy` rewritten for the new Deploy API.** The legacy `/api/developer/apps/.../hosting/paste` flow (paste-HTML, `mdev_*` tokens) is no longer documented. Tenant developers now go through:
  - `POST /api/developer/tenant-tokens` to mint a tenant-scoped `mnu_*` token.
  - `POST /api/dev/apps/deploy` with `{manifest, bundle (base64 zip)}`.
- **`MANAURUM_TOKEN` env var renamed to `MANAURUM_TENANT_TOKEN`** in templates and deploy script. Old name is gone — update local `.env.manaurum` files.
- **Manifest schema replaced with v1 (frozen).** The legacy shape (`runtime.entrypoint` URL, `runtime.sandbox`, `description`, `compatibility.min_shell_version`, permissions like `theme.read` / `storage.*` / `files.*` / `window.manage`) is no longer accepted by the deploy validator. The new schema requires `manifest_version: "1"`, `manaurum_sdk_version: "1"`, `slug`, `version` (semver), `entry_point` (bundle-relative path), and limits permissions to a 7-value enum (`auth.read_user`, `auth.read_workspace_members`, `navigation.open_app`, `navigation.close_self`, `events.subscribe`, `db.read_own_entities`, `db.write_own_entities`).
- **`manaurum-app` rewritten for multi-tenant context.** The skill now teaches that `manaurum:init` carries a `tenant` block (`{id, slug}`) plus `workspace`, `user`, `app` blocks — apps can render tenant-aware UI and identify their B2B operator.
- **`templates/manifest.json` and `manaurum-setup` scaffolding updated** to v1 schema + `MANAURUM_TENANT_TOKEN`.

### Added

- Manifest v1 reference with the full enum of permissions, entity field types, integration declarations, and rejection codes.
- New deploy rejection-code table with one-line remediations for every `rejected_*` code returned by the Deploy API.
- Tenant context bridge documentation: `payload.tenant.slug` for B2B kustomization, with explicit "do NOT use as a security filter — RLS already enforces" warning.
- Per-tenant deploy guidance: a `mnu_*` token is bound to ONE tenant; multi-tenant apps require independent deploys with separate tokens.

### Removed (from skill docs)

- Legacy `/api/developer/apps/quick-create`, `/hosting/paste`, `/hosting/upload`, `/manifest`, `/probe-entrypoint`, `/diagnostics` endpoints. They still exist on the platform for the in-platform App Builder UI but are no longer the recommended path for external developers.
- `mdev_*` token references.
- Permissions outside the v1 enum (`theme.read`, `storage.*`, `files.*`, `window.manage`, `notifications.*`, `tasks.suggest`) from the manifest validation table. Runtime SDK methods may still work but are not gated by manifest in v1 — treated as evolving.

### Migration

If you have an existing app deployed via the legacy flow:
1. Generate a new `mnu_*` token (`POST /api/developer/tenant-tokens` with your session JWT).
2. Convert your manifest to v1 schema (see `manaurum-app/references/manifest-spec.md`).
3. Bundle as `bundle.zip` with `index.html` at the root.
4. Redeploy via `POST /api/dev/apps/deploy`. The new deploy creates a fresh `applications` row in your tenant's catalog under the v1 schema.

## 1.1.0 (2026-04-08)

### Added
- **UI Kit reference**: comprehensive design system with exact styles from built-in apps — cards, buttons, inputs, labels, badges, toggles, sidebars, tabs, task cards, section headers, empty/loading states
- **Theme-aware template**: `templates/theme-aware-app.html` demonstrating all design patterns with automatic Smoothie/XP switching
- **Internal hosting docs**: updated publishing reference with paste HTML and upload ZIP hosting on ManAurum (no external hosting needed)
- **Quick-create API docs**: `POST /api/developer/apps/quick-create` for one-step app creation

### Changed
- Design guidelines expanded from basic colors/fonts to full component library
- Publishing flow updated to reflect Telegram-style creation (name only, slug auto-generated)

## 1.0.0 (2026-04-08)

### Added
- `manaurum-app` skill — generate apps from prompts with SDK, manifest, theme support
- `manaurum-deploy` skill — hosting setup, publishing (private/unlisted/public)
- `manaurum-setup` skill — scaffold new project from scratch
- SDK API reference (all postMessage events, SDK methods, 7 permissions)
- Manifest specification (validation rules, field reference, window presets)
- Design guidelines (Smoothie/XP themes, colors, typography)
- Publishing flow (private → unlisted → public, review process)
- Templates: hello-world.html, manifest.json

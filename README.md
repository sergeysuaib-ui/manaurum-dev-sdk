# ManAurum OS Developer SDK — Claude Code plugin

**Version 2.11.0.** Skills that teach Claude Code to build and ship apps for
[ManAurum OS](https://manaurum.com), plus a starter app that deploys green with no edits.

ManAurum OS is a multi-tenant browser desktop. An app of yours is **a Docker container**
that the platform builds, runs and routes: after one deploy it is live at
`https://<your-slug>.apps.manaurum.com` with TLS, and it also appears as a window on the
desktop of every tenant that installs it.

---

## The model in one screen

**Your app is a container. The manifest is the contract.** You ship a tarball with a
`Dockerfile` and a `manifest.json`; the platform builds the image, runs it as a Swarm
service, and points Traefik at it. Nothing about your source language matters — if it
serves HTTP, it works.

**It reaches the platform through one door.** No database credentials, no S3 keys, no
provider tokens. Your container calls the **capability gateway** — a typed HTTP API for
key-value storage, files, AI, events and outbound HTTP — using the
`MANAURUM_RUNTIME_TOKEN` the platform injects. Each capability your app uses must be
declared in the manifest and granted by the tenant admin at install time.

**Who is asking arrives as a signed header.** For routes you mark `auth: "user"`, the
gateway mints a 60-second RS256 JWT and injects it as `X-Manaurum-User-Context`. Verify it
against `CORE_USER_CONTEXT_PUBLIC_KEY_PEM`. The end user's own session token is never
forwarded to you, and you must never forward the user context onward to the gateway.

**Four rules that cost first-timers the most time:**

| Rule | What happens if you miss it |
|---|---|
| `/api/*` is **default-deny**. Every API path must be listed in `manifest.runtime.api_routes`. | The gateway answers `404 route_not_declared` and the request never reaches your container. Looks like a backend bug with silent logs. |
| Traefik targets `manifest.runtime.port` (default **80**). `EXPOSE` is never parsed. | Green deploy, then `502 upstream_unreachable` on every request. |
| The desktop shell requires the `manaurum:ready` handshake within 10 s. | The standalone URL works fine, so you notice nothing — until someone opens the app on the desktop and gets "App is not responding". |
| `/agent/*` bypasses the gateway but **not the network**. Verify the user-context JWT in every handler. | `<slug>.apps.manaurum.com` is Traefik straight to your container, so an unauthenticated POST to `/agent/<name>` reaches your code. Skipping the check because "only the runtime calls this" ships an open endpoint. |

**Who can install it** is `manifest.visibility.mode`: `private` (default), `public`, or
`allow_list` (with `visibility.tenants`). It is enforced when a tenant installs, not by
obscurity — see "Honest gaps" below.

---

## Install the plugin

```bash
claude plugin marketplace add sergeysuaib-ui/manaurum-dev-sdk
claude plugin install manaurum-dev-sdk@manaurum-sdk
```

Updating later:

```bash
claude plugin marketplace update manaurum-sdk
claude plugin update manaurum-dev-sdk@manaurum-sdk
```

Restart Claude Code afterwards. If a skill still describes something this README
contradicts, your local plugin cache is stale — run `/plugin` and update.

**A session that is already running does not notice the update**: the cache keeps one
directory per version, and a skill loaded from the old one keeps reading it. Since 2.9.0
the plugin ships a `SessionStart` hook (`hooks/hooks.json` → `scripts/version_check.py`)
that says so out loud when it happens, leaves a `STALE.md` in the superseded directory
and a `current` pointer beside it. It prints nothing when your copy is current, and it
cannot fail a session — but it only speaks at session start, so after `/plugin update`
the honest move is still to re-invoke the skill.

## Install the CLI

The `manaurum` CLI scaffolds, validates and deploys. It is **not on PyPI yet**; until it
is, install the wheel from this repo's
[releases](https://github.com/sergeysuaib-ui/manaurum-dev-sdk/releases) (Python 3.11+):

```bash
pip install https://github.com/sergeysuaib-ui/manaurum-dev-sdk/releases/download/cli-v0.2.0/manaurum_cli-0.2.0-py3-none-any.whl
manaurum --version
```

Then save your token — ask your ManAurum workspace admin to issue one in
**DevHub → Credentials** (`mna_…`, choose "All apps" scope unless you have a reason not
to; a token restricted to specific slugs cannot deploy an app it does not already list):

```bash
manaurum auth login --token mna_...
```

---

## Quick start

```bash
cp -r templates/v2-starter my-app && cd my-app
grep -rl my-app . | xargs sed -i 's/my-app/<your-app-id>/g'
pip install -r requirements.txt -r requirements-dev.txt && pytest   # all green, offline
manaurum app validate           # manifest against the v2 schema
manaurum app deploy             # 202 + poll; prints the live URL when it activates
```

Copy the starter rather than running `manaurum app init`. The CLI's scaffold was rebuilt
to this same shape (MAN-1397). That rewrite is in no released wheel, and
`pip install manaurum-cli` still 404s on PyPI (MAN-1385), so the wheel you can actually
install is `cli-v0.2.0`, built before it. Until a release carries the new scaffold, the
directory below is the one that is tested on every PR.

The starter deploys unchanged. It is not a hello-world stub: it serves a UI that answers
the shell handshake, verifies a real user-context JWT on `/api/me`, does a real key-value
round trip through the capability gateway on `/api/notes`, and exposes two
`agent_capabilities` so the OS Assistant can read and write on the user's behalf. Its
suite runs offline — no database, no account, no network — and it covers the wiring, not
just the pieces: remove an auth dependency from a route and a test goes red. CI runs it on
every PR and prints the count. Read its `README.md`, then replace the note-taking parts
with your own.

Useful afterwards:

```bash
manaurum app describe --app-id my-app
manaurum app logs --app-id my-app --tail 200
manaurum app list-versions --app-id my-app
manaurum app rollback 0.1.0 --app-id my-app
```

---

## Skills

| Skill | Fires when you say | What it does |
|---|---|---|
| `manaurum-app` | "build / create a ManAurum app" | Writes the app: v2 manifest, Dockerfile, capability calls, user-context verification, the shell handshake. |
| `manaurum-setup` | "start / scaffold a new project" | Sets up a fresh v2 project directory. |
| `manaurum-deploy` | "deploy / publish / release it" | Token issuance, build context, the 202-plus-poll deploy contract, rejection codes, rollback, install. |

You rarely invoke them by name — describing the task is enough:

```
Build a ManAurum app that tracks my team's on-call rota and reminds people the day before
```

Deep references live in `skills/manaurum-app/references/`: the capability catalogue, the
manifest spec, the v2 platform model, the client SDK, publishing, and design. Start with
`reference-apps.md` — three production apps at different sizes, with the load-bearing
parts inlined. Reading one real app beats reading four pages about apps.

## Templates

* `templates/v2-starter/` — the bundle above, and the only complete v2 scaffold that
  exists today. It is deliberately shaped like a real app: `auth.py` + `capability.py` as
  shared infrastructure, `main.py` + `agent_routes.py` as the two surfaces on top, and
  `tests/`. Apps grow by adding surfaces, not by growing one file. It is **not** identical
  to `manaurum app init` output, and it stays here until a CLI release ships the same
  scaffold (MAN-1385).
* `templates/check_ui.py` — the UI contract, mechanically. It reads your static files and
  fails on what a green deploy hides: a hex hidden in a `var()` fallback whose token does
  not exist, `style=`, a `tab`/`sidebar` class, `<button class="row">`, a click target
  with no `is-interactive`, `alert`/`confirm`/`prompt`, more than one primary button in a
  view, a missing `manaurum:ready`, appearance read off `e.data` instead of
  `e.data.payload`. Comments are stripped first, so a comment explaining a rule is not a
  violation of it. `python check_ui.py src/static`, exit 1 on findings. Two apps have now
  been rejected on sight for things on this list; a rule a program checks is the only kind
  that survives a hurry. CI runs it against the starter, so the reference app is held to
  the reference linter.
* `templates/check_app.py` — the same idea for the backend, run on the directory the
  deploy packs: an `/api/*` route no `runtime.api_routes` rule covers (including the
  `/api/x/*`-does-not-cover-`/api/x` case), a declared route nothing serves, an
  `/agent/*` handler with no user-context verification, `runtime.port` disagreeing with
  the `CMD` or with `EXPOSE`, an `entry_point` naming nothing, a `.env*` inside the app
  directory, a capability called but not declared (or declared and never called), and
  migrations that are not ordered `*.sql` or carry destructive DDL without
  `migration.breaking`. Routes are read out of Python decorators with `ast`; for another
  language it says so and skips those two rules rather than guessing.
  `python check_app.py my-app`, exit 1 on findings.
* `templates/preview.py` + `preview-fixtures.json` — look at the app before you deploy
  it. A stdlib-only server that serves your static files, stubs every `/api/*` from the
  fixtures file, and frames the page the way the desktop shell does: the shell's exact
  sandbox, a real `manaurum:init` with the appearance and accent you ask for, and two
  badges — one for `manaurum:ready`, one saying whether the appearance was actually
  applied. Fixtures match like `runtime.api_routes` does (`/api/items/*`), a fixture can
  describe a failure or a delay (`{"status": 500}`, `{"delay_ms": 1500}`), and `?width=`
  sizes the app's frame so the narrow window the design contract is written for can be
  photographed honestly. Keep it *beside* the app directory — everything inside is
  packed into the deploy.
* `templates/legacy-v1/` — the old iframe-bundle artifacts. Kept only for apps that
  already ship on v1; do not start anything new from them.

---

## Honest gaps

Things people reasonably expect that do not exist yet. Better to read it here than to
discover it at 2 a.m.:

* **No local dev loop for the backend.** There is no `manaurum app dev`: capabilities are
  only reachable from inside a deployed container, so the inner loop for anything that
  calls the gateway is still deploy and look. The *frontend* now has one —
  `templates/preview.py` frames the page like the shell and stubs the API — but it stubs,
  it does not run your app.
* **Build failures give you one line.** If the image fails to build you get a short
  reason, not the Docker log.
* **"Succeeded" means built and scheduled**, not "your container answers". A deploy that
  reports success can still be 502 on the first request — check the URL yourself.
* **No scheduled jobs and no inbound webhooks.** `schedules` and `webhooks` exist in the
  manifest schema but nothing runs them yet.
* **No metrics.** `manaurum app logs` is a tail of the last N lines, with no follow.
* **Subdomains are public knowledge.** Your app's hostname appears in Certificate
  Transparency logs seconds after its first deploy, whatever `visibility.mode` says.
  Visibility controls *installation*, not the existence of the URL — so put auth on
  anything sensitive, and expect scanners to walk it.

---

## Resources

* [Developer docs](https://manaurum.com/developers)
* [Client SDK (v2, ESM)](https://manaurum.com/sdk/manaurum-v2.mjs)
* [Manifest schema (v2)](https://manaurum.com/sdk/manifest_v2.schema.json)
* [Design tokens](https://manaurum.com/api/library/tokens.css) and the public
  [component library](https://manaurum.com/library)

Legacy v1 (iframe apps, `manaurum.js`, `mnu_*` tokens) is still supported for apps already
on it; each skill keeps a "Legacy v1" section at the bottom.

## License

MIT

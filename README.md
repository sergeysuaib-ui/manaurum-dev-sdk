# ManAurum OS Developer SDK — Claude Code and Codex plugin

**Version 3.20.1.** Skills that teach Claude Code and Codex to build and ship apps for
[ManAurum OS](https://app.manaurum.com) (the product; the API, SDK and developer docs stay on `manaurum.com`), plus a starter app that deploys green with no edits.

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
against `CORE_USER_CONTEXT_PUBLIC_KEY_PEM` with your `MANAURUM_APP_ID` as the audience, and
check its `tenant_id` is your `MANAURUM_TENANT_ID`: every app's tokens share one key and the
audience `manaurum-app`, so only your own id in `aud` says a token is yours. The end user's own session token is
never forwarded to you. Forward the user context to the capability gateway when you act on
the user's behalf; `os.drive.*` and `os.calendar.*` refuse a call without it.

**Four rules that cost first-timers the most time:**

| Rule | What happens if you miss it |
|---|---|
| `/api/*` is **default-deny**. Every API path must be listed in `manifest.runtime.api_routes`. | The gateway answers `404 route_not_declared` and the request never reaches your container. Looks like a backend bug with silent logs. |
| The platform reaches your container on `manifest.runtime.port` (default **80**). `EXPOSE` is never parsed. | The deploy's readiness probe finds nobody listening, rolls back and fails the job. |
| The desktop shell requires the `manaurum:ready` handshake within 10 s. | The standalone URL works fine, so you notice nothing — until someone opens the app on the desktop and gets "App is not responding". |
| `/agent/*` bypasses the gateway. Verify the user-context JWT in every handler, and that it names your app. | The public host refuses `/agent/*`, but every app's container shares one network, so another app can call yours directly. Skipping the check because "only the runtime calls this" ships an endpoint any app can reach. |

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

**Turn on auto-update.** A marketplace added from GitHub does not update itself by
default: one machine was still running 2.7.2 six weeks and a major version later. In
`/plugin` → Marketplaces → `manaurum-sdk` → Enable auto-update, and Claude Code refreshes
the marketplace and the plugin at each session start.

**A session that is already running does not notice the update**: the cache keeps one
directory per version, and a skill loaded from the old one keeps reading it. Since 2.9.0
the plugin ships a `SessionStart` hook (`hooks/hooks.json` → `scripts/version_check.py`)
that says so out loud when it happens, leaves a `STALE.md` in the superseded directory
and a `current` pointer beside it. Since 3.7.0 it also notices a newer release that is not
on disk at all: it reads the marketplace clone, and at most once a day the version on
GitHub (2 s timeout; `MANAURUM_SDK_NO_UPDATE_CHECK=1` turns that off). It prints nothing
when your copy is current, and it cannot fail a session — but it only speaks at session start, so after `/plugin update`
the honest move is still to re-invoke the skill.

## Install in Codex / ChatGPT Work

The same `skills/` and `templates/` serve both agents; `.codex-plugin/plugin.json` (and
the portable `plugin.json` at the root) supply the Codex metadata, so nothing is forked.
To try a checkout locally, put this repository in your personal plugins directory as
`~/.agents/plugins/plugins/manaurum-dev-sdk` and add it to
`~/.agents/plugins/marketplace.json` as a local plugin:

```json
{
  "name": "personal",
  "interface": {"displayName": "Personal"},
  "plugins": [{
    "name": "manaurum-dev-sdk",
    "source": {"source": "local", "path": "./plugins/manaurum-dev-sdk"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Developer Tools"
  }]
}
```

If you already have a personal marketplace, append only the entry in `plugins[]`. Restart
ChatGPT, open the Plugins Directory, select the Personal source, and install **ManAurum
Developer SDK**; start a new chat to load its skills. The Codex CLI alone does not install
a local plugin; installation is done in the ChatGPT desktop app. An install in a fresh
ChatGPT chat is still not verified end to end (MAN-1439), and the skills were written for
Claude Code: they name each other as slash commands (`/manaurum-deploy`), the stale-copy
check at the top of `manaurum-app` assumes Claude Code's per-version plugin cache, and the
session-start update check is a Claude Code hook that does not run in Codex.

## Install the CLI

The `manaurum` CLI scaffolds, validates and deploys. It is **not on PyPI yet**; until it
is, install the wheel from this repo's
[releases](https://github.com/sergeysuaib-ui/manaurum-dev-sdk/releases) (Python 3.11+):

```bash
pip install https://github.com/sergeysuaib-ui/manaurum-dev-sdk/releases/download/cli-v0.3.5/manaurum_cli-0.3.5-py3-none-any.whl
manaurum --version        # manaurum, version 0.3.5
```

Then save your token. Mint it in **DevHub → Credentials** (`mna_…`) and keep the
default, "all my apps": a token restricted to specific apps cannot deploy an app that does
not exist yet. The CLI keeps it in `~/.manaurum/config.json`:

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

Copy the starter rather than running `manaurum app init`. The CLI's scaffold has the same
shape (MAN-1397), and since `cli-v0.3.1` it follows the person's language too, but the
starter is the one this repository tests on every PR, so a rule this plugin adds reaches it
first. Use CLI 0.3.1 or later: 0.3.0 refuses `auth: "optional"` and `auth: "people"` routes
in `app validate` and in the deploy preflight. `pip install manaurum-cli` still 404s on
PyPI (MAN-1385); install the wheel above.

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
| `manaurum-setup` | "scaffold / initialize an app directory" (and `manaurum-app` sends you there) | Sets up a fresh v2 project directory from the starter. |
| `manaurum-deploy` | "deploy / publish / release it" | Token issuance, build context, the 202-plus-poll deploy contract, rejection codes, rollback, install. |

You rarely invoke them by name — describing the task is enough:

```
Build a ManAurum app that tracks my team's on-call rota and reminds people the day before
```

Deep references live in `skills/manaurum-app/references/`: the capability catalogue, the
v2 platform model (manifest included), the client SDK, publishing, and design. Start with
`reference-apps.md` — three production apps at different sizes, with the load-bearing
parts inlined. Reading one real app beats reading four pages about apps.

## Templates

* `templates/v2-starter/` — the bundle above, and the only complete v2 scaffold that
  exists today. It is deliberately shaped like a real app: `auth.py` + `capability.py` as
  shared infrastructure, `main.py` + `agent_routes.py` as the two surfaces on top, and
  `tests/`. Apps grow by adding surfaces, not by growing one file. It is **not** identical
  to `manaurum app init` output, and it stays here until a CLI release ships the same
  scaffold (MAN-1385).
* `templates/patterns/index.html` — the two kinds of screen the starter does not show:
  a list of texts with filter chips, one text on its own page (`.reader`, `.prose`), and
  a list of records to sort through. The starter is a form and a short record list; an
  app people *read* copied from it looks like a ledger, and that is how one was rejected.
  Open it framed with `python templates/preview.py --app templates`.
* `templates/design-review.md` — five questions to answer in writing about each screen
  before a deploy. A screenshot looked at against a list of prohibitions found nothing on
  an app its owner rejected on sight; the questions ask what the owner asks.
* `templates/check_ui.py` — the UI contract, mechanically. It reads your static files and
  fails on what a green deploy hides: a hex hidden in a `var()` fallback whose token does
  not exist, `style=`, a `tab`/`sidebar` class (in markup, JSX or a built bundle), `<button class="row">`, a click target
  with no `is-interactive`, `alert`/`confirm`/`prompt`, more than one primary button in a
  view, a missing `manaurum:ready`, appearance read off `e.data` instead of
  `e.data.payload`, an accent class handed out inside a render loop, more than four
  accent classes in one view, the person's language never applied to `<html lang dir>`,
  and a physical side (`margin-left`, `text-align: left`) that will not mirror for Hebrew.
  Comments are stripped first, so a comment explaining a rule is not a
  violation of it. `python check_ui.py src/static`, exit 1 on findings. Two apps have now
  been rejected on sight for things on this list; a rule a program checks is the only kind
  that survives a hurry. CI runs it against the starter and the patterns page, so the
  reference screens are held to the reference linter.
* `templates/check_app.py` — the same idea for the backend, run on the directory the
  deploy packs: an `/api/*` route no `runtime.api_routes` rule covers, matched the way
  the gateway matches (a trailing `/*` covers what is below, everything else is literal),
  a declared route nothing serves, an `/agent/*` handler with no user-context
  verification, `runtime.port` disagreeing with the `CMD` or with `EXPOSE`, an
  `entry_point` naming nothing, a `.env*` inside the app directory, a capability called
  but not declared, declared and never called, or not registered on Core at all, a root
  key, `auth` mode, slug or Assistant tool name the deploy refuses, and migrations it
  would refuse (read through a small SQL lexer, so a function body, a string or a comment
  is not a statement), a generated column on one of the common built-ins Postgres refuses
  there (`array_to_string`, `concat`, one-argument `to_tsvector`, clock, random and
  sequence functions - not every refusal, so a setting-dependent cast still reaches
  Postgres), a session `SET` in an asyncpg pool's `init=`, and code reading
  `DATABASE_URL` under `"data": {"none": true}`.
  Routes are read with `ast` from decorators, `add_api_route` and `include_router`
  prefixes; for another language it says so and skips those rules rather than guessing.
  `python check_app.py my-app`, exit 1 on findings.
* `templates/recipes/postgres/` — for an app that keeps its data in Postgres: `db.py` (an
  asyncpg pool whose `search_path` survives the pool's `RESET ALL`), `search.py` (full-text
  search that falls back from all-words to some-words instead of answering zero, with an
  XSS-safe snippet), the migrations for both, and a pytest suite that runs against a real
  Postgres — in CI too, including the broken `init=` pool it replaces.
* `templates/manifest_v2.schema.json` + `templates/platform-contract.json` +
  `scripts/platform-strings.json` — the copy of Core's contract the linters and
  `check_repo.py` read: the manifest schema, every registered capability, the reserved
  slugs, the slug pattern, the write-verb rule, the Assistant's tool-name limit, every
  capability's input fields, the
  window's message types, and the snake_case words in the string literals of the Core
  code a developer's errors come from, with the Core
  SHA they came from. `python scripts/sync_contract.py --monorepo ../Manaurum` refreshes
  them; run
  `check_repo.py` afterwards and it names every sentence the refresh made false.
* `scripts/check_repo.py` + `scripts/linter_mutations.py` + `scripts/smoke_tools.py` —
  the plugin checking itself, run by CI on every PR. `check_repo.py` holds the documents
  to the repository (one version string, every documented path and heading citation
  resolves, no hardcoded self-counts, no control byte, no fixed `/tmp` path, no
  documented flag the tool rejects) and to the contract (every registered capability
  documented, no capability named that Core lacks, the `permissions` enum as the schema
  has it, each single-capability section's documented input equal to its schema, no
  quoted error code
  that appears nowhere in Core's strings any more, no window
  message the shell does
  not know and none it sends left undescribed, and none of the facts the 2026-10-02 audit
  found stale back in any document or template), and the newest CHANGELOG release carries
  a `Summary:` line — one plain sentence the team's release announcement quotes;
  `linter_mutations.py` breaks the starter once per
  rule and demands that each linter goes red; `smoke_tools.py` starts `preview.py` and
  the version hook and checks they still behave, including preview's first-screen meter
  in a real headless Chrome. All stdlib, all runnable locally.
* `templates/preview.py` + `preview-fixtures.json` — look at the app before you deploy
  it. A stdlib-only server that serves your static files, stubs every `/api/*` from the
  fixtures file, and frames the page the way the desktop shell does: the shell's exact
  sandbox, a real `manaurum:init` with the appearance, accent and language (`?locale=he`) you
  ask for, an en / ru / he switch that posts `manaurum:locale-change`, and four badges —
  one for `manaurum:ready`, one saying whether the appearance was actually applied, one
  whether the language was, one saying whether the page is centred — plus three measurements of the first
  screen: how many elements are painted in the accent (red above four), whether one badge
  sits on most rows of a list (red), and how far down the first list row starts. Fixtures match like `runtime.api_routes` does (`/api/items/*`), a fixture can
  describe a failure or a delay (`{"status": 500}`, `{"delay_ms": 1500}`), and `?width=`
  sizes the app's frame so the narrow window the design contract is written for can be
  photographed honestly. Keep it *beside* the app directory — everything inside is
  packed into the deploy.

---

## Honest gaps

Things people reasonably expect that do not exist yet. Better to read it here than to
discover it at 2 a.m.:

* **No local dev loop for the backend.** There is no `manaurum app dev`: capabilities are
  only reachable from inside a deployed container, so the inner loop for anything that
  calls the gateway is still deploy and look. The *frontend* now has one —
  `templates/preview.py` frames the page like the shell and stubs the API — but it stubs,
  it does not run your app.
* **"Succeeded" means the container answered one path.** The readiness probe calls
  `runtime.health_path` (or `/healthz`); it does not exercise your `/api/*` routes or the
  window.
* **No inbound webhooks.** `webhooks` exists in the manifest schema but nothing runs it yet.
  Scheduled jobs do run since Core MAN-1373: `schedules` (see `v2-platform.md`, "Scheduled
  jobs — `schedules`").
* **Usage numbers, but no error tracking for an SDK app.** `GET /api/app-usage/<uuid>`
  (MAN-3131) — the platform's app UUID (`app_id` in `GET /api/dev/v2/apps/<slug>`), not
  your slug, called with a signed-in session (the app's author, or a tenant admin in a
  team workspace), not an `mna_*` token — gives per-day
  signed-in users, visits and refused or failed saves, people in the last 7 days and
  people active now; anonymous visitors are not counted. Errors raised in the browser
  are collected only for Aurum Studio apps (MAN-3132): its injected runtime reports them,
  and an SDK app has no such runtime. `manaurum app logs` is a tail of the last N lines,
  with no follow.
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

Platform v2 is the only path for an app built outside the monorepo; the old iframe-bundle
path is retired and these skills do not teach it. An `mnu_*` token is a tenant token for
MCP clients and Drive upload; it cannot deploy an app.

## License

MIT

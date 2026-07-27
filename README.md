# ManAurum OS Developer SDK — Claude Code plugin

**Version 2.7.1.** Skills that teach Claude Code to build and ship apps for
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
pip install -r requirements.txt -r requirements-dev.txt && pytest   # 19 passed
manaurum app validate           # manifest against the v2 schema
manaurum app deploy             # 202 + poll; prints the live URL when it activates
```

Copy the starter rather than running `manaurum app init`. The CLI's scaffold is being
rebuilt to this same shape (MAN-1397), but that rewrite is not in any released wheel yet —
and `pip install manaurum-cli` still 404s on PyPI (MAN-1385), so the wheel you can actually
install is `cli-v0.2.0`, built before it. This section points at the CLI once a release
carries the new scaffold; until then the directory below is the one that is tested.

The starter deploys unchanged. It is not a hello-world stub: it serves a UI that answers
the shell handshake, verifies a real user-context JWT on `/api/me`, does a real key-value
round trip through the capability gateway on `/api/notes`, and exposes two
`agent_capabilities` so the OS Assistant can read and write on the user's behalf. Its
19 tests run offline — no database, no account, no network — and they cover the wiring,
not just the pieces: remove an auth dependency from a route and a test goes red. Read its
`README.md`, then replace the note-taking parts with your own.

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
  to `manaurum app init` output; when the CLI catches up (MAN-1393) this directory goes
  away in favour of it.
* `templates/legacy-v1/` — the old iframe-bundle artifacts. Kept only for apps that
  already ship on v1; do not start anything new from them.

---

## Honest gaps

Things people reasonably expect that do not exist yet. Better to read it here than to
discover it at 2 a.m.:

* **No local dev loop.** There is no `manaurum app dev`; the inner loop today is deploy
  and look.
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

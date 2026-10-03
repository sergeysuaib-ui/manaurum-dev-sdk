# The checks before a deploy — Steps 3.5 and 3.6 in full

`manaurum-app/SKILL.md` gives each mandatory check as a command and the rule for
passing it. This page is the rest: why each check exists, what each part of it
measures, the traps in running it, and what you would have seen instead. Read
it the first time you run the checks, and whenever one of them says something
you do not understand.

Both checks exist because a green deploy hides exactly these failures. Up to
Step 3.5 you have read code, and nobody has *seen* the app; up to Step 3.6
nobody has held the code against the manifest. Everything below otherwise
fails *after* the deploy, in a way that does not look like its cause.

---

## Step 3.5 — Check the UI before you deploy it

**The last step of building an interface, and it is as mandatory as the
handshake in Step 2.5 or `healthz` after a deploy.** Design rules do not
survive a build that is never looked at: the four failures that got a real app
rejected — tab-bar navigation, sentences in badges, a blue button in every row,
a light app in a dark desktop — were all obvious in the first screenshot and
invisible in the diff. Most of them then shipped again in a second app a week
later, by an agent that had read the rules.

### 1. Run the linter

```bash
python <plugin>/templates/check_ui.py my-app/src/static
```

It is 200 lines and it takes a second. `check_ui.py` covers every one of the
seven rules (`SKILL.md` → "The seven rules an app gets sent back for") except
rule 3 — a sentence in a badge is the one only a person can see — and a hover
on something inert (rule 5's first half): it fails a click target with no
hover, but not a hover on something inert. Those two are yours to look for.

It also covers three that a screenshot cannot show either: a hex hidden inside
a `var()` fallback whose token does not exist, a click target with no
`is-interactive`, and appearance read off `e.data` instead of
`e.data.payload`. It fails a page root that caps its width and never centres
it, which no screenshot at or under the cap can show, and the two halves of
rule 4's accent budget it can read from source: an accent class
(`btn-primary`, `btn-ghost`, `badge-accent`) handed out inside a loop, and more
than four of them in one view.

Exit 0 or fix what it names. Do this *before* the screenshots: it is cheaper,
and half of what it finds would otherwise reach the owner rather than you.

### 2. Serve it with stubs

`<plugin>/templates/preview.py` is a stdlib-only script (no install, no
dependencies): it serves your static files, answers every `/api/*` call from a
fixtures file, and adds a `/__shell` page that frames your app the way the
desktop does — the shell's exact sandbox, a real `manaurum:init` with the
appearance and accent you ask for, and three badges: one for
`manaurum:ready`, one that says whether the appearance was actually *applied*,
and one that measures whether your page is *centred* in the frame. Keep it
**beside** the app directory, never inside it: everything inside is packed into
the deploy.

```bash
cp <plugin>/templates/preview.py <plugin>/templates/preview-fixtures.json .
# one entry per /api path your UI calls; anything unlisted answers {}
python preview.py --app my-app/src/static
```

Fixture paths match the way `runtime.api_routes` does — exact first, then the
longest `/prefix/*` — so `/api/items/42` is reachable and the detail screen
photographs with real content. A fixture value can also be an envelope,
`{"status": 500}` or `{"delay_ms": 1500, "body": {…}}`, which is how you
photograph the three states `design.md` asks you to distinguish: nothing yet,
could not load, still loading.

### 3. Photograph both appearances, the wide window and the narrow one

Chrome or Edge, same flags (on Windows, the full path to `chrome.exe` and any
fresh directory for the profile).

```bash
chrome --headless=new --disable-gpu --hide-scrollbars \
  --user-data-dir="$(mktemp -d)" --virtual-time-budget=4000 \
  --window-size=1240,1000 --screenshot=light.png \
  "http://127.0.0.1:8765/__shell?appearance=light"

# and again with ?appearance=dark → dark.png
```

A fresh `--user-data-dir` keeps the run independent of whatever browser profile
is open; a locked profile is one of the ways this command exits without writing
a file and without printing an error, which reads as "the page failed to
render".

**`--virtual-time-budget` waits for the fetches, and it cannot be shortened to
catch a skeleton.** Chrome pauses virtual time while a request is in flight, so
against a `{"delay_ms": 6000}` fixture a budget of 400ms and one of 1200ms both
wait the full six seconds and photograph the *loaded* page (measured, Chrome
141 `--headless=new`). To photograph a loading state, **drop the flag
entirely** — then the shot happens at the load event, with the skeletons still
up. The trade is that preview's own appearance check has not run yet at that
moment, so take the theme evidence from one of the other screenshots.

Add `&accent=lavender` (or any of the nine) to check you are not hardcoding
blue.

**The wide window — the first thing an owner does is drag the window wider.**
Up to your `max-width` a centred and a left-glued page are pixel-identical, so
no narrow shot can tell them apart; past it, a cap with no
`margin-inline: auto` leaves the app on the left edge and dead space on the
right. That shipped in four apps (MAN-2849) — and it was *in* the 1240 shot
above, 216px of empty right margin that nobody read as a defect. So do not read
it; the third badge measures it:

```bash
… --window-size=1920,1000 --screenshot=wide.png \
  "http://127.0.0.1:8765/__shell?appearance=light"
```

`layout centred` is the pass. `layout OFF-CENTRE - 0px left, 216px right` is
the fail, with both gaps in pixels. `layout fills …px` means the shot is not
wider than your cap and proves nothing about centring — which is what the
narrow shot below will always say.

**The narrow window, because that is the one the contract is written for.**
Add `&width=900` (or 760, or whatever your smallest supported window is): it
sizes *your app's frame* inside a large browser window, so the headless
viewport floor never applies.

```bash
… --window-size=1240,1000 --screenshot=narrow.png \
  "http://127.0.0.1:8765/__shell?width=900&appearance=light"
```

Do not try to do this by shrinking the browser instead: both browsers floor
their own layout viewport at ~500px, so `--window-size=390,800` still lays out
at 500 and merely crops the PNG — a perfectly good phone layout photographs as
broken (measured on Chrome and Edge, `--headless=new`). `&device=mobile` posts
the mobile device flag, which is a different thing from geometry and worth
combining with `&width=390`.

**Headless cannot click, so the second screen is only reachable by URL.** A view
behind a button is a view no screenshot ever sees. Each view gets its own
fragment — `#customers`, `#item/42`, read on load and on `hashchange` — and you
shoot it with `…/__shell?entry=/index.html%23item/42`. The starter's
`index.html` ships this router; decide the fragments in Step 0, because
retrofitting them after the app exists is exactly why this check gets skipped.

### 4. Read the bar across the top of each picture, then criticise the pictures

Criticise them honestly, against the seven rules and the `Never` table that
opens `design.md` — out loud, in your reply. Besides the three badges,
`preview.py` measures the first screen of the rendered app: how many elements
are painted in the accent (red above four), whether one badge sits on more than
half the rows of a list (red), and how far down the first list row starts. A
red pill is a failure however good the picture looks.

The linter has already taken the mechanical half; what is left is the half only
a person (or you, looking) can see: is the hierarchy right, is the empty state
saying something useful, would you show this to the person who asked for it.
Also read the terminal: `preview.py` logs every `/api/*` your UI called, which
is the cheapest way to find a route missing from `runtime.api_routes` before it
404s in production.

### 5. Answer the design review in writing, and put the answers in your reply

Copy `<plugin>/templates/design-review.md` beside the app directory, not inside
it. Looking at a screenshot does not work on its own: an agent that
photographed its app, looked, and criticised it out loud against the list of
prohibitions saw nothing wrong — every mistake the owner then named was in that
picture, and none of them was a prohibition. The questions are not a list of
prohibitions:

1. What is the most important thing on this screen — and does it *look* the
   most important?
2. How many accent-coloured things are on it? (The bar says. Over four, redo.)
3. Cover the metadata with your hand. Does each list row still make sense?
4. How much of the first screen do the filters and controls take before the
   first row of data?
5. Is this a screen for reading, for entering, or for sorting through a list —
   and is it laid out as that kind (Step 0, item 6)?

The fifth is the one that catches the expensive mistake: a reader built as a
list-triage screen passes every rule. Answer per screen, fix what the answers
name, re-shoot, and only then deploy — name what is wrong and fix it before the
deploy, not after the rejection.

---

## Step 3.6 — Check the app against its manifest

**The last step before the deploy, and the cheapest one.** Step 3.5 looked at
the interface; this looks at the contract. Everything it checks is described in
`SKILL.md` or in `v2-platform.md` in prose, and every one of them otherwise
fails *after* the deploy, in a way that does not look like its cause.

```bash
python <plugin>/templates/check_app.py my-app
```

Pass the directory that holds `manifest.json` — the same directory the deploy
packs. Exit 0 or fix what it names.

| It finds | What you would have seen instead |
|---|---|
| an `/api/*` route no `runtime.api_routes` rule covers — including the `/api/x/*`-does-not-cover-`/api/x` case | `404 route_not_declared` at the gateway. Your handler never runs, and your logs are silent, so it reads as a backend bug. |
| a declared route nothing serves | the manifest describing an app you did not build |
| an `/agent/*` handler with no user-context verification | nothing. An endpoint any other app's container can call, indefinitely. |
| `runtime.port` disagreeing with what the container binds (and with `EXPOSE`) | a deploy that fails its readiness probe, a build and push later |
| `frontend.entry_point` naming a file that is not there | the window opens on a 404 |
| any `.env*` **inside** the app directory | a token baked into an image layer and retained per version. There is no way to un-leak it. |
| a capability called but not declared — or declared and never called | `403 capability_not_granted` at the first real use; or a grant request a tenant admin is asked to approve for nothing |
| `migrations/`: a non-`.sql` file, numbers of mixed width, a `DO $$` block, destructive DDL without `migration.breaking` | a migration that silently never runs, runs in the wrong order, or is refused at deploy |
| `migrations/`: a generated column on one of the common built-ins Postgres does not accept there (`array_to_string`, `concat`, one-argument `to_tsvector`, `now()`, `random()`) — not every refusal: a cast that depends on a setting, such as `::date` on a `timestamptz`, still gets through | a file the deploy's validator passes and Postgres then refuses, for every tenant |
| a session `SET` (`SET search_path`) inside an asyncpg `create_pool(init=...)` | an app that works on the platform and fails on the second request on your own machine |
| code that reads `DATABASE_URL` while the manifest says `"data": {"none": true}` | a green deploy and a crash on the first query — that mode injects no database |
| an invented key in `runtime` (`"prot": 8000`) | a `422` at deploy, after the pack and the upload — the linter names it offline, with the keys you could have meant |
| an `/agent/*` path listed in `api_routes` | nothing. It configures nothing while looking exactly like it did. |
| a relative `frontend.icon` (`icons/app.svg`) | that literal string painted into the launcher tile |
| an `mna_*`/`mnu_*` token literal anywhere in the directory | your deploy (or MCP and Drive) rights handed to every future reader of the image |
| `metadata.description` still starting with `TODO` | what the tenant admin reads on the install screen |

It also prints a **note** — not a failure — when the app has no tests at all.

**What it cannot see.** Routes and `/agent/*` handlers are read out of
**Python** decorators with `ast` — that is the starter's stack, and importing
your app to ask its router would need its dependencies installed. In any other
language it says so and skips those two rules; the manifest, port, capability,
`.env` and migration rules still run, because those read files rather than
code. A capability name assembled at run time (`f"os.kv.{verb}"`) is invisible
to it for the same reason.

And **write your own tests** — the starter ships a suite that covers the wiring
rather than the pieces (remove an auth dependency from a route and a test goes
red), and it is there to be copied, not just to be run. The one test worth
writing first is the one this step automates: your routes against your
manifest.

---

## Documenting code in the same edit that writes it

Step 3 in `SKILL.md` gives the rule; this is the whole of it.

Not a pass at the end: by then nobody remembers which `None` meant "absent" and
which meant "we don't know", and the docstring records the signature instead of
the contract. Python takes a Google-style docstring (summary line, the *why*,
then only the `Args:` / `Returns:` / `Raises:` that carry information); browser
JS takes JSDoc. Spend the words on what a reader cannot see — units, what an
empty return means, which failure is normal, what a caller must not do.
`item_id: The item id` is noise; a function with nothing non-obvious to say
gets one summary line. The starter's `tests/test_documented.py` fails on any
undocumented module, function or class under `src/`: keep it. And never anchor
a test on comment or docstring text — slice on a declaration instead, or
improving a sentence breaks the suite.

---

## When a check was skipped: the common codes

What the checks above would have caught, as it looks when it reaches the
platform instead. Deploy refusals and the job's failures in full:
`manaurum-deploy/SKILL.md`. Capability errors in full:
`capabilities-reference.md` → "Gates that run before your capability does".

| HTTP | Meaning | Fix |
|---|---|---|
| 401 `invalid_credential` | Bad/expired/revoked `mna_*`, or not an `mna_*` token. | Mint a fresh one in Dev Hub. |
| 412 `app_id_must_be_uuid` | `os.kv.*` or `os.events.emit` was called with the slug for `X-Manaurum-App-Id`. | Use the UUID from `process.env.MANAURUM_APP_ID` for those two families only. |
| 422 `manifest_validation_failed` (from the POST) | Manifest fails the v2 schema, names a reserved slug, or declares a write-named agent tool `is_write: false`. | Read `errors[]`; fix and retry. |
| 409 `version_already_published` (from the POST) | That `version` was already deployed, including a deploy that failed after its push. | Bump `version`. |
| job `failed`: `migration validation failed (…)` | Migration SQL contains destructive DDL and `migration.breaking` is not set, or a forbidden statement. | Destructive: set `migration.breaking: true` (deliberate) or rewrite as additive. Forbidden (`DO`, `COPY`, `SET`, …): rewrite; no flag unlocks it. |
| 412 `egress_not_declared` / `host_not_in_allow_list` | `os.http.fetch` with no egress hosts declared at all / to a host not in `runtime.egress_allowed_hosts`. | Add the host to the manifest, redeploy. |
| 404 `route_not_declared` | An `/api/*` path is missing from `runtime.api_routes`. Default-deny — the container never saw the request. | Declare the path. Remember `/api/x/*` does not cover `/api/x`. |
| 403 `user_context_required` | A user-scoped capability (`os.drive.*`, `os.calendar.*`) was called without `X-Manaurum-User-Context`. | Forward the header your `auth: "user"` route received. |
| 403 `capability_not_granted` | The capability is in your manifest but not in the install's grant set. | Redeploying is not enough — the tenant's install grants must be extended. |
| job `failed` at `readiness_failed` | Nothing answered on `runtime.port` (or `health_path` returned 5xx); the service was rolled back. | Read `result.log_tail`. Bind `0.0.0.0` on port 80, or set `runtime.port` to the port you actually listen on. |
| job `failed`: `docker build failed` | Image build failed. | Read `result.log_tail`. Common: `COPY` source doesn't exist, dependency install failed. |

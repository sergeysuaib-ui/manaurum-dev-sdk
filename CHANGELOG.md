# 2.7.2 — the `dev` runtime has no editor any more (MAN-1577)

### Why

Manaurum removed the App Builder — the in-browser Monaco editor at slug
`appbuilder` — from the product on 2026-08-07 (MAN-1408). Aurum Studio is now the
only builder it ships. Four files in this skill still described that editor as a
live surface, in eight places, so an agent reading them would hand a developer a
path that no longer exists.

### What changed

The `dev` runtime mode is **not** gone, and this release does not pretend it is.
`runtime.mode: dev`, the `dev_apps` / `dev_app_files` tables and the
`/api/dev/v2/dev-apps/*` routes are all still mounted in Core. What disappeared is
the only UI that drove them. So the docs now say exactly that, rather than
deleting sections that remain technically accurate:

- `SKILL.md` — `runtime.mode: dev` is described as a platform-internal prototyping
  runtime that no longer has an editor.
- `references/v2-platform.md` — the `dev` section keeps its contract details under
  a banner saying no editor ships for it and you should target `hosted`.
- `references/publishing.md` — the session-cookie publish endpoint and its
  poll surface are relabelled "dev mode"; the table now records that the route has
  had no UI client since 2026-08-07. The `mna_*` CLI path is unaffected and is the
  one to use.
- `references/capabilities-reference.md` — `capability_denied_in_dev_mode` is
  described by the manifest field that triggers it rather than by the dead product
  name, and the `KNOWN_CAPABILITIES` caveat now notes that
  `app_builder_v2_capabilities.py` is a legacy filename for a live, shared file.

Historical CHANGELOG entries are untouched.

# 2.7.1 — the skill answers to what people actually say (MAN-1453)

### Why

Everything 2.7.0 built sat behind a door that only opened for one word.

Measured on `f004843` (2.7.0), eight sentences a non-developer would open with,
each in a fresh empty directory with the plugin loaded:

| | skill invoked |
|---|---|
| "i need an app to keep track of which of my plants ive watered" | ❌ |
| "i want something to track my freelance invoices" | ❌ |
| "can you build me a little tool for logging my gym workouts" | ❌ |
| "i need a place to write down what my clients ordered" | ❌ |
| "make me something to remember my kids school stuff" | ❌ |
| "i want an app for my shop" | ❌ |
| "build me a simple tool to track who owes me money" | ❌ |
| "хочу приложение чтобы вести учёт расходов" | ❌ |

**0 of 8.** Say "manaurum" and it fired every time; describe the problem and it
never did. The agent instead offered ManAurum as option 2 of 3 and recommended a
plain standalone page — in the "I don't know" run it built a 1095-line local HTML
file styled with `data-theme`, the one pattern `design.md` prohibits.

So the interview (MAN-1435) and the stylesheet (MAN-1436) were both unreachable
by the exact first sentence they were built for. The target user cannot program;
they describe a problem and never think to name a platform.

### Changed

- **`manaurum-app`'s `description` now triggers on intent, not just on the
  product noun.** It keeps every existing trigger and adds the case that was
  missing: someone asking for an app or a tool to run part of their life or work
  without naming a technology, in any language. It also says out loud not to
  offer a standalone HTML page instead, and lists what still does **not** belong
  to this skill — work inside an existing codebase, a plain script, or a stack
  the user already chose.

After, same eight sentences, same conditions: **8 of 8**. A four-sentence control
group that must NOT match — a Python file-renaming script, a Next.js landing
page, "explain how OAuth works", and a dark-mode toggle for a React component in
the current folder — stayed at **0 of 4** before and after.

### Note for anyone editing a `description` again

Two traps cost real time here, both silent:

1. **A double quote inside an unquoted YAML scalar removes the skill from the
   list entirely.** No parse error, no warning — `manaurum-app` simply stopped
   existing while `manaurum-deploy` and `manaurum-setup` still loaded. If a skill
   vanishes, look at the frontmatter punctuation before anything else.
2. **Do not measure trigger rates with `--disallowedTools Write Edit Bash`.** An
   agent that cannot write files declines the skill, so the first run of this
   experiment showed 0 of 8 *after* the fix as well and nearly buried it. Give
   the run full tool access and kill it on a timeout instead.

# 2.7.0 — ask before you build, and ship something worth looking at (MAN-1435 / MAN-1436)

### Why

Two gaps, both measured on `origin/main` at 2.6.0, both about the same moment: what
happens when a person who cannot program says "build me an app".

**Nothing asked them anything.** Both skills opened at "copy the starter" / "write the
manifest". Read that as a missing process step and you fix the wrong thing — the person
is not withholding a spec, they *do not have one* and do not know what they are supposed
to tell you. So the agent invented the data model, the surfaces and the
`agent_capabilities` from one sentence, and the guess stayed invisible until the app
existed and was wrong.

**The design guidance was not merely absent, it contradicted the file next to it.**
`references/design.md` was 442 lines built around a two-theme world: 12 XP references,
`app.mul.*` (which does not exist in the v2 SDK — 0 hits in `manaurum-v2.mjs`), and 0
mentions of the v2 client SDK. Meanwhile `references/sdk-api.md:59` — same directory —
already said the correct thing: theme is *always* `smoothie` inside an iframe, style off
`appearance` and `accent`. The plugin shipped both instructions and let the agent pick.

Three findings worth keeping, all verified against the monorepo rather than assumed:

- **`app.onReady` / `app.onThemeChange` are live v2 API**, not v1 leftovers
  (`manaurum-v2.mjs:195,208`). The defect in `design.md` was never a dead call — it was
  *semantics*. It taught `onThemeChange(theme => body.className = theme)`. The shell
  sends `IFRAME_THEME`, a hardcoded `'smoothie'` (`IframeAppHost.tsx:127,309`), and the
  SDK passes that constant to the callback (`:126`). An app copying that snippet sets
  `class="smoothie"` forever and **never reacts to dark mode**. Only `app.mul.*` was
  genuinely dead.
- **XP cannot reach an app at all** — "the XP look stops at the window frame"
  (`IframeAppHost.tsx:124`). It is a shell easter egg for one tenant. Every XP style
  block in this plugin was code that could not execute, in v1 as well as v2.
- **The starter ignored the appearance signal entirely.** It styled off
  `prefers-color-scheme`, which tracks the *browser*. Measured: with the shell posting
  `appearance: 'dark'`, the 2.6.0 starter stayed `rgb(246,247,251)` and never set
  `data-appearance`. A user in OS dark mode got a white app in a dark desktop.

### Added

- **A discovery phase before any file is created** (MAN-1435). `Step 0` in both skills:
  one question at a time, plain language, and — the load-bearing move — **propose what
  you think the app is after two or three answers and invite correction**, because people
  correct a wrong guess far better than they specify from nothing. It is explicitly not a
  gate ("just build me a todo list" → draft the brief, confirm once, go) and it always
  terminates ("I don't know" → pick the default, record it, say so).
- **`templates/v2-starter/BRIEF.md`** — the spec, in the user's words, that they own and
  can edit. Six sections that each map to something concrete: §1 → route auth and
  visibility, §2 → screens and `runtime.api_routes`, §3 → the data model, §4 →
  `agent_capabilities`, §5 → guardrails, §6 → every guess the agent made, marked
  `(assumed)`. Verified end to end: adding one line to §4 of a real brief produced one
  `agent_capabilities` entry and one `POST /agent/<name>` handler, with §5 forcing it to
  `UPDATE` rather than `DELETE`.
- **`skills/manaurum-app/references/discovery.md`** — the question bank, the defaults for
  the uncooperative case, the brief→manifest derivation table, and **two worked
  transcripts**: a vague one-liner reaching a five-status enum and two Assistant
  capabilities without a single technical question, and an "I don't know to everything"
  run that still terminates. Transcripts because a model imitates a transcript; it skims
  a rule.
- **`templates/v2-starter/src/static/app.css`** (MAN-1436) — a real stylesheet, and the
  half that actually changes what gets built. Tokens, page shell, cards, lists and rows,
  forms, four button ranks, badges, empty states, skeletons, focus rings, mobile. It uses
  **the OS token names** (`--space-*`, `--surface-*`, `--radius-*`, `--accent`) so
  adopting the shared system later is one `<link>` and no rule has to move.
- **All eight OS accents**, copied verbatim from `globals.css`. The public
  `tokens.css` defines six — `amber` and `green` silently fall back to blue there.
- **`tests/test_static.py`** — five tests for the contract that only breaks inside the
  desktop: the stylesheet is served, `index.html` links what it ships, the handshake reply
  precedes the module bundle, appearance reaches the DOM on init *and* on change, and
  `[hidden]` is overridden. Mutation-checked: 7 of 7 deliberate breaks go red. The first
  version of this file let 2 of them through because it matched the explanatory comments
  rather than the code — the `_code()` helper and the comment in that file exist so the
  next person does not repeat it.

### Changed

- **`design.md`: 442 → 216 lines.** All XP styling and `app.mul.*` gone. What replaced it
  describes what a v2 app actually is (an isolated iframe with its own CSS), gets the
  appearance/accent contract right, and adds what was missing entirely: layout and
  composition, so an agent with correct tokens stops inventing a page shape. It now points
  at `app.css` as the artifact instead of re-dumping CSS.
- **`design.md` is no longer filed under "Legacy v1"** in either skill. It was reachable
  only from the v1 sections, so nothing on the v2 path ever read it. `manaurum-app/SKILL.md`
  now points at it and at `app.css` where an agent decides what to copy.
- **The starter follows the shell, not the browser.** `index.html` writes
  `data-appearance` / `data-accent` from `manaurum:init` and `manaurum:theme-change`, using
  `prefers-color-scheme` only as the standalone default. Measured after: shell `dark` +
  browser `light` → `rgb(23,23,26)`; shell `light` + browser `dark` → `rgb(247,247,249)`.
  Both directions, and the handshake still answers.
- **The starter's UI shows the patterns instead of describing them** — a form with a real
  empty state, a skeleton that resolves into a key/value panel, and a list of the install's
  `granted_capabilities` with badges. That list is read from the raw `manaurum:init`
  payload because the v2 SDK does not expose `granted_capabilities` (0 hits in
  `manaurum-v2.mjs`), and it is the fastest way to see why a call returns
  `403 capability_not_granted`.
- **`templates/legacy-v1/theme-aware-app.html` adapts to appearance, not to XP.** It was
  21 lines of unreachable XP CSS, `body.className = ctx.theme` (always `'smoothie'`), the
  claim "adapts to both Smoothie and XP themes automatically", and **no dark mode at all**.
  It now uses the v1 SDK's `onAppearanceChange` / `onAccentChange`, which existed all
  along. `hello-world.html` got the same fix.
- **Two factual corrections in `sdk-api.md`**: the `manaurum:theme` wire example showed a
  payload of `{"theme": "xp"}` the shell never sends, and `app.getTheme()` was documented
  as possibly returning `"xp"`.

Added in review, after running the skill from blank directories five times:

- **Template paths now carry the `<plugin>/` root marker.** `manaurum-app/SKILL.md`,
  `discovery.md` and `design.md` pointed at a bare `templates/v2-starter/…`, and in one run
  out of two the agent resolved that against the *skill* directory, got
  `File does not exist`, and silently wrote its own `app.css`, its own `BRIEF.md` and no
  tests at all — justifying the missing suite with "the reference fixture needs a real
  Postgres", which the starter disproves (24 pass with no Postgres and no Docker).
  `manaurum-setup` never had the problem because it already wrote
  `cp -r <plugin>/templates/v2-starter`. The three files now match it, and the instruction
  says to resolve the root and retry rather than fall back to writing the file.
- **The `[hidden]` guard is in `design.md` too, not only inside `app.css`.** An agent that
  writes its own stylesheet — which is correct and expected when the app is not Python —
  never sees the rule. Observed twice out of five runs: both re-derived sheets patched
  `.modal-backdrop[hidden]` by hand and without `!important`, which is exactly the
  case-by-case vigilance the global rule exists to replace.
- **`design.md` now states the stance on sidebars, tab bars and toggle switches.** All
  three had sections on `origin/main`; `app.css` deliberately ships none of them, but
  nothing said so, which read as an omission rather than a decision.
- **The two `legacy-v1` templates say what does not work.** Their `onAppearanceChange` /
  `onAccentChange` hooks are correct, but the shipped v1 SDK never fires them — its
  `manaurum:theme-change` handler aliases its own context and compares each value against
  the copy it just overwrote, so the guard is always false (**MAN-1450**). Verified against
  the live `manaurum.js`: init applies, every subsequent change is dropped. Still a strict
  improvement — before this release neither template read `ctx.appearance` at all — but the
  comment no longer promises live updates the platform does not deliver.

### Not changed

- **v1 is still supported and its SDK calls still appear in the Legacy v1 sections.** That
  is what those sections are for. `app.onReady` in a v1 example is correct.
- **`is_write` stays in the starter manifest.** It is dead at runtime (MAN-1425) and
  `v2-platform.md` already documents that precisely while telling you to declare it
  truthfully anyway. Removing it from the artifact would have contradicted deliberate
  guidance; this release leaves the position alone.
- **XP mentions in this changelog.** History is not rewritten. The remaining XP text in
  the *skills* is now exclusively "this cannot reach you, do not style for it".
- **`templates/v2-starter/` still exists.** Deleting it in favour of the CLI scaffold is
  MAN-1393 item 4 and is blocked on a CLI release, not on an opinion.
- **The shared design system is still vendored, not linked** — MAN-1401 is unresolved, the
  URL `tokens.css` documents for itself does not resolve, and a failed `<link>` has no
  graceful degradation. Token *names* match so the swap stays cheap.
- Aurum Studio. Out of scope by decision (2026-07-26): the terminal is the product here,
  and no shared core is being built.

# 2.6.0 — the artifacts teach, not the prose (MAN-1394 / MAN-1395 / MAN-1396)

### Why

An agent holding this skill imitates the **artifact** it copies far more reliably
than the paragraph it reads. 2.5.0 shipped 4,339 lines of accurate prose next to a
starter that a real app has nothing in common with: no tests, no `/agent/*` handler,
one 200-line `main.py`. So the skill said "declare `agent_capabilities`" in three
files while the only copyable app declared none, and said "split by domain" while the
only copyable app was a single module. The artifact won, every time.

Three concrete costs, all found by building an app with the 2.5.0 skill and deploying it:

- **The filename in every snippet was wrong.** `manifest_v2.json` appeared in 14 places
  across the three skills; the schema, the CLI and the platform have only ever accepted
  `manifest.json`. Copy any snippet verbatim and `manaurum app validate` cannot find your
  manifest.
- **The shipped `deploy.sh` could not deploy.** `jq --arg` took the base64 archive as a
  command-line argument — 163,840 characters for a 20-file app — and died with
  `jq: Argument list too long`. Separately its `tar` exclude list had no `.venv`, so the
  same app produced a 58 MB build context instead of 60 KB.
- **A security claim was false.** The skills stated `/agent/*` "is never reachable from
  the public URL". Skipping `api_routes` removes the *gateway*, not the network:
  `<slug>.apps.manaurum.com` is Traefik straight to the container. Verified against a live
  deploy on 2026-07-26 — an unauthenticated POST reaches the handler. An app written to
  that sentence ships an open endpoint.

### Added

- **`templates/v2-starter/` is now shaped like a real app.** `src/auth.py` (RS256
  `user_context` verification) and `src/capability.py` (the gateway client) as shared
  infrastructure; `src/main.py` and `src/agent_routes.py` as the two surfaces built on
  them. Apps grow by adding surfaces, not by growing one file — and the starter now
  demonstrates that instead of asserting it.
- **Two working `agent_capabilities`**, manifest entry through to handler. This is the
  MAN-1396 half: the *handler* side was documented nowhere, so the identity trap was
  invisible. `read_my_note` takes no input on purpose — a capability with a `user_id`
  argument lets the model read somebody else's data by passing a different one.
- **A test suite that runs offline** — `tests/conftest.py` generates a throwaway RSA
  keypair and signs its own `user_context` tokens, so JWT verification and the agent
  handlers are testable with no database, no account and no network. 19 tests, including
  every way a token can be wrong and one that fails if a user can read another's note.
  Testing had **zero** occurrences in the plugin before this release.
- **`tests/test_routes.py` covers the wiring, not just the pieces.** Unit-testing the
  verifier and unit-testing a handler both stay green when the two stop being wired
  together — and the route is then open on a public hostname. So these drive real HTTP
  through the app with `TestClient` (no database, no new dependency: `httpx` is already a
  runtime dep). Three mutations that a 13-test suite waved through now go red: making
  `note_key()` return a constant, dropping `Depends(auth_claims)` from an `/agent/*`
  handler, and dropping it from a route in `main.py`. Added in review — a starter whose
  green suite implies its security-critical lines are covered teaches the wrong lesson
  exactly where this release claims to teach the right one.
- **`skills/manaurum-app/references/reference-apps.md`** (MAN-1394) — the reference ladder.
  `shift-checklist` (22 files) as the one to read whole, `family-space-v2` (77 files) as the
  ceiling, `libi` as the testing exemplar, each with the load-bearing excerpt inlined so the
  page stands alone for a developer without the monorepo. Named paths are provenance, not
  the deliverable.
- **A testing section** in `manaurum-setup/SKILL.md`, leading with `pytest` rather than
  `docker build`, and explaining why the local `401 missing_user_context` on `/api/me` is
  the correct answer rather than a failure.

### Changed

- **`manifest_v2.json` → `manifest.json`** in all 14 places across the three skills. The
  one occurrence left in this file is history and stays.
- **`deploy.sh` and the two quickstart snippets** switched to `jq --rawfile/--slurpfile`
  (reads the payload from disk, no `ARG_MAX` ceiling) and gained
  `.venv venv __pycache__ .pytest_cache dist build` in the `tar` excludes. Fixed at all
  four sites, then run verbatim against a real project to prove it.
- **`agent_capabilities[]` in `references/v2-platform.md`** — the three-field stub is
  replaced by a full entry (description with a positive trigger, an ordering constraint
  and a negative), the handler excerpt, and the note that a valid `user_context` JWT is
  authentication, not authorization.
- **`is_write` is documented as declarative only.** The runtime does not read it for
  hosted apps: there is no such column, the deploy-time sync ignores the key, and at
  request time `dispatch == "backend"` forces `is_write=True` for *every* capability,
  readers included. So read-only capabilities take the write path and are excluded from
  cross-app insight, which filters on `not is_write`. Tracked as MAN-1425 — the skill now
  says what is true rather than what was intended.
- **`manaurum-setup/SKILL.md` starts from the working starter** instead of assembling an
  app from snippets, and says explicitly that where a snippet disagrees with
  `templates/v2-starter/`, the starter wins. Its inline `index.html` body was deleted in
  favour of pointing at the starter's; the lesson about the handshake stayed.
- Manifest examples use `"port": 8000` (matching the starter and every hosted app in
  production) instead of 80, and carry an `agent_capabilities` entry.
- **The starter no longer draws a `migrations/` directory it does not ship.** Git cannot
  track an empty directory, and the obvious fix is a trap: `migrations/` is SQL-only, so a
  `.gitkeep` sitting in it raises `BundleMigrationError: non-SQL file in migrations/` and
  **fails the deploy** — breaking the starter's one promise, that it deploys green as-is.
  The README says so instead, and § Storage already covered when to create the directory.
- **`README.md`** — the "three rules" table gained the `/agent/*` one; the quick start
  copies the starter instead of running `manaurum app init`, and says why; and the claim
  that the starter is "byte-identical to `manaurum app init` output" is retracted, because
  it is not.

### Not changed

- **`templates/legacy-v1/`** — untouched, still there for apps already on v1.
- **`templates/v2-starter/` was not deleted.** Removing it in favour of `manaurum app init`
  is MAN-1393's item 4. The CLI-side rewrite exists (MAN-1397, monorepo PR #1455, in review
  as this ships) and the two scaffolds converged on the same shape independently — but that
  rewrite is in no released wheel, and `pip install manaurum-cli` still 404s on PyPI
  (MAN-1385), so the only CLI a developer can install is `cli-v0.2.0`, built before it.
  Deleting the starter now leaves them with no working scaffold at all. Sequencing: #1455
  merges → a CLI release ships → the quick start repoints and this directory goes.
  Deferred, not dropped.
- **`marketplace.json`** carries no version field and did not get one.

# 2.5.0 — the human-facing half catches up (MAN-1365)

### Why

2.4.0 fixed `skills/**` for v2 and stopped there. The two surfaces a **person** reads
first were untouched, so the agent read correct v2 while the human read a v1 pitch:

- `README.md` described apps as "regular web pages in an iframe", sold the Test Harness
  and the XP theme, offered "paste HTML or upload ZIP" and Vercel/Netlify hosting, and
  documented a "Private → Unlisted → Public App Store" ladder that does not exist. It
  also announced itself as version 1.6.0 while the plugin shipped 2.4.0.
- `templates/` held three v1 artifacts and **no v2 starter at all**, so every app
  regenerated container boilerplate from prose.

### What changed

- **README rewritten for v2.** What a v2 app actually is (a container on
  `<slug>.apps.manaurum.com`), the capability gateway and the signed user-context header
  in a paragraph each, `visibility.mode` instead of the invented ladder, the three skills
  and when each fires, and a copy-paste quick start. The three rules that cost
  first-timers the most time — `/api/*` default-deny, `runtime.port` (never `EXPOSE`),
  and the 10-second `manaurum:ready` handshake — are a table near the top rather than
  buried in a skill.
- **`templates/v2-starter/`** — byte-identical to `manaurum app init` output. It deploys
  unchanged: serves a UI that answers the shell handshake, verifies a real RS256
  user-context JWT on `/api/me`, and does a key-value round trip through the capability
  gateway on `/api/notes`. Regenerate it with that command rather than editing it here,
  so the two distribution channels cannot drift.
- **`templates/legacy-v1/`** — the old iframe artifacts, kept only for apps already on v1.
- **The CLI is installable again.** `pip install manaurum-cli` is advertised in six places
  across the product but the package has never existed on PyPI. Until it does, the wheel
  ships as a release on this repo (`cli-v0.2.0`) and the README points at it. Verified
  end to end in a clean virtualenv: install → `manaurum app init` → `app validate`.
- **An "honest gaps" section.** No local dev loop, one-line build failures, "succeeded"
  meaning built-and-scheduled rather than serving, no cron or webhooks behind the manifest
  fields that exist for them, logs without follow, and subdomains being public knowledge
  through Certificate Transparency the moment an app first deploys.

### Not changed

`skills/**` — corrected in 2.4.0 (MAN-1330) and re-read during this work; no new factual
errors found.

# 2.4.0 — realignment with the monorepo (MAN-1330)

### Why

The skills documented several mechanisms that **do not exist in the platform**, so an
app authored strictly from this plugin could not work:

- **Its API 404s.** `runtime.api_routes` was never mentioned anywhere in the plugin. The
  gateway is default-deny on `/api/*`: an undeclared path returns `404 route_not_declared`
  and never reaches the container, so the app looks like it has a backend bug with silent
  logs.
- **Its container 502s.** The plugin taught *"the platform reads your `EXPOSE` line and
  routes Traefik to it"*. Nothing in Core parses `EXPOSE`. The upstream is
  `<swarm-service>:<port>` where `port` is `manifest.runtime.port`, default **80** — so the
  Node/FastAPI Dockerfiles we shipped (`EXPOSE 8080` / `EXPOSE 8000`, no `runtime.port`)
  produced a green deploy that 502s on every request.
- **It is unusable as a desktop window.** `manaurum:ready` was never taught for v2 at all.
  The shell hard-enforces the handshake for both runtimes (`READY_TIMEOUT_MS = 10_000`) and
  covers the app with "App is not responding" when it is missed — and the standalone
  `<slug>.apps.manaurum.com` URL works fine without it, so the omission is invisible until
  someone opens the app on the desktop. This is not hypothetical: MAN-1321 shipped exactly
  that bug in the first-party app Libi.

On top of that, the deploy flow was taught as synchronous (`{"status": "succeeded"}` from
the POST) when it is 202-plus-poll, and the runtime credential was taught as a
developer-token env var (`MANAURUM_V2_TOKEN`) that the platform has never injected.

**`permissions[]` is correct and was deliberately kept.** An audit during this work flagged
the `permissions[]` documentation added in 2.3.0 as an error; **that flag was itself wrong**.
MAN-1316 added `permissions` to `manifest_v2.schema.json` (enum `["microphone"]`, drives the
iframe `allow=` Permissions-Policy delegation) and 2.3.0 documents it accurately. Do not
"re-fix" it.

### Fixed — mechanisms that did not exist

- **`EXPOSE` → `runtime.port`.** Removed the "platform reads your `EXPOSE`" claim from
  `manaurum-app/SKILL.md` and `manaurum-setup/SKILL.md`. `EXPOSE` is documentation only;
  `runtime.port` (default 80) is the sole input, and the three numbers that must agree are
  `runtime.port`, your `CMD`'s port, and `EXPOSE`. Added the `127.0.0.1`-vs-`0.0.0.0` trap,
  and made the starter Dockerfiles declare a matching `runtime.port`.
- **`MANAURUM_V2_TOKEN` → `MANAURUM_RUNTIME_TOKEN` + `MANAURUM_CORE_URL`.** The container
  never carries a developer token: the platform injects a per-(tenant, app) `mna_*` runtime
  credential, minted fresh on every deploy. The call contract in
  `capabilities-reference.md` and the worked examples in `manaurum-app/SKILL.md` and
  `manaurum-setup/SKILL.md` now build the URL from `${MANAURUM_CORE_URL}` and authenticate
  with `${MANAURUM_RUNTIME_TOKEN}`.
- **`runtime.env_secrets` deleted** — it is not in the schema and Core never reads it. It
  appeared to work only because the `runtime` sub-object is not strict, so it validated and
  did nothing.
- **`MANAURUM_BROKER_URL` deleted** — never injected (MAN-163 removed it because the shared
  broker DSN had grants on every app's schema). Every recipe built on it is gone.
- **`migrate_command` is documented as dead.** It is in the schema, but Core has **no call
  site** for it — an app whose schema depends on it deploys green with no tables. The
  migration path is `migrations/*.sql`, run once per (app, tenant).
- **Deploy is asynchronous.** `POST /api/dev/v2/deploy` always returns **202** with
  `{"deploy_job_id", "status": "pending"}` — never `succeeded`. Replaced the "sync response,
  ~7–10s" text in `manaurum-app/SKILL.md` and `manaurum-deploy/SKILL.md`, and rewrote the
  `deploy.sh` template around a real polling loop. Added: only `401` / `403
  app_id_out_of_scope` / `422 invalid_archive_b64` fail synchronously; manifest, migration
  and Docker failures surface as `status: "failed"` on the job.
- **`succeeded` ≠ serving.** There is no readiness probe in the hosted path, so a
  crash-looping or wrong-port container still produces a green job. Every deploy path now
  ends in an explicit `/healthz` check.
- **`runtime.byo_endpoint_url` → `runtime.entrypoint`.** The old spelling appears nowhere in
  Core and (non-strict sub-object again) validates cleanly while leaving a BYO app with no
  URL.
- **Root `description` removed from the v2 example manifest** in `v2-platform.md` — the v2
  root is `additionalProperties: false`, so it is a hard rejection. It belongs in
  `metadata.description`; likewise `icon` → `frontend.icon`, `category` → `metadata.category`.
- **`os.tenant_config.get` re-documented against the handler.** It does not read
  `tenants.features` or install-time `tenant_config`; it reads `tenants.app_builder_config`
  through a Pydantic model with one field (`prompt_extension`) and `extra: "ignore"`, so
  every other key returns `null` and `app_id` is ignored. Flagged as unreliable.
- **v1 status codes corrected** in `publishing.md`: version reuse is `409
  rejected_version_conflict` (not 400); an over-50 MB bundle is `413
  rejected_bundle_too_large`.

### Added

- **`runtime.api_routes`** — a full section in `manaurum-app/SKILL.md`, the field reference
  in `v2-platform.md` § 2, the scaffold in `manaurum-setup/SKILL.md`, the `app.fetch` note in
  `sdk-api.md`, and a triage row in `manaurum-deploy/SKILL.md`. Covers default-deny, `auth:
  "user"` vs `"anonymous"`, the 60s `user_context` JWT injected as `X-Manaurum-User-Context`,
  `streaming: true`, precedence, that there is **no `method` field**, and that `/api/x/*` does
  not match the bare `/api/x`.
- **The `manaurum:ready` handshake.** New "Step 2.5 (MANDATORY)" in `manaurum-app/SKILL.md`,
  a full contract section in `sdk-api.md` (the real `manaurum:init` payload, the 10s timeout,
  the three origin/source/type checks the shell applies, the belt-and-braces inline-listener +
  post-mount pattern that shipped for Libi in MAN-1321), and the listener baked into the
  starter `index.html` in `manaurum-setup/SKILL.md`.
- **`sdk-api.md` now covers v2.** New runtime-selector table at the top, a
  "Platform v2 — frontend SDK (`manaurum-v2.mjs`)" section (`init()`, `onReady` /
  `onThemeChange` / `onDeviceChange` / `onAuthFailure`, context getters, `app.fetch` with its
  opt-in `retry` semantics, `app.pickFromDrive()`, and what the SDK deliberately does *not*
  do), the `V2_ALLOWED_MESSAGES` framing list, and the v1 bridge verbs a v2 frame is refused.
  Everything below the new "Legacy v1" divider is explicitly marked v1-only.
- **Migrations documented end-to-end** (`v2-platform.md` § 7, plus summaries in the setup and
  deploy skills): `migrations/*.sql`, flat and SQL-only, run once per (app, tenant) in lexical
  order, sha256-pinned; and the DDL validator's **four** classes —
  `additive` / `neutral` pass, `destructive` needs `migration.breaking: true`, `forbidden`
  (`DO $$`, `COPY`, `CREATE EXTENSION`, `BEGIN`/`COMMIT`, any `SET`, role/database DDL) is
  never allowed — with **default-deny** as the master rule. Includes the context-sensitive
  additives (`CREATE INDEX` / `SET NOT NULL` on a fresh object) and the real-world `DO $$`
  rejection that hit Libi (MAN-1327).
- **Runtime DB reality**: `DATABASE_URL` is a per-(app, tenant) `appusr_*` login,
  `NOSUPERUSER NOBYPASSRLS`, **no CREATE** — so `CREATE TABLE IF NOT EXISTS` on boot dies with
  `permission denied for schema app_<slug>__<hex>`. Plus `MANAURUM_TARGET_SCHEMA` and
  `CORE_USER_CONTEXT_PUBLIC_KEY_PEM` in every env-var table.
- **`data` modes.** `{"none": true}` for an app with no Postgres of its own — omitting the
  block selects managed mode and provisions a schema + role. Added to the setup scaffold and
  both manifest references.
- **The rest of the v2 root surface** in `v2-platform.md`: the complete 23-key list plus
  `platforms`, `provides`, `consumes`, `optional_capabilities`, `offline`, `tenant_config`,
  and `agent_capabilities[]` (with the server-to-server `POST /agent/<name>` dispatch, which
  bypasses `runtime.api_routes`). `webhooks` and `schedules` are marked shape-validated only —
  Core does not invoke them in v2.x.
- **`os.calendar.list_events` / `os.calendar.create_event`** in `capabilities-reference.md`
  (idempotent upsert via `source_ref`, overlap-not-containment range semantics, no pagination),
  and a pre-dispatch gate table covering `capability_not_granted`, `tenant_mismatch`,
  `user_context_required`, `invalid_user_context`, `capability_denied_in_dev_mode`. Grant
  enforcement is unconditional — an install with an **empty** grant list denies everything, so
  adding a capability and redeploying is not sufficient.
- **A "What will bite you" section** in `manaurum-app/SKILL.md`, for the failures that only
  appear inside the desktop: no `alert()` / `confirm()` / `prompt()` (the sandbox is
  `allow-scripts allow-forms allow-same-origin`; `allow-modals` is never emitted), Core
  force-assigns `frame-ancestors` and strips `X-Frame-Options` on `/apps/*` (but leaves the
  rest of your CSP), a **relative** `frontend.icon` paints as literal text, unknown `runtime`
  keys validate and are ignored, and `.env*` is **not** excluded by the CLI packager.
- **`publishing.md` rewritten** around a v2 section: publish-vs-deploy (App Builder validates
  the manifest synchronously with `422`; the CLI validates it inside the job), the poll
  surfaces, `experiment.platform_v2_hosted_runtime`, the three icon rules including the Dev Hub
  route's 8-character limit, and the listing-edit/manifest overwrite trap. The v1 tenant
  catalog is retained below, demoted and labelled legacy.
- **`manaurum-deploy/SKILL.md`**: the NDJSON `/stream` progress endpoint, `version_label` as a
  required rollback argument (and rollback being async too), the per-(tenant, app) bare-git
  history behind `fetch-source` — with the warning that a secret in the tar is permanent even
  after the tarball window prunes — and a "failures you'll actually hit" table keyed by symptom.
- **`manifest-spec.md` v1-only banner** with a v1→v2 field-mapping table, and an explicit note
  that `permissions` exists in both versions and means different things.
- **A maintenance note** in `capabilities-reference.md`: the registry under
  `backend/app/services/capabilities/` is the source of truth, the checklist is
  `docs/standards/ADDING_A_V2_CAPABILITY.md` § 9, and there is **no** automated parity check
  between the code and this plugin.

### Changed

- **`egress_allowed_hosts`** now documents the enforcement point (copied onto the version row,
  read by the `os.http.fetch` handler) *and* flags the live monorepo bug where declared hosts
  are written into the container's `/etc/hosts` as `0.0.0.0 <host>` — the inverse of an
  allow-list. Guidance: route all external HTTP through `os.http.fetch` and do not build on
  either reading of raw container egress until it is resolved.
- **The `runtime` sub-object's non-strictness is described, not advocated.** It is why
  `port` / `egress_allowed_hosts` work at all and why `"prot": 8000` deploys green and 502s.
  Whether it *should* be strict is called out as an open question, not a recommendation.
- **Redeploying the same `(app_id, version)` is no longer described as a DB no-op** — the
  pipeline inserts another `v2_app_versions` row every time; it is idempotent only for the
  running service.
- **Scaffold layout**: `src/` plus a narrow `COPY src/`, a starter `.dockerignore`, and
  `.env.manaurum` documented as deploy-time-only. `manaurum-app` and `manaurum-setup` name
  that credential `MANAURUM_TOKEN`; `manaurum-deploy/SKILL.md` still spells the same
  deploy-time variable `MANAURUM_V2_TOKEN`, which is cosmetic but not yet unified.

# 2.3.0 — 2026-07-19

- **Voice-app platform surfaces (MAN-1316, docs work item MAN-1323)** —
  the skill can now build a working voice app end-to-end:
  - `os.ai.transcribe` documented (capabilities-reference + the SKILL.md
    capability table): BYOK speech-to-text on the tenant's **OpenAI** key,
    ≤ 25 MB decoded audio, default model `gpt-4o-transcribe`, real error
    codes verified against the handlers (`invalid_audio_base64`,
    `audio_too_large`, 412 `integration_not_configured`, and the fact that
    every upstream failure is 502 `upstream_error:openai` — never 504).
  - Manifest `permissions[]` (browser Permissions-Policy delegation, enum
    `["microphone"]`) added to the manaurum-setup scaffold + validation
    rules, the manaurum-app manifest steps, and the v2-platform.md § 1
    field reference — a scaffolded mic app no longer ships broken inside
    the shell iframe.
  - `os.http.fetch` section REWRITTEN against the actual handler: the old
    text taught a text-only `body` (which corrupts binary payloads) and a
    nonexistent `timeout_seconds` field. Now documents `body_base64` /
    `response_format: "base64"` (~5 MB each way), `timeout_ms`, the real
    output shape (`content_length`, `elapsed_ms`), and the real error
    codes (`unsafe_url`, `host_not_in_allow_list`,
    `upstream_response_too_large`, …).
- Version note: the 2.2.0 changelog entry below shipped on 2026-06-24 but
  `plugin.json` was never bumped past 2.1.0; this release corrects the
  drift by moving straight to 2.3.0.

# 2.2.0 — 2026-06-24

- **Source retention (MAN-990 / MAN-993)**: the deploy skill now documents
  that the platform retains each version's build context (your uploaded tar)
  in object storage instead of discarding it — your source is no longer
  single-copy on your machine, and a version stays rebuildable after its
  image is pruned. Added the `GET /apps/{app_id}/versions/{version}/source`
  signed-download route, the `has_source` flag on the versions list, the
  rolling-window retention policy, and the `manaurum app fetch-source` /
  DevHub "Download source" surfaces.

# 2.1.0 — 2026-06-10

- **Drive bridge (MAN-608)**: documented the `os.drive.*` capability family
  (stage/publish "Save to Files", list/read/write in granted folders), the
  `drive.{slug}.file.*` change events, and the `app.pickFromDrive()` SDK
  helper (manaurum-v2.mjs 2.1.0). Reframed `os.files.*` as per-app private
  scratch + documented the new `os.files.list`.

# Changelog

## 2.0.0 (2026-05-07) — Platform v2 is the default flow

This is a **major** release. The skill defaults flip: every new app is now scaffolded, taught, and deployed as a Platform v2 containerized hosted app. The v1 (iframe + `manaurum.js` + `mnu_*` token + `/api/dev/apps/deploy`) flow is preserved as a legacy section in each skill, only used when an existing v1 app needs maintenance.

### Why

Platform v2 shipped to production on 2026-05-06/07. New apps have access to the capability gateway (KV / files / AI / OCR / notifications / events / RPC / HTTP egress / audit), per-tenant isolation via FORCE-RLS on every Core table, and a one-command deploy that yields `https://<slug>.apps.manaurum.com` with TLS in ~7–10 seconds. There is no Core PR for any of this. v1 cannot match those primitives — every v1 app is a static iframe with permission-gated `postMessage` calls, and per-tenant deploys are independent.

The team's working assumption from now on: **all new app work goes on v2**. v1 is feature-frozen for existing apps. This skill release reflects that.

### Added

- **`manaurum-app/SKILL.md`** rewritten with v2 as the primary flow. Teaches: container model, env vars, capability gateway contract, manifest v2 minimum, common rejection codes, what NOT to do. Legacy v1 path preserved as a brief section at the bottom with pointers to the v1 references.
- **`manaurum-deploy/SKILL.md`** rewritten. v2 flow first (`POST /api/dev/v2/deploy`, build context as base64 tarball, sync response shape, rollback, version listing). Legacy v1 deploy preserved.
- **`manaurum-setup/SKILL.md`** rewritten. v2 project scaffolding first (`Dockerfile` + `manifest_v2.json` + `.env.manaurum` with `mna_*` token). v1 scaffolding preserved.
- **`references/v2-platform.md`** — long-form companion. Manifest field reference, runtime modes, capability contract, token issuance/revocation, deploy lifecycle (build → push → swarm → traefik), rollback, migrations + dedicated app schemas, visibility + App Store v2.
- **`references/capabilities-reference.md`** — input/output reference for every capability shipped in v2: `os.kv.*`, `os.tenant_config.get`, `os.secrets.*`, `os.files.*`, `os.ai.*`, `os.ocr.extract`, `os.notifications.send_to_user`, `os.events.emit`, `os.http.fetch`, `os.compliance.audit_query`, `os.apps.call`, `os.apps.bulk_export`.

### Changed

- Plugin `description` updated to mention v2-as-default + legacy v1 support.
- Banner added at the top of all three SKILL files explaining "v2 is the new default" and how to decide between v2 and v1 for a given task.

### Preserved (no behavior change)

- `references/manifest-spec.md` — v1 manifest schema reference. Still authoritative for v1 apps.
- `references/sdk-api.md` — v1 SDK API (`storage.*`, `files.*`, `db.*`, `ai.*`, `mul.*`, etc.). Still authoritative for v1 apps.
- `references/design.md` — Smoothie + XP themes for v1 iframe apps.
- `references/publishing.md` — App Store v1 submission flow.

### Tokens — `mna_*` vs `mnu_*` vs `mdev_*`

| Format | What it's for | Endpoint |
|---|---|---|
| `mna_*` | **v2 default**. Capability gateway + hosted-runtime deploy. | `/api/capability/<name>`, `/api/dev/v2/deploy`. |
| `mnu_*` | Legacy v1 deploy. | `/api/dev/apps/deploy`. |
| `mdev_*` | Legacy App Builder (deprecated; migrated to `mna_*` 2026-05-07). | removed. |

The three are NOT interchangeable; using one against the other's endpoint returns 401.

### Migration path for skill consumers

If you have a Claude Code instance with this plugin installed at v1.15 and you upgrade to v2.0:

- Existing v1 apps continue to work — v1 deploy endpoints + tokens are unchanged on the platform side.
- New `/manaurum-app`, `/manaurum-deploy`, `/manaurum-setup` invocations now teach v2 by default. To explicitly target v1, ask: "scaffold a v1 (legacy iframe) app".
- The `manaurum.js` SDK is unchanged. Static URL `https://manaurum.com/sdk/manaurum.js` continues to serve.

### Reference

- Manaurum PRs that shipped v2 to prod: #418 (capability gateway core), #420 (`os.files.*`), #422 (`os.tenant_config` + `os.secrets`), #425 (`os.ai.*`), #429 (`os.ocr.*`), #430 (`os.events.emit`), #431 (`os.compliance.audit_query`), #432 (`os.apps.call`), #439 (R-4 hosted runtime backbone), #450 (DevHub `mna_*` token UI), #458 (R-4 production wiring — registry + swarm + traefik), and hot-fixes #451, #453, #454, #455, #456, #459.
- First v2-deployed app on prod: `https://v2-smoke.apps.manaurum.com` (2026-05-07, deployed via `POST /api/dev/v2/deploy` from cold start in ~8s).

---

## 1.15.0 (2026-04-30) — F1.5 evolution — `renamed_from` + dedicated `include`

### Added

- **`renamed_from` field-level hint** documented in `manifest-spec.md`. Set `"renamed_from": "<old_name>"` on a dedicated field and the diff engine emits `ALTER TABLE RENAME COLUMN` instead of the default DROP+ADD on next deploy. Additive — no data loss. Drop the hint on the deploy after the rename. Validator R9 rejects shared-only use, self-rename, and source-name-still-exists collisions.
- **R9 row** in the cross-field rules table.
- **`include` for dedicated entities** documented in `sdk-api.md`. The shared-storage `include` had a convention-based FK lookup (child must have `<parent>_id` field); dedicated uses the explicit `references` declaration. Single indexed `IN(...)` query per child type — no N+1. Caps unchanged: 4 includes max, 100 children per parent.

### Notes

- Pure-documentation release. Backend changes shipped in Manaurum PR #341 (merged + deployed 2026-04-30). Runtime API and SDK build unchanged — same `app.db.list('parent', { include: [...] })` works against either tier.

## 1.14.0 (2026-04-30) — F1.5 hardening — R8 quotas + destructive add-NOT-NULL

### Added

- **R8 row** in the cross-field rules table (`manifest-spec.md`). Per-app quotas now enforced by the validator: max **50** entities per app, max **100** fields per entity, max **20** compound indexes per entity. Generous; you should not hit these in a real app — the point is to surface a clear early reject if a manifest is accidentally ballooning (codegen bug, abuse).

### Changed

- **Additive vs destructive table** in `manifest-spec.md` — adding a `required: true` field to an existing entity is now classified as **destructive** by the diff engine. Previously it would slip through as additive and PG would reject the ALTER on populated tables with a generic error. Now the deploy returns a clean `rejected_destructive_change` with a description pointing at the safe two-step pattern (add as optional → backfill → tighten to required), or the dev passes `allow_destructive=true` to make the intent explicit.

### Notes

- Pure-documentation release — runtime API and SDK build unchanged. Companion to Manaurum PR #339 (validator + diff engine + telemetry).

## 1.13.0 (2026-04-30) — graduated storage (`storage: "dedicated"`)

### Added

- **Dedicated storage tier documented.** New "Dedicated storage" section in `manaurum-app/references/manifest-spec.md`: when to use it (>10k rows / per-tenant `UNIQUE` / FKs / compound indexes), full example, the field-level extras (`unique`, `references`), the entity-level `indexes[]` array, the R1–R7 cross-field rules, additive vs destructive change classification, and the "runtime is the same" reminder.
- **SKILL.md updated** so the Database quick overview surfaces both tiers (shared = EAV-pivot, default; dedicated = real PG table). Validation rules table updated — `entities[].storage` is no longer marked "only `shared`". The same `app.db.create / get / list / update / delete` works against either tier; the platform routes behind the unchanged interface.

### Why this matters

Until now `storage: "dedicated"` was reserved-but-rejected. Apps that grew past EAV-comfortable size had to either accept slow EAV reads or ask the platform team for an Alembic migration + Core PR. With the F1.5 graduated-storage path live (Manaurum PR #328 merged + deployed on prod 2026-04-30), an external developer writes one word in the manifest and gets a real table — real columns, real indexes, real FKs, real `UNIQUE` — auto-generated and migrated by the deploy pipeline. The boundary "go to Core via PR" moves from "I need one JOIN or index" up to "I need shell-level intervention".

### Notes

- Pure-documentation release — no template change. The runtime API and SDK build are unchanged.
- Storage tier is a one-way decision per entity. Plan before first deploy: changing `storage` between `shared` and `dedicated` after deploy is rejected as a destructive transition.
- (Plumbing only: 1.12.0 shipped the Component Library docs but missed the `plugin.json` version bump — this release lands at 1.13.0 to keep the cache directory layout monotonic.)

## 1.12.0 (2026-04-30) — manaurumOS Component Library

### Added

- **`manaurum.mul.*` documented end-to-end.** New "Component Library (MUL)" section in `manaurum-app/references/sdk-api.md` covers `mul.list()`, `mul.search(query, filters?)`, `mul.get(id)` — thin same-origin wrappers over the public read-only `/api/library/*` endpoints. Includes wire format, build-time vs runtime guidance, and the "no permission required" note (the library is curated and unauthenticated).
- **`SKILL.md` quick overview** updated to surface the library as a first-class building block. Step 2 (design) now nudges devs to browse the catalogue before drawing from scratch.
- **`design.md`** opens with a "don't design from scratch when you can borrow" pointer to the library.

### Notes

- Underlying surface ships in PRs #325 (HTTP API + catalogue UI at `/library`, merged), #326 (SDK v1.9.0 helpers, merged), #327 (App Builder catalogue injection under `experiment.app_builder_uses_library`, merged).
- The library is curated, public, and read-only. No tenant scoping, no auth headers — same-origin fetch is enough. Iframe apps with strict CSP `connect-src` should bake chosen components into the bundle at build time rather than fetching at runtime.
- Pure-documentation release — no template change.

## 1.11.0 (2026-04-28) — db.batch (atomic multi-write)

### Added

- **`manaurum.db.batch(ops)`** (Phase 3 slice 3.1). Run multiple writes in one transaction — all-or-nothing.
  - `ops` is an array of up to **50** entries, each `{op: 'create'|'update'|'delete', entity_type, record_id?, data?}`.
  - Single tenant-bound DB session, single `commit()` at the end. Any failure rolls the whole batch back.
  - Errors include `at: <index>` so the app can point at the failing op precisely; status code matches the underlying single-op error (400 / 404 / 405 / 422).
  - SDK build: **v1.8.0**.
  - Documented in `references/sdk-api.md` → "Database API" → `db.batch` with op-shape table, atomicity model, error shape, and wire format.

### Use cases

Receptions Confirm (status flip + N stock_movement inserts), bulk import, multi-step status transitions, anything where a partial commit would corrupt an app-level invariant.

### Notes

- Forward-additive — existing single-op SDK calls are unchanged.
- Larger workloads must chunk client-side; chunks are atomic individually but not collectively.

## 1.10.0 (2026-04-28) — db.list child-fetch via include

### Added

- **`db.list` `include` option** (Phase 2 slice 2.4). Hydrate each parent record with its children in one round-trip:
  - `include: ['<child_entity>', ...]` — array of distinct child entity names, max **4** per call.
  - Convention-based FK: the child entity must declare `<parent_entity>_id` UUID with `indexed: true` in its manifest.
  - Up to **100 children per parent** (sorted by `created_at` asc); extras dropped silently for v1.
  - Implementation is N+1 (one child query per parent per include); promote to JOIN once we have planner data.
  - Nested includes are not supported — hydrated child records always have `includes: null`.
  - SDK build: **v1.7.0**.
  - Documented in `references/sdk-api.md` → "Database API" with example, rules, and new errors (`InvalidIncludeError` 422, `include_must_be_json` / `include_must_be_array` 400).

### Notes

- Forward-additive — `db.list` calls without `include` keep working unchanged.
- Phase 2 of the SDK roadmap is now fully shipped: 2.1 (db.list operators) + 2.2 (entity immutability) + 2.3 (db.aggregate) + 2.4 (child-fetch).

## 1.9.0 (2026-04-28) — db.aggregate

### Added

- **`manaurum.db.aggregate(entity, options)`** (Phase 2 slice 2.3). Single-round-trip GROUP BY for dashboards.
  - `metrics`: list (max 8) of `COUNT(*)` / `SUM(<field>)` / `AVG(<field>)`. Numeric metric fields must be `indexed: true` and `integer`/`decimal`.
  - `group_by`: any `indexed: true` field.
  - `where`: same operator grammar as `db.list` (slice 2.1).
  - Hard cap of 1000 distinct groups — `422 AggregateCardinalityExceeded` on overflow.
  - Decimal metric values come back as JSON strings (Decimal-safe); UUID/timestamp keys also stringified. SDK build: **v1.6.0**.
  - Documented in `references/sdk-api.md` → "Database API" with response shape, error table, and wire format. Errors: `InvalidMetricError`, `AggregateCardinalityExceeded`, `metrics_must_be_json`, `metrics_must_be_array`.

### Notes

- Forward-additive — existing `db.list` / `db.create` / etc. unchanged.
- `MIN`/`MAX` and `COUNT(field)` deferred. Once we have planner data on real datasets, MIN/MAX are the next likely additions.

## 1.8.0 (2026-04-28) — db.list filter operators + entity immutability flags

### Added

- **Range / IN filters on `db.list`** (Phase 2 slice 2.1). The `where` option in `manaurum.db.list(entity, { where })` now accepts structured operators on indexed fields:
  - Scalar value = equality (back-compat, e.g. `{ status: 'open' }`).
  - Operator dict = `{ op: value, ... }` with operators `eq`, `gt`, `gte`, `lt`, `lte`, `in`. Multiple ops on one field share a single JOIN, so `{ created: { gte: '2026-04-01', lt: '2026-05-01' } }` runs as one range predicate.
  - `in` takes a non-empty list (max 100 items).
  - Filtered fields must still be `indexed: true` — same rule as `sort_by`.
  - Wire format: `GET /api/app-data/{slug}/{entity}?where=<URL-encoded JSON>` — the SDK and bridge handle the encoding for you.
  - New error codes: `422 FilterOperatorError`, `422 IndexValueCoercionError`, `400 where_must_be_json`, `400 where_must_be_object`. All documented in `references/sdk-api.md` → "Errors".
- **Entity immutability flags** (Phase 2 slice 2.2). Manifest entities can declare append-only / non-deletable semantics enforced at the storage layer:
  - `"immutable": true` — every UPDATE on records of this entity is rejected with `405 EntityImmutable`.
  - `"no_soft_delete": true` — every soft-delete is rejected with `405 EntityNotSoftDeletable`.
  - Both default to `false`; combine them for a strict append-only journal (e.g. Receptions `stock_movement`).
  - Documented in `references/manifest-spec.md` → "Entities" with a `stock_movement` example.

### Notes

- Both changes are forward-additive. Existing manifests and `db.list` callers keep working unchanged.
- `db.list` with operators: the SDK build is **v1.5.0** (bump from v1.4.0). The platform's bundled SDK is updated automatically on deploy; tenant apps can import either version.

## 1.7.0 (2026-04-28) — runtime AI API

### Added

- **`ai.use` manifest permission.** New entry in the v1 permissions enum (`manifest-spec.md` → "Permissions enum (v1)"). Declare it if your app calls `manaurum.ai.complete` or `.vision`. v1 runtime doesn't enforce it (yet) — declaration is for transparency at install time and forward compatibility when per-tier limits arrive. Workspace admin's gate stays at Settings → Agents (`mode='disabled'` → `AI_DISABLED`).
- **`manaurum.ai.*` runtime API documented end-to-end.** New "AI API" section in `references/sdk-api.md` covers:
  - `app.ai.complete({ prompt, system? })` — text completion.
  - `app.ai.vision({ prompt, image, system? })` — image+prompt completion. `image` accepts `{file_id}` (resolved server-side from the app's `stored_files`) or `{data_url}` (inline base64).
  - Wire format: `manaurum:ai-complete` / `manaurum:ai-vision` postMessage verbs → `POST /api/app-ai/{slug}/complete` and `/vision`.
  - Error codes: `AI_NOT_CONFIGURED`, `AI_DISABLED`, `VISION_UNSUPPORTED`, `IMAGE_INVALID`, `IMAGE_MIME_UNSUPPORTED`, `NOT_FOUND`, `TIMEOUT (90s)`.
  - Vision provider support in v1: openai (gpt-4o family), openrouter, anthropic (claude-3 family), deepseek, glm. Gemini rejects with `VISION_UNSUPPORTED`.
- **`SKILL.md` quick-overview updated** to surface `app.ai.*` as a first-class capability alongside `db.*`.

### Notes

- The iframe **never** sees the LLM API key. The platform resolves the workspace's configured provider+model from Settings → Agents and writes per-app `llm_token_usage` rows attributed to the calling `application_id` so workspace admins see per-app spend.
- No manifest permission required in v1; the gate lives in Settings → Agents (a workspace admin can disable AI for a specific app, surfacing as `AI_DISABLED`). A formal `ai.use` manifest permission is on the roadmap and will be additive.

## 1.6.0 (2026-04-27) — runtime Database API

### Added

- **`manaurum.db.*` runtime API documented end-to-end.** New "Database API" section in `references/sdk-api.md` covers `create`, `get`, `list` (with pagination + indexed sort), `update` (full replace), and `delete` (soft). Includes wire format (postMessage type → HTTP route), error table mapping `422 EntityTypeNotDeclared`, `404 record_not_found`, `422 FieldNotIndexedError`, etc.
- **Manifest ↔ runtime bridge documented** in `references/manifest-spec.md`. Explains that declaring `entities[]` at deploy time is what enables `manaurum.db.*` calls at runtime, with a worked example showing why undeclared types and unindexed sort fields fail.
- **`SKILL.md` quick-overview updated** to make `db.*` the first-class persistence path; `storage.*` / `files.*` / `collections.*` demoted to a single "legacy runtime APIs" line.

### Changed

- The "Quick overview (v1.5 SDK)" bullet pair in `manaurum-app/SKILL.md` now leads with the manifest-gated `db.*` API.

### Note

This release is purely documentation — the underlying runtime has been live since W4.3 (`backend/app/routes/app_data.py` + the `manaurum.db.*` block in `frontend/public/sdk/manaurum.js`). No backend or SDK shipping change.

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

# 3.18.0 - CLI 0.3.1, and Core's 2026-10-04 merges ahead of their deploy: the SDK's language, speech, the team list, no dev runtime

Summary: The guide installs command-line tool 0.3.1 and describes what ManAurum merged on 4 October before it goes live: speaking aloud, a list of your team, and the person's language in the browser.

### Why

Several things changed on the platform side, and the SDK either still described each one
as it was before or did not mention it:

* **CLI 0.3.1 is published** ([cli-v0.3.1](https://github.com/sergeysuaib-ui/manaurum-dev-sdk/releases/tag/cli-v0.3.1)).
  0.3.0 refused `auth: "optional"` and `auth: "people"` routes in `app validate` and in the
  deploy preflight, so `v2-platform.md` told people to deploy an `optional` route with
  `--skip-preflight`. 0.3.1 accepts both. It also refuses an `app_id` the deploy would
  refuse: `app init` before it writes anything, `app validate` and the preflight before the
  build, instead of a `422` after the upload (`app_id_error`, `manaurum_cli/manifest.py`).
  The README still installed the 0.3.0 wheel.
* **`manaurum-v2.mjs` 2.5.0** (Core sergeysuaib-ui/manaurum#2379, merged 2026-10-04) hands
  the app the person's language: `app.locale` / `app.dir` and the same fields on the
  `onReady` context, from `manaurum:init`, and `app.onLocaleChange(cb)` for
  `manaurum:locale-change`. Every `on…` registration, `onReady` included, now returns a
  function that unregisters the callback. The same PR corrected the SDK's own `fetch()`
  docblock, which said an absolute URL is subject to `egress_allowed_hosts`: it is a plain
  browser request Core never sees. `sdk-api.md` still said the SDK drops the language.
* **`manaurum-v2.mjs` 2.4.0** (Core sergeysuaib-ui/manaurum#2318, MAN-2561, merged
  2026-10-04) checks who sends `manaurum:init`: only `window.parent` on a shell origin, then
  that pinned window alone, and it exports `trustedShellOrigins`. The pages said the SDK
  does not check the sender and exports two names, as if 2.3.0 were the SDK.
* **The dev runtime is deleted** (Core sergeysuaib-ui/manaurum#2296, MAN-1423):
  `/api/dev/v2/dev-apps`, the Monaco dev mode, the capability gateway's dev-mode allow-list
  and the `capability_denied_in_dev_mode` error. A v2 app has two runtime modes, `hosted` and
  `byo`; `dev` stays in the schema enum but is retired and not a separate runtime any more.
  Four pages still described the mode, one of them as a second publish endpoint.
* **`os.ai.speak`** (Core sergeysuaib-ui/manaurum#2382, MAN-2727 / MAN-3256, merged
  2026-10-04): text or Markdown in, the whole MP3 back as base64, five voices, at most
  4,000 characters spoken per call. The same PR changed who pays for `os.ai.transcribe`:
  it is no longer the tenant's own key only, but the tenant's OpenAI integration, else
  Manaurum's metered voice key inside the shared AI spending limits (`429 ai_spend_cap`),
  and both voice capabilities honour AI Off. The reference called transcription BYOK and
  said it ignores `X-Manaurum-Workspace-Id`.
* **`os.directory.list_users`** (Core sergeysuaib-ui/manaurum#2112, MAN-2519): `{}` in, the
  people on the app's team out, for assignee and recipient pickers. Until now an app knew
  that someone acted (a user id) and never who.

### What changed

* **CLI.** README installs the `cli-v0.3.1` wheel and says to use 0.3.1 or later, because
  0.3.0 refuses `optional` and `people` routes; its paragraph on `manaurum app init` no
  longer reads as if a word were missing. `v2-platform.md` drops the `--skip-preflight`
  workaround and states 0.3.1 as the minimum. `scripts/open-claims.txt`: the MAN-3235 line
  goes (no page says the published CLI refuses `optional` any more), and the MAN-1385 line
  names the cli-v0.3.1 wheel, re-checked 2026-10-04 (PyPI still answers `404` for
  `manaurum-cli`). `check_app.py`'s docstring says cli-v0.3.1 has the `CONCURRENTLY` rule.
* **The `app_id` rule, wherever `app_id` is described** (`v2-platform.md`'s field table,
  `SKILL.md` Step 1, `manaurum-setup`, the `manaurum-deploy` refusal table): 3–40
  characters of lowercase letters, digits and hyphens, starting with a letter and ending
  with a letter or digit; not shaped like a UUID; not a reserved platform name; not under
  the `draft-` prefix, which is Aurum Studio's private drafts. The deploy refuses the prefix
  first, with `422 slug_reserved` (`owner_deploy_slug`,
  `backend/app/services/v2_apps/owner_deploy.py`), and the refusal table gains that row.
* **`check_app.py`** refuses an `app_id` under `draft-`, as the deploy and CLI 0.3.1 do;
  until now it said `clean` for `draft-notes`. Its `app_id_invalid` message also names the
  last-character rule. The prefix rule needs no platform list, so it runs even with no
  contract copy beside the script, as `load_contract`'s docstring promises such rules do.
  `linter_mutations.py` has one red mutation for it (`draft-notes`) and one that must stay
  green (`my-draft-notes`: the prefix, not the word).
* **SDK 2.5.0 in `sdk-api.md`.** The version and the `sdk_version` the SDK sends with
  `manaurum:ready`; `app.locale` / `app.dir` in the getters table and in the context's field
  list; an `app.onLocaleChange` row; the unregister function for every `on…`; a "With the
  SDK" paragraph in "The person's language" (`null` until the handshake, outside the shell
  or from an older shell, fall back to `navigator.language`; the callback can repeat the
  current value; the shell's language is not always the token's; test for
  `onLocaleChange` before calling it, because an older copy has none). The inline listener
  stays the first place the language is applied: it runs before any module loads, and it
  is what `check_ui.py` checks. The "No language" bullet goes. Everything 2.5.0 adds is
  marked as such: the getters and the context's `locale` / `dir` are `undefined` before it,
  the unregister function is missing before it (2.4.0 returns nothing), the `sdk_version`
  is the SDK's own (`'2.3.0'` from production that day), and the page's example tests both
  `onLocaleChange` and what it returned before calling them.
* **Browser requests are not egress.** `app.fetch` with an absolute URL is a plain browser
  request to that host: it never passes through Core, nothing filters it, and only
  `os.http.fetch`, called from the app's server, enforces `egress_allowed_hosts`; pass
  `credentials: 'omit'` for a third-party host. `sdk-api.md` says so, and
  `v2-platform.md`'s `egress_allowed_hosts` section adds a browser request to another host
  to what the list does not cover. The starter's page calls only its own relative `/api/*` paths, so nothing
  there contradicts it.
* **No dev runtime.** `v2-platform.md` §2 names two modes and says the schema's `dev` is
  retired and not a separate runtime any more (the deploy does not look at it); its `dev`
  subsection is deleted. The grant check is skipped only for an active BYO host, and even
  then not for `os.ai.complete` / `os.ai.providers` (`v2-platform.md`, from
  `capability_gateway.py`; `capabilities-reference.md`). The
  `capability_denied_in_dev_mode` row leaves the gate table and the AI family's "none works
  for a dev app" bullet goes. `publishing.md` loses the dev-mode publish endpoint, its poll
  route and its two preconditions, describes one endpoint, and says not to use the retired
  dev-apps route. `SKILL.md` and `manaurum-setup` say `dev` is retired; do not use it.
* **SDK 2.4.0's sender check** (Core sergeysuaib-ui/manaurum#2318, MAN-2561, merged
  2026-10-04). The SDK takes `manaurum:init` only from `window.parent` on a shell origin,
  pins that window and origin, stops forged `manaurum:*` messages before the app's handlers,
  and sends Drive picks only to the pinned shell. `sdk-api.md` (handshake, cross-origin
  rules, `pickFromDrive`) and `SKILL.md` Step 2.5 say which versions check the sender and
  which do not; "exports two names" becomes three, with `trustedShellOrigins`. The inline
  listener stays required: it runs before any module, and production still serves 2.3.0.
* **`os.ai.speak`** has its own section in `capabilities-reference.md`: input (`text`
  1–20,000 characters of plain text or Markdown, `voice` one of five, `lang`), output
  (`audio_base64`, `mime_type: "audio/mpeg"`, `voice`, `model`, `truncated`), what is
  spoken (code as a placeholder, links as their label, at most 4,000 characters cut at a
  sentence end), how to play and keep the MP3, and `400 nothing_to_speak`. It joins the
  family table, the AI family ("all eight share"), the `SKILL.md` capability table and
  `manaurum-setup`'s note on voice apps.
* **Voice funding.** `os.ai.transcribe` is no longer "BYOK": its section says who pays for
  both voice capabilities (the tenant's OpenAI integration, else Manaurum's metered voice
  key, else `412 integration_not_configured`), which workspace a call resolves and that it
  needs none, the four workspace answers that refuse a call even when the tenant has its
  own key (`400 workspace_context_required` for a blank header,
  `403 workspace_context_mismatch`, `412 workspace_context_unavailable` when only the
  Sandbox qualifies, `403 workspace_context_unavailable` when the forwarded user context
  names a workspace with no install the person can reach — read from
  `completion_context.py`, which is more exact than Core's guide), that AI Off is
  `403 ai_disabled`, that Manaurum's key serves three models only
  (`400 model_not_available`), and that every upstream failure is `502` on either key,
  never `504`. The gates table, the call contract's `X-Manaurum-Workspace-Id` line, the
  quotas table (`429 ai_spend_cap`), `os.ai.providers` (a `transcribe` entry pays for
  speech too, and its absence does not mean voice is unavailable) and the `SKILL.md`
  table follow.
* **`os.directory.list_users`** has a section like the locations one: exactly `{}` in;
  `{users: [{user_id, display_name, email, avatar_url?}]}` out, ordered by email, active
  non-anonymous members once each; the whole team tenant, or in the public tenant only the
  workspace the forwarded user context was minted for (else the person's primary one) and
  only when one of the app's owners works in it (an app-only call there gets
  `{users: []}`); where `display_name` comes from; a profile upload's `avatar_url` prefixed
  with the OS origin; no paging; the tenant only from the verified gateway context;
  sensitive, with how each kind of install gets it. It joins the family table, the
  sensitive list, the `SKILL.md` capability table and `v2-platform.md`'s "Names and roles",
  and the reference's "no `os.workspace.members`" line points to it.
* **The contract copy is re-synced** at Core `7c1f09566` (2026-10-04: `main` with
  sergeysuaib-ui/manaurum#2112, #2302 and #2380 merged), with
  `py -3.12 scripts/sync_contract.py --monorepo ../Manaurum --ref 7c1f095666a8e74d5904d42b8bdbfe7f4c1693bd`.
  The manifest schema is unchanged. The contract gains `os.ai.speak` and
  `os.directory.list_users` with their inputs (34 capabilities), and `check_repo.py`
  failed until both were documented and the reference's count said 34. The strings lose
  `capability_denied_in_dev_mode`, `dev_apps`, `hosted_runtime_not_ready` and the rest of
  the dev runtime's words, none of which a page quotes; `platform_v2_dev_mode` stays, as
  the name of an unrelated App Store flag. README's description of the copy no longer
  quotes a capability count, and `linter_mutations.py`'s capability-count mutation reads
  the reference's current number instead of expecting 32, which this sync turned into a
  missing anchor.
* **Dated production notes.** Every page that states one of Core's 2026-10-04 merges as
  current says, once per section, that it merged that day, that production had not
  deployed it, and what happens until it does: `capabilities-reference.md` (a note under
  the header — 34 registered on `main`, 32 on production that day — that the speak,
  directory and transcribe sections point to), `SKILL.md`'s capability rows,
  `manaurum-setup` (voice apps, the `draft-` rule), `v2-platform.md` (the `app_id` row,
  `dev`, "Names and roles", and a note that #2380's second, per-app audience waits for the
  deploy), `publishing.md` (the retired dev-apps route still answers on production)
  and the `manaurum-deploy` refusal table (`422 slug_reserved`). The reference's header and
  footer now agree on what was read by hand at which commit and what `check_repo.py`
  compares, the footer no longer says nothing is compared automatically, and the header
  note says CLI 0.3.1 does not know the two new capability names (they arrive in the
  unpublished 0.3.2), so only `check_app.py` notices an undeclared call to one.
  `sdk-api.md` says exactly which handlers 2.4.0's guard stops a forged message before
  (every non-capture handler, and capture-phase ones registered after it) and that
  `manaurum:session-response` is left to Core's session runtime.

### Not in this release

* **`https://manaurum.com/sdk/manaurum-v2.mjs` still served 2.3.0** on 2026-10-04 after
  #2318 and #2379 merged. The pages describe 2.4.0 and 2.5.0 as such, name 2.3.0 as what
  production served that day, and say to test for `onLocaleChange` before calling it.
* **Production had not deployed Core's 2026-10-04 merges** that day: a request to
  `/api/dev/v2/dev-apps` still answered `401` (the route was mounted), and a route added at
  07:25 that morning answered `404`. So production predates `os.ai.speak` and the voice
  funding (#2382), `os.directory.list_users` (#2112), the dev runtime's removal (#2296), the
  deploy's `draft-` refusal (#2368), the per-app audience (#2380) and SDK 2.4.0 / 2.5.0
  (#2318, #2379). Until it deploys, `os.ai.speak` and `os.directory.list_users` answer
  `404 capability_not_found`, `os.ai.transcribe` runs on the tenant's own OpenAI key only,
  the retired dev-apps routes still answer, and the deploy accepts a `draft-` slug that CLI
  0.3.1 and `check_app.py` already refuse. The pages say so where each fact is taught.
* **The starter's behaviour is unchanged.** What moved in it is the `app.css` version stamp
  and two comments (below). Its inline listener already checks the sender and applies
  `locale` / `dir`; its comments speak of 2.3.0, which is still what production serves.
* **What else the re-sync window holds, untaught.** Between `1256064` and `7c1f09566` Core
  also added personal versions of first-party apps (MAN-3098: `pv-` hosts and, for those
  only, `MANAURUM_SOURCE_SCHEMA` / `MANAURUM_VERSION_SCHEMA`), Aurum Studio's private
  drafts (MAN-2915 and its follow-ups), Duties (MAN-3059–3061) and `agent_jobs`
  (MAN-3062). None changes the manifest schema or adds a capability, and `check_repo.py`
  asks for none of them; the skills do not teach them.
* **The starter's `auth.py` keeps its audience check as it is.** Core now also names the
  app in every user_context `aud` (sergeysuaib-ui/manaurum#2380, MAN-3231), but a starter
  that requires it 401s against a Core that does not mint it yet, so that change waits for
  the deploy. Only its comments moved: `auth.py` and `tests/test_auth.py` no longer say
  Core's locale reader raises `KeyError` for an unknown language with no `dir`; Core reads
  that as absent since sergeysuaib-ui/manaurum#2381, as the starter always did.

### Checked

* `py -3.12 scripts/check_repo.py`: clean. `py -3.12 scripts/linter_mutations.py`: every
  mutation caught. `py -3.12 scripts/smoke_tools.py`: passes. The starter's `pytest -q`
  passes; `check_ui.py` and `check_app.py` say `clean` for the starter, and `check_ui.py`
  for the patterns page.
* Against Core: `owner_deploy.py`, `reserved_slugs.py` and the CLI's `manifest.py` on the
  MAN-3235 branch; `frontend/public/sdk/manaurum-v2.mjs` and
  `docs/handoff/V2_DEVELOPER_GUIDE.md` §8 at `2587dd77c` (#2379); the capability gateway,
  `main.py` and the guide's §1 on the MAN-1423 branch (#2296); `capabilities/ai.py`,
  `services/voice.py`, `capabilities/completion_context.py`, `capabilities/directory.py`,
  `capabilities/sensitivity.py`, `routes/capability_gateway.py` (the voice workspace map and
  the BYO grant exception), `frontend/public/sdk/manaurum-v2.mjs`, the CLI's
  `project_checks.py`, the guide's §3 and "Voice" section and `PLATFORM_V2_CONTRACTS.md` at
  `7c1f09566`; the manifest schema just before #2382 (any capability name deploys, so a
  manifest that declares `os.ai.speak` deploys on production and only the call fails).
* Production on 2026-10-04: `https://manaurum.com/sdk/manaurum-v2.mjs` served `2.3.0`, and
  an unauthenticated request to `/api/dev/v2/dev-apps` answered `401`, a route that exists;
  the `404` for the route added at 07:25 is the independent review's check.

# 3.17.0 - an app's server knows the person's language too

Summary: An app's server and the Assistant's requests now know which language the person picked in ManAurum, so emails, replies and exports can be written in it; the starter shows how.

### Why

3.16.0 taught the page to follow the person's language and said, correctly at the time,
that nothing outside the window could learn it (MAN-3244). Core shipped MAN-3244 in PR
#2341 (merged 2026-10-03): every `user_context` it mints - the gateway's on `user` and
`optional` routes, and the Assistant's call to `/agent/<name>` - now carries optional
`locale` (`en` | `ru` | `he`) and `dir` (`ltr` | `rtl`) claims from
`user_profiles.preferred_language`, and the person pass carries the same pair. Both are
absent when the person made no explicit choice or Core could not read it; Core reads
only a supported language with its own direction, and never refuses a token over the
pair. Core caches the value for 60 s, so a switch reaches a server within a minute. The
SDK still said the server could not learn it, and the starter's verifier dropped the
claims.

### What changed

* **The copy of Core's contract is re-synced** at Core `1256064` (2026-10-04). The
  manifest schema now has the `people` route mode and `people` block of App people
  (MAN-3216), so `check_app.py` no longer refuses a manifest that uses them. The skills
  do not teach App people yet; that is its own release, and the places that list the
  route modes now say `people` exists. The sync also brought **platform cron** (MAN-1373,
  merged 2026-10-03): `schedules` are live, so `v2-platform.md` gains "Scheduled jobs —
  `schedules`" (what arrives, verifying the system token, the at-most-once rules) and
  README and the field table stop saying nothing runs them.
* **Starter `src/auth.py`.** `UserContextClaims` and `PersonClaims` gain `locale` and
  `dir` (`None` when absent), read by `locale_pair()` exactly as Core's
  `read_locale_claims` reads them (`user_context_jwt.py:84`, `:102-113`): a supported
  language with its own direction, else both `None`, never an error. One difference,
  on purpose: Core's copy raises `KeyError` for a signed token whose unknown locale has
  no `dir` (Core never mints one); this one returns absent. New `server_language(request,
  claims)` picks the language for text the server writes: the claim, then the first
  en / ru / he in `Accept-Language`, then English.
* **Starter `GET /api/me`** returns `locale`, `dir` and `language`, so a standalone tab
  can learn the ManAurum choice; the page inside the window keeps following
  `manaurum:locale-change`, which is live.
* **Starter tests.** Each language read from the token; nine bad pairs (wrong
  direction, unknown or upper-case language, no `dir`, a number, nulls) accepted with
  no language; a token without the claims still verifies; the person pass carries the
  pair; `server_language` falls back in order; `/api/me` returns all three.
* **Docs.** `sdk-api.md` "The person's language" now says where the server gets it,
  when it is absent, that it can trail a switch by up to a minute, that the Assistant's
  calls carry no `Accept-Language`, and that an `anonymous` route still has only
  `Accept-Language`. `v2-platform.md` lists the optional claims in the verification
  steps, on the person pass and in "Names and roles". `SKILL.md` Step 2.5 points to the
  token instead of to what the server could not learn.
* **`check_repo.py`** treats "cannot learn the language" and "language ... not in the
  user_context" as a stale fact, with a red mutation in `linter_mutations.py`; the
  MAN-3244 line leaves `scripts/open-claims.txt`.

# 3.16.0 - apps speak the language the person chose, and switch when it changes

Summary: Apps built with the SDK now use the language the person picked in ManAurum (English, Russian or Hebrew) and switch the moment it changes; Hebrew screens read right to left.

### Why

The shell has told every window the person's language since MAN-2289: `locale` and `dir`
in `manaurum:init`, and `manaurum:locale-change` whenever the person switches. Nothing in
the SDK used it. `manaurum-v2.mjs` 2.3.0 drops both (MAN-3233), the starter never read
them, its interface was English-only, and its stylesheet said `margin-left` and
`text-align: left` - so an app copied from it stayed English for a Russian reader and
was laid out left to right for a Hebrew one. `sdk-api.md` had one sentence about it; no
check, no preview and no line of starter code did.

### What changed

* **Starter `index.html`.** The inline shell listener (sender check, handshake,
  appearance and device untouched) applies `payload.locale` / `payload.dir` from
  `manaurum:init` and `manaurum:locale-change` to `<html lang dir>` and
  `window.__manaurum`, and fires `manaurum-locale`. A standalone tab guesses from
  `navigator.languages` (en / ru / he, else English). Every visible string now comes from
  one `STRINGS = { en, ru, he }` table through `t(key)` and `data-i18n`, with `{0}` slots
  for code names that render as `<span class="mono" dir="ltr">`; numbers and dates go
  through `Intl` with the OS's tags (`en`, `ru-RU`, `he-IL`); the page re-renders on a
  switch, and what code wrote is redrawn rather than kept, so "Saved at 14:05" follows
  the new language's clock. A locale the shell sends that `STRINGS` has no table for
  resets `<html>` to English, left to right, so the head's `LOCALE_DIR` and `STRINGS`
  cannot drift into English laid out right to left. The note field has `dir="auto"`, and
  the back arrow `.flip-rtl`.
* **Starter `app.css`.** Every physical side is logical now (`border-inline`,
  `text-align: start`, `margin-inline-end`, `padding-inline-start`,
  `border-inline-start`), `.mono` is bidi-isolated, `.flip-rtl:dir(rtl)` mirrors an
  arrow, and the header names this as its fourth rule. Checked in headless Chrome: the
  starter mirrors completely under `?locale=he`, and switches live.
* **Starter tests.** `test_static.py` asserts that the listener applies `locale` and
  `dir` on init and on `locale-change` behind the sender check, the standalone fallback,
  that the three catalogues carry the same keys and the same `{0}` / `{time}` slots,
  that every key the code names exists, the fallback to English for a locale with no
  table, the save time formatted when drawn, the `Intl` tags, and no physical side in
  `app.css`.
* **`check_ui.py`** fails an `index.html` that never writes `locale` / `dir` from the
  payload onto `<html lang dir>` (the same shape as the appearance rule, so the
  standalone guess does not count), one with no `manaurum:locale-change`, and every
  physical side in a stylesheet - `margin-*`, `padding-*`, `border-left/right`, a
  corner like `border-top-left-radius`, `left` / `right` positioning, a four-value
  shorthand whose left and right differ (`padding: 4px 0 4px 20px`), `text-align` /
  `float` / `clear` left or right - naming the logical replacement. What mirrors anyway
  is not flagged: both sides alike in one rule, `margin: 0 auto`, `left: 50%`. A write
  in a helper counts when the helper is called with the payload's values
  (`setLanguage(p.locale, p.dir)`), and an app in one language on purpose declares it,
  `<html lang="he" dir="rtl" data-languages="he">`, and is held to that instead.
  `linter_mutations.py` has twelve red mutations and six must-stay-green cases for
  them; one of the reds found that the starter's own `window.__manaurum.dir = dir` was
  being counted as the document write.
* **`preview.py`.** `?locale=en|ru|he` sends the matching `dir` in `manaurum:init`; the
  bar has an en / ru / he switch that posts `manaurum:locale-change`, `&switch=he` posts
  one by itself after ready, and the shell posts one on ready as the real shell does. A
  new badge reads the framed page's `<html lang>` and computed direction back:
  `language applied`, `language IGNORED`, or `fixed language` for an app that declares
  one, also on `<body data-locale-check>`. `smoke_tools.py` checks the payload per
  locale and, in Chrome with the browser pinned to `en-US`, that the starter reads green
  in Hebrew, Russian and after a live switch, a copy that ignores the payload reads red,
  and the patterns page reads `fixed`.
* **`patterns/index.html`** is English only, and says so with `data-languages="en"`:
  its sample text has no Russian or Hebrew, and English laid out right to left is wrong
  for a reader and a screen reader alike.
* **Docs.** `sdk-api.md` has a new section, "The person's language": where the setting
  lives (on the account, `user_profiles.preferred_language`, and in the shell's own
  cookie), how a window gets it, what the app does with it, the standalone fallback, and
  plainly what cannot learn it - an app's server, the Assistant's `/agent` calls and a
  standalone tab - because Core does not put it in `user_context`, the person pass or any
  capability (MAN-3244, listed in `scripts/open-claims.txt`). `design.md` gains a "Right
  to left" section and a `Never` row for physical sides; `checks.md` describes the new
  rules, the fourth badge and the Hebrew screenshot; `SKILL.md` Step 2.5 gets a fourth
  non-negotiable and three lines in the handshake snippet.

# 3.15.0 - the app skill is half as long: the path stays, the detail moves to the references

Summary: The main app-building guide is now half as long, so the AI reads less before it starts; nothing was dropped, the details moved to reference pages it opens when needed.

### Why

`skills/manaurum-app/SKILL.md` had grown to 827 lines and 9,727 words, and an agent loads
all of it on every app request, before it has asked the person a single question. Most of
that length was not the path but the reasons for it: incident stories, the full Step 3.5
procedure with every measured browser quirk, the `check_app.py` findings table, the
deploy rejection codes, and paragraphs that repeated what `v2-platform.md`, `sdk-api.md`
and `design.md` already said. The rules that get apps rejected were in there, but an agent
had to read past 9,000 words to be sure it had them all.

### What changed

* **`SKILL.md`: 9,727 → 5,020 words** (827 → 537 lines). It keeps the path in order —
  Step 0, the reference apps, the seven rules (stories trimmed), the project layout and
  token rule, the minimal manifest and the `api_routes` default-deny rule, the port rule,
  the handshake script itself with its three non-negotiables (the sender check against
  exactly the two shell origins plus loopback, an answer within 10 s, appearance from
  `e.data.payload`), the capability headers, every mandatory step with its commands, and
  Step 4's three carry-overs. Every heading other files cite is unchanged, and the "How to
  use this skill" map now lists `references/checks.md`. Each place that lost detail
  points at where it went.
* **`references/checks.md` (new, 2,638 words)** - Steps 3.5 and 3.6 in full: all five
  parts of the UI check with the `--virtual-time-budget`, ~500px viewport-floor, wide-
  and narrow-window and fragment details; what `check_ui.py` covers rule by rule; the
  `check_app.py` findings table and what it cannot see; the documentation rule behind
  `tests/test_documented.py`; and the gateway and capability error codes those checks
  prevent (deploy codes stay in `manaurum-deploy/SKILL.md`, which owns them).
* **`references/v2-platform.md` (8,965 → 9,770)** - `api_routes` precedence and "one
  rule covers every verb"; the `app.listen(80, 'localhost')` case and the traffic path; Core's
  framing and CSP header rewrites; no host volumes; what the deploy packs (the exact
  exclude list, why `.env*` must live one level up, why `.dockerignore` does not help);
  the static nginx Dockerfile; the five deploy stages, ~8 s, no Core PR; the
  developer-token and `mnu_*` rules; `permissions`
  details (standalone URL unaffected, what a still photo needs); other tenants are a 403.
* **`references/sdk-api.md` (3,298 → 3,563)** - why the handshake lets `manaurum:session-*`
  through, what the loopback line is for, why the appearance is applied in the same
  listener, what the starter's `index.html` adds, and the app that pinned only the apex.
* **`references/design.md` (4,968 → 5,220)** - `window.print()` / `beforeunload` and the
  native-dialog replacements; no downloads, new tabs or clipboard writes and what to do
  instead; the small-window console check before a deploy; the "second app a week later"
  history of the seven rules.
* **`references/discovery.md` (2,194 → 2,276)** - why every screen gets a URL fragment
  in Step 0. **`references/capabilities-reference.md` (7,769 → 7,892)** - the Node call
  example, the private-files vs the user's Drive paragraph, `os.kv` is FORCE-RLS.
* Every fact taken out of `SKILL.md` was checked against the old text and lives in one
  of these files, or already lived in `manaurum-deploy/SKILL.md`; nothing was dropped.
  `scripts/check_repo.py` now requires the two measured Step 3.5 facts (drop
  `--virtual-time-budget` for a loading state; the ~500px headless viewport floor) in
  `references/checks.md` as well.

# 3.14.0 - screens people read, filters that stay quiet, and an accent budget (from PR #27)

Summary: Apps made for reading now get their own layout, filters stop shouting in the accent colour, and the checks warn when too much of a screen is coloured.

### Why

PR #27 (cut against 2.11.0) came from dindex-kb, a knowledge base over 1679 posts that
passed every check and was rejected on sight. The author had copied the shape of a
list-triage app, as the skill says to, and a reader came out looking like a ledger: titles
one typographic step above their captions, metadata on the right, thirteen category
filters built from accent-coloured `.btn-ghost`. Each rule was obeyed to the letter -
one primary button per view held while over twenty accent-coloured things sat on the first
screen, and "a badge is a word" held for a badge on 816 rows of 1679. Nothing in the SDK
named the difference between an app you read and one you sort through, and `app.css` had
nothing for the first kind. The PR sat unmerged and conflicting while main moved to 3.x;
this release ports its design half. Its database half shipped separately (3.13.0).

The same PR found a starter bug that is still on main: the cards inside a `[data-view]`
touch. `.app` spaces its own children, and since the router (2.9.0) those are the header
and the views. Measured through `preview.py` in headless Chrome: 0px between the
starter's overview cards before this release, 16px after.

### What changed

* **`app.css`** gained the reading half, every class mobile-aware: `.row.row-text` with
  `.row-headline` / `.row-excerpt` / `.row-foot`; `.reader`, `.article-title`,
  `.article-meta`, `.lead`, `.prose`, `.pull`; `.chips` / `.chip` / `.chip-n` (quiet until
  chosen, only the selected one accent, a sideways-scrolling row on mobile); the OS's own
  `--lh-relaxed: 1.7` (`frontend/src/app/globals.css:258`); `a` in the accent instead of
  the browser's blue; a capped, truncating `.row-meta`; and `.app > [data-view]` with
  `.app`'s own rhythm - the touching-cards fix. A labelled search `.field` in a `.toolbar`
  now takes the width the bare input has; it still does not grow (MAN-2849's rule stays).
* **`templates/patterns/index.html` (new)** - the screens the starter does not show,
  built only from `app.css`: a list of texts with chips, one article, a list of records
  with one badge on the one row that needs it. Its head script keeps the shell-origin
  check (MAN-2506) that PR #27's predates. CI holds it to `check_ui.py`.
* **`references/design.md`** - "What kind of screen is it" (sorting, reading, entering,
  and what each is built from), "Accent is a pointer, not a paint", four `Never` rows,
  every new class in the pattern table. **SKILL.md**: Step 0 asks for the kind of every
  screen (recorded in `BRIEF.md` §2); rules 3 and 4 add "it marks the few" and "at most
  four accent-coloured things on the first screen"; Step 3.5 reads the new bar and ends in
  **`templates/design-review.md` (new)**, five questions answered in writing per screen.
  `discovery.md` maps the kind in §2 to a layout; `reference-apps.md` says none of the
  three reference apps is a reader and points at the patterns page.
* **`check_ui.py`** fails on an accent class (`btn-primary`, `btn-ghost`, `badge-accent`)
  handed out inside a loop, and on more than four in one view of `index.html`. Unlike
  PR #27's version, loops are read only from scripts and inline handlers, so "for (most)
  teams" in a paragraph is not a loop. **`preview.py`** measures the rendered first
  screen and shows it beside main's three badges: accent count (red above four), a badge
  on more than half the rows of a list (red), where the first list row starts; transitions
  are frozen while it reads, or a non-default accent counts 0 mid-fade.
* **Tests**: `linter_mutations.py` - three red mutations and three that must stay green
  (chips toggled in a loop, four accent things in a view, "for (" in running text).
  `smoke_tools.py` drives a real headless Chrome through the meter: the patterns page must
  read green, a copy with thirteen ghost filters and a badge on every row red on both.
* **A flush card is flush on mobile too.** `body[data-device="mobile"] .card` outranked
  `.card.card-flush`, so on a phone every list row sat 16px inside its card and the
  hairlines stopped short (the starter's capabilities card, and the patterns lists).
  Measured in headless Chrome at 390px with `device: mobile`: 16px inset before, 0 after.
* **A toolbar in a view is spaced once.** A `.toolbar` directly in `.app` or a view kept
  its own bottom margin on top of the column gap: 32px above the card in the starter's
  detail view, 16px now. A toolbar inside anything else (with chips under it, in a
  `.reader`) keeps its margin.
* **Review fixes before release.** `preview.py` swaps the accent for a placeholder colour
  while it counts: graphite in light equals `--text-tertiary` and green in dark equals
  `--color-success`, so captions and success badges read as accent (the patterns list
  read 24). `check_ui.py` counts accent classes only in `class="..."` values outside
  `<style>` and `<script>` (the primary-button count too), adds a page header above the
  views to each view's first screen, and in a loop no longer flags a selector,
  `classList.remove` or `classList.toggle(cls, condition)`. The starter's capability
  rows lose their "granted" badge - on every row it marked nothing. The patterns page's
  order rows are inert, so they lose `is-interactive`; its post rows answer Enter and
  Space. Mobile text rows keep 16px. `smoke_tools.py` adds graphite-light and green-dark
  meter cases and fails if the two accent budgets drift.

# 3.13.0 - a database template that lasts past one request, and search that answers

Summary: Apps that keep their data in a database get a ready-made, tested starting point, including a search box that finds something when a question is phrased loosely.

### Why

PR #27 (2.12.0) carried a Postgres recipe and three linter rules for it, and sat unmerged
and conflicting while main moved on to 3.12.0. This ports that part of it - the recipe,
its CI job, the rules and the two reference sections - onto the current tree, with every
platform fact re-checked against Core main. The rest of PR #27 (screen kinds, the
patterns page, the design review, preview's first-screen meter) is not in this release.

The bug the recipe exists for is asyncpg's, not the platform's: the pool runs `RESET ALL`
on every connection it takes back, so a `SET search_path` in `init=` lasts one request.
On the platform the role's default search_path hides it; on any other Postgres the app
fails with `relation ... does not exist` on the second request. Several first-party apps
shipped it until MAN-1443.

### What changed

* **`templates/recipes/postgres/`** (from PR #27): `db.py` puts `search_path` in
  `server_settings`, which survives the reset, with the platform's own value (the schema,
  one `ext_<name>` per granted extension, `pg_temp`) and the first-use pool and timeouts
  `v2-platform.md` already teaches. `search.py` runs full-text search strictly, then
  relaxed (`or`) when that finds nothing, says which one answered, and HTML-escapes the
  `ts_headline` snippet before marking it. Three migrations: the table, a weighted
  generated `tsvector` column, and its GIN index built `CONCURRENTLY` in a file of its own.
  The pytest suite runs against a real Postgres and includes the broken `init=` pool.
* **CI**: a `postgres recipe` job runs that suite against `postgres:16-alpine` and fails
  if it would only skip. The tools job byte-compiles `templates/recipes/` too.
* **`check_app.py`**: three rules from PR #27, rewritten on main's SQL lexer - a session
  `SET` inside an asyncpg `create_pool(init=...)` (not when `setup=` or `server_settings`
  re-applies that setting), code reading `DATABASE_URL` under `"data": {"none": true}`,
  and a generated column on a function Postgres refuses there (`array_to_string`,
  `concat`, one-argument `to_tsvector`, clock and random functions). The last one runs
  whether or not the deploy's validator is importable, because the validator does not
  judge volatility. PR #27's own CONCURRENTLY, 64 KB and SQL-reader changes are not
  ported: main's versions supersede them.
* **`linter_mutations.py`**: a red case and a must-stay-green case for each rule,
  including the whole recipe copied into the starter.
* **`v2-platform.md`** section 7: "Connecting from the container" and "Full-text search";
  the role's search_path is stated as Core sets it. **SKILL.md** points to the recipe and
  lists the new rules in Step 3.6 and "What NOT to do". README lists the recipe.

# 3.12.0 - the plugin installs in Codex too (MAN-1439)

Summary: The ManAurum SDK can now also be installed in Codex / ChatGPT, using the same skills and templates as Claude Code.

### Why

PR #34 added Codex packaging in September, cut at 3.0.0; it sat unmerged and conflicting
while the skills moved on. Its README and setup edits are superseded by later releases;
its manifests are not.

### What changed

* **`.codex-plugin/plugin.json`** and a portable root **`plugin.json`** (from PR #34): Codex
  reads the same `skills/` and `templates/`, nothing is copied.
* **README**: "Install in Codex / ChatGPT Work", with what is not verified yet (an install
  in a fresh ChatGPT chat, MAN-1439) and what does not carry over (the skills' slash-command
  cross-references, the stale-copy check, the session-start update hook).
* **`check_repo.py`**: both new manifests carry the plugin's version, or the build fails —
  PR #34's had stayed at 3.0.0.

# 3.11.0 - document the code in the edit that writes it, and the starter checks it

Summary: Apps built with the SDK now explain their own code as they are written, and the starter's tests fail if a function is left unexplained.

### Why

roiduani proposed this in PR #18 (2.9.0), which sat unmerged while the skill moved on. An
app nobody can safely change is a cost the first author never sees: the docstring written
after the app works records the signature, not what a `None` meant.

### What changed

* **`manaurum-app` Step 3**, "Document it in the same edit that writes it": Google-style
  docstrings and JSDoc, spent on what the signature cannot say; never anchor a test on
  comment text. (Shortened from PR #18; it does not take the Step 3.5 number, which is the
  UI check now.)
* **`templates/v2-starter/tests/test_documented.py`** (from PR #18): an `ast` walk that
  fails on any undocumented module, function or class under `src/`. The five starter
  functions that had none now do (`_ok`, `_fail`, `save_my_note`, `read_note`,
  `write_note`); `_fail` says why it cuts at 300 characters (Core passes the model no more,
  `v2_capability_dispatch.py`).

# 3.10.0 - every capability's documented input, checked against its schema

Summary: The SDK's own checks now also catch a capability documented with the wrong input fields, before an app built from it fails.

### Why

The worst findings of the audit were inputs: `os.files.upload` without its required
`size_hint`, `os.ocr.extract` sending `key` for `file_key`, `os.apps.call` with fields Core
does not have (K2–K4). 3.3.0 rewrote the reference by hand; nothing kept it right. This is
the last item of the audit's contract plan (section 3, item 2).

### What changed

* **`scripts/sync_contract.py`** records `capability_inputs` in
  `templates/platform-contract.json`: for each of the 32 capabilities, the input fields and
  `required` of the schema its handler registers, read with `ast` (module constants and
  `**` merges followed; a value it cannot evaluate is ignored, but a schema whose fields,
  `required`, `oneOf` or `not` it cannot read stops the sync).
* **`check_repo.py`**, in `capabilities-reference.md`, under a heading that names one
  capability: the **Input:** example (an inline `{ … }`, the fenced block below it, or the
  key-only form) may send only fields the schema has, must send every required one, and
  respects the schema's `oneOf` / `not`; a `| Field | … | Required |` table lists exactly the
  schema's fields, required where the schema requires them; an example in a shape the
  check cannot read is a finding, not a pass. Today 23 examples and 13 tables are checked
  and match Core; no sentence changed. Capabilities documented under a heading that names
  several (`os.drive.list` / `.read` / …, the image and location pairs) are not checked; they
  were verified by hand against Core a5b9db9.
* **`linter_mutations.py`**: six more (145) — Core renames a field, drops one, adds one,
  makes one required, makes one optional, and requires one the example leaves out.

# 3.9.0 - manaurum-app reads in order, and each fact lives in one place (audit Н14)

### Why

`manaurum-app/SKILL.md` gave no reading order, repeated the deploy script that
`manaurum-deploy` owns, kept a second copy of the container's environment table that had
already drifted from `v2-platform.md`'s, and shared its trigger ("start building a new app")
with `manaurum-setup`.

### What changed

* **"How to use this skill"** at the top of `manaurum-app`: the steps in order — including
  the scaffold step that hands off to `manaurum-setup` — and which reference to open for
  what.
* **Step 4** keeps the token and the three things to carry (echo the slug, the POST is
  asynchronous, what `succeeded` means) and hands the script, the refusals and rollback to
  `manaurum-deploy`, instead of a second copy of its script.
* **The environment table lives in `v2-platform.md` only**, now with what the skill's copy
  knew and it did not (`MANAURUM_APP_ID` is the app id header for `os.kv.*` and
  `os.events.emit` only; the `DATABASE_URL` role has no CREATE; `MANAURUM_V2_TOKEN` is never
  injected). The skill keeps the three rules people get wrong and a pointer.
* **`manaurum-setup`'s description** says what it is for — scaffolding files — and sends
  "what to build" to `manaurum-app` and deploying to `manaurum-deploy`.

# 3.8.0 - the error codes and the window protocol, checked against Core

### Why

The audit's systemic recommendation was a copy of Core's contract that CI checks the
documents against. 3.7.0 did that for the manifest schema and the capability list. Error
codes and the window's message types were still trusted to memory, and both are what a
developer matches on: a renamed code turns an error branch into dead code, and a message the
shell stopped sending is a handler that never fires.

### What changed

* **`scripts/sync_contract.py`** also records the window protocol in
  `templates/platform-contract.json` (`messages`: what a v2 app may post, from
  `V2_ALLOWED_MESSAGES`; what the shell posts back, from `IframeAppHost.tsx`; the v1 prefixes
  it refuses; the session runtime's two), and writes `scripts/platform-strings.json`: every
  snake_case word in a string literal of the Core code a developer's errors come from
  (gateways, deploy and credential routes, capability handlers, the Assistant's dispatch),
  read with `ast`, docstrings aside, plus the literal tails of the f-strings an error is
  built from (`detail=f"{prefix}_backslash"`), so a built code still counts.
* **`check_repo.py`**: every error code a document quotes (`` `404 route_not_declared` ``,
  `` `502 upstream_error:<provider>` ``, or each code in the second cell of a status row) must
  still appear in those strings - which catches a code Core dropped, though not one renamed
  while its old name survives in some other string; every `manaurum:*` a document or
  template names must be one the shell handles, sends or refuses; and every message in the
  protocol must be described in `sdk-api.md`. Every quoted code and every message type
  matches Core today, so this release changes no sentence.
* **`v2-platform.md`** names MAN-3235 as the CLI release that will know `auth: "optional"`,
  with a line in `open-claims.txt`, so `--tickets` lists it until it ships.
* **`linter_mutations.py`**: eight more (139), red and must-stay-green.

# 3.7.1 - what the 2026-10-02 audit left: stale pointers, the `.dockerignore` myth, untested rules

### Why

After 3.2.0–3.7.0 the audit's critical, high and medium findings were closed but a tail of
smaller ones was not, and one of them turned out to be wrong advice, not a stale pointer.

### What changed

* **`.dockerignore` is no defence on a platform deploy.** `manaurum-app/SKILL.md` and
  `manaurum-deploy/SKILL.md` recommended it as a "second line of defence" against a leaked
  `.env`. Core builds with Docker's classic builder (`POST /build`, `version=1`,
  `production.py`), which does not apply `.dockerignore` to the uploaded context, and the tar
  is stored as uploaded. Both now say: keep `.env*` out of the directory, and let the
  Dockerfile's `COPY` list keep files out of the image. The starter's `.dockerignore` header,
  which said "anything listed here never reaches the builder", and its
  `requirements-dev.txt` say the same.
* **The published CLI refuses `auth: "optional"`.** `cli-v0.3.0` was cut on 2026-09-02, a month
  before MAN-3200; its schema allows `user` and `anonymous` only, so `app validate` and the
  deploy preflight refuse a manifest 3.6.0 teaches. `v2-platform.md` says so and gives the way
  round (`--skip-preflight` after `check_app.py`, or the API).
* **Usage numbers exist** (audit С28). README's "No metrics" now describes
  `GET /api/app-usage/<uuid>` (MAN-3131: the platform's app UUID, a signed-in session) and
  says browser-error capture (MAN-3132) is for Aurum Studio apps only.
* **The starter waits as long as Core does** (Н2): `capability.timeout_for()` gives `os.ai.*`
  and `os.ocr.*` 185 s and `os.http.*` / `os.apps.*` 35 s instead of a flat 15 s, with tests.
* **`verdant`** is the ninth accent (Н9; `globals.css`, `preferences.py`): in `app.css`,
  `design.md` and `preview.py`; `SKILL.md` says nine.
* **`sdk-api.md`** (Н10): `manaurum-v2.mjs` exports `findClippedContent` as well as
  `ManaurumV2`; the layout guard, `app.checkLayout()` and `init({ layoutCheck: false })` are
  described; `IframeAppHost.tsx` line references updated.
* **Pointers and leftovers** (Н7, Н8, Н12, Н13, С15): "19 passed" in `manaurum-setup` and
  the starter README (`check_repo.py` now refuses "N passed" too, and reads the starter
  README); a link to a section that does not exist;
  `production.py` and `agent/types.py` line numbers; "`dev` (in-browser editor)" — that
  builder is gone; the slug rule in `manaurum-setup`; "on `dokploy-network`" (the shared app
  network, whatever it is named); the starter README telling people to set `migrate_command`;
  the build-context scan's refusals (a file over 32 MB among them), which only an `enforce`
  scan makes, in a row of their own.
* **CHANGELOG** (Н15): every release heading is `#` now; 2.0.0 and older used `##`.
* **`check_repo.py`** refuses "no `workspace_id`" in the token, the last phrase on the audit's
  ban list; `open-claims.txt` re-verified against Linear.
* **`linter_mutations.py`**: 15 more mutations (131), one for each linter rule that had
  never been seen to fail (Н1): a module that does not parse, no Dockerfile, migration
  numbering, an unparseable manifest, short hex, `rgba()`, `style=` colour, `<button
  class="row">`, a clickable row without `is-interactive`, no `index.html`, two primaries in
  one view, device and payload never read.

# 3.7.0 - the linters check what the platform checks, and the plugin can see itself drift

### Why

The 2026-10-02 audit found two things wrong with the tools, beyond the documents.

* **The linters were kinder than the platform.** `check_app.py` accepted `{param}` and a
  bare `*` in `runtime.api_routes` (the gateway matches both literally, so the route 404s),
  missed routes mounted with `include_router(prefix=)` or `add_api_route`, passed an
  `/agent/*` handler whose only "check" was a word in a comment, flagged
  `optional_capabilities` and capability names in a README, never knew which capabilities
  exist, and let through most of what the deploy refuses: root-key typos, reserved and
  invalid slugs, write-named tools declared read-only, tool names the Assistant drops, and,
  without the CLI installed, `BEGIN`, `SET`, `COPY`, `CREATE EXTENSION`, `RENAME`,
  `DROP INDEX`, `.SQL` and the 64 KiB cap. `check_ui.py` flagged `ui.confirm()` and
  `style.width`, and its appearance check passed an app that never applied the shell's
  appearance.
* **Nothing compared the plugin with the platform.** Every stale fact had the same history:
  Core changed and no program here held a copy of what Core says. And the version hook
  only compared directories in the local cache, so a machine stuck on 2.7.2 with nothing
  newer on disk heard nothing for six weeks.

### What changed

* **`templates/manifest_v2.schema.json` + `templates/platform-contract.json`**: a copy of
  Core's contract with the SHA it came from — the schema, the 32 capabilities, reserved
  slugs, the slug pattern, the write-verb prefixes, the Assistant's tool-name format.
  **`scripts/sync_contract.py`** refreshes it from a monorepo checkout, read-only.
* **`check_app.py`** reads the contract instead of keeping its own lists, matches routes
  exactly as `api_route_matcher.py` does, follows `include_router` and `add_api_route`,
  decides `/agent/*` protection from the AST (a `Depends`/`Security` on the handler, its
  decorator, its router or its include, followed through wrappers and `Annotated`
  aliases across modules), and adds the slug, root-key, `auth`-mode, tool-name,
  write-verb, `entrypoint` and `byo`/`permissions` rules and the migration ones above.
  What it cannot trace (an include in a loop, a computed prefix, `app.mount`) it says
  as a note instead of guessing. FastAPI's own security schemes (`OAuth2PasswordBearer`
  and the rest, however assigned or imported) never count as a check: they read headers
  the gateway strips, and the runtime calls `/agent/*` with `X-Manaurum-User-Context`
  only (`agent/v2_capability_dispatch.py`). A library dependency is taken silently only
  when its name says user context or claims; one that says only auth, user, token,
  verify or the like is taken and named in a note. Migrations are read through a small
  SQL lexer, so a plpgsql or `BEGIN ATOMIC` function body, a string or a comment is not
  a statement: an `updated_at` trigger is no longer "transaction control", and
  `'Rename it'` is not a RENAME. `DROP EXTENSION` is destructive (a `DropStmt` to Core),
  not forbidden; a function in a language other than sql or plpgsql is forbidden; a file
  that starts with a UTF-8 BOM is refused, as the deploy's parser refuses it; a
  subdirectory under `migrations/` is a note (the deploy skips it); the 64 KiB cap is
  measured on the concatenation exactly as the deploy builds it.
* **`check_ui.py`**: only the global `alert`/`confirm`/`prompt`, in scripts and inline
  `on*=` handlers; only a colour set through `element.style`; appearance must be written
  from a value read off the payload (directly or destructured) by code that is used -
  called, or passed by name as a handler.
* **`check_repo.py`** holds every document and every text file under `templates/` to the
  contract — each registered capability documented, no unregistered one named, the
  `permissions` enum as the schema has it, `check_app.py`'s fallback keys equal to the
  schema's — and refuses eleven facts found stale, wherever they come back. "An earlier
  version said..." excuses its own sentence only, not the paragraph around it.
* **`version_check.py`** also reads the marketplace clone and, at most daily, the released
  version on GitHub (2 s, opt-out `MANAURUM_SDK_NO_UPDATE_CHECK`), and says how to update
  and how to turn auto-update on. A failed check is remembered for the day too, and the
  whole fetch, DNS included, has one 2 s deadline. `hooks.json` finds `python3`, `python`
  or `py -3`.
* **`linter_mutations.py`**: 65 new mutations, red and must-stay-green, for every new rule.
* **README**: auto-update, the contract files, what the checks now cover.
* **The gateway drops a client's identity headers (MAN-3214, platform `c1a7ccc`),
  continued from 3.6.0.** `v2-platform.md` and the starter's `auth.py` still said, in
  places, that the gateway passes the client's headers through. It now drops that
  header, `X-Manaurum-Person` and the system-call headers on every branch
  (`_CORE_ASSERTED_HEADERS` in `routes/v2_app_gateway.py`). The starter still refuses two
  copies, as defense in depth; `check_repo.py` refuses the old sentence.
* **The contract is synced at platform `56ce52c`**, which includes MAN-3200: `auth:
  "optional"` is in the schema's enum, so `check_app.py` accepts it (3.6.0 documents it).

# 3.6.0 - `auth: "optional"` and the person pass (Core MAN-3200, MAN-3214)

### Why

Apps whose pages both guests and members open (a share link, a voting room) had to
mint their own pass on a `user` route and carry it on `anonymous` routes, because the
gateway had no "the user if signed in" mode. Core adds it as stage 1 of App people
(MAN-3212, D-160). Ship this release together with the Core deploy that carries it:
before that deploy an `optional` route fails manifest validation.

### What changed

* `SKILL.md`, `references/v2-platform.md` "Pages that guests and members both open":
  `auth: "optional"` replaces "there is no third mode". A member gets the usual
  `user_context` plus `X-Manaurum-Person` (`aud` = `MANAURUM_APP_ID`); a guest and a
  member of another tenant get neither and are indistinguishable; never a `401`.
* `references/sdk-api.md` "Sessions in a standalone tab": the `stale` signal, and why a
  `POST` is not repeated.
* `templates/v2-starter/src/auth.py`: `verify_person_pass` and the `optional_person`
  dependency, with the audience, tenant, `typ` and duplicate-header checks;
  six tests in `tests/test_auth.py`.
* The pass verifier requires the `aud` claim (`require_aud`): python-jose skips the audience
  check for a token with no `aud` at all. Core does the same (sergeysuaib-ui/manaurum#2328).
* The duplicate `X-Manaurum-User-Context` note: Core now drops a client-sent copy
  (MAN-3214). The starter keeps refusing two headers; it costs nothing.

# 3.5.0 - the manifest, the gateway, the window and the Assistant, checked against the code (MAN-1452)

### Why

The last part of the 2026-10-02 audit (`docs/audits/`): facts about the manifest, the
gateway, the window and the Assistant that had gone stale.

* "`/agent/*` is on the public internet" in twelve places: the gateway has refused it since
  MAN-1432. The check is still needed, for a different reason: every app's container shares
  one network.
* "`runtime` is not strict" (v2-platform.md:24, the copy 3.1.0 missed).
* "`data.shared` is one cross-tenant schema with an isolation warning": it is managed mode
  under another name. `connection_cap` is read by nothing; `data.extensions` was not
  mentioned.
* "`egress_allowed_hosts` drops everything else" and a `0.0.0.0` bug fixed in MAN-2263: the
  list is enforced by `os.http.fetch` only.
* "`entrypoint` on a hosted app is ignored" (it is a `422`); `platforms.mobile.entrypoint`
  works for v1 only; the `offline` block does nothing for v2.
* "The rest of your CSP survives verbatim"; "an external `app.fetch` is subject to the
  gateway's egress rules"; "`tokens.css` has a dead hostname and 6 of 8 accents" (fixed in
  MAN-2367).
* Not documented at all: the 57-character limit on slug plus tool name, the approval card,
  the Assistant's 30 s timeout, `routing_hints` in the user's language, the gateway's other
  answers (`app_not_found`, `app_disabled`, `path_traversal_rejected`, the 30 s
  `upstream_timeout`), `/__manaurum/`, the read-only runtime, `locale` / `dir` /
  `manaurum:locale-change`, the session wrapper's own answers, and that the token carries
  no role.

### What changed

* **`references/v2-platform.md`**: §1 (strictness, `app_id` rules, `data`, `platforms`,
  `agent_capabilities`, `offline`), the `/agent/*` warning, routing hints, approval cards,
  timeouts, the guest pass (HMAC-SHA256, constant-time compare, revocation, the other-tenant
  `404`), names and roles, a new "What else the gateway answers", `byo` `entrypoint`,
  egress.
* **`SKILL.md`**, **`references/sdk-api.md`**, **`references/design.md`**,
  **`manaurum-setup`**: the same facts where they repeat them; the setup example's reader
  declares `"is_write": false`.
* **`/agent/*` wording** in README, `check_app.py`, the starter's `agent_routes.py`, README
  and test docstrings.
* **`app.css`**: the tokens note.

# 3.4.0 - the deploy as it runs now: a probe, a migration gate, immutable versions, owner tokens (MAN-2600)

### Why

The audit (`docs/audits/`) found the deploy pages describing the pipeline from before
September, the same fact repeated in up to twelve places:

* "There is no readiness probe" and "a wrong port deploys green and then 502s". The probe
  has existed since MAN-1369 and is on by default: a container that does not answer on
  `runtime.port` fails the deploy and is rolled back.
* "A failed per-tenant migration still activates the version". Since MAN-2510 it stops the
  version from going live.
* "Only three things fail synchronously; the manifest is validated in the job". The POST
  now refuses a bad manifest, slug or owner (MAN-2597), a used version or another tenant's
  slug (MAN-1586, MAN-1587) and an oversized archive (MAN-164) with its own `4xx`, none of
  which were listed.
* "Redeploying the same version is fine for dev iteration". It is `409
  version_already_published`, also after a deploy that failed once its image was pushed.
* The token pages still taught `{"apps":["*"]}`, a cap of 5 and "blank means all apps".
  `*` is refused, the cap is 20, and a brand-new app can only be deployed with an "all my
  apps" (`owner`) token (MAN-2597).
* Rollback was "flips `installed_version_id`, no body"; logs were "a stub"; the README
  pinned the CLI to `cli-v0.2.0` although `cli-v0.3.0` shipped on 2026-09-03.

### What changed

* **`manaurum-deploy/SKILL.md`** is the single home of the deploy contract, rewritten
  against Core `main` 97d5660:
  * Prereqs: both token kinds, what a new app needs, lifetimes, the cap, where the CLI keeps
    the token, single ownership.
  * The job: the result on success and on failure (`log_kind`/`log_tail`), the phases in
    order, migrations before the container swap.
  * Every synchronous refusal of the POST, in order.
  * What `succeeded` means: the migration gate and the readiness probe, `health_path`
    strict when declared.
  * Versions are immutable; when a label is used up.
  * Migrations: the 64 KiB total, UTF-8, the 30 s / 5 s timeouts, and `migration.breaking`
    applying to every file.
  * Rollback (`version_label`, `409 deploy_in_progress`, what it skips), logs (a real tail,
    not redacted).
  * Who gets the app after a deploy, and that another tenant's install does not serve its
    users today.
  * Deleting an app: what is kept, and the redeploy-a-deleted-slug trap.
* **`v2-platform.md` §4–§6** keep the token facts in brief and point at the deploy skill;
  §7 and §8 are corrected (the gate, the install fan-out, App Store).
* **`SKILL.md`, `publishing.md`, `manaurum-setup`, README, `check_app.py`, the starter's
  Dockerfile and README**: the probe instead of "502", the synchronous manifest check,
  `cli-v0.3.0`.

# 3.3.0 - the capability reference, checked against the code one capability at a time (MAN-2144, MAN-2198, MAN-2995, MAN-1923)

### Why

The 2026-10-02 audit (`docs/audits/`, in 3.2.0) found `capabilities-reference.md`
describing a platform from before September. Followed literally, it produced calls that
fail on the first request while the deploy stays green:

* `os.files.upload` without `size_hint`, which has been required since MAN-1707
  (2026-08-13): a `422` on every upload.
* `os.ocr.extract` with `{provider, object_key, schema}`; the input is
  `{file_key, schema?}`, and the output and errors were different too.
* `os.apps.call` with `{app_id, version: "1", timeout_seconds}`; the input is
  `{target_app_id, method, args, version: int, timeout_ms}`, and only four methods of
  two built-in apps can be called. "RPC to another v2 app" (SKILL.md, v2-platform.md)
  does not exist.
* `os.ai.complete` and `os.ai.embed` answering with `usage`; they answer `tokens_used`,
  `cost_usd` and `cost_known`, so reading `usage` raised on every success. `top_p` was
  documented as a passthrough and is a `422`. The page also described `os.ai.complete` as
  BYOK only, before MAN-2412 bound it to the workspace's chosen backend.

Six registered capabilities were not documented at all (`os.ai.providers`,
`os.ai.image_submit`, `os.ai.image_poll`, `os.locations.list`, `os.locations.get`,
`os.drive.delete`): the page said "All 26" of 32. Others were stale: the Drive chapter
(5 MB, create-only, a notification MAN-2991 removed), `os.compliance.audit_query` ("scoped
to the calling app"; it returns the whole tenant's rows), `os.apps.bulk_export` (no
dataset is registered, so every call is a `404`), event subscriptions (no hosted app can
receive events), notification limits, quotas, and three error codes that do not exist
(`missing_provider_credentials`, `upstream_5xx`, `422 egress_not_declared`).

Two open PRs already carried part of this, written against 2.7–2.10: #17 (Drive) and #20
(camera, `size_hint`, the image capabilities, by roiduani). Their content is carried over
here and corrected where the platform moved since.

### What changed

* **`references/capabilities-reference.md`** is rewritten against Core `main` 8fe6f5d,
  capability by capability, from the input schemas, return values and raise sites:
  * the inventory of all 32, and what does not exist;
  * the call contract (which app-id form each family keys by, the user context, bodies
    that are not JSON, `format` not being enforced) and every gate the gateway runs, in
    order, with its code;
  * per capability: input with ranges and defaults, output, errors, limits;
  * `os.ai.complete`: which backend answers (unpinned, `provider`, `model` only), which
    workspace, `log_prompt`, the spend cap, and the error table;
  * new sections for `os.ai.image_submit` / `image_poll`, `os.ai.providers` and
    `os.locations.*`; `os.drive.write` overwrite with `if_match`, and `os.drive.delete`;
  * a quotas section that lists the limits that actually fire.
* **`v2-platform.md` §3** stops repeating the contract (its error table was the stale copy)
  and points at the reference. `provides` / `consumes`, the wildcard grant and the dev-mode
  allow-list are corrected.
* **`SKILL.md`**: the capability table matches the reference; `egress_not_declared` is a
  `412`; `MANAURUM_APP_ID` is the app-id header for `os.kv.*` and `os.events.emit` only.
* **`permissions`** is `["microphone", "camera"]` in every place that said microphone only
  (MAN-1920), with when a still photo needs no declaration and the `byo` refusal
  (MAN-1922).
* **`scripts/open-claims.txt`**: MAN-133, MAN-2253, MAN-1289 and MAN-2199, which the new text cites
  as open.
# 3.2.0 - a token is checked for whose it is, and the window for who is talking (MAN-1307, MAN-3203)

### Why

The audit of 3.1.0 against Core's `main` (285c8a8, `docs/audits/`) found three
places where the starter, and the text around it, taught something unsafe:

* **`src/auth.py` accepted any app's `user_context`.** It checked signature,
  issuer, audience and expiry, which every app's tokens pass: Core signs them
  all with one key for one audience. It never compared `app_id` or
  `tenant_id`, and it defaulted missing claims to `""`. So a token the gateway
  minted for app A, which A's developer sees, opened app B for 60 seconds.
  The gateway also does not remove an `X-Manaurum-User-Context` the client
  sent, and adds its own under a different letter case, so a container can
  receive two headers, with `headers.get()` returning the client's. MAN-1307
  covers the binding on the platform side; the second header is not yet
  ticketed.
* **The handshake trusted the first sender.** The starter's `index.html`, the
  snippet in `SKILL.md` and both in `sdk-api.md` acted on `manaurum:init`
  from any window and answered it. Any page can frame a v2 app, every other
  app included, and `manaurum-v2.mjs` 2.3.0 adopts whoever posts
  `manaurum:init` as its shell, on every `init`, and sends that window the
  app's Drive pick requests. The platform rule (MAN-2506) is
  the parent window and the shell's two origins. `sdk-api.md` described the
  first-sender behaviour as correct.
* **`check_app.py` could not catch a real deploy token.** Its pattern wanted
  16 letters or digits straight after `mna_`; Core mints
  `mna_<12 hex>_<secret>` and `mnu_<env>_<secret>`, and the mutation that
  "proved" the rule planted a shape no token has. Generated in the real
  format, 400 tokens out of 400 passed the old rule. Meanwhile
  `manaurum-setup` drew `.env.manaurum` inside the app directory, where the
  CLI packager uploads it, while `manaurum-app` said one level up.

The starter also said the capability gateway rejects a forwarded user
context. It requires one for `os.drive.*` and `os.calendar.*`, and
`call_capability()` had no way to send it.

### What changed

* **`templates/v2-starter/src/auth.py`** requires `sub`, `tenant_id`,
  `app_id`, `app_version`, `exp` and `iat`; refuses a token whose `app_id` is
  not `APP_SLUG` (`401 user_context_wrong_app`) or whose `tenant_id` is not
  `MANAURUM_TENANT_ID` (`401 user_context_wrong_tenant`, and `503` when that
  variable is missing); and refuses a request that carries the header twice
  (`401 user_context_ambiguous`). `UserContextClaims` gains `workspace_id`,
  which the gateway does mint, and `token`, for forwarding.
* **`src/capability.py`**: `call_capability(..., user_context=claims.token)`.
* **`src/static/index.html`** checks `event.source === window.parent` and the
  origin against `https://manaurum.com` / `https://app.manaurum.com` in a
  listener registered before the SDK's, which stops whatever it refuses, so
  the SDK never sees it either. It lets `manaurum:session-*` through untouched:
  Core injects a session-renewal script into every v2 page that talks to a
  Core frame of its own and checks those messages itself. On loopback the
  guard also admits the page's own origin, so `preview.py` can frame it.
  Checked in a browser against `preview.py`: a sibling frame's `init` and
  `theme-change` are dropped, its `session-response` reaches the next
  listener, and the shell's messages work.
* **Tests** in `test_auth.py`, `test_routes.py`, `test_capability.py` (new)
  and `test_static.py`. The `user_context` fixture now mints the slug, the
  tenant and a `workspace_id`, as the gateway does; it minted a UUID `app_id`
  before. Each new check (the app and tenant binding, the required claims,
  `exp`, `iat`, the duplicate header, the missing tenant, forwarding, and in
  `index.html` the parent, self, origin and propagation checks, the loopback
  exception and the session pass-through) was removed or widened in turn, and
  the suite went red each time.
* **`SKILL.md`, `references/v2-platform.md`, `references/sdk-api.md`,
  `manaurum-setup`**: every handshake snippet carries the sender check and
  replies to the checked origin instead of `'*'`. The four verification steps
  for `X-Manaurum-User-Context` are written down once, in `v2-platform.md`.
  Neither page says the SDK may be trusted to pick its shell.
* **`templates/check_app.py`** matches the token shapes Core mints, exactly
  enough that an identifier like `mna_token_from_the_environment` is not one.
  `scripts/linter_mutations.py` plants a real-shaped `mna_*` and a new
  `mnu_*` case; both survive the old pattern.
* **`.env.manaurum` lives one level above the app, everywhere.** The setup
  tree and the `.env.manaurum` section say so, and `deploy.sh` reads
  `../.env.manaurum` and refuses to run with one inside the app directory.
* **`templates/preview.py`** sends `locale` and `dir` in `manaurum:init`, as
  the shell does, and its "NO manaurum:ready" badge names the origin rule.
* **`docs/audits/`**: the audit report and its evidence.

### Not in this release

* The platform half: stripping a client's `x-manaurum-*` headers at the
  gateway and minting one audience per app. Until that ships, the checks in
  `auth.py` are the whole defence.
* `manaurum-v2.mjs` 2.4.0 (MAN-2561) has not shipped; `https://manaurum.com/sdk/`
  still serves 2.3.0, so the pages keep naming 2.3.0 and keep the inline
  guard mandatory rather than optional.
* The rest of the audit's findings: deploy, tokens, capabilities, `/agent/*`
  wording and the linters' other gaps go in their own releases.

# 3.1.0 - what the first app ported to v2 found missing (Planning Poker)

Summary: Fewer false alarms when checking your app, and app settings are found again.

### Why

Moving Planning Poker onto Platform v2 produced eleven points of feedback.
Checked against Core's `main`, most of them were gaps in these skills rather
than in the platform, and two were defects in the SDK itself:

* `check_app.py` called `runtime.public_paths` and `runtime.health_path` "a
  key the platform does not read". The gateway reads the first and the
  post-deploy probe reads the second, so every app with a guest page got a
  false red.
* The starter's `src/capability.py` said in a comment to send the slug to
  everything but `os.kv` and `os.events`, and then sent the UUID to
  everything. `os.secrets` and `os.files` store under the header as sent, and
  `manaurum app set-secret` writes under the slug. So an app grown from the
  starter read every secret set from the CLI as `404`.

Checking those turned up a third: since MAN-1899 (2026-08-23) `runtime` is
`additionalProperties: false`. Five places here still said it was not strict
and that a typo deploys green and does nothing. A typo is a `422` now.

### What changed

* **`templates/check_app.py`** knows all eleven `runtime` keys the schema
  declares, and says a stray one is a `422`. `scripts/linter_mutations.py`
  gains a must-stay-green case with `public_paths`, `health_path` and
  `resources`. It was red on 3.0.0.
* **The starter** sends the UUID to `os.kv.*` / `os.events.*` and the slug,
  kept as `APP_SLUG`, to everything else. Two new tests pin the slug to the
  manifest and the form to each family.
* **`references/v2-platform.md`**:
  * §2 lists the eleven keys and who reads each one, and documents
    `public_paths`, `health_path` and `resources`, which these skills had
    never mentioned.
  * New: "Pages that guests and members both open". There is no optional
    auth mode, and the gateway strips `Cookie` and `Authorization`. The
    section gives the signed-pass pattern two apps already use, and says
    that `user_context` carries no name.
  * New: "Streaming routes - the limits". The limits are 50 streams per
    (app, tenant) per process, 15 minutes per stream and 60 seconds of
    silence; the section covers what each means for a client.
  * §7 explains why the runtime role cannot `setval` and how a migration
    realigns a sequence after an import that kept its ids.
* **`references/capabilities-reference.md`**: which app-id form each family
  keys by and what the wrong one looks like; `404 secret_not_found` named;
  drop credentials when an `os.http.fetch` redirect changes host, and declare
  the redirect's host.
* **`references/sdk-api.md`**: a new "Sessions in a standalone tab" section
  covers the 15-minute cookie, the `fetch` renewal Core injects (MAN-2541),
  and what it does not cover (`EventSource`, `anonymous` routes, an
  `Authorization` header of your own).
* **`SKILL.md`** "What will bite you": the window has no downloads, new tabs
  or clipboard writes, and says what to do instead of each.
* **`manaurum-deploy`**: the `mna_*` token, not the manifest, decides the
  tenant a deploy lands in, and how to check it before the first deploy.

# 3.0.0 - the v1 app path is retired (MAN-3021)

### Why

On 2026-09-28 the platform retired the v1 path for third-party apps (decision
D-144). The iframe-bundle deploy, `POST /api/dev/apps/deploy`, has answered 404
since 2026-08-05, and the public v1 SDK files under `manaurum.com/sdk/` other
than `manaurum.js` redirect to `manaurum.com/developers#v1-retired`. These skills still taught that
path in a "Legacy v1" section at the bottom of each one, and still called it
supported. An agent following them would build an app nothing can deploy.
Removing a documented path is a breaking change, hence the major version.

### What changed

* **Removed the v1 path everywhere:** the "Legacy v1" sections of
  `manaurum-app`, `manaurum-setup` and `manaurum-deploy` (Manifest v1, the
  `manaurum.js` postMessage SDK with its storage and db bridge, the zip-bundle
  deploy, the per-tenant catalog, `mnu_*` deploy tokens and their housekeeping),
  `references/manifest-spec.md`, the v1 half of `references/sdk-api.md` and of
  `references/publishing.md`, and `templates/legacy-v1/`.
* **`mnu_*` is described as what it is now:** a tenant token for MCP clients
  and Drive upload, minted with explicit scopes and unable to deploy. Deploys
  use an `mna_*` credential through `manaurum app deploy` or
  `POST /api/dev/v2/deploy`, and nothing else.
* **No link to a removed public file remains.** `manaurum.js` is still served
  for apps that have not moved yet; `sdk-api.md` names it once, to say it is
  retired and must not be loaded.
* **`mna_*` credentials** are minted at Dev Hub → Credentials (the old
  "v2 Tokens (Beta)" tab name is gone), and the shell's answer to a v2 frame's
  `manaurum:ai-*` (rejected with an error reply) is documented.
* **Frontmatter, `plugin.json` and the README** describe a v2-only plugin.
  `scripts/smoke_tools.py` stops parsing the deleted v1 manifest.

# 2.14.0 - a database that comes up late is retried, not remembered (MAN-3008)

### Why

On 2026-09-25 the provider's hypervisor starved the prod VM of CPU for ten
minutes, and Swarm recreated about half the containers at once. The v2 apps
were up at 18:07:08; the main Postgres accepted connections only at 18:07:58.
Five hosted apps open their pool once in `lifespan` and catch the failure into
a "no database" mode. They served empty 200s behind a green `/healthz` for 43
hours, and Postgres logged nothing, because the apps had stopped asking. A user
found it.

These skills never said how to hold a connection. `DATABASE_URL` was described
as a credential, and what an app does when the database is not there yet was
left to each author. The apps that got it right (a pool opened on first use)
did so by accident of whichever app they were copied from.

### What changed

* **`skills/manaurum-app/references/v2-platform.md`** - a new section, "Your
  database can come up after your container": the rule (never remember a
  failed connection), the ten-line lazy pool with a lock and a connect timeout
  under the gateway's 30 s, and the two shapes that look careful and are not.
  One swallows the failure; the other crashes, and takes the UI and `/healthz`
  down with it until the database is back. The same rule covers a secret or
  anything else fetched from Core at boot.
* **`skills/manaurum-app/SKILL.md`** - one line in "What NOT to do", pointing
  at that section.

# 2.13.0 - a capped page is a centred page, and something checks it (MAN-2849)

### Why

The starter's `.app` set `max-width: var(--container-lg, 1024px)` and nothing
centred it. Every app built from the starter sat on the left edge of any
window wider than 1024px, and four of them - `zapiski`, `zb-announcer`,
`dindex-kb`, `zb-meetings` - carry the line verbatim, because the file is
copied as-is. An owner found it within a minute: dragging the window wider is
the first thing anyone does.

It passed the whole prescribed check. `check_ui.py` had no geometry rule.
`design.md` stated half the rule ("cap the width") in prose. And the Step 3.5
screenshot did show it - at the default 1240px the starter leaves 0px on the
left and 216px on the right - but a one-sided gap in a single picture reads as
"fine" to whoever is looking. The lesson is MAN-2455's again: what a person has
to notice in a screenshot is prose; what the preview measures is a check.

### What changed

* **`templates/v2-starter/src/static/app.css`** - `.app` gets `width: 100%;
  margin-inline: auto`. The toolbar search field stops growing (`flex: 0 1
  320px`, full width on mobile), so it no longer flings its siblings to the
  far edge; `.toolbar-spacer` is the one thing that grows. And a provenance
  line, `manaurum-starter app.css 2.13.0`, which `check_repo.py` keeps equal to
  the plugin version: it is how a deployed app's source says which template it
  was copied from.
* **`templates/check_ui.py`** - fails a page root (the first layout element in
  `<body>`) that caps its width and is not centred by `margin`/`margin-inline`
  `auto`, by the `left: 50%` + `translateX(-50%)` trick, or by a centring
  `<body>`. Only the root is judged: a `max-width` deeper in the page (the
  starter's own `.empty-body`, a fixed toast) is its parent's business.
* **`scripts/linter_mutations.py`** - two red mutations (the MAN-2849 line
  verbatim; the same defect in a `<style>` block) and three that must stay
  **green**: a fixed toast with `max-width: 80%`, a defective rule patched by an
  appended block, and a root centred by `<body>`. The harness now supports
  must-stay-green cases for `check_ui.py`, not only for `check_repo.py`.
* **`templates/preview.py`** - a third badge: `layout centred`,
  `layout OFF-CENTRE - 0px left, 216px right`, or `layout fills Npx` when the
  frame is not wider than the cap and so proves nothing about centring.
* **Step 3.5** - a wide shot (`--window-size=1920,1000`), and "a red badge is a
  failure however good the picture looks".
* **`design.md`** - "cap the width **and centre it**", and a row in the `Never`
  table.
* **A correction:** Step 3.5, the seven rules and `What NOT to do` all said
  `check_ui.py` covers every rule but rule 3. It never checked the first half of
  rule 5, a hover on something inert. The text now says so.

### Not in this release

The deployed apps are not fixed by this, and cannot be from here: `app.css` is
vendored by copy and the platform has no channel into a live app's stylesheet.
That is MAN-1401's real subject. The backend's advisory lint does not get the
new rule either, because it is a hand-kept copy of `check_ui.py` that has
already drifted (MAN-2765); adding a rule to both by hand is the defect class
this release is about.

# 2.12.0 - the migration chapter stops hiding a rule (MAN-2624)

### Why

An app author adding an index to a table that already exists met three checks
before production and all three missed the same rule.

The validator refuses a plain `CREATE INDEX` on a pre-existing table and says
"use CONCURRENTLY". Do exactly that - add the word to the file you already
have - and the deploy refuses the file, because `CREATE INDEX CONCURRENTLY`
cannot run inside a transaction block and the rest of the file needs one. That
second rule lived only in the deploy executor: not in the validator, not in the
CLI's vendored copy of it, not on this page. So `manaurum app
validate-migration` said green under a sentence promising "green here means
green there", and the refusal arrived in production - after the image was
pushed, which on immutable tags costs a version number (dindex-kb 0.6.0,
2026-09-19).

The platform side is fixed in the monorepo (MAN-2622 / MAN-2623 / MAN-2624):
the rule is in both validators now, the pre-push gate reads files one at a
time the way the runner does, and a blocked deploy says why instead of
pointing at an event stream the operator has no job on.

### What changed

`references/v2-platform.md` section 7:

* a new subsection, **"A file that uses `CONCURRENTLY` may contain nothing
  else"** - what Postgres refuses and why the platform resolves it this way,
  that `migration.breaking: true` does not override it, the worked three-file
  shape, and the do-not-write counter-example;
* the context-sensitive tier note now says each **file** is analysed whole and
  one file is all the validator sees at once - `0001_init.sql` creating the
  table does not make a plain `CREATE INDEX` in `0002` additive;
* the local-validation promise says "file by file in the same order", which is
  what makes it true.

`templates/check_app.py`:

* the migration rule defers to the deploy's own AST validator when a copy that
  knows this rule is importable, and reports exactly what the deploy will say.
  Stdlib-only still holds - the import failing is an ordinary outcome;
* the capability is PROBED, not read off a version string. The rule landed in
  the CLI without a version bump, and the wheel authors can actually install
  predates it, so "is it installed" was the wrong question: a stale copy would
  have silently replaced this check with nothing;
* it does NOT guess when no usable validator is there. A text test cannot
  decide this rule - `'a -- b'` inside a string literal eats the rest of the
  line, `DETACH PARTITION "m_2024--old" CONCURRENTLY` reads as a comment, and
  the word inside a string or a nested block comment reads as a request. Core
  settled this in MAN-2510: "regex-based detection is explicitly rejected: the
  AST is the contract." So the run prints a note naming exactly which rules
  went unchecked, and `clean` stops meaning two different things;
* a validator that refuses without a per-statement breakdown is reported
  rather than swallowed.

`scripts/linter_mutations.py`:

* a mutation for the new rule - the shape an author lands on by following the
  validator's advice literally. It runs against a stub validator on
  `PYTHONPATH`, which makes it deterministic AND gives the validator branch
  its first test: CI installs no Python packages, so without a double that
  branch is the one thing nothing ever runs. The stub is a test double, not a
  second opinion - the real verdicts live in the monorepo, behind pglast;
* a mutation may name more than one acceptable wording, because one rule can
  be reported by either engine. Still a substring match: a mutation cannot
  pass on the linter saying something unrelated.

# 2.11.1 — `os.notifications.send_to_user` as the platform actually answers it (MAN-2516)

### Why

The reference taught a request the gateway rejects and a response that hid the
one state that mattered. A hosted app built from it (`zb-vip-crm`, "tell me when
a new lead arrives") sent `deep_link: {app_id, path}` and got `422`; after
switching to `link` it got `200 {"delivered": false}` for every lead, counted the
200 as sent, and marked every lead "notified". Nobody was notified: in-app
notifications were dead for every hosted app on the platform, and the page never
mentioned that a 200 can mean "not delivered".

The platform side is fixed in the monorepo (MAN-2516): in-app notifications from
hosted apps are delivered, a platform-side non-delivery is a non-200, and a
`delivered: false` always says why.

### What changed

`references/capabilities-reference.md`, the `os.notifications.send_to_user`
section, rewritten against the handler:

* the input field is **`link`** (a string handed back to your own app on click),
  not `deep_link`; `title` is optional; `data` is accepted and not stored;
* the output section says to read `delivered`, and lists every `reason` a
  `delivered: false` carries — all of them about the recipient;
* the error table uses the real codes (`user_not_in_tenant`,
  `integration_not_configured`; the old `user_not_found_in_tenant` and
  `missing_provider_credentials` never existed) and adds the new ones:
  `412 in_app_unavailable`, `429 notification_rate_limited` (in-app: 10 per
  hour and 50 per day per app and recipient), `501 sms_unavailable`,
  `502 provider_rejected` /
  `provider_unreachable`, `504 provider_outcome_unknown`, each with whether a
  retry is safe;
* how the click reaches the app (`manaurum:init` `payload.deepLink`, or a
  `manaurum:deep-link` message), and that the SDK does not surface it;
* `capability_not_granted` says how an install ends up without the grant (a
  redeploy never widens an existing grant; strict grants withhold this
  sensitive capability even at first install) and names the way through
  today: the platform operator, until tenant admins get a grant screen
  (MAN-1112, registered in `scripts/open-claims.txt`);
* the click section says to attach the `message` listener synchronously at
  startup, because the shell sends the link once.

Also in the same file: the gateway section no longer says a wildcard `"*"` grant
allows everything. Wildcard grants were removed in MAN-1585.

`references/sdk-api.md`: the four mentions of SDK 2.2.0 now say 2.3.0, the
version `manaurum-v2.mjs` carries. Each statement was re-checked against 2.3.0
(it still reads neither `granted_capabilities` nor `deepLink`, and still has no
window-framing helpers).

# 2.11.0 — the backend contract gets a program that checks it (MAN-2533)

### Why

MAN-2510 named the mechanism, and it is not specific to design:

> **An agent treats as contract what sits in a numbered step marked mandatory,
> and treats everything else as reference material for if there is time left.**

2.9.0 acted on that for the UI: a mandatory numbered step, a machine check, and
a library that resists the mistake. The rest of the SDK never got the same
pass — so everything that is prose today is, by that mechanism, optional today.

The most expensive v2 failure is the clearest case. A route in code that no
manifest rule covers is described **three times** in the skill and was checked
nowhere, while being entirely decidable from the app's own source before a
deploy. The evidence that this is the gap and not carelessness: the acceptance
build for MAN-2510 wrote fifty tests unprompted, and one of them was exactly
this check — the agent wrote the SDK's missing linter itself, because the skill
warns about `route_not_declared` in prose and nothing catches it.

### What changed

**`templates/check_app.py` (new) — the manifest against the code.** Stdlib
only, `python check_app.py my-app`, exit 1 on findings, run on the directory
the deploy packs:

* an `/api/*` route no `runtime.api_routes` rule covers — **including the
  `/api/x/*`-does-not-cover-`/api/x` case**, which is the shape where the
  detail screen works and the list screen 404s;
* a declared route nothing serves;
* an `/agent/*` handler with no user-context verification — that path is on the
  public internet with no gateway in front of it, and nothing will ever tell
  you;
* `runtime.port` disagreeing with what the `CMD` binds, and with `EXPOSE`
  (which is decoration — but a decoration that disagrees is what the next
  reader believes);
* `frontend.entry_point` naming a file that is not there;
* any `.env*` **inside** the app directory;
* a capability called but not declared (403 at the first real use), or declared
  and never called (an over-broad grant a tenant admin is asked to approve for
  nothing);
* `migrations/`: a non-`.sql` file, numbers of mixed width, an anonymous
  `DO $$` block, destructive DDL without `migration.breaking`.

Routes and handlers are read out of **Python** decorators with `ast` — that is
the starter's stack, and importing the app would need its dependencies. For any
other language it says so and skips those two rules; the manifest, port,
capability, `.env` and migration rules still run, because those read files
rather than code.

**Wired the way the UI linter was wired**, because a tool nobody runs is prose
with a shebang: **Step 3.6 (MANDATORY)** in `manaurum-app/SKILL.md`, a line in
`What NOT to do`, a pre-flight in `manaurum-deploy/SKILL.md` that runs both
linters before anything is packed, a test in the starter that runs it against
the starter, and a CI job that holds the reference app to it.

**`templates/v2-starter/tests/test_manifest.py` (new).** Four tests over the
manifest the starter's own suite never had, and the first one is the one worth
copying: every `/api/*` route the *running app* reports is covered by a
`runtime.api_routes` rule. It asks the app rather than the source, so it also
covers a route registered somewhere no decorator scan would look. Plus: no
`/agent/*` path in `api_routes` (declaring it there configures nothing), every
declared `agent_capability` has a handler, and every capability declares
`is_write` — because omitting it is not the same as `false`.

**`scripts/linter_mutations.py` (new) — twenty mutations, one per rule.** A
linter nobody has seen fail is a linter nobody has tested. Each rule in
`check_ui.py` and `check_app.py` gets a copy of the starter with that one rule
broken and a demand for red, and CI runs the lot.

**It immediately found a dead rule.** `check_ui.py`'s `@media max-width` check
only ever ran over `.html`/`.js` — and a media query lives in a stylesheet, so
the rule could not fire on the one file type that carries it. It had been dead
since 2.9.0 and no amount of reading found it; one mutation did.

**And `check_repo.py` now gets the same treatment.** 2.10.0 shipped it with no
negative test at all — the file whose own docstring tells the story of a regex
silently disabled by one byte. Eighteen more mutations cover it, and half of
them are the other direction: prose a person would legitimately write, with a
demand that it stays **green**. Each of those was a real false positive first:

* `` Never write the build context to `/tmp/ctx.tar` `` — the sentence
  teaching the MAN-2456 lesson could not be written, and neither could
  `/tmp/ctx-$$.tar`, which is the *fix* rather than the defect.
* "Write two tests for every capability you use" read as a hardcoded count of
  this repository's own suite.
* "`check_ui.py` catches one of the two ways a hex reaches the markup" produced
  `a hardcoded count of what the linter checks ("one of the")`.
* "MAN-2532 is Done, but it was blocked on a runner for two days" demanded a
  register entry for a closed ticket — which would have filled the open-claims
  register with closed tickets.
* "`scripts/deploy.sh` in YOUR project" was reported as a missing file in this
  one.
* A `.zip` and a `.jpeg` failed the build with `control byte 0x03 … rewrite the
  file with a real editor, not a shell heredoc`. The binary test is now a NUL
  byte rather than a list of extensions somebody has to maintain.

Also real, and fixed: a `!.env.manaurum` line in the starter's `.gitignore`
satisfied the coverage check while git would have tracked the token file
(gitignore's last-match-wins is not `fnmatch`); `doc.parent.parent` let a file
*outside the checkout* satisfy a documented path; `add_argument("-p", "--port")`
made the documented `--port` report as unsupported; and a `;` in the sentence
splitter separated a ticket from its own marker.

**`smoke_tools.py` was testing whatever was on port 8766.** A fixed port plus
"it answered 200" ran the entire suite against an unrelated HTTP server and
produced nine findings blaming `preview.py`, none of which named the real
cause. It now takes a port from the OS and refuses to run unless the page it
gets back is preview's own.

**Three ways CI could pass while failing.** `count=$(pytest --collect-only -q |
tail -1)` swallowed a pytest failure entirely — GitHub's default shell is
`bash -e` with no `pipefail` — and wrote `starter suite: ` with no number,
green; the same pipe hid a crash in the ticket listing. `cancel-in-progress`
applied to `push: main` too, so two merges in quick succession could land a
commit whose build was cancelled. And there is now a **windows** job: these
tools are maintained and run on Windows, `check_repo.py` makes a whole design
decision about the cp1252 console, and CI had never once exercised that path.

# 2.10.0 — the plugin can finally catch its own drift (MAN-2532)

### Why

2.9.0 gave apps a linter. This repository still had nothing: **no automated
checks of any kind, and every PR merged with zero CI runs.** The only detector
of an instruction that had drifted from reality was an agent building an app, a
customer rejecting it, and the agent writing a two-page ticket — which happened
twice (MAN-2439, MAN-2510) before anyone noticed that this *was* the detector.

One afternoon of reading `main` on 2026-09-09 found nine slips, every one of
them mechanically decidable:

* `templates/v2-starter/src/static/app.css` used `var(--container-lg, 1024px)`
  with that token declared nowhere — the reference stylesheet breaking the exact
  rule its own `Never` table names;
* `.gitignore` covered `.env` and `.env.local` but not `.env.manaurum`, the one
  filename the skill tells you to create, next to a paragraph explaining that a
  leaked deploy token cannot be un-leaked;
* `README.md` said "19 tests"; the suite had 24, then 27;
* `SKILL.md` said the linter checked "nine of the seven rules", the CHANGELOG
  said ten, the truth was fifteen;
* `README.md` said `**Version 2.7.3**` while `plugin.json` said `2.8.0`;
* both skills taught a deploy writing to `/tmp/ctx.tar` — a fixed path in a
  shared directory, which is how two sessions crossed build contexts and one
  app was published over another (MAN-2456);
* `.dockerignore` carried a comment describing an effect it cannot have;
* `README.md` called MAN-1393 the blocker for the starter directory, months
  after MAN-1393 and MAN-1397 both went Done;
* Step 3.5 described the opposite of what the browser does.

None of them is serious alone. Together they are the SDK lying about itself,
and an agent has no way to tell which sentence is the stale one.

### What changed

**`.github/workflows/ci.yml` (new) — three jobs, on every PR and on `main`.**
No secrets, no network beyond `pip` for the starter's own pinned dependencies,
and under two minutes.

* **starter** — `pytest` in `templates/v2-starter`, then
  `python templates/check_ui.py templates/v2-starter/src/static`. *The reference
  app is held to the reference linter*, which is the single line that would have
  caught the `--container-lg` bug on the day it landed. The test count is
  printed into the job summary, so it lives in exactly one place.
* **tools** — byte-compiles what the skill tells you to run, feeds `check_ui.py`
  a deliberately broken copy of the starter and fails if it stays green (a
  linter never shown to fail is a linter nobody has tested), and runs
  `scripts/smoke_tools.py`.
* **docs** — `scripts/check_repo.py`.

**`scripts/check_repo.py` (new) — the documents against the repository.**
Stdlib only, `path:line: message` findings that always name the file first.
Eleven checks, each one a slip from the list above: one version string across
four files; every `templates/…` / `references/…` path a document names exists;
every quoted `§ "Heading"` citation resolves; every `Step N` reference has a
Step N; no hardcoded count of tests or of what the linter checks (and the
"seven rules" heading is checked against the list under it); no control byte in
any source file; no fixed `/tmp/<name>` in a shell recipe; the starter's ignore
files cover `.env.manaurum` and the `.dockerignore` still carries the note
correcting its own `migrations/` line; every documented flag is one the tool
accepts; and two measured facts that live in two files at once must still agree
there.

**`scripts/smoke_tools.py` (new).** `preview.py` is a server a MANDATORY step
tells you to start, and `version_check.py` is a hook whose every failure path is
a deliberate silent success — so a hook that raises on line 3 looks exactly like
a hook with nothing to report. This starts both. It checks preview's four
fixture behaviours (exact, longest `/prefix/*`, method-qualified, and the
`{"status": 500}` envelope), because those are what make *empty*, *could not
load* and *still loading* three different screenshots instead of one; and it
checks that `version_check.py` prints **nothing** when the copy is current.

**`scripts/open-claims.txt` (new).** Nothing offline can tell you MAN-1393
closed. So every sentence in a live document claiming some ticket's work is
still outstanding needs a line here with the state as last verified and the
date — enforced both ways, so the file cannot rot into a list of closed
tickets. CI prints it on every run.

**The drift itself, fixed.** The `/tmp/ctx.tar` recipes now use a per-run
`mktemp -d` with a cleanup trap; the MAN-1393 and MAN-1397 claims are gone; the
three counts are sentences instead of numbers; a stale `§ "Legacy v1 deploy"`
citation now names the heading that exists.

**One correction that is not cosmetic.** `references/v2-platform.md` still said
`is_write` was *declarative only — the runtime ignores it for hosted apps*.
That stopped being true on 2026-08-21 (MAN-1425/MAN-1872): the manifest value is
persisted and read, **but the column is nullable and NULL is not `false`** — a
capability that omits the key falls back to `is_write=True`, so a reader that
says nothing is journalled, confirmation-gated and excluded from cross-app
insight. Write `"is_write": false` explicitly. The starter's `read_my_note` now
does.

# 2.9.0 — a rule a program checks (MAN-2510, MAN-2455)

### Why

2.8.0 put the design rules in the body of the skill, added Step 3.5 and shipped
`preview.py`. A week later a second app — technically flawless again, every
platform trap cleared on the first attempt — was rejected on sight again, by an
agent that had the rules in its context.

The mechanism is worth naming, because it is not carelessness: **an agent treats
as contract what sits in a numbered step marked mandatory, and treats everything
else as reference material for if there is time left.** Beside that sits
`app.css`, and copying it looks and feels like the design step being done — the
UI assembles, it resembles the template, every technical check is green. A rule
in another file loses to an artifact in your hands.

So 2.9.0 is mostly not new rules. It is checks, a library that refuses to build
the wrong thing, and one honest promotion of design into the mandatory part.

What the second app shipped, all of it described in `design.md` already:
`<button class="row">` instead of `<li class="row">` (which is why the owner saw
"the list is not full width, the rows look like buttons"), a tab bar as
navigation, `var(--text-muted, #666)` with four token names that exist nowhere,
and a card per field. And a fifth, from MAN-2455: an app that answered the
handshake and read `e.data.appearance` instead of `e.data.payload.appearance`,
so it applied nothing and sat light inside a dark desktop for four days while
every check stayed green.

### What changed

**`templates/check_ui.py` (new) — the UI contract, mechanically.** Fifteen
checks over the app's static files, covering six of the seven rules (a sentence
in a badge is the one only a person can see): a `var()` whose token is declared nowhere (a hex in
a fallback is a hardcoded colour wearing a token's clothes), hex or `rgba()` in
markup, `style=` and `element.style.*`, `alert`/`confirm`/`prompt`, a
`tab`/`tabs`/`sidebar` class, `@media max-width`, `<button class="row">`, a click
target with no `is-interactive`, more than one primary button in a view, and a
missing `manaurum:ready` / `data-appearance` / `data-device` / `payload` read.
Stdlib only, `python check_ui.py src/static`, exit 1 on findings.

Three things it does deliberately: it strips comments first (without that, the
sentence "never call `confirm()`" in a comment is itself a finding — that is how
its first run failed); it treats `*.css` and `<style>` blocks as the place
colours are allowed to live and everything else as markup; and it counts primary
buttons **per `data-view`**, because a hash-routed app keeps every view in one
file and each view is allowed one.

**Step 3.5 is now `(MANDATORY)` in its heading, and the linter is its first
step.** The only signal of obligation that an agent reliably reads is the one in
the heading — Step 2.5 had it, Step 3.5 did not. The linter runs before the
screenshots because it is cheaper and it catches what a picture cannot show.

**The seven rules gained the two sentences that were missing.** Rule 2 now says
where the values arrive (`e.data.payload`, not `e.data`) and what the failure
looks like, because an agent that already has a handshake reads "appearance
comes from `manaurum:init`" as "yes, I do that" and never re-opens Step 2.5.
Rule 5 now runs both ways: hover if and only if the click does something — so a
row with a handler must carry `.row.is-interactive`, and stays an `<li>`.

**`What NOT to do` has a UI line.** It is the only section on the page whose
title is "what not to do", so everything absent from it reads as "not what you
get sent back for". Six technical entries, and the thing that actually got two
apps rejected was not among them.

**`preview.py`:**
- fixtures match the way `runtime.api_routes` does — exact, then longest
  `/prefix/*`. An exact-key dict could never answer `/api/items/42`, so the
  detail screen photographed as an empty card, every time;
- a fixture may be an envelope — `{"status": 500}`, `{"delay_ms": 1500, "body":
  …}` — so that *nothing yet*, *could not load* and *still loading*, which
  `design.md` asks you to distinguish, are all photographable rather than one of
  three;
- `?width=` / `?height=` size the app's frame inside a large browser window. The
  whole contract is written for a window that is "often 900px", the recommended
  shot is 1240×1000, and both headless browsers floor their own viewport at
  ~500px — so this is the only honest way to photograph the narrow case;
- a second badge: **appearance applied / appearance IGNORED**, read back off the
  framed page's `<html>`. MAN-2455's bug fails this badge with no judgement call
  from anyone.

**The starter stops making the mistakes easy to make.** `.row-title` and
`.row-sub` get `display: block` (as `<span>`s they ran together on one line and
`text-overflow: ellipsis` did nothing); `.row` gets the button neutralisers that
`.btn` four blocks below it already had, plus a comment saying a row is an
`<li>`; `a.btn` loses the underline; `.toolbar` and `mark` exist (the second so
that search highlighting is not reinvented in the banned yellow); and where
`.tab`, `.tabs`, `.sidebar` and `.switch` would be there is now a comment
saying they are absent on purpose. A missing class and a gap in the library look
identical, and that is how a tab bar gets built.

**Hash routing moved into the starter and into Step 0.** `index.html` ships an
eight-line router, two `data-view`s and a list whose rows are `<li class="row
is-interactive">` with one delegated handler and a keyboard path. The
requirement used to arrive in Step 3.5, when the app already exists and
retrofitting it is expensive — so it was skipped, and every screenshot only ever
showed the first screen.

**`references/design.md` gained the token table**, name by name, each with what
it is and which neighbour it is not. There was no list anywhere, so names were
invented by analogy — and an invented name in a `var()` fallback breaks no
stated rule while being exactly the hardcode the rules forbid. Plus the two
`Never` rows for that and for a silent click target.

**The plugin now says when your copy of it is stale** (`hooks/hooks.json` →
`scripts/version_check.py`). Measured in MAN-2510: a session loaded 2.7.2, the
cache received 2.8.0 fifty-one minutes later, and the session kept reading 2.7.2
paths for another day — the release meant to prevent that app's failure missed
it by an hour and was never noticed. The SessionStart hook compares this copy
against its siblings in the cache, says so in one paragraph when it is behind
(or when its directory carries `.orphaned_at`), writes `STALE.md` into the
superseded directory and a `current` pointer beside it — because SKILL.md
teaches agents to find the plugin root by walking the filesystem, and two
directories that differ only by a hidden marker are indistinguishable. It prints
nothing when the copy is current, and it cannot fail a session.

`SKILL.md` also states its own version at the top and tells the agent to look at
the parent directory of `<plugin>` before trusting what it is reading.

**The deploy recipe stopped using shared filenames** (MAN-2456). Both skills
told everyone to write the build context to `/tmp/ctx.tar` and the request body
to `/tmp/deploy.json`. `/tmp` is shared: on 2026-09-08 two sessions deploying
two apps on one machine collided on exactly this, and one of them shipped the
other's archive — phases streaming healthily, `activated` reported for an app it
had never touched, while its own app stayed on the old version. Now: a per-run
`mktemp -d`, and the slug echoed from the manifest before the upload, because a
run that reports success for the wrong app is worse than one that fails.
# 2.8.0 — the design rules travel with the skill, and somebody looks at the app (MAN-2439)

### Why

An app built on 2.7.2 cleared every technical trap on the first attempt —
manifest v2, `runtime.port`, default-deny `api_routes` (including the
`/api/x/*`-does-not-cover-`/api/x` edge), managed Postgres, migrations, the
`manaurum:ready` handshake, a secret through `os.secrets`, deploy and job
polling. Its interface was then rejected on sight, and correctly: a tab bar as
navigation, badges holding whole sentences, a primary button in every row of a
list, and an app that stayed in its own palette inside a dark desktop.

All four are written down in `references/design.md`. That file was never opened.

The mechanism matters more than the miss. The skill pointed at `design.md`
twice, and both pointers read as further reading — while a complete, correct
`app.css` sat one directory away. Copying the stylesheet *feels* like the design
step: the UI assembles, it looks like the template, and every technical check
passes. Nothing in the skill said otherwise, and two things in it actively
helped the failure along:

- **The handshake snippet in Step 2.5 dropped the payload on the floor.** It
  answered `manaurum:ready` and read nothing else — so an app that followed this
  skill to the letter ignored `appearance` and `accent` by construction. That is
  the third violation, with a recipe.
- **Nothing ever asked anyone to look at the result.** Rules cannot survive a
  build that is never seen. All four failures were obvious in the first
  screenshot and invisible in the diff.

One correction to the report, checked rather than assumed: the starter template
does **not** ignore the theme. `index.html` writes `data-appearance` /
`data-accent` on `<html>` and `app.css` carries the dark block, all eight
accents and `color-scheme` — that landed in 2.7.0 (MAN-1436) and is present in
the published 2.7.2. Verified by framing the unmodified starter and
photographing it in both appearances. The gap was in the skill's own snippet,
not in the template.

### What changed

- **`manaurum-app/SKILL.md` — "The seven rules an app gets sent back for."**
  Seven lines in the section that already tells the agent to copy the look,
  before the first file is written: no tab bar or sidebar; appearance and accent
  from `manaurum:init`; a badge is a word, not a sentence; one primary button per
  view; hover only on what is clickable; no hex or inline `style=` in the
  markup; no `alert()` / `confirm()` / `prompt()`. The link to `design.md` stays,
  but the checklist works without following it.

- **`manaurum-app/SKILL.md` Step 2.5 — the handshake snippet now applies the
  theme.** One listener, both jobs, because both arrive in one message; it also
  handles `manaurum:theme-change`. With a paragraph saying plainly that
  answering the handshake and discarding the payload is a shipped bug, not a
  shortcut.

- **`manaurum-app/SKILL.md` Step 3.5 — "Look at the UI before you deploy it."**
  A mandatory last step of building an interface, in the same position as
  "check `/healthz`" after a deploy: serve with stubs, screenshot light and
  dark, then open the pictures and criticise them out loud against the seven
  rules. Includes the three things that make the procedure lie to you: headless
  cannot click, so a view reachable only through a button needs a URL fragment
  before a screenshot can reach it; a fresh `--user-data-dir` keeps the run
  independent of an open browser profile, which is one of the ways the command
  exits writing no file and printing no error; and the layout viewport floors at
  ~500px, so `--window-size=390,800` crops rather than reflows and a good phone
  layout photographs as broken. Both browser claims re-measured for this
  release — Chrome and Edge, `--headless=new`.

- **`templates/preview.py` + `templates/preview-fixtures.json` (new).** A
  stdlib-only preview server, no install and no dependencies: your static files,
  a JSON stub for every `/api/*` call, and a `/__shell` page that frames the app
  the way the desktop does — the shell's exact sandbox (so `alert()` is as dead
  as it is in production), a real `manaurum:init` carrying whichever
  `appearance`, `accent` and `device` you ask for, and a red badge when
  `manaurum:ready` never comes back. It lives beside the app directory, never
  inside it: everything inside is packed into the deploy. Every API hit is
  logged, which is the cheapest way to find a route missing from
  `runtime.api_routes` before it 404s in production.

- **`manaurum-app/references/design.md` now opens with a `Never` table.** Nine
  rows, each a rule an app has shipped without and been sent back for, each with
  one line of why. The rules were all in the file already — spread through the
  prose of six sections, where they were visible only to someone reading the
  whole page.

- **`manaurum-deploy/SKILL.md`** — the pre-flight section now sends you to Step
  3.5 first if nobody has looked at the app yet.

- **`README.md`** — `templates/preview.py` documented under Templates, and the
  "no local dev loop" gap corrected: the frontend now has one, the backend still
  does not.

Version note. The report expected 2.7.3 to be the `os.drive.*` work; it is not —
2.7.3 is the scroller rule (MAN-2112), and `os.drive.*` was documented back in
2.1.0 (MAN-608). Either way nothing was left unpublished: 2.7.3 has been on
`main` since it merged, and a plugin install caches per version, so a machine
sitting on 2.7.2 has a stale cache rather than an old release. `/plugin` →
update brings 2.7.3 and this release together.

# 2.7.3 — an app owns its scroller, and the SDK says so out loud (MAN-2112)

### Why

The skill had nothing to say about scrolling. 3,816 lines across `SKILL.md` and
eight references, and `overflow` appeared in exactly one of them — about a query
cardinality cap. `scroll` appeared nowhere at all. So agents building v2 apps
kept shipping the same bug: content clipped at the window edge with no scrollbar
anywhere.

It is structural, not careless. The OS window's content area *is* `overflow:
auto` and it *does* scroll a **builtin** app. It can never scroll an iframe app:
the iframe is `height: 100%` of that same box, so it is never taller than the box
and the shell's scrollbar never appears. An iframe app scrolls itself or it does
not scroll — and nothing said so. Meanwhile every design mockup fakes an OS
window with `overflow: hidden`, which ports perfectly while the inner scroller it
was paired with does not, because the real layout gets rewritten around it.

Finance v2 shipped exactly this on its desktop layout, from its first commit. The
public P&L share page had the same failure in June (MAN-340). MAN-1050 is the
same "one scroll container" rule broken from the other side — a *nested* scroller
trapping the user, fixed by deleting it.

### What changed

- `references/design.md`, Window rules — **"One scroll container, and it is
  yours"**. The first draft of this rule was wrong and review caught it before
  merge: `overflow: auto` on its own changes nothing, because a block with auto
  height grows to fit its content and never overflows. A fixed shell needs all
  three of a flex-column root, `flex: 1` **and** `overflow: auto` on the element
  holding the content, and `min-height: 0` on the flex items in between.
- `manaurum-app/SKILL.md` — an entry in "What will bite you", which already opens
  with the right frame: it works in a tab and breaks in the desktop.
- `manaurum-deploy/SKILL.md` — a pre-flight step with an actual procedure: the
  smallest window you support, enough data to overflow it, and the browser
  console as the observable.
- `templates/v2-starter/src/static/app.css` — the starter was already correct
  (`min-height: 100%` on `.app`, no clip on the root) by accident rather than by
  rule. Now the rule sits above `html, body { height: 100% }`, so a port does not
  overwrite it silently.

Platform-side, in the same ticket: both SDK artifacts measure this at run time
and console-error with the offending element (`manaurum.js` 1.12.0,
`manaurum-v2.mjs` 2.3.0). The check is scoped to "a window-sized element clips
and nothing on the page scrolls at all" — verified in Chromium against seven
healthy layouts that must stay silent, including a collapsed panel, a tall line
clamp and a decorative hero, all of which an earlier revision flagged. Opt out
with `init({ layoutCheck: false })`; `app.checkLayout()` forces a measurement
even then.

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

# 2.0.0 (2026-05-07) — Platform v2 is the default flow

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

# 1.15.0 (2026-04-30) — F1.5 evolution — `renamed_from` + dedicated `include`

### Added

- **`renamed_from` field-level hint** documented in `manifest-spec.md`. Set `"renamed_from": "<old_name>"` on a dedicated field and the diff engine emits `ALTER TABLE RENAME COLUMN` instead of the default DROP+ADD on next deploy. Additive — no data loss. Drop the hint on the deploy after the rename. Validator R9 rejects shared-only use, self-rename, and source-name-still-exists collisions.
- **R9 row** in the cross-field rules table.
- **`include` for dedicated entities** documented in `sdk-api.md`. The shared-storage `include` had a convention-based FK lookup (child must have `<parent>_id` field); dedicated uses the explicit `references` declaration. Single indexed `IN(...)` query per child type — no N+1. Caps unchanged: 4 includes max, 100 children per parent.

### Notes

- Pure-documentation release. Backend changes shipped in Manaurum PR #341 (merged + deployed 2026-04-30). Runtime API and SDK build unchanged — same `app.db.list('parent', { include: [...] })` works against either tier.

# 1.14.0 (2026-04-30) — F1.5 hardening — R8 quotas + destructive add-NOT-NULL

### Added

- **R8 row** in the cross-field rules table (`manifest-spec.md`). Per-app quotas now enforced by the validator: max **50** entities per app, max **100** fields per entity, max **20** compound indexes per entity. Generous; you should not hit these in a real app — the point is to surface a clear early reject if a manifest is accidentally ballooning (codegen bug, abuse).

### Changed

- **Additive vs destructive table** in `manifest-spec.md` — adding a `required: true` field to an existing entity is now classified as **destructive** by the diff engine. Previously it would slip through as additive and PG would reject the ALTER on populated tables with a generic error. Now the deploy returns a clean `rejected_destructive_change` with a description pointing at the safe two-step pattern (add as optional → backfill → tighten to required), or the dev passes `allow_destructive=true` to make the intent explicit.

### Notes

- Pure-documentation release — runtime API and SDK build unchanged. Companion to Manaurum PR #339 (validator + diff engine + telemetry).

# 1.13.0 (2026-04-30) — graduated storage (`storage: "dedicated"`)

### Added

- **Dedicated storage tier documented.** New "Dedicated storage" section in `manaurum-app/references/manifest-spec.md`: when to use it (>10k rows / per-tenant `UNIQUE` / FKs / compound indexes), full example, the field-level extras (`unique`, `references`), the entity-level `indexes[]` array, the R1–R7 cross-field rules, additive vs destructive change classification, and the "runtime is the same" reminder.
- **SKILL.md updated** so the Database quick overview surfaces both tiers (shared = EAV-pivot, default; dedicated = real PG table). Validation rules table updated — `entities[].storage` is no longer marked "only `shared`". The same `app.db.create / get / list / update / delete` works against either tier; the platform routes behind the unchanged interface.

### Why this matters

Until now `storage: "dedicated"` was reserved-but-rejected. Apps that grew past EAV-comfortable size had to either accept slow EAV reads or ask the platform team for an Alembic migration + Core PR. With the F1.5 graduated-storage path live (Manaurum PR #328 merged + deployed on prod 2026-04-30), an external developer writes one word in the manifest and gets a real table — real columns, real indexes, real FKs, real `UNIQUE` — auto-generated and migrated by the deploy pipeline. The boundary "go to Core via PR" moves from "I need one JOIN or index" up to "I need shell-level intervention".

### Notes

- Pure-documentation release — no template change. The runtime API and SDK build are unchanged.
- Storage tier is a one-way decision per entity. Plan before first deploy: changing `storage` between `shared` and `dedicated` after deploy is rejected as a destructive transition.
- (Plumbing only: 1.12.0 shipped the Component Library docs but missed the `plugin.json` version bump — this release lands at 1.13.0 to keep the cache directory layout monotonic.)

# 1.12.0 (2026-04-30) — manaurumOS Component Library

### Added

- **`manaurum.mul.*` documented end-to-end.** New "Component Library (MUL)" section in `manaurum-app/references/sdk-api.md` covers `mul.list()`, `mul.search(query, filters?)`, `mul.get(id)` — thin same-origin wrappers over the public read-only `/api/library/*` endpoints. Includes wire format, build-time vs runtime guidance, and the "no permission required" note (the library is curated and unauthenticated).
- **`SKILL.md` quick overview** updated to surface the library as a first-class building block. Step 2 (design) now nudges devs to browse the catalogue before drawing from scratch.
- **`design.md`** opens with a "don't design from scratch when you can borrow" pointer to the library.

### Notes

- Underlying surface ships in PRs #325 (HTTP API + catalogue UI at `/library`, merged), #326 (SDK v1.9.0 helpers, merged), #327 (App Builder catalogue injection under `experiment.app_builder_uses_library`, merged).
- The library is curated, public, and read-only. No tenant scoping, no auth headers — same-origin fetch is enough. Iframe apps with strict CSP `connect-src` should bake chosen components into the bundle at build time rather than fetching at runtime.
- Pure-documentation release — no template change.

# 1.11.0 (2026-04-28) — db.batch (atomic multi-write)

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

# 1.10.0 (2026-04-28) — db.list child-fetch via include

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

# 1.9.0 (2026-04-28) — db.aggregate

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

# 1.8.0 (2026-04-28) — db.list filter operators + entity immutability flags

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

# 1.7.0 (2026-04-28) — runtime AI API

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

# 1.6.0 (2026-04-27) — runtime Database API

### Added

- **`manaurum.db.*` runtime API documented end-to-end.** New "Database API" section in `references/sdk-api.md` covers `create`, `get`, `list` (with pagination + indexed sort), `update` (full replace), and `delete` (soft). Includes wire format (postMessage type → HTTP route), error table mapping `422 EntityTypeNotDeclared`, `404 record_not_found`, `422 FieldNotIndexedError`, etc.
- **Manifest ↔ runtime bridge documented** in `references/manifest-spec.md`. Explains that declaring `entities[]` at deploy time is what enables `manaurum.db.*` calls at runtime, with a worked example showing why undeclared types and unindexed sort fields fail.
- **`SKILL.md` quick-overview updated** to make `db.*` the first-class persistence path; `storage.*` / `files.*` / `collections.*` demoted to a single "legacy runtime APIs" line.

### Changed

- The "Quick overview (v1.5 SDK)" bullet pair in `manaurum-app/SKILL.md` now leads with the manifest-gated `db.*` API.

### Note

This release is purely documentation — the underlying runtime has been live since W4.3 (`backend/app/routes/app_data.py` + the `manaurum.db.*` block in `frontend/public/sdk/manaurum.js`). No backend or SDK shipping change.

# 1.5.0 (2026-04-27) — BREAKING: tenant-aware Deploy API

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

# 1.1.0 (2026-04-08)

### Added
- **UI Kit reference**: comprehensive design system with exact styles from built-in apps — cards, buttons, inputs, labels, badges, toggles, sidebars, tabs, task cards, section headers, empty/loading states
- **Theme-aware template**: `templates/theme-aware-app.html` demonstrating all design patterns with automatic Smoothie/XP switching
- **Internal hosting docs**: updated publishing reference with paste HTML and upload ZIP hosting on ManAurum (no external hosting needed)
- **Quick-create API docs**: `POST /api/developer/apps/quick-create` for one-step app creation

### Changed
- Design guidelines expanded from basic colors/fonts to full component library
- Publishing flow updated to reflect Telegram-style creation (name only, slug auto-generated)

# 1.0.0 (2026-04-08)

### Added
- `manaurum-app` skill — generate apps from prompts with SDK, manifest, theme support
- `manaurum-deploy` skill — hosting setup, publishing (private/unlisted/public)
- `manaurum-setup` skill — scaffold new project from scratch
- SDK API reference (all postMessage events, SDK methods, 7 permissions)
- Manifest specification (validation rules, field reference, window presets)
- Design guidelines (Smoothie/XP themes, colors, typography)
- Publishing flow (private → unlisted → public, review process)
- Templates: hello-world.html, manifest.json

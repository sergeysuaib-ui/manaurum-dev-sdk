# Dimension: gateway — app gateway, request auth, runtime environment

SDK: `C:\dev\wt\sdk-audit` @ 6f52dce (3.1.0). Platform: SNAP @285c8a8.
Paths below: SDK relative to the SDK root; platform as `<path>:<line> @285c8a8` (backend paths are under `backend/app/`).

## Findings

### GW-01 — CRITICAL — A `user_context` is not bound to one app, and a client-sent `X-Manaurum-User-Context` reaches the container first. The SDK calls the header "the only trustworthy identity", and its verifier checks neither `app_id` nor `tenant_id`
- **SDK:**
  - `templates/v2-starter/src/main.py:28-29`: "that header is the only trustworthy caller identity you get".
  - `templates/v2-starter/src/auth.py:61-83` checks the signature, iss, aud and exp, then returns `tenant_id` and `app_id` without comparing them to anything.
  - `skills/manaurum-app/references/v2-platform.md:247`: "Whatever identity you need arrives as `X-Manaurum-User-Context`".
  - `SKILL.md:234` says the same.
- **Platform:**
  - `routes/v2_app_gateway.py:564-573 @285c8a8`: `_filter_request_headers` drops only hop-by-hop headers plus `authorization` and `cookie`. An inbound `x-manaurum-user-context` passes through.
  - `:912`: the minted token is added under the key `"X-Manaurum-User-Context"`. That key differs in case from the lowercase key Starlette produced, so on a `user` route both headers are sent, and the client's copy comes first.
  - On `anonymous` routes and on pages, the client's copy is the only one, forwarded unchanged.
  - `services/v2_apps/user_context_jwt.py:70-71`: every app gets the same `iss` / `aud` (`manaurum-core` / `manaurum-app`).
  - Core already treats cross-app replay as a real threat. `routes/capability_gateway.py:867-896` refuses "a same-tenant replay by another app" through an `app_id` check. No container-side equivalent exists.
  - Every container shares one overlay network (`services/v2_apps/stack_generator.py:16-24, 291`), so another app's container can also call `http://v2-app-<slug>-<t8>:<port>/api/...` directly.
- **Reproduced locally (no network):** `scratchpad/gw-probe/probe.py` runs the SNAP `proxy_v2_app` with stubbed dependencies and a mock container.
  - `GET /api/me` (a `user` route) carrying a client header gave: "container got 2 header(s); first = RELAYED-TOKEN".
  - On an `anonymous` route: "1 header(s); first = RELAYED-TOKEN".
  - Starlette `headers.get`, which the starter uses, returns the first value.
- **Verdict:** CONFIRMED for the code path (local run used httpx 0.28.1; prod pins 0.27.2, whose header-merge logic is the same). Behaviour at the prod edge is LIKELY. Whether Traefik strips the header is in Questions.
- **Impact:** A malicious app X gets a fresh token for every user who opens X. It can replay that token to app Y within 60 s, through the public URL or directly over the overlay network. Y's starter-derived verifier then accepts the victim's identity. The tenant does not matter either, because nothing compares `tenant_id`.
- **Fix:** both.
  - Platform: drop any inbound `x-manaurum-*` header case-insensitively in `_filter_request_headers`, and set the minted header under a lowercase key. Consider an app-specific `aud`.
  - SDK: `verify_user_context` must require `app_id == APP_SLUG` and `tenant_id == MANAURUM_TENANT_ID`. Never read the header on `anonymous` routes. Fix the "only trustworthy identity" text in main.py, SKILL.md and v2-platform.md.
- **Related:** MAN-1588 (similar class, but about the capability header). No existing ticket found.

### GW-02 — HIGH — "There is no readiness probe" appears in 4 places; the probe has existed since 2026-07-25
- **SDK:**
  - `skills/manaurum-deploy/SKILL.md:193`: "There is **no readiness probe anywhere in the hosted deploy path.**"
  - `:464`: "succeeded only means Docker accepted the spec. There is NO readiness".
  - `SKILL.md:654`: "There is no readiness probe on the hosted path".
  - `references/publishing.md:42`: "There is no readiness".
  - All four contradict the SDK's own `references/v2-platform.md:229`, which is correct.
- **Platform:**
  - `services/v2_apps/production.py:3955-4005 @285c8a8`: "MAN-1369 — only now do we find out whether the thing we just deployed actually serves". On failure it rolls back and raises `DeployStepError`.
  - The probe is on unless an operator sets `MANAURUM_V2_READINESS_PROBE=0` (`:1059`).
  - It waits for Swarm convergence on the new image first (`:1236-1271`).
  - MAN-1369 merged 2026-07-25 (`b25cc8011`, `960ea5e6e`).
- **Verdict:** CONFIRMED.
- **Impact:** Developers are told a green deploy may not be serving, and that they must hand-roll a curl loop. A red `readiness_failed` deploy then has no explanation anywhere in the deploy skill.
- **Fix:** SDK. Say that `succeeded` means the new task answered HTTP on `runtime.port`, strictly on `health_path` if one is declared, within 90 s. On failure the service is rolled back, or scaled to zero on a first deploy. Document the `readiness_probing`, `readiness_ok` and `readiness_failed` phases.

### GW-03 — HIGH — "A wrong port deploys green and then 502s on every request" appears in about 12 places; with the probe it is now a failed deploy
- **SDK:**
  - `SKILL.md:283`, `:555`, `:682` ("502 (serving, after a green deploy)").
  - `skills/manaurum-deploy/SKILL.md:37`, `:341`.
  - `skills/manaurum-setup/SKILL.md:152`, `:237`.
  - `templates/check_app.py:14`, `:333`, `:347` ("Traefik routes to the manifest's port, so this deploys green and 502s").
  - `README.md:36` ("Traefik targets `manifest.runtime.port`").
  - `templates/v2-starter/README.md:88`.
- **Platform:**
  - The probe dials the same `<service>:<runtime.port or 80>` the gateway uses (`services/v2_apps/production.py:1128-1137 @285c8a8`). A wrong port or a loopback-only bind gives `ConnectError`, then `ReadinessError`, rollback and a failed job (`:1277-1305`, `:3974-4005`).
  - Separately, Traefik never targets the app port. It routes to the Core backend with `addPrefix /apps/<slug>` (`services/v2_apps/traefik_yaml.py:236-246`), which `SKILL.md:294` states correctly.
- **Verdict:** CONFIRMED.
- **Impact:** The symptom table points at the wrong signal. A port mismatch now shows up as a failed deploy with `readiness_failed`, not as a 502 later. The README and check_app also misstate who dials the port.
- **Fix:** SDK. Rewrite the symptom as "deploy fails at readiness (connection refused on `<service>:<port>`) and is rolled back", and change "Traefik" to "the gateway" in README.md:36 and check_app.py. Keep "502 after green" only for a container that dies after activation.

### GW-04 — HIGH — "/agent/* is reachable from the public internet; Traefik goes straight to your container" has been stale since MAN-1432 (2026-07-27)
- **SDK:**
  - `references/v2-platform.md:117`: "anyone on the internet can POST `/agent/<name>`… Verified 2026-07-26".
  - Also `v2-platform.md:156`, `:281` ("routes `<app_id>.apps.manaurum.com` to it via Traefik").
  - `README.md:38`; `SKILL.md:554` ("An open endpoint on the public internet, indefinitely").
  - `templates/check_app.py:16`, `:277-279`, `:290`.
  - `templates/v2-starter/src/agent_routes.py:19-21`; `templates/v2-starter/README.md:117-119`; `templates/v2-starter/tests/test_manifest.py:12`; `tests/test_routes.py:6`.
  - These contradict `SKILL.md:294`: "Traefik never talks to your container directly".
- **Platform:**
  - `routes/v2_app_gateway.py:98` sets `_RESERVED_PREFIXES = ("/agent/",)`.
  - `:795-796`: `/agent`, plus case and double-slash variants, gets 404 `route_not_declared` before anything reaches the container.
  - Traefik routes the host to the Core backend (`services/v2_apps/traefik_yaml.py:236-246`).
  - Fixed by MAN-1432 (`821af49e0`, 2026-07-27); the platform docs were corrected in MAN-1444 (`e04501bde`).
  - The verification still matters, for a different reason: every container shares the overlay network (`services/v2_apps/stack_generator.py:16-24`), so any other app's container can POST `http://<service>:<port>/agent/<name>`.
- **Verdict:** CONFIRMED.
- **Impact:** The advice (verify the JWT) is still right, but the reason is wrong. That undermines trust in the rest of the page and hides the real attacker, which is other tenants' apps on the shared network (see GW-01).
- **Fix:** SDK. Replace the stated reason everywhere: "the public URL refuses `/agent/*` (404); the path is reachable from every other container on the shared overlay, so verify, and check `app_id`/`tenant_id` (GW-01)."

### GW-05 — HIGH — `health_path` "is not reachable from outside" is false
- **SDK:**
  - `references/v2-platform.md:229`: "straight to your container… so it needs no `api_routes` entry and is not reachable from outside."
  - This contradicts `v2-platform.md:245` and `SKILL.md:251` ("`/healthz`… always reach your container anonymously"), and `manaurum-deploy/SKILL.md:206-218`, which tells you to curl the public `/healthz`.
- **Platform:**
  - The probe does call the container directly (`services/v2_apps/production.py:1135-1137 @285c8a8`).
  - But any non-`/api`, non-`/agent` path on `<slug>.apps.manaurum.com` is proxied anonymously (`routes/v2_app_gateway.py:817-863`). It is gated only for top-level document navigations to non-public pages, so a curl or fetch gets it.
  - The platform's own schema has the same false sentence: `services/_schemas/manifest_v2.schema.json`, `runtime.health_path.description`, "is never reachable from outside".
- **Verdict:** CONFIRMED.
- **Impact:** A developer who trusts this sentence puts diagnostics such as config, DB status or versions on a "private" health path that is in fact public.
- **Fix:** both, the SDK sentence and the schema description. It is reachable unless it lives under `/api/` (then default-deny applies) or `/agent/`.

### GW-06 — HIGH — The MAN-1899 sentence survived 3.1.0: "the `runtime` sub-object is *not* strict"
- **SDK:** `references/v2-platform.md:24`: "The `runtime` and `metadata` **sub**-objects are *not* strict… `runtime.port` and `runtime.egress_allowed_hosts` work (real, read by Core, just undeclared)… a typo like `runtime.byo_endpoint_url` passes validation". The same file says the opposite at `:203` and `:310`.
- **Platform:** In `services/_schemas/manifest_v2.schema.json` @285c8a8, `runtime.additionalProperties` is `false` and `port` is declared ("Formally declared now that `runtime` is additionalProperties:false"). Only `metadata` is non-strict.
- **Verdict:** CONFIRMED.
- **Impact:** This is exactly the lesson from the audit context: the CHANGELOG says five places were fixed, and this sixth one still says a typo deploys green.
- **Fix:** SDK. Make the line about `metadata` only.

### GW-07 — HIGH — The starter says the token has no `workspace_id`; it always has one on gateway routes
- **SDK:** `templates/v2-starter/src/auth.py:31-34`: "There is deliberately no `workspace_id` — the token does not carry one, so do not key your data on a workspace". `UserContextClaims` drops it. This contradicts `references/v2-platform.md:262`, which lists `workspace_id`.
- **Platform:**
  - `routes/v2_app_gateway.py:904-911 @285c8a8` always passes `workspace_id=str(session.workspace_id)`.
  - `agent/v2_capability_dispatch.py:133-140` passes it when the context has one.
  - `services/v2_apps/user_context_jwt.py:133-136` puts it in the payload.
  - The platform's vendored `services/v2_apps/_manaurum_runtime.py:22-25` carries the same stale sentence.
- **Verdict:** CONFIRMED.
- **Impact:** The starter tells developers a claim does not exist, so workspace-scoped apps get built some other way, and the two SDK files disagree.
- **Fix:** both. Add `workspace_id` to the starter's dataclass and docstring, and fix the platform's `_manaurum_runtime.py` docstring.

### GW-08 — MEDIUM — The 3.1.0 "guest pages" pattern leaves out the cross-tenant case: a signed-in visitor from another tenant gets `404 app_not_found`, not `401`
- **SDK:**
  - `references/v2-platform.md:256`: "The page asks for it once. A guest gets `401` and carries on without one".
  - `:251` and `SKILL.md:236`: "a `user` route answers a guest `401`".
- **Platform:** `routes/v2_app_gateway.py:892-903 @285c8a8`: a valid session whose workspace is outside the app's tenant gets `404 app_not_found`. The page itself is still served to that person, because the login gate has no tenant check (`:849-862`). MAN-3188, the Planning Poker port that 3.1.0 came from, says it outright: "A logged-in visitor from another tenant gets 404 `app_not_found` on `user` routes — the UI must fall back to guest join."
- **Verdict:** CONFIRMED.
- **Impact:** A share link opened by someone signed in to another tenant fails as an error instead of falling back to guest mode.
- **Fix:** SDK. In step 2, "a guest gets `401`, or `404 app_not_found` if signed in elsewhere; treat both as guest".
- **Related:** MAN-3188, MAN-3200.

### GW-09 — HIGH — Cross-tenant installs: the gateway only serves the home tenant, yet the SDK promises "one deploy serves every tenant that installs the app"
- **SDK:**
  - `skills/manaurum-deploy/SKILL.md:367`: "one deploy serves every tenant that installs the app".
  - `SKILL.md:216`: "`public` (any tenant can install via App Store v2)".
  - `references/v2-platform.md:584`: "The platform runs a separate Swarm service per (app, tenant)".
  - `SKILL.md:691`: `MANAURUM_TENANT_ID` is the "tenant your app is installed in".
- **Platform:**
  - `services/v2_apps/gateway_production.py:107-126 @285c8a8`: the loader joins `v2_app_installs i ON i.tenant_id = a.tenant_id`, which is only the home tenant's install.
  - `routes/v2_app_gateway.py:892-903`: the tenant check runs against `app_record.tenant_id`. Every user in a consuming tenant therefore gets `404 app_not_found` on every `user` route.
  - Deploy creates exactly one service, for the deploying tenant (`services/v2_apps/production.py:3941-3951`), and `MANAURUM_TENANT_ID` is that tenant (`services/v2_apps/stack_generator.py:305`).
  - Agent dispatch for a cross-tenant install mints with the app's tenant (MAN-2722).
- **Verdict:** CONFIRMED for the code path. Whether cross-tenant use is meant to work today is UNVERIFIABLE (see Questions).
- **Impact:** A `public` app installed by tenant B deploys green and is broken for every B user.
- **Fix:** SDK now: say that `user` routes serve the home tenant only, and that `MANAURUM_TENANT_ID` is the deploying tenant. Platform: decide and track it.
- **Related:** MAN-2722.

### GW-10 — MEDIUM — The SDK error tables are missing most of what the gateway can return; the 30 s buffered-route limit is undocumented
Every status the gateway and streaming handler can return, checked against the SDK tables (`SKILL.md:670-683`, `skills/manaurum-deploy/SKILL.md:335-347`, `references/v2-platform.md:357-370`):

| Gateway answer | Source @285c8a8 | In SDK? |
|---|---|---|
| 404 `route_not_declared` (undeclared `/api/*`; also `/agent/*`) | `routes/v2_app_gateway.py:796`, `:808-810` | yes, but the `/agent` cause is not mentioned (GW-04) |
| 404 `app_not_found`: unknown slug or not ready; a non-`/api` path on the Core origin; a cross-tenant user on a `user` route | `:733`, `:745`, `:901-903` | **no** |
| 503 `app_disabled` (API calls) or a 503 HTML page (developer kill switch, `POST /api/developer/apps/{slug}/disable`) | `:752-759`; `routes/developer/__init__.py:1388` | **no** |
| 400 `path_traversal_rejected` | `:781-784` | **no** |
| 401 `authentication_required` with `X-Manaurum-Session: required` and `Cache-Control: no-store` | `:888-891` | only in prose (v2-platform.md:251, sdk-api.md:242) |
| 302 to `<app_base_url>/?next=…` (private page, document navigation, no session) | `:830-835`, `:315-352` | prose only |
| 504 `upstream_timeout`: buffered route over **30 s**; streaming connect over 5 s | `:1002`, `:1010-1013`; `routes/v2_gateway_streaming.py:81`, `:195-198` | **no**. The 30 s appears only inside a code comment (v2-platform.md:604) |
| 502 `upstream_unreachable` | `:1014-1021`; `routes/v2_gateway_streaming.py:199-202` | yes (cause stale, GW-03) |
| 429 `stream_concurrency_exceeded` | `routes/v2_gateway_streaming.py:179-182` | yes |

- **Verdict:** CONFIRMED.
- **Impact:** A non-streaming route that runs longer than 30 s (an AI call, a report) answers 504 behind a green deploy, and nothing tells the developer to stream or go async. The kill switch's 503 reads as an outage. Agent dispatch also has a 30 s timeout (`agent/v2_capability_dispatch.py:43`).
- **Fix:** SDK. Add one "gateway answers" table to `v2-platform.md` §2 and link to it from both skills.

### GW-11 — MEDIUM — Cookies the app sets never come back, and the SDK only states the rule ("strips `Cookie`") without saying what breaks
- **SDK:** `references/v2-platform.md:247` and `SKILL.md:236` say "strips `Cookie` and `Authorization`" but give no consequence.
- **Platform:**
  - The app's `Set-Cookie` is forwarded to the browser; only `manaurum_session` and `Domain=manaurum.com` cookies are dropped (`routes/v2_app_gateway.py:589-639 @285c8a8`).
  - The browser's `Cookie` header is always stripped on the way in (`:561`, `:570`).
- **Verdict:** CONFIRMED.
- **Impact:** Framework defaults (cookie sessions, CSRF double-submit cookies such as Django CSRF, express-session or Flask session) set the cookie and never see it again, so logins and forms fail behind a green deploy. MAN-3188's `pp_g_<room>` cookie is a real instance.
- **Fix:** SDK. One sentence: "cookies you set reach the browser but are never sent back to your container; turn off cookie-based sessions/CSRF".

### GW-12 — MEDIUM — A "private page" is a login redirect, not access control
- **SDK:** `references/v2-platform.md:223`: "Without the key every page is private". The qualifier at `:225`, "document navigations only", does not say that the HTML is still served anonymously to everything else.
- **Platform:**
  - `routes/v2_app_gateway.py:127-145`, `:830-863 @285c8a8`: only a GET with `Sec-Fetch-Dest: document`, or with `Accept` containing `text/html`, is checked. Fetch, iframe and curl requests are proxied anonymously.
  - A signed-in user of any tenant is served the page with no tenant check (`:849-862`).
- **Verdict:** CONFIRMED.
- **Impact:** Server-rendered data in a "private" page is readable by anyone.
- **Fix:** SDK. "`public_paths` only decides who is sent to log in; never put data in page HTML — fetch it from a `user` route."

### GW-13 — MEDIUM — The session-renewal description (3.1.0) is accurate on the happy path but leaves out behaviour apps will hit
- **SDK:** `references/sdk-api.md:242-248`. The 15 min cookie and 7-day refresh are correct (`config.py:110-111`, `routes/auth.py:690-694 @285c8a8`), and so are the trigger, the retry once and the exclusions. Not stated:
  - (a) The injected `fetch` checks with Core before **every** `user`-route call. It can **reject** with `Error("Manaurum session renewal is temporarily unavailable…")` when Core does not answer within 10 s, and not only on a changed user (`services/v2_apps/session_runtime.js:109-119`).
  - (b) In a standalone tab with no Core session, a `user`-route fetch never reaches the network; it gets a synthetic 401 (`:115`).
  - (c) `app.onAuthFailure` fires only for `app.fetch` (`frontend/public/sdk/manaurum-v2.mjs:502-510`), while sdk-api.md:242 implies any call.
  - (d) The script is injected only into a GET 200 `text/html` on the app subdomain that is not an attachment (`routes/v2_app_gateway.py:1033-1043`). It opens a hidden `<core>/v2-session` frame on every page load (`session_runtime.js:84`). It forces `Cache-Control: no-store` and drops `ETag`/`Last-Modified` on HTML (`services/v2_apps/session_recovery.py:104-110`).
  - (e) `SKILL.md` "Don't set your own framing headers" says "the rest of your CSP survives verbatim". It does not: `script-src` gets a nonce and `frame-src` gets `<core>/v2-session` (`services/v2_apps/session_recovery.py:24-50`, `:104-105`).
- **Verdict:** CONFIRMED.
- **Impact:** Unhandled promise rejections in app code that expects a `Response`, and caching that silently changes.
- **Fix:** SDK. Add (a) to (e) as short bullets.

### GW-14 — HIGH — `app.fetch` with an absolute URL is "subject to the gateway's egress rules": false
- **SDK:** `references/sdk-api.md:228`: "an absolute `https://` URL (passes through unchanged; external hosts are still subject to the gateway's egress rules)".
- **Platform:** a browser `fetch` to an external host never goes through Core. `egress_allowed_hosts` is enforced only by `os.http.fetch` (`references/v2-platform.md:322` itself says so). The wrong claim comes from the platform's own SDK comment (`frontend/public/sdk/manaurum-v2.mjs:408-410 @285c8a8`).
- **Verdict:** CONFIRMED.
- **Impact:** Developers believe the browser is sandboxed by the egress allow-list and reason about data exfiltration and CSP from that false premise.
- **Fix:** both, the sdk-api.md line and the mjs comment.

### GW-15 — MEDIUM — Runtime hardening (MAN-2264) is undocumented
- **SDK:** nothing. `SKILL.md:698` calls the env table "the complete set".
- **Platform:**
  - With `MANAURUM_V2_RUNTIME_HARDENING` set to `all` or the slug, the container gets: a read-only root filesystem, `User 10001:10001`, all capabilities dropped, `NoNewPrivileges`, a 128 MiB tmpfs at `/tmp` charged to the memory limit, and an extra env var `HOME=/tmp/home` (`services/v2_apps/stack_generator.py:171-242`, `:375-389`; `services/v2_apps/production.py:358-388 @285c8a8`).
  - The default is off; the code describes the rollout plan as "first-party apps first… then `all`".
  - Every container also has a 512 pids limit (`services/v2_apps/stack_generator.py:79`).
- **Verdict:** UNVERIFIABLE-WITHOUT-PROD (the env value in prod).
- **Impact:** On the day `all` is turned on, an app that writes outside `/tmp`, or that spools uploads larger than 128 MiB, breaks on its next deploy.
- **Fix:** SDK. Add a "write only to `/tmp`; assume read-only root and uid 10001" rule, and add `HOME` to the env table with a note.

### GW-16 — LOW — The runtime token expires 365 days after the last deploy
- **SDK:** `SKILL.md:695` and `references/v2-platform.md:297` say "Minted fresh on every deploy", with no expiry.
- **Platform:** `services/v2_apps/runtime_credentials.py:90` and `:166` set `expires_after_days: int = 365`.
- **Verdict:** LIKELY (I did not check whether the call site overrides the default).
- **Impact:** An app left untouched for a year starts getting `401 invalid_credential` on every capability call.
- **Fix:** SDK. One clause: "expires 365 days after the deploy that minted it — redeploy to renew".

### GW-17 — LOW — Platform `file:line` pointers have drifted
- `references/v2-platform.md:105` cites `production.py:40-43`. The "reserved" text is now at `services/v2_apps/production.py:49-52 @285c8a8`.
- `references/v2-platform.md:123` cites `app/agent/types.py:108` for the 400-character cap. The check is at `agent/types.py:117`; line 108 is the `name` length check.
- `v2-platform.md:117` says "Verified 2026-07-26". That was one day before MAN-1432.
- **Fix:** SDK. Cite symbols rather than lines.

### GW-18 — LOW (cross-dimension, residue of the 3.1.0 change) — UUID vs slug for `X-Manaurum-App-Id`
- `SKILL.md:675`: "Use the UUID from `process.env.MANAURUM_APP_ID`".
- `SKILL.md:692`: "Use as `X-Manaurum-App-Id`".
- Both contradict `SKILL.md:356`, which says the slug for `os.secrets.*` and `os.files.*`. Handing this to the capabilities dimension.

### GW-19 — HIGH (cross-dimension, post-deploy) — "A per-tenant migration failure does not fail the job; the version still activates"
- **SDK:** `skills/manaurum-deploy/SKILL.md:199-200` and `:335`; `references/v2-platform.md:488`.
- **Platform:** the MAN-2510 gate is on by default (`services/v2_apps/production.py:1090-1102 @285c8a8`). `:3839-3870` emits `migration_gate_blocked` and fails the deploy *before swarm*.
- **Verdict:** CONFIRMED. Handing this to the migrations dimension; noted here because it is in the post-deploy text.

## Verified correct (no action)
- **Stream limits:** 50 per (app, tenant) per process; 200 total; 900 s lifetime; 60 s idle; 429 `stream_concurrency_exceeded`. All env-overridable (`routes/v2_gateway_streaming.py:57-76`). Re-authentication happens only at connect.
- **JWT:** RS256, iss `manaurum-core`, aud `manaurum-app`, 60 s TTL, header `X-Manaurum-User-Context`. The `app_id` claim is the slug. There is no name or email.
- **Route matching:** `/*` does not match the bare prefix or `/`; longest literal prefix wins and ties go to the first rule (`services/v2_apps/api_route_matcher.py:41-98`). `public_paths` uses the same matcher (`routes/v2_app_gateway.py:186-195`).
- **Headers and sessions:** the gateway strips `Cookie` and `Authorization` on every request. A 401 carrying `X-Manaurum-Session` can only come from the gateway, because the upstream copy is stripped (`:583`). Cookie 15 min, refresh 7 days.
- **Environment variable names** match `services/v2_apps/stack_generator.py:304-348` (plus `HOME` when hardened, GW-15).
- **`runtime` keys and limits:** the 11 `runtime` keys match the schema; `resources` is 64–2048 MiB and 50–2000 millicores, a value above the ceiling is a 422, and the defaults are 512 / 500. `health_path` strict means a 5xx fails the deploy; without it, any HTTP answer passes.
- **3.1.0 fixes:** the stream limits, the session renewal basics, `public_paths`/`health_path` in check_app, and "no third mode" are all correct apart from the gaps noted in GW-05, GW-08 and GW-13.

## Questions (no evidence yet)
1. **GW-01:** does Traefik or any edge middleware in prod strip client `X-Manaurum-*` request headers? Nothing in the backend does. Even if Traefik does, the overlay-network path stays open.
2. **GW-09:** is a `public` app installed in tenant B supposed to work through the gateway today, or is cross-tenant use deliberately blocked until there are per-install containers? No ticket found apart from MAN-2722.
3. **GW-15:** what is the current `MANAURUM_V2_RUNTIME_HARDENING` value in prod?
4. **GW-16:** does `_mint_runtime_token_for_deploy` override the 365-day default?

## Summary
- **Covered:** both gateway route files, the production wiring, the JWT mint and verify code, the route matcher, session recovery (Python, JS and the Core relay page), the stack env, the readiness probe, runtime credentials and agent dispatch. Checked against SKILL.md, v2-platform.md, sdk-api.md, the post-deploy parts of the deploy and setup skills, check_app.py, README and the starter (auth, main, agent_routes, README). The client-header relay (GW-01) was reproduced locally against the SNAP handler.
- **Biggest problems:** one security defect (GW-01), and three stale facts repeated across many files: no readiness probe, wrong port leads to green then 502, and `/agent/*` on the public internet (GW-02 to GW-04).
- **Not covered:** BYO-mode proxying (`dev_v2_byo.py`), the Core-origin `/apps/<slug>/api/*` surface beyond the header rules, the `/__manaurum/runtime-errors` path that Core reserves on every app host, `usage_counters` and `runtime_errors` beyond a skim, and Traefik behaviour at the edge.

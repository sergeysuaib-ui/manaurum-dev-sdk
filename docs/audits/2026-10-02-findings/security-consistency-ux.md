# Dimension: security-consistency-ux

SDK = `C:\dev\wt\sdk-audit` @ 6f52dce (3.1.0). Platform = SNAP @285c8a8 (paths below are relative to SNAP).
Probe scripts (read-only, local): `<scratchpad>\sec-probe\dup_header.py`, `token_regex.py`, `links.py`.

---

## A. Security of what the SDK teaches

### SEC-1 · CRITICAL · LIKELY (mechanism CONFIRMED locally, exploitation unverified on prod)
**A client can smuggle its own `X-Manaurum-User-Context` past the gateway, and the starter accepts a token minted for any other app.**

- SDK: `templates/v2-starter/src/auth.py:60-67` verifies only sig + `iss` + `aud` + `exp`. It never compares `claims.app_id` with the app's slug or `claims.tenant_id` with `MANAURUM_TENANT_ID`. `auth.py:92` reads `request.headers.get(USER_CONTEXT_HEADER)`, which returns the first value. No SDK page says the claims must be bound to the app.
- Platform:
  - `aud` is one constant for every app: `_AUDIENCE = "manaurum-app"` at `backend/app/services/v2_apps/user_context_jwt.py:71 @285c8a8`. The `app_id` claim is the slug (`routes/v2_app_gateway.py:908`, `agent/v2_capability_dispatch.py:137`).
  - `_filter_request_headers` drops only `authorization` and `cookie` (`routes/v2_app_gateway.py:561-571 @285c8a8`). An inbound `x-manaurum-user-context` therefore survives.
  - On a `user` route the gateway then adds `forwarded_headers["X-Manaurum-User-Context"] = token` (`:912`) with different casing to the lowercase key taken from `dict(request.headers)` (`:866`). Both headers get forwarded.
  - On `anonymous` and static paths nothing is minted, so the client's header passes through on its own.
  - Reproduced with httpx 0.28.1 and Starlette 1.7.0 (`sec-probe/dup_header.py`). httpx sends both lines. The container's `request.headers.get(...)` returns the **attacker's** value: `{'get': 'ATTACKER', 'all': ['ATTACKER', 'MINTED']}`.
  - Core itself treats cross-app replay as a real threat and binds the claims on its own surface: tenant check at `routes/capability_gateway.py:676-684` and "Refuse a same-tenant replay by another app" at `:868-896 @285c8a8`.
  - App containers share one network (`services/v2_apps/stack_generator.py:17-24 @285c8a8`, "One **shared** app network"). Another app's container can therefore also POST straight to `http://<service>:<port>/agent/*` or `/api/*`, with no gateway in between.
- Impact: the developer of any app the victim uses receives the victim's JWTs on every request. Within 60s they can act as the victim in any app grown from the starter. This works through the gateway (smuggled header) or straight over the shared network, and the deploy stays green.
- Fix (both sides):
  - SDK: in `auth.verify_user_context`, refuse a token unless `claims["app_id"] == APP_SLUG` and `claims["tenant_id"] == MANAURUM_TENANT_ID`. Add a test for each, and teach the rule in SKILL.md Step 3 and v2-platform §agent_capabilities.
  - Platform: strip inbound `x-manaurum-user-context` (case-insensitive) in `_filter_request_headers`, and make `aud` per-app (for example `manaurum-app:<slug>`).
- Related: MAN-1452 (wrong threat model in the docs), MAN-2722 (the agent-dispatch mint copies the gateway's), MAN-609/628-2 (the binding Core does for itself). I found no existing Linear ticket for header smuggling or `aud` binding (searched "user_context", "User-Context", "aud", "impersonat").

### SEC-2 · HIGH · CONFIRMED
**`check_app.py`'s token-literal rule can never match a real `mna_*` or `mnu_*` token, and its mutation test uses a fake format.**

- SDK:
  - `templates/check_app.py:87` defines `TOKEN_LITERAL = r"\bmn[au]_[A-Za-z0-9]{16,}"`.
  - SKILL.md:563 promises it finds "an `mna_*`/`mnu_*` token literal anywhere in the directory".
  - `scripts/linter_mutations.py:201` plants `mna_9f3c1de77a04b26e5c81`, which has no inner underscore.
- Platform: real tokens are `f"{_TOKEN_PREFIX}{key_prefix}_{secret}"`, with a 12-hex key id and then `_` (`routes/developer/v2_credentials.py:409-411`, `services/v2_apps/runtime_credentials.py:183 @285c8a8`). `mnu_<env>_<32>` follows the same pattern (`auth/token_kinds.py:5`).
  - Three freshly generated real-format tokens: **NOT MATCHED** (`sec-probe/token_regex.py`).
  - Core's own build-context credential scan rejects the deploy on third-party prefixes (`sk-ant-`, `ghp_`, `AKIA`… at `services/credential_markers.py:14-25`; reject at `build_context_scanner.py:1042-1045, 1110-1116`). That list does **not** include `mna_` or `mnu_`.
- Impact: a deploy token pasted into `config.py` or `settings.json` passes the linter and the platform. It deploys green and is retained per version. The `.env*` rule only catches dotfiles.
- Fix:
  - SDK: use `\bmn[au]_[A-Za-z0-9]+_[A-Za-z0-9_-]{16,}` and plant a real-format token in the mutation test.
  - Platform: add `mna_` and `mnu_` to `CREDENTIAL_SUBSTRINGS`.
  - Also document `build_context_rejected` / `hardcoded-credential` in the deploy failure table. No SDK file mentions it today (grep for "hardcoded-credential" and "failed validation" finds nothing).

### SEC-3 · HIGH · CONFIRMED (the MAN-1899 pattern)
**The starter and the README say the gateway rejects a forwarded user context. The gateway requires it for `os.drive` and `os.calendar`.**

- SDK says the opposite in two places:
  - `templates/v2-starter/src/capability.py:76-77`: "Do NOT forward the user_context header here — the gateway rejects it on this path."
  - `README.md:28-29`: "you must never forward the user context onward to the gateway."
- SDK says the right thing in four places: SKILL.md:357, SKILL.md:680, `manaurum-setup/SKILL.md:318-320`, and `capabilities-reference.md:62-65`. The last one even says: "If you read anywhere that the gateway *rejects* a user context on this path, that statement is wrong."
- Platform: `routes/capability_gateway.py:649-684` verifies a presented header and `:763` raises `403 user_context_required` @285c8a8.
- Impact: an app grown from the starter (`call_capability` has no way to pass the header) gets 403 on every `os.drive.*` and `os.calendar.*` call.
- Fix: rewrite those two places. Give `call_capability(name, payload, user_context=None)` the ability to forward the header.

### SEC-4 · MEDIUM · CONFIRMED
**The handshake trusts the first sender, against the platform's own rule (MAN-2506).**

- SDK:
  - `templates/v2-starter/src/static/index.html:63-77` accepts `manaurum:init` from any `event.source` or origin. It sets `framed = true` and replies to `event.origin`.
  - The SKILL.md:310-325 snippet does no origin check.
  - `references/sdk-api.md:127` says to "capture `event.origin` off `manaurum:init` and reply to exactly that."
- Platform: the rule is "accept `manaurum:*` only from `window.parent` and from `https://manaurum.com` / `https://app.manaurum.com`; never store `event.origin` from whatever posts the first init" (`docs/handoff/V2_DEVELOPER_GUIDE.md`, commit e863f95dc @285c8a8 ancestry, 2026-09-13). The CLI template already applies it (`manaurum-cli-py/manaurum_cli/templates/index.html.template`).
- Impact: any frame or window that posts first becomes the "shell". Appearance, device, `granted_capabilities` and deep links can all be spoofed. The impact is low for the starter, which only renders them with `textContent`, but grows with every app that acts on the init payload.
- Fix: copy the platform guard. Let `preview.py` pass its origin through an opt-in query flag, so the local harness still works.
- Related: MAN-2506.

### SEC-5 · MEDIUM · CONFIRMED (gap)
**The new guest-pass pattern (3.1.0) is underspecified for a security primitive.**

- SDK: `references/v2-platform.md:255-260` gives the whole construction: "HMAC over (user id, what it grants, expiry), with the key kept in `os.secrets`." It has no code and no test, and the starter does not implement it. The gaps:
  - No algorithm or encoding named (HMAC-SHA256; a canonical, unambiguous payload such as base64url JSON, not string concatenation).
  - No timing-safe comparison (`hmac.compare_digest`). The repo has no occurrence of `compare_digest`.
  - No expiry figure ("keep it short").
  - No revocation story: a member removed from the tenant keeps the pass until it expires, and rotating the key logs everyone out.
  - No key provisioning: who writes the secret (`manaurum app set-secret`, or the app on first use), how many bytes, and the slug-keyed namespace (SKILL.md:356).
  - No reminder to declare `os.secrets.get` in the manifest.
  - Nothing on where the client may keep the pass (never in a URL or query string).
  - "A guest gets `401`" (`:256`) is not guaranteed in a standalone tab. The injected runtime treats `/api/pass` as a `user` route and opens the Core relay first. If the relay times out it throws instead of answering 401 (`services/v2_apps/session_runtime.js:104-117 @285c8a8`: `throw new Error('Manaurum session renewal is temporarily unavailable…')`).
- Impact: each app reinvents the pass. The likely bugs are `==` comparison, a forgeable concatenation, no expiry check, and a guest page that crashes on a thrown fetch.
- Fix: add a 30-line reference implementation (`src/guest_pass.py`) plus tests to the starter, or to v2-platform.md. Say "treat a thrown fetch as guest."
- Related: MAN-3200.

### SEC-6 · HIGH · CONFIRMED
**The SDK contradicts itself about where the deploy token file lives, and two of its versions put it inside the uploaded directory.**

- One level up: SKILL.md:157 and :167 ("The token file lives one level up, and that placement is the point"), plus `manaurum-deploy/SKILL.md:319-320`.
- Inside the app directory:
  - `manaurum-setup/SKILL.md:71` draws `.env.manaurum` inside `my-app/` ("Deploy-time token (gitignored)").
  - The `deploy.sh` template sources it from the app directory (`manaurum-deploy/SKILL.md:372-374`: `if [ -f .env.manaurum ]`), and the Quickstart runs from `cd my-app`.
- Platform: the CLI packager excludes only exact names, with no `.env*` (`manaurum-cli-py/manaurum_cli/packaging.py:20-31 @285c8a8`). The context is retained and committed to per-app git history (deploy SKILL:310-313).
- Impact: the curl path happens to be safe (`--exclude='.env*'`). Following setup and then running `manaurum app deploy` ships the token, and `check_app.py` fails the layout that setup itself prescribes.
- Fix: one rule, workspace-level `.env.manaurum`. Fix the setup tree, make `deploy.sh` source `../.env.manaurum`, and update the starter `.gitignore` comment.

### SEC-7 · MEDIUM · CONFIRMED
**Egress: the SDK claims a network boundary that does not exist, and its "known bug" note is stale.**

- SDK:
  - SKILL.md:713: "`egress_allowed_hosts` controls outbound; DROP everything else."
  - `v2-platform.md:326` still describes the `0.0.0.0 <host>` blackhole as an unresolved live bug.
- Platform: MAN-2263 was fixed 2026-09-02 (#1923, mono-log line 60). The list is now only a label: "nothing in this spec decides reachability, so undeclared egress is open. TODO(MAN-185): enforce" (`services/v2_apps/stack_generator.py:350-357`, also `:31-33`). An optional egress network depends on prod env (`:17-24`).
- Impact: developers reason about supply-chain exfiltration from a boundary that is not there. The advice to route egress through `os.http.fetch` still holds (`capabilities/http_fetch.py:260-263, 311-326`: allow-list enforced, `follow_redirects=False`).
- Fix: replace both texts with "only `os.http.fetch` is enforced; raw egress from the container is currently open (MAN-185)."

### SEC-8 · HIGH · CONFIRMED (known MAN-1452, still open; reporting its spread and the missing correct reason)
**`/agent/*` is called "Traefik straight to your container / public internet" in 9 places.** The gateway has refused it since MAN-1432 (2026-07-26).

- The 9 places:
  - `README.md:36`, `README.md:38`
  - `v2-platform.md:117` ("Verified 2026-07-26 against a live deploy…"), `v2-platform.md:156`
  - SKILL.md:554
  - `templates/check_app.py:16, :277-279, :290`
  - `templates/v2-starter/src/agent_routes.py:19-22`
  - `templates/v2-starter/tests/test_manifest.py:11-12`
- SKILL.md:294 says the opposite, correctly: "Traefik never talks to your container directly".
- Platform: `_RESERVED_PREFIXES = ("/agent/",)` at `routes/v2_app_gateway.py:98`, refused at `:795` before proxying. Module docstring `:6-7`: "The container is NEVER reached directly by Traefik".
- What the SDK should say instead: the JWT check is still mandatory because every other app container on the shared app network can reach `/agent/*` directly (`stack_generator.py:17-24`). That is also why SEC-1's app-id binding matters.
- Fix: land MAN-1452 with that wording.

### SEC-9 · MEDIUM · CONFIRMED
**The `mna_*` token-scope docs describe the pre-MAN-1585/2597 model.**

- SDK:
  - `v2-platform.md:387` ("blank for `*`"), `:398` (`-d '{"apps": ["*"]}'`), `:401` ("Cap: 5 active"), `:421` ("`["*"]` (default)").
  - `:361` ("Wildcard `*` is honored").
  - `:109` ("Wildcard `"*"` grants everything", about capability grants). This contradicts `capabilities-reference.md:60` ("There is no wildcard grant (MAN-1585)").
- Platform:
  - `routes/developer/v2_credentials.py:233-292` refuses the wildcard with `apps_wildcard_not_allowed`. `:74` sets the cap to 20 by default. `:195-202` adds `scope_kind: "owner"` (MAN-2597). `:98` sets expiry to 365 days by default.
  - `routes/capability_gateway.py:688` says "Exact match, no wildcard (MAN-1585)".
  - MAN-2620 (an ex-member's apps token) shipped 2026-09-23 (mono-log line 32). It is not mentioned anywhere.
- Impact: the issuance curl in the docs fails. Agents explain scopes wrongly, for example "wildcard is the default".
- Fix: rewrite §4 around `scope_kind: apps|owner`. Mention that an apps token stops working when its holder leaves the tenant or stops owning the app.

### SEC-10 · LOW · CONFIRMED
**Side gaps in the auth code and guidance.**

- (a) `auth.py:31-34` says "There is deliberately no `workspace_id` — the token does not carry one". The platform mints `workspace_id` on both paths (`v2_app_gateway.py:910`, `v2_capability_dispatch.py:139`), and `v2-platform.md:262` lists it.
- (b) python-jose does not require `exp`, `iat` or `sub` unless asked. Only Core signs these tokens, so this is hardening: pass `options={"require_exp": True, "require_iat": True}`.
- (c) No SDK text says not to perform state changes on GET `user` routes. The MAN-2248 fix (`services/v2_apps/gateway_production.py:231-300 @285c8a8`, merged 2026-09-02 though Linear still shows In Review) deliberately lets a cross-site top-level GET navigation carry the session, so a side-effecting GET stays CSRF-able.

---

## B. Internal consistency

### Contradictions found (facts in 2+ places that disagree)

| id | sev | fact | wrong locations | right locations / platform truth |
|---|---|---|---|---|
| CON-1 | HIGH | Is there a post-deploy readiness probe? | "no readiness probe": SKILL.md:654; deploy SKILL:193, :464 (deploy.sh comment); `publishing.md:43-44`; README:212 | `v2-platform.md:208, 229`; CHANGELOG 3.1.0 :10-11; `services/v2_apps/production.py:1050-1059` (`MANAURUM_V2_READINESS_PROBE` default "1"), `:1114-1135`, `:1317` (rollback) |
| CON-1b | HIGH | Does a per-tenant migration failure still activate the version? | "version still activates": deploy SKILL:199-200, :252-253; `v2-platform.md:488` | `production.py:1090-1102`: MAN-2510 migration gate, default ON (`=0` "restores the old ... activate anyway behaviour") |
| CON-2 | HIGH | Is `runtime` strict? (MAN-1899; 3.1.0 said "five places" were fixed) | `v2-platform.md:24`: "`runtime` ... sub-objects are *not* strict ... a typo ... does nothing" | `v2-platform.md:203`, `:310`; SKILL.md:292; schema `_schemas/manifest_v2.schema.json` runtime `additionalProperties: false` (checked) |
| CON-3 | MEDIUM | `egress_not_declared` status | SKILL.md:678 says `422` | `412`: `v2-platform.md:322, 366`; `capabilities-reference.md:664`; `capabilities/http_fetch.py:261` |
| CON-4 | MEDIUM | rollback request | SKILL.md:665 and `v2-platform.md:459-462` ("rollback to previous version", no body) | deploy SKILL:264-271 (`version_label` required); `routes/dev_v2_deploy.py:764-765` (`version_label: str`) |
| CON-5 | MEDIUM | user context to the capability gateway | `capability.py:76-77`; README:28-29 | SKILL.md:357; setup:318; `capabilities-reference.md:62-65` (SEC-3) |
| CON-6 | HIGH | `/agent/*` reachability | 9 places (SEC-8) | SKILL.md:294; `v2_app_gateway.py:98, 795` |
| CON-7 | MEDIUM | wildcard capability grant | `v2-platform.md:109` | `capabilities-reference.md:60`; CHANGELOG :288-289 |
| CON-8 | MEDIUM | token file location | setup:71; deploy SKILL:372-374 | SKILL.md:157, 167; deploy SKILL:319-320 (SEC-6) |
| CON-9 | LOW | `X-Manaurum-App-Id` = UUID everywhere? | SKILL.md:692 ("Use as `X-Manaurum-App-Id`"); `v2-platform.md:338, 365`; `capabilities-reference.md:20`; setup:291 | SKILL.md:356; `capabilities-reference.md:31-41`; `capability.py:24-40` (slug for secrets and files) |
| CON-10 | LOW | `DATABASE_URL` modes | setup:294 ("the default, and `data.shared`") | SKILL.md:698 and `v2-platform.md:300` (managed only). Needs one answer |
| CON-11 | LOW | `dev` runtime | setup:148 ("(in-browser editor)") | SKILL.md:209; `v2-platform.md:316` (editor removed 2026-08-07) |
| CON-12 | LOW | packager exclude list | SKILL.md:731, setup:251, deploy SKILL:315-316 (subsets) | SKILL.md:170 = `manaurum-cli-py/manaurum_cli/packaging.py:20-31` (10 names) |
| CON-13 | LOW | does `.dockerignore` protect a platform deploy? | SKILL.md:161, 173; deploy SKILL:321; setup:69; starter `.dockerignore:1-3` ("anything listed here never reaches the builder") | setup:253-255 and the same `.dockerignore`'s own NOTE ("does not apply .dockerignore server-side"). Prod truth: UNVERIFIABLE (question Q1) |
| CON-14 | LOW | starter test count | setup:42, :360 ("19 passed"); setup:65 lists 4 test files | 38 passed (orchestrator); `tests/` holds 6 files incl. `test_manifest.py`, `test_static.py`. `check_repo.py`'s "no hardcoded self-counts" rule misses this form |
| CON-15 | LOW | `workspace_id` claim | `auth.py:31-34` ("does not carry one") | `v2-platform.md:262`; platform mint (SEC-10a) |
| CON-16 | LOW | Swarm network | `v2-platform.md:281, 439`; deploy SKILL:231 ("on `dokploy-network`") | `stack_generator.py:17-24` (configurable apps network plus optional egress network, MAN-185 phase B) |
| CON-17 | LOW | traffic path | README:36 ("Traefik targets `manifest.runtime.port`") | SKILL.md:294 (Traefik → Core → container) |

### Broken cross-references (script `sec-probe/links.py` plus a manual check of every `→ "…"` / `§` citation)

- SKILL.md:253 points to `references/v2-platform.md` "§ Manifest reference". No such heading exists (it is "## 1. Manifest v2 — full field reference"). Its promise of "custom capabilities, secrets" is also unmet: secrets are not a manifest key.
- `manaurum-deploy/SKILL.md:260`: "Full classification: `manaurum-app/SKILL.md`". The tiers live in `v2-platform.md` §7.
- Every other quoted-heading citation resolves:
  - SKILL.md:236, 237, 346, 361, 712, 723, 735
  - `v2-platform.md:260`
  - `sdk-api.md:129`
  - deploy:35, 62, 69
  - setup:348
- No markdown `[..](..#anchor)` links are broken.

### Duplicated-facts inventory (fact → locations → proposed single source)

| fact | locations | single source (others link) |
|---|---|---|
| user_context: RS256, 60s, header name, iss/aud | SKILL.md:234; `v2-platform.md:242`; setup:158-159; `sdk-api.md:230`; README:25-27; `main.py:26-29`; `auth.py:21-24` | `auth.py` constants plus a v2-platform §"user_context" (add the app_id/tenant binding there) |
| `/agent/*` threat model | 10 places (SEC-8) | `v2-platform.md` §agent_capabilities, one paragraph |
| user context forwarded to the capability gateway | SKILL.md:357, 399-400, 680; setup:318; cap-ref:62-65, 220, 269; `capability.py:76`; README:29 | `capabilities-reference.md` §call contract |
| App-id form per family | SKILL.md:356, 675, 692; cap-ref:31-41; v2-platform:338, 361-365; setup:291; `capability.py:24-40` | `capabilities-reference.md` §call contract, plus the code |
| Rejection and status codes (404 route_not_declared, 412 egress…, 403 not_granted…) | SKILL.md:670-683; deploy:324-346; v2-platform:355-370; cap-ref per section | `capabilities-reference.md` (runtime) and deploy SKILL (deploy-time) |
| Readiness and "succeeded ≠ serving" | SKILL.md:654; deploy:191-220, 464; publishing:43; README:212; v2-platform:229 | `v2-platform.md` §runtime.health_path |
| Migration rules and tiers | SKILL.md:162, 559; deploy:244-260, 342-345; setup:85-87; v2-platform §7 | `v2-platform.md` §7 |
| Packager excludes and the tar command | SKILL.md:170, 600-605, 731; deploy:86-91, 315-316, 399-412; setup:251; `check_app.py`; `.dockerignore` | `manaurum-deploy` `deploy.sh` (one copy). SKILL.md Step 4 should link, not repeat |
| Manifest validation rules (app_id, port, api_routes, data, icon, permissions) | SKILL.md:205-224, 226-251; setup:142-180; v2-platform §1-2; publishing:47-88 | `v2-platform.md` §1-2 |
| Env var table | SKILL.md:67, 689-698; setup:286-295; v2-platform:291-300 | `v2-platform.md` §hosted |
| Token mint path and `.env.manaurum` | SKILL.md:157, 584-590; deploy:12, 20-21, 376-378; setup:71, 324-332; README:81-89; v2-platform §4 | `manaurum-deploy` §Prereqs |
| Handshake snippet | SKILL.md:309-326, 337-342; setup:257-272; sdk-api.md §handshake; starter `index.html` | starter `index.html` (with the MAN-2506 guard) |
| No dialogs, downloads or popups | SKILL.md:142-144, 725, 733-739; setup:278-280; sdk-api:129 | `sdk-api.md` §Cross-origin rules |
| Streaming limits | SKILL.md:237; v2-platform:264-277 | v2-platform (consistent today) |

---

## C. Agent ergonomics

### UX-1 · HIGH · CONFIRMED — this machine runs 2.7.2, and here is what an agent following it hits today

- Installed copy: `C:\Users\sergei\.claude\plugins\installed_plugins.json` shows `"version": "2.7.2", installedAt 2026-08-12T21:48`. The cache holds only `2.7.2/` (with an `.in_use` marker). The skill list loaded into **this** session shows the 2.7.2 descriptions ("...and legacy v1", "Legacy v1 ... `mnu_*` ... is supported").
- Dangerous differences against origin/main 3.1.0 (`git diff --no-index --stat`: 9 files, +790/−1409):

1. **The v1 path is taught as supported.** The descriptions of all three skills mention it. Sections: 2.7.2 `SKILL.md:16, 464-468`; `publishing.md:103` (`POST /api/dev/apps/deploy` with `mnu_*`); `references/manifest-spec.md`; `sdk-api.md:248+`; `templates/legacy-v1/`. Platform: 404 since 2026-08-05, retired 2026-09-28 (3.0.0 CHANGELOG).
2. **"`runtime` is not strict" in 5 places.** 2.7.2 `SKILL.md:231, 458`; `v2-platform.md:24, 252`; `setup:300`. A typo is now a 422.
3. **The app-id is the UUID for everything.** 2.7.2 `capabilities-reference.md:32` says "Always send `MANAURUM_APP_ID`", and the starter `capability.py:49` sends the UUID for every call. Every CLI-set secret then reads as 404, and file namespaces split.
4. **The deploy writes to a fixed `/tmp/ctx.tar`.** 2.7.2 `SKILL.md:336-353`. That is the MAN-2456 collision, where one session shipped another session's archive.
5. **No linters, preview or version hook.** `templates/` has only `legacy-v1` and `v2-starter`; no `check_app.py`, `check_ui.py`, `preview.py`, `hooks/` or `scripts/`.
6. **Missing 3.x knowledge.**
   - `public_paths`, `health_path` and `resources` do not appear, so guest pages get redirected to login.
   - The DB-comes-up-late rule is absent (MAN-3008), so apps keep a failed pool forever.
   - Session renewal, the streaming limits and the window restrictions (downloads, popups, clipboard) are absent.
   - The `os.http.fetch` redirect credential-drop rule is absent.
   - The 2.7.2 handshake snippet ignores `payload.appearance`; that is the seven-rules bug the later releases exist to prevent.
7. **Wildcard grant and wildcard token scope taught as real.** 2.7.2 `capabilities-reference.md:52`; `v2-platform.md:109, 340, 363`.

### UX-2 · MEDIUM · CONFIRMED — why it did not update, and why nobody was warned

- **The marketplace clone is 2.7.3; the install stayed at 2.7.2.** The clone at `~/.claude/plugins/marketplaces/manaurum-sdk` is at `ac1df45` (2.7.3, fetched 2026-08-28 01:34) and its `plugin.json` says `"version": "2.7.3"`. The installed plugin is still 2.7.2: the marketplace was refreshed once, but `plugin update` never ran. Nothing has been fetched since, while origin is at 3.1.0.
- **No auto-update is configured.**
  - `known_marketplaces.json` has no `autoUpdate` for `manaurum-sdk`, and its `lastUpdated` field still says 2026-08-02.
  - `settings.json` `extraKnownMarketplaces.manaurum-sdk` carries only its `source`.
  - `autoUpdatesChannel: "latest"` governs the Claude Code binary, not plugins.
  - Claude Code does not auto-update third-party marketplaces by default (LIKELY: standard behaviour, not provable from the repo).
  - README:51-60 gives only manual `marketplace update` and `plugin update` commands. It never says to enable auto-update.
- **The hook cannot catch this case.**
  - `hooks/hooks.json` and `scripts/version_check.py` exist only since 2.9.0, so a 2.7.x install has no hook at all.
  - Even in 3.1.0 the hook only compares **sibling cache directories** (`version_check.py:72-81`). It never reads the marketplace clone (here 2.7.3 > 2.7.2) or the remote, so "installed old, nothing newer cached" prints nothing.
  - The SKILL.md:8-16 banner relies on the same sibling check.
- Fix:
  - In `version_check.py`, also compare against `~/.claude/plugins/marketplaces/<mkt>/.claude-plugin/plugin.json`, and tell the user to run `/plugin update`.
  - In the README install section, add "enable auto-update for this marketplace in `/plugin` → Marketplaces".

### UX-3 · LOW · CONFIRMED — trigger overlap and repeated content

- **"Start building a new app" matches two skills.**
  - `manaurum-app` description: "Build apps for ManAurum OS … deploy API".
  - `manaurum-setup` description: "start building a new ManAurum/SeregaOS app, scaffold a project".
  - Setup repeats app's Step 0 brief (setup:16-30 vs SKILL.md:24-57) and the manifest rules.
- **The deploy block appears three times.** SKILL.md:594-619; deploy:74-109; deploy:360-479.
- **3.1.0's `manaurum-deploy` description no longer mentions v1 or `mnu_*`** (`manaurum-deploy/SKILL.md:3`). It is correct; only the installed 2.7.2 copy still advertises v1.
- Fix:
  - Make setup's description defer to `manaurum-app` for new apps ("only when the user explicitly asks to scaffold"), or fold setup into manaurum-app.
  - Keep one `deploy.sh`.

### UX-4 · LOW · CONFIRMED — context cost

- **The main skill alone is ~13k tokens.** `manaurum-app/SKILL.md` is 53.5 KB.
- **The required reading before the first file is ~25–35k tokens.** The skill sends the agent to `reference-apps.md` (7.7 KB), `design.md` (21 KB), `discovery.md` (12 KB), `app.css` (630 lines) and `index.html` (462 lines).
- **Two references are large.** `v2-platform.md` is 48.5 KB and `capabilities-reference.md` 31 KB. References load lazily (only when the agent opens them), which is right.
- **Duplication adds to the load.** It costs space twice: the deploy and setup skills re-state Steps 3.5 and 3.6 and the deploy script.
- Suggested read order to state at the top of SKILL.md:
  1. Step 0 → `discovery.md`
  2. Copy the starter
  3. Steps 1–3
  4. `capabilities-reference.md` only for the capabilities you call
  5. `design.md` before the UI
  6. Steps 3.5 and 3.6
  7. Deploy
- Move the Step 3.5 screenshot procedure (SKILL.md:404-534, ~130 lines) into `design.md`.

### UX-5 · OK — version consistency

- `plugin.json` (3.1.0), README:3, the SKILL.md:8 banner and CHANGELOG top all agree, and `scripts/check_repo.py:252-289` enforces it.
- `marketplace.json` has no version and points at `url` HEAD. That is fine, but a user cannot pin to a version.

---

## Questions (no evidence either way)

- **Q1 (CON-13).** Does the prod builder (classic or BuildKit via `POST /build` with the scanner's re-emitted tar) apply `.dockerignore`? The SDK says both yes and no.
- **Q2 (SEC-7).** Is `MANAURUM_EGRESS_NETWORK` set on prod, making the app network `--internal`? This decides whether raw container egress is open today.
- **Q3 (platform).** `os.http.fetch` resolves the hostname to check for private IPs, then lets httpx resolve again (`http_fetch.py:284` vs `:326`). That is a DNS-rebinding TOCTOU an app developer controlling a declared host's DNS could use. Is it ticketed?
- **Q4.** Is `GET /api/dev/v2/apps/<id>/logs` still a stub (SKILL.md:668, deploy:288), or a real tail (README:216)?
- **Q5.** Is `mnu_*` issued at "Settings → Team → Keys & tokens" (deploy:12)? Not checkable from SNAP.
- **Q6 (SEC-1).** Is Traefik or any proxy in front of Core configured to drop inbound `X-Manaurum-*` headers? Nothing in the repo does, but Dokploy/Traefik middleware lives outside SNAP.

## Summary

- **Covered.** The security of the user_context flow end to end: gateway mint and header filter, agent dispatch, the Core binding vs the starter's missing binding, with a local reproduction of the header smuggling. Also the token formats and the linter regex, the guest pass, the handshake origin rule, egress, credential scanning and token scopes. Then a systematic duplicated-facts inventory with 17 contradictions and the cross-reference check, the installed 2.7.2 vs 3.1.0 diff, and the marketplace and update mechanism.
- **Most severe.**
  - SEC-1: a cross-app user_context replay via a smuggled header or the shared network; the starter has no app_id/tenant binding.
  - SEC-2: the token-literal linter never matches real tokens.
  - SEC-3 / CON-1 / CON-2: stale facts the 3.1.0 fixes left behind (gateway "rejects" user context; "no readiness probe"; "runtime not strict").
  - UX-1/2: this machine's agents run 2.7.2, which teaches the retired v1 path, and no hook can warn them.
- **Not done.** No live-prod verification (header smuggling, `.dockerignore`, egress network). I did not read `design.md`, `discovery.md`, `reference-apps.md`, `check_ui.py` or `preview.py` line by line. Capability input schemas I left to the capabilities dimension.

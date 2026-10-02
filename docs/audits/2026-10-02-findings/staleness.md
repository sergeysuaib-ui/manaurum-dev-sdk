# Dimension: STALENESS — the platform moved; did the SDK follow?

SDK = `C:\dev\wt\sdk-audit` @ 6f52dce (3.1.0). Platform = `@285c8a8` (SNAP unless noted).
Raw list of app-relevant commits outside mono-log paths: `findings/staleness-outside.txt` (155 lines, reviewed by title; the relevant ones are folded in below).

Headline: the MAN-1899 pattern recurs at least six times. In each case one fact was true once, appears in 3–6 SDK files, and the platform changed it weeks ago. Often another SDK file already states the new truth, so the SDK contradicts itself: readiness probe, migration gate, the `*` token scope, runtime strictness, the `microphone`-only enum, and `/agent/*` being reachable from the internet.

---

## Findings

### ST-01 HIGH — "No readiness probe": wrong since 2026-07-25, repeated in 4 places
- SDK:
  - `skills/manaurum-deploy/SKILL.md:193`: "There is **no readiness probe anywhere in the hosted deploy path.**"
  - `skills/manaurum-deploy/SKILL.md:464-465`: "There is NO readiness probe on the platform side"
  - `skills/manaurum-app/SKILL.md:654`: "There is no readiness probe on the hosted path"
  - `skills/manaurum-app/references/publishing.md:42-43`: "There is no readiness probe in the hosted path"
  - These contradict `references/v2-platform.md:208,219,229` (written in 3.1.0): "the post-deploy probe… a container that never answers is rolled back".
- Platform: `backend/app/services/v2_apps/production.py:1050-1060 @285c8a8` `_readiness_enabled()` "Default ON". `:1037-1038`: `/healthz`, 90 s window. `:1172-1215` `await_swarm_convergence` waits for the new task first. The job emits `readiness_probing`/`readiness_failed`/`readiness_ok` (`:3963-4008`). Landed in b25cc8011 (2026-07-25, MAN-1368/1369). The guide agrees with the code: `docs/handoff/V2_DEVELOPER_GUIDE.md:1918-1950`.
- Verdict: CONFIRMED.
- Impact: agents are told `succeeded` means only "Docker accepted the spec". They miss that a failed probe rolls back to the previous version, and that a first deploy with nothing listening is reported `failed`.
- Fix: SDK. Replace the four sentences with the v2-platform.md:229 wording, and make "hit /healthz yourself" a belt-and-braces step rather than the only check.

### ST-02 HIGH — "A per-tenant migration failure does not fail the job; the version still activates": wrong since 2026-09-09
- SDK:
  - `skills/manaurum-deploy/SKILL.md:199-200`: "a per-tenant migration failure does not fail the job… the version still activates"
  - `skills/manaurum-deploy/SKILL.md:252`: "marks that tenant's migration run `failed`, and the new version still activates"
  - `references/v2-platform.md:488`: "It does not currently fail the *deploy* (the new version still activates)"
  - `references/v2-platform.md:441`: "Per-tenant failures isolate to that tenant; other tenants continue"
- Platform: `production.py:3822-3870 @285c8a8`. If any tenant failed and `_migration_gate_enabled()` (`:1090-1102`, "Default ON"), the job emits `migration_gate_blocked` and raises `MigrationGateBlocked` (`:219`) before `swarm_applying`. The message says "Add a new migration file that fixes it forward". Landed in d7a5c1a88 (MAN-2510, 2026-09-09); the reason was added by MAN-2622 (2a3b45ba8).
- Verdict: CONFIRMED.
- Impact: the SDK predicts "live with one tenant stuck". The actual outcome is a red deploy that does not activate, and an author who edits the failed file then breaks the tenants where it already applied.
- Fix: SDK. Rewrite all four sentences. Keep "never edit an applied file", and cite the gate's own remedy text.

### ST-03 HIGH — "Only three things fail synchronously; the manifest is validated inside the job": wrong since 2026-09-16/19
- SDK:
  - `skills/manaurum-deploy/SKILL.md:178-189`: "The POST checks the credential, the credential's app scope, and the base64 — nothing else"
  - `skills/manaurum-deploy/SKILL.md:324-334`: sync table with 4 rows, then "Everything else is a job failure"
  - `skills/manaurum-app/SKILL.md:635`: "the manifest has not even been validated yet"
  - `references/publishing.md:22-25`: "Do **not** expect a `422` from `/deploy` for a bad manifest"
  - `references/v2-platform.md:430`: "a manifest or migration rejection does **not** come back as a synchronous 422"
  - Failure table `manaurum-deploy/SKILL.md:345`: lists root-key errors as "Job `failed`"
- Platform: `backend/app/routes/dev_v2_deploy.py:815-819 @285c8a8` runs `owner_deploy_slug` before anything else. It answers `422 {"error":"manifest_validation_failed","errors":[…]}` or `422 app_id_invalid` (`services/v2_apps/owner_deploy.py:84-105`). After that come `413 archive_too_large` (`:832`), then the preflight/claim (`:877-890`): `409 slug_owned_by_another_tenant`, `409 version_already_published`, `409 slug_reserved`, and `403 app_id_out_of_scope` when the app exists but the caller does not own it (`owner_deploy.py:118-131`). Landed in MAN-1586/1587 (72a10918b, 2026-09-16), MAN-2597 (f11a34c05, 2026-09-19) and MAN-2620 (53c12504a, 2026-09-23).
- Verdict: CONFIRMED.
- Impact: agents misread a synchronous 422 or 409 as the platform misbehaving. The `deploy.sh` template handles a non-202 correctly (`manaurum-deploy/SKILL.md:432-436`), so only the prose and tables are wrong.
- Fix: SDK. Rewrite the synchronous-refusals table with these 7 codes.

### ST-04 HIGH — Redeploying the same version: the SDK calls it "useful for dev iteration"; the platform refuses it (immutable tags)
- SDK:
  - `references/v2-platform.md:445`: "the pipeline runs a plain `INSERT`… effectively idempotent… useful for dev iteration"
  - Image paths at `v2-platform.md:437` (`manaurum-registry:5000/v2-app-<slug>:<version>`), `SKILL.md:648` and `manaurum-deploy/SKILL.md:156`.
- Platform:
  - `production.py:4165-4203 @285c8a8` preflight returns `version_already_published` ("MAN-1586 immutable tags"), and the job refuses again at `:593`.
  - The image repository is `v2-app-<slug>-<tenant8>`, pinned by digest (`services/v2_apps/registry_client.py:121-150`).
  - The SDK's own CHANGELOG 2.12.0 already says "on immutable tags costs a version number", but the reference was not updated.
- Verdict: CONFIRMED.
- Impact: a dev loop that redeploys `0.1.0` gets `409` on every attempt after the first.
- Fix: SDK. State that every deploy needs a new semver, and that a failed deploy whose image was pushed also burns that version.

### ST-05 HIGH — The `*` token scope and grant wildcard survive in 6 places; the scope model is pre-MAN-2597
- SDK:
  - `references/v2-platform.md:387`: "blank for `*` (all apps owned by the developer…)"
  - `:398`: `-d '{"apps": ["*"]}'`
  - `:421`: "`["*"]` (default)"
  - `:361`: "Wildcard `*` is honored"
  - `:109`: "Wildcard `"*"` grants everything"
  - `manaurum-deploy/SKILL.md:330`: "Use a credential scoped to this app (or `*`)"
  - `:401`: "Cap: 5 active per (user, tenant)"
  - `README.md:83-84`: "choose 'All apps' scope"
- Platform:
  - `backend/app/routes/developer/v2_credentials.py:261-295 @285c8a8`: an empty list gives `400 apps_required`; `"*"` gives `400 apps_wildcard_not_allowed`.
  - `:318-356`: listing an app you do not own, or one that does not exist yet, gives `403 apps_not_owned` ("To deploy an application that does not exist yet, issue a token for all your applications").
  - `:194-206`: `scope_kind: "owner"` (MAN-2597); `:104` owner default is 90 days; `:74` cap is 20.
  - `services/capabilities/granted_capabilities.py:13`: "There is no wildcard (MAN-1585)".
- Verdict: CONFIRMED. The CHANGELOG 2.11.1 claim covered capabilities-reference.md only; v2-platform.md was missed.
- Impact: the documented API recipe mints nothing; following it gets 400. Following the "list the slug" advice for a brand-new app gets 403. The SDK never mentions the owner token, which is the only way to deploy a new app.
- Fix: SDK. Rewrite §4 Tokens around `scope_kind: owner` vs `apps`, remove every `*`, and fix the cap. The guide already has this text (`V2_DEVELOPER_GUIDE.md:120-144`).
- Related: MAN-3199.

### ST-06 HIGH — The exact MAN-1899 sentence ("runtime is not strict") is still in v2-platform.md
- SDK:
  - `references/v2-platform.md:24`: "The `runtime` and `metadata` **sub**-objects are *not* strict. Unknown keys there validate silently… how a typo like `runtime.byo_endpoint_url` passes validation and does nothing."
  - The same file contradicts it at `:203` ("`runtime` is **strict**") and `:310` ("since `runtime` became strict it is a `422`").
- Platform:
  - `backend/app/services/_schemas/manifest_v2.schema.json:96 @285c8a8`: `runtime` has `"additionalProperties": false` with 11 declared keys, including `port` and `egress_allowed_hosts` (`:192`).
  - `metadata` is genuinely non-strict.
- Verdict: CONFIRMED.
- Impact: this is the regression CHANGELOG 3.1.0 says it fixed ("Five places here still said it was not strict"); a sixth survived. It is also wrong that `port` and `egress_allowed_hosts` are "undeclared".
- Fix: SDK. Delete the `runtime` half of the sentence and keep it for `metadata`. Have check_repo.py flag "not strict" near "runtime".
- Related: MAN-1899.

### ST-07 HIGH — `permissions` enum "today: `["microphone"]`", stated in 5 places; camera has been valid since 2026-09-02
- SDK:
  - `skills/manaurum-app/SKILL.md:219`
  - `references/v2-platform.md:104` ("Enum today: `["microphone"]` (MAN-1316)")
  - `references/publishing.md:64`
  - `skills/manaurum-setup/SKILL.md:175-176`
  - (`sdk-api.md:51` example)
  - Contradicted by `SKILL.md:733` ("delegates only `microphone` and `camera`").
- Platform:
  - `manifest_v2.schema.json:318-328 @285c8a8`: enum `["microphone","camera"]`.
  - `frontend/src/components/window/iframeHostPolicy.ts:68` `camera: 'camera'`.
  - `manifest_v2_validator.py:266-273`: non-empty `permissions[]` with `runtime.mode: "byo"` is refused (MAN-1922).
  - Landed in 413731243 (MAN-1920, 2026-09-02).
- Verdict: CONFIRMED.
- Impact: an agent building a camera or barcode app is told it is impossible. The byo + permissions ban is undocumented.
- Fix: SDK. Change all five places, add the CLI ≥ 0.3.0 note, and add the byo ban.

### ST-08 HIGH — The `os.ai.complete` contract is pre-MAN-2412 (2026-09-07)
- SDK:
  - `references/capabilities-reference.md:347-387`: "(BYOK) The tenant's API key is used"; `provider` and `model` marked required; errors `412 missing_provider_credentials`, `400 unsupported_provider`.
  - `SKILL.md:391`: "LLM (BYOK — tenant configures keys…)".
- Platform:
  - `backend/app/services/capabilities/ai.py:1-12 @285c8a8`: "Text completions share workspace backend selection and the managed spending allowance with the Assistant".
  - The schema requires only `messages` (`:179`); `provider` and `model` are optional.
  - Workspace context is mandatory (`ai.py:1065-1067`, `routes/capability_gateway.py:847-866`, `services/capabilities/completion_context.py:105-112`): forward `X-Manaurum-User-Context` or send `X-Manaurum-Workspace-Id`. Otherwise the call fails with `412 workspace_context_required` or `403 workspace_context_unavailable`.
  - New errors: `403 ai_disabled`, `412 ai_backend_unavailable`, `429 ai_spend_cap`, `412 integration_not_configured`.
  - `missing_provider_credentials` exists nowhere in `backend/app`.
  - Guide: `V2_DEVELOPER_GUIDE.md:338,365-377,1036-1060`.
- Verdict: CONFIRMED.
- Impact: apps send a needless `provider`, which pins them off the workspace's AI. Background jobs in an app installed in more than one workspace get 412. Error handling keys on a code that never arrives.
- Fix: SDK. Rewrite the section from `ai.py`, `completion_context.py` and guide §7.

### ST-09 HIGH — `os.files.upload` example omits the required `size_hint` (since 2026-08-13)
- SDK: `references/capabilities-reference.md:167` shows the input `{ "key", "content_type" }` with a table of two required fields. No quota or rate limits are mentioned, and `size_hint` appears nowhere in skills/.
- Platform:
  - `backend/app/services/capabilities/files.py:95 @285c8a8`: `"required": ["key", "content_type", "size_hint"]` (MAN-1707, c1656b9e0).
  - Limits per the guide (`V2_DEVELOPER_GUIDE.md:425-457`): 50 MB per object, signed as exact content-length; 1 GB / 10 000 objects per (app, tenant); 20/min and 200/h; TTL 300 s default, 3600 s max.
- Verdict: CONFIRMED.
- Impact: every call copied from the SDK gets `422 input_schema_violation`.
- Fix: SDK. Add `size_hint`, the signed Content-Type rule and the limits table.

### ST-10 HIGH — "/agent/* is on the public internet": false since 2026-07-27 (MAN-1432), stated in 6 places
- SDK:
  - `references/v2-platform.md:117`: "anyone on the internet can POST `/agent/<name>`… Verified 2026-07-26"
  - `skills/manaurum-app/SKILL.md:554`
  - `templates/check_app.py:16,290`: "public internet with no gateway in front of it"
  - `templates/v2-starter/src/agent_routes.py:20`
  - `templates/v2-starter/tests/test_manifest.py:12`
- Platform:
  - `backend/app/routes/v2_app_gateway.py:80-98 @285c8a8`: `_RESERVED_PREFIXES = ("/agent/",)`.
  - `:786-797`: answers `404 route_not_declared`.
  - Fix 821af49e0 (2026-07-27). Monorepo commit e04501bde (MAN-1444) corrected the same claim in the CLI scaffold the same day, and its comment calls the old wording "the sort of belief that ends with an unauthenticated handler".
- Verdict: CONFIRMED. The verification date in the SDK is one day before the fix.
- Impact: the advice to verify the JWT is still right, but the factual claim is wrong, and a linter message asserts it to every user.
- Fix: SDK. Use the neutral MAN-1444 wording: "the Manaurum gateway refuses the prefix; your JWT check must still hold on its own".

### ST-11 MEDIUM — The egress "Unresolved — 0.0.0.0 Hosts blackhole" warning is stale (since 2026-09-02)
- SDK: `references/v2-platform.md:326`: "The deploy also writes each declared host into the container's Swarm `Hosts` entries as `0.0.0.0 <host>`… a live monorepo bug".
- Platform: 504ef87ad (MAN-2263) removed it. `services/v2_apps/stack_generator.py:32,365-373 @285c8a8` now writes only the `manaurum.egress_allowed_hosts` label. Container-level egress is unenforced: the MAN-185 phase B apps and egress networks are "inert until configured" (2bcc23917).
- Verdict: CONFIRMED.
- Impact: a raw `fetch` to a declared host now works; the SDK says it fails.
- Fix: SDK. Say that container egress is currently not enforced either way, and that `os.http.fetch` is the enforced path.

### ST-12 MEDIUM — `os.drive.publish`: notification, size cap and extension list are all stale
- SDK: `references/capabilities-reference.md:238-241`: "they get a notification… Limits: 5 MB; extensions `md txt csv json pdf png jpg jpeg webp`".
- Platform:
  - `services/capabilities/drive.py:18 @285c8a8`: "No notification: the user asked for the save" (MAN-2991, 5203d8952, 2026-09-28).
  - `services/drive_publish.py:51`: `PUBLISH_MAX_BYTES = 50 MiB` (MAN-1959, 2026-09-01).
  - Guide `:476-488` lists ~20 extensions and the error codes.
- Verdict: CONFIRMED.
- Fix: SDK. Copy the guide paragraph, and tell authors to show their own confirmation.

### ST-13 MEDIUM — Notifications: "in-app keeps the first 2000", and no expiry
- SDK: `references/capabilities-reference.md:521`: "`body` 1–4096 chars; in-app keeps the first 2000." There is no mention of the 7-day lifetime.
- Platform: `services/notification_service.py:48-49 @285c8a8` (`TITLE_MAX = 200`, `BODY_MAX = 4096`) and `:41-42` (7-day lifetime for both kinds), from MAN-2992 (a8abea302, 2026-09-28). Guide `:629-631`.
- Verdict: CONFIRMED.
- Fix: SDK. One line each.

### ST-14 MEDIUM — The handshake answers the first sender; the platform rule since 2026-09-13 says trust only the parent shell's origins
- SDK: `skills/manaurum-app/SKILL.md:309-325` (the snippet replies to any `manaurum:init`) and `templates/v2-starter/src/static/index.html:63-80` (replies to `event.source` at `event.origin`, with no check).
- Platform: MAN-2506 (e863f95dc). `V2_DEVELOPER_GUIDE.md:1317-1333 @285c8a8` and `manaurum-cli-py/manaurum_cli/templates/index.html.template:31-37` require `event.source === window.parent` and `SHELL_ORIGINS = ['https://manaurum.com','https://app.manaurum.com']`.
- Verdict: CONFIRMED.
- Impact: any page that frames the app can drive its theme and init state, and every starter-derived app inherits this.
- Fix: SDK, starter and snippet. Adopt the CLI template's guard. check_ui.py could require it.
- Related: MAN-2561 (the same gap in `manaurum-v2.mjs`).

### ST-15 MEDIUM — Five shipped capabilities missing from the catalogue
- SDK: `SKILL.md:383-399` ("Capabilities available today") and the `capabilities-reference.md` headings. None mention `os.ai.image_submit`/`os.ai.image_poll` (MAN-2133, 2026-08-28), `os.ai.providers` (MAN-2136, 2026-08-31), `os.drive.delete` (MAN-1958/1959, 2026-09-01) or `os.locations.list`/`os.locations.get` (MAN-2185, 2026-09-02).
- Platform: registered in `services/app_builder_v2_capabilities.py:56-78 @285c8a8`, `services/capabilities/drive.py:891`, `ai.py:1731` and `main.py:342-350`. The CLI knows them (`manaurum-cli-py/manaurum_cli/project_checks.py:84-106`). The guide documents image generation (`:1205`).
- Verdict: CONFIRMED.
- Fix: SDK. Add the entries, copying from the guide and the handler schemas.

### ST-16 MEDIUM — Slug rules: "schema only enforces minLength 1, keep under ~40 in practice"
- SDK: `references/v2-platform.md:80` and `skills/manaurum-setup/SKILL.md:144-145`. No reserved-slug list anywhere. (`SKILL.md:207` has the right regex.)
- Platform:
  - `owner_deploy.py:92-105 @285c8a8`: `422 app_id_invalid` "3-40 characters… not shaped like a UUID", at request time.
  - `services/v2_apps/reserved_slugs.py` `RESERVED_SLUGS` (app, apps, www, api, mcp, registry, …) is refused by `manifest_v2_validator.py:262-267` (MAN-2500, 2026-09-13).
  - `traefik_yaml.py:52,58`: `MAX_SLUG_LEN = 40` (MAN-2845).
- Verdict: CONFIRMED.
- Fix: SDK. Give one rule in all three places and list the reserved names. check_app.py could check both.

### ST-17 MEDIUM — The write-verb refusal for agent capabilities is undocumented and unchecked
- SDK: `references/v2-platform.md:152` teaches `is_write` carefully, but never says that an explicit `"is_write": false` on `create_`/`add_`/`update_`/`delete_`/`log_`/`save_`/… is refused at deploy. `check_app.py` and starter `tests/test_manifest.py` do not check it.
- Platform: `manifest_v2_validator.py:143-150 @285c8a8` `_WRITE_VERB_PREFIXES` and `_write_verbs_declared_read_errors` (MAN-2358, 0e7d56143, 2026-09-06).
- Verdict: CONFIRMED.
- Fix: SDK. Add one paragraph and a check_app.py rule (it is pure manifest).

### ST-18 MEDIUM — The CLI install is pinned to 0.2.0; the README says no released wheel has the new scaffold
- SDK:
  - `README.md:78` pins `cli-v0.2.0`.
  - `README.md:103-106`: "That rewrite is in no released wheel… install is `cli-v0.2.0`".
  - `README.md:153-154`.
  - `scripts/open-claims.txt:18`: "the released wheel predates the new scaffold".
- Platform:
  - `gh release list`: `cli-v0.3.0` "Latest", 2026-09-03.
  - Monorepo 53d60f88f (MAN-2301) moved every pin to 0.3.0.
  - 0.3.0 (version bump 413731243, 2026-09-02) postdates the MAN-1397 scaffold rewrite (a466425ec, 2026-07-27).
  - 0.2.0 rejects `"camera"` locally.
- Verdict: CONFIRMED.
- Impact: users install a CLI with the old scaffold, no camera, and no MAN-1897 preflight. The open-claims register vouches for a false sentence, because the gate checks only that the ticket is open, not that the sentence is true.
- Fix: SDK. Pin 0.3.0 and reword the MAN-1385 claim to "not on PyPI" only.

### ST-19 MEDIUM (UNVERIFIABLE-WITHOUT-PROD) — Staged runtime hardening is not mentioned anywhere
- SDK: nothing about a read-only root FS, `/tmp` tmpfs or `HOME`. The starter already runs as uid 10001 (`templates/v2-starter/Dockerfile:26`), which helps.
- Platform: MAN-2264 (438e67268). `stack_generator.py:36-39,167-175 @285c8a8`: when hardened, CapDrop ALL, ReadOnly, User 10001, NoNewPrivileges, a 64 MiB tmpfs at /tmp, and HOME=/tmp. It is enabled per slug or for all apps via `MANAURUM_V2_RUNTIME_HARDENING` (`production.py:361-404`), and the author cannot opt out.
- Verdict: UNVERIFIABLE whether it is on in prod.
- Impact: an app that writes to disk outside /tmp, or caches under `~`, will crash the day ops flips it.
- Fix: SDK (and the guide). Add a "write only to /tmp, ≤64 MiB, treat the FS as read-only" rule.

### ST-20 LOW — `/__manaurum/` is reserved on every app subdomain
- SDK: silent.
- Platform: `routes/v2_app_runtime_errors.py:1-12 @285c8a8` (MAN-3132, 2026-09-30) answers `POST /__manaurum/runtime-errors` itself. Guide `:1559-1564`: "Do not serve anything of your own under `/__manaurum/`."
- Fix: SDK. One line, and possibly a check_app.py route rule.

### ST-21 LOW — "Logs: first slice returns a stub; full log streaming is planned"
- SDK: `SKILL.md:668`.
- Platform: `routes/dev_v2_deploy.py:1375-1403 @285c8a8` returns a real Swarm tail with `?tail=`, clamped to 1000 lines, and `404 service_not_found`.
- Verdict: CONFIRMED.
- Fix: SDK.

### ST-22 LOW — App Store v2 "UI pending; install via the API", and "auto-installed implicitly"
- SDK: `references/v2-platform.md:635` and `:629`.
- Platform:
  - The marketplace UI and routes exist: `routes/app_store_v2_marketplace.py:154,310,465 @285c8a8`, used by `frontend/src/stores/appStoreStore.ts`.
  - MAN-2749 requires a ready current version to install.
  - MAN-2693 (baf554a3e): in the public tenant the home install reaches only each owner's primary workspace.
- Fix: SDK.

### ST-23 LOW — Pipeline description out of date
- SDK:
  - `references/v2-platform.md:432-443` and `manaurum-deploy/SKILL.md:224-233` put migrations last and omit the readiness, migration-gate and agent-capability-sync phases.
  - "Builds the Docker image **inside the backend container**" is no longer how it works.
  - "~7–10s end to end".
- Platform: phases at `production.py:3639-4067 @285c8a8` run in this order: manifest_validated → migrations_extracted → image_pushing (build, push, DB, per-tenant migrations) → migration gate → swarm → traefik → readiness → agent_capabilities_synced → activated. MAN-2262 (809eef9fc) moved builds to a deployer service. The job result also carries `ui_warnings` (MAN-2510), which the SDK never mentions.
- Fix: SDK.

### ST-24 LOW — Hard-coded test count went stale
- SDK: `skills/manaurum-setup/SKILL.md:41`: "`pytest   # 19 passed`". The orchestrator measured 38 passed. `scripts/check_repo.py` exists to catch exactly this and misses the `# N passed` form.
- Fix: SDK. Remove the count and teach check_repo the form.

### ST-25 LOW — "The shell at `manaurum.com`"
- SDK: `references/sdk-api.md:124`.
- Platform: the shell is canonical at `app.manaurum.com` (MAN-2498/2499, d3be8fa04); `SHELL_ORIGINS` contains both hosts (guide `:1329`). The SDK's own README:4 already says app.manaurum.com.
- Fix: SDK.

### Incidental wrong facts found on the way (not staleness; other dimensions likely own them)
- `SKILL.md:678` `422 egress_not_declared`: the handler returns 412, and has since 2026-05-07 (`services/capabilities/http_fetch.py:261`). v2-platform.md:365 has it right.
- `SKILL.md:677` `422 migration_validation_failed`: this code does not exist in `backend/app`.
- `capabilities-reference.md:496` (OCR) `412 missing_provider_credentials`: does not exist either.
- `SKILL.md:675` / `v2-platform.md:365` give the blanket advice "use the UUID" for `app_id_must_be_uuid`. That contradicts the 3.1.0 slug/UUID split (MAN-1588 / MAN-1491 territory).
- Undocumented developer surface: `GET /api/app-usage/{app_id}` (MAN-3131, `routes/app_usage.py`), which gives the author usage counts.

---

## Ticket citations in the SDK (task 3)

| Ticket | Linear state | SDK sentence still true? |
|---|---|---|
| MAN-1112 | Todo | Yes. No grant screen (`capabilities-reference.md:557`, open-claims). |
| MAN-1385 | Backlog | **No.** `README.md:103-106,153-154` and `open-claims.txt:18` say the released wheel predates the scaffold; 0.3.0 has it (ST-18). Only "not on PyPI" is still true. |
| MAN-1401 | In Progress | Yes (`design.md:335`, `app.css:20`). |
| MAN-1404 | In Progress | Yes (`reference-apps.md:18`). |
| MAN-1316 | Done | Cited as origin; **"Enum today: microphone" next to it is false** (ST-07). |
| MAN-1425 / MAN-1872 | Done (1872 lookup failed in the script) | Yes, but ST-17 is missing beside it. |
| MAN-1585 | Done | `capabilities-reference.md:60` is true; **v2-platform.md still teaches the wildcard** (ST-05). |
| MAN-1899 | Done | `v2-platform.md:203`, `check_app.py:77,368` are true; **`v2-platform.md:24` contradicts it** (ST-06). |
| MAN-163, 235, 1321, 1327, 1393, 1397, 2439, 2510, 2532, 2541, 2624, 990 | Done | Historical citations, true. |
| MAN-2516 | Done | Section is true except the 2000-char line (ST-13). |
| MAN-2456 | Backlog | Cited as a lesson (`/tmp` collision); fine. |
| MAN-2849 | Backlog | SDK side fixed in 2.13.0; ticket still open (deployed apps not fixed). Wording is fine. |
| MAN-608 | Backlog (epic) | `sdk-api.md:252` "MAN-608 B3" picker; the picker exists. Fine. |
| MAN-9999 | n/a | Fixture in `linter_mutations.py`. |

Other time-words checked and still true: `os.tenant_config.get` "do not rely" (`services/capabilities/tenant_config.py` still reads the app-builder config); `os.apps.call` "in-process today" (`rpc.py:15-19`); webhooks/schedules "deferred" (guide §9 still TODO); `migrate_command` unused.

## CHANGELOG claims vs platform (task 2)
- 3.1.0: verified true.
  - `public_paths` / `health_path` are read.
  - Stream limits 50 / 900 s / 60 s match `v2_gateway_streaming.py:57-76`.
  - The session renewal is real.
  - **Exception:** "Five places… said it was not strict", but a sixth remains (ST-06).
- 3.0.0: verified true. The v1 `/sdk` redirect is at `frontend/next.config.ts:48`, and `manaurum:ai-*` is rejected with a reply (MAN-3017).
- 2.14.0: verified true (MAN-3008 lazy pool; the platform also removed the Swarm restart cap).
- 2.12.0: verified true (the CONCURRENTLY rule is in both validators; validation is per file).
- 2.11.1: true for notifications (10/h and 50/d at `notifications.py:50`). The "wildcard removed" fix was applied to one file only (ST-05).
- 2.10.0: the `is_write` NULL→write fallback is true. MAN-2358 (refusal of explicit false on write verbs) landed later and was not reflected (ST-17).

## V2_DEVELOPER_GUIDE vs SDK, where they disagree (task 4; excluding MAN-1491's app-id/breaking/transactions)
In each row below, the code backs the guide.

| Topic | Guide @285c8a8 | SDK | Finding |
|---|---|---|---|
| Readiness probe | `:1918-1950` | "no probe" ×4 | ST-01 |
| Token scope | `:120-144` (owner token default, `*` gone) | `*` ×6 | ST-05 |
| `permissions` camera | `:263-271` | microphone-only ×5 | ST-07 |
| Shared text AI / workspace context / `ai_spend_cap` | `:338,365-377,1036+` | BYOK-only, provider required | ST-08 |
| `os.files` limits and `size_hint` | `:425-457` | absent | ST-09 |
| `os.drive.publish` | `:476-488` (50 MB, no notification) | 5 MB, notification | ST-12 |
| Notification body and expiry | `:629-631` | 2000 chars, no expiry | ST-13 |
| Handshake origin rule | `:1317-1333` | first sender | ST-14 |
| `os.ai.image_*` | `:1205` | absent | ST-15 |
| `/__manaurum/` reserved | `:1559-1564` | absent | ST-20 |
| CLI version | `:73` 0.3.0 | README 0.2.0 | ST-18 |
| Gateway refuses owner tokens on capability calls | `:324` `owner_scoped_credential_not_accepted` | absent | LOW; containers use the runtime token |

Places where both the guide and the SDK are stale or silent: the migration gate (ST-02), synchronous deploy refusals and `version_already_published` (ST-03/04), reserved and 40-character slugs (ST-16), the write-verb refusal (ST-17) and runtime hardening (ST-19). These belong in MAN-1491's scope as well.

## Questions (no proof either way)
- Q1: Is `MANAURUM_V2_RUNTIME_HARDENING` set in prod, and for which slugs? This decides whether ST-19 is CRITICAL (an app writing to `/app` crashes) or a forward-looking gap.
- Q2: Is `v2_strict_capability_grants` on in prod? The SDK repeatedly says "with strict grants switched on"; the default is off.
- Q3: Are `MANAURUM_EGRESS_NETWORK` / `MANAURUM_OVERLAY_NETWORK` set in prod (MAN-185 phase B)? If so, the egress statement in ST-11 changes again.
- Q4: Does a 0.3.0 wheel already carry the MAN-2500 reserved-slug mirror and the MAN-2624 rule, or did those land after the 0.3.0 cut without a bump (CHANGELOG 2.12.0 suggests the latter)? If they landed after, "pin 0.3.0" is necessary but not enough.

## Summary
Covered:
- all ~45 developer-visible commits in mono-log, with diffs read for the recent ~3 weeks;
- a title-level triage of 155 app-relevant commits outside those paths;
- every MAN-N cited in the SDK against Linear;
- a grep sweep for time-words;
- the CHANGELOG 2.10–3.1 claims;
- a guide-vs-SDK diff on the topics above.

25 findings: 10 HIGH, 9 MEDIUM (one UNVERIFIABLE), 6 LOW, plus incidental wrong codes.

Not done: line-by-line diffs of the Studio/demo/finance commits (judged not developer-facing from titles), a full env-var parity check, the OCR/embed/transcribe error tables, and MAN-2248's effect on cross-app `fetch`.

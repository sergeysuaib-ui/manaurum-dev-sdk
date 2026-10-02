# Dimension `gaps`: the areas the completeness skeptic flagged

SDK = `C:\dev\wt\sdk-audit` @6f52dce. Platform = SNAP @285c8a8 (a few frontend files were read with `git show 285c8a885:`).
This is a read-only audit. Nothing was executed against prod. "CONFIRMED" here means confirmed by reading the code, not by running it.
I checked every item against CONSOLIDATED.md and do not repeat anything already listed there. Where a finding extends an existing item, the item number is given.

---

## Findings

### G-01 HIGH: An app cannot receive events. `consumes.events` and drive change events are inert
- **SDK:** `skills/manaurum-app/references/capabilities-reference.md:255-256` says *"Subscribe to `drive.{your_slug}.file.{created|updated|deleted}` in `consumes.events`"*. `:582` says the dispatcher *"delivers to subscribers (other apps that registered for this event type)"*. Neither the SDK nor README "Honest gaps" says that registering is impossible.
- **Platform:**
  - No code reads the manifest's `consumes` or `provides`. A grep of `backend/app` for `get("consumes")` and `["consumes"]` finds nothing.
  - `event_subscribers` is only ever SELECTed (`backend/app/services/events/dispatcher.py:92-101 @285c8a8`). `git grep` finds no INSERT anywhere at 285c8a885 outside tests.
  - With no subscribers, the dispatcher still marks the event delivered (`dispatcher.py:134-137`: *"No registered subscribers — nothing to do; mark delivered"*).
  - MAN-2485 §7 says it directly: *"`event_subscribers` has no writer outside tests, so a v2 app cannot react to anything"*. MAN-3072 (Todo) calls its own planned writer *"the first production writer of that table"*.
- **Verdict:** CONFIRMED.
- **Impact:** A developer builds a Drive-sync feature or an inter-app reaction exactly as documented. The deploy is green, and nothing ever arrives.
- **Fix (SDK):**
  - State that `os.events.emit` is emit-only today, that `consumes.events` is not read, and that drive change events reach no one.
  - Remove or caveat the subscription instruction at CR:255.
  - Add this to README "Honest gaps".
- **Related:** MAN-2485, MAN-3072. Overlaps skeptic #14, which asked how a consumer receives events. The answer is that it cannot.

### G-02 HIGH: An agent capability silently disappears when `sdk__<slug>__<name>` exceeds 64 characters
- **SDK:** `v2-platform.md:132` gives the only length rule for `agent_capabilities`: *"Hard cap 400 chars"* on `description`. Nothing limits the combined tool name, and `check_app.py` has no rule for it.
- **Platform:**
  - The tool name is built as `f"sdk__{safe_app}__{safe_cap}"` (`backend/app/agent/sdk_capability_tools.py:80-85 @285c8a8`).
  - `Tool.__post_init__` raises *"Tool.name too long (>64 chars)"* (`backend/app/agent/types.py:107-108`).
  - `tool_registry.py:419-426` catches the error and only logs `sdk_capability_tool_build_failed`.
  - The schema allows `name` up to 64 characters (`manifest_v2.schema.json` agent_capabilities.items.name). Slugs may be up to 40 characters (`traefik_yaml.py:52`, `{1,38}`).
  - Nothing at deploy checks the sum, which must be: slug length + capability name length ≤ 57.
- **Verdict:** CONFIRMED by reading the code. The arithmetic is exact. Not run.
- **Example:** slug `warehouse-inventory-manager` (27) with capability `list_low_stock_items_by_location` (32) gives a 66-character tool name, so the tool is dropped. The SDK itself warns at `v2-platform.md:118` that when a tool is missing, the Assistant then *guesses*.
- **Fix (both):**
  - SDK: state the rule (slug with `-` replaced by `_`, plus name, ≤ 57) next to the 400-character rule, and add a check_app rule.
  - Platform: reject the manifest at deploy instead of dropping the tool at request time.
- **Related:** none found in Linear (searched "Tool.name too long", "tool name 64").

### G-03 MEDIUM: The setup skill's "required keys" manifest gives a read-only capability with no `is_write`
- **SDK:** `skills/manaurum-setup/SKILL.md:116-126` declares `list_items` (*"List the user's items… Not for creating anything."*) without `is_write`. This contradicts the SDK's own rule at `v2-platform.md:152` (*"Write `"is_write": false` explicitly on every read-only capability"*).
- **Coverage:** `templates/check_app.py` has no `is_write` rule. Only the starter's own test enforces it (`templates/v2-starter/tests/test_manifest.py:87-100`), so an app written from the setup snippet passes the linter.
- **Platform:** `sdk_capability_tools.py:142-166 @285c8a8`: when the flag is absent, `return dispatch != "core"`, which is True for every hosted app. As a result, `write_gate.py:165` puts an approval card in front of every call.
- **Verdict:** CONFIRMED.
- **Impact:** Every "what's in my app?" question stops on an approval card. The read is also excluded from cross-app insight.
- **Fix (SDK):**
  - Add `"is_write": false` to the setup example.
  - Add a check_app rule: every `agent_capabilities[]` entry must state `is_write`.

### G-04 MEDIUM: The `/agent/*` dispatch contract leaves out its timeout and its idempotency behaviour
- **SDK:**
  - `v2-platform.md:112` and `:152` (*"deduped for idempotency"*) describe the dispatch.
  - `templates/v2-starter/src/agent_routes.py:10-35` describes the reply contract.
  - Neither mentions a timeout, retries, or what the app must do to stay idempotent. The only "30 s" anywhere in the SDK is a DB-pool comment (`v2-platform.md:604`).
- **Platform:**
  - The dispatch timeout is `_INVOKE_TIMEOUT_SECONDS = 30.0`. When it fires the call is reported as *"timed out"*, but the container keeps running the request (`backend/app/agent/v2_capability_dispatch.py:43,144-153 @285c8a8`).
  - Dedup works like this: `idempotency_key` is **popped** from the model's arguments and matched against an in-memory per-turn map. It is never forwarded to the container (`backend/app/agent/dispatcher.py:109-122`).
  - A non-2xx reply body (first 200 characters) is placed into the model's context (`v2_capability_dispatch.py:159-163`).
  - Readers with `is_write:false` run in parallel (`parallel_safe`, `sdk_capability_tools.py:256`).
- **Verdict:** CONFIRMED.
- **Impact:** A write that takes more than 30 s is reported to the model as failed while it still completes. A retry in a later turn (or another turn) then writes twice, and the app gets no key to dedupe on.
- **Fix (SDK):**
  - Document the 30 s budget: aim for under 25 s, and run long work asynchronously.
  - Tell developers to make writes idempotent on a natural key.
  - Say that Core's dedup is per-turn and does not reach the app.
  - Say that error bodies are shown to the model, so no stack traces.
- **Platform side note:** `docs/handoff/V2_DEVELOPER_GUIDE.md:1490,1494 @285c8a8` promises *"approval + undo + dedup"*. But `backend/app/agent/undo.py:355-373` has inverse handlers only for Core kinds (file_*, shift_create, …), so an app write is never undoable. The guide should drop "undo" for v2 apps. The SDK does not repeat the claim.

### G-05 MEDIUM: The approval-card guidance (MAN-2998) is missing from the SDK
- **SDK:** a grep of `skills/` and `templates/` finds no mention of the approval card or of "only the fields that change". `v2-platform.md:126-150`'s write example `create_family_space_item` is fine on its own, but the SDK has no update-capability guidance at all.
- **Platform:** `V2_DEVELOPER_GUIDE.md:1508-1555 @285c8a8` (MAN-2998, Done) sets out the rules:
  - the card caps arguments at 10 keys per level;
  - an update takes only the changed fields, and explicit `null` clears a field;
  - the identifier is required, at the top level, and id-like;
  - `additionalProperties:false` makes undeclared keys fail, but only *after* approval.
- **Verdict:** CONFIRMED (the gap).
- **Impact:** A write written as a full-record replace gives a truncated card. Any field the model drops while copying the record is silently wiped.
- **Fix (SDK):** port the MAN-2998 paragraph into v2-platform § agent_capabilities and add an `update_*` example.
- **Related:** MAN-2998, MAN-2983.

### G-06 MEDIUM: Deleting an app, uninstalling it, and what happens to its data are all undocumented, and redeploying a deleted slug is a trap
- **SDK:** the whole lifecycle is one line, `v2-platform.md:633` (*"Uninstall is soft (sets `tombstoned_at`)"*). There is no word on deleting an app, on data retention, on export, or on reusing a slug. The CLI has no delete command (`manaurum-cli-py/manaurum_cli/main.py` commands: init/validate/…/diff).
- **Platform:**
  - **Uninstall** only tombstones the row (`backend/app/services/app_store_v2.py:381-390 @285c8a8`). The schema, kv, files and secrets all stay.
  - **Delete** is `DELETE /api/developer/apps/{slug}` (`backend/app/routes/developer/__init__.py:1412-1420`) followed by `_real_teardown_runner` (`backend/app/services/v2_apps/production.py:4558-4590`). It deletes `app_kv`, `app_secrets`, `v2_app_migrations`, the versions and the runtime credentials. It deliberately **keeps** the managed schema (*"redeploying the same slug reattaches to it"*).
  - os.files objects are keyed `app/{app_id}/{tenant}/…` (`capabilities/_storage_keys.py:72`; the app_id is the slug, according to the SDK). Teardown deletes only the `v2-app-source/` prefix (`production.py:4678`), so those objects survive too.
  - The slug is reserved for 30 days (`production.py:1487`).
- **Trap (LIKELY):**
  1. The migration ledger is keyed by the app **UUID** (`production.py:3493-3510`) and is deleted at teardown, but the schema is kept by **slug** (`db_broker.py:135-142`).
  2. So redeploying the same slug starts with an empty ledger and re-runs `0001_init.sql` against tables that already exist.
  3. A plain `CREATE TABLE` then fails that tenant, and the MAN-2510 gate (H4) fails the deploy.
  4. After a delete and redeploy, the old DB rows and files come back while kv and secrets are gone.
- **Verdict:** the lifecycle facts are CONFIRMED. The re-run failure is LIKELY (not executed).
- **Fix:**
  - SDK: add a section, "Uninstall vs delete: what survives (schema, files) and what does not (kv, secrets, ledger)". Mention the 30-day slug reservation, and that there is no tenant export or erase hook.
  - Platform: drop the schema on teardown, or keep the ledger with it, or key the ledger by slug.
- **Related:** MAN-601, MAN-1587, MAN-1876.

### G-07 MEDIUM: `migration.breaking` is a whole-bundle switch, and once a destructive file ships it can never be turned off
- **SDK:**
  - `v2-platform.md:106` (*"`breaking: true` lets the DDL validator through destructive statements"*), `:525`, and `skills/manaurum-deploy/SKILL.md:256-259` present it as a per-change opt-in.
  - `v2-platform.md:54-58`'s manifest example sets `"rollback_strategy": "drop new table"` with no note that the field is ignored.
- **Platform:**
  - `backend/app/services/v2_apps/deploy_pipeline.py:478-517 @285c8a8` validates **every** file in `migrations/` on every deploy with the current manifest's `breaking` flag. Already-applied files are not exempt (`for filename, file_sql in migration_files: validate_migration_sql(file_sql, breaking_allowed=breaking, …)`).
  - The schema description says *"`reason` and `rollback_strategy` are recorded and read by nothing today"*.
- **Verdict:** CONFIRMED by reading the code.
- **Impact:** After v3 ships `0003_drop_col.sql` with `breaking:true`, any later version that resets `breaking` to false is refused at deploy. Keeping it true switches off the destructive guard for every future migration.
- **Fix (SDK):**
  - Say that `breaking` applies to the whole `migrations/` directory on every deploy and must stay true once a destructive file exists.
  - Mark `reason` and `rollback_strategy` as informational only.
  - Teach expand/contract (two-phase) migration. The deploy skill already says rollback does not revert the schema (`deploy SKILL.md:345`, `:271-273`).
- **Platform:** consider validating only files that are not yet applied, or recording the flag per file.

### G-08 MEDIUM: `data.shared` and `data.connection_cap` do nothing, but the SDK describes behaviour for both
- **SDK:**
  - `skills/manaurum-app/SKILL.md:213` says `{"shared": true}` means *"one cross-tenant schema — you own every `WHERE tenant_id`, and tenant admins see an isolation warning at install"*.
  - `v2-platform.md:91` says the same and lists `connection_cap`.
- **Platform:**
  - `_manifest_needs_managed_db` (`backend/app/services/v2_apps/production.py:784-803 @285c8a8`) returns True for `shared`, exactly as for the default. Nothing else reads `shared`: a grep of `backend/app/services/v2_apps`, `db_broker.py` and the app-store routes finds no use. So the app gets the same per-(app, tenant) schema.
  - The "isolation warning" exists only in the schema description (`manifest_v2.schema.json:225`). Neither backend nor frontend has it.
  - `connection_cap` is never read. The broker cap comes from the env var `MANAURUM_BROKER_CONN_CAP` (`backend/app/services/db_broker.py:117-118`).
- **Verdict:** CONFIRMED.
- **Impact:** A developer who chooses `shared` for cross-tenant analytics adds `tenant_id` columns, and every tenant still gets its own schema. A developer who raises `connection_cap` gets nothing from it.
- **Fix (both):**
  - SDK: describe `shared` as "currently identical to the default" and `connection_cap` as "ignored".
  - Platform: correct the schema text, which is published at `frontend/public/sdk/manifest_v2.schema.json:225`.

### G-09 MEDIUM: The `offline` (Manaurum Edge) block is inert for a v2 hosted app, and the SDK does not say so
- **SDK:**
  - `v2-platform.md:103` describes `offline.features/reference_data/streams` as a working Edge declaration.
  - `sdk-api.md:62,213` only notes that `manaurum-v2.mjs` does not read it.
  - It is not in README "Honest gaps".
- **Platform:**
  - `frontend/public/sdk/manaurum-v2.mjs @285c8a8` contains no occurrence of "offline".
  - `app.offline` and the box stream ops live in the v1 `frontend/public/sdk/manaurum.js:206-267`.
  - `IframeAppHost.tsx:324-337` only forwards the block, plus an `offline_token`.
  - Nothing in `backend/app` reads `manifest["offline"]` for v2 apps; the only hits are in the schema and `integration_catalogue.py`.
- **Verdict:** LIKELY. I found no v2 container path to the box, but I did not search the Edge repo.
- **Impact:** A developer of an on-site shop app (the SDK's own bakery example) declares `offline` and expects it to survive a WAN outage. It does not.
- **Fix (SDK):** one line in "Honest gaps" and at `v2-platform.md:103`: "Edge/offline is not available to hosted v2 apps".

### G-10 MEDIUM: Post-deploy observability: usage counters exist but are undocumented, and README says "No metrics"
- **SDK:**
  - `README.md:211` says *"No metrics. `manaurum app logs` is a tail of the last N lines"*.
  - `skills/manaurum-app/SKILL.md:668` calls logs a stub (already L10).
  - There is no mention of usage data or of runtime-error capture.
- **Platform:**
  - The gateway counts people and opens for **every** v2 app (`backend/app/routes/v2_app_gateway.py:835-845,905-955 @285c8a8`, MAN-3131).
  - The app's author can read them at `GET /api/app-usage/{app_id}` (`backend/app/routes/app_usage.py:58-80`, mounted at `main.py:1113`). This route uses a user session via `get_current_user`, not an `mna_*` token.
  - Runtime-error capture (`POST /__manaurum/runtime-errors`, MAN-3132) is fed only by the injected runtime of Aurum Studio apps (`backend/app/routes/v2_app_runtime_errors.py:1-12`).
  - `services/v2_apps/runtime_errors.py` has only record and sweep functions; no route reads the errors at HEAD.
- **Verdict:** CONFIRMED.
- **Impact:** Developers are told there is nothing, so they miss the usage endpoint. They also cannot know that the errors their users hit are not collected for SDK-built apps.
- **Fix (SDK):**
  - Document `GET /api/app-usage/{app_id}`: author-only, signed-in people only, and anonymous pages are not counted.
  - Say that runtime-error reporting is Studio-only.
  - Recommend structured stdout logging plus `manaurum app logs`.

### G-11 MEDIUM: There is no role or admin signal anywhere, and the SDK never says so
- **SDK:** `v2-platform.md:262` lists the JWT claims (*"ids: `sub`, `tenant_id`, `workspace_id`, `app_id`, `app_version`. No name and no email"*). No page says there is no role claim, and none shows how to build an admin-only feature. `discovery.md:162` only assumes there is "no separate manager role".
- **Platform:**
  - `mint_user_context` payload: sub/tenant_id/app_id/app_version/iss/aud/iat/exp/jti/workspace_id only (`backend/app/services/v2_apps/user_context_jwt.py:117-135 @285c8a8`).
  - `manaurum:init` carries only `user.nickname` (`frontend/src/components/window/IframeAppHost.tsx:308`).
  - The capability registry (`backend/app/services/capabilities/*`) has no user or directory capability. MAN-2485 proposes `os.directory.list_users` as missing.
- **Verdict:** CONFIRMED.
- **Impact:** An app that needs "only the manager can edit prices" has no platform signal to rely on, and nothing tells the developer to build their own.
- **Fix (SDK):**
  - State "no role claim".
  - Show the pattern: an app-side `roles` table keyed by `sub`, with the first user (or an `os.secrets`-held bootstrap code) as admin.
- **Related:** MAN-1289, MAN-2485.

### G-12 LOW: The mobile defaults are misdescribed by the platform schema and missing from the SDK; the setup example omits `platforms`
- **SDK:** `v2-platform.md:94` lists `platforms` keys with no defaults. The setup example (`skills/manaurum-setup/SKILL.md:95-131`) has no `platforms`. The starter does declare it (`templates/v2-starter/manifest.json:26-36`, adaptive/single-view).
- **Platform:**
  - The schema says `supported` defaults to false and `supportLevel` to `"none"` (blocked) (`manifest_v2.schema.json:306`).
  - But the phone resolver gives an undeclared v2 app `'fallback'`, shown with a "best on desktop" banner (`frontend/src/components/mobile/useMobileAppResolver.ts:86-92 @285c8a8`).
  - `backend/app/routes/mobile.py:~110` takes `mobile_supported` *"default true"*.
  - MAN-2323 (gaining mobile in a later version) and MAN-2690 (deep links on the phone) are Done.
- **Verdict:** CONFIRMED.
- **Impact:** Minor. An app built from the setup snippet appears on phones with a desktop banner, not blocked as the schema implies.
- **Fix:**
  - SDK: give the real defaults, and add `platforms` to the setup snippet or point to the starter.
  - Platform: fix the schema defaults text.

### G-13 LOW: `migrate_command`: the SDK is right; the platform schema and guide are wrong (fix belongs to the platform)
- **SDK:**
  - `v2-platform.md:105` and `:617-619` (*"Core has no call site for it"*) are correct.
  - The pointer `production.py:40-43` has drifted; it is now `:49-52` (add to L6).
  - `templates/v2-starter/README.md:151` (*"set `migrate_command` in the manifest"*) is wrong; already L17.
- **Platform:**
  - `backend/app/services/v2_apps/production.py:49-52 @285c8a8` says *"`migrate_command` … reserved … not wired in this slice"*. A grep finds no other call site.
  - The text that contradicts it is published in three places:
    - `manifest_v2.schema.json:251`, both the backend copy and the public `frontend/public/sdk/` copy that the SDK README links: *"invoked by the deploy pipeline once per (app, tenant)"*.
    - `docs/handoff/V2_DEVELOPER_GUIDE.md:248`.
    - `docs/handoff/V2_DEVELOPER_GUIDE.md:729`: *"Core invokes `migrate_command` once per tenant install"*.
- **Verdict:** CONFIRMED.
- **Fix (platform):** correct the schema description and the guide. MAN-1491 (stale V2 guide) covers the guide part. Then fix the SDK pointer and the starter README.

### G-14 Addendum to H33 (cross-tenant installs). Two more facts, not new findings
- **Install runs no migrations.** `POST /app-store/v2/install` only inserts a row with `migration_status: "pending"` (`backend/app/services/app_store_v2.py:319-372`, in-memory twin `:604-605 @285c8a8`). Migrations run only in the next deploy's fan-out, so a tenant that installs after the last deploy has no tables until the developer redeploys. `deploy SKILL.md:356` ("one deploy serves every tenant") and `v2-platform.md:441` do not say this.
- **The agent dispatcher mints the wrong tenant.** It mints `user_context.tenant_id` from `v2_apps.tenant_id`, the app's home tenant, not from the installing workspace's tenant (`backend/app/agent/v2_capability_dispatch.py:57-92,133-140`). An Assistant call from a tenant-B user therefore reaches the home-tenant container with a tenant-A token.

---

## Areas checked where the SDK is correct (no finding)
- **`is_write` semantics.** The omitted → write fallback is described correctly at `v2-platform.md:152`, the starter manifest sets it on both capabilities, and starter test `test_manifest.py:87` enforces it.
- **The 400-character description cap.** Stated correctly at `v2-platform.md:132`, matching `sdk_capability_tools.py:139,169-203` and the schema's maxLength.
- **Input validation and reply shape.** Arguments are validated against `input_schema` at dispatch (`dispatcher.py:129`). The `{ok, output}` / `{ok:false, error}` reply is correct (`v2_capability_dispatch.py:170-179`).
- **`schedules` and `webhooks` do nothing.** The SDK says so correctly (`README.md:209-210`, `v2-platform.md:100-101`), and a grep of `backend/app` finds no consumer.
  - Remaining gap (MEDIUM, ungraded detail): there is only a one-line recipe. Nothing says that an in-container job has no `user_context`, so the `os.drive.*` / `os.calendar.*` calls it makes get 403 `user_context_required` (`capability_gateway.py:760-764`).
  - There is no HMAC or constant-time webhook example. The schema's planned contract is in `manifest_v2.schema.json` webhooks.signature.
  - `replicas` is 1 (`stack_generator.py:410`), so an in-process cron does not double-fire today.
- **`data.extensions`** is already M11.

## Questions (no evidence either way)
1. Is a workspace **guest** (external invitee) minted a `user_context` on `auth:"user"` routes and agent calls? If so, the app sees a guest exactly as it sees a member.
2. Do Edge boxes run any v2 hosted container? I did not search the Edge repo (relates to G-09).
3. Does `CREATE TABLE IF NOT EXISTS` pass the migration validator as additive? It would be the cheap mitigation for G-06; `deploy SKILL.md:343` suggests it, but I did not verify it in `migration_validator`.
4. Does a teardown or delete also remove `agent_capabilities` rows, or do they linger as active for a deleted `v2_app_id`? `_real_teardown_runner` does not list them; the dispatcher would then answer "not deployed/ready".
5. Is `GET /api/app-usage/{app_id}` reachable with an `mna_*` token? It uses `get_current_user`, which looks session-only.

## Summary
- **Covered:** all 10 requested areas: OS-Assistant dispatch (sync, registry, is_write, approval gate, dedup, undo, tool-name limit), migrate_command, schedules/webhooks, uninstall/teardown/data retention, data modes, breaking/rollback/new-tenant replay, platforms/offline, events receiving, roles, observability.
- **Strongest new items:**
  - G-01: events can never be received.
  - G-02: a capability is dropped silently when slug + name exceed 57 characters.
  - G-06: delete keeps the schema but drops the migration ledger.
  - G-07: `breaking` is a whole-bundle switch.
- **Not done:**
  - Nothing was executed: no deploy, no runtime probe.
  - I did not audit `optional_capabilities`, `tenant_config`, `metadata`/App Store listing, the sandbox download/popup paths, the i18n details beyond M7, or the quota/BYOK shape (skeptic #10, #15, #17-19, #22).

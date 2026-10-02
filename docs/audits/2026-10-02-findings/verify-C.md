# verify-C: adversarial check of gaps.md (G-01..G-13, G-14 addendum)

- **Inputs:** SDK `C:\dev\wt\sdk-audit` @6f52dce. Platform: SNAP @285c8a8, plus `git grep/show 285c8a885` for the frontend and CLI.
- **Method:** read-only. Nothing was executed against prod. Linear was searched read-only.
- **Verdicts:**
  - CONFIRM means the code agrees, after trying to refute the finding.
  - REFUTE means the code disagrees.
  - UNCLEAR means the code does not settle it.
  - Line numbers are corrected where gaps.md drifted.

## Summary table

| id | verdict | SDK lines (corrected) | key platform evidence @285c8a8 | severity | existing ticket | note |
|---|---|---|---|---|---|---|
| G-01 | CONFIRM (one correction) | CR:255-256, CR:582, **also v2-platform.md:99** ("every event you subscribe to") | `services/events/dispatcher.py:92-108,132-138`; no writer of `event_subscribers` anywhere (git grep, non-test) | HIGH, agree | **MAN-133** "Add os.events.subscribe capability" (Todo); MAN-3072, MAN-2485 | `consumes` IS read, but only for the install-UI dependency list (`app_store_v2.py:209-232,483`) |
| G-02 | CONFIRM | v2-platform.md:94 ("≤64 chars", misleading), :132; check_app.py has no rule | `agent/sdk_capability_tools.py:80-84`; `agent/types.py:107-108`; `agent/tool_registry.py:419-426`; `app_studio/agent_verbs.py:108-115,195` | HIGH, agree | none for this path; MAN-3172 is the same bug in the MCP generator (different code) | Exact rule: len(slug)+len(name) ≤ 57; at a 40-char slug the name is ≤ 17 |
| G-03 | CONFIRM | manaurum-setup/SKILL.md:116-126; contradicts v2-platform.md:152 | `sdk_capability_tools.py:142-166`; `configs/write_gate.py:158-171`; `runtime.py:2185-2196`; validator refuses only an explicit `false` on write verbs (`manifest_v2_validator.py:212-238`) | MEDIUM, agree | none | Absence is legal at deploy, so the snippet deploys green and every read is gated |
| G-04 | CONFIRM | v2-platform.md:112,152; starter `src/agent_routes.py:10-35` | `agent/v2_capability_dispatch.py:43,143-163`; `agent/dispatcher.py:109-122`; map scoped per `_loop` (`runtime.py:1838`); `undo.py:353-373`; `sdk_capability_tools.py:256` | MEDIUM, agree | none | Dedup is per turn and the key is popped, never forwarded |
| G-05 | CONFIRM | none (no "approv*" guidance in skills/ or templates/ for writes) | `docs/handoff/V2_DEVELOPER_GUIDE.md:1508-1555`; `configs/write_gate.py:120` (`_ARG_KEYS_MAX = 10`) | MEDIUM, agree | MAN-2998 (Done), MAN-2997 (Atlas update, In Progress) | Port the guide paragraph |
| G-06 | CONFIRM (the trap is real, by code trace; not executed) | v2-platform.md:633 only | teardown `production.py:4558-4590,4677-4678,4749-4796`; ledger `production.py:3493-3510` (keyed by app UUID); schema `run_migration_real.py:65-74` (slug+tenant); runner `run_migration_real.py:147-209`; new UUID on re-insert `production.py:2035-2043`; gate `production.py:1090-1102,3823-3846` | MEDIUM, agree (borderline HIGH, see extra twist) | none direct; MAN-3003 related (ledger/schema desync, asks for a re-run "from empty") | Extra twist: the kept schema reattaches to *whoever* next deploys that slug in that tenant |
| G-07 | CONFIRM | v2-platform.md:54-58,106,525; deploy SKILL.md:256-259 | `v2_apps/deploy_pipeline.py:477-520` (every bundle file, current `breaking`); the caller passes all files (`production.py:3654-3657,3728`); the runner validates only new files (`run_migration_real.py:163-183`) | MEDIUM, agree | none (MAN-1491 covers the "consent" wording only; MAN-3003 is adjacent) | Platform comment at :510-518 admits pre-flight "judges history" but exempts only transactionality |
| G-08 | CONFIRM | manaurum-app/SKILL.md:213; v2-platform.md:91 | `production.py:784-803`; only other `data` reader is `:820` (extensions); `db_broker.py:117-118`; "isolation warning" only in schema text `manifest_v2.schema.json:225` (backend + `frontend/public/sdk`) | rubric says HIGH (wrong fact), practical impact MEDIUM | none | Studio's per-table `shared` (`app_studio/data_model.py`) is unrelated |
| G-09 | CONFIRM (upgraded from LIKELY) | v2-platform.md:103; sdk-api.md:62,211-213 (even suggests reading `offline` by hand) | box config is derived from **v1 tables only**: `services/offline_sync/config_delivery.py:52-66` (`applications`, `application_versions`, `workspace_app_installs`); `entity_resolver.py:48-49,120-121` likewise; `manaurum-v2.mjs` has 0 "offline" | MEDIUM, agree | none found | No v2 path to the box exists in the monorepo |
| G-10 | CONFIRM (two corrections) | README.md:211; SKILL.md:668 | `routes/app_usage.py:58-80` (author **or tenant admin in a team workspace**, `get_current_user`); `main.py:1113`; gateway counting `v2_app_gateway.py:836-846`; `routes/v2_app_runtime_errors.py:1-12`; `services/v2_apps/runtime_errors.py` has only record/scrub/sweep | MEDIUM, agree | MAN-3131/3132 (origin) | No frontend consumer of `/api/app-usage` found at HEAD |
| G-11 | CONFIRM | v2-platform.md:262; discovery.md:162 | `services/v2_apps/user_context_jwt.py:119-136`; `IframeAppHost.tsx:308`; capability list has no user/role/directory op | MEDIUM, agree | MAN-1289, MAN-2485; MAN-3047 (workspace roles for v2 marketplace, Todo) | none |
| G-12 | CONFIRM | v2-platform.md:94; setup SKILL.md:95-131 | schema `manifest_v2.schema.json:303-306` (default `none`); `frontend/src/components/mobile/useMobileAppResolver.ts:~92` (`declared ?? 'fallback'`); `routes/mobile.py:187` (`get("mobile_supported", True)`) | LOW, agree | none | none |
| G-13 | CONFIRM | v2-platform.md:105 cites `production.py:40-43`, now **:49-52**; :617-619 correct; starter README.md:151 wrong (L17) | `production.py:49-52`; schema `:251` (both copies); guide `:248`, `:729` | LOW, agree | MAN-1491 (guide) | The platform contradicts itself: `frontend/src/app/developers/page.tsx:603,630` already says "reserved and not wired" |
| G-14a (install runs no migrations) | CONFIRM | deploy SKILL.md:356; v2-platform.md:441 | `app_store_v2.py:605` (`migration_status: "pending"`); install routes trigger nothing (`routes/app_store_v2.py:254-318`); fan-out lists installs only at deploy (`deploy_pipeline.py:~695`) | addendum | none | none |
| G-14b (agent dispatch mints home tenant) | CONFIRM, **already ticketed** | none (the SDK does not cover it) | `agent/v2_capability_dispatch.py:57-92,133-140` (no reachability check); the gateway does check and 404s a cross-tenant user (`v2_app_gateway.py:892-903`, `gateway_production.py:424-478`) | SEC, platform-only | **MAN-2722** [SEC-REVIEW] (Todo, High) | Not new; cite MAN-2722 |

---

## Detail per item (only where I add to or correct gaps.md)

### G-01: CONFIRM, with one correction
- **Correction.** "No code reads `consumes`" is wrong as worded.
  - `app_store_v2.py:209-232` (`_consumed_app_slugs`) reads `consumes.rpc` and `consumes.events[].app_id`.
  - It is used at `:483` only to build the install page's "depends on" list ("no auto-install").
  - Nothing turns a `consumes.events` entry into a subscription.
- **Writers.** `git grep subscriber_app_id|EventSubscriber|event_subscribers` at 285c8a885 (non-test) finds one hit in code: the SELECT at `dispatcher.py:96-99`.
  - The rest are the data_map, the isolation tool, and baseline DDL/grants.
  - No route, capability or alembic seed inserts into the table.
- **The rest holds.** `routes/events.py` is the shell's SSE stream, not app events. The capability list has no `os.events.subscribe`; MAN-133 (Todo) asks for exactly that.
- **Extra SDK spot.** `v2-platform.md:99` tells authors to *"declare … every event you subscribe to"*, which implies the subscription exists.

### G-02: CONFIRM. The limit, precisely
- **How the name is built.**
  - `_tool_name_for` = `"sdk__" + safe(slug) + "__" + safe(name)`.
  - `safe()` maps each non-alnum character to `_` one-for-one, and `lower()` keeps the length.
  - So len = 5 + len(slug) + 2 + len(name).
  - `Tool.__post_init__` raises when the result is > 64.
  - **Rule: len(slug) + len(name) ≤ 57.**
- **Slug range.** `_VALID_SLUG_RE` gives 3–40 characters, so the name may be anywhere from 54 down to **17** characters.
  - gaps.md's arithmetic is right: 27 + 32 = 59, which gives a 66-character tool name.
- **Refutation attempts that failed:**
  1. `manifest_v2_validator.validate_manifest_v2` has no length or sum check. It runs the schema plus is_write-verb, reserved-slug and byo checks.
  2. The schema `app_id` has no maxLength or pattern. The 40 cap comes from traefik/registry.
  3. `agent_capability_sync.py` upserts rows without building a `Tool`.
  4. `build_capability_tool` is called only from `tool_registry.py:421`, inside a try/except that logs `sdk_capability_tool_build_failed`.
  5. The CLI validator has no rule.
- **Strongest evidence.** The platform knows about this. `app_studio/agent_verbs.py:108-115` says, in a comment, that an over-long name *"does not fail anything — the capability just silently vanishes from the Assistant"*. `:195` computes `64 - 7 - len(slug)`. That guard covers Aurum Studio drafts only, not SDK/CLI deploys.
- **Related ticket.** MAN-3172 (In Progress) caps names from the **MCP generator** (`slug__entity__op`). That is a different code path, so it is not a duplicate.
- **Also fix:** `v2-platform.md:94`'s "≤64 chars" next to `name`.

### G-03: CONFIRM
- **The approval gate.** `write_gate.requires_approval` returns True for any backend tool with `is_write`. `runtime.py:2185-2196` applies it on the OS-Assistant loop.
- **The validator.** It refuses only an explicit `false` on write-verb names. Omission is "legal by design" (`manifest_v2_validator.py:180-184`), so the setup snippet deploys green.

### G-04: CONFIRM
- **Timeout.** `httpx.AsyncClient(timeout=30.0)`, and a timeout raises *"timed out handling"*. Nothing cancels the container-side work.
- **Dedup scope.** `idempotency_map` is created per `_loop` invocation (`runtime.py:1838`). Two other call sites pass `{}` (`:1248`, `:1450`).
- **Inverse handlers.** `UNDO_HANDLERS` lists only Core kinds (file_*, folder_create, reception_draft_create, shift_create, menu_price_update, tm_task_create).
- **Guide wording.** The guide's "approval + undo + dedup" is at `V2_DEVELOPER_GUIDE.md:1494`.

### G-06: CONFIRM, including the trap
- **Trace:**
  1. Teardown deletes `v2_app_migrations WHERE app_id = :aid` (the UUID) and the `v2_apps` row (`production.py:4774,4795`).
  2. Redeploy is `INSERT INTO v2_apps … ON CONFLICT (tenant_id, app_slug)`. The row was deleted, so a **new UUID** is minted (`:2035`).
  3. The 30-day reservation does not block the owners (`:1579-1607`).
  4. The runner calls `lookup_applied(tenant, new_uuid)`, which returns [], so every file is "new".
  5. Each file is validated, then executed into `schema_name_for(slug, tenant)`, which is the **kept** schema (`run_migration_real.py:148-209`).
  6. A plain `CREATE TABLE` raises "relation already exists". The runner returns `failed`, and the MAN-2510 gate (default ON, `MANAURUM_V2_MIGRATION_GATE`) blocks the deploy before swarm (`production.py:3838-3846`).
- **Mitigation (answers gaps.md Q3).**
  - `migration_validator.py:520-521` classifies every `CreateStmt` as additive, so `CREATE TABLE IF NOT EXISTS` passes.
  - A fully idempotent migration set therefore re-runs cleanly and silently reattaches the old data.
  - Anything non-idempotent fails the redeploy: `ALTER TABLE … ADD COLUMN` without `IF NOT EXISTS`, `CREATE INDEX` without `IF NOT EXISTS`, or seed `INSERT`s (which would also duplicate rows).
- **Extra twist, worth stating.**
  - The kept schema is keyed by slug + tenant, not by owner.
  - After the 30-day reservation lapses, or immediately for a co-owner, the next developer in that tenant who deploys that slug inherits the previous app's tables and rows.
  - Files under `app/<slug>/<tenant>/…` are inherited the same way. The starter keys `os.files` by slug (`templates/v2-starter/src/capability.py:24-40`), and teardown deletes only `v2-app-source/…` (`production.py:4678`).
- **Smaller facts:**
  - `app_kv` is deleted by UUID. It would be orphaned anyway, because the UUID changes.
  - Other tenants' schemas `app_<slug>__<theirhex>` are kept too.
  - `agent_capabilities` rows are not deleted. They become unreachable via the install join (relates to gaps.md Q4).
- **Side note, out of scope here.**
  - `manaurum-deploy/SKILL.md:252-254` says that after editing an applied file *"the new version still activates"*.
  - With the MAN-2510 gate default ON, the deploy is blocked instead.
  - If CONSOLIDATED's H4 does not already cover this sentence, it should.

### G-07: CONFIRM
- **Pre-flight scope.** Pre-flight loops `for filename, file_sql in migration_files` with `breaking_allowed=breaking`. Production passes the full extracted bundle.
- **Effect.**
  - A historical `DROP` file plus `breaking:false` raises `MigrationValidationError` before `push_image`, and the deploy is refused.
  - The per-tenant runner would have skipped that file as already applied, so the refusal comes only from pre-flight.
- **Platform comment.** The code at `deploy_pipeline.py:510-518` already reasons that pre-flight "judges history" and "would be refused for ever". It applies that exemption only to `enforce_transactionality`, not to `breaking`.
- **Inert fields.** `reason` / `rollback_strategy`: a grep for readers finds none. The schema says *"recorded and read by nothing today"*.

### G-09: upgrade to CONFIRM
- **Where the box config comes from.** The Edge box's offline config is built by `offline_sync/config_delivery.py:_DERIVE_CONFIG_SQL`. It joins `workspace_app_installs → applications → application_versions`, which are v1 tables.
- **What is missing.** No code in `services/offline_sync/` references `v2_apps`, `v2_app_versions` or `v2_workspace_installs`.
- **The shell side.** `IframeAppHost.tsx:324-337` passes the block through, but `manaurum-v2.mjs` does not read it.
- **Result.** A v2 app's `offline` block can never reach a box.
- **Still unchecked.** The Edge repo itself, which gaps.md Q2 also left open.

### G-10: CONFIRM, two corrections
- **Who can read usage.** The route allows the author **and tenant admins in a team workspace** (`app_usage.py:66`, `usage_access`), not only the author.
- **No UI.** I found no frontend caller of `/api/app-usage` at HEAD, so today the counters are API-only. `UsageTab.tsx` reads a different endpoint.
- **Runtime-error route.** The route answers on any v2 app's subdomain. Only the Studio runtime posts to it, and nothing reads the stored rows back.

### G-13: CONFIRM
- **The platform disagrees with itself.**
  - `frontend/src/app/developers/page.tsx:603,630` (the public developers page) says `migrate_command` is "reserved and not wired".
  - The schema (`:251`, both copies) and `V2_DEVELOPER_GUIDE.md:248,729` say it runs.
- **Where the fix goes.** On the platform, under MAN-1491 for the guide part.
- **SDK pointer.** Update `production.py:40-43` to `:49-52`.

### G-14: both facts CONFIRM
- **(a) Install.** `insert_install` writes `pending` and nothing triggers a run. The fan-out takes `list_installs_for_app` only inside `run_deploy`.
- **(b) Agent dispatch.**
  - It mints `tenant_id = v2_apps.tenant_id` and calls the home-tenant service, with no `user_can_reach_workspace_in_tenant` check.
  - The gateway runs that check and 404s a cross-tenant caller, so the agent path is a second door without the guard.
  - **Already filed as MAN-2722** ([SEC-REVIEW], Todo, High). Reference it and do not re-file.

---

## Linear searches run (read-only)
- **Queries:**
  - event_subscribers, consumes.events, subscribe, os.events.subscribe
  - Tool.name too long, tool name 64, tool name
  - teardown, delete app, purge, reattach, managed schema
  - v2_app_migrations ledger, migration.breaking, breaking, already applied, rollback_strategy
  - data.shared, shared, connection_cap, connection cap, isolation warning
  - cross-tenant install, agent dispatch tenant
- **Relevant hits:**
  - MAN-133: G-01.
  - MAN-3072 and MAN-2485: G-01 context.
  - MAN-3172: G-02, adjacent (MCP path).
  - MAN-3003: G-06/G-07, adjacent.
  - MAN-1491: G-13, and the G-07 wording.
  - MAN-2722: G-14b, a duplicate.
  - MAN-2997/2998: G-05.
  - MAN-3047: G-11, adjacent.
- **No existing ticket found for:** G-02 (SDK deploy path), G-06 (ledger/schema desync on delete and redeploy), G-07 (whole-bundle `breaking`), G-08.

## Bottom line
- **Verdicts.** Nothing was refuted. 13 of 13 findings and both addendum facts are CONFIRMED by code.
- **Corrections to gaps.md:**
  - G-01: `consumes` is read, but for the UI dependency list only.
  - G-09: upgraded to CONFIRMED (the offline sync is v1-only).
  - G-10: usage is also readable by tenant admins, and no UI reads it.
  - G-13: line pointer.
  - G-14b: already MAN-2722.
- **New sharpening:**
  - G-02: the exact budget is slug + name ≤ 57, and the platform already guards it for Studio only.
  - G-06: the kept schema and files are inherited by any later deployer of the slug in that tenant. Idempotent migrations hide the trap instead of failing.

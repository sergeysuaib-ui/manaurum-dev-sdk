# Dimension: manifest-deploy (MANIFEST, DATA/MIGRATIONS, DEPLOY, UPDATE, ROLLBACK)

SDK root = `C:\dev\wt\sdk-audit` @ 6f52dce (3.1.0). Platform = SNAP @285c8a8.
`backend/app/services/_schemas/manifest_v2.schema.json` and `frontend/public/sdk/manifest_v2.schema.json`
are **byte-identical** (`cmp`), and so is `manaurum-cli-py/manaurum_cli/schemas/manifest_v2.schema.json`.

Abbreviations: DS = `skills/manaurum-deploy/SKILL.md`, AS = `skills/manaurum-app/SKILL.md`,
V2 = `skills/manaurum-app/references/v2-platform.md`, PUB = `skills/manaurum-app/references/publishing.md`,
SS = `skills/manaurum-setup/SKILL.md`, CA = `templates/check_app.py`.

---

## 1. Schema property matrix

Root: `additionalProperties:false`, required = manifest_version, manaurum_sdk_version, app_id, name, version, runtime.
SDK lists the 23 root keys correctly (PUB:50-53, V2:22,87). CA has **no root-key check** (only `RUNTIME_KEYS`, CA:82-84), although its docstring says "The root object and `runtime` are both strict" (CA:367).

| Property (type / constraints) | SDK description | Correct? | check_app.py |
|---|---|---|---|
| manifest_version const "2" | V2:78 | yes | no |
| manaurum_sdk_version const "2" | V2:79 | yes | no |
| app_id string minLength 1 + **server rules**: `^[a-z][a-z0-9-]{1,38}[a-z0-9]$`, not UUID-shaped (422 `app_id_invalid`, owner_deploy.py:92-104), not one of 14 reserved slugs (manifest_v2_validator.py:263-267, reserved_slugs.py:38-55) | AS:213 regex right; V2:80 and SS:144-145 "schema only enforces minLength … keep it … in practice"; reserved slugs nowhere | partly stale (F-11) | no |
| name string minLength 1 | V2:81 | yes | no |
| version `^\d+\.\d+\.\d+$` + immutable once pushed (409 `version_already_published`) | AS:214 "Each redeploy must be a NEW version"; V2:445 says same-version redeploy works | V2:445 wrong (F-06) | no |
| runtime (object, additionalProperties:false, required mode) | V2:203 strict; **V2:24 "not strict"** | contradiction (F-01) | yes - `RUNTIME_KEYS` hardcoded, 11 keys, matches schema today; no drift test |
| runtime.mode enum hosted/byo/dev | V2:190-194, AS:215 | yes | via RUNTIME_KEYS only |
| runtime.health_path `^/` | V2:208,229 (probe, strict on 5xx, rollback) | yes, but contradicted by "no readiness probe" x5 (F-02) | key only |
| runtime.resources {memory_mb 64-2048, cpu_millicores 50-2000}, addlProps false | V2:233 | yes | key only |
| runtime.api_routes[] {path `^/` req, auth enum user/anonymous req, streaming bool}, addlProps false | V2:235-245, AS:226-251, SS:152-162 | yes | yes (route coverage) |
| runtime.public_paths[] `^/` | V2:221-225 | yes | key only |
| runtime.sandbox[] enum allow-scripts/allow-forms/allow-same-origin | V2:215 | yes | key only |
| runtime.entrypoint uri `^https://`; **forbidden (`false`) when mode is hosted/dev**, schema allOf[0] | V2:308 "any `entrypoint` you write is ignored" for hosted | wrong (F-12) | key only |
| runtime.port int 1-65535, default 80 | V2:217-219, AS:216 | yes | yes (CMD/EXPOSE) |
| runtime.egress_allowed_hosts string[] | V2:320-326 | V2:326 stale (F-13) | key only |
| runtime.replicas int >=1 (ignored), runtime.image (ignored) | V2:213 | yes | key only |
| data {none, byo, shared bool; connection_cap 1-100; **extensions** uniqueItems enum vector/pg_trgm}, addlProps false | V2:91, AS:220, SS:163-168 | `extensions` absent everywhere (F-09) | no |
| migrate_command string[] (never executed) | V2:105,617-619 | yes | no |
| migration {breaking, reason, rollback_strategy} | V2:106, DS:256-260 | yes | `breaking` read (CA:588) |
| visibility {mode enum private/public/allow_list, tenants[]} | V2:93,623-633; DS:348-356 | mostly; home-install fan-out missing (F-16) | no |
| platforms.desktop.supported; platforms.mobile {supported, optimized, entrypoint `^https://`, supportLevel enum full/adaptive/fallback/none, navigationPattern enum stack/tabs/list-detail/single-view/composer-first} | V2:94 lists keys, no enums/defaults | gap (LOW) | no |
| permissions[] uniqueItems enum **microphone, camera**; maxItems 0 when byo | AS:219, V2:104, PUB:64, SS:175-176 say `["microphone"]`; AS:733 says mic+camera | stale x4 (F-05) | no |
| frontend {entry_point, bundle_path, icon, window{default_width>=320, default_height>=240}} | V2:92, AS:222-223 | yes (minimums not stated) | entry_point exists, icon not relative |
| requires_capabilities[] {name, version req, quota_per_tenant_per_day obj} | V2:95 | yes | yes |
| optional_capabilities[] same shape | V2:96 "App Store v2 reads this to compute the optional grant set the tenant admin sees" vs schema:382 "consent sheet lists only requires_capabilities" | contradicts schema text (Q-3) | **ignored** -> false positive (F-15) |
| agent_capabilities[] {name `^[a-z][a-z0-9_]*$` <=64, description 1-400, input_schema obj, is_write, routing_hints, example}, addlProps false; + server rule: write-verb name with `is_write:false` = 422 (MAN-2358) | V2:111-152 | yes except MAN-2358 rule absent (F-11) | /agent handler auth only |
| provides/consumes {rpc[], events[]} | V2:98-99 | yes | no |
| webhooks[] {name pattern, path `^/`, signature{method enum hmac-sha256, header, secret_ref}} deferred | V2:100 | shape partly; LOW | no |
| schedules[] {name, cron minLength 9, timezone, handler_path, timeout_seconds 1-3600} deferred | V2:101 (no timeout_seconds) | LOW | no |
| tenant_config {schema, required_at_install} | V2:102 | yes | no |
| metadata {category, tags, description, homepage, support_email, source_url} | V2:107 | yes | description != TODO |
| offline {features[], reference_data[], streams[{name, type ledger/state, key, entity_type, conflict_policy grey_out/optimistic_reconcile}]}, addlProps false | V2:103 (name, type only) | LOW gap | no |

`RUNTIME_KEYS` is hardcoded (CA:82-84) and correct at 285c8a8, but nothing in `scripts/` or CI compares it with the schema (grep for `RUNTIME_KEYS`/`schema.json` in scripts/.github: no hits) - the same drift that produced the 3.1.0 fix can recur silently.

---

## 2. Migration rules: validator vs SDK vs check_app.py

Platform: `backend/app/services/migration_validator.py` @285c8a8 (CLI copy `manaurum_cli/migrations.py` identical rules, minus the size cap - on purpose, `tests/test_migration_validator_parity.py:139-153`).

| Rule (platform) | SDK text (V2 §7, DS:256-260, AS:559) | CA with CLI importable | CA fallback (no CLI - the common case) |
|---|---|---|---|
| forbidden: COPY, DO, CREATE/ALTER/DROP ROLE, GRANT/REVOKE ROLE, CREATE/DROP/ALTER DATABASE, ALTER SYSTEM, SET, CREATE EXTENSION, BEGIN/COMMIT/SAVEPOINT (validator:49-69) | V2:514 complete | yes | only `DO $$` (CA:89,639) - **all others missed** |
| CREATE FUNCTION only LANGUAGE sql/plpgsql (validator:558-569) | V2:503,514 | yes | missed |
| default-deny for any unrecognised node (validator:595-599) e.g. ALTER SEQUENCE, REFRESH MATERIALIZED VIEW, ALTER DEFAULT PRIVILEGES, CREATE RULE, REINDEX, VACUUM | V2:516 | yes | missed |
| destructive: any DROP (TABLE/INDEX/VIEW/FUNCTION/POLICY/TRIGGER/...), RENAME, TRUNCATE, REVOKE, DROP COLUMN, ALTER COLUMN TYPE, DROP CONSTRAINT (validator:571-578, 674-690) | V2:512 | yes | only DROP TABLE/SCHEMA/DATABASE/TYPE/SEQUENCE, DROP COLUMN, TRUNCATE, ALTER COLUMN TYPE, DROP CONSTRAINT (CA:90-96) - **DROP INDEX/VIEW/FUNCTION/POLICY/TRIGGER, RENAME, REVOKE missed** |
| plain CREATE INDEX on non-fresh table / SET NOT NULL on non-fresh column = destructive (validator:530-541, 695-705) | V2:505-508 | yes | unchecked, and the note says so (CA:557-562) |
| CONCURRENTLY file must contain nothing else, `mixed_transaction` / `unanalysable` (validator:288-321) | V2:527-554 | yes if CLI new enough (probe CA:505-554) | unchecked, note says so |
| **64 KB cap** (`MAX_MIGRATION_BYTES`, validator:113) - enforced in the deploy on the **concatenation of all files** (deploy_pipeline.py:496-502) and per file in the runner | nowhere in SDK | **no** (CLI has no size cap) | no |
| `migrations/` direct child must end with `.sql`, case-sensitive (bundle_migrations.py:164) | DS:342, V2:485 correct | CA uses `path.suffix.lower()` (CA:601) -> `0001.SQL` passes CA, fails deploy | same |
| files must be UTF-8 (bundle_migrations.py: `migrations/<f>: not valid UTF-8`) | nowhere | no | no |
| subdirectories ignored | DS:342, V2:486 | CA reports a directory as a problem (CA:597-599) - harmless false positive | same |
| per-statement `statement_timeout` 30 s, `lock_timeout` 5 s (app_db_role.py:56,63; production.py:3352-3358) | nowhere | n/a | n/a |
| breaking only lifts destructive, never forbidden/mixing | V2:500-501,525,533; DS:256-259 | yes | CA says forbidden `DROP DATABASE` needs `migration.breaking` (misleading, LOW) |

The fallback note (CA:557-562) names only the context-sensitive and CONCURRENTLY rules as "UNCHECKED", which implies everything else was checked. Demonstrated in a scratch dir (since deleted) with no `manaurum_cli` importable: a manifest with `app_id:"api"`, a bogus root key, `record_sale` + `is_write:false`, `permissions:["camera"]`, `optional_capabilities:[os.kv.get]`, and `0001_init.sql` containing CREATE EXTENSION, COPY ... PROGRAM, SET, DROP INDEX, RENAME, REVOKE, BEGIN, ALTER SEQUENCE plus a `0002_a.SQL` gave **"1 problem(s)"**: the false positive on `os.kv.get` from optional_capabilities. All the rest - each of them a 422 or job failure on the platform - went unreported.

---

## 3. Deploy rejections: platform vs SDK

`POST /api/dev/v2/deploy` @285c8a8 order (routes/dev_v2_deploy.py:776-1010):

| # | HTTP | detail | Source | In SDK? |
|---|---|---|---|---|
| 1 | 401 | `invalid_credential` (for missing header too - `resolve_mna_or_401` defaults, auth/v2_developer_auth.py:402-403) | | yes; DS:329 also lists `missing_authorization`, never returned by dev routes (LOW) |
| 2 | 403 | `runtime_credential_not_allowed` (MAN-2242, v2_developer_auth.py:463-465) | | no |
| 3 | 422 | `{"error":"manifest_validation_failed","errors":[...]}` - full schema + MAN-2358 + MAN-2500 + byo ban (owner_deploy.py:86-91) | dev_v2_deploy.py:815 | **SDK says manifest is validated only in the job** (F-03) |
| 4 | 422 | `{"error":"app_id_invalid","requested_app_id","hint"}` - slug regex 3-40 / UUID-shaped (owner_deploy.py:92-104) | | no |
| 5 | 403 | `{"error":"app_id_out_of_scope","requested_app_id","token_scope","hint"}` (object, not string; v2_developer_auth.py:543-575) | | yes, but as string + wrong fix (F-08) |
| 6 | 413 | `archive_too_large` (> 88 MiB base64 chars, config.py:536-537) | dev_v2_deploy.py:831-834 | no |
| 7 | 422 | `invalid_archive_b64` | | yes |
| 8 | 409 | `slug_owned_by_another_tenant`, `version_already_published` (production.py:4187,4203) | claim_owner_deploy, owner_deploy.py:135-142 | no |
| 9 | 409 / 403 | `slug_reserved` (409), `app_id_out_of_scope` (403, lost race) (owner_deploy.py:143-151) | | no |
| 10 | 202 | `{deploy_job_id, status:"pending"}` | | yes |

Job failures (after 202), not in SDK: `version_already_published` from the registry check (production.py:574-599: "A version that was pushed by a deploy that later failed ... counts as published"); archive limits from `decompress_bounded` (always on, via bundle_migrations: gzip/plain tar only, 64 MB expanded, 20 000 entries - archive_limits.py:32,83-93; bundle_migrations.py `_MAX_ENTRIES`); migration aggregate 64 KB; `readiness_failed` + rollback with `result.log_kind/log_tail` (production.py:3962-4007; dev_v2_deploy.py:419-436); `MigrationGateBlocked` "not activated: the migration failed for N tenant(s)" (production.py:3839-3904). Build-context scanner rules (symlinks, ONBUILD, remote ADD, base-image allow-list, credential markers, 32 MB/file, Dockerfile 512 KB - build_context_scanner.py:93-118, 1040-1116) run only when `v2_build_scan_mode` is audit/enforce; default `off` (config.py:503-508), and nothing in the repo sets it -> Q-1.

Rollback `POST /apps/{id}/rollback`: sync `409 deploy_in_progress` (dev_v2_deploy.py:1136-1141); job errors `app_not_found`, `slug_released`, `version_not_found`, `already_current`, `image_unavailable` (production.py:4337-4420). The SDK documents none of them.

---

## 4. Findings

### F-01 - HIGH - "runtime is not strict" survives in V2:24, contradicting V2:203 and V2:310 (the MAN-1899 lesson, sixth copy)
- SDK: V2:24 "The `runtime` and `metadata` **sub**-objects are *not* strict. Unknown keys there validate silently ... `runtime.byo_endpoint_url` passes validation". The same file says the opposite at V2:203 and V2:310. CHANGELOG 3.1.0 claims "Five places here still said it was not strict" were fixed. This one was missed.
- Platform: schema:96 runtime `"additionalProperties": false`.
- Verdict: CONFIRMED. Impact: an agent that reads §1 first believes a runtime typo is harmless. Fix (SDK): rewrite V2:24 to say runtime is strict (metadata/frontend/visibility/platforms are not). Add a `check_repo.py` assertion that bans the phrase "not strict" near "runtime".

### F-02 - HIGH - "No readiness probe" is stated in 5 places. The platform has one (MAN-1369) and the SDK documents it in V2:208/229
- SDK: DS:193 "There is **no readiness probe anywhere in the hosted deploy path.**"; DS:196-197; DS:464-465 (deploy.sh comment); AS:654 "There is no readiness probe on the hosted path"; PUB:42-43 "There is no readiness probe in the hosted path".
- Platform: production.py:1008-1034 (MAN-1369 header quotes the skill's old sentence), :3962-4008 probe -> on failure `rollback_swarm_service` + `DeployStepError(log_kind="container")`. The default is ON (`MANAURUM_V2_READINESS_PROBE`, :1050-1060), with a 90 s window (:1037). Activation happens only after the probe (:4021).
- Verdict: CONFIRMED (code). Prod kill-switch state is UNVERIFIABLE-WITHOUT-PROD. Impact: developers are taught that `succeeded` means nothing and that a crash-loop deploys green. In fact the job fails with the container log, and the previous version keeps serving. Fix (SDK): in all 5 places, say that `succeeded` means the new task answered HTTP on `runtime.port` (strict 5xx check if `health_path` is declared). On failure the job is `failed` with `result.log_tail` and the old version is restored. Keep the own-/healthz check only as advice for the DB-dependent case: the probe never touches the DB (production.py:3826-3829).

### F-03 - HIGH - "Manifest is validated only inside the job; no synchronous 422" is wrong since MAN-2597 (2026-09-19)
- SDK: DS:178-189 "Only three things fail synchronously ... **Manifest schema ... validated inside the job**"; DS:344 (manifest error listed as a job failure); AS:635 "the manifest has not even been validated yet"; V2:430 "a manifest ... rejection does **not** come back as a synchronous 422"; PUB:15,23-25 "Do **not** expect a `422` from `/deploy` for a bad manifest".
- Platform: dev_v2_deploy.py:808-818 -> owner_deploy.py:86-104: `validate_manifest_v2` then the slug shape, answered as `422 {"error":"manifest_validation_failed","errors":[...]}` / `422 {"error":"app_id_invalid",...}` before anything is claimed. Further sync refusals: 413, 409 x3 (table §3).
- Verdict: CONFIRMED. Impact: scripts and agents poll for a job that was never created, or treat a 4xx JSON body as unexpected. Fix (SDK): replace the "three things" list in DS, AS, V2 and PUB with the table in §3. The deploy.sh (`JOB_ID` empty -> prints body) already copes.

### F-04 - HIGH - "A per-tenant migration failure does not fail the job; the version still activates" is the opposite of MAN-2510 (2026-09-09)
- SDK: DS:199-200 "a **per-tenant migration failure does not fail the job** ... the version still activates"; DS:251-253 "marks that tenant's migration run `failed`, and the new version still activates"; V2:441 "Per-tenant failures isolate to that tenant; other tenants continue"; V2:488 "It does not currently fail the *deploy* (the new version still activates)". V2:554 already says the opposite ("blocks the whole deploy for every tenant") - an internal contradiction.
- Platform: production.py:3823-3904 `MigrationGateBlocked`: "not activated: the migration failed for N tenant(s) ... the running version is unchanged and no container was replaced". The gate is on by default (:1090-1102).
- Also wrong in V2 §5 ordering (V2:432-441): migrations are listed as step 8 after Swarm/Traefik. In fact they run inside `run_deploy` (deploy_pipeline.py:693-711) **before** Swarm, while the old code still serves. Tenants where they succeeded keep the new schema even when the gate blocks.
- Verdict: CONFIRMED. Impact: developers misread the failure mode. They will not know that a failed migration burns the version label (F-06), that one bad tenant blocks every tenant, or that the old code must tolerate the new schema. Fix (SDK): rewrite DS:199-200, DS:250-254, V2:441, V2:488. State the remedy the platform prints: fix forward with a new file if any tenant applied it, else fix the file, and deploy a **new version**.

### F-05 - HIGH - `permissions` enum is given as `["microphone"]` in 4 places. The schema allows `camera` since MAN-1920 (2026-09-02)
- SDK: AS:219 "Enum today: `["microphone"]`"; V2:104 "Enum today: `["microphone"]` (MAN-1316)"; PUB:64 "the enum is `["microphone"]` today"; SS:175-176. AS:733 in the same skill says the frame delegates "`microphone` and `camera`".
- Platform: schema:323-327 enum `["microphone","camera"]`. The CLI 0.3.0 release was cut for camera (MAN-2301).
- Verdict: CONFIRMED. Impact: an agent building a scanner/photo app concludes the camera cannot work inside the shell. Fix (SDK): one sentence in all 4 places - enum microphone|camera, refused for `mode: byo`.

### F-06 - HIGH - Version labels are immutable and burned by failed deploys. V2:445 teaches the opposite
- SDK: V2:445 "Redeploying the same `(app_id, version)` is **not** a DB no-op ... every redeploy of `1.0.0` adds another version row. It is effectively idempotent for the *running service* ... useful for dev iteration". Nowhere does the SDK say that a failed deploy consumes the version.
- Platform: preflight `409 version_already_published` (production.py:4159-4204, MAN-1586). The registry check at build time says "A version that was pushed by a deploy that later failed ... counts as published" (production.py:574-599). The image is pushed before migrations/readiness (deploy_pipeline.py:603-645), so a migration-gate or readiness failure burns the label.
- Verdict: CONFIRMED. Impact: the "retry the same version after fixing" loop is answered with 409. Fix (SDK): delete V2:445. Add to DS "Bump version": every attempt that got past the build needs a new version, failed or not, and `409 version_already_published` means bump.

### F-07 - HIGH - Token issuance doc (V2 §4) describes the pre-MAN-1585/2597 API: wildcard default, cap 5, no `scope_kind`
- SDK: V2:387 "blank for `*`"; V2:395-398 `-d '{"apps": ["*"]}'`; V2:401 "Cap: 5 active per (user, tenant)", and the response shape lacks `scope_kind`; V2:421 "`["*"]` (default) -> any app owned by the developer".
- Platform: routes/developer/v2_credentials.py:233-311. `apps` absent/empty -> `400 apps_required`; `"*"` -> `400 apps_wildcard_not_allowed`; non-slug -> `400 apps_invalid_app_id`; an apps token may list only apps the caller already owns (`403 apps_not_owned`, :319-357, whose message is "To deploy an application that does not exist yet, issue a token for all your applications instead"). `scope_kind:"owner"` takes no apps, default 90 days (:99-104, :359-382); apps tokens default 365 days (:98). Cap 20, env-overridable (:74). `expected_tenant_id` -> `409 tenant_changed` (:458-472).
- Verdict: CONFIRMED. Impact: the curl in V2 always fails with 400. An agent following V2 cannot mint a token that can create a new app. Fix (SDK): rewrite §4 around `scope_kind: "owner"` (needed for a first deploy) vs `"apps"` (existing owned apps only), the 400/403/409 codes, the cap of 20, and the defaults. Remove V2:421-422. Related MAN-3199.

### F-08 - HIGH - `403 app_id_out_of_scope` fix advice is impossible, and the ownership rule (MAN-1876/2597/2620) is not taught
- SDK: DS:330 "The credential's `apps` list doesn't cover the manifest's `app_id`. | Use a credential scoped to this app (or `*`)." V2:361 "Wildcard `*` is honored."
- Platform: the deploy runs under the owner rule for every token (dev_v2_deploy.py:785-805; `owner_scoped=True` at :948). Only the first deployer is recorded in `v2_app_owners` (production.py:2093). An apps-token listing someone else's app still gets 403 (MAN-2620). The detail is an object with `hint` and `token_scope` (v2_developer_auth.py:543-575). No route adds co-owners (grep `INSERT INTO v2_app_owners`: only production.py:2093).
- Verdict: CONFIRMED. Impact: a second developer on a team tenant cannot redeploy a colleague's app and is told to fix the token, which cannot help. Fix (SDK): replace the row. 403 means you do not own this app in this workspace, or it is not yours to create, so read `detail.hint`; `*` does not exist. Mention that the first deployer becomes the owner. Platform: Q-2.

### F-09 - MEDIUM - `data.extensions` (MAN-1960 curated pgvector/pg_trgm) is absent from the SDK, which says extensions are impossible
- SDK: V2:520 "**No `CREATE EXTENSION`** — you cannot install `pgcrypto` or `uuid-ossp`"; V2:91, AS:220, SS:163-168 list the data keys without `extensions`.
- Platform: schema:233-243. production.py:809-884: requested ∩ allow-list ∩ operator grant; types land in `ext_<name>` on search_path (:3330-3351). Without a grant, a migration using `vector` fails. Under MAN-2510 that now blocks the deploy for all tenants (F-04).
- Verdict: CONFIRMED. Impact: semantic-search / fuzzy-match apps are designed around a limitation that no longer exists, or fail opaquely. Fix (SDK): add `extensions` to V2 §1 data row and §7, with the operator-approval step and the "type does not exist" symptom.

### F-10 - MEDIUM - The 64 KB migration cap applies to the concatenation of ALL migration files and is undocumented. CLI and check_app cannot see it
- SDK: no mention (grep "64 KB/MAX_MIGRATION" -> none).
- Platform: deploy_pipeline.py:496-502 `enforce_size_cap(migration_sql)` on the concat (comment: "Keep the aggregate"). validator:113,137-162 raises `forbidden` "... over the 65536-byte limit — split it into several files", but splitting cannot help an aggregate. The CLI deliberately has no cap (cli tests/test_migration_validator_parity.py:139-153).
- Verdict: CONFIRMED (code). Impact: an app whose cumulative history passes 64 KB becomes undeployable. Applied files may not be edited, and removing them breaks new installs. `manaurum app validate-migration` stays green. Fix: SDK - document the aggregate cap and keep migrations terse. Platform - the message advises splitting, which does not reduce an aggregate; decide whether already-applied files should count (Q-4).

### F-11 - MEDIUM - Deploy-time manifest rules beyond the schema are not documented: reserved slugs (MAN-2500), UUID-shaped slugs, slug regex enforcement, write-verb `is_write:false` (MAN-2358)
- SDK: V2:80 "Schema only enforces `minLength: 1` — but ... keep it `^[a-z]...` ... in practice"; SS:144-145 "no regex in the schema ... keep it"; reserved list and MAN-2358 rule are absent. V2:152 explains `is_write` but not that `record_sale` + `false` is a 422.
- Platform: manifest_v2_validator.py:143-147,212-239 (write verbs), :263-267 + reserved_slugs.py:38-55 (14 names incl. `app`, `api`, `www`, `mcp`, `registry`, `library`, `staging`); owner_deploy.py:92-104 (slug regex + UUID shape, 422 `app_id_invalid`).
- Verdict: CONFIRMED. Impact: low cost now that these are synchronous 422s, but an agent choosing a slug like `api` or `library` for a docs app hits a refusal the SDK never mentions. Fix (SDK): list the rules in V2 §1 / AS:213. Optionally have check_app check the slug and the reserved list.

### F-12 - HIGH (low impact) - `runtime.entrypoint` on a hosted app is a 422, not "ignored"
- SDK: V2:308 "for `hosted` apps the URL is platform-derived ... and any `entrypoint` you write is ignored".
- Platform: schema:17-41 allOf: mode hosted|dev -> `"entrypoint": false`.
- Verdict: CONFIRMED. Fix (SDK): "forbidden outside `byo` - a 422".

### F-13 - HIGH (low impact) - The egress "Unresolved ... resolves to 0.0.0.0" note is stale (MAN-2263, 2026-09-02)
- SDK: V2:326 "The deploy also writes each declared host into the container's Swarm `Hosts` entries as `0.0.0.0 <host>`".
- Platform: stack_generator.py:350-373 - the list is a label only; "nothing in this spec decides reachability, so undeclared egress is open" (TODO MAN-185).
- Verdict: CONFIRMED. Impact: the advice (use `os.http.fetch`) stays right, but the stated reason is false, and raw container egress is open rather than inverted. Fix (SDK): replace the note.

### F-14 - MEDIUM - check_app.py migration fallback misses most of the validator and implies otherwise. `.SQL` is a false negative
- SDK: CA:89-96 (pattern list), CA:557-562 (note names only 2 unchecked rule families), CA:601 `path.suffix.lower() != ".sql"`. V2:566 says the fallback "leaves them unchecked ... prints a note naming exactly what went unchecked".
- Platform: §2 table; bundle_migrations.py:164 `base.endswith(".sql")` (case-sensitive).
- Verdict: CONFIRMED (scratch run, §2). Impact: with the usual install (no CLI importable), `clean` on migrations means almost nothing, while the note suggests near-complete coverage. Fix (SDK): make the note say that only DO-blocks and a subset of DROP/TRUNCATE/ALTER TYPE/DROP CONSTRAINT were checked. Optionally add the remaining forbidden keywords as warnings, and use a case-sensitive `.sql` check.

### F-15 - MEDIUM - check_app.py ignores `optional_capabilities` (false positive) and has no root-key check (false negative)
- SDK: CA:469-474 reads only `requires_capabilities`; CA:373-380 only `RUNTIME_KEYS`.
- Platform: deploy_pipeline.py:663-689 auto-grants requires ∪ optional to the home install. The root is `additionalProperties:false` (schema:15).
- Verdict: CONFIRMED (scratch run). Impact: an app that correctly declares an optional capability gets a red it does not deserve (the same failure class 3.1.0 fixed for runtime keys), and a root typo passes check_app. Fix (SDK): union both arrays. Check root keys against the 23-key set, derived from or tested against the schema.

### F-16 - MEDIUM - Deploying into a team tenant installs the app on every workspace's desktop (MAN-2693). The SDK says only "auto-installed implicitly"
- SDK: V2:629 "`private` (default) — only the home tenant sees the app. Auto-installed implicitly."; DS:352.
- Platform: tenant_lookup.py:218-245 - team tenant -> every workspace; public tenant -> each owner's primary workspace only. production.py `ensure_home_tenant_install` (:2166+). A redeploy keeps the existing grant list (ON CONFLICT DO NOTHING, :2175-2182).
- Verdict: CONFIRMED. Impact: a developer testing v0.1.0 in a company tenant ships it to every colleague's desktop on the first deploy. Fix (SDK): say so in DS "Multi-tenant deploys" and V2 §8, and suggest a personal/public tenant for experiments.

### F-17 - MEDIUM - Rollback is under-documented and V2 §6 is wrong
- SDK: V2:458-462 "rollback to previous version ... flips `v2_app_installs.installed_version_id`" with no body; AS:666 "flips the install back to the previous version". The DS section is correct (DS:262-277), but no errors are documented.
- Platform: `version_label` is required (dev_v2_deploy.py:764-765). The runner re-points `v2_apps.current_version_id` (production.py:4421-4428 -> activate_version :2456-2475), not installs. Errors: sync 409 `deploy_in_progress`; job `app_not_found` / `slug_released` / `version_not_found` / `already_current` / `image_unavailable`. A rollback runs **no readiness probe and no migration gate**, and does **not** re-sync `agent_capabilities` (production.py:4284-4470).
- Verdict: CONFIRMED. Fix (SDK): align V2 §6 and AS:666 with DS, and add the error list. State that rollback is not probed, so re-check by hand, and that Assistant tools keep the newer version's list (see P-2).

### F-18 - MEDIUM - The deploy job result and events are documented as 4 fields. The real result carries what a developer needs
- SDK: DS:148-162, AS:642-651 show `{app_id, version_id, image_tag, url}`. DS:156 and V2:437 give the image as `v2-app-my-app:1.0.0`.
- Platform: production.py:4065-4091 adds `version`, `image_digest`, `manifest_fingerprint`, `migration_fingerprint`, `per_tenant_status`, `ui_warnings` (MAN-2510 advisory UI lint). Failed jobs carry `result.log_kind/log_tail` (dev_v2_deploy.py:419-436). The phases are `manifest_validated` (+`ui_warnings`), `migrations_extracted`, `image_pushing`, `image_pushed`, `migration_failed`, `migration_gate_blocked`, `swarm_applying`, `swarm_applied`, `traefik_written`, `readiness_probing`, `readiness_ok|readiness_failed`, `agent_capabilities_synced`, `activated`. The image repo is `v2-app-<slug>-<tenant8>` (registry_client.py:136-150, MAN-1586).
- Verdict: CONFIRMED. Fix (SDK): document `ui_warnings`, `log_tail` and `per_tenant_status`, plus the phase list for stream readers.

### F-19 - MEDIUM - Archive limits and format are undocumented
- SDK: none (grep 413/archive_too_large/20 000/64 MB -> only CHANGELOG v1).
- Platform: 413 `archive_too_large` > 88 MiB base64 (config.py:536-537). Always-on: gzip or plain tar only (bzip2/xz refused), ≤ 64 MB expanded, ≤ 20 000 entries (archive_limits.py:32,83-93; bundle_migrations.py `_MAX_ENTRIES`). Migration files must be UTF-8.
- Verdict: CONFIRMED. Fix (SDK): one table in DS "Quickstart".

### F-20 - MEDIUM - CLI install pin and version claims are stale. HEAD CLI differs from the published 0.3.0 under the same number
- SDK: README:78 installs `cli-v0.2.0`; README:102-106 "That rewrite is in no released wheel ... the wheel you can actually install is `cli-v0.2.0`".
- Platform: `cli-v0.3.0` was published 2026-09-03 (`gh release list`; Linear MAN-2301 Done: "No surface pins `cli-v0.2.0`"). 0.2.0 rejects `camera`. HEAD `pyproject.toml` still says 0.3.0, but MAN-2358, MAN-2500 and MAN-2624 landed in `manaurum_cli/` after the release (git log of manaurum-cli-py since 09-03). The published 0.3.0 therefore lacks them, which is exactly what CA:524-527 works around.
- Verdict: CONFIRMED. Fix: SDK - pin `cli-v0.3.0` and drop the "no released wheel" paragraph (verify the 0.3.0 scaffold first). Platform - cut 0.3.1 so "0.3.0" names one artifact (MAN-1385 already warned).

### F-21 - LOW - "`.dockerignore` as a second line of defence" cannot protect retained source
- SDK: DS:320-321 "ship a `.dockerignore` as a second line of defence". The starter's own `.dockerignore` (templates/v2-starter/.dockerignore:26-29) says the platform does not apply it server-side.
- Platform: deploy_pipeline.py:579-583 - retention (MAN-990) and git history (MAN-1002) store "the developer's ORIGINAL upload".
- Verdict: CONFIRMED for retention. Fix (SDK): say `.dockerignore` affects at most the image, never the retained archive or git history, so only excluding at pack time helps.

### F-22 - LOW - Smaller stale or contradictory facts
- DS:288 and AS:668 call logs a "stub". It is a real Swarm tail, `?tail` clamped at 1000 (dev_v2_deploy.py:1375-1404; production.py:5116-5153). CONFIRMED.
- AS:677 `422 migration_validation_failed` - no such code exists in backend (grep). Migration refusals are job errors. CONFIRMED.
- DS:329 `401 missing_authorization` is never returned by `/api/dev/v2/*` (v2_developer_auth.py:402-403). CONFIRMED.
- V2:109 "Wildcard `"*"` grants everything" vs capabilities-reference.md:60 "There is no wildcard grant (MAN-1585)". This is an SDK self-contradiction. Owner: capabilities dimension.
- V2:401 cap 5 vs 20 (part of F-07). DS:228 "inside the backend container" - builds moved to a deployer service (MAN-2262, deploy_backend). LIKELY.
- SS:166-167 says omitting `data` "fails the deploy at `swarm_applying` with `MANAURUM_DDL_DSN is not set`". Stated unconditionally, but prod runs managed-mode apps with migrations (MAN-2510/3008 narratives). LIKELY wrong for prod; UNVERIFIABLE-WITHOUT-PROD.
- No `scripts/` test ties `RUNTIME_KEYS` (CA:82-84) to the schema (§1).

---

## 5. Platform-side findings (fix location: platform)

- **P-1 MEDIUM - CONFIRMED (code).** Rollback ignores `deploy_status`. `_target_deploy_status` is read and unused (production.py:4366), so a rollback "to" a label whose deploy was blocked by the migration gate or failed readiness activates it. It gets no probe and no gate, which bypasses MAN-2510 for that tenant set. Proposed: refuse targets whose `deploy_status != 'ready'`, or run the probe.
- **P-2 MEDIUM - CONFIRMED (code).** Rollback never calls `sync_v2_agent_capabilities` (only the deploy does, production.py:4045). After a rollback the Assistant still offers the newer version's tools, which the older container may 404.
- **P-3 LOW.** CLI `app deploy` docstring still says the endpoint "answers 202 pending *before* it has validated the manifest" (manaurum-cli-py/manaurum_cli/main.py:398-399). Stale since MAN-2597. The CLI also lacks the slug-shape check that `owner_deploy_slug` applies (manaurum_cli/manifest.py has reserved slugs, not `_VALID_SLUG_RE`/UUID). Low cost now that the server answers 422 synchronously.
- **P-4 LOW.** The size-cap message "split it into several files under migrations/" (migration_validator.py:154-157) is wrong when the cap is hit on the aggregate (F-10).

---

## 6. Questions (no evidence; need prod or owner)

- Q-1: What are `MANAURUM_V2_BUILD_SCAN_MODE` and `MANAURUM_V2_BUILD_ALLOWED_BASE_IMAGES` on prod? If `enforce`, the SDK is missing a whole rejection class: symlinks anywhere, ONBUILD, remote ADD, non-allow-listed `FROM`, and credential substrings (`AKIA`, `ASIA`, `AIza`, `sk-ant-`...) in any text file including `.md`/`.json`. Some of these could false-positive. Note that `mna_` is not among the markers (credential_markers.py:14-25), so a packed `.env.manaurum` is not caught even in enforce mode.
- Q-2: Is there any supported way to add a co-owner to a v2 app (team development)? None found in routes.
- Q-3: Does the App Store consent sheet show `optional_capabilities`? The schema says no (schema:382) and V2:96 says yes. The UI lives outside SNAP.
- Q-4: Should already-applied migration files count toward the 64 KB aggregate (F-10)?
- Q-5: Are `MANAURUM_V2_READINESS_PROBE` and `MANAURUM_V2_MIGRATION_GATE` at their defaults (on) on prod? F-02 and F-04 assume yes.

---

## 7. Summary
Covered: the full schema property matrix (both schema copies are identical), every validator rule against SDK text and both check_app paths (with a scratch-dir demonstration), all synchronous and job-level deploy refusals, token issuance (MAN-1585/2596/2597/2620), the readiness probe, the migration gate, version immutability, rollback internals, home-install fan-out (MAN-2693), the CLI command surface and release state, and the starter manifest, Dockerfile and .dockerignore.
Biggest themes: five SDK sentences still say "no readiness probe", four say "manifest validated only in the job", four say "migration failure still activates", four give the mic-only enum, and V2 §4 tokens is pre-MAN-1585. V2:24 is a sixth surviving copy of "runtime not strict".
Not covered in depth: V2_DEVELOPER_GUIDE.md (known stale, MAN-1491), dev-mode publish route internals, BYO deploy (`dev_v2_byo`), the deployer service (MAN-2262) build path, and real execution of the pglast validator (pglast/jsonschema 4 are not installed, so verdicts on SQL classification are from code reading).

# Verify-A: C1–C7, H1–H17

SDK = C:\dev\wt\sdk-audit @6f52dce. Platform = SNAP @285c8a8 (`be/` = backend/app/). Each line reads: id | verdict | corrected SDK lines | key platform evidence | severity | note.

## CRITICAL

**C1 | CONFIRM**
- **SDK:** starter `src/auth.py:43-83`. It never compares `app_id`/`tenant_id` and reads them with `.get(...,"")`, so a missing claim is tolerated. `main.py:28-29` "only trustworthy caller identity". `SKILL.md:235` (not 234) "anonymous: proxied with no user context". `v2-platform.md:247`.
- **Platform evidence:**
  - Audience: `be/services/v2_apps/user_context_jwt.py:71` has a constant aud, and the platform's own verifier `:140-197` + `_manaurum_runtime.py:103-140` also never bind app_id.
  - Gateway: `be/routes/v2_app_gateway.py:564-573` strips only hop-by-hop + authorization/cookie. `:866` `dict(request.headers)` gives lowercase keys (Starlette). `:912` adds `"X-Manaurum-User-Context"` under different casing.
  - Re-derived with httpx 0.28.1 / Starlette 1.7: httpx sends **both** lines in insertion order (client first), and the container's `request.headers.get()` returns **the client's copy**. Anonymous and non-/api paths forward the client header alone.
  - Nothing else strips it. Traefik per-app config is only compress + addPrefix → Core (`traefik_yaml.py:190-246`). No main.py middleware touches it.
  - Shared network: `stack_generator.py:17-24`.
  - Mitigation exists only at the capability gateway, and only for os.ai.complete (`completion_context.py:78-81`).
- **Severity:** keep CRITICAL for the platform half. The SDK half alone ≈ HIGH. It needs a captured token, i.e. an attacker who runs an app the victim opens in the same tenant.
- **Note:** MAN-1307 (SEC-LOW, Todo) covers app binding. **The inbound-header pass-through is unticketed.** I searched "user context", "user_context", "User-Context header", "duplicate header", "inbound X-Manaurum", "header spoof", "client-supplied", "strip inbound header" with no hit. It removes MAN-1307's "needs flat network" precondition, so file it as a platform ticket. The starter should still bind `app_id`==APP_SLUG and `tenant_id`==MANAURUM_TENANT_ID.

**C2 | CONFIRM**
- **SDK:** `capabilities-reference.md:160-184`. No `size_hint` anywhere in the SDK.
- **Platform evidence:** `be/services/capabilities/files.py:95-96` has required `["key","content_type","size_hint"]` and additionalProperties false. The gateway answers `422 input_schema_violation` (`be/routes/capability_gateway.py:307-325,773`). Limits: `be/constants.py:139-140` (50 MB / 1 GB). Rate limits `files.py:71` (20/60s, 200/h) → `upload_rate_limited` `:336`. The PUT must match the signed exact length.
- **Severity:** agree.
- **Note:** every documented call returns 422.

**C3 | CONFIRM**
- **SDK:** `capabilities-reference.md:467-496`.
- **Platform evidence:**
  - Input: `be/services/capabilities/ocr.py:84-99` takes `{file_key, schema?}` with additionalProperties false. No `provider`/`object_key`.
  - Output: `:599-610` returns `{extracted, confidence, model_used, tokens_used{}, cost_usd}`.
  - Errors: `404 file_not_found` `:277`, `412 ai_provider_not_configured` `:256`, `422 vlm_output_schema_violation` `:427`.
- **Severity:** agree.
- **Note:** documented models are stale too (default `claude-sonnet-4-6`, `:72`).

**C4 | CONFIRM**
- **SDK:** `capabilities-reference.md:718-738`, `SKILL.md:398`, `v2-platform.md:98-99`.
- **Platform evidence:**
  - Input: `be/services/capabilities/rpc.py:64-80` requires `target_app_id, method, args`; `version` int; `timeout_ms`; additionalProperties false. The documented `app_id`/`"1"`/`timeout_seconds` → 422.
  - Output: `{result, latency_ms, target_version}` (`:126`).
  - Dispatch is in-process only (`:16-19`). Registered targets are `be/services/builtin_rpc/__init__.py:90-92`: menu-profitability (3 methods) + receptions (1). That is **4 methods on 2 builtins**, not "4 targets".
- **Severity:** agree.
- **Note:** a v2→v2 RPC is impossible.

**C5 | CONFIRM**
- **SDK:** `capabilities-reference.md:347-387`.
- **Platform evidence:**
  - Input: `be/services/capabilities/ai.py:176-217` requires only `messages`; provider/model are optional; no `top_p` (additionalProperties false).
  - Output: `:1322-1329` returns `{content, tokens_used, cost_usd, cost_known, provider, model}`.
  - Errors: `412 workspace_context_required` `:1067` / `completion_context.py:112`, `403 ai_disabled` `:1083`, `429 ai_spend_cap` `:1124`, `403 app_installation_required` `completion_context.py:77`. `missing_provider_credentials`/`upstream_5xx` appear nowhere in be/.
- **Severity:** agree.
- **Note:** the workspace auto-resolves when the app is installed in exactly one non-ephemeral workspace. It is 412 only with more than one, and 403 `workspace_context_unavailable` with none. Nothing in the SDK mentions X-Manaurum-Workspace-Id.

**C6 | CONFIRM (starter) / REFUTE (README cite)**
- **SDK:** starter `src/capability.py:76-77` "the gateway rejects it on this path". `call_capability()` has no parameter to forward it. Starter `README.md:28-29` contains no such claim (tree lines only).
- **Platform evidence:** `be/routes/capability_gateway.py:655-684` accepts and verifies the header. `:762-764` raises `403 user_context_required` for auth_mode user. drive/calendar are registered `auth_mode="user"` (`drive.py:845-895`, `calendar.py:125,134`).
- **Severity:** suggest **HIGH**. The failure is a loud, self-naming 403 and `SKILL.md:357,680` + `CR:62-65` give the fix.
- **Note:** this also feeds C5. Without the forwarded context, os.ai.complete needs a workspace selector when the app is in more than one workspace.

**C7 | CONFIRM (facts)**
- **SDK:** setup `SKILL.md:71` (.env.manaurum inside the app tree). deploy `SKILL.md:372-374` sources `./.env.manaurum`. App `SKILL.md:157,167` says one level up. `check_app.py:87` regex. `linter_mutations.py:201` fake token.
- **Platform evidence:**
  - CLI packager: `manaurum-cli-py/manaurum_cli/packaging.py:20-41` is an exact-name exclude list. It has no `.env*`, ignores `.dockerignore`/`.gitignore`, and `iterdir()` includes dotfiles. The CLI keeps its own creds in config_path (`config.py:29`), so .env.manaurum is purely SDK-induced.
  - Token shape `be/routes/developer/v2_credentials.py:409-411`: `mna_<12hex>_<urlsafe>`. Verified: the regex never matches a real mna_ token, nor a real `mnu_<env>_<32>` (`tenant_developer_api_token.py:83-85`).
  - The platform scanner's `credential_markers.py:14-25` has no mna_/mnu_, and the scanner is **off by default** (`be/config.py:503-504`, `deploy_pipeline.py:343`).
- **Severity:** suggest **HIGH**.
- **Note:** several defences make the leak require CLI deploy *and* an ignored linter:
  - The deploy.sh tar excludes `.env*` (deploy `SKILL.md:400`).
  - `check_app.py:444-457` rule 5 flags any `.env*` inside the app dir regardless of TOKEN_LITERAL.
  - The starter `.gitignore`/`.dockerignore` cover `.env*`.

  The real defect is the setup tree contradicting SKILL.md:157, plus a dead token regex.

## HIGH

**H1 | CONFIRM**
- **SDK:** starter `index.html:63-84`, `SKILL.md:309-325`, `sdk-api.md:97-104,127`.
- **Platform evidence:** rule at `docs/handoff/V2_DEVELOPER_GUIDE.md:1315-1339` @285c8a8 (git show) and `manaurum-cli-py/manaurum_cli/templates/index.html.template:31-37` (SHELL_ORIGINS + `source===window.parent`). `frontend/public/sdk/manaurum-v2.mjs:235-252` stores the first sender's origin.
- **Severity:** agree.
- **Note:** in the starter the impact is a spoofed theme. It becomes real if an app trusts `init.user`/`granted_capabilities`. Frame-ancestors not re-checked.

**H2 | CONFIRM**
- **SDK:** deploy `SKILL.md:193-196,464-465`; app `SKILL.md:654`; `publishing.md:42-43`; `README.md:207-208` (not 212).
- **Platform evidence:** `be/services/v2_apps/production.py:1050-1060` (default ON) and `:3962-4007`. A failed probe rolls back, fails the job and attaches logs (MAN-1369, 2026-07-25).
- **Severity:** agree.
- **Note:** whether prod sets `MANAURUM_V2_READINESS_PROBE=0` cannot be checked without prod.

**H3 | CONFIRM**
- **SDK:** `SKILL.md:283,555,682`; deploy `:37,341`; setup `:152,237`; `check_app.py:14,333,347`; `README.md:36`; starter `README.md:88`.
- **Platform evidence:** `production.py:1110-1131` makes the probe dial `service:runtime.port`, so a wrong port or a 127.0.0.1 bind means no answer, a ReadinessError and a rollback with a failed job. `traefik_yaml.py:236-246` shows Traefik → Core backend, not the app port.
- **Severity:** agree.

**H4 | CONFIRM (except deploy:335)**
- **SDK:** deploy `SKILL.md:199-200,251-253`; `v2-platform.md:441,488`. The `deploy:335` cite has no such claim.
- **Platform evidence:** `production.py:1090-1102` (gate default ON) and `:3839-3904` (MigrationGateBlocked "blocked before swarm"; nothing activates).
- **Severity:** agree.
- **Note:** v2-platform §5 (`:432-441`) lists migrations as step 8, after swarm/traefik. Really they run before swarm (`deploy_pipeline.py:693-711` + `production.py:3846`).

**H5 | CONFIRM**
- **SDK:** deploy `SKILL.md:178-188,324-334,344`; `SKILL.md:635`; `v2-platform.md:430`; `publishing.md:15,22-25`.
- **Platform evidence:** `be/routes/dev_v2_deploy.py:813-890` and `be/services/v2_apps/owner_deploy.py:64-104,107-131`. Synchronous refusals:
  - 422 `manifest_validation_failed` (+errors)
  - 422 `app_id_invalid`
  - 413 `archive_too_large`
  - 409 `slug_owned_by_another_tenant` / `version_already_published` / `slug_reserved`
  - 403 `app_id_out_of_scope`
  - 403 `runtime_credential_not_allowed` (`be/auth/v2_developer_auth.py:466`)
- **Severity:** agree.

**H6 | CONFIRM**
- **SDK:** `v2-platform.md:445` (contradicts `SKILL.md:208`); image path `v2-platform.md:437`, `SKILL.md:648`, deploy `:156`.
- **Platform evidence:** `production.py:4166-4204` (preflight 409) and `:574-599` (a tag pushed by a failed deploy counts as published). `be/services/v2_apps/registry_client.py:133`: `v2-app-{slug}-{tenant8}`.
- **Severity:** agree.

**H7 | CONFIRM**
- **SDK:** `v2-platform.md:361,387,398,401,421`; deploy `:330`; `v2-platform.md:109` (grant wildcard).
- **Platform evidence:** `be/routes/developer/v2_credentials.py:261-298` (400 `apps_required` / `apps_wildcard_not_allowed`), `:318-350` (403 `apps_not_owned`; a new app needs an owner token), `:74` cap 20, `:98,104` 365/90 days. Grant wildcard removed: `granted_capabilities.py:13,203`.
- **Severity:** agree.
- **Note:** `CR:60` already says "no wildcard grant", which makes this an internal contradiction. "No co-owner route" not verified.

**H8 | CONFIRM**
- **SDK:** `v2-platform.md:24`.
- **Platform evidence:** `be/services/_schemas/manifest_v2.schema.json:96` (runtime additionalProperties false).
- **Severity:** agree.
- **Note:** half of the sentence is still true: `metadata` has no additionalProperties (not strict). Only the `runtime` half and the "typo passes" example are false.

**H9 | CONFIRM**
- **SDK:** `SKILL.md:219`, `v2-platform.md:104`, `publishing.md:64`, setup `:175-176`. The `sdk-api.md:51` cite is an example payload, not an enum claim; drop it.
- **Platform evidence:** `schema:318-328` enum microphone+camera. A byo `permissions` maxItems 0 rule sits in the schema allOf.
- **Severity:** agree (per rubric); low impact.

**H10 | CONFIRM**
- **SDK:** `v2-platform.md:117,156,281`; `README.md:38`; `SKILL.md:554`; `check_app.py:16,277-291`; starter `agent_routes.py:19-21`, `README.md:115-117`, `tests/test_manifest.py:11-12`, `tests/test_routes.py:6-9,33`.
- **Platform evidence:** `be/routes/v2_app_gateway.py:98-113,786-797` (404 `route_not_declared`, MAN-1432; case-folded and slash-collapsed).
- **Severity:** agree (wrong fact).
- **Note:** the advice "verify the JWT" stays correct (shared network, C1). Only the rationale is wrong.

**H11 | CONFIRM**
- **SDK:** `v2-platform.md:229`.
- **Platform evidence:** `v2_app_gateway.py:817-857` proxies non-/api paths anonymously; only document navigations to private pages redirect. The schema description `manifest_v2.schema.json:109` repeats the false claim.
- **Severity:** suggest MEDIUM.
- **Note:** true only for a health_path under undeclared `/api/` or under `/agent/`.

**H12 | CONFIRM**
- **SDK:** `capabilities-reference.md:3-4` ("All **26**").
- **Platform evidence:** 32 `CapabilityDefinition(name=...)` in `be/services/capabilities/*.py`, all registered via `be/main.py:316-349,1146-1196`. Zero SDK mentions of os.ai.providers / ai.image_submit / ai.image_poll / locations.list / locations.get / drive.delete.
- **Severity:** suggest MEDIUM (gap), except the false count.

**H13 | CONFIRM**
- **SDK:** `capabilities-reference.md:236-251`.
- **Platform evidence:**
  - Size limit: `be/services/drive_publish.py:51` is 50 MB.
  - Extensions: `drive.py:64-92` adds gif/doc/docx/xls/xlsx/zip/rar/audio.
  - Notification: `drive.py:18` "No notification".
  - Write: `drive.py:164-180` accepts `file_id` overwrite + `if_match`, and `:772-774` returns 412 `version_conflict`. So `write` is not "create-only".
  - Delete: os.drive.delete is registered.
- **Severity:** agree.

**H14 | CONFIRM**
- **SDK:** `capabilities-reference.md:673`.
- **Platform evidence:** `be/services/capabilities/compliance.py:62-83` is RLS tenant-only; `app_filter` is optional and caller-supplied, so any app reads every app's rows in the tenant.
- **Severity:** agree.
- **Note:** MAN-2253 is In Progress.

**H15 | CONFIRM**
- **SDK:** `capabilities-reference.md:742-750`.
- **Platform evidence:** `be/services/capabilities/bulk_export.py:83-95` requires `target_app_id, dataset` (additionalProperties false), so the documented `{dataset_name,version,args}` → 422. No `BulkExportDataset` is registered outside tests, so every call hits `404 dataset_not_found` (`:137`).
- **Severity:** agree (arguably the same class as C4).

**H16 | CONFIRM**
- **SDK:** `capabilities-reference.md:400-410`.
- **Platform evidence:** `ai.py:1475-1482` returns `{embeddings, tokens_used, cost_usd, cost_known, provider, model}` with no `usage`.
- **Severity:** agree.

**H17 | CONFIRM**
- **SDK:** `design.md:330-332` (plus `:324-325` "one `<link>`"); starter `app.css:19-27`.
- **Platform evidence:** `library/tokens/tokens.css` @285c8a8 (not in SNAP; via git show). `:13-15` names the fixed host. `:125-126` define amber and green (verdant too). `--app-bg`, `--surface-input` and `--font-mono` are absent, but the starter uses them. Fixed by MAN-2367 (9166b92c5, 2026-09-06).
- **Severity:** suggest MEDIUM.
- **Note:** the stale text causes no runtime break.

## Summary

- **Result:** 24/24 claims hold in substance. Two citations are refuted or misplaced: C6 starter README:28-29 and H4 deploy:335. Line corrections are given inline (H2 README 207-208, H5 v2-platform 430, C1 SKILL 235, H9 drop sdk-api:51).
- **Severity changes:**
  - Down to HIGH: C6 and C7 (existing linter rule 5 and deploy.sh guard mitigate C7).
  - Down to MEDIUM: H11, H12, H17.
  - C1: keep CRITICAL only on the strength of the newly found, unticketed gateway pass-through of client-supplied `X-Manaurum-User-Context` (client copy reaches the container first). The app-binding half is MAN-1307 (SEC-LOW).
- **Not checked:** the effective prod env (readiness, migration gate, scan mode); H1 frame-ancestors; H7 "no co-owner route".

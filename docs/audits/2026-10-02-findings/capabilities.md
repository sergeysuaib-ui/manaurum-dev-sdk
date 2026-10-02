# Dimension: CAPABILITIES — completeness and accuracy

SDK = `C:\dev\wt\sdk-audit` @ 6f52dce (3.1.0). Platform = monorepo @285c8a8 (SNAP extract).
Abbreviations: `CR` = `skills/manaurum-app/references/capabilities-reference.md`,
`V2P` = `skills/manaurum-app/references/v2-platform.md`, `caps/` = `backend/app/services/capabilities/`.

## 1. Authoritative registry (32 capabilities)

Every `CapabilityDefinition(name=...)` under `caps/`, all wired at boot (`backend/app/main.py:340-359` and `:1146-1196` @285c8a8). All `version=1`. **No registration sets `quota_per_tenant_per_day`**, so every daily quota is `None` = unlimited (`caps/quota.py:82-85`; MAN-2569 open). No per-capability feature flag, except `os.ai.image_*`, which checks the tenant flag `platform.ai_image` inside the handler (default OFF, `caps/ai_image.py:114,383-385`). Sensitive set (`caps/sensitivity.py:278-285`): prefixes `os.ai. os.ocr. os.bulk_export. os.notifications. os.http. os.secrets.`. These are withheld at first install only when `settings.v2_strict_capability_grants` is on (`config.py:483`, default False).

| Capability | auth | exec class | sensitive | In SDK? | Input | Output | Errors | Verdict |
|---|---|---|---|---|---|---|---|---|
| os.kv.get / os.kv.set | app | fast_db | no | yes | ok | ok | ok | accurate |
| os.tenant_config.get | app | fast_db | no | yes (CR ok, SKILL.md wrong) | ok | ok | ok | see H7 |
| os.secrets.get / .set | app | fast_db | yes | yes | ok | ok | ok | accurate |
| os.files.upload | app | external_io | no | yes | **missing required `size_hint`** | missing `content_length` | 413/429 missing | **C2** |
| os.files.download | app | fast_db | no | yes | `expires_in` missing | ok | "404" is wrong | L1 |
| os.files.delete / os.files.list | app | external_io | no | yes | ok | ok | — | accurate |
| os.drive.stage/publish/list/read/write | user | mixed | no | yes | write: overwrite missing | write output missing fields | — | **H6** |
| os.drive.delete | user | fast_db | no | **no** | — | — | — | **H1/H6** |
| os.calendar.create_event / list_events | user | fast_db | no | yes | ok | ok | ok | accurate |
| os.ai.complete | app (+workspace) | external_io | yes | yes | provider/model wrongly "required"; `top_p` passthrough is false; `log_prompt` missing | **wrong** | **wrong** | **C4** |
| os.ai.embed | app | external_io | yes | yes | `log_prompt` missing | **wrong** | missing | **H2** |
| os.ai.transcribe | app | external_io | yes | yes | ok | ok | ok | accurate |
| os.ai.providers | app (+workspace) | fast_db | yes | **no** | — | — | — | **H1** |
| os.ai.image_submit / image_poll | app | external_io | yes | **no** | — | — | — | **H1** |
| os.ocr.extract | app | external_io | yes | yes | **wrong** | **wrong** | **wrong** | **C1** |
| os.notifications.send_to_user | app | external_io | yes | yes | ok | ok | one code missing; one wrong number | M4 |
| os.events.emit | app | fast_db | no | yes | `payload` must be an object; `idempotency_key` missing | ok | — | M3 |
| os.http.fetch | app | external_io | yes | yes | ok | ok | ok | accurate (3.1.0 redirect fix verified) |
| os.compliance.audit_query | app | fast_db | no | yes | ok | missing `app_id` field | — | **H5** (scope claim wrong) |
| os.apps.call | app | fast_db | no | yes | **wrong** | **wrong** | **wrong** | **C3** |
| os.apps.bulk_export | app | db_stream | **no** (MAN-1902) | yes | **wrong** | sentinel wrong | — | **H9** |
| os.locations.list / os.locations.get | app | fast_db | no | **no** | — | — | — | **H1** |

`os.workspace.members` (MAN-1289) and `os.directory.list_users` (MAN-2519, In Review) are **not registered** @285c8a8. The SDK correctly does not claim them.

---

## 2. Findings

### CRITICAL

**C1 — `os.ocr.extract` is documented with a contract that 422s on every call** — CRITICAL, CONFIRMED
- SDK `CR:469-496`: "Two providers: `anthropic-vision` … `openai-vision`"; input `{provider, object_key, schema}`, all three "required". Output `{ "data": …, "model": … }`. Errors `404 object_not_found`, `422 schema_violation`, `412 missing_provider_credentials`.
- Platform `caps/ocr.py:84-98 @285c8a8`: `"required": ["file_key"]`, `additionalProperties: False`, `schema` optional. No `provider` and no `object_key` field exists, so the documented body is a 422 `input_schema_violation`. Output `ocr.py:600-610`: `{extracted, confidence, model_used, tokens_used{prompt,completion,total}, cost_usd}`. Errors: `412 ai_provider_not_configured` (:256), `404 file_not_found` (:277), `422 vlm_output_not_json` / `vlm_output_schema_violation` (:396,:426), `400 invalid_schema_not_object` (:510), `400 invalid_file_key_*`. The provider is auto-resolved: anthropic first, then openai (:230-258).
- Impact: an app built from the SDK fails every OCR call, and the deploy is green. A developer who fixes the input then reads `output.data`, which does not exist.
- Fix: SDK. Rewrite the section from `ocr.py`. Related: MAN-1563 (first-key-wins resolution), MAN-2961.

**C2 — `os.files.upload` omits the required `size_hint` (MAN-1707, platform since 2026-08-13)** — CRITICAL, CONFIRMED
- SDK `CR:166-184`: input `{ "key", "content_type" }`; output `{upload_url, expires_at}`. `size_hint` appears nowhere in the SDK (grep).
- Platform `caps/files.py:95` `"required": ["key", "content_type", "size_hint"]`. `size_hint` is the **exact** byte length signed into the URL (`:104-114, :382-387`), so a PUT of any other size is rejected by R2. Limits: 50 MB per object, 1 GB per (app, tenant) (`backend/app/constants.py:139-140`). Upload URLs are throttled at 20 per minute and 200 per hour per (app, tenant) (`files.py:71`). New errors: `413 object_too_large`, `413 namespace_quota_exceeded {used_bytes, quota_bytes}`, `413 namespace_scan_incomplete` (>10 000 objects), and `429 upload_rate_limited` with `Retry-After: 60` (`:299-380`). The output adds `content_length` (:393). `expires_in` (60–3600) is optional on upload and download (`:77-85`).
- Impact: every upload written from the SDK gets `422 input_schema_violation`. Before MAN-1707 it worked, which makes this the "true once, now false" pattern.
- Fix: SDK. Document `size_hint` (exact length), the caps, the 413/429 errors, `expires_in` and `content_length`. Also add it to the SKILL.md capability table.

**C3 — `os.apps.call`: wrong field names and types, wrong output and errors, and "RPC to another v2 app" is not possible** — CRITICAL, CONFIRMED
- SDK `CR:718-738`: input `{app_id, method, version: "1", args, timeout_seconds}`. Output: "Whatever the target method returns". Errors `404 method_not_found`, `503 timeout`. `SKILL.md:398` says "Sync RPC to another v2 app". `V2P:98` says "Another app calling you via `os.apps.call` must find the method here [provides]".
- Platform `caps/rpc.py:64-80`: `required: ["target_app_id","method","args"]`, `version` is an **integer**, `timeout_ms` (max 30000), `additionalProperties: False`. The documented body is therefore a 422. Output `rpc.py:194-201`: `{result, latency_ms, target_version}`. Errors: `404 rpc_target_not_found`, `422 rpc_args_schema_violation`, `503 rpc_target_timeout`, `503 rpc_target_unavailable`. Targets come only from the in-process `RpcRegistry`, populated solely by builtins (`services/builtin_rpc/__init__.py`, registered `menu_profitability.py:560-585` and `receptions.py:128-131`: `recipes.ingredients`, `sales.daily_totals`, `sales.dish_totals`, `stock.levels`). A hosted v2 app **cannot be a target**: `provides.rpc` is not read. `consumes.rpc` is not enforced (`rpc.py:21-24,157-158`).
- Impact: every documented call is a 422. Any design that relies on app-to-app RPC is impossible.
- Fix: SDK. Document the real wire format, state that only builtin targets exist and name them, and remove the "another v2 app" / "must find the method here" claims. Platform: the consumes gate is tracked in MAN-2253 / MAN-1905.

**C4 — `os.ai.complete`: wrong output shape and error codes, and the workspace / company-funded model is undocumented (MAN-1971, MAN-2412, MAN-2158)** — CRITICAL, CONFIRMED (code) / LIKELY (prod frequency)
- SDK `CR:347-386`: BYOK only, "Five providers", `provider` and `model` **required**, "`temperature`, `max_tokens`, `top_p`, etc. … passed through". Output `{content, model, usage:{input_tokens, output_tokens}}`. Errors `412 missing_provider_credentials`, `400 unsupported_provider`, `502 upstream_5xx`. `SKILL.md:391` says "LLM (BYOK — tenant configures keys…)".
- Platform:
  - Schema `caps/ai.py:176-217`: only `messages` is required. `provider` and `model` are optional. `additionalProperties: False` with exactly `provider, model, messages, temperature, max_tokens, log_prompt`, so **`top_p` is a 422**. Message roles are limited to system/user/assistant and content must be a string.
  - Output `ai.py:1322-1329`: `{content, tokens_used:{input,output,total}, cost_usd, cost_known, provider, model}`. There is no `usage`.
  - When neither `provider` nor `model` is pinned, the call uses the **workspace's** completion backend, which can be the managed company-funded "manaurum" provider (`ai.py:1076-1079`, MAN-1971 / MAN-2412).
  - The gateway resolves an installed-workspace context for `os.ai.complete` and `os.ai.providers` (`routes/capability_gateway.py:848-866`, `completion_context.py:70-113`). New errors:
    - `403 app_installation_required`
    - `403 workspace_context_unavailable` (no non-ephemeral workspace install)
    - `412 workspace_context_required`. An app-only call with no user context, made by an app installed in more than one workspace, must send the new **`X-Manaurum-Workspace-Id`** header (gateway :600, :852).
    - `403 workspace_context_mismatch`
    - `403 ai_disabled` (AI switched off for the app in Settings)
    - `412 ai_backend_unavailable`
    - `429 ai_spend_cap {subject, window}`
    - `412 integration_not_configured {provider}`
    - `412 no_ai_provider_configured`
    - `502 upstream_error:<provider>`, or `502 {error: ai_upstream_error, attempts[]}`
    
    (`ai.py:945-989, 1066-1124, 1346-1354`)
  - `log_prompt: false` (MAN-2158) keeps prompts out of `llm_call_log` (`ai.py:118-130, 1047`).
- Impact: code that reads `output.usage.*` crashes on a successful response. `top_p` breaks the call. A background job in a multi-workspace tenant gets a 412 the SDK never mentions. The cost of a call (`cost_usd`/`cost_known`) is invisible to developers.
- Fix: SDK. Rewrite the section: optional provider/model, the workspace header, the managed fallback, the error table, `log_prompt`, the real output. Update `SKILL.md:391` and `V2P:370`.

### HIGH

**H1 — 6 registered capabilities are undocumented, and "All 26" is stale (32 registered)** — HIGH, CONFIRMED
- SDK `CR:3`: "All **26** capabilities registered … are documented below". A grep of the whole SDK finds no `os.ai.providers`, `os.ai.image_submit`, `os.ai.image_poll`, `os.locations.list`, `os.locations.get` or `os.drive.delete`. `CR:218` says "All five capabilities" for drive, but there are six. The `SKILL.md:384-400` table also omits `os.files.list`, `os.apps.bulk_export` and the six above.
- Platform: `caps/ai.py:1729-1739` (providers, MAN-2136, 2026-08-31). `caps/ai_image.py:879-905` (image submit/poll, MAN-2133, 2026-08-28): submit `{prompt≤4000, size, quality, format, compression}` → `{job_id, provider, driver_model, state:"pending"}`; poll `{job_id}` → `{state: pending|failed|done, image_base64, mime_type, …tokens_used, cost}`; `403 image_generation_not_enabled` without the tenant flag `platform.ai_image`, `404 image_job_not_found`. `caps/locations.py:288-311` (MAN-2185): `list {kind?: sales_point|warehouse}` → `{locations[{id,name,kind}], count}` with a 500 cap; `get {location_id}` → row or `404 location_not_found`. `caps/drive.py:785-832, 891-897` (`os.drive.delete {file_id}` → `{deleted, file_id, filename}`, soft delete to Trash).
- Impact: developers re-implement image generation and branch lookup by hand, or never learn that `os.ai.providers` exists to check before they fail.
- Fix: SDK. Add six sections. Replace the hard-coded "26" with the grep command `CR:762-765` already gives, or a generated count.

**H2 — `os.ai.embed` output and errors are wrong** — HIGH, CONFIRMED
- SDK `CR:402-410`: output `{embeddings, model, usage:{input_tokens}}`. No errors are listed.
- Platform `caps/ai.py:1475-1482`: `{embeddings, tokens_used, cost_usd, cost_known, provider, model}`. Errors: `412 integration_not_configured`, `502 upstream_error:<provider>` (`:1379-1420`). The input also accepts `log_prompt` (:242).
- Fix: SDK.

**H3 — The universal error table and the call example in V2P §3 are stale; the MAN-1585 "wildcard" fact survives in 5 places** — HIGH, CONFIRMED
- SDK:
  - `V2P:338` example `X-Manaurum-App-Id: <uuid>`. That contradicts the slug rule (`CR:31-41`, `SKILL.md:356`).
  - `V2P:361` "Wildcard `*` is honored". `V2P:109` "Wildcard `"*"` grants everything". `V2P:398` `-d '{"apps": ["*"]}'`. `V2P:421` "`["*"]` (default) → any app". `skills/manaurum-deploy/SKILL.md:330` "(or `*`)".
  - `V2P:362` "404 | (none)".
  - `V2P:365` lists `app_id_must_be_uuid` as universal.
  - `V2P:370` `502 upstream_5xx`.
- Platform:
  - `caps/granted_capabilities.py:13,203-207`: "There is no wildcard (MAN-1585)". `auth/v2_developer_auth.py:61-66`: `"*"` is refused at every layer (DB CHECK, issuance, scope).
  - `routes/capability_gateway.py:754` `404 capability_not_found`.
  - `app_id_must_be_uuid` is raised only by `os.kv.*` and `os.events.emit` (`caps/_ctx.py:64-91`).
  - `upstream_5xx` exists nowhere in `backend/app` (grep).
  - Undocumented gateway codes: `403 owner_scoped_credential_not_accepted` (:719), `412 malformed_tenant_id_header` (:646), `503 user_context_unavailable` (:663), `501 system_caller_not_implemented` (:624). `CR:53` presents `tenant_mismatch` as `detail.error`, but it is a plain string detail (:748).
- Impact: a developer told that "`*` grants everything" will not list their capabilities, and a token request with `"*"` is refused. `CR:60` already says the opposite, so the SDK contradicts itself.
- Fix: SDK. Make `V2P` §3 one table generated from the gateway, delete every wildcard sentence, and point to `CR` for per-capability codes.

**H4 — The starter template tells every app the gateway "rejects" user_context** — HIGH, CONFIRMED
- SDK `templates/v2-starter/src/capability.py:76-77`: "Do NOT forward the user_context header here — the gateway rejects it on this path." `CR:62-65` explicitly says that statement is wrong.
- Platform `routes/capability_gateway.py:656-685`: a presented `X-Manaurum-User-Context` is verified and used. It is **required** for `auth_mode: user` (`:761-764`, detail at :763).
- Impact: the starter's `call_capability()` has no way to pass the header, and the comment is copied into every new app. An app that adds `os.drive.*` or `os.calendar.*` follows the comment and gets `403 user_context_required`. This is the stale-sentence pattern (cf. MAN-1899).
- Fix: SDK. Fix the docstring and give `call_capability(name, payload, user_context=None)` an optional header.

**H5 — `os.compliance.audit_query` is documented as app-scoped; it returns every app's rows in the tenant** — HIGH, CONFIRMED
- SDK `CR:673`: "scoped to the calling tenant + app". `SKILL.md:397`: "Read your own capability call audit log".
- Platform `caps/compliance.py:82-90` and `caps/audit.py:86-103`: the only scope is tenant RLS, and `app_filter` is optional and caller-supplied. The output also contains `app_id` (`audit.py:114`), which `CR:698-710` omits.
- Impact: an app shows tenant-wide data as "its own" audit log. The privacy property the doc promises does not exist.
- Fix: the platform fix is MAN-2253 (In Progress). Until it lands, the SDK should say the result is tenant-wide and that callers must pass `app_filter`.

**H6 — `os.drive.*` limits and behaviour are stale (MAN-1958/1959, 2026-09-01)** — HIGH, CONFIRMED
- SDK `CR:238-241`: "they get a notification … Limits: 5 MB; extensions `md txt csv json pdf png jpg jpeg webp`". `CR:251`: `os.drive.write` "create-only". No `os.drive.delete`.
- Platform:
  - `caps/drive.py:17-18`: "No notification: the user asked for the save inside the app."
  - `services/drive_publish.py:51` `PUBLISH_MAX_BYTES = 50 MB`.
  - The extension map `drive.py:66-94` adds gif, markdown, doc(x), xls(x), zip, rar, mp3, m4a, ogg/oga, wav and flac.
  - `os.drive.write` takes `file_id` + `if_match` to overwrite. The schema requires exactly one of `folder_id`/`file_id` (`:163-180`). It returns `{…, version_no, etag}` and `412 version_conflict {current_etag}` (`:740-783`).
  - `os.drive.stage` takes optional `size_hint` and `expires_in` (`:109-131`).
  - `os.drive.delete` exists (:785-832).
- Fix: SDK.

**H7 — `SKILL.md` says `os.tenant_config.get` reads "tenant feature flags"; CR says the opposite** — HIGH, CONFIRMED
- SDK `SKILL.md:388`: "Read tenant feature flags / config." `CR:103-126`: "Not `tenants.features` … DO NOT RELY ON THIS TODAY".
- Platform `caps/tenant_config.py:67-72` with `services/tenant_app_builder_config.py:68-79`: it reads only `prompt_extension`. CR is right and SKILL.md is stale.
- Fix: SDK. Fix the SKILL.md row.

**H8 — CR's "codegen auto-detector caveat" describes a bug fixed two months ago** — HIGH (stale fact), CONFIRMED
- SDK `CR:339-343`: "`os.calendar.*`, `os.drive.*` and `os.files.list` are absent from the capability auto-detector".
- Platform `services/app_builder_v2_capabilities.py:46-79`: all 32 names are present, pinned by a parity test (MAN-1445, 2026-08-02).
- Fix: SDK. Delete the caveat.

**H9 — `os.apps.bulk_export` input is wrong and the capability has no datasets** — HIGH, CONFIRMED
- SDK `CR:744-748`: input `{dataset_name, version: "1", args}`; size sentinel `{"_error": "size_limit"}`.
- Platform `caps/bulk_export.py:83-95`: `required: [target_app_id, dataset]`, optional `since/until/limit`, `additionalProperties: False`, so the documented body is a 422. The sentinel is `{"_error":"bulk_export_size_cap_exceeded"}` (:147-154). Nothing in `backend/app` registers a dataset (grep for `BulkExportRegistry.register` callers is empty), so every call is `404 target_app_not_found` (:128-129).
- Fix: SDK. Document the real input, or mark the capability as "no datasets exist yet". Platform: the sensitivity prefix misses it (MAN-1902).

### MEDIUM

**M1 — `check_app.py` ignores `optional_capabilities` and flags a correct app** — MEDIUM, CONFIRMED (reproduced)
- SDK `templates/check_app.py:470-474` reads only `requires_capabilities`.
- Platform: optional capabilities are granted at install (`services/v2_apps/deploy_pipeline.py:664-671`; schema `manifest_v2.schema.json:382` "Granted at install alongside the required set").
- Repro: in a copy of the starter, moving `os.kv.set` to `optional_capabilities` produces "calls os.kv.set but manifest.requires_capabilities does not declare it - … 403".
- Fix: SDK. Treat requires ∪ optional as declared, and run the "declared but not called" check over both.

**M2 — `check_app.py` cannot tell a real capability from a typo** — MEDIUM, CONFIRMED (reproduced)
- SDK: `check_app.py:65-68,461-499` derives names only by regex over quoted `"os.x.y"` strings and compares called against declared. It has no list of real names. `scripts/linter_mutations.py:106-107,221-222` mutates to the non-existent `os.kv.delete` and expects the message "capability_not_granted".
- Platform: the manifest schema accepts any string name (`manifest_v2.schema.json:358-378`). The gateway looks up the registry **before** the grant check and answers `404 capability_not_found` (`capability_gateway.py:751-754`).
- Repro: renaming `os.kv.set` to `os.kv.delete` in both the manifest and the code passes the capability rule.
- Fix: SDK. Embed the 32 names, with a warning rather than an error for unknown ones, and add a `version_check.py` / CI parity step against the registry grep. Fix the mutation's expected wording. This needs care: a hard-coded list is exactly what drifted in App Builder (MAN-1445).

**M3 — `os.events.emit` input** — MEDIUM, CONFIRMED
- SDK `CR:596`: "`payload` | yes — any JSON". `idempotency_key` is not mentioned.
- Platform `caps/events.py:43-50`: `payload: {"type":"object"}`, so a scalar or array is a 422. `idempotency_key` is optional, and a duplicate returns the existing `event_id` (:15-16). `event_name` is only checked for length 1–256; the `<group>.<verb>` form in CR is advice, not validation.
- Fix: SDK.

**M4 — `os.notifications.send_to_user` residuals after MAN-2516** — MEDIUM, CONFIRMED
- SDK `CR:521`: "in-app keeps the first 2000". `CR:559` documents `app_not_live` only as a `reason` of `in_app_unavailable`.
- Platform: `services/notification_service.py:49,233` `BODY_MAX = 4096`, and 4096 is what is stored. Email and SMS raise a separate `412 {"error":"app_not_live"}` (`caps/notifications.py:576-586`). SMS bodies are cut at 1600 (`:476`).
- Fix: SDK.

**M5 — The Quotas section misses every limit that actually rejects; the manifest's quota field is inert** — MEDIUM, CONFIRMED
- SDK `CR:752-756` talks only about `quota_exceeded`. `V2P:95` offers `quota_per_tenant_per_day` in the manifest.
- Platform: no registration sets a quota (grep), so `429 quota_exceeded` is unreachable (MAN-2569). Nothing reads the manifest field (no consumer outside registry/gateway).
- The 429s that do fire:

  | Code | Limit | Source |
  |---|---|---|
  | `upload_rate_limited` | 20/min, 200/h per app+tenant | `files.py:71` |
  | `publish_rate_limited` | 20/min, 200/h per user | `drive.py:97,341` |
  | `notification_rate_limited` | 10/h, 50/day | `notifications.py:261` |
  | `ai_spend_cap` | — | `ai.py:1124` |
- Fix: SDK. List the real limits and say the manifest quota is accepted and ignored.

**M6 — `os.http.fetch` probably cannot egress from a cross-tenant install** — MEDIUM, LIKELY (UNVERIFIABLE-WITHOUT-PROD)
- SDK `V2P:320-322`, `CR:604`: declared hosts are allowed. No tenant caveat.
- Platform `caps/http_fetch.py:192-203`: the allow-list query is `WHERE a.tenant_id = :tid`, with the **calling** tenant. The container of a cross-tenant install runs with `MANAURUM_TENANT_ID` = the installing tenant (`services/v2_apps/stack_generator.py:305`). The `v2_apps` row lives in the owner tenant (`caps/_ctx.py:33-37`: "a cross-tenant install's row lives in the OWNER tenant, invisible under RLS"). The result is an empty list and `412 egress_not_declared`.
- Fix: platform (resolve via the install row or the reader session, as `completion_context.installed_app_metadata` does). The SDK should note the limitation until then. No ticket found.

**M7 — `SKILL.md` troubleshooting gives the wrong status and code for egress** — MEDIUM, CONFIRMED
- SDK `SKILL.md:678`: "422 `egress_not_declared` | App tried `os.http.fetch` to a host not in …".
- Platform `http_fetch.py:260-263`: `412 egress_not_declared` means no hosts are declared at all. A host missing from the list is `412 host_not_in_allow_list`. CR has it right.
- Fix: SDK.

**M8 — The `permissions` enum misses `camera`** — MEDIUM, CONFIRMED
- SDK `V2P:104` and `skills/manaurum-setup/SKILL.md:175-176`: "Enum today: `["microphone"]`".
- Platform `manifest_v2.schema.json:320-327`: `["microphone","camera"]`. The shell maps camera (`frontend/src/components/window/iframeHostPolicy.ts:68`, MAN-1920).
- Fix: SDK.

### LOW

- **L1** `CR:192` says `os.files.download` gives "404 if not found". The handler only signs a URL and never checks existence (`files.py:397-420`), so a missing object surfaces as an R2 404 on the GET. `invalid_key_*` 400s (`_storage_keys.py:43-58`) are undocumented. CONFIRMED.
- **L2** `V2P:318` describes the dev-mode allow-list by naming groups that do not exist (`os.payments.*`, `os.cron.*`). The real list is `os.kv.* os.files.* os.tenant_config.* os.secrets.* os.compliance.audit_query` (`capability_gateway.py:97-108`). CONFIRMED.
- **L3** "Only dev-mode apps and active BYO hosts short-circuit" (`CR:58-60`, `V2P:109`) is incomplete: a caller whose app id resolves to no install falls through (`no_install`, `granted_capabilities.py:36-41,160-179`). That includes a **slug** header from a cross-tenant install, because `_resolve_app_uuid` looks up the slug only in the calling tenant (`:92-135`). The SDK tells developers to send the slug, so it steers cross-tenant apps into this hole. Platform ticket MAN-2199. The SDK should not promise more than the gate gives. CONFIRMED (code).
- **L4** The SDK never says which capabilities are "sensitive" or that strict grants are off by default (`sensitivity.py:278-285`, `config.py:483`). `CR:557` refers to "this **sensitive** capability" with no definition. MEDIUM-adjacent; platform misclassification of `os.apps.bulk_export` is MAN-1902.
- **L5** `skills/manaurum-setup/SKILL.md:389-392` says that with placeholder UUIDs "calls fail with `412 app_id_must_be_uuid`". A UUID cannot trigger that code. With no `MANAURUM_RUNTIME_TOKEN`/`MANAURUM_CORE_URL`, the starter raises its own `CapabilityError("capability env not fully injected …")` (`templates/v2-starter/src/capability.py:59-63`). CONFIRMED.
- **L6** `calendar.create_event` stores `source_app` = the raw `X-Manaurum-App-Id` (`caps/calendar.py:74,90,99`). The `source_ref` idempotency key is therefore per header form: switching between slug and UUID duplicates events. The SDK's slug rule makes the slug stable, so this is low risk; worth one sentence. CONFIRMED (code).

---

## 3. Gateway call contract — verified

`POST /api/capability/{name}` (`capability_gateway.py:591-604`). It requires a Bearer `mna_*` (`:612-626`; 401 `missing_authorization` / `invalid_credential`), `X-Manaurum-Tenant-Id` (UUID, which must equal the credential's tenant: 403 `tenant_mismatch`, `:748`) and `X-Manaurum-App-Id` (slug or UUID, scope-checked, `:729`). `X-Manaurum-User-Context` is optional and verified when present (`:656-685`). `X-Manaurum-Workspace-Id` is optional and read only for `os.ai.complete`/`providers` (`:600,852`). The body is JSON; an unparseable body becomes `{}` and is then schema-validated (`:767-772`). Success returns `{output, correlation_id}` (`:588`, `:1290`). Streaming returns NDJSON. BYO returns the raw proxied response with `X-Manaurum-Correlation-Id`. Gate order: auth → scope → tenant binding → registry (404) → auth_mode → schema (422) → dev allow-list → user-context app binding → grant (403) → quota → dispatch. CR's "grant runs ahead of quota, dispatch and audit" is correct.

The `os.http.fetch` 3.1.0 redirect fix is correct: `follow_redirects=False` (`http_fetch.py:326`), `Location` must be re-checked by the app, and egress is an exact host match (`:222-237`).

## 4. How `check_app.py` derives capability names

Nothing is hard-coded and nothing comes from a platform source. It regex-scans every source file for quoted `"os.<a>.<b>"` strings (`check_app.py:65-68`) and diffs them against `requires_capabilities` only (`:470-474`). So it is not "out of date" against the registry; it simply has no notion of the registry (M2), and it misreads `optional_capabilities` (M1). The regex `[a-z_]+` excludes digits, which registry names allow (`registry.py:28`), but no current name has a digit.

## 5. Questions (no evidence yet)

- Q1: Does the events dispatcher actually deliver `os.events.emit` events to a hosted v2 subscriber container? (Not traced; it belongs to the events dimension.)
- Q2: `os.tenant_config.get` does `getattr(config, key)` on a Pydantic model. A key such as `model_dump` returns a bound method, which probably becomes a 500 `handler_exception` (`tenant_config.py:72`). Harmless, but untested.
- Q3: Is `v2_strict_capability_grants` on in production? If it is, every capability under `os.ai.`/`os.http.`/`os.secrets.`/`os.notifications.`/`os.ocr.` is withheld at first home install. That changes the "deploy and it works" story the starter tells.

## Summary

Covered:
- All 32 registered capabilities: schemas, outputs and errors against CR, SKILL.md and V2P.
- The gateway contract, grants, dev-mode, sensitivity and quotas.
- `check_app.py` behaviour, reproduced twice; the starter's `capability.py`.
- Recent MAN tickets: 1707, 1971/2412, 2133, 2136, 2158, 2185, 2516, 1958/1959, 1445, 1585, 1289.

Top issues:
- Five capabilities are documented with wire contracts that 422 or crash on every call: OCR, files.upload, apps.call, ai.complete output, bulk_export.
- Six capabilities are undocumented.
- A stale "gateway rejects user_context" line ships in the starter template.

Not covered: drive event delivery and the `pickFromDrive` frontend path; BYO proxy signing; `_dispatch_streaming` internals; Gemini embedding model names; live production verification of M6 and Q3.

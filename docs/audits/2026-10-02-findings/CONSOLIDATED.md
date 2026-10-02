# Consolidated findings (deduplicated) — to be verified

Source detail with full citations: findings/{gateway,capabilities,manifest-deploy,window,staleness,tools-starter,security-consistency-ux}.md
(ids in brackets point there). SDK = C:\dev\wt\sdk-audit @6f52dce. Platform = SNAP @285c8a8.

## CRITICAL (app breaks or becomes insecure, deploy green)
C1 [GW-01, SEC-1, TS-01] Cross-app user_context replay: starter auth.py:43-83 never binds claims.app_id==APP_SLUG / tenant_id==MANAURUM_TENANT_ID (and accepts tokens missing those claims); one shared audience "manaurum-app" (user_context_jwt.py:70-71); gateway v2_app_gateway.py:561-572 does not strip inbound x-manaurum-user-context, adds minted one under different casing (:866,:912) so client copy reaches container first; anonymous routes pass client header alone; shared docker network (stack_generator.py:16-24). SDK claims header is "the only trustworthy caller identity" (main.py:28-29, SKILL.md:234, v2-platform.md:247).
C2 [cap C2, ST-09] os.files.upload: SDK example (capabilities-reference.md:166-184) omits required size_hint (files.py:95) -> 422 every call; limits 50MB/1GB/rate 20/min undocumented.
C3 [cap C1] os.ocr.extract: documented input {provider, object_key, schema} vs real {file_key, schema?} additionalProperties false (ocr.py:84-98); output/errors wrong.
C4 [cap C3] os.apps.call: documented body 422 (rpc.py:64-80: target_app_id, int version, timeout_ms); only 4 builtin targets; "RPC to another v2 app" (SKILL.md:398, v2-platform.md:98) false.
C5 [cap C4, ST-08] os.ai.complete: output has no `usage` (real {content,tokens_used,cost_usd,cost_known,provider,model}); top_p -> 422; provider/model optional; workspace context (X-Manaurum-Workspace-Id) + new errors (workspace_context_required, ai_disabled, ai_spend_cap, app_installation_required) undocumented; documented missing_provider_credentials/upstream_5xx don't exist.
C6 [H4, SEC-3, TS-04] Starter capability.py:76-77 + starter README.md:28-29: "gateway rejects user_context on this path" -> call_capability() can't forward it; gateway requires it for os.drive.*/os.calendar.* -> 403 user_context_required (capability_gateway.py:648-684,:763). SKILL.md:357/680, CR:62-65 say opposite.
C7 [SEC-6 + SEC-2/TS-02] Deploy token leak path: setup SKILL.md:71 tree and deploy SKILL.md:372-374 deploy.sh put .env.manaurum INSIDE app dir (SKILL.md:157,167 say one level up); CLI packager packaging.py:20-31 has no .env* exclusion; check_app.py:87 TOKEN_LITERAL requires 16 alnum after mna_ but real tokens are mna_<12hex>_<secret> (v2_credentials.py:408-411) so never matches; mutation linter_mutations.py:201 uses fake shape; platform credential_markers.py lacks mna_/mnu_.

## HIGH (wrong fact / security-relevant)
H1 [W-01, W-02, SEC-4, ST-14, W-14] Handshake trusts first sender: starter index.html:63-84, SKILL.md:310-325, sdk-api.md:99-104,127 accept manaurum:init from anyone; platform rule MAN-2506 (V2_DEVELOPER_GUIDE.md:1316-1333, CLI template SHELL_ORIGINS): only window.parent and manaurum.com/app.manaurum.com. manaurum-v2.mjs:235-250 same flaw (platform). Frame-ancestors *.manaurum.com lets other apps frame (LIKELY).
H2 [GW-02, F-02, ST-01, CON-1] "no readiness probe": deploy SKILL.md:193,196-197,464; app SKILL.md:654; publishing.md:42; README:212. Platform production.py:1050-1060, :3955-4008 (MAN-1369, default on). v2-platform.md:229 already right.
H3 [GW-03] "wrong port -> green deploy then 502" in ~12 places (SKILL.md:283,555,682; deploy:37,341; setup:152,237; check_app.py:14,333,347; README.md:36; starter README.md:88). Probe dials runtime port (production.py:1128-1137) -> deploy fails & rolls back. README:36 "Traefik targets app port" false (traefik_yaml.py:236-246).
H4 [GW-19, F-04, ST-02] "failed per-tenant migration still activates version": deploy:199-200,251-253,335; v2-platform.md:441,488. Platform MAN-2510 gate production.py:1090-1102,:3839-3904. Also v2-platform §5 order (migrations before swarm, deploy_pipeline.py:693-711).
H5 [F-03, ST-03] "only 3 things fail synchronously; manifest validated in job": deploy:178-189,324-334,344; SKILL.md:635; v2-platform.md:430; publishing.md:15,22-25. Platform dev_v2_deploy.py:808-890, owner_deploy.py:84-131: sync 422 manifest_validation_failed, 422 app_id_invalid, 413 archive_too_large, 409 slug_owned_by_another_tenant/version_already_published/slug_reserved, 403 runtime_credential_not_allowed, 403 app_id_out_of_scope (object with hint).
H6 [F-06, ST-04] v2-platform.md:445 "redeploying same version fine for dev iteration" -> 409 version_already_published (production.py:4159-4204), failed deploy burns label (:574-599); image path v2-app-<slug>-<tenant8> (v2-platform.md:437, SKILL.md:648, deploy:156 stale).
H7 [F-07, F-08, ST-05, SEC-9, cap H3] Token scope wildcard "*" / {"apps":["*"]} / cap 5 / "wildcard grants everything": v2-platform.md:109,361,387,398,401,421; deploy:330 "(or *)". Platform v2_credentials.py:74-104,233-382: 400 apps_required, 400 apps_wildcard_not_allowed, 403 apps_not_owned, scope_kind "owner" required for first deploy, cap 20, lifetimes 90/365d. No co-owner route.
H8 [W-04, GW-06, F-01, ST-06] v2-platform.md:24 "runtime ... not strict" (MAN-1899 sentence survived 3.1.0 which claimed fixing all five). schema :96 additionalProperties false.
H9 [W-05, F-05, ST-07, M8] permissions enum "["microphone"]" at SKILL.md:219, v2-platform.md:104, publishing.md:64, setup:175, sdk-api.md:51; schema :318-328 allows camera (MAN-1920); SKILL.md:733 says both. permissions[] + byo refused (MAN-1922) undocumented.
H10 [GW-04, SEC-8, TS-03, ST-10] "/agent/* reachable from public internet / Traefik straight to container": v2-platform.md:117,156,281; README:36,38; SKILL.md:554; check_app.py:16,277-291; starter agent_routes.py:19-22, README.md:115-119, tests/test_manifest.py:11-12, tests/test_routes.py:6-9,33. Platform v2_app_gateway.py:98,:786-797 -> 404 route_not_declared (MAN-1432, 2026-07-27). Keep JWT check (shared network).
H11 [GW-05] v2-platform.md:229 health_path "not reachable from outside" false (v2_app_gateway.py:817-863 proxies non-/api anonymously). Platform schema description same.
H12 [cap H1, ST-15] 6 registered capabilities undocumented: os.ai.providers, os.ai.image_submit, os.ai.image_poll, os.locations.list, os.locations.get, os.drive.delete; CR:3 "All 26" vs 32 registered.
H13 [cap H6, ST-12] os.drive.*: 5MB->50MB, extension list, no publish notification (MAN-2991), write overwrite file_id/if_match/412 version_conflict, delete exists.
H14 [cap H5] os.compliance.audit_query "scoped to tenant+app" (CR:673) — actually tenant-wide (platform fix MAN-2253).
H15 [cap H9] os.apps.bulk_export documented input 422; no dataset registered -> every call 404.
H16 [cap H2] os.ai.embed output shape (usage vs tokens_used/cost_usd).
H17 [W-07] design.md:330-333, app.css:26-27: tokens.css "dead hostname, missing 2 accents" fixed MAN-2367; "one <link> swap" false (--app-bg, --surface-input, --font-mono absent).
H18 [GW-14] sdk-api.md:228 app.fetch to external URL "subject to gateway egress rules" false (browser fetch). Same wrong comment in manaurum-v2.mjs:408-410.
H19 [SEC-7, F-13, ST-11] SKILL.md:713 egress allow-list "DROPs everything else" false; v2-platform.md:326 stale 0.0.0.0 blackhole (fixed MAN-2263). Container egress not enforced (stack_generator.py:350-373), only os.http.fetch enforces.
H20 [GW-07, TS-05, SEC-10] starter auth.py:31-34 "token carries no workspace_id" — gateway mints it (v2_app_gateway.py:904-911). Platform _manaurum_runtime.py:22-25 same stale.
H21 [TS-06] check_app route matcher accepts {param} and bare trailing * (check_app.py:210-235); gateway api_route_matcher.py:48-64 allows only trailing /* -> 404 in prod, linter green.
H22 [TS-07, cap M1/M2, F-15] check_app capability rule: FP on optional_capabilities (CA:469-474; platform grants required+optional deploy_pipeline.py:663-689), comments, README; FN on f-string URL form, typo'd name (no registry list; CLI vendors KNOWN_CAPABILITIES), test-only calls.
H23 [TS-08] check_app /agent auth rule is substring match (check_app.py:99-101,286): passes marker-in-comment and `UserContextClaims | None = None` w/o Depends; fails router-level dependencies=[Depends()].
H24 [TS-09] check_app route discovery misses include_router(prefix=), annotated router, add_api_route (check_app.py:142-153).
H25 [TS-12] check_ui appearance check (check_ui.py:334-336) passes when payload.appearance never applied; SKILL.md claims coverage.
H26 [F-20, ST-18] README.md:78,102-106 pins cli-v0.2.0, "no released wheel has new scaffold" — cli-v0.3.0 published 2026-09-03 (MAN-2301 Done); 0.2.0 rejects camera. open-claims MAN-1385 line vouches false sentence.
H27 [UX-1, UX-2, TS-18] Machine runs plugin 2.7.2 (v1 path, non-strict runtime, UUID for every capability, fixed /tmp/ctx.tar MAN-2456, no linters/hook). version_check.py:72-97 only compares sibling cache dirs; hooks.json:9 calls `python`.
H28 [F-12] v2-platform.md:308 runtime.entrypoint on hosted "ignored" -> 422 (schema allOf :17-41).
H29 [W-09, GW-13] SKILL.md:727 "rest of your CSP survives verbatim" — gateway rewrites script-src/frame-src, forces no-store (session_recovery.py).
H30 [M7, CON-3, F-22] wrong/nonexistent codes: SKILL.md:678 egress_not_declared 422 (real 412, http_fetch.py:261); SKILL.md:677 migration_validation_failed (doesn't exist); missing_provider_credentials, upstream_5xx (don't exist); deploy:329 401 missing_authorization (dev routes never return).
H31 [GW-18, CON-9] X-Manaurum-App-Id "always UUID" at SKILL.md:675,692; v2-platform.md:338,365; CR:20; setup:291 vs 3.1.0 slug rule (SKILL.md:356).
H32 [F-17, CON-4] Rollback: SKILL.md:665-666, v2-platform.md:458-462 "flips installed_version_id, no body" -> real re-points v2_apps.current_version_id, version_label required (dev_v2_deploy.py:764-765); rollback errors undocumented; rollback runs no probe/gate.
H33 [GW-09, cap M6] Cross-tenant install: gateway loader joins only home tenant install (gateway_production.py:107-126) -> user routes 404 for tenant-B users; os.http.fetch allow-list lookup filters on calling tenant -> 412. SDK promises "one deploy serves every tenant" (deploy:367, v2-platform.md:584, SKILL.md:216,691). Related MAN-2722.

## MEDIUM (gaps)
M1 [GW-10] gateway error table missing 404 app_not_found (3 causes), 503 app_disabled (kill switch), 400 path_traversal_rejected, 504 upstream_timeout; 30 s non-streaming timeout only in a code comment (v2-platform.md:604); agent dispatch 30 s.
M2 [GW-11] Cookie always stripped inbound -> cookie sessions/CSRF break silently; not stated.
M3 [GW-12] "every page is private" (v2-platform.md:223) — only top-level navigations redirect; fetch/iframe/curl get HTML (v2_app_gateway.py:127-145,830-863).
M4 [GW-13] Session renewal gaps (sdk-api.md:242-248): renewal-unavailable rejection, synthetic 401 for guest, onAuthFailure only for app.fetch, hidden /v2-session frame, no-store/ETag loss.
M5 [SEC-5, GW-08] Guest-pass pattern (v2-platform.md:251-260) lacks alg, constant-time compare, expiry/revocation, key provisioning via os.secrets; cross-tenant signed-in user gets 404 app_not_found not 401.
M6 [GW-15, ST-19] Runtime hardening MAN-2264 (read-only rootfs, uid 10001, /tmp tmpfs, HOME=/tmp/home, pids 512) undocumented (off by default; prod unknown).
M7 [W-03, TS-22] locale/dir in init + manaurum:locale-change (MAN-2289) undocumented; mjs drops; preview.py omits.
M8 [W-06] v2-platform.md:94 platforms.mobile.entrypoint used only for v1 manifests (IframeAppHost.tsx:176-191).
M9 [W-08] preview.py fake shell posts from 127.0.0.1 -> app following MAN-2506 origin rule reported "NO manaurum:ready".
M10 [W-15, W-17, TS-13] check_ui FPs: confirm rule flags ui.confirm(...) and prose; .style.* flags setProperty/width; drift vs platform ui_lint.py (vendored JS, entry_point != index.html, external-script handshake).
M11 [F-09] data.extensions (MAN-1960) absent; v2-platform.md:520 says extensions impossible.
M12 [F-10, F-19] Undocumented limits: 64 KB total of all migration files (deploy_pipeline.py:496-502), UTF-8, 30 s statement / 5 s lock timeouts; archive 88 MiB b64 / 64 MB expanded / 20 000 entries / gzip-or-tar.
M13 [F-11, ST-16, ST-17, TS-11] Slug rules (3-40, not UUID, reserved list MAN-2500), write-verb is_write:false refused (MAN-2358), root-key typos — neither documented (v2-platform.md:80, setup:144 "schema only enforces minLength") nor in check_app.
M14 [F-14, TS-10, TS-15] check_app fallback migration rules miss BEGIN/COMMIT, SET, CREATE EXTENSION, COPY, DROP INDEX/VIEW, RENAME, uppercase .SQL; wrong consequence text for non-.sql (fails deploy) and CONCURRENTLY mixing (deploys green, fails per tenant).
M15 [F-16, ST-22] Install fan-out MAN-2693 (team tenant -> every workspace desktop; public -> owners only) vs "auto-installed implicitly" (v2-platform.md:629); App Store v2 "pending" stale.
M16 [F-18, ST-23] Deploy job result: missing version, image_digest, per_tenant_status, ui_warnings, log_kind/log_tail; phase list.
M17 [cap M3, M4, M5] os.events payload must be object, idempotency_key; notifications 4096 not 2000, 412 app_not_live, SMS 1600, 7-day expiry; quotas: real 429s upload_rate_limited/publish_rate_limited/notification_rate_limited/ai_spend_cap; quota_per_tenant_per_day ignored.
M18 [TS-17] starter capability.py:18 15 s timeout vs os.ai.complete 180 s / http.fetch 30 s.
M19 [TS-16] conftest.py:89 mints UUID app_id; platform mints slug.
M20 [TS-19] check_repo.py reads only README + skills/**/*.md; RUNTIME_KEYS not pinned to schema.
M21 [W-18] offline_token passed into every app iframe (platform, LIKELY).
M22 [cap L2-L4] sensitive-capability list not documented; dev-mode allow-list groups nonexistent; grant check skipped with no install row (MAN-2199).

## LOW
L1 [TS-20] ~20 linter rules without mutation. L2 [W-10] accent `verdant`. L3 [W-11] sdk-api exports (findClippedContent, layoutCheck) and stale IframeAppHost line refs. L4 [W-13] deepLink sources. L5 [GW-16] runtime token 365 d. L6 [GW-17] drifted platform file:line pointers. L7 [CON-14, ST-24] setup "19 passed" vs 38. L8 [CON-10..13,16,17] DATABASE_URL when, dev editor, packager excludes 3 lists, .dockerignore protection, dokploy-network. L9 [F-21] .dockerignore can't keep secret out of source retention. L10 [F-22] logs "stub" is real tail. L11 broken anchors SKILL.md:253 "§ Manifest reference", deploy:260. L12 [UX-3, UX-4] skill overlap/context cost (~13k tokens SKILL.md). L13 [ST-20] /__manaurum/ reserved. L14 [ST-25] shell at app.manaurum.com. L15 CHANGELOG heading levels mixed (# vs ##). L16 [W-12] session-request logged as ignored (platform). L17 [TS-21] starter README migrate_command, requirements "pins match platform", health_path not declared.

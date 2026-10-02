# Dimension: tools-starter

SDK = `C:\dev\wt\sdk-audit` @6f52dce (3.1.0). Platform = SNAP @285c8a8.
Reproductions live in `<scratchpad>\tooltest\`. Each one copies the starter, applies one change and runs the real tool:
- `harness_app.py`: check_app.py, 33 cases
- `harness_ui.py`: check_ui.py, plus the platform's own `ui_lint.lint_sources` loaded from SNAP for comparison
- `jwt_compat.py`: tokens minted by the platform's `mint_user_context`, verified by the starter's verifier
- `dup_header.py`: how the gateway's header forwarding behaves

Re-run any of them with `C:\dev\wt\.venv-audit\Scripts\python.exe <file> [CASE]`.

---

## Findings

### TS-01 CRITICAL: a user-context token minted for another app is accepted by the starter, and the gateway forwards a client-supplied one ahead of its own
- **SDK:** the starter checks only `iss`, `aud`, `exp` and the signature. It never binds `app_id` or `tenant_id` to the container's own, and it defaults missing claims to `""`. See `templates/v2-starter/src/auth.py:43-83` and `:80` (`tenant_id=str(claims.get("tenant_id", ""))`).
- **Platform, part 1 (gateway forwarding):**
  - `backend/app/routes/v2_app_gateway.py:562-572 @285c8a8`: `_filter_request_headers` drops only hop-by-hop headers, `authorization` and `cookie`. An inbound `x-manaurum-user-context` is forwarded.
  - `:866`: `forwarded_headers = _filter_request_headers(dict(request.headers))`. Starlette lower-cases these keys.
  - `:912`: `forwarded_headers["X-Manaurum-User-Context"] = token` adds the minted token under a different-case key, so both headers go to the container.
  - On non-`/api` paths and `anonymous` routes the client's header is forwarded and nothing is minted (`:798-864`).
- **Platform, part 2 (what the token says):**
  - Every token has the same `aud` "manaurum-app" (`user_context_jwt.py:71`). It carries `app_id`=slug and `tenant_id` (`v2_app_gateway.py:904-911`).
  - The platform's own verifier requires those claims (`user_context_jwt.py:192-197`). The starter's does not.
- **Proof:**
  - `dup_header.py` sends the gateway's exact header dict through httpx into a Starlette app. `request.headers.get("X-Manaurum-User-Context")` returns `TOKEN_SUPPLIED_BY_CLIENT`; `getlist` returns `[client, minted]`.
  - `jwt_compat.py`: the starter accepts a platform-minted token whose `app_id` is `some-other-app` and whose tenant is a different UUID.
  - It also accepts a token with no `tenant_id`, `app_id` or `app_version`; the platform verifier rejects that one.
- **Verdict:**
  - The header precedence is CONFIRMED locally (same Starlette and httpx code paths).
  - The production hop (uvicorn behind Core) is LIKELY, not run against prod.
- **Who can exploit it:** the author of any v2 app receives Core-signed tokens for its users. Within the 60-second TTL they can replay one against another app's container:
  - in the `X-Manaurum-User-Context` header of a request to that app's public host;
  - or on any route that uses `auth_claims` off `/api`.

  The starter's verifier accepts the replayed identity.
- **Impact:** cross-app impersonation with a green deploy.
- **Fix:**
  - Platform: drop every inbound `x-manaurum-*` header in `_filter_request_headers`.
  - SDK: in the starter's verifier, require all four claims and check `claims.app_id == APP_SLUG` and `claims.tenant_id == MANAURUM_TENANT_ID`; add a test for each.
- **Related:** MAN-1588, the same class of problem (identity taken from a header). A Linear search for "X-Manaurum-User-Context" found no existing ticket.

### TS-02 HIGH: check_app's baked-token rule cannot match a real `mna_` or `mnu_` token
- **SDK:**
  - `templates/check_app.py:87` uses `TOKEN_LITERAL = re.compile(r"\bmn[au]_[A-Za-z0-9]{16,}")`, which needs 16 alphanumerics straight after the prefix.
  - The mutation that tests it uses an invented token shape, `mna_9f3c1de77a04b26e5c81` (`scripts/linter_mutations.py:201`).
- **Platform:**
  - A real `mna_` token is `mna_<12 hex>_<token_urlsafe>`: `routes/developer/v2_credentials.py:408-410 @285c8a8` and `services/v2_apps/runtime_credentials.py:109-110,183`. The `_` after 12 characters breaks the run.
  - A real `mnu_` token is `mnu_<env>_<32>` (`auth/token_kinds.py:5`).
  - The build-context scanner's credential list has no `mna_` or `mnu_` entry (`services/credential_markers.py`), so nothing else catches it either.
- **Proof:** generated real-format tokens print `NOT matched` for both kinds. Harness case `R_token_with_dash` is clean.
- **Verdict:** CONFIRMED.
- **Impact:** SKILL.md Step 3.6 promises this check ("an `mna_*`/`mnu_*` token literal anywhere"). It never fires on a real token, so a baked deploy token ships with no layer catching it.
- **Fix (SDK):**
  - Use `\bmn[au]_[0-9a-f]{12}_[A-Za-z0-9_-]{20,}` and `\bmnu_[a-z]+_[A-Za-z0-9]{24,}`.
  - Change the mutation to the real shape.
- **Fix (platform):** add `mna_` and `mnu_` to `CREDENTIAL_SUBSTRINGS`.

### TS-03 HIGH: stale fact, repeated in at least 10 places, that `/agent/*` on the public host goes "Traefik straight to the container"
- **SDK:**
  - `templates/check_app.py:16, :277-279, :289-291`: "this path is on the public internet with no gateway in front of it".
  - `README.md:38`.
  - `skills/manaurum-app/references/v2-platform.md:117`: "Verified 2026-07-26 … answered by the container".
  - `skills/manaurum-app/SKILL.md:554`.
  - `templates/v2-starter/src/agent_routes.py:20`.
  - `templates/v2-starter/README.md:115-118`.
  - `templates/v2-starter/tests/test_routes.py:8-9, :33`.
  - `templates/v2-starter/tests/test_manifest.py:11-12`.
- **Platform:**
  - `services/v2_apps/traefik_yaml.py:240-246 @285c8a8`: the app host forwards to the Core backend, not to the container.
  - `routes/v2_app_gateway.py:98`: `_RESERVED_PREFIXES = ("/agent/",)`, refused outright; the case-folded and double-slash spellings are refused too (`:104-124`).
  - This landed in commit 821af49e0 on 2026-07-27 (MAN-1432), one day after the SDK's "verified" date.
- **Verdict:** CONFIRMED.
- **Impact:** the threat model the SDK teaches is wrong. The advice is still good: keep verifying the JWT as defence in depth, because self-hosted or BYO routing may differ. But "the only thing standing between a stranger and your handler" is false, and the check_app finding's wording is false.
- **Fix (SDK):** rewrite all of these to say the gateway refuses `/agent/*` (MAN-1432), and that the in-container check is still required because the agent runtime reaches the container over the internal network and a BYO deployment may route differently.

### TS-04 HIGH: the starter's capability client says the gateway rejects a forwarded user context; it has accepted one since 2026-06-10
- **SDK:**
  - `templates/v2-starter/src/capability.py:76-77`: "Do NOT forward the user_context header here — the gateway rejects it on this path."
  - This contradicts the SDK itself: `skills/manaurum-app/SKILL.md:361, :399-400` and `references/capabilities-reference.md:269` say `os.drive.*` and `os.calendar.*` MUST forward it.
- **Platform:**
  - `routes/capability_gateway.py:648-682 @285c8a8` verifies `X-Manaurum-User-Context` and checks the tenant (MAN-609, commit 463b8d0bd, 2026-06-10).
  - `:763` answers `403 user_context_required` for user-scoped capabilities that arrive without it.
- **Verdict:** CONFIRMED.
- **Impact:** an app grown from the starter's single `call_capability` path cannot use Drive or Calendar, and the comment tells the developer not to fix it.
- **Fix (SDK):** let `call_capability` take an optional `user_context`, forward it when present, and fix the comment.

### TS-05 HIGH: the starter says the token has no `workspace_id`; it has one
- **SDK:** `templates/v2-starter/src/auth.py:33` says "``workspace_id`` — the token does not carry one, so do not key your data on a workspace". This contradicts `references/v2-platform.md:262`, which lists `workspace_id`.
- **Platform:** the claim is minted in `routes/v2_app_gateway.py:910 @285c8a8` and `agent/v2_capability_dispatch.py:139`. It came in with commit a5bd7c484 on 2026-09-07 (MAN-2412).
- **Verdict:** CONFIRMED.
- **Impact:** a developer is told a fact that is false. The starter's `UserContextClaims` also drops the claim.
- **Fix (SDK):** expose `workspace_id: str | None` in the starter's claims and correct the sentence.

### TS-06 HIGH: check_app passes declared rules the gateway can never match
- **SDK:**
  - `templates/check_app.py:210-235`: `covered_by` normalises `{param}` in both the handler and the rule. Any rule ending in `*` counts as a prefix glob (`:230-232`).
  - The starter's own test `_covers` (`tests/test_manifest.py:37-42`) implements the gateway's semantics correctly, so the SDK carries two copies of the rule that disagree.
- **Platform:** `services/v2_apps/api_route_matcher.py:48-64 @285c8a8`. Only a trailing `/*` is a wildcard; everything else is an exact literal match. The CLI already refuses both shapes (`manaurum-cli-py/manaurum_cli/project_checks.py` `check_route_globs`, `_is_dead_rule`).
- **Proof:** `A_param_rule` (rule `/api/items/{item_id}`) and `B_star_no_slash` (rule `/api/items*`) are both clean in check_app and both 404 at the gateway. `C_mid_star` is caught, but reported as "nothing serves it" rather than "dead rule".
- **Verdict:** CONFIRMED.
- **Impact:** the linter goes green and the deploy goes green, then every request on that route gets a 404.
- **Fix (SDK):** use the matcher's exact semantics, port the CLI's dead-rule check, and apply it to `public_paths` too. Add mutations A and B.

### TS-07 HIGH: check_app's capability rule has both false positives and false negatives
- **SDK:** the rule is a quoted-string regex, `templates/check_app.py:68`. It reads only `requires_capabilities` (`:470-474`) and scans every file, including tests, README and comments (`:477-487`).
- **Platform:**
  - Optional capabilities are granted at install: `services/app_store_v2.py:289-310 @285c8a8` uses required ∪ optional.
  - An unknown name gets `404 capability_not_found` (`routes/capability_gateway.py:754`).
  - The registry has exactly 32 names (`services/capabilities/*.py`, `CapabilityDefinition(name=…)`). The CLI vendors that list as `KNOWN_CAPABILITIES` and also matches the URL form of a call (`project_checks.py` `_CAPABILITY_PATTERNS`).
- **Proof:**

  | Case | Kind | What happens |
  |---|---|---|
  | `D_optional_capability` | false positive | Flagged as "not declared" |
  | `K_capability_in_comment` | false positive | Flagged |
  | `K2_capability_in_readme` | false positive | Flagged |
  | `K3_url_form_capability_call` (`f"{base}/api/capability/os.ai.complete"`, the shape behind the shift-checklist outage) | false negative | Clean |
  | `J_capability_typo` (`os.kv.gett` declared and called) | false negative | Clean |
  | `K4_capability_only_in_tests` (the app stops calling `os.kv.set`, only a test names it) | false negative | Clean; the over-broad grant is not reported |

- **Verdict:** CONFIRMED.
- **Fix (SDK):**
  - Merge `optional_capabilities` into the declared set.
  - Skip the `tests/` directory, `*.md`, and comments and docstrings (`tokenize`).
  - Add the URL form.
  - Vendor the 32-name list, or import the CLI's when it is installed, and flag unknown names.

### TS-08 HIGH: the `/agent/*` verification rule is satisfied by any text match
- **SDK:** `templates/check_app.py:99-101, :286` checks whether a marker substring appears anywhere in the handler's source.
- **Platform:** the agent runtime POSTs to the container and expects it to verify (`agent/v2_capability_dispatch.py:142-149 @285c8a8`).
- **Proof:**

  | Case | Kind | What happens |
  |---|---|---|
  | `F_marker_in_comment` (`# TODO: add Depends(auth_claims) / user_context check`) | false negative | Clean |
  | `F2_annotation_only` (`claims: UserContextClaims \| None = None`, no `Depends`) | false negative | Clean, and the handler is open |
  | `E_router_level_dependency` (`APIRouter(prefix="/agent", dependencies=[Depends(auth_claims)])`, the idiomatic FastAPI form) | false positive | Flagged red |
  | `I_agent_capability_without_handler` (an `agent_capabilities` entry with no `/agent/<name>`) | false negative | Clean; the agent's tool call fails |
  | `T_agent_declared_no_mount` (router never passed to `include_router`) | false negative | Clean; every capability 404s |

  The starter's own `test_every_agent_capability_has_a_handler` catches I and T; the linter does not.
- **Verdict:** CONFIRMED.
- **Fix (SDK):**
  - Require an actual `Depends(<auth fn>)` in the handler's arguments or in the router's `dependencies=`, using the AST rather than a substring.
  - Cross-check `agent_capabilities[].name` against the discovered `/agent/*` routes.

### TS-09 HIGH: route discovery misreads common FastAPI layouts
- **SDK:**
  - `templates/check_app.py:142-153` reads only an `ast.Assign` prefix.
  - It ignores `include_router(..., prefix=)`, `AnnAssign` and `add_api_route`.
- **Platform:** the CLI handles these deliberately (`project_checks.py` `_assignments`, `_mounted_with_a_prefix`, `_routes_in_tree`), "a missed check, never a false one".
- **Proof:**

  | Case | Kind | What happens |
  |---|---|---|
  | `G_include_router_prefix` (correct manifest, router mounted with `prefix="/api/items"`) | false positive | Two false reds: "declares … and nothing serves it" |
  | `G2_include_router_prefix_undeclared` | false negative | Clean, though the gateway 404s |
  | `H_annotated_router` (`router: APIRouter = APIRouter(prefix="/api/tags")`, undeclared) | false negative | Clean |
  | `U_api_route_wrong_method_shape` (`app.add_api_route("/api/stats", …)`, undeclared) | false negative | Clean |
  | `AA_auth_route_outside_api` (`@app.get("/export.csv")` with `Depends(auth_claims)`) | false negative | Clean. The gateway mints nothing off `/api` (`v2_app_gateway.py:798-864`), so the route always 401s, or trusts a replayed header (TS-01) |

- **Verdict:** CONFIRMED.
- **Fix (SDK):**
  - Port the CLI's resolver: AnnAssign; mark a router mounted with a prefix as "unknown" instead of guessing.
  - Flag `auth_claims` used on a non-`/api`, non-`/agent` route.

### TS-10 MEDIUM: check_app's fallback migration rules miss most of what the deploy refuses, and its note implies otherwise
- **SDK:**
  - `templates/check_app.py:88-96` lists only DROP TABLE/SCHEMA/…, DROP COLUMN, TRUNCATE, ALTER COLUMN TYPE, DROP CONSTRAINT and DO.
  - `UNCHECKED_RULES` (`:557-562`) says only the "parse-tree" rules went unchecked.
  - `:601` uses `path.suffix.lower()`.
- **Platform:**
  - `services/migration_validator.py:49-69 @285c8a8` forbids BEGIN/COMMIT, SET, CREATE EXTENSION, COPY, roles and more.
  - `:572-579`: any DropStmt (DROP INDEX, DROP VIEW and so on), RENAME and REVOKE are destructive (`:548-556`).
  - Default-deny for unrecognised statements (`:588-596`).
  - `services/v2_apps/bundle_migrations.py:162-169` accepts only a case-sensitive `.sql`.
- **Proof:** these cases are all clean with no CLI installed:
  - `P_forbidden_sql` (BEGIN, SET search_path, CREATE EXTENSION, COMMIT)
  - `P2_destructive_not_in_list` (DROP INDEX, RENAME COLUMN, DROP VIEW)
  - `K5_upper_sql_suffix` (`0001_init.SQL`, which the deploy refuses)
  - `O_data_none_with_migrations` and `O2_managed_without_migrations`. The CLI's `check_storage_coherence` refuses both; check_app does not check this at all.
- **Verdict:** CONFIRMED (code paths; pglast was not installed, to avoid a download).
- **Fix (SDK):**
  - Add the text-decidable forbidden and destructive keywords.
  - Make the `.sql` check case-sensitive.
  - Port storage coherence.
  - Reword the note to "only a pattern list ran".

### TS-11 MEDIUM: manifest rules the deploy enforces that check_app does not mirror
- **SDK:** `check_manifest_shape` (`templates/check_app.py:364-404`) checks only the `runtime` keys. `RUNTIME_KEYS` (`:82-84`) is hardcoded and currently in sync: the 11 keys match `manifest_v2.schema.json:96-207 @285c8a8` exactly.
- **Platform:**
  - The root object is `additionalProperties:false` (`schema:15`).
  - `api_routes[].auth` is required (`:135-138`).
  - An agent description longer than 400 characters is refused (`:424`).
  - `health_path` is strict when declared (`:109`).
  - The `public_paths` gotcha: `/*` does not cover `/` (`:162`).
  - Write-verb names with `is_write:false` are refused (`services/manifest_v2_validator.py:143-239`).
  - Reserved slugs are refused (`:263-267`).
  - The slug regex is enforced only at the Traefik mint (`traefik_yaml.py:51`).
- **Proof:** all of these are clean:
  - `N_root_typo`
  - `N2_route_missing_auth`
  - `N3_write_verb_declared_read`
  - `N4_reserved_slug` (`app_id:"api"`)
  - `N5_bad_slug`
  - `N6_desc_too_long`
  - `L_health_path_unserved` (`health_path:"/health"`, no handler)
  - `M_public_paths_dead` (`["/*", "/share/{token}"]`)
- **Verdict:** CONFIRMED for the linter. The 422 comes from code reading, and N5's exact failure point is LIKELY.
- **Fix (SDK):**
  - When `manaurum_cli` is importable, run its schema and project validators (the same pattern as for migrations); otherwise print a note saying they were not run.
  - Always check that `health_path` is served, and check `public_paths` globs.

### TS-12 HIGH: check_ui's appearance rule passes even when the shell's appearance is never applied
- **SDK:**
  - `templates/check_ui.py:334-336` checks for the substring `data-appearance` or `dataset.appearance` anywhere in the page.
  - The starter's standalone fallback always contains it (`index.html` `applySystemAppearance`).
  - `SKILL.md:110-113` claims check_ui checks rule 2, and `tests/test_static.py:80-92` uses the same regex.
- **Proof:** `ZD_appearance_never_applied` changes `root.dataset.appearance = payload.appearance` to a dead variable. check_ui is clean, the platform's ui_lint is clean, and the full starter suite reports **38 passed** (`app/ZD_full`). That is exactly rule 2's failure: a light app in a dark desktop.
- **Verdict:** CONFIRMED.
- **Fix (SDK):** require a `payload.appearance` read that is assigned to `dataset.appearance`, or rely on preview.py's APPLIED badge in a test. Add the mutation.

### TS-13 MEDIUM: check_ui disagrees with the platform's ui_lint it claims to mirror, and has false positives on legitimate patterns
- **SDK:** `templates/check_ui.py:272-274, :317-320`.
- **Platform:** `services/v2_apps/ui_lint.py:11-14 @285c8a8`: "mirror templates/check_ui.py … Keep the two in step". It skips vendor/dist/build directories (`:42-44`) and generated files (`:97-111`), and uses `frontend.entry_point` (`:136`).
- **Proof:**

  | Case | check_ui | Platform ui_lint |
  |---|---|---|
  | `V_vendored_library` (`vendor/tinychart.umd.js`) | 3 false reds | clean |
  | `W_entry_point_not_index` (entry `/app.html`) | "index.html is missing" | clean |
  | `X_handshake_in_external_script` (handshake moved to `boot.js`) | false red | false red |
  | `Z_method_named_confirm` (`dialog.confirm(...)`) | false red | false red |
  | `Y_token_in_style_attr` (`style="border-color: var(--border-hairline)"`) | says "an inline colour cannot follow an appearance change", which is false for a token | same |
  | `Y2_css_custom_property_from_js` (`el.style.setProperty('--progress', …)`) | red | — |

- **Verdict:** CONFIRMED.
- **Fix (SDK):**
  - Read `frontend.entry_point` from `../manifest.json` when it is present.
  - Port `_looks_generated` and the skip list.
  - Look for the handshake in any script the entry page loads.
  - Match only `window.`, bare, or `globalThis.` modal calls.

### TS-14 MEDIUM: design.md "Never" rows are decidable from the text but unchecked, and SKILL overstates what is covered
- **SDK:**
  - `references/design.md:21-22`: no root clip; no `hue-rotate` or hot-linked webfont.
  - `SKILL.md:146-150` says these "need a window rather than a picture".
  - `SKILL.md:142-145` (rule 6) bans all inline `style=`, while check_ui allows non-colour `style=` by design (`check_ui.py:49-52`).
  - `SKILL.md:713-716` says five of the seven rules are "not a matter of remembering"; rule 2 is not covered (TS-12).
- **Proof:** `ZA_overflow_hidden_root` (`.app{height:100vh;overflow:hidden}`) and `ZB_hotlinked_font_and_hue_rotate` are clean in both linters.
- **Verdict:** CONFIRMED.
- **Fix (SDK):** add the root-clip check (reuse `root_hooks`/`css_rules`), `hue-rotate`, and `fonts.googleapis.com`/`@import url(http`. Align rule 6's wording with what is enforced.

### TS-15 MEDIUM: the SDK states the wrong consequences for two migration mistakes
- **SDK:**
  - `templates/check_app.py:602-604` and `SKILL.md:559` say a non-`.sql` file in `migrations/` "silently never run[s]".
  - `templates/check_app.py:502` and `scripts/linter_mutations.py:142` say the deploy refuses a file that mixes CONCURRENTLY with other statements.
- **Platform:**
  - `bundle_migrations.py:159-169 @285c8a8`: "A README in migrations/ is a deploy error, not a silent ignore". The starter's `README.md:150` gets this right.
  - `deploy_pipeline.py:507-520` validates with `enforce_transactionality=False`. The deploy is green and the per-tenant runner refuses the file later.
- **Verdict:** CONFIRMED.
- **Impact:** for the CONCURRENTLY case, a developer expects a red deploy and gets a green deploy with migrations that fail per tenant.
- **Fix (SDK):** correct the wording in all four places.

### TS-16 MEDIUM: the starter's test JWT uses a UUID `app_id`; the platform mints the slug
- **SDK:** `templates/v2-starter/tests/conftest.py:89` sets `"app_id": "22222222-…"`. `test_agent.py:25` uses the slug, so the suite is internally inconsistent.
- **Platform:** `v2_app_gateway.py:908 @285c8a8` (`app_id=app_record.slug`) and `agent/v2_capability_dispatch.py:137` (`app_id=slug`).
- **Verdict:** CONFIRMED.
- **Impact:** a developer who adds the app-binding check that TS-01 needs, written against the test fixture (`== MANAURUM_APP_ID`), gets green tests and a 401 on every production request.
- **Fix (SDK):** mint `app_id="my-app"` (the slug) plus `workspace_id` and `jti`, exactly as `mint_user_context` does.
- **Positive result:** `jwt_compat.py` shows the starter verifies a token minted by the platform's real `mint_user_context` (RS256, iss/aud/exp). Algorithm confusion is blocked: jose refuses an HS256 token keyed with the public PEM. The crypto path is real, not mocked.

### TS-17 MEDIUM: the starter's single capability client times out before the gateway does
- **SDK:** `templates/v2-starter/src/capability.py:18` sets `httpx.Timeout(15.0, connect=5.0)` for every capability.
- **Platform:** `services/capabilities/ai.py:603 @285c8a8` (`_HTTP_TIMEOUT_S = 180.0`); `http_fetch.py:305-307` (`timeout_ms` up to 30000). The agent's dispatch budget is 30 s (`agent/v2_capability_dispatch.py:43`).
- **Verdict:** LIKELY (not timed live).
- **Impact:** an app grown from the starter that calls `os.ai.complete` or a slow `os.http.fetch` gets a 503 at 15 s while the gateway keeps working and charging quota.
- **Fix (SDK):** a per-capability timeout, at least 60 s for `os.ai.*` and `timeout_ms/1000+5` for `os.http.fetch`. Document it.

### TS-18 MEDIUM: version_check never compares against a real release
- **SDK:**
  - `scripts/version_check.py:84-97` compares the version only with sibling directories in the local plugin cache.
  - `hooks/hooks.json:9` invokes `python`, not `python3` or `py`.
- **Machine evidence:**
  - `~/.claude/plugins/cache/manaurum-sdk/manaurum-dev-sdk/` holds only `2.7.2`, which has no `hooks/` and no `scripts/`.
  - The hook has never run here, and if it did it would print nothing (no newer sibling) while 3.1.0 is released.
  - `python` resolves to Anaconda 3.9; on default macOS or Ubuntu there is no `python` and the hook fails silently.
- **Verdict:** CONFIRMED (design).
- **Fix (SDK):**
  - Compare against the marketplace's `plugin.json` version, cached once a day and silent on network failure, or at least against `marketplace.json`'s source.
  - Use `python3 … || python …`.

### TS-19 MEDIUM: check_repo cannot see the stale facts this audit found
- **SDK:**
  - `scripts/check_repo.py:48, :227-231`: live docs are `README.md` plus `skills/**/*.md` only.
  - Template docstrings are read only for headings (`:53-54`).
  - The starter's README, BRIEF, src and tests docstrings, which carry TS-03, TS-04 and TS-05, are not checked.
  - `PAIRED_CLAIMS` holds only 2 claims (`:176-189`).
  - Nothing pins `RUNTIME_KEYS` or `TOKEN_LITERAL` to a vendored copy of the schema or token format.
- **Verdict:** CONFIRMED.
- **Fix (SDK):**
  - Vendor `manifest_v2.schema.json` (as the CLI does) and assert `RUNTIME_KEYS == schema.runtime.properties`.
  - Add the starter's `*.md` files and Python docstrings to the live docs.
  - Turn "Traefik straight to the container" into a banned phrase (PAIRED_CLAIMS-style).

### TS-20 LOW: mutation coverage is missing for many linter rules
`scripts/linter_mutations.py:204-257, :338-353`.

**check_app rules with no mutation:**
- Python that does not parse (`check_app.py:194-198`)
- Dockerfile missing (`:337-340`)
- a directory inside `migrations/` (`:597-600`)
- a migration without a leading number (`:607-610`)
- duplicate migration numbers (`:651-655`)
- the validator refusing without a breakdown, or failing to parse (`:627-635`)
- `manifest.json` that does not parse (`:673-675`)
- the bare-`*` and `{param}` branches of `covered_by` (TS-06)

**check_ui rules with no mutation:**
- short hex
- `rgba()`
- colour in `style=`
- `.style.*` assignment
- `<button class="row">`
- a row missing `is-interactive`
- more than one primary button per view
- missing `data-appearance` (TS-12)
- missing `data-device`
- `payload` never read
- `index.html` missing
- an undeclared `var()` in `.html` or `.js` (only the CSS case is mutated)

**Mutations that use an unrealistic input:** the token mutation (TS-02).

### TS-21 LOW: smaller starter inaccuracies
- **`migrate_command` advice:**
  - `templates/v2-starter/README.md:151` tells the developer to "set `migrate_command` in the manifest".
  - `services/v2_apps/production.py:49-51 @285c8a8` says it is "reserved … not wired in this slice".
  - Fix: remove the advice.
- **`.dockerignore` header:**
  - `templates/v2-starter/.dockerignore:3` says "anything listed here never reaches the builder".
  - Its own note at `:26-29` says a platform deploy ignores the file.
  - `.env*` is still uploaded and retained by the platform (`manaurum_cli/packaging.py:20-31`).
  - Fix: reword the header.
- **Pins:**
  - `requirements.txt:10-15` claims the versions "match the platform's runtime base", but uses httpx 0.28.1 where the platform has 0.27.2 (`backend/requirements.txt @285c8a8`).
  - It leaves starlette and cryptography unpinned, while the platform pins them for CVEs (starlette 1.3.1, cryptography 50.0.0).
  - This contradicts its own "unpinned build is a different image every deploy" comment.
- **`health_path`:**
  - The starter serves `/healthz` but does not declare `health_path`.
  - Per `schema:109`, the post-deploy probe is then lenient: anything answering HTTP passes.
  - Declaring it makes a 5xx `/healthz` fail the deploy instead of going live.
- **A stale test docstring:**
  - `tests/test_routes.py:57-60` says "the fake_kv fixture … does the namespacing itself".
  - It does not (`conftest.py:120-126`).

### TS-22 LOW: preview.py differs from the shell in two ways
- It answers every `/api/*` without consulting `runtime.api_routes` (`templates/preview.py:340-372`), so an undeclared route photographs as working. Only a stderr log line hints at it.
- `build_init` (`:237-262`) omits `locale` and `dir`, which the shell sends (`frontend/src/components/window/IframeAppHost.tsx:313-314 @285c8a8`), so RTL and locale branches cannot be previewed.
- **Fix:** with `--manifest`, answer `404 route_not_declared` for undeclared paths; add `?locale=` and `?dir=`.

---

## Rule inventory

Each rule is listed with its platform mirror, whether its list is derived or hardcoded, and whether it has a mutation.

### check_app.py

| Rule | Platform mirror | List / sync | Mutation |
|---|---|---|---|
| routes declared/served | `api_route_matcher.py` | semantics diverge (TS-06) | yes (3) |
| `/agent/*` auth | `v2_capability_dispatch.py`, `v2_app_gateway.py:98` | marker list hardcoded (TS-08) | yes |
| `entry_point` exists | none (shell) | STATIC_ROOTS hardcoded | yes |
| port, CMD, EXPOSE | `stack_generator.py`, `v2_capability_dispatch.py:88` | default 80 is correct | yes (2) |
| `.env*` | `manaurum_cli/packaging.py:20` | accurate | yes |
| capabilities | `capability_gateway.py`, CLI `KNOWN_CAPABILITIES` | no list (TS-07) | yes (2) |
| migrations | `migration_validator.py`, `bundle_migrations.py` | hand-picked subset (TS-10) | 6 of 10 branches |
| runtime keys | `schema:96-207` | hardcoded, **in sync** (11/11) | yes |
| `/agent` in `api_routes` | `v2_app_gateway.py:98` | — | yes |
| relative icon | `routes/developer/__init__.py:187,500` | — | yes |
| TODO description | none (SDK policy) | — | yes |
| token literal | no platform mirror | wrong format (TS-02) | unrealistic |
| tests note | none | — | no |

### check_ui.py
Every pattern is hardcoded and matches `ui_lint.py` regex-for-regex where both have the rule.

- **check_ui only:** STYLE_PROP, ROW_INTERACTIVE, PRIMARY, `payload`, `uncentred_cap`, `@media` in `.css`, `var()` in `.css`.
- **Platform only:** generated-file and vendor skip, `entry_point`.
- Mutations are listed in TS-20.

---

## Questions (not findings: they need prod or an owner)
1. Is the base-image allow-list (`MANAURUM_V2_BUILD_ALLOWED_BASE_IMAGES`, `deploy_pipeline.py:355-384`) set to enforce on prod? If yes, nothing in the SDK or check_app tells developers which `FROM` images are allowed, and `python:3.12-slim` would need to be on the list.
2. Is runtime hardening (MAN-2264: read-only root fs, uid 10001) on for third-party apps? The starter is compatible: uid 10001 matches `HARDENED_UID`, and nothing writes outside `/tmp`. The SDK never mentions this constraint for apps that write to disk.
3. TS-01 production hop: does uvicorn behind Core in prod deliver both header copies in the same order? This is easy to confirm with one request against a staging app that echoes `getlist`.

## Noticed in passing (other dimensions; not re-verified in depth)
- **Egress enforcement:**
  - `SKILL.md:713` says `egress_allowed_hosts` "controls outbound; DROP everything else".
  - `services/v2_apps/stack_generator.py:31-33, :353-356 @285c8a8` says "nothing in this spec enforces it … undeclared egress is open" (MAN-185 is a TODO).
- **Hosts blackhole:**
  - `references/v2-platform.md:326` says the Hosts-blackhole bug is unresolved.
  - It was fixed by MAN-2263, commit 504ef87ad, 2026-09-02 (`stack_generator.py:350-356`).
- **Capability gateway app binding:** the gateway's user-context check binds the tenant but not `user_claims.app_id` to `X-Manaurum-App-Id` (`capability_gateway.py:673-682`). This is a platform note related to MAN-1588.

---

## Summary
- **Covered:** every rule in check_app.py and check_ui.py was mapped to its platform source and probed with 33 constructed app cases and 11 UI cases. check_repo, version_check, hooks, preview and smoke_tools were reviewed. The starter was checked for its auth, capability client, agent routes, Dockerfile, pins and tests, including real platform-minted JWTs and a header-forwarding proof.
- **Most important:**
  - The starter trusts any app's user context, and the gateway forwards a client-supplied one ahead of its own (TS-01).
  - The token-literal rule never fires on a real token (TS-02).
  - "`/agent` is Traefik straight to the container" has been false since 2026-07-27 and appears in at least 10 places (TS-03).
  - Two more stale starter claims (TS-04, TS-05).
  - check_app's route, capability and agent rules have proven false positives and false negatives that the platform's own CLI already avoids.
- **Not done:**
  - The real pglast validator was not run (no download).
  - Nothing was tested against prod or staging.
  - smoke_tools.py was not re-run (the orchestrator ran it clean).
  - design.md was not compared token by token against app.css.

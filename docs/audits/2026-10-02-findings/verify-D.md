# Verifier D: re-check of reworded rows + spot-check

SDK @6f52dce (`C:\dev\wt\sdk-audit`), platform @285c8a8 (SNAP). Read-only.

## Reworded rows

**К1: CONFIRM.**
- `ST/src/auth.py:43-83` checks signature, iss, aud and exp. It reads `tenant_id` and `app_id` with `claims.get(..., "")` and never compares them, so a token without these claims also passes.
- `main.py:28-29` contains "the only trustworthy caller identity". The line numbers are exact.
- `V2P:247` is accurate. `SKILL:235` is the `anonymous` bullet ("proxied with no user context"), which is relevant; `234-235` would be a slightly better citation (optional).
- Platform:
  - `routes/v2_app_gateway.py:561`: `_USER_AUTH_HEADERS = {"authorization","cookie"}`.
  - `:564-573`: the filter.
  - `:866`: `_filter_request_headers(dict(request.headers))`. Starlette keys are lowercase, so the client's `x-manaurum-user-context` survives.
  - `:912`: `forwarded_headers["X-Manaurum-User-Context"] = token` is a different-case key, so both copies are sent. The minted one is only added under `auth_mode == "user"` (`:885`).
  - `user_context_jwt.py:71`: `_AUDIENCE = "manaurum-app"`.
  - `stack_generator.py:17-24`: one shared app network.
- Re-reproduced: `httpx.Headers({'x-manaurum-user-context':'client','X-Manaurum-User-Context':'minted'})`, then Starlette `Headers.get` returns `client`.

**В1: CONFIRM.**
- `ST/src/capability.py:76-77` says "Do NOT forward the user_context header here — the gateway rejects it on this path". `call_capability(name, payload)` has no parameter for it.
- Platform:
  - `routes/capability_gateway.py:655-684` verifies the header and also returns 401 on a tenant mismatch.
  - `:761-764` returns `403 user_context_required` when `auth_mode=="user"`.
  - `auth_mode="user"` is set on all six `os.drive.*` (`services/capabilities/drive.py:841-895`) and both `os.calendar.*` (`calendar.py:121-134`).
- The contradiction is real: `SKILL:357` and `:680` and `CR:62-65` all say "forward it". `CR:65` even says "If you read anywhere that the gateway *rejects* … that statement is wrong."

**В2: NEEDS-REWORD (path only; the substance is confirmed).**
- Confirmed:
  - `SET:71` puts `.env.manaurum` inside the app tree.
  - `DEP:372-374` sources `./.env.manaurum` from the current directory.
  - `SKILL:157,167` and `DEP:319-320` say the file goes one level up.
  - `CA:87` is `\bmn[au]_[A-Za-z0-9]{16,}`. The real token is `mna_{token_hex(6)}_{token_urlsafe(24)}` (`routes/developer/v2_credentials.py:409-411`). Tested with a generated token: no match.
  - `linter_mutations.py:201` uses `mna_9f3c1de77a04b26e5c81`, a format that does not exist.
  - The CLI's `packaging.py:20-41` has no `.env*` exclusion.
  - `config.py:503-504` has `default="off"`.
  - `deploy.sh` excludes `.env*` (`DEP:87,400`).
- Wrong: the markers file is not under `v2_apps`.
- Fix: replace `services/v2_apps/credential_markers.py:14-25` with **`services/credential_markers.py:14-25`**. Trivial: `CA:444-457` → `CA:444-458`.

**В27: NEEDS-REWORD (path only; the substance is confirmed).**
- Confirmed:
  - `DEP:356` says "one deploy serves every tenant that installs the app".
  - `V2P:584` says "a separate Swarm service per (app, tenant)".
  - `SKILL:216` and `:691` are relevant.
  - `services/v2_apps/gateway_production.py:107-126` joins installs only `ON i.tenant_id = a.tenant_id`, so it can only find the home tenant's install.
  - `routes/v2_app_gateway.py:892-903`: the `tenant_verifier` returns 404 `app_not_found` for a user outside the home tenant.
- Wrong: `app_store_v2.py` is ambiguous because two such files exist. `routes/app_store_v2.py:319-372` is uninstall and list, not install. The right citation is **`services/app_store_v2.py:319-372`**: `install()` only inserts a row, with no container and no migrations. The route at `routes/app_store_v2.py:253,266` calls only this.
- Suggested wording: "…`services/app_store_v2.py:319-372` (установка только вставляет строку `v2_app_installs`)".

**С17: CONFIRM.**
- Without the CLI, the fallback (`CA:638-649`) catches only these:
  - `DO $$`;
  - DROP TABLE, SCHEMA, DATABASE, TYPE or SEQUENCE;
  - DROP COLUMN, TRUNCATE, ALTER COLUMN TYPE, DROP CONSTRAINT (`CA:88-96`).
- It misses BEGIN/COMMIT, SET, CREATE EXTENSION, COPY, DROP INDEX/VIEW and RENAME. All of these are refused by `services/migration_validator.py:49-69` (FORBIDDEN) and `:572-596` (DropStmt, RenameStmt, default-deny).
- The note at `CA:557-562` claims that only the index, SET NOT NULL and CONCURRENTLY rules went unchecked.
- `CA:601` uses `path.suffix.lower()`, so it accepts `.SQL`. The platform's `services/v2_apps/bundle_migrations.py:164` (`base.endswith(".sql")`) raises `BundleMigrationError`, and `production.py:3577,3634` show that this fails the deploy before the image push. So `CA:602-604` ("silently never run") is wrong. `SET:67` already says "fails the deploy".

**«Не находка, а предупреждение» (MAN-3183): CONFIRM.**
- `main.py:23` imports the router and `:1037` mounts it: `app.include_router(dev_v2_apps.router, prefix="/api/dev/v2", ...)`. There is no flag dependency at the router level: `routes/dev_v2_apps.py:81` has a plain `APIRouter(prefix="/dev-apps")`, and create and list use only `get_current_user`.
- `routes/capability_gateway.py:98-108` is `_DEV_MODE_ALLOW_LIST`.
- `:820-824` (the raise continues to `:830`) returns `403 capability_denied_in_dev_mode` when `is_dev_app`.
- `_is_dev_app_default` (`:116-149`) is a real `SELECT … FROM dev_apps`, not a stub.
- Linear:
  - MAN-3183 (Backlog) states "`/api/dev/v2/dev-apps/*` now answers 404 … `capability_denied_in_dev_mode` is gone". That is false at 285c8a8.
  - MAN-1423 is In Progress (updated 2026-09-30).
- Optional: the path should read `routes/capability_gateway.py`. С21 cites `:97-108`, and `:98-108` is exact.

## Spot-check of 8 citations elsewhere

| Row | Citation | Result |
|---|---|---|
| К2 | `services/capabilities/files.py:95-96` (`required` includes `size_hint`, `additionalProperties:false`), `:71` (20/60 s); `constants.py:139-140` (50 MB / 1 GB) | OK |
| В4 | `production.py:1050-1060` `_readiness_enabled()` default "1" | OK; also `DEP:193-196` says "no readiness probe anywhere" (OK) |
| В5 | `CA:14,333,347` text "green deploy, then 502" | OK |
| В8 | `V2P:437` (`v2-app-<slug>:<version>`), `:445` ("useful for dev iteration"), `SKILL:648`, `DEP:156` image_tag; `registry_client.py:133` `v2-app-{slug}-{tenant8}`; `production.py:4166-4204` (`version_already_published` at `:4203`) | OK |
| В10 | `V2P:24` "*not* strict"; schema `:96` `additionalProperties:false` under `runtime` (`:90`) | OK |
| В12 | `V2P:117` ("Traefik straight to your container"), `:156`, `:281` | OK |
| В16 | `frontend/public/sdk/manaurum-v2.mjs:406-409` egress comment | OK |
| В19 | `api_route_matcher.py:48-64` handles only a trailing `/*` and exact matches | OK |
| С1 | `main.py:316-349` registry imports and registration | OK |
| С7 | `SKILL:727` "rest of your CSP survives verbatim"; `session_recovery.py:30-32` rewrites script-src and frame-src | OK |
| **В25** | `SET:291` | **NEEDS-REWORD.** `SET:291` says "the UUID form — required by `os.kv.*` and `os.events.emit`". That matches the 3.1.0 rule, so it is not "always UUID". The other three are correct: `SKILL:692` ("Use as `X-Manaurum-App-Id`"), `V2P:338` (`<uuid>`) and `CR:20`. Wording: «“`X-Manaurum-App-Id` — всегда UUID” осталось в трёх местах (`SKILL:692`, `V2P:338`, `CR:20`)…» |

## Summary
- Of the 6 rows, 4 are CONFIRM (К1, В1, С17, MAN-3183) and 2 are NEEDS-REWORD for a wrong path only (В2: `services/credential_markers.py`; В27: `services/app_store_v2.py`). Nothing was refuted.
- The spot-check covered 11 rows: 10 accurate, and В25 over-counts by one (`SET:291` is correct).
- Not covered: the prod/edge behaviour (Traefik header stripping, prod flags).

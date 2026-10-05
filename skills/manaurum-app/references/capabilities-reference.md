# Capabilities — input/output reference

The exhaustive reference for every Platform v2 capability. All **34** capabilities
registered on Core's `main` at `7c1f09566` (2026-10-04) are documented below, all
`version: 1`. Every entry gives the input (from the capability's JSON Schema), the output on
success, and the errors that capability itself raises.

> **Production lags `main` here.** `os.ai.speak`, the voice-key funding of
> `os.ai.transcribe` (sergeysuaib-ui/manaurum#2382) and `os.directory.list_users` (#2112)
> merged in Core on 2026-10-04, and production had not deployed them that day, so it
> registered 32 capabilities. Until it does, `os.ai.speak` and `os.directory.list_users`
> answer `404 capability_not_found`, and `os.ai.transcribe` runs on the tenant's own OpenAI
> key only (`412 integration_not_configured` without one). The three sections below
> describe `main`, and each points back here. CLI 0.3.2 knows both new names: `manaurum
> app validate` refuses a call to one your manifest does not declare, as `check_app.py`
> does. 0.3.1 does not know them and says nothing.

| Family | Capabilities |
|---|---|
| Key/value, config, secrets | `os.kv.get`, `os.kv.set`, `os.tenant_config.get`, `os.secrets.get`, `os.secrets.set` |
| Your app's private files | `os.files.upload`, `.download`, `.delete`, `.list` |
| The user's Drive | `os.drive.stage`, `.publish`, `.list`, `.read`, `.write`, `.delete` |
| The user's calendar | `os.calendar.create_event`, `.list_events` |
| Locations | `os.locations.list`, `.get` |
| The team | `os.directory.list_users` |
| AI | `os.ai.complete`, `.embed`, `.transcribe`, `.speak`, `.image_submit`, `.image_poll`, `.providers`, `os.ocr.extract` |
| Messaging and events | `os.notifications.send_to_user`, `os.events.emit` |
| Outbound HTTP | `os.http.fetch` |
| Audit | `os.compliance.audit_query` |
| Other apps | `os.apps.call`, `os.apps.bulk_export` |

Nothing else exists: there is no `os.kv.delete` or `os.kv.list`, no `os.secrets.delete`,
no calendar update or delete, and no `os.workspace.members` (MAN-1289); the team's names
and addresses come from `os.directory.list_users`.

## The call contract

Your **container** makes the call, using credentials the platform injects for it:

```
POST ${MANAURUM_CORE_URL}/api/capability/<name>
Authorization: Bearer ${MANAURUM_RUNTIME_TOKEN}
X-Manaurum-Tenant-Id: ${MANAURUM_TENANT_ID}
X-Manaurum-App-Id:    <your slug, or MANAURUM_APP_ID for os.kv.* / os.events.emit>
X-Manaurum-User-Context: <the JWT your route received>   # required for auth_mode: user
X-Manaurum-Workspace-Id: <workspace uuid>                # os.ai.complete / .providers / .speak / .transcribe, rarely
Content-Type: application/json

<the capability's input object — no wrapper>
```

- `MANAURUM_CORE_URL` and `MANAURUM_RUNTIME_TOKEN` are **injected at deploy** by the
  platform. `MANAURUM_RUNTIME_TOKEN` *is* an `mna_*` token, but it is a per-(tenant, app)
  runtime credential minted fresh on every deploy — **not** your developer CLI token.
  Never bake an `mna_*` you created yourself into the image; that one is deploy-time only.
  In production `MANAURUM_CORE_URL` resolves to `https://manaurum.com`, but read the env
  var rather than hardcoding it.
- **App-id form matters, and nothing converts it.** The gateway hands
  `X-Manaurum-App-Id` to the handler exactly as sent, and each family keys its storage by
  one form. `os.kv.*` and `os.events.emit` key by the **UUID** (`MANAURUM_APP_ID`) and
  answer `412 app_id_must_be_uuid` to a slug. `os.secrets.*`, `os.files.*` (and therefore
  `os.ocr.extract`, which reads a file you stored) and the Drive staging key key by the
  string **as sent** — send the slug, your manifest's `app_id`. `os.drive.publish` and
  `.write` refuse a key staged under the other form (`403 staging_key_out_of_scope`). They accept a UUID too, which is
  the trap: the call succeeds against a namespace nothing else writes. `manaurum app
  set-secret` stores under the slug, so an app that sends the UUID reads every CLI-set
  secret as `404 secret_not_found`, and a file uploaded under one form is not found under
  the other. The rest resolve either form, but send one form everywhere. The env carries only the UUID, so keep the slug
  as a constant in your code; the starter's `src/capability.py` does, and its tests pin it
  to the manifest.
- **Forward the user context whenever you act for a user.** It is required for
  `auth_mode: "user"` capabilities (`os.drive.*`, `os.calendar.*`), it picks the workspace
  for `os.ai.complete`, and elsewhere it records who acted in the audit log. The gateway
  verifies it and refuses one minted for another app or tenant. The starter's
  `call_capability(..., user_context=claims.token)` sends it.
- **A body that is not valid JSON, or a request without `Content-Length`, is read as
  `{}`** and then validated, so a serialisation
  bug shows up as a schema error about a missing field, not as a parse error.
- **`"format"` is not enforced.** The validator ignores `date-time`, `uri` and the like, so
  a malformed date reaches the handler and usually comes back as `500 handler_exception`
  rather than `422`. Validate dates before you send them.

The same call from Node, inside your container:

```javascript
const CORE = process.env.MANAURUM_CORE_URL;

async function setKV(key, value) {
  const resp = await fetch(`${CORE}/api/capability/os.kv.set`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${process.env.MANAURUM_RUNTIME_TOKEN}`,
      'X-Manaurum-Tenant-Id': process.env.MANAURUM_TENANT_ID,
      'X-Manaurum-App-Id':    process.env.MANAURUM_APP_ID,   // the UUID: os.kv.* only
      'Content-Type':         'application/json',
    },
    body: JSON.stringify({ key, value }),
  });
  if (!resp.ok) throw new Error(`os.kv.set failed: ${resp.status}`);
  return resp.json();  // { output: { ok: true }, correlation_id: "…" }
}
```

**Success:** `{ "output": { … }, "correlation_id": "<uuid>" }` — read `output`.
`os.apps.bulk_export` streams `application/x-ndjson` instead, with no wrapper.

**Errors:** FastAPI's shape, `{ "detail": <string or object> }`. The code is `detail`
itself when it is a string, else `detail.error`. Both shapes occur, sometimes within one
capability, so handle both.

## Gates that run before your capability does

These fire in the gateway, in this order, before any handler code, so they apply to
**every** capability.

| HTTP | `detail` / `detail.error` | When |
|---|---|---|
| 401 | `missing_authorization` | No `Authorization: Bearer …`. |
| 401 | `invalid_credential` | The bearer is not an `mna_*`. |
| 501 | `system_caller_not_implemented` | You sent `X-Manaurum-Caller-System`. Don't. |
| 401 | `invalid_credential` | The `mna_*` is unknown, revoked, expired or wrong. |
| 412 | `missing_tenant_id_header` | Tenant header absent. |
| 412 | `missing_app_id_header` | App-id header absent. |
| 412 | `malformed_tenant_id_header` | Tenant header not a UUID. |
| 503 | `user_context_unavailable` | You sent a user context and Core cannot verify it right now (fails closed). |
| 401 | `invalid_user_context` (+ `message`) | The user context is invalid or expired (60 s), lacks a required claim, or names another tenant (`"user_context tenant mismatch"`). |
| 403 | `owner_scoped_credential_not_accepted` | The bearer is an owner-scoped developer token. Containers use `MANAURUM_RUNTIME_TOKEN`. |
| 403 | `app_id_out_of_scope` | `X-Manaurum-App-Id` is not an app this credential covers. |
| 403 | `tenant_mismatch` | `X-Manaurum-Tenant-Id` is not the credential's tenant. |
| 404 | `capability_not_found` | No such capability (a typo). |
| 403 | `user_context_required` | `auth_mode: "user"` capability and no user context. |
| 422 | `input_schema_violation` (+ `message`, `path`) | The input fails the capability's schema. Every schema here is `additionalProperties: false`, so an unknown field is a `422`. |
| — | workspace errors, `ai_disabled` | `os.ai.complete` and `os.ai.providers`, see `os.ai.complete`; `os.ai.speak` and `os.ai.transcribe`, see `os.ai.transcribe`. |
| 401 | `invalid_user_context`, `"user_context app mismatch"` | The user context was minted for another app. |
| 403 | `capability_not_granted` | The install's `granted_capabilities` lack this capability. **An install with an empty grant list denies everything.** |
| 429 | `quota_exceeded` | Not reachable today: no capability declares a daily quota (see Quotas). |
| 500 | `handler_exception` | The handler crashed. Usually bad input the schema could not catch (a malformed date), or a provider failure in `os.ocr.extract` / the image capabilities. |

Grant enforcement applies whenever your app has an install row in the calling tenant,
which every deployed hosted app has in its own tenant. Active BYO hosts skip it (except
for `os.ai.complete` and `os.ai.providers`, which are still checked), and so, today, does
an app id with **no** install row there (MAN-2199): do not
read a successful call as proof of a grant. There is no
wildcard grant (MAN-1585): every capability has to be listed. A redeploy never widens an
existing install's grants, so a capability you add in a later version is missing on old
installs until an admin grants it (MAN-1112).

**Sensitive capabilities.** `os.ai.*`, `os.ocr.*`, `os.notifications.*`,
`os.directory.*`, `os.http.*` and `os.secrets.*` are classed sensitive
(`backend/app/services/capabilities/sensitivity.py`). When the platform runs with strict
grants, these are not granted automatically at install; a tenant admin grants them
explicitly.

---

## `os.kv.set` — store a value

Per-app, per-tenant key/value in Postgres (FORCE-RLS by tenant). **App id: the UUID.**

**Input:**

```json
{ "key": "any-string-up-to-256", "value": <any JSON> }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `key` | string | yes | 1–256 chars. Treated opaquely. |
| `value` | any | yes | Stored as `jsonb`; overwrites. No size cap in the schema. |

**Output:** `{ "ok": true }`

**Errors:** `412 app_id_must_be_uuid` — you sent the slug.

---

## `os.kv.get` — read a value

**Input:** `{ "key": "..." }`

**Output:** `{ "value": <stored value, or null> }`

A missing key returns `value: null`, not 404. There is no list and no delete: keep an index
key yourself if you need to enumerate.

---

## `os.tenant_config.get` — read tenant config — ⚠️ DO NOT RELY ON THIS TODAY

**Input:** `{ "key": "some-key" }` (1–200 chars)

**Output:** `{ "value": <value, or null> }` — a missing key is `null`, never a 404.

**What it actually reads.** Not `tenants.features`, and not the `tenant_config` values a
tenant supplied at install (those land in `v2_app_installs.config`, which nothing under
`capabilities/` reads). The handler reads the tenant's `app_builder_config` and does a
plain attribute lookup on it. That model has **exactly one field — `prompt_extension`**.

Consequences, both of them surprising:

- **Any key other than `prompt_extension` returns `{"value": null}`.** Timezone, locale,
  branding, feature flags, your manifest's `tenant_config.schema` keys — all null.
- **`app_id` is ignored.** The lookup is per-tenant only, so two apps in the same tenant
  read the same value; you cannot scope config to your app.

Treat this capability as **unreliable until the read path is repointed**. If you need
per-tenant configuration today, keep it in your own schema and seed it from your app's
settings UI, or use `os.secrets.*` for credentials.

---

## `os.secrets.set` — store an encrypted secret

Encrypted at rest. Per-(app, tenant, name), where "app" is the `X-Manaurum-App-Id` value
as sent — send the slug, which is what `manaurum app set-secret` writes under.

**Input:**

```json
{ "name": "openai_api_key", "value": "sk-..." }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | 1–200 chars. |
| `value` | string | yes | No size cap. |

**Output:** `{ "ok": true }`

---

## `os.secrets.get` — read an encrypted secret

**Input:** `{ "name": "openai_api_key" }`

**Output:** `{ "value": "sk-..." }`, or `404 secret_not_found` when nothing is stored under
this (app, tenant, name) — which is also what a secret set under the other app-id form
looks like (see the call contract above). There is no list and no delete.

---

## `os.files.upload` — get a presigned PUT URL

Your app's **private** object storage: the user never sees these objects (for that, use
`os.drive.*`). The platform never proxies bytes — it returns a presigned URL your
container (or the browser) uploads to directly. **App id: the slug, as sent.**

**Input:**

```json
{ "key": "user-uploads/avatar.png", "content_type": "image/png", "size_hint": 20480 }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `key` | string | yes | 1–1024 chars, relative to your namespace. Stored as `app/<app id as sent>/<tenant_id>/<key>`, server-built. No leading `/`, no `\`, no `..` (`400 invalid_key_…`). |
| `content_type` | string | yes | 1–255 chars. The PUT must send the same `Content-Type`. |
| `size_hint` | integer | **yes** | 0–52428800. **Not a hint:** the exact byte length of the body you will PUT, signed into the URL (MAN-1707). A body of any other length is refused by the object store with an error that reads like a permissions problem. |
| `expires_in` | integer | no | 60–3600 seconds; default 300. |

**Omitting `size_hint` is `422 input_schema_violation`.** This page said otherwise until
3.3.0, and an app that followed it failed every upload.

**Output:**

```json
{ "upload_url": "https://…?X-Amz-…", "expires_at": 1735689600, "content_length": 20480 }
```

`PUT` the bytes to `upload_url` with the same `Content-Type` and exactly `content_length`
bytes.

**Limits and errors:**

| HTTP | `detail` | When |
|---|---|---|
| 400 | `invalid_key_empty_or_non_string` / `_leading_slash` / `_backslash` / `_parent_traversal` | Bad `key`. |
| 429 | `{"error":"upload_rate_limited","retry_after_seconds":60}` (+ `Retry-After`) | More than **20 URLs a minute or 200 an hour** for this (app, tenant). |
| 413 | `{"error":"namespace_quota_exceeded","used_bytes":…,"quota_bytes":…}` | Your (app, tenant) namespace would pass **1 GiB**. |
| 413 | `{"error":"namespace_scan_incomplete","max_objects":10000}` | More than 10,000 objects: the usage check cannot count them. Keep your own ledger at that size. |

Max **50 MiB** per object.

---

## `os.files.download` — get a presigned GET URL

**Input:** `{ "key": "user-uploads/avatar.png", "expires_in": 300 }` (`expires_in` optional, 60–3600)

**Output:** `{ "download_url": "...", "expires_at": <unix> }`

**It does not check that the object exists.** A URL is signed for any key; a missing
object shows up as an error from the object store when the URL is fetched. Errors: the
four `400 invalid_key_…`.

---

## `os.files.delete` — delete an object

**Input:** `{ "key": "user-uploads/avatar.png" }`

**Output:** `{ "ok": true }` — immediate, no trash.

---

## `os.files.list` — list your own objects

**Input:** `{ "prefix": "user-uploads/", "max_keys": 100, "cursor": null }` — all optional;
`max_keys` 1–1000, default 100.

**Output:** `{ "files": [{ "key", "size", "last_modified" }], "cursor": "<next page or null>" }`

Keys are app-relative (what you passed to upload).

---

## `os.drive.*` — the user's Drive (user context required)

The file system the USER owns and sees in the Files app. All six capabilities are
`auth_mode: "user"`: every call MUST forward the inbound `X-Manaurum-User-Context` JWT
(60 s TTL — forward immediately, never store), or it is `403 user_context_required`.
Declare each one you use in `requires_capabilities`. All but `os.drive.stage` answer
`412 user_has_no_workspace_in_tenant` when the user has no workspace here.

`os.files.*` is your app's PRIVATE scratch, which the user never sees. To put a document
into the USER's file system, read a user-picked file, or work in a folder the user granted
you, use these capabilities plus the browser-side `app.pickFromDrive()` picker — all
consent-gated, and all requiring the forwarded `X-Manaurum-User-Context`.

### `os.drive.stage` — presigned PUT to a user-scoped staging key

**Input:** `{ "content_type": "image/png", "size_hint": 20480, "expires_in": 600 }` —
`content_type` required; `size_hint` (0–50 MiB) optional but, when given, signed into the
URL like `os.files.upload`; `expires_in` 60–3600, default 300.

**Output:** `{ "staging_key", "upload_url", "expires_at" }`

The staging key is server-built and scoped to (your app, tenant, acting user) —
unaddressable by anyone else. PUT your bytes to `upload_url`, then publish or write. A
staged object nobody publishes is removed after 7 days.

### `os.drive.publish` — publish the staged artefact into the user's Drive

**Input:** `{ "staging_key": "...", "filename": "report.csv", "folder_name": "optional" }`
(`filename` 1–255 chars, no path; `folder_name` 1–100)

**Output:** `{ "file_id", "filename", "folder_id", "folder_name", "size_bytes" }`

The document becomes the user's OWN file, in a folder named after your app by default,
and your app keeps no residual access. **The user gets no notification** (MAN-2991): they
asked for the save inside your app, so tell them yourself.

Limits: **50 MiB**; extensions `md markdown txt csv json pdf png jpg jpeg webp gif doc docx
xls xlsx zip rar mp3 m4a ogg oga wav flac` (no svg, no html); the content is sniffed, so
a ".xlsx" that is not one is refused; **20 saves a minute and 200 an hour per user**,
shared with `os.drive.write`.

**Errors:** `403 staging_key_out_of_scope`, `422 filename_must_not_contain_path`,
`415 {"error":"file_type_not_publishable","allowed_extensions":[…]}`,
`429 publish_rate_limited`, `404 staging_object_not_found`, `413 artefact_too_large`,
`415 content_does_not_match_type`, `413 drive_quota_exceeded`.

### `os.drive.list` / `.read` / `.write` / `.delete` — granted folders

Standing access after the folder owner grants your app viewer or editor in Files → Share.
Effective access = the grant INTERSECTED with the acting user's own access; anything
outside it reads as 404.

- **`os.drive.list`** `{ "folder_id" }` → `{ folder: {folder_id, name}, folders: [{folder_id, name}], files: [{file_id, filename, mime_type, size_bytes, etag}] }`.
  At most 200 files per call, no paging. `404 folder_not_found`.
- **`os.drive.read`** `{ "file_id" }` → `{ file: {file_id, filename, mime_type, size_bytes, etag}, download_url, expires_at }`.
  The URL is signed for 5 minutes and downloads as an attachment.
  `404 file_not_found` / `folder_not_found`, `503 read_requires_object_storage`.
- **`os.drive.write`** `{ "staging_key", "filename", "folder_id" | "file_id", "if_match"? }` —
  exactly one of `folder_id` / `file_id`.
  - `folder_id` creates a new file → `{ file_id, filename, folder_id, size_bytes }`.
  - `file_id` (MAN-1958) replaces that file's content; the old content stays as a version
    the user can restore. The name and type cannot change
    (`415 overwrite_cannot_change_type`). Pass `if_match` with the `etag` you last saw to
    get `412 {"error":"version_conflict","current_etag":…}` instead of overwriting someone
    else's change. → `{ file_id, filename, folder_id, size_bytes, version_no, etag }`.
  - Needs an editor grant (`403 app_grant_is_viewer_only`) and the acting user must own
    the folder (`403 write_requires_folder_owner`). Same limits and errors as publish.
- **`os.drive.delete`** `{ "file_id" }` (MAN-1958) → `{ "deleted": true, "file_id", "filename" }`.
  A soft delete into the user's Trash, restorable for 30 days. Same grant rules as write.
  There is no hard delete.

### Drive events and the picker

- When a file changes in a folder granted to apps, the platform emits
  `drive.<slug>.file.created` / `.updated` / `.deleted` events to every app granted on it,
  whoever made the change. **A hosted app cannot
  receive events today** (see `os.events.emit`), so do not build on them.
- Frontend: `app.pickFromDrive({ accept: ['image/'] })` opens the OS picker; the user
  picks; you get a ~5-min signed URL for that one file. `sdk-api.md` covers it, including
  the sender check it depends on.

Full chapter: `docs/handoff/V2_DEVELOPER_GUIDE.md` ("Two storages", "Saving a
document into the user's Drive", "Working in a granted folder").

---

## `os.calendar.*` — the user's calendar (user context required)

Two capabilities over the OS calendar store — the same service the builtin Calendar UI
and the OS Assistant's agent tools write through, never a second copy. Both are
`auth_mode: "user"`: every call MUST forward the inbound `X-Manaurum-User-Context` JWT
(60 s TTL — forward immediately, never store), or you get `403 user_context_required`.
Declare each one you use in `requires_capabilities`. There is no update or delete.

Events are owned by the **acting user**, not by your app. The `X-Manaurum-App-Id` you send
is recorded, as sent, as the event's `source_app`, so send the same form every time.

### `os.calendar.create_event` — create (or idempotently upsert) an event

**Input:**

```json
{
  "title":       "Delivery window",
  "start_at":    "2026-07-24T09:00:00Z",
  "end_at":      "2026-07-24T11:00:00Z",
  "all_day":     false,
  "location":    "Warehouse 3",
  "description": "Pallets 41–48",
  "source_ref":  "order-8821"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | string | yes | |
| `start_at` | string | yes | ISO8601 date-time. `Z` is accepted. |
| `end_at` | string | yes | ISO8601 date-time. |
| `all_day` | boolean | optional | Default `false`. |
| `location` | string | optional | |
| `description` | string | optional | |
| `source_ref` | string | optional | **Your** id for the thing the event represents. |

**Output:** the created event —

```json
{
  "id": "<uuid>", "title": "Delivery window",
  "start_at": "2026-07-24T09:00:00+00:00", "end_at": "2026-07-24T11:00:00+00:00",
  "all_day": false, "location": "Warehouse 3",
  "source_app": "<your app>", "source_ref": "order-8821"
}
```

**Use `source_ref` for anything you may re-sync.** With it, the write is an idempotent
upsert keyed by `(user, source_app, source_ref)` — call it again with new times and the
same row is updated. Without it, every call creates a NEW event, so a retry duplicates.

### `os.calendar.list_events` — read the user's events

**Input:** `{ "start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z" }` — both
optional. Omitting a bound makes that side open-ended.

**Output:** `{ "events": [ <same shape as above>, … ] }`, ordered by `start_at`.

Three things to know before you build on it:

- **Overlap, not containment.** An event is returned when `start_at < end` AND
  `end_at > start`, so multi-day and in-progress events appear.
- **You see the user's WHOLE calendar**, not just events your app created. Filter on
  `source_app` yourself if you only want your own.
- **A recurring event comes back once**, as its master row, not once per occurrence.
  Cancelled events are left out, and `description` is not returned.
- **No pagination and no server-side cap.** An open-ended range returns every event the
  user has. Always pass a bounded `start`/`end`.

**Errors:** the gates above. A malformed date-time is **`500 handler_exception`**, not a
422 — validate your ISO8601 before sending.

---

## `os.locations.list` / `os.locations.get` — the tenant's places (MAN-2185)

Resolve a `location_id` the tenant uses elsewhere (a shop, a warehouse) to a name. Read-only,
`auth_mode: "app"`.

- **`os.locations.list`** `{ "kind": "sales_point" | "warehouse" }` (optional) →
  `{ "locations": [{ "id", "name", "kind" }], "count" }`. At most 500, no paging.
- **`os.locations.get`** `{ "location_id": "<uuid>" }` → `{ "id", "name", "kind" }`.
  `404 location_not_found` for one that does not exist **or** belongs to another tenant.

---

## `os.directory.list_users` — the people on the app's team (MAN-2519)

Fill an assignee or recipient picker, or show a name for a `sub` from the user context.
Read-only, `auth_mode: "app"`. Merged in Core on 2026-10-04 (sergeysuaib-ui/manaurum#2112);
production had not deployed it that day — until it does, the call is
`404 capability_not_found` (the note at the top of this page).

**Input:** `{}` — exactly that; any field is a `422 input_schema_violation`.

**Output:**

```json
{ "users": [ { "user_id": "…", "display_name": "Dana Levi", "email": "dana@example.com",
               "avatar_url": "https://…/api/profile/uploads/…" } ] }
```

- **Who is in it.** Each active, non-anonymous member once, even one who belongs to several
  workspaces, ordered by email address. In a team tenant that is everyone in the tenant. In
  the public tenant, where people do not know each other, it is only the workspace the
  forwarded `X-Manaurum-User-Context` was minted for (or, when the person can no longer
  reach that one, their primary workspace in the tenant), and only when one of the app's
  owners works in that workspace. An app-only call there (no user context), or a person
  from a workspace none of the app's owners is in, gets `{ "users": [] }`. So forward the
  user context when you call it on someone's behalf.
- **`display_name`** is the profile's full name, else a nickname the person changed from the
  default, else the part of the address before the `@`. It is never empty.
- **`avatar_url`** is present only when the person has one. A profile upload, which Core
  stores as a path, comes back prefixed with the OS origin (Core's `app_base_url`) rather
  than as a path that would resolve against your app's host; any other stored value comes
  back as stored.
- **No paging, no filter.** A team is small; filter in your container.
- **The tenant comes only from the verified gateway context.** No input names a tenant, so
  an app cannot list another one.
- **Sensitive** (`os.directory.*`). An App Store install has it only when the installer
  grants it. The home install gets it from the first deploy, unless the platform runs with
  strict grants, when an admin grants it. Without a grant: `403 capability_not_granted`.

---

## The AI family — what all eight share

`os.ai.complete`, `os.ai.embed`, `os.ai.transcribe`, `os.ai.speak`, `os.ai.image_submit`,
`os.ai.image_poll`, `os.ai.providers` and `os.ocr.extract`:

- **All are sensitive** (the `os.ai.` / `os.ocr.` prefixes). With strict grants switched on
  they are not seeded at install and a tenant admin has to grant them.
- **None has a daily quota**, so `429 quota_exceeded` cannot fire for them. The limit that
  does fire is the shared ManAurum AI spending limit (`429 ai_spend_cap`): on an unpinned
  `os.ai.complete`, and on `os.ai.speak` / `os.ai.transcribe` when Manaurum's voice key
  pays (below).
- **Errors come in two shapes.** Some `detail`s are a bare string
  (`"upstream_error:openai"`, `"audio_too_large"`, `"ai_provider_not_configured"`), some an
  object (`{"error": "…", …}`). Handle both.
- **A cost that cannot be priced is `null`**, never `0`; `cost_known` says which.
- **Upstream timeouts are long** (180 s for completion, embedding and OCR, 120 s for speech
  and transcription), but a request a browser makes to your app is cut at **30 s** by the
  gateway (`504 upstream_timeout`). A
  slow completion inside a browser-initiated `/api/*` call fails there first. Run it as a
  background job your page polls, or declare the route `"streaming": true` and stream (the
  30 s cut applies to buffered routes; streams have their own limits, `v2-platform.md`).

---

## `os.ai.complete` — text completion

**Which model answers depends on whether you name one.** Since MAN-2412:

- **Name neither `provider` nor `model` (the default, and the recommended call).** The OS
  uses the text backend Settings chose for **your app in this workspace**: the app's own
  assignment if it has one, else the workspace default profile, else the workspace's older
  agent configuration, else the company-funded
  "ManAurum AI" model (MAN-1971). It does **not** read the tenant's BYOK keys in Settings →
  Integrations. A workspace whose configured backend is broken fails closed
  (`412 ai_backend_unavailable`); it never falls through to another account.
- **Name `provider`.** The tenant's BYOK key for that provider (Settings → Integrations) is
  used, with `model` or that provider's default. Missing key: `412 integration_not_configured`.
- **Name only `model`.** The first configured BYOK provider (anthropic, openai, gemini,
  deepseek, groq, in that order, with keys whose last Settings test failed moved to the
  end) is used with your model.

Exactly one backend is tried. There is no fall-through to a second provider any more.

**Which workspace.** The completion is billed and governed per workspace. The gateway
picks it from the `workspace_id` in the `X-Manaurum-User-Context` you forward, or, without
one, from the workspaces your app is installed in. If that is more than one, send
`X-Manaurum-Workspace-Id`; otherwise you get `412 workspace_context_required`. Forwarding
the user context is the simple way to never think about this.

**Input:**

```json
{
  "messages": [
    { "role": "system", "content": "You are a helpful assistant." },
    { "role": "user",   "content": "Hello." }
  ],
  "temperature": 0.2,
  "max_tokens": 1024,
  "log_prompt": false
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `messages` | array | **yes** | ≥ 1 item; each `{role, content}` with `role` `system`/`user`/`assistant` and `content` a **string** (no multimodal parts, no tool calls). |
| `provider` | string | no | `anthropic`, `deepseek`, `gemini`, `groq`, `openai`. Pins BYOK — see above. |
| `model` | string | no | 1–256 chars. |
| `temperature` | number | no | 0–2. |
| `max_tokens` | integer | no | 1–200000. Omitted: the model's known output ceiling, else 4096. |
| `log_prompt` | boolean | no | Default `true`. `false` (MAN-2158) stores a length and a tenant-salted digest instead of the prompts and the answer; tokens, cost and attribution are recorded as usual. Use it for the user's private text. |

`additionalProperties: false`: **there is no passthrough** — `top_p`, `stop`, `tools` or any
other field is `422 input_schema_violation`.

**Output:**

```json
{
  "content": "Hi! How can I help?",
  "tokens_used": { "input": 22, "output": 8, "total": 30 },
  "cost_usd": 0.000041,
  "cost_known": true,
  "provider": "manaurum",
  "model": "<the model that answered>"
}
```

There is **no `usage` field** — code that reads `usage.input_tokens` raises on every
successful call. `provider` is the one actually used; an unpinned call can report
`manaurum`, `openrouter`, `custom` and others besides the five. An empty answer, or one whose
whole budget went to reasoning, is never returned as success.

**Errors** (beyond the gates at the top of this page):

| HTTP | `detail` | When |
|---|---|---|
| 403 | `{"error":"app_installation_required"}` | Your app has no single active install in this tenant. |
| 403 | `{"error":"workspace_context_mismatch"}` | The forwarded user context and `X-Manaurum-Workspace-Id` name different workspaces. |
| 400 | `{"error":"workspace_context_required"}` | `X-Manaurum-Workspace-Id` sent but blank. |
| 412 | `{"error":"workspace_context_required", …}` | More than one workspace qualifies and nothing chose one. |
| 403 | `{"error":"workspace_context_unavailable", …}` | No non-ephemeral workspace with your app installed (and, with user context, that the user belongs to). |
| 403 | `{"error":"ai_disabled", …}` | Text AI is switched off for your app in Settings. Applies to pinned calls too. |
| 412 | `{"error":"ai_backend_unavailable","message":…}` | Unpinned call, and the workspace's backend is missing, broken, or unavailable. The message says which. |
| 412 | `{"error":"integration_not_configured","provider":…}` | `provider` pinned, no BYOK key for it. |
| 412 | `{"error":"no_ai_provider_configured"}` | Only `model` pinned, and the tenant has no BYOK key at all. |
| 429 | `{"error":"ai_spend_cap","subject":"user"\|"tenant","window":"day"\|"month"}` | The shared ManAurum AI spending limit is reached. Managed backend only; BYOK is never capped here. |
| 502 | `"<provider>_upstream_error:<status>"` / `"upstream_error:<provider>"` (string) | `provider` pinned and the provider failed. `deepseek` and `groq` report as `openai_upstream_error:<status>`. |
| 502 | `{"error":"ai_upstream_error","attempts":[{provider, model, status, reason, detail}]}` | Unpinned (or only `model`) and the backend failed. `attempts` has exactly one entry. |

---

## `os.ai.embed` — embeddings (BYOK)

The tenant's own key, from Settings → Integrations. Not routed through the workspace
backend, and `X-Manaurum-Workspace-Id` is ignored.

**Input:**

```json
{ "provider": "openai", "model": "text-embedding-3-small", "input": "text to embed" }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `provider` | string | **yes** | `openai` or `gemini`. |
| `model` | string | **yes** | 1–256 chars. No default. |
| `input` | string or string[] | **yes** | Non-empty. Gemini embeds an array one string at a time, sequentially. |
| `log_prompt` | boolean | no | As on `os.ai.complete`. |

**Output:**

```json
{
  "embeddings": [[0.012, -0.034, ...]],
  "tokens_used": { "input": 4, "output": 0, "total": 4 },
  "cost_usd": 0.0000001, "cost_known": true,
  "provider": "openai", "model": "text-embedding-3-small"
}
```

`embeddings` is always a list of vectors, even for one string. No `usage` field. Gemini's
token count is a whitespace word count, not a tokenizer count.

**Errors:** `412 {"error":"integration_not_configured","provider":…}`;
`502 "<provider>_upstream_error:<status>"` or `"upstream_error:<provider>"` (strings).

To store vectors in your own Postgres you need the `vector` extension, which the manifest
requests with `data.extensions` and a platform operator has to approve before it is
created.

---

## `os.ai.transcribe` — speech-to-text (OpenAI only)

Base64 audio in → transcript text out (MAN-1316). This is the platform's speech-to-text
path: no key ever reaches your container. OpenAI only — an Anthropic key alone does not
cover it.

**Who pays — this and `os.ai.speak`** (Core sergeysuaib-ui/manaurum#2382, MAN-2727 /
MAN-3256). Merged in Core on 2026-10-04; production had not deployed it that day — until it
does, `os.ai.transcribe` runs on the tenant's own OpenAI key only and `os.ai.speak` is
`404 capability_not_found` (the note at the top of this page). On `main`, both voice
capabilities are paid for like text AI:

1. **The tenant's OpenAI integration**, when the tenant has one. The tenant pays OpenAI
   directly, and the shared limits are not touched. An integration that exists but holds
   no usable key is `412 integration_not_configured`; it does not fall through to
   Manaurum's key.
2. **Otherwise Manaurum's metered voice key**, for a call from a resolved workspace that is
   not temporary. It draws on the same user and tenant spending windows as managed text AI
   — a call with a forwarded user context counts against the user and the tenant, an
   app-only call against the tenant — and a full window is `429 ai_spend_cap` before the
   provider is contacted.
3. Neither: `412 integration_not_configured` with `provider: "openai"`.

For `os.ai.speak` the provider is the speaking model's: a Gemini model is paid by the
tenant's Gemini integration, else Manaurum's Gemini key, and the 412 names `"gemini"`.

**Which workspace.** The forwarded user context's `workspace_id`, else
`X-Manaurum-Workspace-Id`, picks it among the workspaces your app is installed in that are
not temporary and that the forwarded person can reach; with neither, the one such workspace
if there is exactly one. A voice call does not need a workspace: when none resolves (no
install qualifies, or several and nothing chose), it still runs, on the tenant's own
integration only. Manaurum's key needs a workspace, so forward the user context whenever
you can. Four answers refuse the call even when the tenant has its own key
(`completion_context.py`):

- `403 workspace_context_mismatch` — the user context and the header name different
  workspaces.
- `400 workspace_context_required` — the header is sent blank.
- `412 workspace_context_unavailable` — the only installs the call could resolve to are
  temporary (the Sandbox), including when the user context or the header names the
  Sandbox: no key pays for a call from there.
- `403 workspace_context_unavailable` — the forwarded user context names a workspace where
  your app has no install the person can reach.

**AI Off applies.** If a workspace administrator switched AI off for your app in the
resolved workspace, both capabilities answer `403 ai_disabled` before any key is read; when
no workspace resolves, AI off for your app in any workspace of the tenant refuses the call.

Every call, on either key, is recorded in the workspace's AI usage, attributed to your app
and to the forwarded user, priced per second of audio. Neither the audio, the text nor the
transcript is stored; the record holds sizes, the voice and the MIME type.

To RECORD audio inside the OS shell iframe, the app must also declare
`"permissions": ["microphone"]` in its manifest (see `v2-platform.md` §1) — without it the
browser blocks `getUserMedia` in the iframe.

**Input:**

```json
{
  "audio_base64": "<base64, standard alphabet>",
  "mime_type":    "audio/webm",
  "model":        "gpt-4o-transcribe",
  "language":     "ru",
  "prompt":       "ManAurum, SeregaOS"
}
```

| Field | Required | Notes |
|---|---|---|
| `audio_base64` | yes | Max **25 MiB decoded**; the string itself is capped at 35,000,000 chars (`422` beyond). Decoding is strict: a `data:` prefix, spaces or line breaks make it `400 invalid_audio_base64`. |
| `mime_type` | optional | Default `audio/webm`. Pass what you actually recorded — Chrome MediaRecorder emits `audio/webm`, iOS Safari `audio/mp4`. |
| `model` | optional | Default `gpt-4o-transcribe`; `whisper-1` and `gpt-4o-mini-transcribe` also work. On Manaurum's voice key only these three are served (anything else is `400 model_not_available`); the tenant's own key passes any model through. |
| `language` | optional | ISO-639-1 hint, e.g. `"ru"`. |
| `prompt` | optional | Vocabulary-biasing prompt (names, domain terms), ≤ 4000 chars. |

There is no `provider` and no `log_prompt` field; sending either is a `422`.

**Output:**

```json
{ "text": "…transcript…", "provider": "openai", "model": "gpt-4o-transcribe" }
```

No token or cost fields.

**Errors** (beyond the gates at the top of this page):
- `400 invalid_audio_base64` — undecodable, non-strict or empty base64.
- `400 audio_too_large` — decoded audio over 25 MiB.
- `400 model_not_available` — on Manaurum's voice key, a `model` other than the three above.
- `403 {"error":"ai_disabled","message":…}` — AI is off for your app (above).
- `400 {"error":"workspace_context_required"}`, `403 {"error":"workspace_context_mismatch"}`,
  `403` / `412 {"error":"workspace_context_unavailable","message":…}` — the workspace cases
  under "Which workspace" above.
- `412 {"error":"integration_not_configured","provider":"openai"}` — no key can serve, or
  the tenant's OpenAI integration holds no usable key. The tenant admin fixes either in
  Settings → Integrations.
- `429 {"error":"ai_spend_cap","message":…,"subject":…,"window":…}` — Manaurum's voice key,
  and a shared spending window is full.
- `502 upstream_error:openai` — EVERY upstream failure (non-2xx, timeout, transport), on
  either key; the status is not included, and it is never a `504`. Upstream timeout is
  120 s.

Keep your own transcript record if you need one: the platform keeps none.

---

## `os.ai.speak` — text to speech, MP3 out (OpenAI or Gemini)

Text or Markdown in → the whole MP3 back as base64. Merged in Core on 2026-10-04
(sergeysuaib-ui/manaurum#2382; Gemini and `model` in #2385); production had not deployed
it that day — until it does, the call is `404 capability_not_found` (the note at the top of
this page). Workspace-resolved and switched off exactly as `os.ai.transcribe` above; the
same errors apply except the audio ones.

**Which model speaks:** the `model` you pass, else the model a workspace admin chose for
your app (Settings → Agent Management → App Setup, a model and a voice per app), else
Manaurum's default (`gpt-4o-mini-tts`). It is paid like `os.ai.transcribe`, by the
speaking model's provider: the tenant's own integration for that provider, else
Manaurum's key for it where Manaurum has one.

**Input:**

```json
{ "text": "Your order **#1042** is ready for pickup.", "voice": "nova", "lang": "en" }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `text` | string | **yes** | 1–20,000 characters of plain text or Markdown. Code blocks are spoken as a short placeholder, links as their label, formatting marks are dropped. At most 4,000 characters of what remains are spoken: longer text is cut at the last sentence end (or hard at 4,000 when there is none in the second half) and `truncated` comes back `true`. |
| `model` | string | no | `gpt-4o-mini-tts`, `gemini-3.8-flash-tts` or `gemini-3.8-flash-lite-tts`. Omit it to use your app's setting or Manaurum's default. |
| `voice` | string | no | OpenAI: `alloy` (default), `coral`, `nova`, `onyx`, `sage`. Gemini: `en-us-bodi` (default) and the 30 prebuilt voices (Achernar, Achird, Algenib, Algieba, Alnilam, Aoede, Autonoe, Callirrhoe, Charon, Despina, Enceladus, Erinome, Fenrir, Gacrux, Iapetus, Kore, Laomedeia, Leda, Orus, Puck, Pulcherrima, Rasalgethi, Sadachbia, Sadaltager, Schedar, Sulafat, Umbriel, Vindemiatrix, Zephyr, Zubenelgenubi). A name in neither list is `422 input_schema_violation`. A voice of the other provider is replaced by the configured voice, unless you also passed `model`: then it is `400 unknown_voice`. |
| `lang` | string | no | ISO-639-1 code of the text, e.g. `"ru"`: the code-block placeholder is spoken in it. English when absent or unknown. |

**Output:**

```json
{ "audio_base64": "<base64 of the MP3>", "mime_type": "audio/mpeg", "voice": "nova",
  "model": "gpt-4o-mini-tts", "truncated": false }
```

It is not a stream. Hand the base64 to your page and play it as a `data:` URL of
`mime_type` (`new Audio("data:" + mime_type + ";base64," + audio_base64)`); to play it again
later, store the decoded bytes with `os.files.upload` — the platform keeps neither the text
nor the audio. For longer text, split it at sentence ends, make one call per part and play
them in order, or check `truncated`.

**Errors** (beyond the gates, and those of `os.ai.transcribe` that are not about audio or
`model`):

| HTTP | `detail` | When |
|---|---|---|
| 400 | `{"error":"nothing_to_speak","message":…}` | Once code and formatting marks are removed, nothing speakable is left. |
| 400 | `{"error":"unknown_voice","message":…}` | You passed `model` with a voice that model does not have. |
| 412 | `{"error":"integration_not_configured","provider":…}` | Neither the tenant nor Manaurum has a key for the speaking model's provider, or the tenant has an integration for it that holds no usable key — that does not fall through to Manaurum's key. |
| 412 | `{"error":"speech_setting_invalid",…}` | Your app's voice setting names a model or voice that is no longer offered; a workspace admin updates it in Settings. |
| 422 | `input_schema_violation` | Empty `text`, `text` over 20,000 characters, or an unknown `model` or `voice`. |

Gemini audio comes back as `audio/mpeg` like OpenAI's, at 64 kbps. A Gemini call costs a
little more with a library voice such as `en-us-bodi`: a fixed input overhead per call of
about $0.0008 on top of the audio.

---

## `os.ai.image_submit` / `os.ai.image_poll` — generate an image (BYOK, two calls)

Image generation is a **background job**, not a request that returns a picture: one image
takes tens of seconds (46–48 s measured for 1536×1024 `medium`), longer than the 30 s the
gateway gives a browser request. So it is two capabilities — submit hands back a `job_id`,
and you poll until the state is terminal. Both need the tenant flag **`platform.ai_image`**
(off by default) and the tenant's **OpenAI** BYOK key. `os.ai.providers` tells you up front
whether both are in place. Neither prompt nor image is ever logged.

**`os.ai.image_submit` input:**

```json
{ "prompt": "a paper crane on a slate background, studio light",
  "size": "1024x1024", "quality": "low", "format": "webp" }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `prompt` | string | **yes** | 1–4000 chars. Passed through verbatim. |
| `size` | string | no | `1024x1024` (default), `1536x1024`, `1024x1536`. |
| `quality` | string | no | `low`, `medium` (default), `high`. Moves cost and time a lot. |
| `format` | string | no | `webp` (default), `png`, `jpeg`. |
| `compression` | integer | no | 0–100, default 80; ignored for `png`. |

**There is no input image** — the capability generates a picture and cannot edit one you
already hold.

**Submit output:** `{ "job_id": "…", "provider": "openai", "driver_model": "gpt-5.1", "state": "pending" }`

**`os.ai.image_poll` input:** `{ "job_id": "…" }`

**Poll output — always HTTP 200; branch on `state`:**

```json
{ "state": "pending" }
{ "state": "failed", "error": "<≤300 chars>" }
{ "state": "done", "image_base64": "…", "mime_type": "image/webp",
  "driver_model": "gpt-5.1-2025-11-13", "image_model": "gpt-image-2",
  "tokens_used": { "driver": { "input": 42, "output": 9 }, "image": { "input": 0, "output": 1120 } },
  "cost_usd": 0.0112, "cost_known": true }
```

`cost_usd` is a number only when both halves are priced. The platform sets no polling
interval; every poll is one upstream request, so poll every few seconds, not in a tight
loop. A job nobody polls to the end has its cost accounted by a sweeper 15–25 minutes
in; polling it still works after that.

**Storing the result is your job.** Decode the base64 and put the bytes in
`os.files.upload`, whose `size_hint` must be the exact **decoded** length (MAN-2117: a
drawing that was ready on the first poll was reported as a five-minute timeout because of
that).

**Errors:**

| HTTP | `detail` | When |
|---|---|---|
| 403 | `{"error":"image_generation_not_enabled", …}` | `platform.ai_image` is off for the tenant (checked on submit **and** on every poll). |
| 412 | `{"error":"integration_not_configured","provider":"openai"}` | No OpenAI key. |
| 404 | `{"error":"image_job_not_found"}` | Poll: unknown id, or a job of another app. |
| 502 | `{"error":"image_submit_failed" \| "image_poll_failed", "upstream_status":…, "detail":…}` | The provider refused or answered garbage. |
| 500 | `handler_exception` | A network failure or timeout towards the provider. Treat as retryable. |

---

## `os.ai.providers` — what AI this app can use here

Read-only discovery. Input `{}` (any field is a `422`). Uses the same workspace resolution
as `os.ai.complete`, so its workspace errors apply; it needs `os.ai.providers` itself in the
grants. Advisory only: nothing is reserved, and things can change before the real call.

**Output:**

```json
{
  "providers": [ { "provider": "openai", "last_test_ok": true,
                   "serves": ["complete", "embed", "transcribe", "image"] } ],
  "platform_fallback": true,
  "completion": { "available": true, "selection_source": "managed_default",
                  "display_name": "ManAurum AI", "unavailable_reason": null },
  "image_generation_enabled": false
}
```

- `providers` — the tenant's BYOK keys, never the keys themselves. `serves` is what each can
  answer *here*: `complete` for all five, `embed` for openai and gemini, `transcribe` for
  openai, `image` for openai only when the flag is on. `transcribe` on the openai row means
  the tenant's integration pays for both `os.ai.transcribe` and `os.ai.speak` (there is no
  `speak` entry). Once production runs `main` (the note at the top of this page), its
  absence does **not** mean voice is unavailable: Manaurum's voice key may still serve the
  call, so make it and handle a `412` rather than hiding a voice feature on this field
  alone.
- `completion` — whether an **unpinned** `os.ai.complete` will work, and with what.
  `unavailable_reason` is `capability_not_granted`, `ai_disabled` or
  `ai_backend_unavailable` when it will not.
- `platform_fallback` — `true` when that default is the company-funded model.

Use it to hide a button rather than fail at the click.

---

## `os.ocr.extract` — read a stored image or PDF (BYOK vision)

The tenant's own key: **Anthropic** if configured (`claude-sonnet-4-6`), else **OpenAI**
(`gpt-4o`). You cannot choose the provider or the model. PDFs work on Anthropic only.

**Input:**

```json
{
  "file_key": "user-uploads/invoice.png",
  "schema": { "type": "object", "properties": { "total": { "type": "number" } } }
}
```

| Field | Required | Notes |
|---|---|---|
| `file_key` | **yes** | A key you wrote with `os.files.upload`, **under the same `X-Manaurum-App-Id` form** (the slug). No leading `/`, no `\`, no `..`. |
| `schema` | no | A JSON Schema the result must satisfy. Without it you get whatever the model returned. |

`additionalProperties: false` — `provider`, `object_key` or `model` is a `422`.

**Output:**

```json
{
  "extracted": { "total": 142.50 },
  "confidence": 0.92,
  "model_used": "claude-sonnet-4-6",
  "tokens_used": { "prompt": 1200, "completion": 40, "total": 1240 },
  "cost_usd": 0.0042
}
```

- `extracted` — with `schema`, the validated object. Without it, the parsed JSON if the
  model returned JSON (a non-object comes back as `{"value": …}`), else `{"text": "<raw>"}`.
- `confidence` is a fixed per-provider number (0.92 Anthropic, 0.85 OpenAI), not a measure
  of this result.
- Note the token keys: `prompt`/`completion` here, `input`/`output` on `os.ai.*`. There is
  no `cost_known`.

**Errors:**

| HTTP | `detail` (string) | When |
|---|---|---|
| 400 | `invalid_file_key_…` | Empty key, leading slash, backslash, or `..`. |
| 404 | `file_not_found` | Nothing stored under that key for this app-id form and tenant. |
| 412 | `ai_provider_not_configured` | Neither an Anthropic nor an OpenAI key. (Not `integration_not_configured`.) |
| 422 | `vlm_output_not_json` / `vlm_output_schema_violation` | `schema` given and the model's answer is not JSON / does not match. |
| 500 | `handler_exception` | Any provider failure, including a PDF on OpenAI. OCR has no 502; treat a 500 here as "the provider failed". |

---

## `os.notifications.send_to_user` — deliver a notification

Three channels: `in_app` (the Notification Center on the user's desktop, free),
`email` (Resend, BYOK), `sms` (Twilio, BYOK — see `501 sms_unavailable` below).

**Input:**

```json
{
  "to_user_id": "<user id>",
  "channel":    "in_app",
  "title":      "Invoice ready",
  "body":       "Your invoice #123 is ready to review.",
  "link":       "/invoices/123"
}
```

| Field | Required | Notes |
|---|---|---|
| `to_user_id` | yes | A member of your tenant. |
| `channel` | yes | `in_app` / `email` / `sms` |
| `body` | yes | 1–4096 chars, stored in full. SMS sends the first 1600. Email sends it **as HTML**, so escape anything a user typed. |
| `title` | no | ≤ 200 chars. In-app uses the first 200 chars of `body` when omitted; email uses it as the subject, or "Notification" without one. |
| `link` | no | In-app only, ≤ 1024 chars. Opaque to the platform; handed back to **your** app when the user clicks the notification (below). |
| `data` | no | Any object. Accepted and not stored. |

There is **no `user_id` and no `deep_link` field**; either one is
`422 input_schema_violation`. A notification can only ever open the app that sent it.
In-app notifications expire after **7 days**. An app installed in a tenant other than the
one it was deployed into finds no live install of itself there, so every send is a `412`.

**Output — read `delivered`, not the HTTP status:**

```json
{ "delivered": true,  "channel": "in_app", "message_id": "<id>" }
{ "delivered": false, "channel": "in_app", "reason": "muted_by_recipient" }
```

A `200` with `delivered: false` always carries a `reason`, and every reason describes
the **recipient** — something your app cannot change, so do not retry:

| `reason` | Meaning |
|---|---|
| `muted_by_recipient` | The user switched your app off in Settings → Notifications. |
| `app_not_installed_for_recipient` | Your app is not installed in that user's workspace. |
| `recipient_has_no_email` | `channel: email`, and the user has no address on file. |
| `recipient_has_no_phone` | `channel: sms`, and the user has no number on file. |

A `200 {"delivered": false}` with **no** `reason` comes from a platform older than
MAN-2516, which answered that way for every in-app send from a hosted app: nothing was
delivered.

**Errors** — anything the platform or the provider could not do is non-200.

| HTTP | `detail` / `detail.error` | Meaning | Retry? |
|---|---|---|---|
| 403 | `capability_not_granted` | The install is not granted this **sensitive** capability. See the gates at the top. A grant screen is not yet available to tenant admins (MAN-1112); ask the platform operator. | no |
| 404 | `user_not_in_tenant` | `to_user_id` is not a member of your tenant. | no |
| 412 | `in_app_unavailable`, `reason: app_not_live` | No live install of your app in this tenant (not deployed, disabled, or uninstalled), so **no** in-app notification can be delivered. | no — fix the install |
| 412 | `in_app_unavailable`, `reason: app_slug_conflict` | Your `app_id` is also a built-in's or a catalogue app's, so the desktop could not tell your notifications from that app's. | no — redeploy under another `app_id` |
| 412 | `app_not_live` | The same, for `email` / `sms`. | no — fix the install |
| 412 | `integration_not_configured` | `email` / `sms` without the tenant's Resend / Twilio keys. | after the admin connects them |
| 429 | `notification_rate_limited` (+ `window`: `hour`/`day`, `limit`) | In-app only: your app has already sent this recipient 10 notifications in the last hour or 50 in the last day. Muted or refused sends do not count. Email and SMS have no rate limit. | later — batch or summarise instead |
| 501 | `sms_unavailable` | The platform stores no phone numbers, so no SMS can be delivered. | no |
| 502 | `provider_rejected` (+ `provider_status`) | The provider refused; nothing was sent. | no |
| 502 | `provider_unreachable` | The provider could not be reached; nothing was sent. | yes, later |
| 504 | `provider_outcome_unknown` | The provider call failed after it was sent. The message **may** have been delivered. | only if a duplicate is acceptable |

**When the user clicks.** The Notification Center opens your app's window (switching
tenant first if needed) and passes `{ "action": "open", "payload": { "link": "…" } }`
to your iframe — `payload` is `{}` when you sent no `link`. It arrives inside
`manaurum:init` as `payload.deepLink` when the click opened your window, and as a
`manaurum:deep-link` message when the window was already open. The platform does not
navigate your iframe; route to `link` yourself. The v2 SDK does not surface either
message (`sdk-api.md`), so add your own `message` listener — attach it synchronously at
startup, after the shell-sender check: the shell sends the link once and then forgets it,
so a listener registered later (in a React effect, after a fetch) may miss it.

---

## `os.events.emit` — publish an event (emit only)

Writes the event to the platform's outbox. **App id: the UUID.**

**No hosted v2 app can receive events today.** Declaring them under `consumes.events`
does nothing, and the dispatcher has no subscribers
to deliver to (MAN-133). Emitting is harmless, but do not build a feature on another app,
or your own, hearing it.

**Input:**

```json
{
  "event_name":      "invoice.created",
  "payload":         { "invoice_id": "...", "total": 100 },
  "idempotency_key": "invoice-123-created"
}
```

| Field | Required | Notes |
|---|---|---|
| `event_name` | yes | 1–256 chars, `<group>.<verb>`, e.g. `invoice.created`. Not namespaced to your app. |
| `payload` | yes | A JSON **object** (not a list or a scalar). |
| `idempotency_key` | no | ≤ 256 chars. A repeat returns the first event's id, and the first payload wins. |

**Output:** `{ "event_id": "<uuid>", "queued_at": "<iso>" }`

**Errors:** `412 app_id_must_be_uuid`. There is no rate limit.

---

## `os.http.fetch` — external HTTP (egress allow-list)

The host must appear in `manifest.runtime.egress_allowed_hosts` of your **current
version**: an exact, case-insensitive host match, no wildcards, port ignored. Default-deny,
HTTPS only. This is the only egress the platform checks — your container's own outbound
connections are not filtered — so route through it whatever must be auditable.

**Input:**

```json
{
  "url":     "https://api.example.com/foo",
  "method":  "GET",
  "headers": { "Accept": "application/json" },
  "body":    "<string body>",
  "timeout_ms": 10000
}
```

| Field | Required | Notes |
|---|---|---|
| `url` | yes | `https://` only. |
| `method` | optional | `GET` (default) / `POST` / `PUT` / `DELETE`. |
| `headers` | optional | Plain object, sent as is. |
| `body` | optional | **String** body — for text/JSON payloads. |
| `body_base64` | optional | **Binary** request body, base64-encoded (MAN-1316). Mutually exclusive with `body`. ≤ 7,000,000 chars (~5 MB decoded). |
| `response_format` | optional | `"text"` (default — response `body` is UTF-8 with replacement, LOSSY for binary) or `"base64"` (lossless — exact bytes in `body_base64`, `body` comes back empty). |
| `timeout_ms` | optional | 1–30000, default 10000. (Milliseconds — there is no `timeout_seconds` field.) |

**Binary payloads — the rule:** the default `text` wire corrupts binary data in BOTH
directions. To send raw bytes (file uploads, audio), base64 them into `body_base64`; to
receive raw bytes (file downloads), pass `response_format: "base64"` and read
`body_base64` from the output.

**Output:**

```json
{
  "status": 200,
  "headers": { ... },
  "content_length": 1234,
  "elapsed_ms": 87,
  "body": "…text (or empty string in base64 mode)…",
  "body_base64": "…only present when response_format is base64…"
}
```

Upstream 4xx/5xx are NOT errors — they come back in `status` and your app handles them.
Redirects are not followed; handle `Location` yourself with a second call (it re-passes the
allow-list checks, so the redirect's host has to be in `egress_allowed_hosts` too). Your
`headers` are sent verbatim on every call, so when the `Location` host differs from the
one you called, drop `Authorization` and any other credential before following it — Jira
answers attachment downloads with a `303` to a CDN, and following it with the headers
unchanged hands your Jira token to the CDN.

**Errors:**
- `412 egress_not_declared` — your current version declares no egress hosts.
- `412 host_not_in_allow_list` — URL host isn't in the declared list.
- `400 unsafe_url` — non-https scheme, a local name, a private-range IP, or a hostname that
  resolves to one.
- `422 input_schema_violation` — both body fields sent (older platforms:
  `400 body_and_body_base64_exclusive`).
- `400 invalid_body_base64` — `body_base64` undecodable.
- `502 upstream_unreachable` — DNS / connect / TLS failure.
- `502 upstream_response_too_large` — response over the 5 MiB cap.
- `504 upstream_timeout` — upstream didn't answer within `timeout_ms`.

**Installed in another tenant?** The allow-list is looked up in the calling tenant, so an
app deployed by one tenant and installed in another gets `412 egress_not_declared` there.

---

## `os.compliance.audit_query` — read the capability audit trail

Reader over the capability audit log. **It is scoped to the tenant, not to your app:**
without `app_filter` it returns every app's calls in the tenant (MAN-2253 tracks narrowing
it). Pass `app_filter` yourself, and do not show its output to users as "your app's
activity" without filtering.

**Input:**

```json
{
  "since":              "2026-05-01T00:00:00Z",
  "until":              "2026-05-08T00:00:00Z",
  "capability_filter":  "os.kv.set",
  "app_filter":         "my-app",
  "limit":              100
}
```

| Field | Required | Notes |
|---|---|---|
| `since` | yes | ISO8601. A malformed value is `500 handler_exception`. |
| `until` | optional | ISO8601. |
| `capability_filter` | optional | exact match on capability name. |
| `app_filter` | optional | exact match on the app id **as it was sent** by the calling app. |
| `limit` | optional | 1–1000, default 100. |

**Output:**

```json
{
  "entries": [
    {
      "event_id": "...",
      "correlation_id": "...",
      "app_id": "my-app",
      "capability_name": "os.kv.set",
      "capability_version": 1,
      "actor_developer_user_id": "...",
      "latency_ms": 5,
      "ok": true,
      "error_code": null,
      "started_at": "..."
    }
  ],
  "total":     1,
  "has_more":  false
}
```

Entries are newest first. `total` is the number returned, not the number matching, and
`has_more` is only `entries.length == limit`. A failure your handler raised is recorded as
`error_code: "handler_http_error"`, not with its own code.

---

## `os.apps.call` — call a built-in app's method

Synchronous, in-process. **Only four methods of two built-in apps can be called, and a
hosted v2 app cannot be a target** — there is no RPC between v2 apps. Each target is
switched on per tenant, and an unflagged tenant gets a bare `404`.

| `target_app_id` | `method` | Returns |
|---|---|---|
| `receptions` | `stock.levels` | stock per item |
| `menu-profitability` | `recipes.ingredients` | recipes with their ingredients |
| `menu-profitability` | `sales.daily_totals` | units and revenue per day |
| `menu-profitability` | `sales.dish_totals` | units and revenue per dish |

**Input:**

```json
{ "target_app_id": "receptions", "method": "stock.levels", "args": { "limit": 200 },
  "version": 1, "timeout_ms": 10000 }
```

| Field | Required | Notes |
|---|---|---|
| `target_app_id` | yes | From the table. |
| `method` | yes | From the table. |
| `args` | yes | An object; validated against the method's own schema. |
| `version` | no | Integer ≥ 1, default 1. |
| `timeout_ms` | no | 1–30000, default 10000. |

**Output:** `{ "result": <the method's answer>, "latency_ms": 12, "target_version": "1" }`

All four are behind flags only the burgeris tenant has today.

**Errors:** `404 rpc_target_not_found` (or a bare `404` for an unflagged tenant),
`422 rpc_args_invalid` from the method itself,
`422 rpc_args_schema_violation`, `503 rpc_target_timeout`, `503 rpc_target_unavailable`.

---

## `os.apps.bulk_export` — streaming export (not usable today)

Declared, but **no dataset is registered on the platform**, so every call answers
`404 target_app_not_found`. Do not build on it. For the record, the input is
`{ "target_app_id", "dataset", "since"?, "until"?, "limit"? }`; the output would be an
`application/x-ndjson` stream capped at 100 MiB, ending with
`{"_error":"bulk_export_size_cap_exceeded"}` when cut.

---

## Quotas and rate limits

**No capability declares a daily quota**, so `429 quota_exceeded` does not happen today.
The limits that do fire are per capability:

| Limit | Where | Answer |
|---|---|---|
| 20 upload URLs a minute, 200 an hour, per (app, tenant) | `os.files.upload` | `429 upload_rate_limited` + `Retry-After: 60` |
| 1 GiB per (app, tenant) | `os.files.upload` | `413 namespace_quota_exceeded` |
| 50 MiB per object | `os.files.upload` (`size_hint`) | `422 input_schema_violation` |
| 20 saves a minute, 200 an hour, per user | `os.drive.publish` / `.write` | `429 publish_rate_limited` |
| 10 a hour, 50 a day, per (app, recipient) | `os.notifications.send_to_user`, in-app | `429 notification_rate_limited` |
| Shared ManAurum AI spend, per user and per tenant, day and month | `os.ai.complete` on the managed backend; `os.ai.speak` / `os.ai.transcribe` on Manaurum's voice key | `429 ai_spend_cap` |

The manifest key `quota_per_tenant_per_day` is accepted and has no effect.

---

## Keeping this file honest

The registry is the source of truth: `backend/app/services/capabilities/` in the monorepo —
`grep -rn 'name="os\.' backend/app/services/capabilities/` enumerates every capability that
exists, and each `CapabilityDefinition` carries the `auth_mode` and input schema this page
describes. This page was last read against the handlers capability by capability at Core
`main` 8fe6f5d (2026-10-02); `os.ai.speak`, the voice funding and workspace rules of
`os.ai.transcribe` and `os.directory.list_users` were read against `7c1f09566`
(2026-10-04). Separately, `scripts/check_repo.py` holds this page to the contract copy
synced at `7c1f09566`: every registered capability documented, the count above, and each
single-capability section's input example and field table equal to its schema.

When a capability is added or changed in the monorepo, the checklist that must be walked is
`docs/standards/ADDING_A_V2_CAPABILITY.md`. Its § 9 covers this plugin explicitly — this
file, `manaurum-app/SKILL.md`, `v2-platform.md` § 1 and `manaurum-setup/SKILL.md` all have
to move with the code, because a stale skill actively generates broken apps. Beyond the
names and inputs `check_repo.py` compares, nothing checks outputs, errors or behaviour
against the registry; the checklist is the mechanism.

# Capabilities — input/output reference

The exhaustive reference for every Platform v2 capability. All **26** capabilities
registered in `backend/app/services/capabilities/` are documented below. Every entry
documents:

- The capability name + version.
- Required input fields (JSON Schema-derived).
- Output shape on success.
- Common error codes specific to that capability.

## The call contract

Your **container** makes the call, using credentials the platform injects for it:

```
POST ${MANAURUM_CORE_URL}/api/capability/<name>
Authorization: Bearer ${MANAURUM_RUNTIME_TOKEN}
X-Manaurum-Tenant-Id: ${MANAURUM_TENANT_ID}
X-Manaurum-App-Id:    ${MANAURUM_APP_ID}
X-Manaurum-User-Context: <the JWT your route received>   # auth_mode: user only
Content-Type: application/json
```

- `MANAURUM_CORE_URL` and `MANAURUM_RUNTIME_TOKEN` are **injected at deploy** by the
  platform. `MANAURUM_RUNTIME_TOKEN` *is* an `mna_*` token, but it is a per-(tenant, app)
  runtime credential minted fresh on every deploy — **not** your developer CLI token.
  Never bake an `mna_*` you created yourself into the image; that one is deploy-time only.
  In production `MANAURUM_CORE_URL` resolves to `https://manaurum.com`, but read the env
  var rather than hardcoding it.
- **App-id form matters.** `os.kv.*` and `os.events.emit` key their tables by UUID and
  return `412 app_id_must_be_uuid` if you send the slug. Always send `MANAURUM_APP_ID`
  (the UUID); every other capability accepts either form.

Success response: `{ "output": { … }, "correlation_id": "<uuid>" }`. Streaming
capabilities (`os.apps.bulk_export`) return `application/x-ndjson` instead.

## Gates that run before your capability does

These fire in the gateway, before any handler code, so they apply to **every** capability.

| HTTP | `detail.error` | When |
|---|---|---|
| 403 | `capability_not_granted` | The capability is not in the tenant install's `granted_capabilities`. **An install with an EMPTY grant list denies everything** — declaring a capability in your manifest and redeploying is not enough on its own. |
| 403 | `tenant_mismatch` | `X-Manaurum-Tenant-Id` is not the tenant your credential was issued for. The header is no longer trusted on its own. |
| 403 | `user_context_required` | The capability is `auth_mode: "user"` (`os.drive.*`, `os.calendar.*`) and you sent no `X-Manaurum-User-Context`. |
| 401 | `invalid_user_context` | The forwarded JWT failed verification, or its `tenant_id` / `app_id` doesn't match the call. |
| 403 | `capability_denied_in_dev_mode` | App Builder dev-mode app calling a capability outside the dev allow-list. Publish the app. |

Grant enforcement is **unconditional** — it is not "when wired". It runs ahead of quota,
dispatch and audit, and only dev-mode apps and active BYO hosts short-circuit it. A
wildcard `"*"` grant allows everything.

The gateway **accepts** `X-Manaurum-User-Context` on `/api/capability/<name>` and
**requires** it for `auth_mode: "user"` capabilities. On `auth_mode: "app"` capabilities
it is optional and only enriches `acting_user_id` in the audit log. (If you read anywhere
that the gateway *rejects* a user context on this path, that statement is wrong.)

Universal error codes for the rest (credential, headers, schema, quota): see
`v2-platform.md` § 3.

---

## `os.kv.set` — store a value

Per-app, per-tenant key/value in Postgres. FORCE-RLSed.

**Input:**

```json
{ "key": "any-string-up-to-256", "value": <any JSON> }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `key` | string | yes | 1–256 chars. Treated opaquely. |
| `value` | any | yes | Stored as `jsonb`. |

**Output:** `{ "ok": true }`

**Errors:** universal only.

---

## `os.kv.get` — read a value

**Input:** `{ "key": "..." }`

**Output:** `{ "value": <stored value, or null> }`

A missing key returns `value: null`, not 404.

---

## `os.tenant_config.get` — read tenant config — ⚠️ DO NOT RELY ON THIS TODAY

**Input:** `{ "key": "some-key" }`

**Output:** `{ "value": <value, or null> }` — a missing key is `null`, never a 404.

**What it actually reads.** Not `tenants.features`, and not the `tenant_config` values a
tenant supplied at install (those land in `v2_app_installs.config`, which nothing under
`capabilities/` reads). The handler calls `get_config_for_tenant` against the
`tenants.app_builder_config` jsonb column and does a plain `getattr(config, key, None)` on
the resulting Pydantic model. That model (`TenantAppBuilderConfig`, v0) has **exactly one
field — `prompt_extension`** — and is declared `extra: "ignore"`, so every other key in
the column is dropped on load.

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

Encrypted at rest. Per-(app, tenant, name).

**Input:**

```json
{ "name": "openai_api_key", "value": "sk-..." }
```

| Field | Type | Required |
|---|---|---|
| `name` | string | yes |
| `value` | string | yes |

**Output:** `{ "ok": true }`

---

## `os.secrets.get` — read an encrypted secret

**Input:** `{ "name": "openai_api_key" }`

**Output:** `{ "value": "sk-..." }` or 404 if not set.

---

## `os.files.upload` — get a presigned R2 PUT URL

The platform never proxies bytes — it returns a presigned URL the app uploads directly to.

**Input:**

```json
{ "key": "user-uploads/avatar.png", "content_type": "image/png" }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `key` | string | yes | Relative key inside your namespace. The full storage key is `app/<app_id>/<tenant_id>/<key>` — server-built so cross-app/tenant addressing is impossible by construction. |
| `content_type` | string | yes | Upload's `Content-Type` (must match the PUT). |

**Output:**

```json
{
  "upload_url": "https://...r2.cloudflarestorage.com/...?X-Amz-...",
  "expires_at": 1735689600
}
```

URL is valid for 5 minutes. The app then `PUT`s the bytes directly with the `Content-Type` header.

---

## `os.files.download` — get a presigned GET URL

**Input:** `{ "key": "user-uploads/avatar.png" }`

**Output:** `{ "download_url": "...", "expires_at": <unix> }` or 404 if not found.

---

## `os.files.delete` — delete an object

**Input:** `{ "key": "user-uploads/avatar.png" }`

**Output:** `{ "ok": true }`

---

## `os.files.list` — list your own objects

**Input:** `{ "prefix": "user-uploads/", "max_keys": 100, "cursor": null }` (all optional)

**Output:** `{ "files": [{ "key", "size", "last_modified" }], "cursor": "<next page or null>" }`

Keys are app-relative (what you passed to upload). NOTE: `os.files.*` is your
app's PRIVATE SCRATCH — the user never sees these objects in their Files app.
For user-facing documents use `os.drive.*` below.

---

## `os.drive.*` — the user's Drive (consent-gated, user-context required)

The file system the USER owns and sees in the Files app. All five capabilities
are `auth_mode: user`: every call MUST forward the inbound
`X-Manaurum-User-Context` JWT (60s TTL — forward immediately, never store).
Declare each in `requires_capabilities`. Missing/invalid context → 403/401.

### `os.drive.stage` — presigned PUT to a user-scoped staging key

**Input:** `{ "content_type": "image/png", "expires_in": 600 }` (expires optional)

**Output:** `{ "staging_key", "upload_url", "expires_at" }`

The staging key is server-built and scoped to (your app, tenant, acting user) —
unaddressable by anyone else. PUT your bytes to `upload_url`, then publish.

### `os.drive.publish` — publish the staged artefact into the user's Drive

**Input:** `{ "staging_key": "...", "filename": "report.csv", "folder_name": "optional" }`

**Output:** `{ "file_id", "filename", "folder_id", "folder_name", "size_bytes" }`

The document becomes the user's OWN file (folder named after your app by
default), they get a notification, your app keeps no residual access. Limits:
5 MB; extensions `md txt csv json pdf png jpg jpeg webp` (no svg/html);
binary types magic-byte-sniffed; per-user rate limit (429).

### `os.drive.list` / `os.drive.read` / `os.drive.write` — granted folders

Standing access after the folder owner grants your app viewer/editor in
Files → Share. Effective access = the grant INTERSECTED with the acting
user's own access; ungranted folders read as 404.

- `os.drive.list` **Input:** `{ "folder_id" }` → `{ folder, folders[], files[] }`
- `os.drive.read` **Input:** `{ "file_id" }` → `{ file, download_url, expires_at }` (signed, ~5 min, attachment-pinned)
- `os.drive.write` **Input:** `{ "staging_key", "filename", "folder_id" }` → create-only; requires editor grant AND the acting user owns the folder (403 `write_requires_folder_owner`)

### Drive events + the picker

- Subscribe to `drive.{your_slug}.file.{created|updated|deleted}` in
  `consumes.events` — metadata-only change events for granted subtrees.
- Frontend: `app.pickFromDrive({ accept: ['image/'] })` (SDK v2.1+) opens the
  OS picker; the user picks; you get a ~5-min signed URL for that one file.

Full chapter: `docs/handoff/V2_DEVELOPER_GUIDE.md` ("Two storages", "Saving a
document into the user's Drive", "Working in a granted folder").

---

## `os.calendar.*` — the user's calendar (user-context required)

Two capabilities over the OS calendar store — the same service the builtin Calendar UI
and the OS Assistant's agent tools write through, never a second copy. Both are
`auth_mode: "user"`: every call MUST forward the inbound `X-Manaurum-User-Context` JWT
(60s TTL — forward immediately, never store), or you get `403 user_context_required`.
Declare each one you use in `requires_capabilities`.

Events are owned by the **acting user**, not by your app. Your `app_id` is recorded as the
event's `source_app` so the calendar can show provenance, but it does not scope reads.

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

`additionalProperties: false` — an unlisted field is `422 input_schema_violation`.

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
upsert keyed by `(user, your app, source_ref)` — call it again with new times and the same
row is updated. Without it, every call creates a NEW event, so a retry duplicates.

### `os.calendar.list_events` — read the user's events

**Input:** `{ "start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z" }` — both
optional, `additionalProperties: false`. Omitting a bound makes that side open-ended.

**Output:** `{ "events": [ <same shape as above>, … ] }`, ordered by `start_at`.

Three things to know before you build on it:

- **Overlap, not containment.** An event is returned when `start_at < end` AND
  `end_at > start`, so multi-day and in-progress events appear.
- **You see the user's WHOLE calendar**, not just events your app created — including
  Google-synced ones. Filter on `source_app` yourself if you only want your own.
- **No pagination and no server-side cap.** An open-ended range returns every event the
  user has. Always pass a bounded `start`/`end`.

**Errors:** the gateway gates above, plus `422 input_schema_violation`. A malformed
date-time surfaces as `500 handler_exception`, not a 422 — validate your ISO8601 before
sending.

> **App Builder caveat.** `os.calendar.*`, `os.drive.*` and `os.files.list` are absent
> from App Builder's capability auto-detector (`KNOWN_CAPABILITIES`), so generated code
> calling them will NOT be reconciled into the generated manifest and will `403
> capability_not_granted` at runtime. Add them to `requires_capabilities` by hand.

---

## `os.ai.complete` — LLM completion (BYOK)

The tenant's API key is used (configured in Settings → Workspace → Интеграции). Five providers supported: `openai`, `anthropic`, `gemini`, `deepseek`, `groq`.

**Input:**

```json
{
  "provider": "openai",
  "model":    "gpt-4o-mini",
  "messages": [
    { "role": "system",  "content": "You are a helpful assistant." },
    { "role": "user",    "content": "Hello." }
  ],
  "temperature": 0.2,
  "max_tokens": 1024
}
```

| Field | Required |
|---|---|
| `provider` | yes |
| `model` | yes |
| `messages` | yes (array of `{role, content}`) |
| `temperature`, `max_tokens`, `top_p`, etc. | optional, passed through to provider |

**Output:**

```json
{
  "content": "Hi! How can I help?",
  "model":   "gpt-4o-mini",
  "usage":   { "input_tokens": 22, "output_tokens": 8 }
}
```

**Errors:**
- `412 missing_provider_credentials` — tenant hasn't set a key for this provider in Интеграции.
- `400 unsupported_provider` — provider not in the allowed list.
- `502 upstream_5xx` — provider returned 5xx; passed through.

---

## `os.ai.embed` — embedding (BYOK)

Two providers: `openai` (text-embedding-3-small/large), `gemini` (text-embedding-004).

**Input:**

```json
{ "provider": "openai", "model": "text-embedding-3-small", "input": "text to embed" }
```

`input` may also be an array of strings for batch embedding.

**Output:**

```json
{
  "embeddings": [[0.012, -0.034, ...]],
  "model": "text-embedding-3-small",
  "usage": { "input_tokens": 4 }
}
```

---

## `os.ai.transcribe` — speech-to-text (BYOK, OpenAI only)

Base64 audio in → transcript text out (MAN-1316). BYOK with the tenant's
**OpenAI** key specifically — an Anthropic key alone does not cover STT.
This is the platform STT path: the tenant's key never reaches your
container, so BYOK transcription goes through this capability only
(`os.http.fetch` can carry binary but caps at ~5 MB and would need your
own API key + an egress declaration).

To RECORD audio inside the OS shell iframe, the app must also declare
`"permissions": ["microphone"]` in its manifest (see `v2-platform.md` § 1)
— without it the browser blocks `getUserMedia` in the iframe.

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
| `audio_base64` | yes | Max **25 MB decoded** (the upstream upload limit). |
| `mime_type` | optional | Default `audio/webm`. Pass what you actually recorded — Chrome MediaRecorder emits `audio/webm`, iOS Safari `audio/mp4`. |
| `model` | optional | Default `gpt-4o-transcribe`; `whisper-1` and `gpt-4o-mini-transcribe` also work. |
| `language` | optional | ISO-639-1 hint, e.g. `"ru"`. |
| `prompt` | optional | Vocabulary-biasing prompt (names, domain terms), ≤ 4000 chars. |

**Output:**

```json
{ "text": "…transcript…", "provider": "openai", "model": "gpt-4o-transcribe" }
```

**Errors:**
- `400 invalid_audio_base64` — undecodable or empty base64.
- `400 audio_too_large` — decoded audio over the 25 MiB cap.
- `412 integration_not_configured` (`provider: "openai"`) — tenant has no
  OpenAI key in Settings → Workspace → Интеграции.
- `502 upstream_error:openai` — EVERY upstream failure (non-2xx, timeout,
  transport) surfaces as this; the capability never returns 504.

Privacy note: the platform logs only the audio size + MIME for audit —
never the audio or the transcript. Keep your own transcript record if you
need one.

---

## `os.ocr.extract` — OCR via vision LLM (BYOK)

Two providers: `anthropic-vision` (claude-3-5-sonnet), `openai-vision` (gpt-4o).

**Input:**

```json
{
  "provider": "anthropic-vision",
  "object_key": "user-uploads/invoice.pdf",
  "schema": { "type": "object", "properties": { "total": { "type": "number" } } }
}
```

| Field | Required | Notes |
|---|---|---|
| `provider` | yes | |
| `object_key` | yes | Key in your R2 namespace (the platform fetches it). |
| `schema` | yes | JSON Schema the extracted output is validated against. |

**Output:**

```json
{ "data": { "total": 142.50 }, "model": "claude-3-5-sonnet" }
```

**Errors:**
- `404 object_not_found` — `object_key` doesn't exist in your namespace.
- `422 schema_violation` — VLM output didn't match `schema`.
- `412 missing_provider_credentials`.

---

## `os.notifications.send_to_user` — deliver a notification

Three channels: `in_app` (Manaurum desktop notification center), `email` (Resend BYOK), `sms` (Twilio BYOK).

**Input:**

```json
{
  "to_user_id": "<uuid>",
  "channel":    "in_app",
  "title":      "Invoice ready",
  "body":       "Your invoice #123 is ready to review.",
  "deep_link":  { "app_id": "v2-smoke", "path": "/invoices/123" }
}
```

| Field | Required |
|---|---|
| `to_user_id` | yes |
| `channel` | yes (`in_app` / `email` / `sms`) |
| `title` | yes |
| `body` | yes |
| `deep_link` | optional (in-app only) |

**Output:** `{ "delivered": true, "channel": "in_app" }`

**Errors:**
- `404 user_not_found_in_tenant` — `to_user_id` not a member of any workspace in your tenant.
- `412 missing_provider_credentials` — for email/sms when Resend/Twilio keys aren't set.

---

## `os.events.emit` — publish an inter-app event

Writes to `events_outbox` in the caller's transaction. The dispatcher picks it up and delivers to subscribers (other apps that registered for this event type) at-least-once with backoff: 1m / 5m / 15m / 1h / 4h / DLQ-24h.

**Input:**

```json
{
  "event_name": "invoice.created",
  "payload":    { "invoice_id": "...", "total": 100 }
}
```

| Field | Required |
|---|---|
| `event_name` | yes — `<group>.<verb>` form, e.g. `invoice.created`, `user.signed_up` |
| `payload` | yes — any JSON |

**Output:** `{ "event_id": "<uuid>", "queued_at": "<iso>" }`

---

## `os.http.fetch` — external HTTP (egress allow-list)

Hosts must appear in `manifest.runtime.egress_allowed_hosts`. Default-deny.
HTTPS only.

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
| `headers` | optional | Plain object. |
| `body` | optional | **String** body — for text/JSON payloads. |
| `body_base64` | optional | **Binary** request body, base64-encoded (MAN-1316). Mutually exclusive with `body` — sending both is an error. Max ~5 MB decoded. |
| `response_format` | optional | `"text"` (default — response `body` is UTF-8 with replacement, LOSSY for binary) or `"base64"` (lossless — exact bytes in `body_base64`, `body` comes back empty). |
| `timeout_ms` | optional | 1–30000, default 10000. (Milliseconds — there is no `timeout_seconds` field.) |

**Binary payloads — the rule:** the default `text` wire corrupts binary
data in BOTH directions. To send raw bytes (file uploads, audio), base64
them into `body_base64`; to receive raw bytes (file downloads), pass
`response_format: "base64"` and read `body_base64` from the output.

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

Upstream 4xx/5xx are NOT errors — they come back in `status` and your app
handles them. Redirects are not followed; handle `Location` yourself with
a second call (it re-passes the allow-list checks).

**Errors:**
- `412 egress_not_declared` — manifest declares no egress hosts at all.
- `412 host_not_in_allow_list` — URL host isn't in the declared list.
- `400 unsafe_url` — non-https scheme, loopback / private-range target, or
  a hostname resolving to one.
- `422 input_schema_violation` — both body fields sent (rejected at schema
  validation; older platforms surface it as the handler's
  `400 body_and_body_base64_exclusive`).
- `400 invalid_body_base64` — `body_base64` undecodable.
- `502 upstream_unreachable` — DNS / connect / TLS failure.
- `502 upstream_response_too_large` — response over the 5 MB cap.
- `504 upstream_timeout` — upstream didn't answer within `timeout_ms`.

---

## `os.compliance.audit_query` — read your audit trail

Reader-only over `capability_audit_log`, scoped to the calling tenant + app.

**Input:**

```json
{
  "since":              "2026-05-01T00:00:00Z",
  "until":              "2026-05-08T00:00:00Z",
  "capability_filter":  "os.kv.set",
  "limit":              100
}
```

| Field | Required | Notes |
|---|---|---|
| `since` | yes | ISO8601. |
| `until` | optional | ISO8601. |
| `capability_filter` | optional | exact-match on capability name. |
| `app_filter` | optional | exact-match on app_id. |
| `limit` | optional | 1..1000, clamped. |

**Output:**

```json
{
  "entries": [
    {
      "event_id": "...",
      "correlation_id": "...",
      "capability_name": "os.kv.set",
      "capability_version": 1,
      "actor_developer_user_id": "...",
      "latency_ms": 5,
      "ok": true,
      "error_code": null,
      "started_at": "..."
    }
  ],
  "total":     2,
  "has_more":  false
}
```

---

## `os.apps.call` — RPC to another app

Synchronous in-process call (today; hosted-runtime dispatch deferred). The other app must be installed in the same tenant.

**Input:**

```json
{
  "app_id":  "other-app",
  "method":  "invoices.get",
  "version": "1",
  "args":    { "id": "..." },
  "timeout_seconds": 10
}
```

**Output:** Whatever the target method returns. Wrapped in `{ "output": ... }` like every other capability.

**Errors:**
- `404 method_not_found` — other app didn't register `(method, version)`.
- `503 timeout` — exceeded `timeout_seconds` (max 30s).

---

## `os.apps.bulk_export` — streaming export

NDJSON streaming response. 100 MB hard cap; if reached, the last line is `{"_error": "size_limit"}`.

**Input:** `{ "dataset_name": "invoices.history", "version": "1", "args": {} }`

**Output:** `application/x-ndjson` — one JSON object per line.

---

## Quotas

Daily quotas per `(app, capability)` are tracked in `capability_quota_daily`. Default limits TBD (currently `null` = unlimited; will be set per-tenant config). When tripped: `429 quota_exceeded`.

For local dev / heavy testing, ask the platform team or use a separate test tenant.

---

## Keeping this file honest

The registry is the source of truth: `backend/app/services/capabilities/` in the monorepo —
`grep -rn 'name="os\.' backend/app/services/capabilities/` enumerates every capability that
exists, and each `CapabilityDefinition` carries the `auth_mode` and input schema this page
describes.

When a capability is added or changed in the monorepo, the checklist that must be walked is
`docs/standards/ADDING_A_V2_CAPABILITY.md` (active standard since 2026-07-19). Its § 9
covers this plugin explicitly — this file, `manaurum-app/SKILL.md`, `v2-platform.md` § 1 and
`manaurum-setup/SKILL.md` all have to move with the code, because a stale skill actively
generates broken apps. There is **no** automated parity check between the registry and any
documentation surface (this one included); the checklist is the mechanism.

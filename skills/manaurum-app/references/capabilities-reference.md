# Capabilities — input/output reference

The exhaustive reference for every Platform v2 capability. Every entry below documents:

- The capability name + version.
- Required input fields (JSON Schema-derived).
- Output shape on success.
- Common error codes specific to that capability.

The contract for **every** capability call:

```
POST https://manaurum.com/api/capability/<name>
Authorization: Bearer mna_*
X-Manaurum-Tenant-Id: <uuid>
X-Manaurum-App-Id:    <uuid>
Content-Type: application/json
```

Universal error codes (any capability): see `v2-platform.md` § 3.

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

## `os.tenant_config.get` — read tenant config / feature flags

Reads from `tenants.features` jsonb. Useful for per-tenant branding, behavior flags, feature gates.

**Input:** `{ "key": "experiment.my-flag" }`

**Output:** `{ "value": <feature value, or null if unset> }`

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

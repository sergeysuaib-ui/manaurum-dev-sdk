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

**Input:**

```json
{
  "method":  "GET",
  "url":     "https://api.example.com/foo",
  "headers": { "Accept": "application/json" },
  "body":    null,
  "timeout_seconds": 10
}
```

**Output:** `{ "status": 200, "headers": {...}, "body": "..." }`

**Errors:**
- `412 egress_not_declared` — host isn't in manifest egress.
- `400 invalid_url` — URL doesn't parse / isn't `http(s)`.
- `502 upstream_5xx`, `504 upstream_timeout`.

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

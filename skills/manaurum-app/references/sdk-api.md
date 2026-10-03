# ManAurum SDK API Reference

## What this page covers (read first)

Every app built outside the monorepo is a **Platform v2** app, and this page is its browser side.

| | **Platform v2** |
|---|---|
| Client SDK | `https://manaurum.com/sdk/manaurum-v2.mjs` — ES module, exports `ManaurumV2`, internal `VERSION = '2.3.0'` |
| Where the app runs | your own container, served at `https://<app_id>.apps.manaurum.com` |
| Data + capabilities | HTTP only: browser → your backend → `POST {MANAURUM_CORE_URL}/api/capability/<name>` |
| postMessage is used for | the ready handshake, window framing, and the Drive picker — **nothing else** |

Section map:

| Section | What it is |
|---|---|
| `manaurum:ready` — the shell handshake | mandatory for every app with a window |
| The person's language | `locale` / `dir`, `manaurum:locale-change`, and what cannot learn the language |
| Platform v2 — frontend SDK (`manaurum-v2.mjs`) | the optional client helper |

`https://manaurum.com/sdk/manaurum.js` (global `ManaurumSDK`) is the retired v1 SDK. Do not load it.

---

## `manaurum:ready` — the shell handshake (mandatory)

**If your app never replies `manaurum:ready`, it is unusable as a desktop window.** This is enforced by `frontend/src/components/window/IframeAppHost.tsx`, and there is no exemption on this path.

### What the shell sends

The desktop renders `<iframe src="<entrypoint>">` and, on the iframe's `load` event, posts `manaurum:init` into it (`IframeAppHost.tsx:284-352`, `:691-694`) with `targetOrigin` set to the exact origin of your entrypoint.

For a v2 app the entrypoint is **derived by the platform**, not read from your manifest: `https://<app_id>.apps.manaurum.com/` (`lib/v2/deriveEntrypoint.ts:31-42`; the domain comes from `NEXT_PUBLIC_MANAURUM_APPS_DOMAIN`, default `apps.manaurum.com`). The one exception is `runtime.mode: "byo"`, where the manifest's `runtime.entrypoint` is used verbatim.

The payload as actually posted today (`sendInit`):

```json
{
  "type": "manaurum:init",
  "payload": {
    "theme": "smoothie",
    "appearance": "light",
    "accent": "core-blue",
    "device": "desktop",
    "platform": "desktop",
    "screen": { "width": 1440, "height": 900 },
    "safeAreaInsets": { "top": 0, "bottom": 0, "left": 0, "right": 0 },
    "navigationMode": "window",
    "shell": { "hasTabBar": false, "hasBackButton": false, "tabBarHeight": 0 },
    "user": { "nickname": "User" },
    "locale": "he",
    "dir": "rtl",
    "permissions": ["microphone"],
    "appId": "my-app",
    "offline_token": "",
    "granted_capabilities": ["os.kv.set", "os.kv.get"],
    "windowId": "win_42"
  }
}
```

- `theme` is **always** `"smoothie"` inside an iframe — the XP easter egg stops at the window frame (MAN-235). Style off `appearance` (`light` / `dark`) and `accent` instead.
- `granted_capabilities` is sent **only to v2 apps** — the install's admin-approved grant list. `permissions` carries the manifest's `permissions[]` array (browser features such as `microphone`).
- `offline` appears only when the manifest declares an `offline` block; `deepLink` when the window was opened from a notification, an `?open=` link, or another app's "open in source".
- `locale` (`"en"`, `"ru"` or `"he"`) and `dir` (`"ltr"` / `"rtl"`) are the language the person chose in ManAurum (MAN-2289). The shell posts `manaurum:locale-change` with `{locale, dir}` once when the window becomes ready and again whenever the person switches language. SDK 2.3.0 reads neither, so take them from your own listener (behind the sender check) and set `<html lang dir>` from them — the whole path is in "The person's language" below.

**Platform fields** (in `manaurum:init`; `manaurum:device-change` repeats all but `shell`):

| Field | Desktop | Mobile |
|-------|---------|--------|
| `platform` | `"desktop"` | `"mobile"` |
| `device` | `"desktop"` | `"mobile"` (older name, prefer `platform`) |
| `safeAreaInsets` | All zeros | Device notch/home indicator insets |
| `navigationMode` | `"window"` | App's declared `navigationPattern` |
| `shell.hasTabBar` | `false` | `false` (tab bar hidden when app is open) |
| `shell.hasBackButton` | `false` | `true` |
| `shell.tabBarHeight` | `0` | `0` (tab bar hidden when app is open) |

### What your app must reply

```js
// inside your `message` listener, once the sender passed the check below
event.source.postMessage({ type: 'manaurum:ready' }, event.origin);
```

**Within 10 seconds of the window opening** — `READY_TIMEOUT_MS = 10_000` (`IframeAppHost.tsx`). Miss it and the shell paints an overlay across your UI: *"App is not responding — No `manaurum:ready` received within 10s"* (`:792-794`). Your app is still running underneath; the user just cannot see or use it.

For the shell to accept the reply, all of these must hold (`:375-380`):

1. `event.origin` equals the origin the shell derived for your entrypoint. Serve from the host the platform expects; a BYO app on a host that doesn't match `runtime.entrypoint` has every message silently dropped.
2. `event.source` is the iframe's own `contentWindow`. Post from your top-level document — a message relayed from a nested iframe or a worker is rejected.
3. `data.type` is a string starting with `manaurum:`.

A `payload` is optional; the shell reads none. (The v2 SDK sends `{ sdk_version: '2.3.0' }`.)

### The pattern that actually shipped

An SPA whose bundle is deferred can miss `manaurum:init` entirely — the listener does not exist yet when the shell posts. The fix that landed for the first-party app **Libi** (MAN-1321) is belt-and-braces: an inline listener in `<head>`, plus one proactive announcement after mount.

```html
<!-- index.html <head> — alive before the deferred module bundle loads -->
<script>
  // Trust the shell, not the first sender (MAN-2506).
  var SHELL_ORIGINS = ['https://manaurum.com', 'https://app.manaurum.com'];
  // templates/preview.py frames the page from its own loopback origin.
  if (/^(127\.0\.0\.1|localhost|\[::1\])$/.test(location.hostname)) SHELL_ORIGINS.push(location.origin);
  window.addEventListener('message', function (e) {
    if (!e.data || typeof e.data.type !== 'string' || e.data.type.indexOf('manaurum:') !== 0) return;
    // Core's injected session renewal checks its own messages; leave them be.
    if (e.data.type.indexOf('manaurum:session-') === 0) return;
    var trusted = e.source === window.parent && e.source !== window &&
      SHELL_ORIGINS.indexOf(e.origin) !== -1;
    if (!trusted) { e.stopImmediatePropagation(); return; }
    if (e.data.type === 'manaurum:init') {
      e.source.postMessage({ type: 'manaurum:ready' }, e.origin);
    }
  }, true);
</script>
```

```ts
// main.tsx — after ReactDOM.createRoot(...).render(...)
for (const origin of ['https://manaurum.com', 'https://app.manaurum.com']) {
  try {
    window.parent.postMessage({ type: 'manaurum:ready' }, origin);
  } catch {
    /* not embedded in the shell */
  }
}
```

**The listener's other lines.** It lets `manaurum:session-*` through because Core injects a session-renewal script into every v2 page that exchanges those with a Core frame of its own and checks them itself. The loopback line admits one more origin, the page's own, only when the page is served from `127.0.0.1` or `localhost`, so `templates/preview.py` (`manaurum-app/SKILL.md` → Step 3.5) can frame it; without it the preview reports "NO manaurum:ready". No deployed app is ever served from loopback. The `true` at the end registers it in the capture phase: inline and first, so a refused message never reaches the SDK.

**Read the payload in the same listener.** The version in `manaurum-app/SKILL.md` → Step 2.5 also writes `payload.appearance` and `payload.accent` onto `<html>` as `data-appearance` / `data-accent`, on `manaurum:init` and again on every `manaurum:theme-change`, which the shell posts whenever the user changes either; every colour token in the starter's `app.css` keys off those two attributes and nothing else. The two belong in one listener because they arrive in one message. Answering the handshake and ignoring the payload is a shipped bug, not a shortcut: the app comes up, the window works, and it renders in its own palette inside a dark desktop — which is what a user sees first. The starter's `index.html` is that same script plus a `prefers-color-scheme` default for the standalone URL, `manaurum:device-change`, and the `window.__manaurum` context object the rest of that file reads — copy the whole block rather than retyping it.

A proactive `manaurum:ready` is safe: the shell registers its listener when the host component mounts, before it sends `init`. Post it once per shell origin rather than to `'*'`; the post whose origin is not the parent's is not delivered, and Chrome logs a console error for it ("target origin provided … does not match"). That error is expected.

If you load `manaurum-v2.mjs` and call `ManaurumV2.init()`, the SDK answers for you, but only *after* `manaurum:init` arrives. **SDK 2.3.0 does not check who sent it.** It adopts whichever window posts `manaurum:init` as its shell, again on every `init` (the latest sender wins), replies to that window's origin, and sends that window your Drive pick requests (see `app.pickFromDrive()` below). Keep the inline listener above in every app that loads the SDK. It stops every message it refuses, so the SDK never sees one from anybody but the shell, as long as it is registered **before** the SDK's listener: inline at the top of `<head>`, ahead of any module.

> **The trap.** Your standalone URL `https://<slug>.apps.manaurum.com/` works perfectly without the handshake — no shell, no timeout, no overlay. The failure appears *only* inside the desktop window and the mobile home screen, which is where your users are. Libi shipped this way and needed a follow-up release (MAN-1321). Test from the desktop, not just from the tab.

### Cross-origin rules (v2 specifically)

A v2 app served from `<slug>.apps.manaurum.com` is a **different origin** from the shell at `manaurum.com`. Consequences:

- postMessage is the only channel. No shared DOM, no shared `localStorage`, no `document.domain` tricks.
- You cannot read the shell's origin from inside the frame, so check it: act on a `manaurum:*` message only when `event.source === window.parent` and `event.origin` is `https://manaurum.com` or `https://app.manaurum.com`. Use both origins, never `www.`, and never a `*.manaurum.com` pattern, because every v2 app is a `*.manaurum.com` page and may frame yours. Not just one of them either: an app that pinned the apex stopped hearing the shell when it moved to `app.` and never became ready. Never adopt the origin of whoever posts `manaurum:init`: an unauthenticated sender then becomes your shell. SDK 2.3.0 does exactly that, on every `init`, which is why the inline guard above has to run before it.
- The shell posts `manaurum:init` with your origin as `targetOrigin`, so no other embedder can receive it.
- The iframe sandbox is `allow-scripts allow-forms allow-same-origin` (`iframeHostPolicy.ts`). `allow-modals` is never emitted — `alert()` / `confirm()` / `prompt()` are dead in the shell (and work fine on your standalone URL, so "it worked in my browser" proves nothing). Nor are `allow-downloads` or `allow-popups`, and `allow` never delegates `clipboard-write`: downloads, `target="_blank"`, `window.open()` and `navigator.clipboard.writeText()` all fail in the window. What to do instead: `design.md` → "Window rules".
- Browser features are delegated through the iframe `allow` attribute only when your manifest declares them in `permissions[]` (`:197-206`, and the `allow` attribute at `:887`). See `references/v2-platform.md`.

### Which messages a v2 app may send

Window framing only. `V2_ALLOWED_MESSAGES` (`frontend/src/components/window/iframeHostPolicy.ts`):

| Type | Effect |
|---|---|
| `manaurum:ready` | the handshake above |
| `manaurum:set-title` | `{ title }` — rename the window |
| `manaurum:resize` | `{ width, height }` — resize the window |
| `manaurum:close` | close the window |
| `manaurum:toast` | `{ type: 'success' \| 'error' \| 'info', message }` |
| `manaurum:active-record` | `{ entity_type, record_id, record_title? }` — tell the OS which record the user is looking at (camelCase also tolerated) |
| `manaurum:drive-pick` | open the shell's Drive picker — see `app.pickFromDrive()` below |
| `manaurum:diagnostic` | `{ code?, message }` — the SDK's own self-diagnosis (the layout guard); lands in the shell's diagnostic log |

None of these are permission-gated for v2 — they are framing, not data access.

**Rejected outright** — every type starting with `manaurum:storage-`, `manaurum:file-`, `manaurum:db-`, `manaurum:share-`, `manaurum:shared-`, `manaurum:notification`, `manaurum:reminder`, `manaurum:task-suggestion`, `manaurum:ai-` (`V2_REJECTED_MESSAGE_PREFIXES`, same file). Those are the retired v1 bridge. From a v2 iframe the shell refuses them and, when the message carried a `_reqId`, replies on the matching `*-response` channel with:

```json
{ "ok": false, "error": "v2 apps call capabilities via app.fetch() to their own backend, not via postMessage. (manaurum:storage-get)" }
```

`manaurum:notification` / `reminder` / `task-suggestion` have no response channel, so they are dropped with nothing sent back — the call just never resolves. Do the equivalent work over HTTP: your container calls the capability gateway.

`manaurum:ai-*` is answered on `manaurum:ai-response`. Use `os.ai.*` through the gateway instead.

Any other `manaurum:*` type (not framing, not a v1 verb) is ignored: the shell logs it and sends nothing back.

---

## The person's language

The person picks the interface language in ManAurum's settings: English, Russian or Hebrew (`LOCALES`, `frontend/src/i18n/config.ts:14`). Hebrew is written right to left (`LOCALE_DIRECTION`, `:20-24`). An app built from the starter follows that choice, and switches while it is open.

**Where it lives.** On the person's account, in every workspace: `user_profiles.preferred_language` (`backend/app/models/user_profile.py:31`), the `language` preference, where `""` means follow the browser (`backend/app/services/preferences.py:284-296`). The shell resolves the language it shows from its own `manaurum_locale` cookie, then localStorage, then the browser's languages, and on a device with none of those takes the account's value (`frontend/src/i18n/locale.ts:76-84`, `frontend/src/i18n/index.tsx:129-156`). A switch writes the cookie, localStorage and, best effort, the account (`index.tsx:92-100`, `:167-172`). The cookie is host-only on the shell's origin: an app at `<app_id>.apps.manaurum.com` cannot read it.

**How an app gets it: from the window, and only there.**

| When | Message | Carries |
|---|---|---|
| the window opens | `manaurum:init` | `locale` and `dir`, among the other fields above |
| once when the window becomes ready, then whenever the person switches | `manaurum:locale-change` | `{ locale, dir }` |

(`IframeAppHost.tsx:309-314`, `:603-616`.) `locale` is `en`, `ru` or `he`; `dir` is `ltr` or `rtl`. Take `dir` as sent rather than deriving it from a language list of your own. SDK 2.3.0 passes neither on: it drops both from its context and has no handler for `manaurum:locale-change` (MAN-3233). So read them in the inline listener, behind the sender check, next to the appearance.

**What the app does with it.** All four are in the starter's `index.html` and `app.css`, and `check_ui.py` fails on the first and the last:

1. Write `locale` to `<html lang>` and `dir` to `<html dir>`, on `manaurum:init` and on every `manaurum:locale-change`. `lang` is what screen readers, hyphenation and font fallback follow; `dir` mirrors the page. The starter also copies both onto `window.__manaurum` and fires a `manaurum-locale` event, like its appearance and device events.
2. Keep every word a person reads in one table per language — the starter's `STRINGS = { en, ru, he }` and `t(key)`, with `data-i18n="key"` on static text — and re-render on the event. A locale the app has no strings for reads as English, left to right; a key missing from one table reads as English too, which is a Hebrew screen with one English sentence in it (the starter's tests fail on that).
3. Format numbers and dates with `Intl` and the OS's own tags — `en`, `ru-RU`, `he-IL` (`INTL_LOCALE`, `config.ts:27-31`) — never by hand.
4. Use logical CSS (`margin-inline-start`, not `margin-left`) so the page mirrors by itself: `references/design.md` → "Right to left".

**A standalone tab** hears no shell. Guess from `navigator.languages` (the first of en / ru / he, else English), as the starter does. Your server also sees the browser's `Accept-Language`: the gateway forwards request headers other than hop-by-hop, auth and Core's own (`_filter_request_headers`, `backend/app/routes/v2_app_gateway.py:639-650`). Both are the *browser's* language — inside the window as well — which need not be the one chosen in ManAurum.

**What cannot learn it.** Core hands the person's language to nothing outside the window. It is not in the `user_context` JWT (`backend/app/services/v2_apps/user_context_jwt.py:119-131`), not in the person pass (`person_pass.py:85-103`), and no capability returns it. So **your server, the Assistant's calls to your `/agent` routes, and a standalone tab cannot learn the language chosen in ManAurum**; carrying it there is not yet built (MAN-3244). When your server must write text for a person in their language (a reply it renders, an export), have the page send `locale` with the request. Text the server writes with no page behind it — what it answers the Assistant, a scheduled message — is in a language you pick, and the README says which.

---

## Platform v2 — frontend SDK (`manaurum-v2.mjs`)

An ES module served from `https://manaurum.com/sdk/manaurum-v2.mjs` (also at `/sdk/manaurum-v2.mjs` on any Manaurum host). It is **thin on purpose**: it does the handshake, exposes the shell's theme/device context, wraps `fetch` with sane defaults, and opens the Drive picker. It has **no** capability client — v2 capabilities are called by your *container*, not by your page.

```js
import { ManaurumV2 } from 'https://manaurum.com/sdk/manaurum-v2.mjs';

const app = ManaurumV2.init();   // singleton; safe to call repeatedly

app.onReady((ctx) => {
  document.documentElement.dataset.appearance = ctx.appearance; // 'light' | 'dark'
  render(ctx.user?.nickname);
});

const res    = await app.fetch('/api/orders');
const orders = await res.json();
```

`ManaurumV2.init()` constructs the app instance on first call and returns the same instance thereafter. The constructor immediately registers the `message` listener, so calling `init()` early (before your UI mounts) is what makes the handshake land in time.

### Exported surface

The module exports two names. `ManaurumV2` has exactly two members: `init(options?)` and the `version` getter. `findClippedContent(doc)` is the layout guard's own test, exported so it can be tested without a browser: it returns `{ element, selector, hiddenPx, boxHeight }` for the outermost element that hides content with nothing to scroll it, or `null`.

**The layout guard.** After the handshake the SDK watches the page (resize, and DOM mutations for its first 40 checks; at most once a second) and console-errors `content is clipped and nothing scrolls` with the element's selector, once per element, also reporting it to the shell as `manaurum:diagnostic`. `app.checkLayout()` runs it now — call it right after rendering a view you know is long. `init({ layoutCheck: false })` turns it off.

**Callbacks** — all fire-and-forget; a throwing callback is caught and logged as `[ManaurumV2]`, it does not break the SDK.

| Method | Fires |
|---|---|
| `app.onReady(cb)` | once `manaurum:init` arrives, with the context object. **If init already arrived, `cb` runs immediately** — registering late is safe. |
| `app.onThemeChange(cb)` | on `manaurum:theme-change`, with the theme name. Note: the SDK listens for `manaurum:theme-change`, not the legacy `manaurum:theme`. |
| `app.onDeviceChange(cb)` | on `manaurum:device-change`, with `{ device, platform, screen, safeAreaInsets, navigationMode }`. The shell fires it only when the mobile/desktop classification or the safe-area insets actually change — a same-class resize is a no-op. |
| `app.onAuthFailure(cb)` | when an `app.fetch(...)` response has status **401**, with the `Response`. The SDK does **not** redirect — you own the "session expired, reload to log in" UX. The caller still receives the Response. |

**Context and getters**

| Member | Value |
|---|---|
| `app.context` | the whole context object, or `null` before init |
| `app.theme` | `'smoothie'` (always, inside the shell) or `null` |
| `app.appearance` | `'light'` / `'dark'` or `null` |
| `app.accent` | e.g. `'core-blue'` or `null` |
| `app.device` | `'mobile'` / `'desktop'` — defaults to `'desktop'` before init |
| `app.platform` | `'mobile'` / `'desktop'` — mirrors `device` today, kept separate for a future native/web split |
| `app.isMobile` | `true` only when `device === 'mobile'`; `false` before init |
| `ManaurumV2.version` | the SDK version string — useful in diagnostic logs |

`app.context` is built from the init payload with defaults: `{ theme, appearance, accent, user, permissions, windowId, appId, device, platform, screen, safeAreaInsets, navigationMode, shell }`.

Two gaps worth knowing:

- **`granted_capabilities` is not in `app.context`.** The shell sends it; SDK 2.3.0 does not read it. Same for `offline` and `deepLink`. If you need them, add your own `window.addEventListener('message', …)` for `manaurum:init` / `manaurum:deep-link` alongside the SDK, and act only on what passed the sender check above (register it after the inline guard, which then filters for it too).
- `appId` falls back to parsing `<slug>.apps.manaurum.com` out of `window.location.hostname` when the shell omits it — so a hand-loaded test page on any other host gets `appId: null`.

### `app.fetch(path, init?)`

Calls your own backend through the Core gateway. Returns a normal `Response`, so `.json()` / `.text()` / `.blob()` all work.

```js
const res = await app.fetch('/api/orders', {
  method: 'POST',
  body: JSON.stringify({ sku: 'A1' }),
  headers: { 'Content-Type': 'application/json' },
});
```

- `path` must be a `/`-rooted relative path (stays same-origin, so Traefik routes it to Core → your container) **or** an absolute URL (passes through unchanged, straight from the browser: the gateway, `egress_allowed_hosts` and your session play no part, and the other host's CORS decides). It still defaults to `credentials: 'include'`, so an API that answers `Access-Control-Allow-Origin: *` fails unless you pass `{ credentials: 'omit' }`. Anything else throws `TypeError`.
- Defaults applied: `credentials: 'include'` so the Manaurum session cookie reaches Core, and `Accept: application/json` unless you set it. Pass `{ credentials: 'omit' }` for an explicit anonymous probe.
- **Your relative path must be declared in `manifest.runtime.api_routes`** or the gateway answers `404 route_not_declared` and your container never sees the request. Routes declared `auth: "user"` get a 60s `user_context` JWT minted by Core and injected as `X-Manaurum-User-Context`; `auth: "anonymous"` routes are proxied with none. The end user's own bearer is never forwarded to your container.
- **Retries are off by default.** Opt in per call with an SDK-specific `retry` key, which is stripped before the init dict reaches `window.fetch`:

  ```js
  await app.fetch('/api/report', { retry: { attempts: 3, baseDelayMs: 200 } });
  ```

  Only `GET` / `HEAD` / `OPTIONS` retry unless you pass `retry: { …, force: true }` — replaying a POST without an idempotency key risks a double write. Only 5xx and 429 are treated as transient; other 4xx return immediately. Backoff is exponential with full jitter (`200ms`, `400ms`, `800ms`…), capped at 5s per wait. A thrown network error is re-thrown on the last attempt.
- On a 401 the `onAuthFailure` callbacks fire before the Response is returned.

### Sessions in a standalone tab

The `manaurum_session` cookie on `.manaurum.com` is good for 15 minutes from when it was issued; the refresh credential behind it lasts 7 days and never leaves Core's origin. Core renews the session for you (MAN-2541). Every HTML document the gateway serves gets a script injected ahead of your own that wraps `window.fetch`: when a same-origin `/api/*` call to an `auth: "user"` route comes back `401` with `X-Manaurum-Session: required`, it renews — through the shell inside the desktop window, through a hidden `<core>/v2-session` frame in a standalone tab — and retries once. The retry is safe even for a `POST`: a `401` carrying that header came from the gateway, so the request never reached your container. When the refresh credential has expired too, the `401` comes back to you and `app.onAuthFailure` fires. If the person signed in as someone else in the meantime, the call throws instead of retrying.

`app.fetch` goes through the same `window.fetch`, so it is covered. These are not, and in a standalone tab each of them stops recognising the person once the cookie lapses:

- `EventSource` and `XMLHttpRequest` — only `fetch` is wrapped. Read an authenticated stream with `fetch` and a body reader.
- `auth: "optional"` routes are covered differently (Core MAN-3200): there is no `401` to ride, so a member whose cookie lapsed is served as a guest with `X-Manaurum-Session: stale`. The script renews and repeats a `GET`/`HEAD` once; a `POST` already reached you as a guest and is not repeated.
- `auth: "anonymous"` routes — the gateway never answers them with the session `401`, so there is nothing to renew. An app that carries its own pass on such routes owns that pass's expiry.
- A call with `credentials: 'omit'`, an `Authorization` header of your own, a streaming request body, or a cross-origin URL. These go out untouched.

And three answers the wrapper itself can give. A `401 {"detail": "authentication_required"}` with no request sent, when the tab has no session to renew (a guest). A thrown `Error('Manaurum session renewal is temporarily unavailable. Try again.')` when Core could not be asked, before or after the first attempt. And a thrown `Error('Manaurum session changed. Reopen this app.')` when the person signed in as someone else. Handle all three where you handle a `401`.

### `app.pickFromDrive({ accept? })`

Opens the OS file picker over the **user's** Drive (MAN-608 B3). The *shell* renders the picker and the *user* chooses; your app never enumerates the Drive and never needs a Drive-listing capability for this path.

```js
const res = await app.pickFromDrive({ accept: ['image/', 'application/pdf'] });
if (!res.cancelled) {
  const bytes = await fetch(res.files[0].download_url);
}
```

- `accept` is an optional list of MIME types or prefixes ending in `/`. The shell truncates it to 20 entries.
- Resolves to `{ cancelled: true }` if the user cancels, if another pick is already open (`picker_busy`), or if nothing answers within **120 s**. Otherwise `{ files: [...] }`.
- Each handle is `{ file_id, filename, mime_type, size_bytes, download_url, expires_at }`. `download_url` is attachment-pinned and short-lived (~5 min) — fetch it promptly and ask again rather than caching it.
- Wire: the SDK posts `manaurum:drive-pick` with a `_reqId` and awaits `manaurum:drive-pick-response`. It only works inside the shell — outside it there is no shell to post to and the promise resolves `{ cancelled: true }` after the timeout.
- SDK 2.3.0 sends the request (and its `_reqId`) to whichever window last posted it `manaurum:init`, and accepts a response carrying that id from any window. Without the inline sender check above, a page that framed your app and posted `init` receives the pick and can answer it with download URLs of its own choosing.

### What this SDK deliberately does not do

- **No capability client.** There is no `app.capability(...)`. Capabilities are called server-side by your container with `Authorization: Bearer ${MANAURUM_RUNTIME_TOKEN}` against `{MANAURUM_CORE_URL}/api/capability/<name>`. See `references/capabilities-reference.md`.
- **No storage / db / files / ai bridge.** Every `manaurum:storage-*`, `manaurum:db-*`, `manaurum:file-*`, `manaurum:ai-*` message belongs to the retired v1 bridge and is rejected for v2 frames.
- **No language.** 2.3.0 drops `locale` and `dir` from its context and has no handler for `manaurum:locale-change` (MAN-3233). Read them in your inline listener — "The person's language" above.
- **No window-framing helpers.** `set-title` / `resize` / `close` / `toast` are allowed for v2 apps, but SDK 2.3.0 exposes no methods for them — post them yourself with `window.parent.postMessage({ type, payload }, shellOrigin)`.

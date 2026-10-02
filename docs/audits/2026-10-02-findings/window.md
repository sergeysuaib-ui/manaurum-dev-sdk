# Dimension `window`: frontend, window handshake, window restrictions, JS SDK

SDK = `C:\dev\wt\sdk-audit` @ 6f52dce (3.1.0). Platform = 285c8a8 (SNAP plus `git show`).
Paths prefixed `fw/` = `frontend/src/components/window/`, `sdk/` = `frontend/public/sdk/`.

## Message matrix (postMessage, both directions)

| Message | Dir | Payload (platform) | Platform gate | In SDK? | Payload correct in SDK? |
|---|---|---|---|---|---|
| `manaurum:init` | shell→app | theme, appearance, accent, device, platform, screen, safeAreaInsets, navigationMode, shell{}, user{nickname}, **locale, dir**, permissions, appId, offline?, offline_token, granted_capabilities (v2), windowId, deepLink? (`IframeAppHost.tsx:291-345`) | targetOrigin = entrypoint origin | yes, sdk-api.md:35-62 | **no**: `locale`/`dir` missing (W-03) |
| `manaurum:theme` (legacy) | shell→app | {theme} (`:594`) | after ready | mentioned (sdk-api.md:192, starter) | ok |
| `manaurum:theme-change` | shell→app | {theme, appearance, accent} (`:596-599`) | after ready | yes | ok |
| `manaurum:locale-change` | shell→app | {locale, dir} (`:611-614`) | after ready | **no** (W-03) | — |
| `manaurum:device-change` | shell→app | device, platform, screen, safeAreaInsets, navigationMode (`:640-646`) | class or inset change only | yes | ok |
| `manaurum:deep-link` | shell→app | deepLink obj (`:669-672`) | after ready | yes (capabilities-reference.md:571) | trigger is narrower in SDK (LOW, W-13) |
| `manaurum:drive-pick-response` | shell→app | {_reqId, ok, files…} / {ok:false,error:'picker_busy'} (`:507-523`) | — | yes | ok |
| `manaurum:{storage,file,db,ai}-response` | shell→app | {_reqId, ok:false, error} (`:424-440`) | v1-verb reject | yes | ok |
| `manaurum:session-response` | shell/relay→app | {id, outcome} (`lib/v2/sessionBridge.ts:66`) | origin + source | narrative only (sdk-api.md:242) | n/a, it's internal |
| `manaurum:ready` | app→shell | ignored | origin = expectedOrigin, source = iframe (`:375-380`) | yes | ok |
| set-title / resize / close / toast / active-record / drive-pick / diagnostic | app→shell | as in sdk-api.md:136-145 | `V2_ALLOWED_MESSAGES` (`iframeHostPolicy.ts:120-138`) | yes | ok, all 8 match |
| v1 verbs (storage-/file-/db-/share-/shared-/notification/reminder/task-suggestion/ai-) | app→shell | — | rejected (`iframeHostPolicy.ts:146-170`) | yes (sdk-api.md:149-157) | ok |
| `manaurum:session-request` | injected runtime→shell | {id, op} | sessionBridge, but main listener logs it as an error (W-12) | no | n/a |

`manaurum-v2.mjs` exports vs sdk-api.md: `ManaurumV2.{init(options), version}`, the `findClippedContent` named export, and instance `onReady/onThemeChange/onDeviceChange/onAuthFailure/fetch/context/theme/appearance/accent/device/platform/isMobile/pickFromDrive/checkLayout`, static `version`. sdk-api.md matches on fetch (defaults, retry, 401 fan-out, TypeError), pickFromDrive (120 s, 20-entry truncation, cancel shape), onReady and getters. Gaps are in W-03 and W-11. The import URL `https://manaurum.com/sdk/manaurum-v2.mjs` is correct: `/sdk` stays on the apex (`frontend/src/lib/canonicalHost.ts` APEX_PASSTHROUGH_PREFIXES '/sdk' @285c8a8).

Window restrictions verified as correct: sandbox triple only (`iframeHostPolicy.ts:16-40`); `allow` = microphone/camera only, only on a platform-chosen src (`:66-113`); no allow-modals/popups/downloads/top-navigation. The claims at SKILL.md:725 and :733-741 and sdk-api.md:129 about alert/confirm/prompt/print/beforeunload, downloads, `_blank`/`window.open` and `clipboard.writeText` all follow from those attributes. The only false statement in that section is the CSP "verbatim" claim (W-09).

---

## Findings

### W-01 HIGH: every SDK handshake snippet is the pattern MAN-2506 forbids ("trust the shell, not the first sender")
- SDK: `templates/v2-starter/src/static/index.html:63-84` accepts `manaurum:init` from any sender, stores its payload, and replies to `event.origin`. It checks neither source nor origin. The same unguarded pattern is at `SKILL.md:310-324`, `sdk-api.md:99-104`, and `sdk-api.md:127`, which recommends to "capture `event.origin` off `manaurum:init` and reply to exactly that".
- Platform: `docs/handoff/V2_DEVELOPER_GUIDE.md:1316-1325 @285c8a8` says to accept `manaurum:*` only when it comes "from the parent window **and** from one of the shell's origins… Never store `event.origin` from whatever posts the first `manaurum:init`". The rule is repeated at `frontend/src/app/developers/page.tsx:485` and implemented at `manaurum-cli-py/.../index.html.template:28-36` (`SHELL_ORIGINS = ['https://manaurum.com','https://app.manaurum.com']`). The grep finds no mention of MAN-2506 or SHELL_ORIGINS anywhere in the SDK.
- Why it matters: v2 responses get `frame-ancestors 'self' https://manaurum.com https://*.manaurum.com` (`backend/app/main.py:867-869 @285c8a8`). Any other app at `*.apps.manaurum.com` can therefore frame a starter-built app and feed it a forged init (appearance, granted_capabilities shown to the user, appId, device).
- Verdict: CONFIRMED (the rule exists, the SDK lacks it). Impact: every app copied from the starter ships the handshake the platform guide calls unsafe. Fix (SDK): in the starter and the three snippets, gate on `event.source === window.parent && SHELL_ORIGINS.includes(event.origin)` with the list taken from the CLI template. Note that the SHELL is moving to `app.manaurum.com` (MAN-385/MAN-2499), so the list needs both hosts. Related: MAN-2506.

### W-02 HIGH (platform): `manaurum-v2.mjs` itself trusts the first sender
- Platform: `sdk/manaurum-v2.mjs:235-250 @285c8a8` checks no origin or source and overwrites `this._shell = event.source; this._shellOrigin = event.origin` on every `manaurum:init`. `pickFromDrive` (`:584-597`) accepts `drive-pick-response` from any window.
- SDK repeats it as a virtue: `sdk-api.md:127` "…which is what the v2 SDK does", and `:118`.
- Impact: a framing `*.apps.manaurum.com` page can become the SDK's "shell". It then receives `manaurum:drive-pick` and can answer with arbitrary `download_url`s that the app fetches as "the user's file". This is the exact anti-pattern the platform's own guide names. Verdict: CONFIRMED (code). Fix: platform, to apply the SHELL_ORIGINS + `window.parent` gate in mjs; SDK, to stop calling the mjs behaviour correct. Related: MAN-2506. Check this against the W-14 frame-ancestors question.

### W-03 MEDIUM: language (`locale`, `dir`, `manaurum:locale-change`, MAN-2289) is absent from the SDK, and the platform mjs drops it
- Platform: init carries `locale` ('en'|'ru'|'he') and `dir` (`fw/IframeAppHost.tsx:309-314 @285c8a8`), and the shell posts `manaurum:locale-change {locale, dir}` on change (`:607-616`). `manaurum-v2.mjs:251-274` builds `context` field by field, so `ctx.locale` and `ctx.dir` are undefined. There is no locale listener and no `onLocaleChange`. V2_DEVELOPER_GUIDE, the developers page and the CLI template never mention locale either (grep).
- SDK: the grep finds "locale" only in an unrelated line, capabilities-reference.md:119. The sdk-api.md:37-57 payload example and the :209/:213 context and "gaps" lists omit it. `preview.py build_init` (:237-264) omits it too.
- Impact: apps hardcode one language, which is exactly the finance-v2 failure MAN-2289 cites (`IframeAppHost.tsx:85-88`), and a Hebrew user gets LTR. Verdict: CONFIRMED. Fix (both): document `locale`/`dir`/`locale-change` in sdk-api.md, the starter (set `<html lang dir>`) and the preview payload. On the platform side, add them to mjs context plus an `onLocaleChange`.

### W-04 HIGH: v2-platform.md:24 still says `runtime` is "not strict". This is the MAN-1899 sentence 3.1.0 claimed to have removed
- SDK: `skills/manaurum-app/references/v2-platform.md:24`: "The `runtime` and `metadata` sub-objects are *not* strict. Unknown keys there validate silently… a typo like `runtime.byo_endpoint_url` passes". This contradicts `SKILL.md:292`, `v2-platform.md:310`, `manaurum-setup/SKILL.md:300` and CHANGELOG.md:19-21 ("Five places here still said it was not strict").
- Platform: `backend/app/services/_schemas/manifest_v2.schema.json:92-96 @285c8a8` gives `runtime` `"additionalProperties": false`. `metadata` (`:583`) is indeed open.
- Verdict: CONFIRMED. The 3.1.0 fix missed one site. Fix (SDK): rewrite :24 to say runtime is strict and metadata is open. Add `not strict` to a `check_repo.py` banned-phrase list.

### W-05 HIGH: `permissions` enum is documented as `["microphone"]` in five places. Camera has shipped (MAN-1920)
- SDK: `v2-platform.md:104` "Enum today: `["microphone"]` (MAN-1316)". Same claim at `SKILL.md:219`, `manaurum-setup/SKILL.md:175-176`, `references/publishing.md:64`, and capabilities-reference.md:424 by implication. `SKILL.md:733` meanwhile says "delegates only `microphone` and `camera`".
- Platform: `manifest_v2.schema.json:318-328 @285c8a8` has enum `["microphone","camera"]`. `fw/iframeHostPolicy.ts:66-69` has `IFRAME_ALLOW_FEATURES = {microphone, camera}` (commit 413731243, 2026-09-02).
- Verdict: CONFIRMED. A fact true once is now false in four or five files, which is the MAN-1899 pattern. Impact: a scanner or photo app concludes camera is impossible, or omits `permissions:["camera"]` so `getUserMedia({video})` is blocked in the window. Fix (SDK): state the enum once, in v2-platform.md, and link to it from the other places. Also say permissions are refused when `runtime.mode` is `byo` (schema `:321`).

### W-06 MEDIUM: `platforms.mobile.entrypoint` is documented as a v2 feature, but the shell ignores it for v2
- SDK: `v2-platform.md:94` says "`platforms.mobile.entrypoint` is a separate HTTPS URL the shell loads on mobile devices."
- Platform: `fw/IframeAppHost.tsx:176-191 @285c8a8`. The mobile entrypoint is consulted only in the `else if` branch of `if (isV2)`, which means v1 manifests only. `iframeHostPolicy.ts:80-82` and schema `:321` both say "on a v1 manifest". The schema's own description at `:302` ("becomes the iframe src on phones") is misleading too.
- Verdict: CONFIRMED. Impact: a developer builds a separate mobile site that never loads. Fix: SDK, say it is ignored for v2 (use `device`); platform, fix the schema description at `:302`.

### W-07 HIGH: design.md and app.css say the shared token file is broken. It was fixed on 2026-09-06 (MAN-2367)
- SDK: `design.md:330-333`: "the token file documents a hostname that does not resolve, and it defines 6 of the 8 accents… `amber` and `green` silently fall back to blue". `templates/v2-starter/src/static/app.css:26-27` repeats it. `design.md:325-326` adds that app.css uses "the same token names" so "adopting it later is one `<link>`".
- Platform: `library/tokens/tokens.css @285c8a8` (served at `/api/library/tokens.css`, `backend/app/routes/library.py:66,218`). Its header (lines 12-15) now names `https://manaurum.com/api/library/tokens.css` and says library.manaurum.com "does not resolve". Lines 119-127 define all 9 accents, including amber, green and verdant. Commit 9166b92c5 "MAN-2367 … Closes the MAN-1401 decision" injects `/manaurum-tokens.css` into generated apps. Name drift: the starter's `--app-bg`, `--surface-input` and `--font-mono` do not exist in tokens.css, which uses `--surface-wallpaper`. So a one-line `<link>` swap would leave the page background and the inputs undefined.
- Verdict: CONFIRMED. Fix (SDK): drop the "6 of 8 / bad hostname" rationale from both files and correct the "same names" claim, either by listing the three renames or by aligning the starter to `--surface-wallpaper`. MAN-1401 is still "In Progress" in Linear, so "open decision" may stay, but cite MAN-2367 / MAN-2374.

### W-08 MEDIUM: `preview.py` fails an app that follows the platform's handshake rule
- SDK: `templates/preview.py:218` posts init from `http://127.0.0.1:8765` (same origin). Its ready listener `:157-163` checks nothing.
- Platform: the MAN-2506 guard in `manaurum-cli-py/.../index.html.template:31-36 @285c8a8` drops anything not from the shell origins, using `stopImmediatePropagation`.
- Measured: `preview.py --app <CLI template>` in Chromium 152 shows "NO manaurum:ready - the shell would cover this app" and "appearance IGNORED… (read e.data.payload, not e.data)". `__manaurum.init === null`. The second badge's advice is also wrong for this cause.
- Verdict: CONFIRMED (run). Impact: once W-01 is fixed, the SDK's own preview reports the correct app as broken. That pushes developers back to the insecure handshake. Fix (SDK): add a `?shell_origin=` override, or document a dev-origin allowance, for example accepting `location.hostname === '127.0.0.1'` only behind an explicit flag. Make the ready listener check `e.source === app.contentWindow` the way the host does (`IframeAppHost.tsx:375-377`). Related: other preview deltas (no `locale/dir`, no theme-change/locale-change/device-change after ready, no `verdant`) are in W-03 and W-10.

### W-09 MEDIUM: "the rest of your CSP survives verbatim" is false for HTML responses
- SDK: `SKILL.md:727`: "only the framing directives are rewritten: the rest of your CSP survives verbatim". The same sentence's example (`connect-src 'self'` "that forgets your API origin") is moot, because the API is same-origin.
- Platform: `backend/app/services/v2_apps/session_recovery.py:24-50,100-105 @285c8a8`. On every HTML document the gateway rewrites `script-src`/`script-src-elem` (adds a nonce, strips `'none'`) and `frame-src` (adds `<core>/v2-session`), including `<meta http-equiv>` CSPs. It also injects a script ahead of the app's code, sets `cache-control: no-store`, and drops `etag`/`content-length`.
- Verdict: CONFIRMED. Impact: a developer who debugs a CSP or caching issue is told the headers are untouched. Fix (SDK): say the gateway also authorises its injected session script and relay frame, and forces `no-store` on HTML.

### W-10 LOW: the OS can send accent `verdant`; the SDK, starter and preview know 8 accents
- Platform: `frontend/src/stores/themeStore.ts:8,27 @285c8a8` includes `'verdant'`. Choosing the Verdant skin calls `setAccent('verdant')` (`settings/v2/PersonalizeSection.tsx:147`, `InterfacePanel.tsx:239`), and the accent persists after leaving the skin. This is gated by `experiment.verdant_skin`.
- SDK: `design.md:59-60` (8 values), `app.css:149-156` (no verdant rule, so it falls back to core-blue), `preview.py:88`.
- Verdict: CONFIRMED, limited to experiment tenants. Fix (SDK): add a `[data-accent="verdant"]` row copied from tokens.css:127, or describe the fallback as intended.

### W-11 LOW: the sdk-api.md "Exported surface" section is incomplete, and its line citations are stale
- `sdk-api.md:185`: "`ManaurumV2` (the module's only export) has exactly two members". In fact mjs also exports `findClippedContent` (`manaurum-v2.mjs:136`). `init(options)` with `layoutCheck` and `app.checkLayout()` (`:693-696`) are missing from sdk-api.md; they appear only in design.md:162 and deploy SKILL:65.
- Line refs into `IframeAppHost.tsx`: `:316-371` (sendInit is 284-352), `:699-702` (onLoad 691-694), `:394-409` (checks 374-380), `:814-836` (overlay 789-811), `:210/:218-222/:919` (allow 204-206/887; the file has 899 lines). `sdk-api.md:270` tells developers to post to `shellOrigin` without saying where it comes from.
- Verdict: CONFIRMED. Fix (SDK): list the full surface, cite by symbol instead of line.

### W-12 LOW (platform): the session-renewal handshake floods the window's diagnostic log with false errors
- Platform: the injected runtime asks `check` before every `auth:"user"` fetch (`backend/app/services/v2_apps/session_runtime.js:117,137 @285c8a8`), posting `manaurum:session-request` to the parent. It is handled by `sessionBridge`, but the main listener runs `routeV2Message` → `'ignore'` → `addDiag('error', '… ignored — not part of the v2 shell protocol')` (`fw/IframeAppHost.tsx:442-444`; not in `V2_ALLOWED_MESSAGES`, `iframeHostPolicy.ts:120-138`). The log keeps 100 events (`:241`), so these lines push out real diagnostics such as the `content_clipped` one MAN-2112 relies on.
- Verdict: CONFIRMED (code). Fix (platform): treat `manaurum:session-request` as known-silent in `routeV2Message`.

### W-13 LOW: deepLink trigger documented too narrowly
- `sdk-api.md:62`: "`deepLink` only when the window was opened from a notification". Platform: a pending link from desktop links, phone navigation (MAN-2690) or generic item links (`IframeAppHost.tsx:106-108,341`). CONFIRMED. Fix: say "when the window was opened through a link (notification, item link, phone)".

### W-14 MEDIUM (platform, LIKELY): every v2 app can be framed by every other v2 app
- Platform: `backend/app/main.py:867-869 @285c8a8` sets `frame-ancestors 'self' https://manaurum.com https://*.manaurum.com` on the app surface. The CSP wildcard covers `evil.apps.manaurum.com`. The shell origins are only `manaurum.com` and `app.manaurum.com` (CLI template line 31). Being same-site, the framed app gets the user's `.manaurum.com` session cookie. That makes W-01 and W-02 reachable, and it enables cross-app clickjacking.
- Verdict: LIKELY (header confirmed; exploitation not tested). Fix (platform): narrow to the explicit shell origins (keep `'self'` if needed). SDK: no change beyond W-01.

### W-15 MEDIUM: the `check_ui.py` "no modal" rule flags the recommended replacement; it is mirrored in platform ui_lint
- SDK: `templates/check_ui.py:54` `MODALS = \b(alert|confirm|prompt)\s*\(` runs over all text, including strings.
- Platform: `backend/app/services/v2_apps/ui_lint.py:64,173 @285c8a8` (identical).
- Measured (venv, both linters): `await ui.confirm('Delete?')` (an in-app modal, the fix SKILL.md:729 prescribes), `modal.alert(msg)`, and the prose `placeholder="Write a prompt (what should the AI do?)"` each produce "alert/confirm/prompt…". `check_ui.py:53` `STYLE_PROP` also flags `bar.style.width = pct+'%'` and `el.style.setProperty('--progress', v)`, while `:49-50` explicitly calls `style="width:42%"` legitimate.
- Verdict: CONFIRMED. Impact: developers rename a correct helper or ignore the linter, whose own docstring (`:23-24`) calls that worse than no linter. Fix (both): match only a bare or `window.` call (`(?<![.\w])(?:window\.)?(alert|confirm|prompt)\s*\(`), scan with string literals stripped, and exempt `.style.setProperty('--`.

### W-16 LOW: the `@media max-width` ban rests on a wrong premise
- SDK: `design.md:277-278`: "An app window can be narrow on a desktop, and a phone opens your app full screen — a width query gets both cases wrong". `check_ui.py:56,268-270,306-308` fails on any `@media … max-width`. Platform ui_lint `:66,179` mirrors it (in markup only, so it never fires on `.css`; see W-17).
- Platform: `device` is the SHELL viewport class (`fw/IframeAppHost.tsx:264-265`, `window.innerWidth < MOBILE_BREAKPOINT` of the shell page). A narrow desktop window reports `desktop`, and only the iframe's own width query sees the narrow window. `@media (min-width)` is not flagged, so the rule is also trivially bypassed.
- Verdict: LIKELY (the platform fact is confirmed; the design intent may be deliberate). Fix: keep "use `data-device` for touch/back-button", but either allow width queries for fitting or reword the rationale.

### W-17 LOW: check_ui and the platform ui_lint have drifted
- `ui_lint.py:9-15 @285c8a8` says "mirror `templates/check_ui.py`… Keep the two in step". Rules only check_ui has: var()/`@media` in `.css` files, `.style.*`, unmarked interactive rows, more than one primary per view, `payload`, the uncentred cap. Rules only ui_lint has: skipping generated or minified bundles by content (`:97-111`; check_ui skips only `.min.`, so a committed Vite bundle in `src/static` fires everywhere), and an entry point taken from `frontend.entry_point` (check_ui hardcodes `index.html`, `:317`). The SDK never tells developers that ui_lint warnings come back on the deploy result (grep `ui_lint|MAN-2510` finds nothing).
- Token names: check_ui accepts any `--x` the app itself declares (`:123-131`). They are not derived from tokens.css or the design.md table, so "a name that is not here does not exist" (design.md:118) is not what the linter enforces. That is fine, but worth saying.
- Verdict: CONFIRMED. Fix (SDK): add the generated-file skip and a mention of deploy-time UI warnings. Fix (platform): port the missing rules or drop the "mirror" claim.

### W-18 MEDIUM (platform, LIKELY): the user's offline box token is handed to every app iframe
- Platform: `fw/IframeAppHost.tsx:335-338 @285c8a8` puts `offline_token: localStorage[offline_token]` in every init payload, v2 third-party apps included. `frontend/src/lib/accountStorage.ts:52` describes it as "Box-signed offline JWT (MAN-537)", a user credential for the Edge box. The mjs header (`:16-17`) promises the user's bearer never reaches app code.
- SDK: `sdk-api.md:53` lists `"offline_token": ""` and does not say what it is.
- Verdict: LIKELY. It is empty except on Edge-provisioned sessions, and its power on the box is unverified. Fix (platform): send it only to first-party or offline-declared apps, or scope it per app. SDK: document what it is, or omit it.

---

## Questions (no conclusive evidence)
- Q1. Does `document.execCommand('copy')` under user activation work in the sandboxed cross-origin frame? If so, SKILL.md:741 ("Show the value in a read-only field") has a better workaround than the one it gives. MAN-3201 covers the platform side.
- Q2. Tested and NOT a finding: whether the MAN-2506 capture-phase guard (`stopImmediatePropagation`) starves the injected session runtime of `session-response` from its hidden relay frame. In Chromium 152, at-target listeners fire in registration order, the runtime is injected first, and it received the message. It would break only if app code registered before the injected script, which `session_recovery.py:65-74` prevents.
- Q3. `sdk/test-harness.html @285c8a8` (linked from the host's error overlay, `IframeAppHost.tsx:834`) sends only legacy `manaurum:theme` and no theme-change/locale (`:209`). Should the SDK point to it, or is it legacy?

## Summary
Covered: the full postMessage protocol in both directions, the exports of mjs 2.3.0 against sdk-api.md, the sandbox/allow/CSP/frame-ancestors attributes, session recovery (MAN-2541), locale (MAN-2289), camera (MAN-1920), the MAN-2506 handshake rule, check_ui against ui_lint (run on test cases), preview.py against the real host (run in Chromium), and design tokens against tokens.css.
Biggest problems: the SDK teaches and ships the handshake MAN-2506 forbids (W-01), and the mjs does the same (W-02); locale is invisible end to end (W-03); two stale facts repeated across files (W-04 runtime "not strict", W-05 camera); and a stale token-file claim (W-07).
Not done: no prod/browser test of the shell itself, the mobile phone shell (MobileLayout) was not read, `WindowFrame.tsx` was not read (the scroll-ownership claim was checked against mjs and the SDK text instead), and manaurum.js (v1, retired) was not compared.

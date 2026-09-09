#!/usr/bin/env python3
"""Look at a Manaurum v2 app before you deploy it.

Serves your app's static files, answers every /api/* call with a stub, and
frames the whole thing the way the desktop shell does — so a headless
screenshot shows what a user would actually see, including the two failures
that never appear on the standalone URL: a missing `manaurum:ready`, and an
app that ignores the shell's appearance and accent.

Standard library only. Nothing here ships with your app — keep it beside the
app directory, not inside it.

    python preview.py --app my-app/src/static

Then:

    http://127.0.0.1:8765/__shell                   framed, light
    http://127.0.0.1:8765/__shell?appearance=dark   framed, dark
    http://127.0.0.1:8765/__shell?accent=lavender   framed, another accent
    http://127.0.0.1:8765/__shell?width=900         a narrow window, honestly
    http://127.0.0.1:8765/__shell?entry=/index.html%23card/42    a second screen
    http://127.0.0.1:8765/                          the bare page, unframed

The bar across the top is the check, not decoration. It says whether the app
answered `manaurum:ready`, and whether it actually APPLIED the appearance the
shell sent — an app that reads `e.data.appearance` instead of
`e.data.payload.appearance` answers the handshake perfectly and still renders
light inside a dark desktop.

`?width=` / `?height=` size the app's frame inside a large browser window.
Both headless browsers floor their OWN viewport at ~500px, so this is the only
honest way to photograph the narrow layout the design contract is written for.

Screenshot both appearances (Chrome or Edge, same flags). A fresh
--user-data-dir keeps the run independent of whatever browser profile is open;
a locked profile is one of the ways this command exits without writing a file
and without printing an error:

    chrome --headless=new --disable-gpu --hide-scrollbars \
      --user-data-dir="$(mktemp -d)" --virtual-time-budget=4000 \
      --window-size=1240,1000 --screenshot=light.png \
      "http://127.0.0.1:8765/__shell?appearance=light"

Stub responses: a JSON file mapping path -> body, passed with --fixtures
(default: preview-fixtures.json next to this script, if it exists). Paths match
the way `runtime.api_routes` does — exact first, then the longest `/prefix/*` —
so the detail screen at `/api/items/42` is reachable:

    { "/api/me":      { "user_id": "u-1", "nickname": "Preview" },
      "/api/items":   [ { "id": 1, "title": "First" } ],
      "/api/items/*": { "id": 1, "title": "First", "body": "…" } }

A value may also be an envelope describing the response, which is how you
photograph the states that are not "it worked":

    { "/api/items":     { "status": 500 },                    // could not load
      "/api/slow/*":    { "delay_ms": 1500, "body": {} },     // still loading
      "/api/empty":     { "body": [] },                       // nothing here yet
      "PUT /api/items/*": { "ok": true } }                    // a write, not a read

A key may name a method, as the last line does. Paths otherwise match without
one, the way `runtime.api_routes` does - which means a PUT is answered by the
GET fixture unless you say so, and a save whose stub replies with the record it
was reading looks like it worked when it would not have.

To photograph a `delay_ms` fixture mid-flight, run the browser WITHOUT
`--virtual-time-budget`: Chrome pauses virtual time while a request is in
flight, so no budget is short enough to catch the skeleton, and dropping the
flag shoots at the load event instead.

Anything not in that file answers `{}` (GET) or `{"ok": true}` (writes), and
every API hit is logged — a route your UI calls but your manifest does not
declare shows up here before it 404s in production.
"""

import argparse
import html
import json
import os
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ACCENTS = ("core-blue", "teal", "lavender", "coral", "rose", "graphite", "amber", "green")

# A fixture whose keys are all from this set is an envelope describing the
# response, not the response body itself.
ENVELOPE_KEYS = frozenset(("status", "delay_ms", "body"))


def clamp_px(raw):
    """A CSS pixel size from the query string, or None."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return max(240, min(value, 4000))

SHELL_PAGE = """<!doctype html>
<html lang="en" data-appearance="__APPEARANCE__">
<head>
<meta charset="utf-8" />
<title>preview - __APPEARANCE__ / __ACCENT__</title>
<style>
  :root { --hud-bg: #e8e8ee; --hud-fg: #3b3b42; --desk: #d8d8e0; --line: rgba(0,0,0,.14); --ok-fg: #0d7a37; }
  html[data-appearance="dark"] { --hud-bg: #242429; --hud-fg: #c9c9d2; --desk: #141417; --line: rgba(255,255,255,.14);
                                 --ok-fg: #4ade80; }
  html, body { height: 100%; margin: 0; }
  body { display: flex; flex-direction: column; background: var(--desk); color: var(--hud-fg);
         font: 12px/1.5 -apple-system, "Segoe UI", system-ui, sans-serif; }
  .hud { flex: none; display: flex; align-items: center; gap: 14px; padding: 6px 12px;
         background: var(--hud-bg); border-bottom: 1px solid var(--line); }
  .hud b { font-weight: 600; }
  .pill { padding: 2px 9px; border-radius: 999px; font-weight: 600; }
  .pill-wait { background: rgba(128,128,128,.25); }
  .pill-ok { background: rgba(48,209,88,.22); color: var(--ok-fg); }
  .pill-bad { background: #d0342c; color: #fff; }
  .frame { flex: 1; min-height: 0; display: flex; justify-content: center;
           align-items: stretch; overflow: auto; }
  iframe { flex: 1; width: 100%; height: 100%; border: 0; background: transparent; }
  /* A sized frame is the whole point of ?width= : the app gets a narrow window
     inside a large one, so the browser's own ~500px headless floor never
     applies and the crop is visible rather than guessed. */
  .frame.sized { align-items: flex-start; padding: 10px; }
  .frame.sized iframe { flex: none; border: 1px solid var(--line);
                        box-shadow: 0 2px 14px rgba(0,0,0,.18); background: var(--hud-bg); }
</style>
</head>
<body>
  <div class="hud">
    <b>preview</b>
    <span>appearance <b>__APPEARANCE__</b></span>
    <span>accent <b>__ACCENT__</b></span>
    <span>device <b>__DEVICE__</b></span>
    <span __SIZE_HIDDEN__>size <b>__SIZE_LABEL__</b></span>
    <span id="handshake" class="pill pill-wait">waiting for manaurum:ready...</span>
    <span id="themecheck" class="pill pill-wait">checking appearance...</span>
  </div>
  <div class="frame __SIZED__">
    <!-- The shell's own sandbox, verbatim: no allow-modals, so alert() /
         confirm() / prompt() are as dead here as they are in production. -->
    <iframe id="app" src="__ENTRY__" style="__FRAME_STYLE__"
            sandbox="allow-scripts allow-forms allow-same-origin"></iframe>
  </div>
<script>
  var INIT = __INIT__;
  var app = document.getElementById('app');
  var badge = document.getElementById('handshake');
  var theme = document.getElementById('themecheck');
  var ready = false;

  window.addEventListener('message', function (e) {
    if (e.data && e.data.type === 'manaurum:ready') {
      ready = true;
      badge.className = 'pill pill-ok';
      badge.textContent = 'manaurum:ready OK';
    }
  });

  // Did the app actually APPLY what the shell told it? An app can answer the
  // handshake perfectly and still read `e.data.appearance` (undefined) instead
  // of `e.data.payload.appearance`, and then it renders light inside a dark
  // desktop while every technical check stays green. Same origin here, so we
  // can just read the attribute back off <html>.
  function checkTheme() {
    var doc = null;
    try { doc = app.contentDocument; } catch (err) { doc = null; }
    if (!doc || !doc.documentElement) return;
    var got = doc.documentElement.getAttribute('data-appearance');
    if (got === INIT.appearance) {
      theme.className = 'pill pill-ok';
      theme.textContent = 'appearance applied';
    } else {
      theme.className = 'pill pill-bad';
      theme.textContent = 'appearance IGNORED - shell said ' + INIT.appearance +
                          ', app is ' + (got || 'unset') +
                          ' (read e.data.payload, not e.data)';
    }
  }

  app.addEventListener('load', function () {
    app.contentWindow.postMessage({ type: 'manaurum:init', payload: INIT }, location.origin);
    setTimeout(checkTheme, 400);
    // The real shell waits 10s and then covers the app with "App is not
    // responding". Three seconds is enough to put the failure in a screenshot.
    setTimeout(function () {
      checkTheme();
      if (ready) return;
      badge.className = 'pill pill-bad';
      badge.textContent = 'NO manaurum:ready - the shell would cover this app';
    }, 3000);
  });
</script>
</body>
</html>
"""


def build_init(appearance, accent, device):
    """The payload the shell posts, per references/sdk-api.md.

    The mobile column of that file's "Platform fields" table is reproduced
    here: a back button instead of a window frame, real notch insets, and a
    navigation mode taken from the app's declared pattern (`stack` is the
    common one). Get this wrong and an app that branches on those fields is
    exercised with desktop values while the badge says "mobile".
    """
    mobile = device == "mobile"
    return {
        "theme": "smoothie",
        "appearance": appearance,
        "accent": accent,
        "device": device,
        "platform": device,
        "screen": {"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900},
        "safeAreaInsets": ({"top": 47, "bottom": 34, "left": 0, "right": 0} if mobile
                           else {"top": 0, "bottom": 0, "left": 0, "right": 0}),
        "navigationMode": "stack" if mobile else "window",
        "shell": {"hasTabBar": False, "hasBackButton": mobile, "tabBarHeight": 0},
        "user": {"nickname": "Preview"},
        "permissions": [],
        "appId": "preview-app",
        "offline_token": "",
        "granted_capabilities": ["os.kv.get", "os.kv.set"],
        "windowId": "win_preview",
    }


class PreviewServer(ThreadingHTTPServer):
    # Windows lets a second process bind a port that is already listening when
    # SO_REUSEADDR is set, and then splits requests between the two — so a stale
    # server keeps answering with old files through an edit-restart-screenshot
    # loop. Refuse the bind instead; "address in use" is the useful answer.
    allow_reuse_address = False


class Handler(SimpleHTTPRequestHandler):
    fixtures = {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/__shell":
            return self.send_shell()
        if path.startswith("/api/"):
            return self.send_api(path)
        return SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return self.send_error(405)
        return self.send_api(path, default={"ok": True})

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST

    def match_fixture(self, path):
        """Match the way `runtime.api_routes` does, not the way a dict does.

        Routes are declared as globs, so the detail screen lives at
        `/api/items/<id>` and an exact-key lookup can never photograph it: it
        answers {} and you screenshot an empty card. Exact key first, then the
        longest `/prefix/*` that matches.

        A key may also name a method — `"PUT /api/items/*"` — which wins over
        the same path without one. `api_routes` has no method dimension, so
        neither does this by default; but a save whose stub answers with the
        record it was reading looks like it worked when it would not have.
        """
        for candidates in (("%s %s" % (self.command, path),), (path,)):
            for key in candidates:
                if key in self.fixtures:
                    return self.fixtures[key], key
            prefix_key = self._longest_prefix(path, method=self.command
                                              if candidates[0] != path else None)
            if prefix_key is not None:
                return self.fixtures[prefix_key], prefix_key
        return None, None

    def _longest_prefix(self, path, method=None):
        best_key = None
        for key in self.fixtures:
            candidate = key
            if method is not None:
                head, _, rest = key.partition(" ")
                if head != method or not rest:
                    continue
                candidate = rest
            elif " " in key:
                continue
            if not candidate.endswith("/*"):
                continue
            if path.startswith(candidate[:-1]) and (
                    best_key is None or len(candidate) > len(best_key)):
                best_key = key
        return best_key

    def send_api(self, path, default=None):
        fixture, key = self.match_fixture(path)
        source = "stub {}" if key is None else "fixture %s" % key
        if fixture is None:
            fixture = {} if default is None else default

        # A fixture may be a bare body, or an envelope describing the response:
        #   {"status": 500, "delay_ms": 1500, "body": {...}}
        # Empty, failed and slow are three different states, and design.md asks
        # for a different screen for each — so all three must be photographable.
        status, delay_ms, body = 200, 0, fixture
        if isinstance(fixture, dict) and fixture and set(fixture) <= ENVELOPE_KEYS and (
                "body" in fixture
                or isinstance(fixture.get("status"), int)
                or isinstance(fixture.get("delay_ms"), int)):
            # `{"status": "open"}` is a body, not an envelope — a real record
            # can carry a field with that name, and reading it as an HTTP
            # status crashes the preview for no reason.
            status = int(fixture.get("status", 200))
            delay_ms = int(fixture.get("delay_ms", 0))
            body = fixture.get("body", {})
            source += " [status=%d delay=%dms]" % (status, delay_ms)

        if delay_ms > 0:
            time.sleep(min(delay_ms, 30000) / 1000.0)

        blob = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)
        sys.stderr.write("  api  %-6s %-38s -> %s\n" % (self.command, path, source))

    def send_shell(self):
        q = parse_qs(urlparse(self.path).query)
        appearance = q.get("appearance", ["light"])[0].lower()
        if appearance not in ("light", "dark"):
            appearance = "light"
        accent = q.get("accent", ["core-blue"])[0].lower()
        if accent not in ACCENTS:
            accent = "core-blue"
        device = q.get("device", ["desktop"])[0].lower()
        if device not in ("desktop", "mobile"):
            device = "desktop"
        # `entry` is the one caller-controlled string that lands in the page.
        # It must be a path, and it is escaped before it reaches the attribute.
        entry = q.get("entry", ["/index.html"])[0]
        if not entry.startswith("/"):
            entry = "/index.html"
        entry = html.escape(entry, quote=True)

        # ?width= / ?height= size the IFRAME inside a large browser window. The
        # whole design contract is written for a window that is "often 900px",
        # and both headless browsers floor their own viewport at ~500px — so
        # this is the only way to photograph a narrow layout honestly.
        width = clamp_px(q.get("width", [None])[0])
        height = clamp_px(q.get("height", [None])[0])
        style = ""
        if width:
            style += "width:%dpx;" % width
        if height:
            style += "height:%dpx;" % height
        size_label = "%s x %s" % (width or "full", height or "full")

        page = (SHELL_PAGE
                .replace("__APPEARANCE__", appearance)
                .replace("__ACCENT__", accent)
                .replace("__DEVICE__", device)
                .replace("__ENTRY__", entry)
                .replace("__SIZED__", "sized" if style else "")
                .replace("__FRAME_STYLE__", style)
                .replace("__SIZE_HIDDEN__", "" if style else "hidden")
                .replace("__SIZE_LABEL__", size_label)
                .replace("__INIT__", json.dumps(build_init(appearance, accent, device))))
        blob = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def log_message(self, fmt, *args):
        sys.stderr.write("  http %s\n" % (fmt % args))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Preview a Manaurum v2 app the way the shell frames it.")
    ap.add_argument("--app", required=True,
                    help="directory holding index.html and the rest of your static files")
    ap.add_argument("--fixtures", default=os.path.join(here, "preview-fixtures.json"),
                    help="JSON file mapping /api/... paths to response bodies")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    root = os.path.abspath(args.app)
    if not os.path.isdir(root):
        sys.exit("not a directory: %s" % root)
    if not os.path.exists(os.path.join(root, "index.html")):
        sys.stderr.write("warning: no index.html in %s\n" % root)

    # Everything the operator needs goes to stderr, unbuffered: this server is
    # normally backgrounded into a log file, and block-buffered stdout would
    # hold the URLs until the process died.
    say = lambda line: sys.stderr.write(line + "\n")

    if os.path.exists(args.fixtures):
        with open(args.fixtures, encoding="utf-8") as fh:
            Handler.fixtures = json.load(fh)
        stubs = [k for k in Handler.fixtures if k.startswith("/")]
        say("fixtures: %s (%d paths)" % (args.fixtures, len(stubs)))
    else:
        say("fixtures: none - every /api/* answers {}")

    server = PreviewServer(("127.0.0.1", args.port),
                           lambda *a: Handler(*a, directory=root))
    base = "http://127.0.0.1:%d" % args.port
    say("serving %s" % root)
    say("  framed light : %s/__shell" % base)
    say("  framed dark  : %s/__shell?appearance=dark" % base)
    say("  unframed     : %s/" % base)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

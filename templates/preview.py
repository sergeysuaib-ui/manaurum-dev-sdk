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
    http://127.0.0.1:8765/                          the bare page, unframed

Screenshot both appearances (Chrome or Edge, same flags). A fresh
--user-data-dir keeps the run independent of whatever browser profile is open;
a locked profile is one of the ways this command exits without writing a file
and without printing an error:

    chrome --headless=new --disable-gpu --hide-scrollbars \
      --user-data-dir="$(mktemp -d)" --virtual-time-budget=4000 \
      --window-size=1240,1000 --screenshot=light.png \
      "http://127.0.0.1:8765/__shell?appearance=light"

Stub responses: a JSON file mapping path -> body, passed with --fixtures
(default: preview-fixtures.json next to this script, if it exists).

    { "/api/me":    { "user_id": "u-1", "nickname": "Preview" },
      "/api/items": [ { "id": 1, "title": "First" } ] }

Anything not in that file answers `{}` (GET) or `{"ok": true}` (writes), and
every API hit is logged — a route your UI calls but your manifest does not
declare shows up here before it 404s in production.
"""

import argparse
import html
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ACCENTS = ("core-blue", "teal", "lavender", "coral", "rose", "graphite", "amber", "green")

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
  .frame { flex: 1; min-height: 0; display: flex; }
  iframe { flex: 1; width: 100%; height: 100%; border: 0; background: transparent; }
</style>
</head>
<body>
  <div class="hud">
    <b>preview</b>
    <span>appearance <b>__APPEARANCE__</b></span>
    <span>accent <b>__ACCENT__</b></span>
    <span>device <b>__DEVICE__</b></span>
    <span id="handshake" class="pill pill-wait">waiting for manaurum:ready...</span>
  </div>
  <div class="frame">
    <!-- The shell's own sandbox, verbatim: no allow-modals, so alert() /
         confirm() / prompt() are as dead here as they are in production. -->
    <iframe id="app" src="__ENTRY__" sandbox="allow-scripts allow-forms allow-same-origin"></iframe>
  </div>
<script>
  var INIT = __INIT__;
  var app = document.getElementById('app');
  var badge = document.getElementById('handshake');
  var ready = false;

  window.addEventListener('message', function (e) {
    if (e.data && e.data.type === 'manaurum:ready') {
      ready = true;
      badge.className = 'pill pill-ok';
      badge.textContent = 'manaurum:ready OK';
    }
  });

  app.addEventListener('load', function () {
    app.contentWindow.postMessage({ type: 'manaurum:init', payload: INIT }, location.origin);
    // The real shell waits 10s and then covers the app with "App is not
    // responding". Three seconds is enough to put the failure in a screenshot.
    setTimeout(function () {
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

    def send_api(self, path, default=None):
        body = self.fixtures.get(path, {} if default is None else default)
        blob = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)
        sys.stderr.write("  api  %-6s %-38s -> %s\n"
                         % (self.command, path, "fixture" if path in self.fixtures else "stub {}"))

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

        page = (SHELL_PAGE
                .replace("__APPEARANCE__", appearance)
                .replace("__ACCENT__", accent)
                .replace("__DEVICE__", device)
                .replace("__ENTRY__", entry)
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

---
name: manaurum-deploy
description: Deploy and publish a ManAurum OS app. Use when the user wants to deploy, publish, host, upload, or release their ManAurum/SeregaOS app. Covers API token setup, direct deploy from CLI via curl, hosting on ManAurum, external hosting, and publishing flow. Also use when user says "deploy to ManAurum", "upload my app", "publish my app", or "host on ManAurum".
---

# Deploy ManAurum OS App

Help the user deploy their ManAurum OS app. There are two deployment paths:

## Path 1: Deploy directly from CLI (recommended)

This is the fastest path. The user generates an API token once, then deploys from their terminal without opening a browser.

### Step 1: Get an API token

The user needs a ManAurum developer API token. They can generate one from:
- ManAurum OS → Developer Console → Tokens section
- Or via the API if they have a session:

```bash
curl -X POST https://manaurum.com/api/developer/tokens \
  -H "Authorization: Bearer SESSION_JWT" \
  -H "Content-Type: application/json" \
  -d '{"name": "CLI deploy"}'
```

Response includes a token like `mdev_xxxxxxxxxxxxx`. Save it — it's shown only once.

### Step 2: Store the token locally

Save the token so it's available for deploy commands:

```bash
# Create a config file
echo "MANAURUM_TOKEN=mdev_your_token_here" > .env.manaurum

# Or export in shell
export MANAURUM_TOKEN=mdev_your_token_here
```

**Important:** Add `.env.manaurum` to `.gitignore` so the token is never committed.

### Step 3: Deploy single HTML file

For simple apps (one HTML file):

```bash
curl -X POST "https://manaurum.com/api/developer/apps/YOUR_SLUG/hosting/paste" \
  -H "Authorization: Bearer $MANAURUM_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"html\": $(cat index.html | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}"
```

Or the simpler version if the file is small:

```bash
# Read file and deploy
HTML_CONTENT=$(cat index.html)
curl -X POST "https://manaurum.com/api/developer/apps/YOUR_SLUG/hosting/paste" \
  -H "Authorization: Bearer $MANAURUM_TOKEN" \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{"html": $(python3 -c "import json; print(json.dumps(open('index.html').read()))")}
EOF
```

### Step 4: Deploy multi-file app (ZIP)

For apps with multiple files (HTML + JS + CSS + images):

```bash
# Create ZIP
zip -r app.zip index.html style.css app.js assets/

# Upload
curl -X POST "https://manaurum.com/api/developer/apps/YOUR_SLUG/hosting/upload" \
  -H "Authorization: Bearer $MANAURUM_TOKEN" \
  -F "file=@app.zip"
```

The ZIP must contain `index.html` at the root level.

### Step 5: Verify deployment

```bash
curl -s "https://manaurum.com/api/developer/apps/YOUR_SLUG/hosting/status" \
  -H "Authorization: Bearer $MANAURUM_TOKEN" | python3 -m json.tool
```

The app is now live at: `https://manaurum.com/hosted/YOUR_SLUG/index.html`

## Path 2: Deploy via external hosting

If the user prefers to host externally:

1. Deploy to Vercel/Netlify/GitHub Pages/Cloudflare Pages
2. Get the HTTPS URL
3. Set it as the entrypoint in Developer Console → Manifest tab
4. Preview in SeregaOS

## Deploy Script Helper

When generating an app, also create a `deploy.sh` script:

```bash
#!/bin/bash
# Deploy to ManAurum OS
# Usage: ./deploy.sh

set -e

# Load token from .env.manaurum
if [ -f .env.manaurum ]; then
  export $(cat .env.manaurum | xargs)
fi

if [ -z "$MANAURUM_TOKEN" ]; then
  echo "Error: MANAURUM_TOKEN not set"
  echo "Create .env.manaurum with: MANAURUM_TOKEN=mdev_your_token"
  exit 1
fi

APP_SLUG="YOUR_SLUG"
API="https://manaurum.com/api/developer/apps/$APP_SLUG/hosting"

# Check if we have multiple files or just index.html
if [ -f "style.css" ] || [ -f "app.js" ] || [ -d "assets" ]; then
  echo "Packaging multi-file app..."
  zip -r /tmp/manaurum-deploy.zip . -x ".*" "deploy.sh" "node_modules/*" ".env*"
  echo "Uploading ZIP..."
  curl -s -X POST "$API/upload" \
    -H "Authorization: Bearer $MANAURUM_TOKEN" \
    -F "file=@/tmp/manaurum-deploy.zip" | python3 -m json.tool
  rm /tmp/manaurum-deploy.zip
else
  echo "Deploying single file..."
  curl -s -X POST "$API/paste" \
    -H "Authorization: Bearer $MANAURUM_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"html\": $(python3 -c "import json; print(json.dumps(open('index.html').read()))")}" | python3 -m json.tool
fi

echo ""
echo "Live at: https://manaurum.com/hosted/$APP_SLUG/index.html"
```

When creating an app, always generate this deploy script with the correct slug filled in.

## Troubleshooting

| Problem | Solution |
|---------|---------|
| "Invalid token format" | Token must start with `mdev_`. Check you copied the full token. |
| "Invalid or revoked token" | Generate a new token from Developer Console. |
| "App not found" | Check the app slug. The token must belong to the app's developer. |
| "ZIP too large" | Max 10MB. Remove node_modules, .git, large assets. |
| "Invalid file: xxx" | Only web files allowed (html, js, css, images, fonts, wasm). |
| "ZIP must contain index.html" | Ensure index.html is at the root of the ZIP, not in a subdirectory. |

## Post-Deploy: Verify with Probe

After deploying, ALWAYS verify the entrypoint is working:

```bash
curl -s "https://manaurum.com/api/developer/apps/$APP_SLUG/probe-entrypoint" \
  -H "Authorization: Bearer $MANAURUM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://manaurum.com/hosted/'$APP_SLUG'/index.html"}' | python3 -m json.tool
```

**Expected good response:**
```json
{
  "reachable": true,
  "status_code": 200,
  "content_type": "text/html; charset=utf-8",
  "response_time_ms": 45,
  "iframe_blocked": false,
  "error": null
}
```

**If probe fails**, check:
- `reachable: false` → file not found or server error
- `status_code: 404` → index.html missing from ZIP root
- `iframe_blocked: true` → server sets X-Frame-Options: DENY
- `content_type` not text/html → wrong file being served

## Post-Deploy: Check Diagnostics

If the app fails during preview, diagnostic logs are saved automatically. Retrieve them:

```bash
curl -s "https://manaurum.com/api/developer/apps/$APP_SLUG/diagnostics" \
  -H "Authorization: Bearer $MANAURUM_TOKEN" | python3 -m json.tool
```

Each log contains:
- `status`: ready / timeout / error
- `events`: full postMessage timeline with timestamps
- `probe_result`: server-side HTTP check at time of failure
- `created_at`: when it happened

Use this to diagnose why an app fails:
- If status is `timeout` and events show `manaurum:init → app` but no `manaurum:ready ← app`, the app is not calling `ManaurumSDK.init()`
- If status is `error` and no events, the entrypoint URL is unreachable
- If events show permission blocks, the manifest is missing required permissions

### AI Agent Diagnostic Workflow

When a user reports their ManAurum app is broken:

1. Get the app slug
2. Run probe: `POST /api/developer/apps/{slug}/probe-entrypoint`
3. Get diagnostics: `GET /api/developer/apps/{slug}/diagnostics`
4. Analyze the events timeline and probe result
5. Suggest specific fixes

## Publishing Flow

After deploying, the app is automatically set to Private. To share or publish:

1. **Make Unlisted** (share link): Dev Console → Publish tab → "Make Unlisted"
2. **Submit for Public** (App Store): Add screenshot → Submit for Review
3. Or via API with token — future capability

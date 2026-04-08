# ManAurum App Manifest Specification

## Full Manifest Structure

```json
{
  "manifest_version": 1,
  "app_id": "my-weather-app",
  "name": "Weather Widget",
  "version": "1.0.0",
  "description": {
    "short": "Real-time weather for your desktop (max 160 chars)",
    "long": "Optional longer description"
  },
  "icon": "https://your-cdn.com/icon.png",
  "category": "utility",
  "tags": ["weather", "widget"],
  "runtime": {
    "type": "iframe",
    "entrypoint": "https://your-app.com/",
    "sandbox": ["allow-scripts", "allow-forms", "allow-same-origin"]
  },
  "window": {
    "default_size": { "width": 800, "height": 600 },
    "min_size": { "width": 400, "height": 300 },
    "title": "Weather Widget"
  },
  "permissions": ["theme.read", "window.manage"],
  "compatibility": { "min_shell_version": "1.0.0" }
}
```

## Validation Rules

| Field | Rule |
|-------|------|
| `manifest_version` | Must be `1` |
| `app_id` | Lowercase a-z, 0-9, hyphens. 3-50 chars. Globally unique. Regex: `^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$` |
| `name` | 1-100 characters |
| `version` | Semver: X.Y.Z (e.g. `1.0.0`, `2.3.1`) |
| `description.short` | 1-160 characters (required for public apps) |
| `entrypoint` | HTTPS URL that returns HTTP 200. `http://localhost` accepted for private testing only. |
| `window.default_size.width` | 300-2000 pixels |
| `window.default_size.height` | 200-1500 pixels |
| `window.min_size.width` | 200 to default_width |
| `window.min_size.height` | 150 to default_height |
| `permissions` | Only from the allowed list (see SDK reference) |
| `category` | One of: `productivity`, `utility`, `lifestyle`, `entertainment`, `dev_tools`, `other` |
| `tags` | Max 10 tags |

## Required vs Optional

**Required for all apps:**
- manifest_version, app_id, name, version, runtime (type + entrypoint), window.default_size

**Required for Private publishing (no review):**
- All above + description.short + icon

**Additionally required for Public App Store:**
- At least 1 screenshot uploaded via Developer Console

## Window Size Presets

For quick setup, use these common sizes:

| Preset | default_size | min_size | Good for |
|--------|-------------|----------|----------|
| Small widget | 400 x 400 | 300 x 300 | Clocks, calculators, quick tools |
| Medium app | 800 x 600 | 400 x 300 | Standard apps, dashboards |
| Large app | 1100 x 750 | 700 x 500 | Complex UIs, editors |
| Wide panel | 1000 x 500 | 500 x 300 | Horizontal layouts, timelines |

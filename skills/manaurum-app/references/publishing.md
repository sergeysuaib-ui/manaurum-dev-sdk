# Publishing ManAurum OS Apps

## Release Model

ManAurum uses a **versioned release model** with direct publishing:

- Each app has a permanent `app_id` (slug)
- Each app can have many **versions** (semver: X.Y.Z)
- One version is marked as the **live** version — this is what users receive
- When you publish a new live version, all installed copies auto-update
- No review or approval is needed to publish

**Core flow:** Create app → Upload build → Publish version → Users get it automatically.

## App States

| State | Meaning |
|-------|---------|
| **Draft** | Not published yet — only visible in Dev Center |
| **Published** | Live in App Store, available for install |
| **Unpublished** | Removed from store, existing installs still work |
| **Deleted** | Soft-deleted, no new installs, shows "unavailable" |

## Version States

| State | Meaning |
|-------|---------|
| **Draft** | Work in progress, not yet published |
| **Published** | Released, can be promoted to live |
| **Archived** | Retired, no longer active |

## Step-by-Step Publishing Flow

### 1. Host your app
Deploy your HTML/JS app to any HTTPS hosting:
- **ManAurum Hosting**: paste HTML or upload ZIP directly in Dev Center
- **Vercel**: `vercel deploy`
- **Netlify**: drag-and-drop or CLI
- **GitHub Pages**: push to `gh-pages` branch
- **Any server**: just serve static files over HTTPS

For local testing, `http://localhost` works for draft apps.

### 2. Register on ManAurum OS
1. Go to [manaurum.com](https://manaurum.com) and log in
2. Open **Dev Hub** on your desktop
3. Click **"Create App"**
4. Enter your app name (slug auto-generated)

### 3. Connect your entrypoint
1. In the **Build** tab, paste your hosted URL into the entrypoint field
2. Click **"Preview in SeregaOS"**
3. Your app opens in a real OS window

### 4. Auto-publish on first preview
On first successful preview (handshake succeeds), your app:
- Automatically publishes version 1.0.0
- Automatically installs in your workspace
- Appears on your desktop

### 5. Release updates
1. Go to the **Versions** tab
2. Click **"Release Update"**
3. Enter new version number and release notes
4. Click **"Publish"** or **"Publish & Go Live"**
5. All installed copies receive the update automatically

### 6. Rollback
If a release is broken:
1. Go to the **Versions** tab
2. Find the previous stable version
3. Click **"Make Live"**
4. Users automatically revert to that version

## Auto-Update for Users

- Users install the app once — they never need to reinstall
- When you publish a new live version, all installs update automatically
- If the new version adds permissions, users see a confirmation dialog
- If the new version is incompatible with their shell, they stay on the previous version

## Validation Checks

Before publishing, these are validated:
1. Entrypoint HTTPS (or localhost for drafts)
2. Entrypoint responds with HTTP 200
3. Permissions from the allowed list only
4. Version in semver format (X.Y.Z)
5. Window size within range (300-2000 width, 200-1500 height)

**Note:** Short description, icon, and screenshots are **optional** — they don't block publishing.

## Unpublish / Delete

- **Unpublish**: removes from App Store, existing installs keep working, you can republish later
- **Delete**: soft-delete, blocks new installs, existing installs show "App no longer available"

## API Endpoints

### Publish app (creates version + makes live)
```
POST https://manaurum.com/api/developer/apps/{slug}/publish
Authorization: Bearer {token}
```

### Publish a specific version
```
POST https://manaurum.com/api/developer/apps/{slug}/versions/{version_id}/publish
Authorization: Bearer {token}
```

### Make version live (promote)
```
POST https://manaurum.com/api/developer/apps/{slug}/versions/{version_id}/make-live
Authorization: Bearer {token}
```

### Archive a version
```
POST https://manaurum.com/api/developer/apps/{slug}/versions/{version_id}/archive
Authorization: Bearer {token}
```

### Unpublish app
```
POST https://manaurum.com/api/developer/apps/{slug}/unpublish
Authorization: Bearer {token}
```

### Delete app
```
DELETE https://manaurum.com/api/developer/apps/{slug}
Authorization: Bearer {token}
```

### Quick-Create API
```
POST https://manaurum.com/api/developer/apps/quick-create
Authorization: Bearer {token}
Content-Type: application/json

{
  "app_name": "My Weather Widget",
  "developer_name": "Your Name"  // only needed first time
}
```

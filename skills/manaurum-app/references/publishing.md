# Publishing ManAurum OS Apps

## Publishing Modes

| Mode | Who sees it | Review needed | Use case |
|------|-----------|--------------|----------|
| **Private** | Only you | No — auto-validation only | Development and testing |
| **Unlisted** | Anyone with the link | No — auto-validation only | Beta testing |
| **Public** | Everyone in App Store | Yes — admin review | Production release |

## Step-by-Step Publishing Flow

### 1. Host your app
Deploy your HTML/JS app to any HTTPS hosting:
- **Vercel**: `vercel deploy`
- **Netlify**: drag-and-drop or CLI
- **Cloudflare Pages**: connect GitHub repo
- **GitHub Pages**: push to `gh-pages` branch
- **Any server**: just serve static files over HTTPS

For local testing, `http://localhost` works for private apps.

### 2. Register on ManAurum OS
1. Go to [manaurum.com](https://manaurum.com) and log in
2. Open **Developer Console** (Dev Hub on desktop)
3. Click **"Create App"**
4. Enter your app name (slug auto-generated)

### 3. Connect your entrypoint
1. In the **Build** tab, paste your hosted URL into the entrypoint field
2. Click **"Preview in SeregaOS"**
3. Your app opens in a real OS window

### 4. Auto-publish Private
On first successful preview (handshake succeeds), your app:
- Automatically publishes as **Private**
- Automatically installs in your workspace
- Appears on your desktop

### 5. Share for beta testing
1. Click **"Make Unlisted"** in the Publish tab
2. Copy the share link: `manaurum.com/app/{your-slug}`
3. Send to testers — they can install from the link

### 6. Publish to App Store
1. Add at least 1 screenshot (Listing tab → Media)
2. Fill in short description
3. Click **"Submit for Public Review"**
4. Admin reviews (typically 24-48h)
5. After approval, click **"Publish to App Store"**

## Validation Checks

### Private (7 checks):
1. Entrypoint HTTPS (or localhost)
2. Entrypoint responds
3. Icon present
4. Short description present
5. Permissions valid
6. Version semver
7. Window size valid

### Public (9 checks — adds):
8. At least 1 screenshot
9. manifest_version == 1

## Updating Apps

- **Private/Unlisted**: publish updates immediately, no review
- **Public without new permissions**: publish directly
- **Public with new permissions**: requires re-review

## Quick-Create API

For programmatic app creation:
```
POST https://manaurum.com/api/developer/apps/quick-create
Authorization: Bearer {token}
Content-Type: application/json

{
  "app_name": "My Weather Widget",
  "developer_name": "Your Name"  // only needed first time
}

Response:
{
  "app_slug": "my-weather-widget",
  "app_name": "My Weather Widget",
  "app_url": "/app/my-weather-widget"
}
```

---
name: manaurum-deploy
description: Deploy and publish a ManAurum OS app. Use when the user wants to deploy, publish, host, or release their ManAurum/SeregaOS app. Covers hosting setup, entrypoint configuration, private/unlisted/public publishing, and App Store submission.
---

# Deploy ManAurum OS App

Help the user deploy their ManAurum OS app from local development to production.

## Deployment Checklist

Before deploying, verify the app:
- [ ] Loads the ManAurum SDK (`manaurum.js`)
- [ ] Handles `manaurum:init` and sends `manaurum:ready`
- [ ] Adapts to theme changes (smoothie/xp)
- [ ] Works at the declared window size

## Hosting Options

The app needs to be served over HTTPS. Recommend one of:

### Vercel (easiest for single files)
```bash
npm i -g vercel
# Put your app files in a directory
vercel deploy --prod
```

### Netlify (drag and drop)
1. Go to netlify.com → Sites → drag your folder
2. Get HTTPS URL automatically

### GitHub Pages (free, from repo)
1. Push app to a GitHub repo
2. Settings → Pages → Deploy from branch
3. URL: `https://username.github.io/repo-name/`

### Cloudflare Pages
```bash
npx wrangler pages deploy ./your-app-directory
```

## After Hosting

Once the app is live at an HTTPS URL:

1. **Test in harness first**: Open `https://manaurum.com/sdk/test-harness.html`, paste the URL, verify green dot
2. **Connect to ManAurum**: Open Developer Console → your app → Build tab → paste URL → Preview
3. **Auto-publish**: First successful preview publishes as Private automatically
4. **Share**: Make Unlisted → copy link → send to testers
5. **Go public**: Add screenshot → Submit for Review → Publish

## Manifest Configuration

If the user needs to update their manifest (window size, permissions, title):
- Done through Developer Console → Settings tab → Manifest editor
- Or via API: `PUT /api/developer/apps/{slug}/manifest`

## Troubleshooting

| Problem | Solution |
|---------|---------|
| "App not responding" | Check that `manaurum:ready` is sent within 10s of `manaurum:init` |
| Preview shows blank | Check browser console for CORS errors. Entrypoint must allow iframe embedding. |
| Entrypoint validation fails | Ensure URL returns HTTP 200. Check it's not behind auth. |
| "Permission denied" | Check manifest permissions match what your app uses |

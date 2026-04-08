# ManAurum OS Developer SDK — Claude Code Plugin

Build, test, and deploy apps for [ManAurum OS](https://manaurum.com) using Claude Code.

ManAurum OS is a browser-based virtual desktop. Apps run as standalone HTML/JS pages inside iframe windows. This plugin gives Claude the knowledge to help you build ManAurum apps from prompts.

## Install

```bash
# Add the marketplace (one time)
claude plugin marketplace add manaurum-sdk sergeysuaib-ui/manaurum-dev-sdk

# Install the plugin
claude plugin install manaurum-dev-sdk@manaurum-sdk
```

## Skills Included

| Skill | Trigger | What it does |
|-------|---------|-------------|
| `manaurum-app` | "Build a ManAurum app..." | Generates app code with SDK, manifest, theme support |
| `manaurum-deploy` | "Deploy my ManAurum app" | Guides hosting setup and publishing flow |
| `manaurum-setup` | "Set up a ManAurum project" | Scaffolds project from scratch |

## Usage

After installing, just describe what you want:

```
Build a ManAurum OS app that shows the current time with a dark/light theme
```

Or use skills directly:

```
/manaurum-setup
/manaurum-app Create a weather widget
/manaurum-deploy
```

## What Claude will help you with

- Generate HTML/JS apps that integrate with the ManAurum SDK
- Create valid manifests with correct permissions and window sizes
- Apply theme-aware styling (Smoothie/XP themes)
- Test via the ManAurum Test Harness
- Deploy to hosting (Vercel, Netlify, etc.)
- Publish: Private → Unlisted → Public App Store

## How ManAurum Apps Work

Your app is a regular web page. ManAurum loads it in a sandboxed iframe and communicates via postMessage:

1. OS sends `manaurum:init` (theme, user, permissions)
2. Your app responds with `manaurum:ready`
3. Your app can use SDK methods for window management, toasts, notifications

That's it. Any HTML page can become a ManAurum app.

## Resources

- [Developer Docs](https://manaurum.com/developers)
- [Test Harness](https://manaurum.com/sdk/test-harness.html)
- [SDK (UMD)](https://manaurum.com/sdk/manaurum.js)
- [SDK (ESM)](https://manaurum.com/sdk/manaurum.mjs)
- [AGENTS.md](https://manaurum.com/sdk/AGENTS.md)
- [Manifest Schema](https://manaurum.com/sdk/manifest.schema.json)

## License

MIT

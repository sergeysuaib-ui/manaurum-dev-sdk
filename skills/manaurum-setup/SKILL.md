---
name: manaurum-setup
description: Set up a ManAurum OS development environment. Use when user wants to start building for ManAurum/SeregaOS, needs to set up their project, scaffold an app, or initialize a new ManAurum app project from scratch.
---

# Set Up ManAurum OS App Project

Help the user scaffold a new ManAurum OS app project from scratch.

## Quick Setup

Create a minimal project structure:

```
my-manaurum-app/
├── index.html     ← Your app (loaded in ManAurum iframe)
├── style.css      ← Optional styles
├── app.js         ← Optional separate JS
└── manifest.json  ← App manifest (for reference)
```

## Starter Template

Create `index.html` with this content:

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>My App</title>
  <script src="https://manaurum.com/sdk/manaurum.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { padding: 24px; transition: all 0.2s; }
    body.smoothie { font-family: 'Inter', -apple-system, sans-serif; background: #f9f9ff; color: #181c23; font-size: 14px; }
    body.xp { font-family: Tahoma, sans-serif; background: #ece9d8; color: #000; font-size: 12px; }
    h1 { margin-bottom: 12px; }
  </style>
</head>
<body class="smoothie">
  <h1 id="title">Loading...</h1>
  <p id="info"></p>

  <script>
    var app = ManaurumSDK.init();

    app.onReady(function(ctx) {
      document.body.className = ctx.theme;
      document.getElementById('title').textContent = 'Hello, ' + ctx.user.nickname + '!';
      document.getElementById('info').textContent = 'Theme: ' + ctx.theme;
    });

    app.onThemeChange(function(theme) {
      document.body.className = theme;
      document.getElementById('info').textContent = 'Theme: ' + theme;
    });
  </script>
</body>
</html>
```

## Local Development

```bash
# Serve locally
python -m http.server 8000
# or
npx serve .
# or
php -S localhost:8000
```

Then test at: `https://manaurum.com/sdk/test-harness.html?url=http://localhost:8000`

## Using Frameworks

ManAurum apps work with any framework. Just add the SDK:

### React
```jsx
import { useEffect, useState } from 'react';

function App() {
  const [ctx, setCtx] = useState(null);

  useEffect(() => {
    const script = document.createElement('script');
    script.src = 'https://manaurum.com/sdk/manaurum.js';
    script.onload = () => {
      const app = window.ManaurumSDK.init();
      app.onReady(setCtx);
      app.onThemeChange(theme => setCtx(prev => ({ ...prev, theme })));
    };
    document.head.appendChild(script);
  }, []);

  if (!ctx) return <div>Loading...</div>;
  return <h1>Hello, {ctx.user.nickname}!</h1>;
}
```

### Vue, Svelte, plain JS
Same pattern: load SDK, init, handle onReady/onThemeChange.

## Deploy Setup

To enable direct deploy from CLI without opening a browser:

1. Go to [manaurum.com](https://manaurum.com) → Dev Hub → generate an API token
2. Create `.env.manaurum` in your project root:
```
MANAURUM_TOKEN=mdev_your_token_here
```
3. Add to `.gitignore`:
```
.env.manaurum
```

Now you can deploy with `/manaurum-deploy`.

## Next Steps

After setup:
1. Build your app features
2. Test in the Test Harness
3. Use `/manaurum-deploy` to deploy directly to ManAurum OS

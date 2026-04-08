# ManAurum OS Design Guidelines

## Two Themes

ManAurum OS has two visual themes. Your app should adapt to both.

### Smoothie (macOS-like)
- Font: `Inter, -apple-system, sans-serif`
- Body text: 14px
- Headings: 18-26px
- Background: `#f9f9ff`
- Text: `#181c23`
- Primary blue: `#0058bc`
- Cards: white with rounded corners (16-24px radius), subtle shadows
- Inputs: no border, light background `#f1f3fe`, 12px radius
- Buttons: gradient backgrounds, 12px radius

### XP (Windows XP)
- Font: `Tahoma, sans-serif`
- Body text: 12-13px
- Headings: 14-18px
- Background: `#ece9d8`
- Text: `#000`
- Primary blue: `#316ac5`
- Cards: white, 3px radius, 1px solid borders
- Inputs: white, 1px border, 3px radius
- Buttons: flat color, 3px radius

## Theme-Aware Pattern

```javascript
app.onReady(function(ctx) {
  applyTheme(ctx.theme);
});

app.onThemeChange(function(theme) {
  applyTheme(theme);
});

function applyTheme(theme) {
  if (theme === 'xp') {
    document.body.style.fontFamily = 'Tahoma, sans-serif';
    document.body.style.background = '#ece9d8';
    document.body.style.fontSize = '12px';
  } else {
    document.body.style.fontFamily = "'Inter', -apple-system, sans-serif";
    document.body.style.background = '#f9f9ff';
    document.body.style.fontSize = '14px';
  }
}
```

## Window Rules

- The OS provides the window title bar — do NOT render your own
- Your app fills the content area below the title bar
- Be responsive to window resizing (the user can drag window edges)
- Use relative units (%, vh/vw) or listen for resize events

## Colors Reference

| Role | Smoothie | XP |
|------|----------|-----|
| Background | `#f9f9ff` | `#ece9d8` |
| Card background | `rgba(255,255,255,0.6)` | `#fff` |
| Text primary | `#181c23` | `#000` |
| Text secondary | `#414755` | `#666` |
| Primary action | `#0058bc` | `#316ac5` |
| Success | `#16a34a` | `#16a34a` |
| Error | `#ba1a1a` | `#ba1a1a` |
| Border | `rgba(193,198,215,0.1)` | `#aca899` |

## App Icon

- 256x256 PNG recommended
- Should be recognizable at 52x52px
- Uploaded via Developer Console (not in the manifest file itself)

## Mobile Support

Your app works on mobile by default in fallback mode (scrollable desktop view). The `manaurum:init` payload includes `device: "mobile"` or `"desktop"` so you can adapt your layout.

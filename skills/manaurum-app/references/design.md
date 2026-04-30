# ManAurum OS Design System & UI Kit

ManAurum OS has two themes: **Smoothie** (macOS-like) and **XP** (Windows XP). Your app must adapt to both. This reference contains the exact styles used in built-in apps — copy them to look native.

> **Don't design from scratch when you can borrow.** manaurumOS ships a 100-component library (buttons, cards, modals, empty states, dashboards, settings, forms, patterns…) that already uses the Aurora-lite token vocabulary and adapts to both themes. Browse at <https://manaurum.com/library> or fetch from your app: `app.mul.list()`, `app.mul.get('button-primary-01')`. See `sdk-api.md` → "Component Library (MUL)".

## Theme Detection

```javascript
app.onReady(function(ctx) { applyTheme(ctx.theme); });
app.onThemeChange(function(theme) { applyTheme(theme); });

function applyTheme(theme) {
  document.body.className = theme; // 'smoothie' or 'xp'
}
```

Then use CSS classes:
```css
body.smoothie { font-family: 'Inter', -apple-system, sans-serif; background: #f9f9ff; color: #181c23; font-size: 14px; }
body.xp { font-family: Tahoma, sans-serif; background: #ece9d8; color: #000; font-size: 12px; }
```

---

## Color Tokens

| Role | Smoothie | XP |
|------|----------|-----|
| Background | `#f9f9ff` | `#ece9d8` |
| Card | `rgba(255,255,255,0.6)` | `#fff` |
| Text primary | `#181c23` | `#000` / `#333` |
| Text secondary | `#414755` | `#666` |
| Text muted | `#717786` | `#999` |
| Text disabled | `#c1c6d7` | `#aaa` |
| Primary blue | `#0058bc` | `#316ac5` |
| Primary gradient | `linear-gradient(135deg, #0058bc, #0070eb)` | `#316ac5` solid |
| Success | `#16a34a` | `#16a34a` |
| Error | `#dc2626` / `#ba1a1a` | same |
| Warning | `#d97706` | same |
| Border | `rgba(193,198,215,0.1)` | `#aca899` |
| Input bg | `#f1f3fe` | `#fff` |
| Hover bg | `#e6e8f3` | — |

---

## Cards & Containers

### Standard Card
```css
/* Smoothie */
.card {
  background: rgba(255,255,255,0.6);
  border-radius: 20px;
  padding: 14px 18px;
  border: 1px solid rgba(255,255,255,0.4);
  box-shadow: 0 2px 8px rgba(0,0,0,0.02);
}
.card:hover {
  background: rgba(255,255,255,0.9);
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
}

/* XP */
.card {
  background: #fff;
  border-radius: 3px;
  padding: 8px 10px;
  border: 1px solid #aca899;
}
```

### Glass Card (with blur)
```css
.glass-card {
  background: rgba(255,255,255,0.6);
  backdrop-filter: blur(20px);
  border-radius: 24px;
  padding: 24px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.03);
  border: 1px solid rgba(193,198,215,0.1);
}
```

### Info/Highlight Card
```css
.info-card {
  padding: 16px 20px;
  border-radius: 16px;
  background: rgba(0,88,188,0.04);
  border: 1px solid rgba(0,88,188,0.08);
}
```

---

## Buttons

### Primary Button
```css
/* Smoothie */
.btn-primary {
  padding: 12px 24px;
  border-radius: 12px;
  background: linear-gradient(135deg, #0058bc, #0070eb);
  color: white;
  font-weight: 700;
  font-size: 14px;
  border: none;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0,88,188,0.2);
}

/* XP */
.btn-primary {
  padding: 4px 16px;
  border-radius: 3px;
  background: #316ac5;
  color: white;
  font-weight: 700;
  font-size: 11px;
  border: 1px solid #214a87;
  cursor: pointer;
}
```

### Secondary Button
```css
/* Smoothie */
.btn-secondary {
  padding: 6px 18px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 600;
  color: #0058bc;
  border: 1px solid rgba(0,88,188,0.2);
  background: transparent;
}

/* XP */
.btn-secondary {
  background: linear-gradient(to bottom, #fff, #ece9d8);
  border: 1px solid #aaa;
  padding: 2px 8px;
  font-size: 11px;
  border-radius: 3px;
}
```

### Danger / Purple Accent Button
```css
.btn-accent {
  background: linear-gradient(135deg, #7c3aed, #6d28d9);
  /* same structure as primary, different color */
}
```

### Disabled State
```css
.btn:disabled { opacity: 0.6; cursor: default; }
```

---

## Form Inputs

### Text Input
```css
/* Smoothie */
input, textarea {
  width: 100%;
  padding: 12px 16px;
  border-radius: 12px;
  border: none;
  background: #f1f3fe;
  font-size: 14px;
  font-family: 'Inter', sans-serif;
  color: #181c23;
  outline: none;
}

/* XP */
input, textarea {
  width: 100%;
  padding: 6px 8px;
  border-radius: 3px;
  border: 1px solid #7f9db9;
  background: #fff;
  font-size: 12px;
  font-family: Tahoma, sans-serif;
  color: #000;
  outline: none;
}
```

### Label
```css
/* Smoothie */
label {
  font-size: 11px;
  font-weight: 700;
  color: #414755;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  display: block;
  margin-bottom: 6px;
}

/* XP */
label {
  font-size: 11px;
  font-weight: 700;
  color: #333;
  display: block;
  margin-bottom: 4px;
}
```

---

## Toggle Switch

```html
<div class="toggle" onclick="toggle()">
  <div class="toggle-circle"></div>
</div>
```

```css
/* Smoothie */
.toggle {
  width: 40px; height: 22px;
  border-radius: 11px;
  background: #c1c6d7; /* off */
  position: relative; cursor: pointer;
  transition: background 0.2s;
}
.toggle.on { background: #0058bc; }

.toggle-circle {
  width: 18px; height: 18px;
  border-radius: 50%;
  background: white;
  position: absolute; top: 2px; left: 2px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.2);
  transition: left 0.2s;
}
.toggle.on .toggle-circle { left: 20px; }
```

---

## Badges & Pills

### Severity Badges
```css
.badge { padding: 2px 8px; border-radius: 9999px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }

.badge-critical { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }
.badge-high     { background: #fff7ed; color: #ea580c; border: 1px solid #fed7aa; }
.badge-medium   { background: #eff6ff; color: #2563eb; border: 1px solid #bfdbfe; }
.badge-low      { background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }
```

### Status Badges
```css
.badge-draft     { background: #f1f5f9; color: #475569; }
.badge-active    { background: #dcfce7; color: #16a34a; }
.badge-blocked   { background: #fee2e2; color: #dc2626; }
.badge-waiting   { background: #fef9c3; color: #ca8a04; }
.badge-resolved  { background: #dcfce7; color: #16a34a; }
.badge-progress  { background: #dbeafe; color: #2563eb; }
```

### Trust Labels
```css
.trust-internal    { background: #dbeafe; color: #0058bc; }
.trust-verified    { background: #dcfce7; color: #16a34a; }
.trust-beta        { background: #fff7ed; color: #ea580c; }
.trust-third-party { background: #f1f5f9; color: #64748b; }
```

---

## Sidebar Navigation

### Smoothie Sidebar
```css
.sidebar {
  width: 200px;
  background: rgba(241,243,254,0.3);
  backdrop-filter: blur(20px);
  border-right: 0.5px solid rgba(193,198,215,0.1);
  padding: 20px 12px;
}

.nav-item {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 12px; border-radius: 12px;
  font-size: 13px; cursor: pointer;
  color: #414755; background: transparent;
}
.nav-item:hover { background: #e6e8f3; }
.nav-item.active {
  background: #0058bc; color: white;
  box-shadow: 0 4px 12px rgba(0,88,188,0.2);
}
```

### XP Sidebar uses flat list with selected highlight `#316ac5` + white text.

---

## Tab Bar

### Smoothie Tabs
```css
.tab {
  display: flex; align-items: center; gap: 6px;
  padding: 10px 18px;
  border-radius: 12px 12px 0 0;
  font-size: 13px; font-weight: 500;
  color: #717786; border-bottom: 2px solid transparent;
}
.tab.active {
  color: #0058bc; font-weight: 700;
  border-bottom-color: #0058bc;
  background: rgba(255,255,255,0.6);
}
```

### XP Tabs
```css
.tab { padding: 4px 14px; font-size: 11px; font-weight: 700; border-radius: 4px 4px 0 0; color: #333; }
.tab.active { background: #fff; border: 1px solid #aca899; border-bottom: 1px solid #fff; }
.tab:not(.active) { background: #ece9d8; }
```

---

## Section Headers

```css
/* Page title */
h1 { font-size: 26px; font-weight: 800; color: #181c23; letter-spacing: -0.02em; }

/* Section label (uppercase) */
.section-label {
  font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.1em;
  color: #414755; margin-bottom: 8px;
}

/* Subsection title */
h3 { font-size: 16px; font-weight: 800; color: #181c23; }
```

---

## Task & List Items

### Task Card
```css
.task-card {
  padding: 12px 14px;
  border-radius: 14px; /* Smoothie */
  background: rgba(255,255,255,0.7);
  border: 1px solid rgba(0,0,0,0.06);
  margin-bottom: 6px;
  backdrop-filter: blur(10px);
}
```

### Task Status Circle
```css
.status-circle {
  width: 20px; height: 20px;
  border-radius: 50%;
  border: 2px solid currentColor;
  cursor: pointer;
}
/* Colors: todo=#6366f1, in_progress=#f59e0b, done=#22c55e, backlog=#94a3b8 */
```

### Completed Task Text
```css
.task-done { color: #94a3b8; text-decoration: line-through; }
```

---

## Common Patterns

### Icon + Text Row
```html
<div style="display:flex; align-items:center; gap:12px; padding:14px 18px;">
  <span class="material-symbols-outlined" style="font-size:20px; color:#414755;">icon_name</span>
  <div>
    <div style="font-size:14px; font-weight:600; color:#181c23;">Label</div>
    <div style="font-size:11px; color:#64748b;">Description</div>
  </div>
</div>
```

### Material Symbols Icons
ManAurum uses Google Material Symbols. Include:
```html
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet">
```
Usage: `<span class="material-symbols-outlined">settings</span>`
Filled: `style="font-variation-settings: 'FILL' 1"`

### Empty State
```html
<div style="text-align:center; padding:40px 0; color:#94a3b8;">
  <span class="material-symbols-outlined" style="font-size:40px;">inbox</span>
  <p style="font-size:13px; margin-top:8px;">No items yet</p>
</div>
```

### Loading State
```html
<div style="text-align:center; padding:40px 0; color:#94a3b8;">
  <p style="font-size:13px;">Loading...</p>
</div>
```

---

## Window Rules

- The OS provides the title bar — do NOT render your own
- Fill the entire content area (no extra margins on the window edge)
- Padding: use 24px for Smoothie, 12px for XP
- Be responsive to resizing
- Use `100%` width, avoid fixed widths > window min_size

## App Icon

- 256x256 PNG
- Recognizable at 52x52px
- Uploaded via Dev Hub

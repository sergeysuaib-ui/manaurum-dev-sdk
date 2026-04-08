# Changelog

## 1.1.0 (2026-04-08)

### Added
- **UI Kit reference**: comprehensive design system with exact styles from built-in apps — cards, buttons, inputs, labels, badges, toggles, sidebars, tabs, task cards, section headers, empty/loading states
- **Theme-aware template**: `templates/theme-aware-app.html` demonstrating all design patterns with automatic Smoothie/XP switching
- **Internal hosting docs**: updated publishing reference with paste HTML and upload ZIP hosting on ManAurum (no external hosting needed)
- **Quick-create API docs**: `POST /api/developer/apps/quick-create` for one-step app creation

### Changed
- Design guidelines expanded from basic colors/fonts to full component library
- Publishing flow updated to reflect Telegram-style creation (name only, slug auto-generated)

## 1.0.0 (2026-04-08)

### Added
- `manaurum-app` skill — generate apps from prompts with SDK, manifest, theme support
- `manaurum-deploy` skill — hosting setup, publishing (private/unlisted/public)
- `manaurum-setup` skill — scaffold new project from scratch
- SDK API reference (all postMessage events, SDK methods, 7 permissions)
- Manifest specification (validation rules, field reference, window presets)
- Design guidelines (Smoothie/XP themes, colors, typography)
- Publishing flow (private → unlisted → public, review process)
- Templates: hello-world.html, manifest.json

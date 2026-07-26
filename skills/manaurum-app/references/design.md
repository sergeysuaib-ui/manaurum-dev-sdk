# Designing a v2 app

A v2 app is an **isolated iframe that serves its own CSS**. Nothing from the
Manaurum shell cascades in — no reset, no fonts, no tokens, no component
classes. You are not styling a React island inside our app; you are building a
small self-contained web page that has to look like it belongs next to ours.

That is the whole contract, and it cuts both ways: nothing of ours can break
your layout, and nothing of ours will save you from an unstyled one.

## Start from the artifact, not from this page

`templates/v2-starter/src/static/app.css` is a complete stylesheet for a
Manaurum app: tokens, layout, cards, lists, forms, buttons, badges, empty
states, skeletons, mobile. Copy it and change values at the top.

**Do not hand-roll a design from the notes below.** The notes exist to tell you
*when* to reach for each pattern and which mistakes are expensive. The CSS is
the reference for *what* it looks like. An agent that reads this page and then
invents its own layout has done the job backwards.

The starter's `index.html` shows every pattern in use against real data. Read
the two files together.

## Appearance and accent — the one thing to get right

The shell tells your app which appearance (light/dark) and which accent colour
the user is in. Read those; do not guess at them.

```js
// manaurum:init payload → what actually varies
{ appearance: 'light' | 'dark',        // ← style off this
  accent: 'core-blue' | 'teal' | 'lavender' | 'coral'
        | 'rose' | 'graphite' | 'amber' | 'green',
  theme: 'smoothie',                   // ← constant. ignore it.
  device: 'mobile' | 'desktop', … }
```

Three traps, each of which has shipped:

1. **`theme` is always `'smoothie'`.** The XP look is a desktop-shell easter
   egg for one tenant and it deliberately stops at the window frame — the shell
   never passes `'xp'` into an iframe (MAN-235). Branching on `theme`, or
   shipping a second set of styles for it, is dead code that cannot run.

2. **`app.onThemeChange(cb)` hands your callback the string `'smoothie'`** —
   that constant, not the thing that changed. To learn the new appearance you
   must read the getters *inside* the callback:

   ```js
   const app = ManaurumV2.init();
   app.onReady((ctx) => apply(ctx.appearance, ctx.accent));
   app.onThemeChange(() => apply(app.appearance, app.accent));  // ignore the arg
   ```

   A handler written as `onThemeChange(t => applyTheme(t))` compiles, runs, and
   never responds to dark mode.

3. **`prefers-color-scheme` is not Manaurum's appearance.** It tracks the
   *browser*. A user in OS dark mode with a light browser profile gets a light
   app sitting in a dark desktop. Use it only as the standalone default, before
   any shell message, and let the shell win once it speaks. The starter's inline
   `<head>` script does exactly this in ~20 dependency-free lines.

Write the values onto the root element and let CSS do the rest:

```js
document.documentElement.dataset.appearance = ctx.appearance;
document.documentElement.dataset.accent = ctx.accent;
```

```css
:root { --app-bg: #f7f7f9; --text-primary: #0e0f12; }
:root[data-appearance="dark"] { --app-bg: #17171a; --text-primary: #f5f5f7; }
:root[data-accent="lavender"] { --accent: #b49dff; }
```

## Window rules

- **The OS draws the title bar. Never draw your own.** You get the content area.
- **Fill it.** No outer margin against the window edge; one container owns the
  page padding.
- **Be resizable.** Percentage widths and a `max-width`, never a fixed width.
- **No native dialogs.** The shell's iframe sandbox has no `allow-modals`, so
  `alert()` / `confirm()` / `prompt()` are dead inside the desktop — and they
  work on the standalone URL, so "it worked in my browser" proves nothing. A
  `confirm()`-gated delete button becomes a button that does nothing.

## Layout: how to compose a page

Most apps do not need a novel layout. This shape covers almost all of them:

```
┌───────────────────────────────────────────┐
│  Title                        [ Action ]  │  ← page-header
│  One line saying what this is             │
├───────────────────────────────────────────┤
│  ┌─────────────────────────────────────┐  │
│  │ SECTION                             │  │  ← card
│  │ content                             │  │
│  └─────────────────────────────────────┘  │
│  ┌─────────────────────────────────────┐  │
│  │ SECTION                             │  │  ← card
│  └─────────────────────────────────────┘  │
└───────────────────────────────────────────┘
```

- **One primary action per view.** Everything else is secondary or a plain link.
  Two blue buttons side by side means neither is the answer.
- **Group into cards, don't box everything.** Related fields share one card. A
  card per field looks like a form someone lost control of.
- **Take spacing from the scale** (`--space-*`) and use few values: a small gap
  inside a group, a medium one between groups, a large one before a new section.
  Consistent spacing is most of what makes a layout look designed.
- **Cap the width.** `max-width: 1024px`. Text lines that run the full width of
  a maximised window are unreadable.
- **In light mode the page recedes and cards come forward** (white on grey); in
  dark it inverts (cards lighter than the page). Getting that backwards is why
  most dark themes look flat.

## Patterns, and when to use them

Classes are in `app.css`; this is the judgement that goes with them.

| Pattern | Class | Use it for |
|---|---|---|
| List | `.list` / `.row` | Any collection. Rows separated by hairlines — never boxes inside boxes. |
| Row content | `.row-main`, `.row-title`, `.row-sub`, `.row-meta` | Title and optional subtitle left, metadata hugging right. |
| Form field | `.field`, `.field-label`, `.input`, `.field-help` | Label **above** the input, help text below. |
| Buttons | `.btn` + `.btn-primary` / `-secondary` / `-ghost` / `-danger` | One primary per view. |
| Empty state | `.empty` | Every list, and every filter that can return nothing. |
| Loading | `.skeleton`, `.skeleton-line` | Any fetch that can take longer than an instant. |
| Badge | `.badge` + `-accent` / `-success` / `-warning` / `-danger` | Short status. Not for sentences. |
| Inline status | `.status` + `-success` / `-error` | Feedback next to the control that caused it. |
| Key/value | `.kv` | Read-only detail pairs. |

Three of those deserve more than a table row, because skipping them is what
makes an app feel unfinished:

**Empty states.** An empty list with no empty state reads as a broken app. Say
what would be here and offer the action that puts something here. Distinguish
*empty* ("no orders yet") from *unknown* ("could not load") from *filtered to
nothing* ("no orders match this filter" + a clear-filter button) — they are
three different messages and collapsing them into one blank panel is a bug
report waiting to happen.

**Loading.** Use a skeleton shaped like the content, not the word `Loading…`.
It keeps the layout from jumping when data lands, which is most of what makes an
app feel fast. Give every skeleton an explicit width.

**Interactive affordances.** Only give a row a hover state if clicking it does
something — a hover on an inert row is a promise the app does not keep. And
never remove the focus ring; keyboard users navigate your app too.

## Mobile

Branch on the **device the shell reports**, not on a width media query:

```js
document.body.dataset.device = ctx.device;   // 'mobile' | 'desktop'
```

```css
body[data-device="mobile"] .app { padding: var(--space-4); }
body[data-device="mobile"] .btn { min-height: 44px; }
```

An app window can be narrow on a desktop, and a phone opens your app full
screen — a width query gets both cases wrong. The shell is the only thing that
actually knows. It also re-posts `manaurum:device-change` on an orientation flip
or a resize across the breakpoint, so listen for that too.

Give mobile 44px tap targets, full-width primary buttons, and a stacked header.

## Icons

Manaurum's own UI uses Google Material Symbols. You may use them, but **do not
hot-link a font in an app you care about** — a webfont that arrives late reflows
your layout and one that fails to arrive changes your metrics. Self-host the
subset you need in your image, or use text and simple glyphs as the starter
does.

Your **app icon** (`frontend.icon` in the manifest) is separate: an emoji, a
full URL, or an absolute `/api/catalog/media/...` path. A relative path like
`icons/app.svg` is not resolved — it renders as that literal string on the tile.
Omit it and you get a clean generic placeholder, which beats a broken one.

## Do not

- **Do not use gold or yellow as your palette, and never `hue-rotate`.** Both
  are banned in Manaurum surfaces. If the user picks the amber accent, that is
  their choice arriving through `--accent`; it is not a licence to design in it.
- **Do not hardcode hex values in your markup.** Change a token, not 40 rules.
- **Do not style with inline `style=` attributes.** They cannot respond to
  appearance changes and they cannot be overridden.
- **Do not ship a second stylesheet for the XP theme.** It cannot reach you.

## The shared design system, and why the starter vendors its tokens

Manaurum's tokens and component catalogue are public and need no auth:

- `https://manaurum.com/api/library/tokens.css` — the token file
- `https://manaurum.com/library` — the component catalogue

`app.css` deliberately uses **the same token names** as that file, so adopting
it later is one `<link>` and no rule below it has to move.

It vendors the *values* rather than linking the file today because a stylesheet
has no graceful degradation: a dynamically-imported SDK can fall back to
`fetch()`, but a `<link>` that fails to load leaves your user looking at
unstyled HTML. Two concrete gaps also argue for waiting — the token file
documents a hostname that does not resolve, and it defines 6 of the 8 accents
the OS actually offers, so `amber` and `green` silently fall back to blue.

**MAN-1401** is the open decision on how a v2 app should consume the shared
system. When it lands, this section is what changes.

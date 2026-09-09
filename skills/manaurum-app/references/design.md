# Designing a v2 app

## Never

Each row is a rule an app has shipped without at least once — four of them in a
single app, whose interface was rejected on sight while every technical check
passed. If you read nothing else on this page, read the table.

| Never | Why |
|---|---|
| A tab bar or a sidebar as navigation | The window is often 900px wide inside a desktop that already navigates. A sidebar spends a third of the width repeating what the OS said. Stack sections as cards. |
| Style off `prefers-color-scheme` as your only signal | It tracks the *browser*, not Manaurum, so the app ends up light inside a dark desktop. Appearance and accent arrive in `manaurum:init` **inside `e.data.payload`** — reading them off `e.data` is `undefined` and applies nothing while the handshake still looks fine. Write them on `<html>`; keep the media query only as the standalone default. |
| A `var()` fallback with a token that does not exist | `var(--text-muted, #666)` is a hardcoded colour wearing a token's clothes: no appearance change will ever touch it, and nobody reviewing the diff sees a hex. The list of real names is the token table below. |
| A click target that does not look like one | The mirror of the hover rule. A row with a handler needs `.row.is-interactive` — cursor, hover, focus ring — and stays an `<li>`; `<button class="row">` brings ButtonFace, Arial and a content-width box, so the list stops filling the card. |
| A sentence inside a badge | A badge is a status word (`overdue`). A phrase turns a scannable list into a wall of text. |
| More than one primary button per view | Two blues side by side — or one in every row — means none of them is the answer. |
| A hover state on something inert | Hover is a promise that clicking does something. Keep the focus ring; keyboard users navigate too. |
| Hex values in the markup, or inline `style=` | You end up changing 40 rules instead of one token, and an inline colour cannot follow an appearance change. |
| `alert()` / `confirm()` / `prompt()` | The shell's iframe has no `allow-modals`. They return silently, so a `confirm()`-gated delete button does nothing — and they work on the standalone URL, so testing there proves nothing. |
| `overflow: hidden` + a fixed height on your root | The window cannot scroll an iframe app. Clip the root and the bottom of every long view is unreachable, with no scrollbar anywhere. |
| Gold or yellow as a palette, `hue-rotate`, a hot-linked webfont | The first two are banned across Manaurum surfaces; a font that arrives late reflows your app and one that never arrives changes its metrics. |

The rest of this page is *when* to reach for what. The table above is what gets
an app rejected.

A v2 app is an **isolated iframe that serves its own CSS**. Nothing from the
Manaurum shell cascades in — no reset, no fonts, no tokens, no component
classes. You are not styling a React island inside our app; you are building a
small self-contained web page that has to look like it belongs next to ours.

That is the whole contract, and it cuts both ways: nothing of ours can break
your layout, and nothing of ours will save you from an unstyled one.

## Start from the artifact, not from this page

`<plugin>/templates/v2-starter/src/static/app.css` is a complete stylesheet for a
Manaurum app: tokens, layout, cards, lists, forms, buttons, badges, empty
states, skeletons, mobile. Copy it and change values at the top. (`<plugin>` is
the plugin root — the directory with `skills/` and `templates/` side by side. If
the read fails, find the root and retry rather than writing your own.)

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

Then check it, because this is the one failure that is invisible in a code
review and obvious in a picture: `<plugin>/templates/preview.py` frames your app
the way the shell does and lets you ask for any appearance and accent —
`manaurum-app/SKILL.md` → **Step 3.5**. Its second badge answers exactly this
question: `appearance applied` or `appearance IGNORED`.

**The values arrive in `e.data.payload`, not on `e.data`.** An app that reads
`e.data.appearance` gets `undefined`, applies nothing, and still answers the
handshake perfectly — so every check stays green while it renders light inside a
dark desktop. The standalone URL hides it too, because there the
`prefers-color-scheme` fallback runs. This shipped and lived four days.

## The tokens, and which neighbour to pick

This is the whole list. **A name that is not here does not exist**, and
`var(--text-muted, #666)` with a name that does not exist is not a token with a
safety net — it is a hardcoded colour that no appearance change will ever
touch, and the fallback is what you will see. `check_ui.py` fails on it.

| Token | What it is | vs its neighbour |
|---|---|---|
| `--app-bg` | The page behind everything. | Recedes in light, and is the *darkest* layer in dark. Never put content directly on it without a card. |
| `--surface-card` | A card: the raised surface content lives on. | Lighter than `--app-bg` in dark, white in light. If your cards and page look the same, you inverted this. |
| `--surface-panel` | A quieter inset area inside a card (a toolbar strip, a preview well). | Sits *behind* card content, not in front of it. |
| `--surface-input` | Field backgrounds only. | Same value as the card in light, distinct in dark — do not substitute one for the other. |
| `--surface-hover` / `--surface-active` | Row and control feedback. | Translucent overlays, so they work on any surface. Only ever on something clickable. |
| `--border-hairline` | The line between rows, and card edges. | `--border-hairline-strong` is for a border that must read as an edge (inputs, dividers between sections), not for emphasis. |
| `--text-primary` | Titles and body copy. | `--text-secondary` is a subtitle or help text; `--text-tertiary` is metadata (timestamps, counts) and is too faint for anything a user must read. |
| `--text-inverted` | Text on a filled dark surface. | Not "white" — it flips with appearance. |
| `--accent` | The user's accent, from the shell. | `--accent-hover` for the hover state, `--accent-soft` for tinted backgrounds (badges, ghost hover, `mark`), `--accent-contrast` for text *on* the accent. Never write your own tint of it. |
| `--color-danger` / `-success` / `-warning` | Status meaning, not decoration. | Each has a `-soft` companion for the background of a badge or banner; the solid one is for text and icons. |
| `--space-1…12` | The spacing scale (4, 8, 12, 16, 20, 24, 32, 40, 48). | Use few of them: small inside a group, medium between groups, large before a section. |
| `--radius-button` / `-input` / `-card` / `-panel` / `-pill` | Corner radii, by role. | Pick by what the thing *is*, so a card and a button never share a radius by accident. |
| `--fs-caption…--fs-title-2` | The type scale. | `--fs-body` is default copy, `--fs-body-lg` a row title, `--fs-footnote` a subtitle, `--fs-caption` a label. |
| `--motion-fast` / `--motion-normal`, `--ease-standard` / `--ease-spring` | Transition timing. | Fast for hover and colour, normal for anything that moves. |
| `--shadow-card` / `--shadow-button` | Elevation. | Two levels exist on purpose; a third one you invent will not match the OS. |

## Window rules

- **The OS draws the title bar. Never draw your own.** You get the content area.
- **Fill it.** No outer margin against the window edge; one container owns the
  page padding.
- **Be resizable.** Percentage widths and a `max-width`, never a fixed width.
- **One scroll container, and it is yours.** By default it is the document
  itself: never put `overflow: hidden` together with a fixed `height` on your
  root. A fixed shell (header, tab bar, pinned sheet) needs all three of: a
  `display: flex; flex-direction: column` root, `flex: 1` **and**
  `overflow: auto` on the element holding the content, and `min-height: 0` on
  the flex items in between. `overflow: auto` alone does nothing — a block
  with auto height grows to fit its content, so it never overflows and there
  is nothing to scroll.

  The window's content area scrolls a *builtin* app. It can never scroll
  yours: your app is an iframe at `height: 100%` of that box, so the shell's
  scrollbar never appears, and if nothing in your document scrolls, nothing
  does. The `overflow: hidden` in a mockup is the mockup drawing a fake window
  frame — it ports perfectly, and the scroller it was paired with does not.
  That is how this ships. The SDK measures it at run time and console-errors
  with the offending element; `init({ layoutCheck: false })` if you clip on
  purpose.

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

**No sidebar, no tab bar, no toggle switches.** `app.css` deliberately ships
none of the three, and this is the reason: an app window is not a browser window.
It is often 900px wide and sits inside a desktop that already has its own
navigation, so a sidebar spends a third of the width repeating what the OS
already told the user. If a page needs sections, stack them as cards; if it
needs two views, use two `.btn-ghost`s and swap the content; if it needs a
boolean, use a checkbox with a `.field-label`. Reach for a sidebar only when a
list genuinely drives a detail pane, and then build it from `.list` + `.row`
rather than inventing a component.

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

**Interactive affordances — the rule runs both ways.** Only give a row a hover
state if clicking it does something: a hover on an inert row is a promise the
app does not keep. And the mirror of it, which is the half that ships broken:
**anything clickable must say so.** A `.row` with a handler gets
`.row.is-interactive`, which is where the cursor, the hover and the focus ring
come from — without it you have a silent click target that only the person who
wrote it knows about.

It stays an `<li>`. `<button class="row">` is the obvious guess and it is wrong:
a button arrives with its own ButtonFace background, its own border, Arial over
your tokens, and a width that hugs its content — so the list visibly stops
short of the card edge. That is what an owner saw and described as "the list is
not full width, the rows look like buttons". Put one delegated handler on the
`<ul>`, give each row `data-id` and `tabindex="0"`, and answer Enter as well as
click. `check_ui.py` fails on both halves of this rule.

Never remove the focus ring; keyboard users navigate your app too.

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

- **Do not rely on the bare `hidden` attribute to hide anything.** `[hidden]` is
  only `display: none` in the *browser's* stylesheet, and any author `display`
  rule beats it — so `.empty { display: flex }` silently turns `el.hidden = true`
  into a no-op and your empty state renders stacked on top of the list it was
  meant to replace. This shipped once. If you write your own stylesheet instead
  of copying `app.css`, carry this line into it:

  ```css
  [hidden] { display: none !important; }
  ```

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

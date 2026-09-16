# Design review: my-app

<!--
  Step 3.5, part 5. Copy this BESIDE the app directory, not inside it -
  everything inside is packed into the deploy.

  Why it exists. Screenshots alone did not work. An agent photographed its
  app, looked at the pictures, criticised them out loud against the list of
  prohibitions - and found nothing, because nothing on the list was broken.
  The owner opened the app and rejected it on sight. Every mistake the owner
  named was visible in that first screenshot: thirteen accent filters taking
  half the screen, metadata breaking the rows, a headline one typographic step
  above its own caption, a heading repeated inside its card.

  A list of prohibitions asks "did I break a rule". These questions ask "would
  I use this", which is the question the owner asks. Answer them in writing,
  one block per screen, then fix what the answers name, re-shoot, and answer
  again. Put the final answers in your reply to the person.

  The numbers in brackets come from the bar across the top of each preview
  screenshot; copy them, do not estimate.
-->

## Screen: `#____`  (screenshot: ____.png)

**Kind** — sorting / reading / entering: ____

1. **The most important thing on this screen is ____.**
   Does it look the most important — biggest, heaviest, first? If something
   else wins (a filter bar, a header, a badge), say what, and fix it.

2. **Accent-coloured elements on the first screen: [__].**
   Over four: which of them are repeated controls (make them `.chip` or
   `.btn-secondary`) and which are statuses on most rows (make them neutral or
   drop them)?

3. **Cover the metadata.** With the dates, categories and counts hidden,
   does each list row still say what it is? If not, the row is a ledger line,
   and this is probably not a sorting screen.

4. **Before the first row of data: [__% of the window].**
   What takes that space? More than a third on a list screen means the
   filters are the content. Collapse them, cut them to the busiest few, or
   move the rest behind a `<select>`.

5. **Is it laid out as its kind?** A reading screen has a headline scale, a
   text column and almost no accent. A sorting screen has short rows, short
   metadata on the right, and a status on the few rows that need a decision.
   An entering screen has one card of fields and one primary action. Which
   one is this built as - and is that the kind you wrote above?

**Fixed after this review:**

-

**Left as it is, and why:**

-

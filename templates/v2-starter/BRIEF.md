# Brief: my-app

<!--
  THIS FILE IS THE SPEC, AND IT IS YOURS.

  It is written in plain language on purpose: you should be able to read it,
  disagree with it, and change it without knowing how to program. Everything
  the app is built from is derived from the six sections below, so editing a
  line here and asking for a rebuild changes the app.

  The agent fills this in with you by asking questions — one at a time — and
  proposes wording you correct. It does not need you to know what a database
  or an API is.

  Anything the agent decided on your behalf is listed in §6 and marked
  (assumed). Those are the lines to read first: they are the guesses.

  How each section becomes the app:

    §1 Who uses it  →  who is allowed in (route auth, app visibility)
    §2 What they do →  the screens, and the API routes behind them
    §3 What is kept →  the data model (migrations/*.sql, or os.kv keys)
    §4 Assistant    →  agent_capabilities[] + a POST /agent/<name> handler each
    §5 Never        →  the guardrails; things deliberately not built
    §6 Assumed      →  the open decisions, cheapest to change now
-->

## 1. Who uses this

<!-- Real people in real roles. "Me", "my team of 4", "anyone with the link". -->

-

## 2. What they do with it

<!-- One line per thing a person needs to accomplish, in their words.
     Each becomes a screen or an action. If a line needs the word "and",
     it is probably two lines. -->

-

## 3. What must still be there tomorrow

<!-- The things the app has to remember after everyone closes it. Name them
     the way you say them out loud ("an order has a customer, a pickup date,
     and a list of items"). This is the data model; getting it wrong is the
     expensive mistake, which is why it is a question and not a guess. -->

-

## 4. What the Assistant can do on my behalf

<!-- The OS Assistant is the chat in the desktop. Finish the sentence:
     "I want to be able to ask it to ______."
     Reads ("what's due today?") and writes ("mark this done") both count.
     An app that declares none of these is invisible to the Assistant, and
     it will answer questions about your app by guessing. -->

-

## 5. What this app must never do

<!-- Deletion, sending things to people, spending money, touching anything
     outside this app. Say it here and it will not be built. -->

-

## 6. Decided for you (assumed)

<!-- Every guess the agent made because the answer was "I don't know", plus
     the reason it is safe to change. Review these; they are the cheapest
     things to fix now and the most expensive later. -->

-

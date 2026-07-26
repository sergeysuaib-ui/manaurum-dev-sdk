# Discovery — interview before you write anything

The person asking for an app usually cannot program, and — this is the part
that gets misread — **they are not withholding a specification. They do not
have one, and they do not know what they are supposed to tell you.**

So "build me an app for my shop" is not a brief with details omitted. It is the
whole of what they know how to say. If you start writing files from it you will
invent the data model, the screens and the Assistant capabilities yourself, and
they will not be able to tell you that you guessed wrong until the app exists
and is wrong. Rebuilding at that point costs more than asking did.

The fix is six questions and a file.

## The rules

1. **One question per message.** Not a form, not a numbered list of six. A
   conversation. Someone who cannot program will abandon a form and will
   answer a question.
2. **No jargon, ever.** Never "what's your schema", "REST or GraphQL",
   "do you need auth". Ask what they keep, who they show it to, what they wish
   they could ask for.
3. **After two or three answers, stop asking and propose.** Say what you now
   think the app is, in their words, and ask them to correct it. People are
   dramatically better at correcting a wrong guess than at specifying from
   nothing. **This is the highest-leverage move in the whole process** — if you
   only do one thing from this page, do this.
4. **Write `BRIEF.md` before the first line of code.** Copy the template from
   `templates/v2-starter/BRIEF.md`. It is the spec, they own it, and everything
   downstream derives from it.
5. **Never gate on the interview.** If they say "just build me a todo list",
   do not refuse and do not interrogate. Draft the brief yourself, show it, and
   ask **one** confirming question. A product that will not move until a form is
   complete is a form.
6. **Always terminate.** "I don't know" is a complete and acceptable answer.
   Decide, write it into §6 as `(assumed)`, say out loud what you decided, and
   move on. Never ask the same question twice in different words.

## The question bank

Ask in roughly this order, and **skip anything they already told you.** Six is
the ceiling, not the target — three good answers plus a proposal is often
enough.

| # | Ask | You are actually learning |
|---|---|---|
| 1 | Who is going to use this — just you, or other people too? | route auth, app visibility |
| 2 | Walk me through what you'd do with it on a normal day. | the screens, and the API routes behind them |
| 3 | What does it need to still remember tomorrow morning? | **the data model** |
| 4 | When you look at one of those, what do you need to see about it? | the fields |
| 5 | Is there anything you'd want to just *ask* for, instead of clicking around? | `agent_capabilities[]` |
| 6 | Anything it must never do? | guardrails |

Question 3 is the one to protect. It is the data model, it is the expensive
thing to get wrong, and it is the one people can answer perfectly in their own
words if you don't ask it in yours.

## When they don't know

Decide. Then say what you decided and why it is safe.

| They can't answer | Default | Because |
|---|---|---|
| Who uses it | just them — `visibility: private`, every route `auth: "user"` | narrowest thing that works; widening later is a one-line manifest change |
| What it remembers | the one obvious noun from their sentence, with a title, a date and a done flag | covers most small apps; adding a column is an additive migration |
| Which fields | title, created date, status | you can see a list and a detail with these three |
| Assistant | one read-only "list what's in here" capability | makes the app visible to the Assistant; cannot damage anything |
| Never do | no deleting, no sending anything to anyone | the two that are hard to walk back |

Every one of those goes into §6 marked `(assumed)`, and you tell them:
"I've assumed X, Y and Z — they're all in section 6 of the brief and easy to
change."

## Worked transcript — a vague sentence to a brief

> **User:** build me an app for my bakery

**Agent:** Happy to. Who's going to be using it — just you, or other people
too?

> **User:** me and my two bakers

**Agent:** Got it. Walk me through a normal day — what would you be doing in
it?

> **User:** taking cake orders from customers over the phone and then making
> sure we actually make them on the right day

**Agent:** That makes sense. What does it need to still remember tomorrow
morning, after everyone's gone home?

> **User:** the orders. who ordered, what they want, when they're picking it up

**Agent:** Here's what I think you're describing — correct me where I've got it
wrong:

> An **order book** for three people. Each order has a **customer** (name and
> phone), **what they want** (a description, and how many), a **pickup date**,
> and a **status** — one of *taken*, *baking*, *ready*, *collected*. The main
> screen is a list of orders sorted by pickup date, so today's work is at the
> top. You can add an order, edit one, and move it along the statuses.
>
> Nothing gets deleted — an order that falls through gets marked, not removed —
> so you keep a record of what happened.

> **User:** yes but there's usually a deposit, we take half up front. and I need
> to know if they've paid it

**Agent:** Noted — a **deposit** on each order: the amount, and whether it's
been paid. Should the app add the amounts up for you anywhere, or just record
them per order?

> **User:** just per order for now

**Agent:** Last one. Is there anything you'd want to just *ask* for, rather than
clicking around to find?

> **User:** what's due tomorrow. that's the thing I check constantly

**Agent:** That's a good one — the Assistant can answer it from anywhere in the
desktop. I've written this up as `BRIEF.md`; read it and change anything that's
off. I've assumed a couple of things and flagged them in section 6.

**Resulting `BRIEF.md`:**

```markdown
# Brief: bakery-orders

## 1. Who uses this
- The owner and two bakers. Three people, one shared order book.
- Private to this workspace. Customers never see it.

## 2. What they do with it
- Take a cake order while the customer is on the phone.
- See what has to be baked today, and what is coming tomorrow.
- Move an order along as it is baked, made ready, and collected.
- Correct an order after taking it (people change their minds).
- Record whether the deposit has been paid.

## 3. What must still be there tomorrow
- An **order**: customer name, customer phone, what they want (description),
  how many, pickup date, status, deposit amount, deposit paid yes/no,
  when it was taken.
- Status is one of: taken, baking, ready, collected, fell-through.
- Orders are never deleted. A cancelled order becomes "fell-through".

## 4. What the Assistant can do on my behalf
- "What's due tomorrow?" — list orders by pickup date, with customer and item.
- "What still needs baking today?" — same list, filtered to unbaked.

## 5. What this app must never do
- Never delete an order.
- Never contact a customer. It records the phone number; it does not use it.
- Never handle card payments. Deposit paid is a yes/no somebody ticks.

## 6. Decided for you (assumed)
- (assumed) Money is recorded as a plain amount in one currency, with no
  totals or reporting. Adding a total later is easy; changing how money is
  stored is not, so say now if you invoice in more than one currency.
- (assumed) All three people can do everything — no separate manager role.
  Splitting permissions later is a change to who-can-do-what, not to the data.
- (assumed) Orders keep for a year, then stay in the app but drop off the
  default list.
```

Read what that interview did: **it never asked a technical question**, and it
arrived at a five-status enum, a nullable-money field, a soft-delete rule and
two Assistant capabilities. The deposit — the thing most likely to be wrong six
weeks in — surfaced because a proposal was there to be corrected. It would not
have come out of a question.

## Worked transcript — the user who doesn't know

Terminating is the requirement here, not extracting answers.

> **User:** i need something to keep track of my clients

**Agent:** Sure. Who'll be using it — just you, or other people as well?

> **User:** dunno, me for now I guess

**Agent:** I'll set it up for just you then; opening it up later is a one-line
change. What would you need it to remember about a client?

> **User:** I don't know really

**Agent:** No problem — I'll start with the obvious ones and you can tell me
what's missing once you can see it. Here's what I'm going to build:

> A **client list**. Each client has a **name**, a **note** you can type
> anything into, a **status** of *active* or *inactive*, and the **date you
> added them**. One screen: the list, newest first, with a way to add a client
> and open one to edit it. Nothing is ever deleted. The Assistant can answer
> "who are my active clients?".

Anything obviously wrong in that?

> **User:** no idea, just build it

**Agent:** Then I'll build exactly that. Four things I've decided for you are in
section 6 of `BRIEF.md` — the one worth a look is that there's nowhere to record
contact details yet, since I didn't want to guess whether you need email, phone
or an address. Say the word and I'll add it.

Note what did **not** happen: the same question was never asked twice, the third
"I don't know" did not produce a fourth question, and the run ended with a
buildable brief. The agent also named the *single* most consequential gap
instead of reciting all four assumptions — one flag gets read, four get skipped.

## From brief to build

Derive, and keep the derivation visible. When you change the app because the
brief changed, say which line you were following.

| Brief | Becomes |
|---|---|
| §1 who uses it | `auth: "user"` on every route; `visibility.mode`; whether any route is `anonymous` |
| §2 what they do | the screens; one `runtime.api_routes` entry per collection **and** per item path (`/api/orders` *and* `/api/orders/*`) |
| §3 what is kept | the data model → `migrations/0001_init.sql` (or `os.kv` keys for something small); the `data` block |
| §4 Assistant | one `agent_capabilities[]` entry per line, each served at `POST /agent/<name>` — never in `api_routes` |
| §5 never | absent endpoints, and the guardrails inside the ones that exist |
| §6 assumed | what you re-read first when they say "this isn't right" |

Two checks before you write code, and one after:

- **Every line of §3 has a home** in the data model, and nothing is in the data
  model that no line of §3 asked for.
- **§4 is not empty.** An app with no `agent_capabilities` is invisible to the
  Assistant, which will then answer questions about it by guessing. If they had
  no answer to question 5, the default read-only "list what's in here" is the
  floor.
- **After building, re-read the brief and say what you did not do.** Anything
  in §5 you could not enforce, anything in §2 you left out — say it plainly
  rather than letting them discover it.

## Keep the brief alive

`BRIEF.md` ships in the project, next to the code. When they ask for a change,
**edit the brief first, then the code.** Two reasons: the next person (or the
next agent, in a month, with none of this conversation) reads the brief to
understand what the app is for, and the brief is what the self-check verifies
against. A brief that stops matching the app is worse than no brief, because it
is trusted.

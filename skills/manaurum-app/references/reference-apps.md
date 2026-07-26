# Reference apps — what a real v2 app looks like

Four production v2 hosted apps, picked because each one answers a different
question. None was written to be an example; they all have users, which is why
they stay honest.

**How to read this page.** The apps live in the `manaurum` monorepo, so if you
have the repo, open them — that is always better than reading about them. If you
do not, the excerpts below are the load-bearing parts, chosen so the page stands
alone. Nothing here is a snippet you paste unchanged; they are shapes to copy.

| Rung | App | Read it when you are asking |
|---|---|---|
| Ceiling | `family-space-v2` (77 files) | "How far does this runtime actually go?" — and it is the manifest reference. |
| Small | `shift-checklist` (22 files) | "What does a complete app look like when I can still read all of it?" |
| Testing | `libi` (82 files, 11 test files) | "How do I test this?" |

`Finance` becomes the ceiling reference once it lands (MAN-1404); it is a real
business app with a data model, AI tools and reporting. Until then
`family-space-v2` holds that slot.

---

## Small — `shift-checklist`, 22 files

The one to read whole. A restaurant owner builds opening/closing checklists in
the Manaurum desktop; staff tap through them on a wall-mounted tablet in the
kitchen. Two audiences, two surfaces, one container.

```
shift-checklist/
├── Dockerfile              manifest.json          requirements.txt
├── migrations/0001_init.sql, 0002_iter3.sql
└── src/
    ├── main.py             mounts both routers, serves both static surfaces
    ├── api/admin.py        the owner's surface   — every route auth: "user"
    ├── api/kiosk.py        the tablet's surface  — every route auth: "anonymous"
    ├── auth.py db.py       shared infrastructure
    ├── ai.py notifications.py scheduler.py
    └── static/index.html + admin.js/css, kiosk.html + kiosk.js/css
```

**What it teaches: `src/api/` split by *surface*, not by noun.** The split is
not `routes_users.py` / `routes_shifts.py`; it is admin vs kiosk, because that
is where the auth boundary falls. Both files touch shifts. Draw your module
lines where your trust boundaries are, and the auth story reads itself.

That shows up directly in the manifest — 18 `auth: "user"` routes under
`/api/admin/*`, 11 `auth: "anonymous"` routes under `/api/kiosk/*`:

```json
{"path": "/api/admin/templates/*", "auth": "user"},
{"path": "/api/kiosk/shift/start", "auth": "anonymous"}
```

A tablet bolted to a kitchen wall has no user to log in, so those routes are
declared anonymous *deliberately* and the app authenticates the device itself.
There is no implicit anonymous fallback — an undeclared path is `404
route_not_declared` at the gateway and never reaches your container.

Also note what is *not* in `api_routes`: `/healthz`, the static files, and
`/agent/<name>`. Only `/api/*` is gated.

---

## Ceiling — `family-space-v2`, 77 files

Twenty backend modules over shared infrastructure, and the richest manifest we
ship: hosted mode, per-route auth levels including an anonymous Telegram
webhook, an egress allow-list, allow-list visibility, seven platform
capabilities, five agent capabilities with routing hints and examples, two
migrations, a real frontend build, a tenant-migration script, a README.

```
src/  routes_items.py routes_spaces.py routes_invites.py routes_memberships.py
      routes_files.py routes_ai.py routes_dashboard.py routes_profile.py …
      agent_routes.py          ← the OS Assistant surface
      auth.py capability.py db.py deps.py schemas.py sharing.py   ← shared
```

**What it teaches: domain routers over a thin shared core.** `sharing.py` holds
the membership guard; every router calls it rather than re-deriving access. When
you add `routes_files.py`, you inherit the access rules instead of
reimplementing them.

It is also the manifest and `agent_capabilities` reference — see
`v2-platform.md § agent_capabilities[]`, whose examples are taken from here.

One caveat worth knowing before you copy its styling: it uses Tailwind, not the
Manaurum design system. A v2 app is an isolated iframe serving its own CSS, and
how a containerised app should consume the OS design tokens is an open
architectural question (MAN-1401) — not something this app answers.

---

## Testing — `libi`

The only app that shows what a tested v2 app looks like: 11 test files, 3
migrations, split into a pure-function suite (`test_parser.py`,
`test_schemas.py`, `test_clock.py`, `test_growth.py`, `test_digest.py`) and a
DB-backed suite (`*_pg.py`).

Testing a v2 app is not exotic — it is pytest against your own modules. The one
genuinely non-obvious piece is the DB fixture, and it is worth copying almost
verbatim, because all three of its decisions were paid for:

```python
# tests/conftest.py
_DSN = os.environ.get("MANAURUM_TEST_PG_DSN", "").strip()
# Apply every migration in order so the test schema matches what the deploy
# pipeline builds — a new migration is picked up instead of silently un-run.
_MIGRATIONS = sorted((Path(__file__).resolve().parents[1] / "migrations").glob("*.sql"))
_SCHEMA = "libi_test"

async def _configure(conn) -> None:
    """Mirror src/db.py's per-connection setup: search_path + json/jsonb codecs.
    Without the codecs every route that passes a dict payload fails with
    DataError — audit 2026-07-19 M1: the original fixture skipped them, so the
    committed API tests could never pass against a real PG."""
    await conn.execute(f'SET search_path TO "{_SCHEMA}", public')
    for typ in ("jsonb", "json"):
        await conn.set_type_codec(
            typ, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

@pytest_asyncio.fixture
async def db():
    if not _DSN:
        pytest.skip("MANAURUM_TEST_PG_DSN not set — DB-backed test skipped")
    conn = await asyncpg.connect(dsn=_clean_dsn())
    await conn.execute(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE')
    await conn.execute(f'CREATE SCHEMA "{_SCHEMA}"')
    await _configure(conn)
    for mig in _MIGRATIONS:
        await conn.execute(mig.read_text(encoding="utf-8"))
    try:
        yield conn
    finally:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE')
        await conn.close()
```

Three decisions, each one a bug someone already hit:

1. **Real Postgres, not SQLite.** asyncpg's semantics diverge — parameter
   binding, types, `jsonb`. A suite that passes on SQLite tells you nothing
   about what your container will do.
2. **Skip cleanly when `MANAURUM_TEST_PG_DSN` is unset** instead of failing.
   The pure-function suite then still runs everywhere, including in a CI job
   with no database, so the tests stay useful rather than universally red.
3. **Install the json/jsonb codecs in the fixture** exactly as `src/db.py` does
   at runtime. Skipping them made every committed API test unable to pass
   against a real PG — the fixture has to mirror production connection setup,
   or you are testing a different database than you ship.

For the agent-capability handlers, test them as plain functions over the `db`
fixture (`libi/tests/test_agent_pg.py`). You do not need to mint a real
`user_context` JWT to test the handler body — inject the claims object your
`Depends(auth_claims)` would have produced, and cover JWT verification once,
separately.

A second connection into the same schema (`db2` in `libi`, depending on `db`)
is what you want for concurrency tests — double-submit, first-run races,
parallel edits.

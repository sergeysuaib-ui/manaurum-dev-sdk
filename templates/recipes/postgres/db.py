"""Postgres for a v2 app: one asyncpg pool, pinned to the app's own schema.

Copy into `src/db.py` of an app that uses the default, managed data mode (no
`data` block in manifest.json, or one with only `extensions`). The platform
provisions a schema and a login role per (app, tenant) and injects:

    DATABASE_URL             the role's DSN
    MANAURUM_TARGET_SCHEMA   app_<slug>__<tenant_hex>

WHY search_path IS A CONNECTION PARAMETER AND NOT A `SET`

asyncpg runs `RESET ALL` on every connection it takes back into the pool.
Anything set with `SET` - in `init=`, in a startup query, anywhere - is gone
after the first release, and the session falls back to the ROLE's default. A
pool that does `SET search_path` in `init=` therefore answers the first request
on a fresh connection and fails the next one with
`relation "..." does not exist`.

In the cloud the bug hides: the platform gives the app's role a default
search_path of the app's own schema, so the reset lands back on the right
value. On a plain local Postgres the role's default is `"$user", public`, so it
fires exactly where you run the app yourself - which reads as "the platform is
broken" rather than "the template is". It shipped in a template several apps
were copied from.

A value in `server_settings` travels in the connection's startup packet, and
Postgres keeps it as that session's own default: `RESET ALL` restores it
instead of removing it. No round trip on every acquire, nothing to forget.
(`setup=`, which runs a `SET` on every acquire, also works - and costs a round
trip per request.)

The value is the one the platform puts on the role - the schema, one
`ext_<name>` schema per extension in `data.extensions`, then `pg_temp` - so a
table name resolves the same way on your machine as in production. `public`
is not on it in production, so it is not on it here either.

`tests/test_postgres_recipes.py` beside this file proves both halves against a
real Postgres: the `init=` version fails on the second acquire, this one
does not.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncIterator

import asyncpg

# Mirror `data.extensions` from manifest.json - ("vector",), ("pg_trgm",).
# The platform installs each granted extension in a schema of its own, and the
# search_path below REPLACES the role's default, so an extension missing here
# is `type "vector" does not exist` at run time. Postgres skips a schema that
# does not exist, so the same tuple is harmless on a local database.
EXTENSIONS: tuple[str, ...] = ()

_pool: asyncpg.Pool | None = None
_lock = asyncio.Lock()


def quote_ident(name: str) -> str:
    return '"%s"' % name.replace('"', '""')


def search_path(schema: str) -> str:
    """The platform's own value for this role, as one string."""
    parts = [schema] + ["ext_" + name for name in EXTENSIONS]
    return ", ".join(quote_ident(part) for part in parts) + ", pg_temp"


async def configure_connection(conn: asyncpg.Connection) -> None:
    """Per-connection setup that is NOT server session state.

    Type codecs live in the asyncpg connection object, not in the server
    session, so `RESET ALL` does not touch them and `init=` is the right place
    for them. Anything that IS a server setting goes in `server_settings`.
    Public so a test fixture can apply exactly what production applies.
    """
    for typ in ("jsonb", "json"):
        await conn.set_type_codec(
            typ, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


def pool_options(schema: str) -> dict:
    """Everything `create_pool` needs apart from the DSN - shared with tests."""
    return {
        "min_size": 1,
        "max_size": 5,
        "command_timeout": 30,
        "server_settings": {
            "search_path": search_path(schema),   # survives RESET ALL
            "statement_timeout": "30s",
        },
        "init": configure_connection,
    }


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            "%s is not set. It is injected only in the managed data mode - "
            "`\"data\": {\"none\": true}` in manifest.json means no database." % name)
    return value


async def get_pool() -> asyncpg.Pool:
    """The pool, created on first use.

    Deferred on purpose: a missing env var must not crash the app at import,
    so `/healthz` and the static files stay up and only the routes that touch
    the database fail - with a message that names the cause.
    """
    global _pool
    if _pool is None:
        async with _lock:
            if _pool is None:
                schema = _env("MANAURUM_TARGET_SCHEMA")
                _pool = await asyncpg.create_pool(
                    dsn=_env("DATABASE_URL"), **pool_options(schema))
    return _pool


async def close_pool() -> None:
    """Call from the app's shutdown hook."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_db() -> AsyncIterator[asyncpg.Connection]:
    """FastAPI dependency: `db: asyncpg.Connection = Depends(get_db)`."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn

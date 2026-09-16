"""The Postgres recipes against a real Postgres - including the bug they fix.

    MANAURUM_TEST_PG_DSN=postgresql://postgres:postgres@localhost:5432/postgres \
        pytest templates/recipes/postgres

Without the DSN every database test here SKIPS, so the file is safe to copy
into an app whose CI has no database. With `MANAURUM_TEST_PG_REQUIRED=1` a
missing DSN is an error instead - that is how this repository's CI runs it,
because a suite that silently skips proves nothing.

Copying into an app: `from src import db, search` instead of the path tweak
below, and keep `apply_migrations` - applying every file in order is what keeps
the test schema identical to what the deploy builds.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import db  # noqa: E402
import search  # noqa: E402

DSN = os.environ.get("MANAURUM_TEST_PG_DSN", "").strip()
MIGRATIONS = sorted((HERE / "migrations").glob("*.sql"))

if not DSN and os.environ.get("MANAURUM_TEST_PG_REQUIRED"):
    raise RuntimeError("MANAURUM_TEST_PG_REQUIRED is set but MANAURUM_TEST_PG_DSN is not")


async def apply_migrations(conn: asyncpg.Connection, schema: str) -> None:
    """What the deploy does, per file: search_path on the schema, then the SQL.

    One `execute` per file. A file holding a single CONCURRENTLY statement
    runs outside a transaction block that way, exactly as the platform runs
    it; a file that mixed it with anything else would fail here as it fails
    there.
    """
    await conn.execute("SET search_path TO %s, public" % db.quote_ident(schema))
    for path in MIGRATIONS:
        await conn.execute(path.read_text(encoding="utf-8"))
    await conn.execute("RESET search_path")


@pytest.fixture
async def schema(monkeypatch):
    """A throwaway schema, migrated, and the env the platform would inject."""
    if not DSN:
        pytest.skip("MANAURUM_TEST_PG_DSN not set")
    name = "recipe_" + uuid.uuid4().hex[:12]
    admin = await asyncpg.connect(DSN)
    try:
        await admin.execute("CREATE SCHEMA %s" % db.quote_ident(name))
        await apply_migrations(admin, name)
        monkeypatch.setenv("DATABASE_URL", DSN)
        monkeypatch.setenv("MANAURUM_TARGET_SCHEMA", name)
        yield name
    finally:
        await db.close_pool()
        await admin.execute("DROP SCHEMA IF EXISTS %s CASCADE" % db.quote_ident(name))
        await admin.close()


async def role_default_has(schema: str) -> bool:
    """Whether the connecting role would land on the schema by itself.

    In production it would - the platform sets it on the role - and then the
    `init=` bug cannot be seen. A local superuser has `"$user", public`.
    """
    conn = await asyncpg.connect(DSN)
    try:
        return schema in (await conn.fetchval("SHOW search_path"))
    finally:
        await conn.close()


# ── The bug ─────────────────────────────────────────────────────────────────


async def test_set_search_path_in_init_is_lost_after_the_first_release(schema):
    """The template that shipped. Kept as a test so the lesson cannot rot:
    if asyncpg ever stops resetting sessions, this goes red and the
    paragraph in db.py has to change with it."""
    if await role_default_has(schema):
        pytest.skip("this role's own default already points at the schema")

    async def set_path(conn):
        await conn.execute("SET search_path TO %s, public" % db.quote_ident(schema))

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=1, init=set_path)
    try:
        async with pool.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM documents") == 0
        async with pool.acquire() as conn:       # same connection, after RESET ALL
            with pytest.raises(asyncpg.UndefinedTableError):
                await conn.fetchval("SELECT count(*) FROM documents")
    finally:
        await pool.close()


async def test_server_settings_survive_every_release(schema):
    pool = await db.get_pool()
    for _ in range(3):
        async with pool.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM documents") == 0
            assert await conn.fetchval("SHOW search_path") == db.search_path(schema)
            assert await conn.fetchval("SHOW statement_timeout") == "30s"


async def test_codecs_from_init_survive_too(schema):
    pool = await db.get_pool()
    for _ in range(2):
        async with pool.acquire() as conn:
            assert await conn.fetchval("SELECT $1::jsonb", {"a": [1, 2]}) == {"a": [1, 2]}


async def test_the_platform_value_resolves_without_public(schema):
    # `public` is not on the path in production. Nothing the app needs lives
    # there: gen_random_uuid() and the text search configurations are in
    # pg_catalog, which Postgres always searches.
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT gen_random_uuid() IS NOT NULL")
        assert await conn.fetchval("SELECT to_tsvector('russian', 'клиенты') <> ''::tsvector")


# ── Search ──────────────────────────────────────────────────────────────────

DOCS = [
    ("Почему клиенты уходят", "Отток после первого месяца: три причины и одна поправимая.",
     ["продажи"]),
    ("Как считать маржу", "Маржа по заказу и по клиенту - разные числа.", ["финансы"]),
    ("Первый месяц работы с клиентом", "Что должно случиться в первые тридцать дней.",
     ["продажи", "онбординг"]),
    # ts_headline drops what its parser takes for a whole tag, and passes a
    # fragment like this one straight through - measured on Postgres 16.
    ("Опасный текст", "Маржа, и сразу за ней <img src=x onerror=alert(1)> в тексте.", ["тест"]),
]


@pytest.fixture
async def conn(schema):
    pool = await db.get_pool()
    async with pool.acquire() as connection:
        await connection.executemany(
            "INSERT INTO documents (title, body, tags) VALUES ($1, $2, $3)", DOCS)
        yield connection


async def test_generated_column_is_filled(conn):
    assert await conn.fetchval("SELECT count(*) FROM documents WHERE search IS NULL") == 0


async def test_the_index_exists_and_is_valid(conn):
    valid = await conn.fetchval(
        "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE c.relname = 'documents_search_idx' AND n.nspname = current_schema()")
    assert valid is True


async def test_strict_finds_by_stem(conn):
    result = await search.search(conn, "клиент уходит")
    assert result["mode"] == "strict"
    assert [item["title"] for item in result["items"]] == ["Почему клиенты уходят"]


async def test_a_question_falls_back_to_relaxed_instead_of_zero(conn):
    # No document has every one of these words, and a person asks like this.
    result = await search.search(conn, "почему клиенты уходят после первого месяца подписки")
    assert result["mode"] == "relaxed"
    titles = [item["title"] for item in result["items"]]
    assert titles[0] == "Почему клиенты уходят"          # most words, and in the title
    assert "Первый месяц работы с клиентом" in titles


async def test_relaxed_paging_answers_the_same_question(conn):
    first = await search.search(conn, "клиенты маржа тридцать", limit=1)
    assert first["mode"] == "relaxed"
    second = await search.search(conn, "клиенты маржа тридцать", limit=1, offset=1,
                                 relaxed=True)
    assert second["mode"] == "relaxed"
    assert second["items"] and second["items"][0]["id"] != first["items"][0]["id"]


async def test_nothing_is_none_not_an_error(conn):
    assert (await search.search(conn, "синхрофазотрон"))["mode"] == "none"
    assert (await search.search(conn, "   "))["mode"] == "none"
    # Operators that would make to_tsquery raise are just text here.
    assert (await search.search(conn, "маржа & | ! : (("))["mode"] in ("strict", "relaxed")


async def test_tags_are_searchable(conn):
    result = await search.search(conn, "онбординг")
    assert [item["title"] for item in result["items"]] == ["Первый месяц работы с клиентом"]


async def test_the_snippet_is_escaped_before_it_is_marked(conn):
    result = await search.search(conn, "маржа")
    danger = next(i for i in result["items"] if i["title"] == "Опасный текст")
    assert "<img" not in danger["snippet_html"]
    assert "&lt;img src=x onerror=alert" in danger["snippet_html"]
    assert danger["snippet_html"].startswith("<mark>Маржа</mark>")


def test_relaxed_query_shape():
    assert search.relaxed_query("почему -клиенты уходят") == "почему or клиенты or уходят"
    assert search.relaxed_query("a or b") == "a or b"
    assert search.relaxed_query("   ") == ""

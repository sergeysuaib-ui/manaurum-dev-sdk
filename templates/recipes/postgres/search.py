"""Full-text search over one table, with a fallback that does not return zero.

Copy into `src/search.py`. It pairs with `migrations/0002_documents_search.sql`
and `migrations/0003_documents_search_index.sql` beside this file; rename
`documents`, `title`, `body` to your own.

WHY THERE ARE TWO QUERIES

The obvious query - `search @@ websearch_to_tsquery('russian', $1)` - joins the
words with AND. That is right for "invoice march" and wrong for how people ask:
"why do clients leave after the first month" needs every content word in ONE
document, finds nothing, and the app looks broken on day two. So:

1. strict  - `websearch_to_tsquery` as typed: quotes, `-word` and `or` work;
2. relaxed - only when strict found nothing: the same words joined with `or`,
   ranked so that a document matching more of them comes first.

The response says which one answered (`mode`), so the screen can say it too:
"No post has all of these words - these have some of them." A relaxed result
presented as an exact one is how a search loses the person's trust.

`websearch_to_tsquery` never raises on odd input, which is why user text goes
into it; `to_tsquery` raises on a stray `&` or `:`.

WHY THE SNIPPET IS ESCAPED HERE

`ts_headline` returns the document's own text with markers around the hits.
That text came from people, and ts_headline is not a sanitiser: it drops what
its parser takes for a complete tag, and passes a fragment such as
`<img src=x onerror=alert` straight through (measured, Postgres 16). Put its
output into `innerHTML` as it comes and the search box is an XSS hole. So the
markers are control characters no text contains, the snippet is HTML-escaped
first, and only then do the markers become `<mark>`. The browser gets
`snippet_html` that is safe to insert.

`ts_headline` is slow - it re-parses each document - so it runs only over the
page being returned, never over every match.
"""
from __future__ import annotations

import html
import re

import asyncpg

# Built into Postgres (so is 'english'; 'simple' does no stemming at all). It
# must match the configuration the generated column was built with, or the
# words in the query are stemmed differently from the words in the index.
CONFIG = "russian"

_START, _STOP = "\x02", "\x03"
_HEADLINE = ("StartSel=%s, StopSel=%s, MaxFragments=2, MaxWords=28, MinWords=10, "
             'FragmentDelimiter=" ... "' % (_START, _STOP))
_WORD = re.compile(r"\w[\w'-]*")

# The CTE ranks and pages first; ts_headline then runs on at most `limit` rows.
_QUERY = """
WITH q AS (SELECT websearch_to_tsquery($1::regconfig, $2) AS query),
page AS (
    SELECT d.id, d.title, d.body, d.created_at,
           ts_rank_cd(d.search, q.query) AS rank
      FROM documents d, q
     WHERE d.search @@ q.query
     ORDER BY rank DESC, d.created_at DESC, d.id
     LIMIT $3 OFFSET $4
)
SELECT p.id, p.title, p.created_at, p.rank,
       ts_headline($1::regconfig, p.body, q.query, $5) AS snippet
  FROM page p, q
 ORDER BY p.rank DESC, p.created_at DESC, p.id
"""


def relaxed_query(text: str) -> str:
    """'why do clients leave' -> 'why or do or clients or leave'.

    `or` is websearch syntax, so this stays inside the function that never
    raises. A leading `-` is dropped on purpose: in the relaxed pass an
    exclusion would exclude from a result the person did not ask for.
    """
    words = [w for w in _WORD.findall(text) if w.lower() not in ("or", "and")]
    return " or ".join(words)


def snippet_html(raw: str | None) -> str:
    """Escape first, then turn the markers into <mark>. Never the other way."""
    escaped = html.escape(raw or "", quote=False)
    return escaped.replace(_START, "<mark>").replace(_STOP, "</mark>")


async def search(conn: asyncpg.Connection, text: str, *, limit: int = 20,
                 offset: int = 0, relaxed: bool = False) -> dict:
    """One page of results.

    `mode` is "strict", "relaxed" or "none". A client paging through a relaxed
    result passes `relaxed=True` for the next page, so page two answers the
    same question page one did.
    """
    text = (text or "").strip()
    if not text:
        return {"mode": "none", "items": []}

    query, mode = (relaxed_query(text), "relaxed") if relaxed else (text, "strict")
    rows = await conn.fetch(_QUERY, CONFIG, query, limit, offset, _HEADLINE)

    if not rows and not relaxed and offset == 0:
        loose = relaxed_query(text)
        if loose and loose != text:
            rows = await conn.fetch(_QUERY, CONFIG, loose, limit, 0, _HEADLINE)
            mode = "relaxed"

    return {
        "mode": mode if rows else "none",
        "items": [
            {
                "id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"].isoformat(),
                "snippet_html": snippet_html(row["snippet"]),
            }
            for row in rows
        ],
    }

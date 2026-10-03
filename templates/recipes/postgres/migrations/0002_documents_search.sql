-- Search, added to a table an earlier migration created.
--
-- A generated column may only use IMMUTABLE functions, and two ordinary ones
-- are not:
--
--   array_to_string()  is STABLE (for some element types its output depends
--                      on settings), so it cannot index `tags` directly.
--                      A one-line SQL wrapper declared IMMUTABLE is the usual
--                      way through, and it is honest for text[]: turning text
--                      into text depends on no setting.
--   to_tsvector(text)  the ONE-argument form reads default_text_search_config
--                      and is STABLE. Always spell the configuration out:
--                      to_tsvector('russian', ...).
--
-- Postgres refuses either with "generation expression is not immutable".
--
-- LANGUAGE sql is spelled out on purpose: the deploy's migration validator
-- refuses a function whose language it cannot read.
CREATE FUNCTION documents_tags_text(tags text[]) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$ SELECT array_to_string(tags, ' ') $$;

-- Weights: A for the title, B for tags, D for the body, so ts_rank_cd puts a
-- title hit above a body hit. Adding a STORED column rewrites the table under
-- a lock, inside the deploy's 30s statement timeout - fine for thousands of
-- rows, worth a thought for millions.
ALTER TABLE documents ADD COLUMN search tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('russian', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('russian', documents_tags_text(tags)), 'B') ||
    setweight(to_tsvector('russian', coalesce(body, '')), 'D')
) STORED;

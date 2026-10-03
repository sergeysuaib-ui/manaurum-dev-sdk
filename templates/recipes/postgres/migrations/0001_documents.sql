-- The table as it was before it had search. 0002 and 0003 add search to it,
-- which is the case worth copying: on a table created in the SAME file, the
-- generated column goes straight into CREATE TABLE and the GIN index is a
-- plain CREATE INDEX in the same file (both additive there).
CREATE TABLE documents (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title       text        NOT NULL,
    body        text        NOT NULL DEFAULT '',
    tags        text[]      NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX documents_created_at_idx ON documents (created_at DESC);

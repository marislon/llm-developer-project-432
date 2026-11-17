ALTER TABLE fragments
    ADD COLUMN embedding vector(768),
    ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector('simple', text)
        ) STORED;

CREATE INDEX fragments_embedding_hnsw_idx
    ON fragments
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX fragments_search_vector_gin_idx
    ON fragments
    USING gin (search_vector);

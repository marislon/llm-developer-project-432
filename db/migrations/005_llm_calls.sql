CREATE TABLE IF NOT EXISTS llm_calls (
    id              BIGSERIAL PRIMARY KEY,
    job_id          TEXT REFERENCES jobs(id),
    model           TEXT NOT NULL,
    input_tokens    INTEGER NOT NULL CHECK (input_tokens >= 0),
    output_tokens   INTEGER NOT NULL CHECK (output_tokens >= 0),
    cost            NUMERIC(18, 10) NOT NULL CHECK (cost >= 0),
    duration_ms     INTEGER NOT NULL CHECK (duration_ms >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_job_id
    ON llm_calls(job_id);


ALTER TABLE fragments
    ALTER COLUMN page SET NOT NULL,
    ALTER COLUMN section SET DEFAULT '',
    ALTER COLUMN section SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fragments_document_id_ord_key'
          AND conrelid = 'fragments'::regclass
    ) THEN
        ALTER TABLE fragments
            ADD CONSTRAINT fragments_document_id_ord_key
            UNIQUE (document_id, ord);
    END IF;
END
$$;

import psycopg

def get_document_by_hash(
    conn: psycopg.Connection,
    sha256: str,
) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM documents WHERE sha256 = %s",
            (sha256,),
        )
        row = cur.fetchone()

    return row[0] if row else None

def create_document(
    conn: psycopg.Connection,
    document_id: str,
    filename: str,
    ext: str,
    size_bytes: int,
    sha256: str,
    storage_path: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (
                id, filename, ext, size_bytes,
                sha256, storage_path
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                document_id,
                filename,
                ext,
                size_bytes,
                sha256,
                storage_path,
            ),
        )

def get_document(
    conn: psycopg.Connection,
    document_id: str,
) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, filename, status, error
            FROM documents
            WHERE id = %s
            """,
            (document_id,),
        )
        row = cur.fetchone()

    if row is None:
        return None

    return {
        "document_id": row[0],
        "filename": row[1],
        "status": row[2],
        "error": row[3],
    }

def count_fragments(
    conn: psycopg.Connection,
    document_id: str,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM fragments
            WHERE document_id = %s
            """,
            (document_id,),
        )
        row = cur.fetchone()

    return row[0]

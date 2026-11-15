
import psycopg


def create_fragment(
    conn: psycopg.Connection,
    fragment_id: str,
    document_id: str,
    ord: int,
    page: int,
    section: str,
    text: str,
    article: str | None = None,
    brand: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO fragments (
                id, document_id, ord, page,
                section, article, brand, text
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                fragment_id,
                document_id,
                ord,
                page,
                section,
                article,
                brand,
                text,
            ),
        )

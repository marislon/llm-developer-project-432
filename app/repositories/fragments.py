from dataclasses import dataclass

import psycopg

from app.core.config import settings


@dataclass(frozen=True)
class SearchFilters:
    document_id: str | None = None
    page: int | None = None
    section: str | None = None
    article: str | None = None
    brand: str | None = None
    document_ids: list[str] | None = None

def build_filter_conditions(
    filters: SearchFilters | None,
) -> tuple[str, list]:
    if filters is None:
        return "", []

    conditions = []
    params = []

    for field in ("document_id", "page", "section", "article", "brand"):
        value = getattr(filters, field)

        if value is not None:
            conditions.append(f"AND {field} = %s")
            params.append(value)
    if filters.document_ids is not None:
        conditions.append("AND document_id = ANY(%s)")
        params.append(filters.document_ids)
    return " ".join(conditions), params

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
def update_embeddings(
    conn: psycopg.Connection,
    embeddings: list[tuple[str, list[float]]],
) -> None:
    if not embeddings:
        return

    with conn.cursor() as cur:
        cur.executemany(
            """
            UPDATE fragments
            SET embedding = %s::vector
            WHERE id = %s
            """,
            [
                (str(vector), fragment_id)
                for fragment_id, vector in embeddings
            ],
        )

def search_by_vector(
    conn: psycopg.Connection,
    query_embedding: list[float],
    limit: int = 10,
    similarity_threshold: float | None = None,
    filters: SearchFilters | None = None,
) -> list[dict]:
    if similarity_threshold is None:
        similarity_threshold = settings.search_similarity_threshold

    filter_sql, filter_params = build_filter_conditions(filters)

    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            f"""
            SELECT
                id,
                document_id,
                ord,
                page,
                section,
                article,
                brand,
                text,
                1 - (embedding <=> %s::vector) AS score
            FROM fragments
            WHERE embedding IS NOT NULL
                AND 1 - (embedding <=> %s::vector) >= %s
                {filter_sql}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (
                str(query_embedding),
                str(query_embedding),
                similarity_threshold,
                *filter_params,
                str(query_embedding),
                limit,
            ),
        )

        return cur.fetchall()

def search_by_text(
    conn: psycopg.Connection,
    query: str,
    limit: int = 10,
    filters: SearchFilters | None = None,
) -> list[dict]:
    filter_sql, filter_params = build_filter_conditions(filters)

    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            f"""
            SELECT
                id,
                document_id,
                ord,
                page,
                section,
                article,
                brand,
                text,
                ts_rank(
                    search_vector,
                    plainto_tsquery('simple', %s)
                ) AS score
            FROM fragments
            WHERE search_vector @@ plainto_tsquery('simple', %s)
                {filter_sql}
            ORDER BY score DESC, id
            LIMIT %s
            """,
            (query, query, *filter_params, limit),
        )

        return cur.fetchall()

def search_hybrid(
    conn: psycopg.Connection,
    query: str,
    query_embedding: list[float],
    limit: int = 10,
    rrf_k: int = 60,
    similarity_threshold: float | None = None,
    filters: SearchFilters | None = None,
) -> list[dict]:
    if similarity_threshold is None:
        similarity_threshold = settings.search_similarity_threshold

    filter_sql, filter_params = build_filter_conditions(filters)

    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            f"""
            WITH vector_results AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        ORDER BY embedding <=> %s::vector
                    ) AS rank
                FROM fragments
                WHERE embedding IS NOT NULL
                    AND 1 - (embedding <=> %s::vector) >= %s
                    {filter_sql}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            ),
            text_results AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        ORDER BY ts_rank(
                            search_vector,
                            plainto_tsquery('simple', %s)
                        ) DESC, id
                    ) AS rank
                FROM fragments
                WHERE search_vector @@ plainto_tsquery('simple', %s)
                    {filter_sql}
                ORDER BY rank
                LIMIT %s
            ),
            fused AS (
                SELECT
                    COALESCE(v.id, t.id) AS id,
                    COALESCE(1.0 / (%s + v.rank), 0)
                    + COALESCE(1.0 / (%s + t.rank), 0) AS score
                FROM vector_results v
                FULL OUTER JOIN text_results t ON v.id = t.id
            )
            SELECT
                f.id,
                f.document_id,
                f.ord,
                f.page,
                f.section,
                f.article,
                f.brand,
                f.text,
                fused.score
            FROM fused
            JOIN fragments f ON f.id = fused.id
            ORDER BY fused.score DESC, f.id
            LIMIT %s
            """,
            (
                str(query_embedding),
                str(query_embedding),
                similarity_threshold,
                *filter_params,
                str(query_embedding),
                limit,
                query,
                query,
                *filter_params,
                limit,
                rrf_k,
                rrf_k,
                limit,
            ),
        )

        return cur.fetchall()

def get_fragments_without_embeddings(
    conn: psycopg.Connection,
    limit: int = 32,
) -> list[dict]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT id, text
            FROM fragments
            WHERE embedding IS NULL
            ORDER BY id
            LIMIT %s
            """,
            (limit,),
        )

        return cur.fetchall()

def get_document_fragments_without_embeddings(
    conn: psycopg.Connection,
    document_id: str,
    limit: int = 32,
) -> list[dict]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT id, text
            FROM fragments
            WHERE document_id = %s
                AND embedding IS NULL
            ORDER BY ord
            LIMIT %s
            """,
            (document_id, limit),
        )

        return cur.fetchall()

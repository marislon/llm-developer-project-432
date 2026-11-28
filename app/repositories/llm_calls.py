"""Repository-слой: таблица llm_calls в Postgres."""

from decimal import Decimal

import psycopg

from app.core.db import connection


def create_llm_call(
    conn: psycopg.Connection,
    *,
    job_id: str | None,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: Decimal,
    duration_ms: int,
) -> None:
    """Сохраняет информацию о вызове модели."""

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO llm_calls (
                job_id,
                model,
                input_tokens,
                output_tokens,
                cost,
                duration_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                job_id,
                model,
                input_tokens,
                output_tokens,
                cost,
                duration_ms,
            ),
        )


def record_llm_call(
    *,
    job_id: str | None,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: Decimal,
    duration_ms: int,
) -> None:
    """Записывает вызов модели через пул соединений."""

    with connection() as conn:
        create_llm_call(
            conn,
            job_id=job_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            duration_ms=duration_ms,
        )

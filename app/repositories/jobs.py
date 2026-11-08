"""Repository-слой: таблица jobs в Postgres.

Единственный владелец SQL. Статусная машина:
pending → extracting → generating → critiquing → (regenerating) → approved | rejected | failed
"""
import json
import uuid
from datetime import UTC, datetime

import psycopg

from app.core.db import connection
from app.schemas import CardDraft


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_job(
    conn: psycopg.Connection,
    payload: dict,
    idempotency_key: str | None,
) -> tuple[str, bool]:
    """Создаёт задачу или возвращает ID существующей."""

    with conn.cursor() as cur:
        if idempotency_key:
            cur.execute(
                "SELECT id, payload FROM jobs WHERE idempotency_key = %s",
                (idempotency_key,),
            )
            row = cur.fetchone()

            if row:
                existing_id, existing_payload = row

                if existing_payload != payload:
                    raise ValueError(
                        "Idempotency-Key уже используется с другими данными"
                    )

                return existing_id, False

        job_id = uuid.uuid4().hex[:12]

        cur.execute(
            "INSERT INTO jobs (id, idempotency_key, payload) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (idempotency_key) DO NOTHING "
            "RETURNING id",
            (job_id, idempotency_key, json.dumps(payload)),
        )

        inserted = cur.fetchone()

        if inserted is not None:
            return inserted[0], True

        cur.execute(
            "SELECT id, payload FROM jobs WHERE idempotency_key = %s",
            (idempotency_key,),
        )
        row = cur.fetchone()

        if row is None:
            raise RuntimeError("Не удалось найти задание после конфликта ключа")

        existing_id, existing_payload = row

        if existing_payload != payload:
            raise ValueError(
                "Idempotency-Key уже используется с другими данными"
            )

        return existing_id, False

def set_status(
    conn: psycopg.Connection,
    job_id: str,
    status: str,
    *,
    result: CardDraft | None = None,
    error: str | None = None,
    bump_attempts: bool = False,
) -> None:
    sets = ["status = %s", "updated_at = %s"]
    args: list = [status, _now()]

    if result is not None:
        sets.append("result = %s")
        args.append(result.model_dump_json())

    if error is not None:
        sets.append("error = %s")
        args.append(error)

    if bump_attempts:
        sets.append("attempts = attempts + 1")

    args.append(job_id)

    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE jobs SET {', '.join(sets)} WHERE id = %s",
            args,
        )



def get_job(conn: psycopg.Connection, job_id: str) -> dict | None:
    """Возвращает информацию о задании по его ID."""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, status, attempts, result, error,
                   created_at, updated_at
            FROM jobs
            WHERE id = %s
            """,
            (job_id,),
        )
        row = cur.fetchone()

    if row is None:
        return None

    draft = None
    if row[3] is not None:
        draft = (
            CardDraft.model_validate(row[3])
            if isinstance(row[3], dict)
            else CardDraft.model_validate_json(row[3])
        )

    return {
        "id": row[0],
        "status": row[1],
        "attempts": row[2],
        "result": draft,
        "error": row[4],
        "created_at": row[5],
        "updated_at": row[6],
    }

def get_job_by_id(job_id: str) -> dict | None:
    with connection() as conn:
        return get_job(conn, job_id)

def create_job_with_connection(
    payload: dict,
    idempotency_key: str | None,
) -> tuple[str, bool]:
    with connection() as conn:
        return create_job(conn, payload, idempotency_key)

def update_job_status(
    job_id: str,
    status: str,
    *,
    result: CardDraft | None = None,
    error: str | None = None,
) -> None:
    with connection() as conn:
        set_status(
            conn,
            job_id,
            status,
            result=result,
            error=error,
        )

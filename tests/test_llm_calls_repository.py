import uuid
from decimal import Decimal

import psycopg

from app.core.config import settings
from app.repositories.llm_calls import create_llm_call


def test_create_llm_call():
    job_id = uuid.uuid4().hex[:12]

    with psycopg.connect(settings.database_url) as conn:
        try:
            conn.execute(
                """
                INSERT INTO jobs (id, payload)
                VALUES (%s, %s)
                """,
                (job_id, "{}"),
            )

            create_llm_call(
                conn=conn,
                job_id=job_id,
                model="test-model",
                input_tokens=1000,
                output_tokens=500,
                cost=Decimal("0.0025"),
                duration_ms=1500,
            )

            row = conn.execute(
                """
                SELECT job_id, model, input_tokens,
                       output_tokens, cost, duration_ms
                FROM llm_calls
                WHERE job_id = %s
                """,
                (job_id,),
            ).fetchone()

            assert row == (
                job_id,
                "test-model",
                1000,
                500,
                Decimal("0.0025"),
                1500,
            )

        finally:
            conn.rollback()

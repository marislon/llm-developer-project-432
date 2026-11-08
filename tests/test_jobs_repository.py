import pytest

from app.core.db import pool


@pytest.fixture(scope="module")
def db_pool():
    p = pool()
    p.open()
    p.wait()
    try:
        yield p
    finally:
        p.close()

def test_create_job(db_pool):
    from app.repositories.jobs import (
        create_job_with_connection,
        get_job_by_id,
    )

    job_id, created = create_job_with_connection(
        {"supplier_text": "Тестовый товар"},
        None,
    )

    try:
        assert created is True

        job = get_job_by_id(job_id)

        assert job is not None
        assert job["id"] == job_id
        assert job["status"] == "pending"
        assert job["attempts"] == 0
    finally:
        with db_pool.connection() as conn:
            conn.execute(
                "DELETE FROM jobs WHERE id = %s",
                (job_id,),
            )

def test_update_job_status(db_pool):
    from app.repositories.jobs import (
        create_job_with_connection,
        get_job_by_id,
        update_job_status,
    )

    job_id, _ = create_job_with_connection(
        {"supplier_text": "Тест обновления статуса"},
        None,
    )

    try:
        update_job_status(job_id, "extracting")

        job = get_job_by_id(job_id)

        assert job is not None
        assert job["status"] == "extracting"
    finally:
        with db_pool.connection() as conn:
            conn.execute(
                "DELETE FROM jobs WHERE id = %s",
                (job_id,),
            )

def test_job_idempotency(db_pool):
    from uuid import uuid4

    from app.repositories.jobs import create_job_with_connection

    key = f"test-{uuid4().hex}"
    payload = {"supplier_text": "Тест идемпотентности"}

    job_id, created = create_job_with_connection(payload, key)

    try:
        repeated_id, repeated_created = create_job_with_connection(
            payload, key
        )

        assert created is True
        assert repeated_created is False
        assert repeated_id == job_id
    finally:
        with db_pool.connection() as conn:
            conn.execute(
                "DELETE FROM jobs WHERE id = %s",
                (job_id,),
            )

def test_job_idempotency_conflict(db_pool):
    from uuid import uuid4

    from app.repositories.jobs import create_job_with_connection

    key = f"test-{uuid4().hex}"

    job_id, _ = create_job_with_connection(
        {"supplier_text": "Первый товар"},
        key,
    )

    try:
        with pytest.raises(
            ValueError,
            match="Idempotency-Key уже используется",
        ):
            create_job_with_connection(
                {"supplier_text": "Другой товар"},
                key,
            )
    finally:
        with db_pool.connection() as conn:
            conn.execute(
                "DELETE FROM jobs WHERE id = %s",
                (job_id,),
            )

def test_concurrent_job_idempotency(db_pool):
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4

    from app.repositories.jobs import create_job_with_connection

    key = f"test-concurrent-{uuid4().hex}"
    payload = {"supplier_text": "Конкурентный тест"}

    def create():
        return create_job_with_connection(payload, key)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: create(), range(2)))

        assert results[0][0] == results[1][0]
        assert sorted(created for _, created in results) == [False, True]
    finally:
        with db_pool.connection() as conn:
            conn.execute(
                "DELETE FROM jobs WHERE idempotency_key = %s",
                (key,),
            )

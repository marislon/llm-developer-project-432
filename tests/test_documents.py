import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.repositories.documents import update_document_status


@pytest.fixture
def client(db_pool):
    with TestClient(app) as test_client:
        yield test_client

def test_concurrent_document_upload(client, db_pool):
    content = f"Тестовый документ {uuid4()}".encode()
    sha256 = hashlib.sha256(content).hexdigest()
    filename = "concurrent_test.pdf"

    def upload():
        return client.post(
            "/documents",
            files={
                "file": (
                    filename,
                    content,
                    "application/pdf",
                )
            },
        )
    document_id = None
    try:

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: upload(), range(2)))
        results = [response.json() for response in responses]

        document_id = results[0].get("document_id")

        assert all(response.status_code == 202 for response in responses)

        assert results[0]["document_id"] == results[1]["document_id"]

        assert sorted(result["status"] for result in results) == [
            "existing",
            "new",
        ]
    finally:
        with db_pool.connection() as conn:
            row = conn.execute(
                """
                SELECT id, storage_path
                FROM documents
                WHERE sha256 = %s
                """,
                (sha256,),
            ).fetchone()

            if row is not None:
                document_id, storage_path = row

                conn.execute(
                    "DELETE FROM documents WHERE id = %s",
                    (document_id,),
                )

        if row is not None:
            Path(storage_path).unlink(missing_ok=True)


def test_update_document_status(db_pool):
    with psycopg.connect(settings.database_url) as conn:
        document_id = str(uuid4())

        try:
            conn.execute(
                """
                INSERT INTO documents (
                    id, filename, ext, size_bytes,
                    sha256, storage_path
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    document_id,
                    "status_test.pdf",
                    ".pdf",
                    100,
                    uuid4().hex,
                    "test/status_test.pdf",
                ),
            )

            update_document_status(
                conn=conn,
                document_id=document_id,
                status="parsing",
            )

            row = conn.execute(
                """
                SELECT status, error
                FROM documents
                WHERE id = %s
                """,
                (document_id,),
            ).fetchone()

            assert row == ("parsing", None)
        finally:
            conn.rollback()

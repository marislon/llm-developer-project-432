from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from pathlib import Path
import hashlib

@pytest.fixture
def client(db_pool):
    with TestClient(app) as test_client:
        yield test_client

def test_concurrent_document_upload(client, db_pool):
    content = f"Тестовый документ {uuid4()}".encode("utf-8")
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

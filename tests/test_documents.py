import hashlib
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
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
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def test_lifespan(app):
        yield

    app.router.lifespan_context = test_lifespan

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.router.lifespan_context = original_lifespan


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


def test_update_document_status():
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
def test_scanned_pdf_rejected(db_pool):
    from app.services.documents import process_document

    document_id = str(uuid4())
    file_path = Path("data/boiler_scan.pdf")

    assert file_path.exists()

    with db_pool.connection() as conn:
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
                file_path.name,
                ".pdf",
                file_path.stat().st_size,
                uuid4().hex,
                str(file_path),
            ),
        )

    try:
        count = process_document(document_id, str(file_path))

        with db_pool.connection() as conn:
            row = conn.execute(
                """
                SELECT status, error
                FROM documents
                WHERE id = %s
                """,
                (document_id,),
            ).fetchone()

        assert count == 0
        assert row[0] == "rejected"
        assert "не содержит извлекаемого текста" in row[1]

    finally:
        with db_pool.connection() as conn:
            conn.execute(
                "DELETE FROM documents WHERE id = %s",
                (document_id,),
            )

def test_text_pdf_processing(db_pool):
    from app.services.documents import process_document

    document_id = str(uuid4())
    file_path = Path("data/blender_passport.pdf")

    assert file_path.exists()

    with db_pool.connection() as conn:
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
                file_path.name,
                ".pdf",
                file_path.stat().st_size,
                uuid4().hex,
                str(file_path),
            ),
        )

    try:
        count = process_document(document_id, str(file_path))

        with db_pool.connection() as conn:
            row = conn.execute(
                """
                SELECT status, error
                FROM documents
                WHERE id = %s
                """,
                (document_id,),
            ).fetchone()

            fragments = conn.execute(
                """
                SELECT ord, page, text
                FROM fragments
                WHERE document_id = %s
                ORDER BY ord
                """,
                (document_id,),
            ).fetchall()

        assert count > 0
        assert row == ("embedding", None)
        assert len(fragments) == count
        assert [f[0] for f in fragments] == list(range(count))
        assert {f[1] for f in fragments} == {1, 2}
        assert all(f[2].strip() for f in fragments)

    finally:
        with db_pool.connection() as conn:
            conn.execute(
                "DELETE FROM documents WHERE id = %s",
                (document_id,),
            )

def test_xlsx_long_row_not_split(db_pool):
    from tempfile import TemporaryDirectory

    from openpyxl import Workbook

    from app.services.documents import process_document

    document_id = str(uuid4())

    with TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "long_spec.xlsx"

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Спецификация"
        sheet.append(["Артикул", "Описание"])
        sheet.append(["TEST-001", "Длинное описание " * 100])
        workbook.save(file_path)
        workbook.close()

        with db_pool.connection() as conn:
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
                    file_path.name,
                    ".xlsx",
                    file_path.stat().st_size,
                    uuid4().hex,
                    str(file_path),
                ),
            )

        try:
            count = process_document(document_id, str(file_path))

            with db_pool.connection() as conn:
                fragments = conn.execute(
                    """
                    SELECT text
                    FROM fragments
                    WHERE document_id = %s
                    ORDER BY ord
                    """,
                    (document_id,),
                ).fetchall()

            assert count == 1
            assert len(fragments) == 1
            assert "TEST-001" in fragments[0][0]
            assert fragments[0][0].count("Длинное описание") == 100

        finally:
            with db_pool.connection() as conn:
                conn.execute(
                    "DELETE FROM documents WHERE id = %s",
                    (document_id,),
                )
def test_docx_text_and_table_preserved():
    from app.parsers.docx import parse_docx

    file_path = Path("data/blender_kp.docx")
    assert file_path.exists()

    blocks = parse_docx(str(file_path))

    paragraphs = [
        block for block in blocks
        if block.section == "paragraph"
    ]
    table_rows = [
        block for block in blocks
        if block.section == "table"
    ]

    assert len(paragraphs) > 0
    assert len(table_rows) > 0

    assert all(block.text.strip() for block in blocks)
    assert all(block.page == 1 for block in blocks)

    assert all(
        ":" in block.text
        for block in table_rows
    )
    expected_rows = [
        ("BLD-500", "МиксерПро 500", "500 Вт", "белый", "1 490 ₽"),
        ("BLD-800", "МиксерПро 800", "800 Вт", "графитовый", "2 190 ₽"),
        ("BLD-1200", "МиксерПро 1200", "1200 Вт", "чёрный", "3 450 ₽"),
    ]

    assert len(table_rows) == len(expected_rows)

    for block, expected in zip(table_rows, expected_rows):
        for value in expected:
            assert value in block.text

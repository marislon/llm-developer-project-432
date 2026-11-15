
import uuid

import psycopg

from app.core.config import settings
from app.repositories.fragments import create_fragment


def test_create_fragment():
    document_id = str(uuid.uuid4())
    fragment_id = str(uuid.uuid4())

    with psycopg.connect(settings.database_url) as conn:
        conn.execute(
            """
            INSERT INTO documents (
                id, filename, ext, size_bytes, sha256, storage_path, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                document_id,
                "test_fragment.docx",
                ".docx",
                100,
                uuid.uuid4().hex,
                "data/test_fragment.docx",
                "new",
            ),
        )
        try:
            create_fragment(
                conn=conn,
                fragment_id=fragment_id,
                document_id=document_id,
                ord=0,
                page=1,
                section="Технические характеристики",
                text="BL-500: мощность 500 Вт",
                article="BL-500",
                brand="ТехноДом",
            )

            row = conn.execute(
                """
                SELECT document_id, ord, page, section,
                       article, brand, text
                FROM fragments
                WHERE id = %s
                """,
                (fragment_id,),
            ).fetchone()

            assert row == (
                document_id,
                0,
                1,
                "Технические характеристики",
                "BL-500",
                "ТехноДом",
                "BL-500: мощность 500 Вт",
            )
        finally:
            conn.rollback()

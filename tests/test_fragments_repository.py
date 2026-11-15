
import uuid

import psycopg

from app.core.config import settings
from app.repositories.fragments import create_fragment


def test_create_fragment():
    document_id = "7bf89fb4-1d2c-41e2-bdbd-00b25c7c0225"
    fragment_id = str(uuid.uuid4())

    with psycopg.connect(settings.database_url) as conn:
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

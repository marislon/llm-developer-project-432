import psycopg
import structlog

from app.core.config import settings
from app.repositories.fragments import (
    get_fragments_without_embeddings,
    update_embeddings,
)
from app.services.embeddings import embed_documents

logger = structlog.get_logger()


def main() -> None:
    total = 0

    with psycopg.connect(settings.database_url) as conn:
        while True:
            fragments = get_fragments_without_embeddings(
                conn,
                limit=settings.embedding_batch_size,
            )

            if not fragments:
                break

            texts = [fragment["text"] for fragment in fragments]
            vectors = embed_documents(texts)

            embeddings = [
                (fragment["id"], vector)
                for fragment, vector in zip(
                    fragments, vectors, strict=True
                )
            ]

            update_embeddings(conn, embeddings)
            conn.commit()

            total += len(embeddings)

            logger.info(
                "embedding_batch_completed",
                batch_size=len(embeddings),
                total_processed=total,
            )

    logger.info(
        "embedding_backfill_completed",
        total_processed=total,
    )


if __name__ == "__main__":
    main()

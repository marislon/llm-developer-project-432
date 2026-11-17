from app.core.config import settings
from app.core.db import connection
from app.repositories.documents import update_document_status
from app.repositories.fragments import (
    get_document_fragments_without_embeddings,
    update_embeddings,
)
from app.services.embeddings import embed_documents


def index_document(document_id: str) -> int:
    total = 0

    while True:
        with connection() as conn:
            fragments = get_document_fragments_without_embeddings(
                conn,
                document_id,
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

        with connection() as conn:
            update_embeddings(conn, embeddings)

        total += len(embeddings)

    with connection() as conn:
        update_document_status(conn, document_id, "indexed")

    return total

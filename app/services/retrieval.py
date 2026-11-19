"""Получение релевантного контекста для RAG-пайплайна."""

from pathlib import Path

import psycopg

from app.repositories.documents import get_document
from app.repositories.fragments import SearchFilters, search_hybrid
from app.services.context_builder import ContextResult, build_context
from app.services.embeddings import embed_query


def build_search_query(
    conn: psycopg.Connection,
    document_ids: list[str],
    product_hint: str | None = None,
) -> str:
    """Сформировать поисковый запрос."""

    if product_hint and product_hint.strip():
        return product_hint.strip()

    titles = []

    for document_id in document_ids:
        document = get_document(conn, document_id)

        if document is None:
            raise ValueError(
                f"Документ не найден: {document_id}"
            )

        title = Path(document["filename"]).stem
        title = title.replace("_", " ").replace("-", " ")
        titles.append(title)

    return " ".join(titles)

def retrieve_context(
    conn: psycopg.Connection,
    document_ids: list[str],
    product_hint: str | None = None,
    limit: int = 10,
    max_chars: int = 6000,
    similarity_threshold: float = 0.25,
) -> ContextResult:
    """Получить релевантный контекст из выбранных документов."""

    query = build_search_query(
        conn,
        document_ids,
        product_hint,
    )

    query_embedding = embed_query(query)

    fragments = search_hybrid(
        conn,
        query=query,
        query_embedding=query_embedding,
        limit=limit,
        similarity_threshold=similarity_threshold,
        filters=SearchFilters(document_ids=document_ids),
    )

    return build_context(
        fragments,
        max_chars=max_chars,
    )

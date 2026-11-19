import uuid

import psycopg
import pytest

from app.core.config import settings
from app.repositories.fragments import (
    SearchFilters,
    create_fragment,
    search_by_vector,
    search_hybrid,
    update_embeddings,
)


@pytest.fixture
def search_document():
    document_id = str(uuid.uuid4())

    with psycopg.connect(settings.database_url) as conn:
        conn.execute(
            """
            INSERT INTO documents (
                id, filename, ext, size_bytes,
                sha256, storage_path, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                document_id,
                "test_search.docx",
                ".docx",
                100,
                uuid.uuid4().hex,
                "data/test_search.docx",
                "indexed",
            ),
        )

        try:
            yield conn, document_id
        finally:
            conn.rollback()

@pytest.fixture
def search_data(search_document):
    conn, document_id = search_document

    fragments = [
        ("semantic", "Высокая мощность двигателя", [1.0, 0.0]),
        ("both", "Электрический чайник. Чайник", [0.8, 0.6]),
        ("lexical", "Чайник из стали", [0.0, 1.0]),
    ]

    ids = {}
    embeddings = []

    for ord, (name, text, vector) in enumerate(fragments):
        fragment_id = str(uuid.uuid4())
        ids[name] = fragment_id

        create_fragment(
            conn=conn,
            fragment_id=fragment_id,
            document_id=document_id,
            ord=ord,
            page=1,
            section="Тестирование поиска",
            text=text,
        )

        full_vector = vector + [0.0] * 766
        embeddings.append((fragment_id, full_vector))

    update_embeddings(conn, embeddings)

    return conn, document_id, ids

def test_hybrid_search_union(search_data):
    conn, document_id, ids = search_data

    query_vector = [1.0, 0.0] + [0.0] * 766

    results = search_hybrid(
        conn,
        query="чайник",
        query_embedding=query_vector,
        similarity_threshold=0.5,
        filters=SearchFilters(document_id=document_id),
    )

    result_ids = {row["id"] for row in results}

    assert len(results) == 3
    assert result_ids == set(ids.values())

def test_hybrid_search_ranking(search_data):
    conn, document_id, ids = search_data

    query_vector = [1.0, 0.0] + [0.0] * 766

    results = search_hybrid(
        conn,
        query="чайник",
        query_embedding=query_vector,
        similarity_threshold=0.5,
        filters=SearchFilters(document_id=document_id),
        rrf_k=60,
    )

    assert results[0]["id"] == ids["both"]

    scores = [float(row["score"]) for row in results]

    assert scores == sorted(scores, reverse=True)

    expected_score = 1 / 62 + 1 / 61

    assert scores[0] == pytest.approx(expected_score)

def test_vector_search_threshold(search_data):
    conn, document_id, ids = search_data

    query_vector = [1.0, 0.0] + [0.0] * 766

    results = search_by_vector(
        conn,
        query_embedding=query_vector,
        similarity_threshold=0.9,
        filters=SearchFilters(document_id=document_id),
    )

    assert len(results) == 1
    assert results[0]["id"] == ids["semantic"]
    assert results[0]["score"] == pytest.approx(1.0)

def test_hybrid_search_multiple_documents(search_data):
    conn, first_document_id, ids = search_data

    document_ids = [first_document_id]
    expected_ids = set(ids.values())
    query_vector = [1.0, 0.0] + [0.0] * 766

    for selected in (True, False):
        document_id = str(uuid.uuid4())
        fragment_id = str(uuid.uuid4())

        conn.execute(
            """
            INSERT INTO documents (
                id, filename, ext, size_bytes,
                sha256, storage_path, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                document_id,
                "test_multiple.docx",
                ".docx",
                100,
                uuid.uuid4().hex,
                "data/test_multiple.docx",
                "indexed",
            ),
        )

        create_fragment(
            conn=conn,
            fragment_id=fragment_id,
            document_id=document_id,
            ord=0,
            page=1,
            section="Характеристики",
            text="Электрический чайник",
        )

        update_embeddings(
            conn,
            [(fragment_id, query_vector)],
        )

        if selected:
            document_ids.append(document_id)
            expected_ids.add(fragment_id)

    results = search_hybrid(
        conn,
        query="чайник",
        query_embedding=query_vector,
        similarity_threshold=0.5,
        filters=SearchFilters(document_ids=document_ids),
    )

    assert len(results) == 4
    assert {row["id"] for row in results} == expected_ids
    assert {row["document_id"] for row in results} == set(document_ids)

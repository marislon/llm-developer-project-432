from unittest.mock import Mock, patch

import pytest

from app.services.retrieval import build_search_query, retrieve_context


def test_query_from_product_hint():
    conn = Mock()

    result = build_search_query(
        conn,
        document_ids=["doc-1"],
        product_hint="  Электрический чайник  ",
    )

    assert result == "Электрический чайник"


def test_query_from_document_titles():
    conn = Mock()

    with patch(
        "app.services.retrieval.get_document"
    ) as mock_get_document:
        mock_get_document.side_effect = [
            {"filename": "blender_kp.docx"},
            {"filename": "blender-passport.pdf"},
        ]

        result = build_search_query(
            conn,
            document_ids=["doc-1", "doc-2"],
        )

    assert result == "blender kp blender passport"


def test_query_missing_document():
    conn = Mock()

    with patch(
        "app.services.retrieval.get_document",
        return_value=None,
    ), pytest.raises(ValueError, match="Документ не найден"):
        build_search_query(conn, ["doc-1"])

def test_retrieve_context():
    conn = Mock()
    document_ids = ["doc-1", "doc-2"]
    query_vector = [1.0] + [0.0] * 767

    fragments = [
        {
            "id": "frag-1",
            "document_id": "doc-1",
            "ord": 0,
            "text": "Мощность чайника 2200 Вт",
        }
    ]

    with (
        patch(
            "app.services.retrieval.embed_query",
            return_value=query_vector,
        ) as mock_embed,
        patch(
            "app.services.retrieval.search_hybrid",
            return_value=fragments,
        ) as mock_search,
    ):
        result = retrieve_context(
            conn,
            document_ids=document_ids,
            product_hint="Чайник",
        )

    mock_embed.assert_called_once_with("Чайник")
    mock_search.assert_called_once()

    kwargs = mock_search.call_args.kwargs

    assert kwargs["query"] == "Чайник"
    assert kwargs["query_embedding"] == query_vector
    assert kwargs["filters"].document_ids == document_ids
    assert kwargs["limit"] == 10
    assert kwargs["similarity_threshold"] == 0.25

    assert result.fragment_ids == ["frag-1"]
    assert "Мощность чайника 2200 Вт" in result.text
    assert result.size == len(result.text)

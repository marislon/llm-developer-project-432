from app.services.context_builder import build_context


def test_build_context_basic():
    fragments = [
        {
            "id": "frag-001",
            "document_id": "doc-001",
            "ord": 0,
            "page": 1,
            "section": "Характеристики",
            "text": "Мощность: 2200 Вт.",
        },
        {
            "id": "frag-002",
            "document_id": "doc-001",
            "ord": 1,
            "page": 1,
            "section": "Характеристики",
            "text": "Объём: 1,7 л.",
        },
    ]

    result = build_context(fragments)

    assert result.fragment_ids == ["frag-001", "frag-002"]

    assert "[fragment_id: frag-001]" in result.text
    assert "[fragment_id: frag-002]" in result.text

    assert "Мощность: 2200 Вт." in result.text
    assert "Объём: 1,7 л." in result.text

    assert result.size == len(result.text)
    assert result.size <= 6000

def test_build_context_removes_duplicates():
    fragment = {
        "id": "frag-001",
        "document_id": "doc-001",
        "ord": 0,
        "text": "Мощность: 2200 Вт.",
    }

    fragments = [
        fragment,
        {
            **fragment,
            "text": "Другой текст.",
        },
        {
            **fragment,
            "id": "frag-002",
            "ord": 1,
            "text": "Мощность:   2200\nВт.",
        },
        {
            **fragment,
            "id": "frag-003",
            "ord": 2,
            "text": "Объём: 1,7 л.",
        },
    ]

    result = build_context(fragments)

    assert result.fragment_ids == ["frag-001", "frag-003"]
    assert result.text.count("Мощность:") == 1
    assert "Другой текст." not in result.text
    assert "Объём: 1,7 л." in result.text

def test_build_context_respects_size_limit():
    fragments = [
        {
            "id": "frag-001",
            "document_id": "doc-001",
            "ord": 0,
            "text": "Мощность: 2200 Вт.",
        },
        {
            "id": "frag-002",
            "document_id": "doc-001",
            "ord": 1,
            "text": "A" * 500,
        },
        {
            "id": "frag-003",
            "document_id": "doc-001",
            "ord": 2,
            "text": "Объём: 1,7 л.",
        },
    ]

    result = build_context(fragments, max_chars=200)

    assert result.fragment_ids == ["frag-001", "frag-003"]
    assert result.size <= 200
    assert result.size == len(result.text)
    assert "[fragment_id: frag-002]" not in result.text
    assert "Мощность: 2200 Вт." in result.text
    assert "Объём: 1,7 л." in result.text

def test_build_context_empty_result():
    fragments = [
        {
            "id": "frag-001",
            "document_id": "doc-001",
            "ord": 0,
            "text": "   \n\t  ",
        },
        {
            "id": "frag-002",
            "document_id": "doc-001",
            "ord": 1,
            "text": "A" * 500,
        },
    ]

    for items in ([], fragments):
        result = build_context(items, max_chars=100)

        assert result.text == ""
        assert result.fragment_ids == []
        assert result.size == 0

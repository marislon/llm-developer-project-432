from unittest.mock import Mock, patch

from app.schemas import SourceReference
from app.services.validation import validate_sources


def test_valid_sources():
    conn = Mock()
    sources = [
        SourceReference(fragment_id="frag_1"),
        SourceReference(fragment_id="frag_2"),
    ]

    with patch(
        "app.services.validation.get_existing_fragment_ids",
        return_value={"frag_1", "frag_2"},
    ):
        errors = validate_sources(
            conn, sources, ["frag_1", "frag_2"]
        )

    assert errors == []


def test_empty_sources():
    errors = validate_sources(Mock(), [], ["frag_1"])

    assert errors == ["Отсутствуют ссылки на источники"]


def test_missing_fragment_id():
    sources = [
        SourceReference(url="https://example.com")
    ]

    with patch(
        "app.services.validation.get_existing_fragment_ids",
        return_value=set(),
    ):
        errors = validate_sources(
            Mock(), sources, ["frag_1"]
        )

    assert errors == [
        "Источник 1: отсутствует fragment_id"
    ]


def test_nonexistent_fragment():
    sources = [
        SourceReference(fragment_id="fake_id")
    ]

    with patch(
        "app.services.validation.get_existing_fragment_ids",
        return_value=set(),
    ):
        errors = validate_sources(
            Mock(), sources, ["frag_1"]
        )

    assert errors == [
        "Фрагмент fake_id не существует в БД"
    ]


def test_fragment_outside_context():
    sources = [
        SourceReference(fragment_id="frag_2")
    ]

    with patch(
        "app.services.validation.get_existing_fragment_ids",
        return_value={"frag_2"},
    ):
        errors = validate_sources(
            Mock(), sources, ["frag_1"]
        )

    assert errors == [
        "Фрагмент frag_2 отсутствует в контексте"
    ]

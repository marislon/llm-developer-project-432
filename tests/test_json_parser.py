import json

import pytest

from app.services.steps import _ensure_json


def test_clean_json():
    source = json.dumps(
        {"title": "Футболка"},
        ensure_ascii=False,
    )

    result = _ensure_json(source)

    assert json.loads(result) == {"title": "Футболка"}

def test_json_in_markdown():
    source = (
        "```json\n"
        '{"title": "Футболка"}'
        "\n```"
    )

    result = _ensure_json(source)

    assert json.loads(result) == {"title": "Футболка"}

def test_json_with_surrounding_text():
    source = (
        "Вот карточка товара:\n"
        '{"title": "Футболка"}'
        "\nКарточка готова."
    )

    result = _ensure_json(source)

    assert json.loads(result) == {"title": "Футболка"}

def test_invalid_json():
    source = "Не удалось сформировать карточку товара"

    with pytest.raises(
        ValueError,
        match="В ответе LLM не найден JSON-объект",
    ):
        _ensure_json(source)

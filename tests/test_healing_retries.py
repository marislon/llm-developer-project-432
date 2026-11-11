from unittest.mock import AsyncMock

import pytest

from app.schemas import SupplierFacts
from app.services import steps


@pytest.mark.anyio
async def test_healing_retries(monkeypatch):
    invalid_response = (
        '{"title":"Футболка",'
        '"description":"Хлопковая футболка",'
        '"confidence":1.5}'
    )

    corrected_response = '{"confidence":0.8}'

    mock_run_agent = AsyncMock(
        side_effect=[invalid_response, corrected_response]
    )

    monkeypatch.setattr("app.services.steps.run_agent", mock_run_agent)

    facts = SupplierFacts(product_name="Футболка")

    result = await steps.generate(facts)

    assert result.confidence == 0.8
    assert result.description == "Хлопковая футболка"
    assert mock_run_agent.await_count == 2

    repair_prompt = mock_run_agent.await_args_list[1].args[1]

    assert "Исправь только поле: confidence" in repair_prompt
    assert '"confidence": 1.5' in repair_prompt
    assert "confidence" in repair_prompt

@pytest.mark.anyio
async def test_healing_retries_exhausted(monkeypatch):
    invalid_response = (
        '{"title":"Футболка",'
        '"description":"Хлопковая футболка",'
        '"confidence":1.5}'
    )

    mock_run_agent = AsyncMock(return_value=invalid_response)

    monkeypatch.setattr(
        "app.services.steps.run_agent",
        mock_run_agent,
    )

    facts = SupplierFacts(product_name="Футболка")

    with pytest.raises(ValueError):
        await steps.generate(facts)

    assert mock_run_agent.await_count == 3

@pytest.mark.anyio
async def test_healing_invalid_json(monkeypatch):
    invalid_response = "Это не JSON"

    corrected_response = (
        '{"title":"Футболка",'
        '"description":"Хлопковая футболка",'
        '"confidence":0.8}'
    )

    mock_run_agent = AsyncMock(
        side_effect=[invalid_response, corrected_response]
    )

    monkeypatch.setattr(
        "app.services.steps.run_agent",
        mock_run_agent,
    )

    facts = SupplierFacts(product_name="Футболка")

    result = await steps.generate(facts)

    assert result.confidence == 0.8
    assert mock_run_agent.await_count == 2

    repair_prompt = mock_run_agent.await_args_list[1].args[1]

    assert invalid_response in repair_prompt
    assert "не найден JSON-объект" in repair_prompt


@pytest.mark.anyio
async def test_healing_empty_response(monkeypatch):
    mock_run_agent = AsyncMock(return_value="")

    monkeypatch.setattr(
        "app.services.steps.run_agent",
        mock_run_agent,
    )

    facts = SupplierFacts(product_name="Футболка")

    with pytest.raises(
        ValueError,
        match="В ответе LLM не найден JSON-объект",
    ):
        await steps.generate(facts)

    assert mock_run_agent.await_count == 3

@pytest.mark.anyio
async def test_healing_preserves_valid_description(monkeypatch):
    original_description = "Футболка из хлопка для повседневной носки."

    invalid_response = (
        '{"title":"' + "Очень длинный заголовок " * 4 + '",'
        '"description":"' + original_description + '",'
        '"confidence":0.8}'
    )

    corrected_response = '{"title":"Хлопковая футболка"}'

    mock_run_agent = AsyncMock(
        side_effect=[invalid_response, corrected_response]
    )

    monkeypatch.setattr(
        "app.services.steps.run_agent",
        mock_run_agent,
    )

    facts = SupplierFacts(product_name="Футболка")

    result = await steps.generate(facts)

    assert result.title == "Хлопковая футболка"
    assert result.description == original_description
    assert result.confidence == 0.8
    assert mock_run_agent.await_count == 2

    repair_prompt = mock_run_agent.await_args_list[1].args[1]

    assert "Исправь только поле: title" in repair_prompt
    assert original_description in repair_prompt

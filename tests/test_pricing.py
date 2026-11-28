from decimal import Decimal

import pytest

from app.core.config import ModelPricing, settings
from app.llm.pricing import calculate_cost


def test_calculate_cost(monkeypatch):
    monkeypatch.setitem(
        settings.llm_pricing,
        "test-model",
        ModelPricing(
            input_per_million=Decimal(2),
            output_per_million=Decimal(6),
        ),
    )

    cost = calculate_cost(
        model="test-model",
        input_tokens=1000,
        output_tokens=500,
    )

    assert isinstance(cost, Decimal)
    assert cost == Decimal("0.005")

def test_calculate_cost_unknown_model():
    with pytest.raises(ValueError, match="Тариф для модели"):
        calculate_cost(
            model="unknown-model",
            input_tokens=1000,
            output_tokens=500,
        )


@pytest.mark.parametrize(
    "input_tokens, output_tokens",
    [(-1, 500), (1000, -1)],
)
def test_calculate_cost_negative_tokens(
    input_tokens,
    output_tokens,
):
    with pytest.raises(ValueError, match="Количество токенов"):
        calculate_cost(
            model="qwen2.5:3b",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

"""Расчёт стоимости вызовов LLM."""

from decimal import Decimal

from app.core.config import settings

TOKENS_PER_MILLION = Decimal(1000000)


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> Decimal:
    """Рассчитывает стоимость вызова модели в долларах США."""

    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Количество токенов не может быть отрицательным")

    pricing = settings.llm_pricing.get(model)

    if pricing is None:
        raise ValueError(f"Тариф для модели {model} не настроен")

    input_cost = (
        Decimal(input_tokens)
        * pricing.input_per_million
        / TOKENS_PER_MILLION
    )

    output_cost = (
        Decimal(output_tokens)
        * pricing.output_per_million
        / TOKENS_PER_MILLION
    )

    return input_cost + output_cost

"""Стадии пайплайна: extract → generate → critique.

Каждая функция — один агент-шаг. Один и тот же код работает в трёх runtime:
- FastAPI-эндпоинт (шаг 1 практики),
- Celery-воркер (шаги 2-3),
- Temporal activity (шаг 4).
Это и есть выигрыш слоистой архитектуры.
"""
import json

from pydantic import ValidationError

from app.agents.prompts import (
    critic_agent,
    critic_prompt,
    extractor_agent,
    extractor_prompt,
    field_repair_prompt,
    generator_agent,
    generator_prompt,
    healing_prompt,
)
from app.core.logging import get_logger
from app.llm.client import run_agent
from app.schemas import CardDraft, CritiqueReport, SupplierFacts
from app.services.validation import (
    get_invalid_fields,
    preserve_valid_fields,
    remove_duplicate_missing_fields,
)

log = get_logger(__name__)


async def extract(supplier_text: str) -> SupplierFacts:
    log.info("step_extract_start")

    out = await run_agent(
        extractor_agent,
        extractor_prompt(supplier_text),
    )

    if isinstance(out, SupplierFacts):
        facts = out
    else:
        facts = SupplierFacts.model_validate_json(_ensure_json(out))

    facts.missing_fields = remove_duplicate_missing_fields(
        facts.characteristics,
        facts.missing_fields,
    )

    return facts


async def generate(
    facts: SupplierFacts,
    feedback: list[str] | None = None,
) -> CardDraft:
    log.info("step_generate_start")

    original_prompt = generator_prompt(facts, feedback)

    out = await run_agent(
        generator_agent,
        original_prompt,
    )

    invalid_response = str(out)
    max_healing_attempts = 2
    original_data = None
    invalid_fields = set()
    field_repair_attempted = False
    field_repair_pending = False
    for attempt in range(max_healing_attempts + 1):
        try:
            current_data = json.loads(_ensure_json(invalid_response))
            if field_repair_pending:
                field_name = next(iter(invalid_fields))

                if (
                    not isinstance(current_data, dict)
                    or set(current_data) != {field_name}
                ):
                    raise ValueError(
                        f"Ожидался JSON только с полем {field_name}"
                    )

                current_data = {
                    **original_data,
                    field_name: current_data[field_name],
                }
                field_repair_pending = False
            if original_data is not None:
                current_data = preserve_valid_fields(
                    original=original_data,
                    corrected=current_data,
                    invalid_fields=invalid_fields,
                )

            return CardDraft.model_validate(current_data)

        except (ValidationError, ValueError) as exc:
            log.warning(
                "card_validation_failed",
                attempt=attempt + 1,
                error=str(exc),
            )
            if isinstance(exc, ValidationError) and original_data is None:
                original_data = json.loads(_ensure_json(invalid_response))
                invalid_fields = get_invalid_fields(exc)
            if attempt == max_healing_attempts:
                raise

            if (
                original_data is not None
                and len(invalid_fields) == 1
                and not field_repair_attempted
            ):
                field_name = next(iter(invalid_fields))

                repair_request = field_repair_prompt(
                    draft=original_data,
                    field_name=field_name,
                    validation_error=str(exc),
                )
                field_repair_attempted = True
                field_repair_pending = True
            else:
                repair_request = healing_prompt(
                    original_prompt=original_prompt,
                    invalid_response=invalid_response,
                    validation_error=str(exc),
                )

            invalid_response = str(
                await run_agent(generator_agent, repair_request)
            )



async def critique(
    facts: SupplierFacts,
    draft: CardDraft,
) -> CritiqueReport:
    log.info("step_critique_start")

    out = await run_agent(
        critic_agent,
        critic_prompt(facts, draft),
    )

    if isinstance(out, CritiqueReport):
        return out

    return CritiqueReport.model_validate_json(
        _ensure_json(out)
    )

def _ensure_json(text) -> str:
    """Извлечь JSON-объект из ответа LLM."""
    s = str(text).strip()

    start = s.find("{")
    if start == -1:
        raise ValueError("В ответе LLM не найден JSON-объект")

    decoder = json.JSONDecoder()
    obj, _end = decoder.raw_decode(s[start:])

    return json.dumps(obj, ensure_ascii=False)

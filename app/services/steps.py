"""Стадии пайплайна: extract → generate → critique.

Каждая функция — один агент-шаг. Один и тот же код работает в трёх runtime:
- FastAPI-эндпоинт (шаг 1 практики),
- Celery-воркер (шаги 2-3),
- Temporal activity (шаг 4).
Это и есть выигрыш слоистой архитектуры.
"""
from app.agents.prompts import (
    critic_agent,
    critic_prompt,
    extractor_agent,
    extractor_prompt,
    generator_agent,
    generator_prompt,
)
from app.core.logging import get_logger
from app.llm.client import run_agent
from app.schemas import CardDraft, CritiqueReport, SupplierFacts
from app.services.validation import remove_duplicate_missing_fields

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

    out = await run_agent(
        generator_agent,
        generator_prompt(facts, feedback),
    )

    if isinstance(out, CardDraft):
        return out

    return CardDraft.model_validate_json(_ensure_json(out))


async def critique(facts: SupplierFacts, draft: CardDraft) -> CritiqueReport:
    log.info("step_critique_start")

    out = await run_agent(
        critic_agent,
        critic_prompt(facts, draft),
    )

    if isinstance(out, CritiqueReport):
        return out

    return CritiqueReport.model_validate_json(_ensure_json(out))


def _ensure_json(text) -> str:
    """Локальные модели иногда оборачивают JSON в ```json ... ``` — срезаем."""
    s = str(text).strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    return s.strip()

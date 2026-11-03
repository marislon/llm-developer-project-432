"""Стадии пайплайна: extract → generate → critique.

Каждая функция — один агент-шаг. Один и тот же код работает в трёх runtime:
- FastAPI-эндпоинт (шаг 1 практики),
- Celery-воркер (шаги 2-3),
- Temporal activity (шаг 4).
Это и есть выигрыш слоистой архитектуры.
"""
from app.agents.prompts import critic_agent, extractor_agent, generator_agent
from app.core.logging import get_logger
from app.llm.client import run_agent
from app.schemas import CardDraft, CritiqueReport, SupplierFacts
from app.services.validation import remove_duplicate_missing_fields

log = get_logger(__name__)


async def extract(supplier_text: str) -> SupplierFacts:
    log.info("step_extract_start")

    out = await run_agent(extractor_agent, supplier_text)

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

    prompt = "Факты о товаре:\n" + facts.model_dump_json(indent=2)

    if feedback:
        prompt += "\n\nЗамечания критика, учти:\n"
        prompt += "\n".join(f"- {issue}" for issue in feedback)

    out = await run_agent(generator_agent, prompt)

    if isinstance(out, CardDraft):
        return out

    return CardDraft.model_validate_json(_ensure_json(out))


async def critique(facts: SupplierFacts, draft: CardDraft) -> CritiqueReport:
    log.info("step_critique_start")

    prompt = (
        "Факты о товаре:\n"
        + facts.model_dump_json(indent=2)
        + "\n\nЧерновик карточки для проверки:\n"
        + draft.model_dump_json(indent=2)
    )

    out = await run_agent(critic_agent, prompt)

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


async def run_pipeline(supplier_text: str, max_attempts: int = 3):
    """Полный цикл: extract → generate → critique → итог."""

    facts = await extract(supplier_text)

    feedback: list[str] = []

    for attempt in range(1, max_attempts + 1):
        draft = await generate(facts, feedback or None)
        report = await critique(facts, draft)

        if report.verdict == "approve":
            log.info("pipeline_approved", attempts=attempt)
            return draft, attempt, "approved"

        feedback = report.issues

        log.info(
            "pipeline_regenerate",
            attempt=attempt,
            issues=feedback,
        )

    return draft, max_attempts, "rejected"

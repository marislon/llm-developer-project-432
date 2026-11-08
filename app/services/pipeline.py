"""Управление пайплайном генерации карточки товара."""

from app.core.logging import get_logger
from app.services.steps import critique, extract, generate

log = get_logger(__name__)


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

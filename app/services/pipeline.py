"""Управление пайплайном генерации карточки товара."""

import asyncio

import psycopg

from app.core.logging import get_logger
from app.services.retrieval import retrieve_context
from app.services.steps import (
    critique,
    critique_from_context,
    extract,
    generate,
    generate_from_context,
)
from app.services.validation import validate_sources

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

async def run_rag_pipeline(
    conn: psycopg.Connection,
    document_ids: list[str],
    product_hint: str | None = None,
    max_attempts: int = 3,
):
    """Генерация карточки на основе документов поставщика."""

    context = await asyncio.to_thread(
        retrieve_context,
        conn,
        document_ids,
        product_hint,
    )

    if not context.fragment_ids:
        raise ValueError("Не найден релевантный контекст")

    feedback: list[str] = []

    for attempt in range(1, max_attempts + 1):
        draft = await generate_from_context(
            context=context.text,
            product_hint=product_hint,
            feedback=feedback or None,
        )
        source_errors = await asyncio.to_thread(
            validate_sources,
            conn,
            draft.sources,
            context.fragment_ids,
        )

        if source_errors:
            feedback = source_errors

            log.info(
                "rag_generator_invalid_sources",
                attempt=attempt,
                issues=feedback,
            )

            continue

        report = await critique_from_context(
            context=context.text,
            draft=draft,
            product_hint=product_hint,
        )

        source_errors = await asyncio.to_thread(
            validate_sources,
            conn,
            report.sources,
            context.fragment_ids,
        )

        if source_errors:
            feedback = report.issues + source_errors

            log.info(
                "rag_critic_invalid_sources",
                attempt=attempt,
                issues=feedback,
            )

            continue

        if report.verdict == "approve":
            log.info("rag_pipeline_approved", attempts=attempt)
            return draft, attempt, "approved"

        feedback = report.issues

        log.info(
            "rag_pipeline_regenerate",
            attempt=attempt,
            issues=feedback,
        )

    return draft, max_attempts, "rejected"

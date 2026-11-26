"""Temporal-activities: те же стадии пайплайна из app/services.

Activities выполняются БЕЗ песочницы — здесь можно импортировать конфиг,
LLM-клиент, ходить в сеть. Данные передаём JSON-строками: Temporal
сериализует их в историю workflow, Pydantic-валидация — на границе.
"""
import json
from dataclasses import asdict

from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.core.db import connection
from app.repositories import jobs as jobs_repo
from app.schemas import CardDraft, SourceReference, SupplierFacts
from app.services import retrieval, steps, validation
from app.services.documents import process_document
from app.services.indexing import index_document


@activity.defn
async def extract_activity(supplier_text: str) -> str:
    facts = await steps.extract(supplier_text)
    return facts.model_dump_json()


@activity.defn
async def generate_activity(facts_json: str, feedback_json: str | None = None) -> str:
    facts = SupplierFacts.model_validate_json(facts_json)
    feedback = json.loads(feedback_json) if feedback_json else None
    draft = await steps.generate(facts, feedback)
    return draft.model_dump_json()


@activity.defn
async def critique_activity(facts_json: str, draft_json: str) -> str:
    facts = SupplierFacts.model_validate_json(facts_json)
    draft = CardDraft.model_validate_json(draft_json)
    report = await steps.critique(facts, draft)
    return report.model_dump_json()

@activity.defn
def update_job_status_activity(
    job_id: str,
    status: str,
    result_json: str | None = None,
    error: str | None = None,
    attempts: int | None = None,
) -> None:
    result = (
        CardDraft.model_validate_json(result_json)
        if result_json is not None
        else None
    )

    jobs_repo.update_job_status(
        job_id,
        status,
        result=result,
        error=error,
        attempts=attempts,
    )

@activity.defn
def process_document_activity(
    document_id: str,
    file_path: str,
) -> int:
    return process_document(document_id, file_path)

@activity.defn
def index_document_activity(document_id: str) -> int:
    return index_document(document_id)

@activity.defn
def retrieve_context_activity(
    document_ids: list[str],
    product_hint: str | None = None,
) -> dict:
    """Получить релевантный контекст для генерации карточки."""

    with connection() as conn:
        context = retrieval.retrieve_context(
            conn,
            document_ids,
            product_hint,
        )

    if not context.fragment_ids:
        raise ApplicationError(
            "Не найден релевантный контекст",
            non_retryable=True,
        )

    return asdict(context)

@activity.defn
async def generate_from_context_activity(
    context: str,
    product_hint: str | None = None,
    feedback: list[str] | None = None,
) -> str:
    """Сгенерировать карточку на основе контекста документов."""

    draft = await steps.generate_from_context(
        context=context,
        product_hint=product_hint,
        feedback=feedback,
    )

    return draft.model_dump_json()

@activity.defn
def validate_sources_activity(
    sources: list[dict],
    context_fragment_ids: list[str],
) -> list[str]:
    """Проверить достоверность ссылок на источники."""

    source_references = [
        SourceReference.model_validate(source)
        for source in sources
    ]

    with connection() as conn:
        return validation.validate_sources(
            conn,
            source_references,
            context_fragment_ids,
        )

@activity.defn
async def critique_from_context_activity(
    context: str,
    draft_json: str,
    product_hint: str | None = None,
) -> str:
    """Оценить карточку товара с учётом исходного контекста."""

    draft = CardDraft.model_validate_json(draft_json)

    report = await steps.critique_from_context(
        context=context,
        draft=draft,
        product_hint=product_hint,
    )

    return report.model_dump_json()

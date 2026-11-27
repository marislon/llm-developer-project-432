import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from temporalio import activity
from temporalio.client import WorkflowExecutionStatus, WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.repositories import jobs as jobs_repo
from app.schemas import CardDraft, CritiqueReport, SourceReference
from app.temporal.activities import update_job_status_activity
from app.temporal.workflows import DocumentCardWorkflow


async def wait_for_job_status(
    job_id: str,
    expected_status: str,
    timeout: float = 30.0,
) -> dict:
    async with asyncio.timeout(timeout):
        while True:
            saved_job = jobs_repo.get_job_by_id(job_id)

            if (
                saved_job is not None
                and saved_job["status"] == expected_status
            ):
                return saved_job

            await asyncio.sleep(0.1)


async def get_status_history(handle, data_converter) -> list[str]:
    history = await handle.fetch_history()
    statuses = []

    completed_activity_ids = {
        event.activity_task_completed_event_attributes.scheduled_event_id
        for event in history.events
        if event.HasField("activity_task_completed_event_attributes")
    }

    for event in history.events:
        if not event.HasField("activity_task_scheduled_event_attributes"):
            continue

        attributes = event.activity_task_scheduled_event_attributes

        if attributes.activity_type.name != "update_job_status_activity":
            continue

        assert event.event_id in completed_activity_ids

        arguments = await data_converter.decode(
            attributes.input.payloads
        )

        statuses.append(arguments[1])

    return statuses

@activity.defn(name="retrieve_context_activity")
async def mock_retrieve_context_activity(
    document_ids: list[str],
    product_hint: str | None = None,
) -> dict:
    if product_hint == "context_failure":
        raise ApplicationError(
            "Тестовая ошибка получения контекста",
            non_retryable=True,
        )
    text = (
        "Электрический чайник.\n"
        "Мощность: 2200 Вт.\n"
        "Объем: 1.7 л.\n"
        "Материал корпуса: нержавеющая сталь."
    )

    return {
        "text": text,
        "fragment_ids": ["fragment-1"],
        "size": len(text),
    }

@activity.defn(name="generate_from_context_activity")
async def mock_generate_from_context_activity(
    context: str,
    product_hint: str | None = None,
    feedback: list[str] | None = None,
) -> str:
    if feedback is not None:
        expected_feedback = {
            "invalid_source": [
                "Фрагмент fake-id отсутствует в контексте",
            ],
            "persistent_invalid_source": [
                "Фрагмент fake-id отсутствует в контексте",
            ],
            "invalid_critic_source": [
                "Фрагмент fake-critic-id отсутствует в контексте",
            ],
            "critic_rework": [
                "Необходимо уточнить объем в заголовке",
            ],
            "persistent_critic_rework": [
                "Необходимо уточнить объем в заголовке",
            ],
        }

        assert feedback == expected_feedback[product_hint]
    fragment_id = "fragment-1"

    if product_hint == "invalid_source" and not feedback:
        fragment_id = "fake-id"

    if product_hint == "persistent_invalid_source":
        fragment_id = "fake-id"
    title = "Электрический чайник"

    if product_hint in ("invalid_critic_source", "critic_rework") and feedback:
        title = "Электрический чайник 1.7 л"
    draft = CardDraft(
        title=title,
        description="Чайник из нержавеющей стали объемом 1.7 л.",
        characteristics={
            "Мощность": "2200 Вт",
            "Объем": "1.7 л",
            "Материал корпуса": "Нержавеющая сталь",
        },
        benefits=["Высокая мощность"],
        missing_fields=["Гарантия"],
        confidence=0.5 if product_hint == "low_confidence" else 0.85,
        sources=[
            SourceReference(fragment_id=fragment_id),
        ],
    )

    return draft.model_dump_json()

@activity.defn(name="validate_sources_activity")
async def mock_validate_sources_activity(
    sources: list[dict],
    context_fragment_ids: list[str],
) -> list[str]:
    errors = []

    if not sources:
        return ["Отсутствуют ссылки на источники"]

    for source in sources:
        fragment_id = source.get("fragment_id")

        if fragment_id not in context_fragment_ids:
            errors.append(
                f"Фрагмент {fragment_id} отсутствует в контексте"
            )

    return errors

@activity.defn(name="critique_from_context_activity")
async def mock_critique_from_context_activity(
    context: str,
    draft_json: str,
    product_hint: str | None = None,
) -> str:
    draft = CardDraft.model_validate_json(draft_json)
    sources = draft.sources

    if product_hint == "invalid_critic_source" and draft.title == "Электрический чайник":
        sources = [
            SourceReference(fragment_id="fake-critic-id"),
        ]
    verdict = "approve"
    issues = []

    if product_hint == "critic_rework" and draft.title == "Электрический чайник":
        verdict = "regenerate"
        issues = ["Необходимо уточнить объем в заголовке"]
    if product_hint == "persistent_critic_rework":
        verdict = "regenerate"
        issues = ["Необходимо уточнить объем в заголовке"]
    report = CritiqueReport(
        verdict=verdict,
        issues=issues,
        sources=sources,
    )

    return report.model_dump_json()

@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
@pytest.mark.parametrize(
    "product_hint, expected_status, expected_confidence, expected_attempts",
    [
        ("Электрический чайник", "approved", 0.85, 1),
        ("low_confidence", "approved", 0.5, 1),
        ("invalid_source", "approved", 0.85, 2),
        ("invalid_critic_source", "approved", 0.85, 2),
        ("critic_rework", "approved", 0.85, 2),
        ("persistent_invalid_source", "rejected", 0.85, 3),
        ("persistent_critic_rework", "approved", 0.85, 3),
    ],
    ids=[
        "approved",
        "low_confidence",
        "invalid_source",
        "invalid_critic_source",
        "critic_rework",
        "persistent_invalid_source",
        "persistent_critic_rework",
    ],
)
async def test_document_card_workflow(
    db_pool,
    product_hint,
    expected_status,
    expected_confidence,
    expected_attempts,
):
    job_id, created = jobs_repo.create_job_with_connection(
        payload={
            "document_ids": ["document-1"],
            "product_hint": product_hint,
        },
        idempotency_key=f"document-card-{uuid.uuid4().hex}",
    )

    assert created is True

    async with await WorkflowEnvironment.start_local() as env:
        with ThreadPoolExecutor(max_workers=2) as executor:
            async with Worker(
                env.client,
                task_queue="document-card-test",
                workflows=[DocumentCardWorkflow],
                activity_executor=executor,
                activities=[
                    mock_retrieve_context_activity,
                    mock_generate_from_context_activity,
                    mock_validate_sources_activity,
                    mock_critique_from_context_activity,
                    update_job_status_activity,
                ],
                workflow_failure_exception_types=[ApplicationError],
            ):
                handle = await env.client.start_workflow(
                    DocumentCardWorkflow.run,
                    args=[
                        ["document-1"],
                        product_hint,
                        job_id,
                    ],
                    id=f"document-card-test-{job_id}",
                    task_queue="document-card-test",
                )

                if product_hint in (
                    "low_confidence",
                    "persistent_invalid_source",
                    "persistent_critic_rework",
                ):
                    await wait_for_job_status(
                        job_id,
                        "waiting_for_human",
                    )

                    description = await handle.describe()
                    assert description.status == WorkflowExecutionStatus.RUNNING
                    if product_hint == "persistent_invalid_source":
                        await handle.signal(
                            DocumentCardWorkflow.submit_human_decision,
                            "approve",
                        )
                        with pytest.raises(TimeoutError):
                            await asyncio.wait_for(
                                handle.result(),
                                timeout=2.0,
                            )

                        description = await handle.describe()
                        assert description.status == WorkflowExecutionStatus.RUNNING

                        saved_job = jobs_repo.get_job_by_id(job_id)
                        assert saved_job is not None
                        assert saved_job["status"] == "waiting_for_human"

                    decision = (
                        "reject"
                        if product_hint == "persistent_invalid_source"
                        else "approve"
                    )

                    await handle.signal(
                        DocumentCardWorkflow.submit_human_decision,
                        decision,
                    )

                await asyncio.wait_for(
                    handle.result(),
                    timeout=30.0,
                )

                statuses = await get_status_history(
                    handle,
                    env.client.data_converter,
                )

                if product_hint == "Электрический чайник":
                    assert statuses == [
                        "retrieving",
                        "generating",
                        "validating_sources",
                        "critiquing",
                        "validating_sources",
                        "approved",
                    ]

                elif product_hint == "low_confidence":
                    assert statuses == [
                        "retrieving",
                        "generating",
                        "validating_sources",
                        "critiquing",
                        "validating_sources",
                        "waiting_for_human",
                        "approved",
                    ]

                elif product_hint == "invalid_source":
                    assert statuses == [
                        "retrieving",
                        "generating",
                        "validating_sources",
                        "regenerating",
                        "generating",
                        "validating_sources",
                        "critiquing",
                        "validating_sources",
                        "approved",
                    ]

                elif product_hint in (
                    "invalid_critic_source",
                    "critic_rework",
                ):
                    assert statuses == [
                        "retrieving",
                        "generating",
                        "validating_sources",
                        "critiquing",
                        "validating_sources",
                        "regenerating",
                        "generating",
                        "validating_sources",
                        "critiquing",
                        "validating_sources",
                        "approved",
                    ]

                elif product_hint == "persistent_invalid_source":
                    assert statuses == [
                        "retrieving",
                        "generating",
                        "validating_sources",
                        "regenerating",
                        "generating",
                        "validating_sources",
                        "regenerating",
                        "generating",
                        "validating_sources",
                        "waiting_for_human",
                        "rejected",
                    ]

                elif product_hint == "persistent_critic_rework":
                    assert statuses == [
                        "retrieving",
                        "generating",
                        "validating_sources",
                        "critiquing",
                        "validating_sources",
                        "regenerating",
                        "generating",
                        "validating_sources",
                        "critiquing",
                        "validating_sources",
                        "regenerating",
                        "generating",
                        "validating_sources",
                        "critiquing",
                        "validating_sources",
                        "waiting_for_human",
                        "approved",
                    ]

                saved_job = jobs_repo.get_job_by_id(job_id)

                assert saved_job is not None
                assert saved_job["status"] == expected_status
                assert saved_job["attempts"] == expected_attempts
                if product_hint == "persistent_invalid_source":
                    assert saved_job["error"] == "Фрагмент fake-id отсутствует в контексте"
                else:
                    assert saved_job["error"] == ""

                result = saved_job["result"]

                assert result is not None
                expected_title = (
                    "Электрический чайник 1.7 л"
                    if product_hint in ("invalid_critic_source", "critic_rework")
                    else "Электрический чайник"
                )

                assert result.title == expected_title
                assert result.confidence == expected_confidence
                assert result.missing_fields == ["Гарантия"]
                if product_hint == "persistent_invalid_source":
                    assert result.sources[0].fragment_id == "fake-id"
                else:
                    assert result.sources[0].fragment_id == "fragment-1"

@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_document_card_workflow_context_failure(db_pool):
    job_id, created = jobs_repo.create_job_with_connection(
        payload={
            "document_ids": ["document-1"],
            "product_hint": "context_failure",
        },
        idempotency_key=f"document-card-{uuid.uuid4().hex}",
    )

    assert created is True

    async with await WorkflowEnvironment.start_local() as env:
        with ThreadPoolExecutor(max_workers=2) as executor:
            async with Worker(
                env.client,
                task_queue="document-card-test",
                workflows=[DocumentCardWorkflow],
                activity_executor=executor,
                activities=[
                    mock_retrieve_context_activity,
                    mock_generate_from_context_activity,
                    mock_validate_sources_activity,
                    mock_critique_from_context_activity,
                    update_job_status_activity,
                ],
                workflow_failure_exception_types=[ApplicationError],
            ):
                handle = await env.client.start_workflow(
                    DocumentCardWorkflow.run,
                    args=[
                        ["document-1"],
                        "context_failure",
                        job_id,
                    ],
                    id=f"document-card-test-{job_id}",
                    task_queue="document-card-test",
                )
                with pytest.raises(WorkflowFailureError):
                    await handle.result()
                statuses = await get_status_history(
                    handle,
                    env.client.data_converter,
                )

                assert statuses == [
                    "retrieving",
                    "failed",
                ]

                saved_job = jobs_repo.get_job_by_id(job_id)

                assert saved_job is not None
                assert saved_job["status"] == "failed"
                assert saved_job["attempts"] == 0
                assert saved_job["result"] is None
                assert saved_job["error"] == "Не удалось получить RAG-контекст"

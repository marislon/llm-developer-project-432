import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from temporalio import activity
from temporalio.api.enums.v1 import EventType
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.core.config import settings
from app.core.db import connection
from app.main import app
from app.repositories import documents as documents_repo
from app.repositories import fragments as fragments_repo
from app.routers import documents, workflows
from app.schemas import CardDraft, CritiqueReport, SourceReference
from app.services import retrieval, steps
from app.temporal import activities
from app.temporal.workflows import DocumentCardWorkflow, DocumentWorkflow


def build_card_draft(fragment_id: str) -> CardDraft:
    return CardDraft(
        title="Электрический чайник",
        description=(
            "Электрический чайник мощностью 2200 Вт. "
            "Объём чайника составляет 1,7 литра. "
            "Корпус изготовлен из нержавеющей стали."
        ),
        characteristics={
            "Мощность": "2200 Вт",
            "Объём": "1,7 л",
            "Материал корпуса": "Нержавеющая сталь",
        },
        benefits=[],
        missing_fields=["Гарантия"],
        confidence=0.6,
        sources=[
            SourceReference(
                fragment_id=fragment_id,
                description=(
                    "Мощность, объём и материал корпуса"
                ),
            ),
        ],
    )


def build_critique_report(fragment_id: str) -> CritiqueReport:
    return CritiqueReport(
        verdict="approve",
        issues=[],
        sources=[
            SourceReference(
                fragment_id=fragment_id,
                description="Характеристики подтверждены",
            ),
        ],
    )

def build_fake_run_agent(
    fragment_id: str,
    invalid_fragment_id: str | None,
    generator_prompts: list[str],
    critic_prompts: list[str],
):
    async def fake_run_agent(agent, prompt: str):
        if agent is steps.rag_generator_agent:
            generator_prompts.append(prompt)
            source_id = fragment_id
            if invalid_fragment_id is not None and len(generator_prompts) == 1:
                source_id = invalid_fragment_id
            return build_card_draft(source_id).model_dump_json()

        if agent is steps.rag_critic_agent:
            critic_prompts.append(prompt)
            return build_critique_report(
                fragment_id
            ).model_dump_json()

        raise AssertionError(
            f"Unexpected agent: {agent}"
        )

    return fake_run_agent

def fake_embed_query(query: str) -> list[float]:
    return TEST_EMBEDDING.copy()

TEST_FRAGMENT_TEXT = (
    "Электрический чайник. "
    "Мощность: 2200 Вт. "
    "Объём: 1,7 л. "
    "Материал корпуса: нержавеющая сталь."
)

TEST_EMBEDDING = [1.0] + [0.0] * 767

def build_fake_process_document(fragment_id: str):
    @activity.defn(name="process_document_activity")
    def fake_process_document(
        document_id: str,
        file_path: str,
    ) -> int:
        with connection() as conn:
            documents_repo.update_document_status(
                conn,
                document_id,
                "parsing",
            )

            fragments_repo.create_fragment(
                conn=conn,
                fragment_id=fragment_id,
                document_id=document_id,
                ord=1,
                page=1,
                section="Характеристики товара",
                text=TEST_FRAGMENT_TEXT,
            )

        return 1

    return fake_process_document

def build_fake_index_document(fragment_id: str):
    @activity.defn(name="index_document_activity")
    def fake_index_document(document_id: str) -> int:
        with connection() as conn:
            documents_repo.update_document_status(
                conn,
                document_id,
                "embedding",
            )

            fragments_repo.update_embeddings(
                conn,
                [(fragment_id, TEST_EMBEDDING)],
            )

            documents_repo.update_document_status(
                conn,
                document_id,
                "indexed",
            )

        return 1

    return fake_index_document

def build_test_activities(fragment_id: str) -> list:
    return [
        build_fake_process_document(fragment_id),
        build_fake_index_document(fragment_id),
        activities.retrieve_context_activity,
        activities.generate_from_context_activity,
        activities.validate_sources_activity,
        activities.critique_from_context_activity,
        activities.update_job_status_activity,
    ]

def configure_model_mocks(
    monkeypatch,
    fragment_id: str,
    invalid_fragment_id: str | None,
    generator_prompts: list[str],
    critic_prompts: list[str],
):
    monkeypatch.setattr(
        steps,
        "run_agent",
        build_fake_run_agent(
            fragment_id, invalid_fragment_id, generator_prompts, critic_prompts
        ),
    )

    monkeypatch.setattr(
        retrieval,
        "embed_query",
        fake_embed_query,
    )

def configure_temporal_mocks(monkeypatch, temporal_client, task_queue):
    async def fake_client():
        return temporal_client

    class FakeDocumentClient:
        @staticmethod
        async def connect(*args, **kwargs):
            return temporal_client

    monkeypatch.setattr(
        workflows,
        "_client",
        fake_client,
    )

    monkeypatch.setattr(
        documents,
        "Client",
        FakeDocumentClient,
    )

    monkeypatch.setattr(
        settings,
        "temporal_task_queue",
        task_queue,
    )

def cleanup_test_data(
    document_id: str | None,
    job_id: str | None,
) -> None:
    with connection() as conn:
        if job_id is not None:
            conn.execute(
                "DELETE FROM jobs WHERE id = %s",
                (job_id,),
            )

        if document_id is not None:
            conn.execute(
                "DELETE FROM documents WHERE id = %s",
                (document_id,),
            )

@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_first_source", [False, True], ids=["valid-source", "regeneration"]
)
async def test_rag_e2e(db_pool, monkeypatch, tmp_path, invalid_first_source):
    fragment_id = f"e2e-fragment-{uuid4().hex}"
    task_queue = f"rag-e2e-{uuid4().hex}"

    document_id = None
    job_id = None

    invalid_fragment_id = (
        f"missing-fragment-{uuid4().hex}" if invalid_first_source else None
    )
    expected_attempts = 2 if invalid_first_source else 1
    generator_prompts: list[str] = []
    critic_prompts: list[str] = []
    configure_model_mocks(
        monkeypatch, fragment_id, invalid_fragment_id, generator_prompts, critic_prompts
    )

    monkeypatch.setattr(
        documents,
        "UPLOAD_DIR",
        tmp_path,
    )

    try:
        async with await WorkflowEnvironment.start_local() as env:
            configure_temporal_mocks(
                monkeypatch,
                env.client,
                task_queue,
            )

            with ThreadPoolExecutor(max_workers=4) as executor:
                async with (
                    Worker(
                        env.client,
                        task_queue=task_queue,
                        workflows=[
                            DocumentWorkflow,
                            DocumentCardWorkflow,
                        ],
                        activities=build_test_activities(fragment_id),
                        activity_executor=executor,
                    ),
                    AsyncClient(
                        transport=ASGITransport(app=app),
                        base_url="http://test",
                    ) as client,
                ):
                    upload_response = await client.post(
                        "/documents",
                        files={
                            "file": (
                                "kettle_spec.docx",
                                f"Test document {uuid4().hex}".encode(),
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            ),
                        },
                    )

                    assert upload_response.status_code == 202

                    upload_data = upload_response.json()
                    document_id = upload_data["document_id"]

                    assert upload_data["status"] == "new"
                    assert document_id

                    document_handle = env.client.get_workflow_handle(
                        f"document-{document_id}"
                    )

                    fragments_count = await asyncio.wait_for(
                        document_handle.result(),
                        timeout=30,
                    )

                    assert fragments_count == 1

                    document_response = await client.get(
                        f"/documents/{document_id}"
                    )

                    assert document_response.status_code == 200

                    document_data = document_response.json()

                    assert document_data["status"] == "indexed"
                    assert document_data["chunks_count"] == 1

                    generation_response = await client.post(
                        "/workflows",
                        json={
                            "document_ids": [document_id],
                            "product_hint": "Электрический чайник",
                        },
                        headers={
                            "Idempotency-Key": f"rag-e2e-{uuid4().hex}",
                        },
                    )

                    assert generation_response.status_code == 202

                    generation_data = generation_response.json()
                    job_id = generation_data["id"]

                    assert generation_data["status"] == "pending"
                    assert job_id

                    async with asyncio.timeout(30):
                        while True:
                            status_response = await client.get(
                                f"/workflows/{job_id}"
                            )

                            assert status_response.status_code == 200

                            status_data = status_response.json()

                            assert status_data["status"] not in (
                                "failed",
                                "rejected",
                            ), status_data

                            if status_data["status"] == "waiting_for_human":
                                break

                            await asyncio.sleep(0.1)

                    assert status_data["attempts"] == expected_attempts
                    draft_response = await client.get(
                        f"/workflows/{job_id}/result"
                    )

                    assert draft_response.status_code == 200

                    draft_data = draft_response.json()

                    assert draft_data["id"] == job_id
                    assert draft_data["status"] == "waiting_for_human"

                    draft = CardDraft.model_validate(draft_data["result"])

                    assert draft.title == "Электрический чайник"
                    assert draft.confidence == 0.6
                    assert draft.characteristics["Мощность"] == "2200 Вт"
                    assert draft.characteristics["Объём"] == "1,7 л"
                    assert "Гарантия" in draft.missing_fields
                    assert "Гарантия" not in draft.characteristics

                    assert len(draft.sources) == 1
                    assert draft.sources[0].fragment_id == fragment_id

                    approval_response = await client.post(
                        f"/workflows/{job_id}/approve"
                    )

                    assert approval_response.status_code == 202

                    assert approval_response.json() == {
                        "id": job_id,
                        "decision": "approve",
                        "status": "accepted",
                    }

                    generation_handle = env.client.get_workflow_handle(
                        job_id
                    )

                    await asyncio.wait_for(
                        generation_handle.result(),
                        timeout=30,
                    )

                    final_status_response = await client.get(
                        f"/workflows/{job_id}"
                    )

                    assert final_status_response.status_code == 200

                    final_status_data = final_status_response.json()

                    assert final_status_data["status"] == "approved"
                    assert final_status_data["attempts"] == expected_attempts
                    assert not final_status_data["error"]

                    final_result_response = await client.get(
                        f"/workflows/{job_id}/result"
                    )

                    assert final_result_response.status_code == 200

                    final_result_data = final_result_response.json()

                    assert final_result_data["id"] == job_id
                    assert final_result_data["status"] == "approved"

                    final_draft = CardDraft.model_validate(
                        final_result_data["result"]
                    )

                    assert final_draft == draft

                    history = await generation_handle.fetch_history()

                    signal_events = [
                        event
                        for event in history.events
                        if event.event_type
                           == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_SIGNALED
                    ]

                    assert len(signal_events) == 1

                    signal_attributes = (
                        signal_events[0].workflow_execution_signaled_event_attributes
                    )

                    assert signal_attributes.signal_name == "submit_human_decision"

                    signal_args = await env.client.data_converter.decode(
                        signal_attributes.input.payloads
                    )

                    assert signal_args == ["approve"]

                    assert history.events[-1].event_type == (
                        EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
                    )

                    completed_activity_ids = {
                        event.activity_task_completed_event_attributes.scheduled_event_id
                        for event in history.events
                        if event.event_type
                           == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED
                    }

                    status_history = []
                    regeneration_errors = []
                    generation_feedback = []

                    for event in history.events:
                        if event.event_type != EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
                            continue

                        attributes = event.activity_task_scheduled_event_attributes

                        if attributes.activity_type.name == "generate_from_context_activity":
                            assert event.event_id in completed_activity_ids
                            generation_args = await env.client.data_converter.decode(
                                attributes.input.payloads
                            )
                            generation_feedback.append(generation_args[2])

                        if attributes.activity_type.name != "update_job_status_activity":
                            continue

                        assert event.event_id in completed_activity_ids

                        args = await env.client.data_converter.decode(
                            attributes.input.payloads
                        )

                        assert args[0] == job_id

                        status_history.append(args[1])
                        if args[1] == "regenerating":
                            regeneration_errors.append(args[3])

                    expected_status_history = [
                        "retrieving",
                        "generating",
                        "validating_sources",
                        "critiquing",
                        "validating_sources",
                        "waiting_for_human",
                        "approved",
                    ]
                    if invalid_first_source:
                        expected_status_history[3:3] = [
                            "regenerating", "generating", "validating_sources"
                        ]

                    assert status_history == expected_status_history
                    assert len(generator_prompts) == expected_attempts
                    assert len(critic_prompts) == 1
                    assert len(generation_feedback) == expected_attempts
                    assert generation_feedback[0] is None

                    if invalid_first_source:
                        assert len(regeneration_errors) == 1
                        assert regeneration_errors[0]
                        feedback = generation_feedback[1]
                        assert feedback
                        assert "; ".join(feedback) == regeneration_errors[0]
                        assert invalid_fragment_id in generator_prompts[1]
                        assert invalid_fragment_id not in generator_prompts[0]
                        assert invalid_fragment_id not in critic_prompts[0]
                    else:
                        assert not regeneration_errors

    finally:
        cleanup_test_data(document_id, job_id)

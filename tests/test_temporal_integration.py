from concurrent.futures import ThreadPoolExecutor

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.repositories import jobs as jobs_repo
from app.temporal.activities import update_job_status_activity
from app.temporal.workflows import CardWorkflow


@activity.defn(name="extract_activity")
async def failing_extract_activity(supplier_text: str) -> str:
    raise ApplicationError(
        "Тестовая ошибка извлечения данных",
        non_retryable=True,
    )

@pytest.mark.anyio
async def test_workflow_fails_on_extract_error(db_pool):
    import uuid
    job_id, created = jobs_repo.create_job_with_connection(
        payload={"supplier_text": "Тестовое описание товара"},
        idempotency_key=f"integration-failure-{uuid.uuid4().hex}",
    )

    assert created is True
    async with await WorkflowEnvironment.start_local() as env:
        assert env.client is not None

        with ThreadPoolExecutor(max_workers=2) as executor:
            async with Worker(
                env.client,
                task_queue="card-integration-test",
                workflows=[CardWorkflow],
                activity_executor=executor,
                activities=[
                    failing_extract_activity,
                    update_job_status_activity,
                ],
                workflow_failure_exception_types=[ApplicationError],
            ):
                handle = await env.client.start_workflow(
                    CardWorkflow.run,
                    args=["Тестовое описание товара", 3, job_id],
                    id=f"card-integration-extract-failure-{job_id}",
                    task_queue="card-integration-test",
                )
                with pytest.raises(WorkflowFailureError):
                    await handle.result()
                saved_job = jobs_repo.get_job_by_id(job_id)

                assert saved_job is not None
                assert saved_job["status"] == "failed"
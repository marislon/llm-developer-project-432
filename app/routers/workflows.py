"""Temporal-вариант через FastAPI: старт workflow, статус, сигналы."""

from fastapi import APIRouter, Header, HTTPException
from temporalio.client import Client

from app.core.config import settings
from app.repositories import jobs as jobs_repo
from app.schemas import DocumentGenerationIn

router = APIRouter(tags=["workflows"])


async def _client() -> Client:
    return await Client.connect(settings.temporal_host)


@router.post("/workflows", status_code=202)
async def start_workflow(
    body: DocumentGenerationIn,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
):
    try:
        job_id, created = jobs_repo.create_job_with_connection(
            body.model_dump(),
            idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    if created:
        client = await _client()

        await client.start_workflow(
            "DocumentCardWorkflow",
            args=[
                body.document_ids,
                body.product_hint,
                job_id,
            ],
            id=job_id,
            task_queue=settings.temporal_task_queue,
        )

    return {
        "id": job_id,
        "status": "pending",
    }

@router.get("/workflows/{wf_id}")
async def workflow_status(wf_id: str):
    # TODO(шаг 4): handle = client.get_workflow_handle(wf_id);
    #   await handle.describe() → run_status; await handle.query("current_status") → status.
    #   Ошибка → HTTPException(404, "workflow not found")
    raise NotImplementedError("workflow_status")


@router.post("/workflows/{wf_id}/approve")
async def approve(wf_id: str):
    # TODO(шаг 4): await client.get_workflow_handle(wf_id).signal("approve")
    raise NotImplementedError("approve")


@router.post("/workflows/{wf_id}/request-changes")
async def request_changes(wf_id: str):
    # TODO(шаг 4): await client.get_workflow_handle(wf_id).signal("request_changes")
    raise NotImplementedError("request_changes")


@router.get("/workflows/{wf_id}/result")
async def workflow_result(wf_id: str):
    # TODO(шаг 4): result = await handle.result() (упадёт, если не завершён → 409)
    raise NotImplementedError("workflow_result")

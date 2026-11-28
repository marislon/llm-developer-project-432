"""Temporal-вариант через FastAPI: старт workflow, статус, сигналы."""

from fastapi import APIRouter, Header, HTTPException
from temporalio.client import Client

from app.core.config import settings
from app.repositories import jobs as jobs_repo
from app.schemas import DocumentGenerationIn

router = APIRouter(tags=["workflows"])


async def _client() -> Client:
    return await Client.connect(settings.temporal_host)

async def _submit_human_decision(
    wf_id: str,
    decision: str,
) -> dict:
    job = jobs_repo.get_job_by_id(wf_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    if job["status"] != "waiting_for_human":
        raise HTTPException(
            status_code=409,
            detail="Job is not waiting for human decision",
        )

    client = await _client()
    handle = client.get_workflow_handle(wf_id)

    await handle.signal(
        "submit_human_decision",
        decision,
    )

    return {
        "id": wf_id,
        "decision": decision,
        "status": "accepted",
    }

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
    job = jobs_repo.get_job_by_id(wf_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return {
        "id": wf_id,
        "status": job["status"],
        "attempts": job["attempts"],
        "error": job["error"],
    }


@router.post("/workflows/{wf_id}/approve", status_code=202)
async def approve(wf_id: str):
    return await _submit_human_decision(wf_id, "approve")


@router.post("/workflows/{wf_id}/reject", status_code=202)
async def reject(wf_id: str):
    return await _submit_human_decision(wf_id, "reject")


@router.get("/workflows/{wf_id}/result")
async def workflow_result(wf_id: str):
    job = jobs_repo.get_job_by_id(wf_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    if job["status"] not in ("waiting_for_human", "approved"):
        raise HTTPException(
            status_code=409,
            detail="Job result is not available",
        )

    if job["result"] is None:
        raise HTTPException(
            status_code=409,
            detail="Job result is not available",
        )

    return {
        "id": wf_id,
        "status": job["status"],
        "result": job["result"],
    }

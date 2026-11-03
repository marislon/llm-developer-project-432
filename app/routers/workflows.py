"""Temporal-вариант через FastAPI: старт workflow, статус, сигналы."""
import uuid

from fastapi import APIRouter, HTTPException
from temporalio.client import Client

from app.core.config import settings
from app.schemas import JobIn

router = APIRouter(tags=["workflows"])


async def _client() -> Client:
    return await Client.connect(settings.temporal_host)


@router.post("/workflows", status_code=202)
async def start_workflow(body: JobIn):
    # TODO(шаг 4): client.start_workflow("CardWorkflow", args=[body.supplier_text, 3],
    #   id=f"card-{uuid.uuid4().hex[:12]}", task_queue=settings.temporal_task_queue)
    #   → вернуть {"id": wf_id, "status": "started"}
    raise NotImplementedError("start_workflow")


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

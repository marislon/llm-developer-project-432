"""Фоновый вариант: job в RabbitMQ → Celery-воркер (шаги 2-3 практики)."""
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from app.repositories import jobs as jobs_repo
from app.schemas import JobIn
from app.workers.celery_app import celery_app

router = APIRouter(tags=["jobs"])


@router.post("/jobs", status_code=202)
def create_job(
    body: JobIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    try:
        job_id, created = jobs_repo.create_job_with_connection(
            {"supplier_text": body.supplier_text},
            idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    if created:
        celery_app.send_task(
            "app.workers.tasks.generate_card",
            kwargs={
                "job_id": job_id,
                "supplier_text": body.supplier_text,
            },
            queue="card.generate",
        )

    return JSONResponse(
        {"id": job_id, "status": "pending"},
        status_code=202,
    )


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs_repo.get_job_by_id(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Задание не найдено",
        )

    return job

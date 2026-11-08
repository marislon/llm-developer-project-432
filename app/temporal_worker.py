"""Точка входа Temporal-воркера: регистрирует workflows + activities."""
import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from app.core.config import settings
from app.core.db import pool
from app.core.logging import get_logger, setup_logging
from app.temporal.activities import (
    critique_activity,
    extract_activity,
    generate_activity,
    update_job_status_activity,
)
from app.temporal.workflows import CardWorkflow

log = get_logger(__name__)


async def main():
    setup_logging()
    pool().open()
    executor = ThreadPoolExecutor(max_workers=5)
    try:
        client = await Client.connect(settings.temporal_host)
        worker = Worker(
            client,
            task_queue=settings.temporal_task_queue,
            activity_executor=executor,
            workflows=[CardWorkflow],
            activities=[
                extract_activity,
                generate_activity,
                critique_activity,
                update_job_status_activity,
            ],
        )
        log.info("temporal_worker_started", task_queue=settings.temporal_task_queue)
        await worker.run()
    finally:
        executor.shutdown(wait=True)
        pool().close()


if __name__ == "__main__":
    asyncio.run(main())

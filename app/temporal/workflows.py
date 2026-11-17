import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities import (
        critique_activity,
        extract_activity,
        generate_activity,
        index_document_activity,
        process_document_activity,
        update_job_status_activity,
    )


@workflow.defn
class CardWorkflow:
    @workflow.run
    async def run(
            self,
            supplier_text: str,
            max_attempts: int = 3,
            job_id: str | None = None,
            confidence_threshold: float = 0.7,
    ) -> str:
        if job_id is not None:
            await workflow.execute_activity(
                update_job_status_activity,
                args=[job_id, "extracting"],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        try:
            facts_json = await workflow.execute_activity(
                extract_activity,
                supplier_text,
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except ActivityError:
            if job_id is not None:
                await workflow.execute_activity(
                    update_job_status_activity,
                    args=[job_id, "failed"],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            raise ApplicationError(
                "Не удалось извлечь факты из текста поставщика",
                non_retryable=True,
            )

        feedback_json = None

        for attempt in range(max_attempts):
            if job_id is not None:
                await workflow.execute_activity(
                    update_job_status_activity,
                    args=[job_id, "generating"],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )

            try:
                draft_json = await workflow.execute_activity(
                    generate_activity,
                    args=[facts_json, feedback_json],
                    start_to_close_timeout=timedelta(seconds=180),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except ActivityError as exc:
                if job_id is not None:
                    await workflow.execute_activity(
                        update_job_status_activity,
                        args=[job_id, "failed"],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                raise ApplicationError(
                    "Не удалось сгенерировать карточку товара",
                    non_retryable=True,
                ) from exc
            if job_id is not None:
                await workflow.execute_activity(
                    update_job_status_activity,
                    args=[job_id, "critiquing"],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )

            try:
                report_json = await workflow.execute_activity(
                    critique_activity,
                    args=[facts_json, draft_json],
                    start_to_close_timeout=timedelta(seconds=180),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except ActivityError as exc:
                if job_id is not None:
                    await workflow.execute_activity(
                        update_job_status_activity,
                        args=[job_id, "failed"],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                raise ApplicationError(
                    "Не удалось проверить карточку товара",
                    non_retryable=True,
                ) from exc

            report = json.loads(report_json)

            if report["verdict"] == "approve":
                draft = json.loads(draft_json)

                status = (
                    "waiting_for_human"
                    if draft["confidence"] < confidence_threshold
                    else "approved"
                )
                if job_id is not None:
                    await workflow.execute_activity(
                        update_job_status_activity,
                        args=[job_id, status, draft_json],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                return draft_json

            feedback_json = json.dumps(
                report["issues"], ensure_ascii=False
            )

@workflow.defn
class DocumentWorkflow:
    @workflow.run
    async def run(
        self,
        document_id: str,
        file_path: str,
    ) -> int:
        fragments_count = await workflow.execute_activity(
            process_document_activity,
            args=[document_id, file_path],
            start_to_close_timeout=timedelta(seconds=180),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        if fragments_count > 0:
            await workflow.execute_activity(
                index_document_activity,
                document_id,
                start_to_close_timeout=timedelta(seconds=600),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

        return fragments_count

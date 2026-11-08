import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities import (
        critique_activity,
        extract_activity,
        generate_activity,
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
    ) -> str:
        if job_id is not None:
            await workflow.execute_activity(
                update_job_status_activity,
                args=[job_id, "extracting"],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        facts_json = await workflow.execute_activity(
            extract_activity,
            supplier_text,
            start_to_close_timeout=timedelta(seconds=180),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
            ),
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

            draft_json = await workflow.execute_activity(
                generate_activity,
                args=[facts_json, feedback_json],
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                ),
            )
            if job_id is not None:
                await workflow.execute_activity(
                    update_job_status_activity,
                    args=[job_id, "critiquing"],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )

            report_json = await workflow.execute_activity(
                critique_activity,
                args=[facts_json, draft_json],
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                ),
            )

            report = json.loads(report_json)

            if report["verdict"] == "approve":
                if job_id is not None:
                    await workflow.execute_activity(
                        update_job_status_activity,
                        args=[job_id, "approved", draft_json],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                return draft_json

                feedback_json = json.dumps(report["issues"], ensure_ascii=False)
        if job_id is not None:
            await workflow.execute_activity(
                 update_job_status_activity,
                 args=[job_id, "rejected", draft_json],
                 start_to_close_timeout=timedelta(seconds=30),
                 retry_policy=RetryPolicy(maximum_attempts=3),
            )
            return draft_json

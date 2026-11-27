import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities import (
        critique_activity,
        critique_from_context_activity,
        extract_activity,
        generate_activity,
        generate_from_context_activity,
        index_document_activity,
        process_document_activity,
        retrieve_context_activity,
        update_job_status_activity,
        validate_sources_activity,
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

@workflow.defn
class DocumentCardWorkflow:
    """Генерация карточки товара по документам поставщика."""

    def __init__(self) -> None:
        self._human_decision: str | None = None
        self._waiting_for_human = False
        self._can_human_approve = False

    @workflow.signal
    async def submit_human_decision(self, decision: str) -> None:
        if not self._waiting_for_human:
            return

        if self._human_decision is not None:
            return

        if decision not in ("approve", "reject"):
            return

        if decision == "approve" and not self._can_human_approve:
            return

        self._human_decision = decision

    async def _set_job_status(
        self,
        job_id: str,
        status: str,
        result_json: str | None = None,
        error: str | None = None,
        attempts: int | None = None,
    ) -> None:
        await workflow.execute_activity(
            update_job_status_activity,
            args=[
                job_id,
                status,
                result_json,
                error,
                attempts,
            ],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

    async def _wait_for_human(
        self,
        job_id: str,
        draft_json: str,
        error: str,
        attempts: int,
        can_approve: bool,
    ) -> None:
        self._can_human_approve = can_approve
        self._waiting_for_human = True

        await self._set_job_status(
            job_id,
            "waiting_for_human",
            result_json=draft_json,
            error=error,
            attempts=attempts,
        )

        await workflow.wait_condition(
            lambda: self._human_decision is not None
        )

        self._waiting_for_human = False

        status = (
            "approved"
            if self._human_decision == "approve"
            else "rejected"
        )

        await self._set_job_status(
            job_id,
            status,
            result_json=draft_json,
            error="" if status == "approved" else error,
            attempts=attempts,
        )

    @workflow.run
    async def run(
        self,
        document_ids: list[str],
        product_hint: str | None,
        job_id: str,
    ) -> None:
        await self._set_job_status(job_id, "retrieving")

        try:
            context = await workflow.execute_activity(
                retrieve_context_activity,
                args=[document_ids, product_hint],
                start_to_close_timeout=timedelta(seconds=180),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except ActivityError as exc:
            await self._set_job_status(
                job_id,
                "failed",
                error="Не удалось получить RAG-контекст",
            )
            raise ApplicationError(
                "Не удалось получить RAG-контекст",
                non_retryable=True,
            ) from exc

        max_attempts = 3
        feedback: list[str] = []
        sources_valid = False

        for attempt in range(1, max_attempts + 1):
            sources_valid = False
            await self._set_job_status(
                job_id,
                "generating",
                attempts=attempt,
            )

            try:
                draft_json = await workflow.execute_activity(
                    generate_from_context_activity,
                    args=[
                        context["text"],
                        product_hint,
                        feedback or None,
                    ],
                    start_to_close_timeout=timedelta(seconds=180),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except ActivityError as exc:
                await self._set_job_status(
                    job_id,
                    "failed",
                    error="Не удалось сгенерировать карточку товара",
                )
                raise ApplicationError(
                    "Не удалось сгенерировать карточку товара",
                    non_retryable=True,
                ) from exc


            draft = json.loads(draft_json)

            await self._set_job_status(
                job_id,
                "validating_sources",
            )

            try:
                source_errors = await workflow.execute_activity(
                    validate_sources_activity,
                    args=[
                        draft["sources"],
                        context["fragment_ids"],
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except ActivityError as exc:
                await self._set_job_status(
                    job_id,
                    "failed",
                    error="Не удалось проверить источники карточки",
                )
                raise ApplicationError(
                    "Не удалось проверить источники карточки",
                    non_retryable=True,
                ) from exc

            if source_errors:
                feedback = source_errors

                if attempt < max_attempts:
                    await self._set_job_status(
                        job_id,
                        "regenerating",
                        error="; ".join(feedback),
                    )

                continue

            await self._set_job_status(
                job_id,
                "critiquing",
            )

            try:
                report_json = await workflow.execute_activity(
                    critique_from_context_activity,
                    args=[
                        context["text"],
                        draft_json,
                        product_hint,
                    ],
                    start_to_close_timeout=timedelta(seconds=180),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except ActivityError as exc:
                await self._set_job_status(
                    job_id,
                    "failed",
                    error="Не удалось проверить карточку критиком",
                )
                raise ApplicationError(
                    "Не удалось проверить карточку критиком",
                    non_retryable=True,
                ) from exc

            report = json.loads(report_json)

            await self._set_job_status(
                job_id,
                "validating_sources",
            )

            try:
                critic_source_errors = await workflow.execute_activity(
                    validate_sources_activity,
                    args=[
                        report["sources"],
                        context["fragment_ids"],
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except ActivityError as exc:
                await self._set_job_status(
                    job_id,
                    "failed",
                    error="Не удалось проверить источники критика",
                )
                raise ApplicationError(
                    "Не удалось проверить источники критика",
                    non_retryable=True,
                ) from exc

            if critic_source_errors:
                feedback = report["issues"] + critic_source_errors

                if attempt < max_attempts:
                    await self._set_job_status(
                        job_id,
                        "regenerating",
                        error="; ".join(feedback),
                    )

                continue
            sources_valid = True
            if report["verdict"] == "approve":
                if draft["confidence"] < 0.7:
                    await self._wait_for_human(
                        job_id=job_id,
                        draft_json=draft_json,
                        error="",
                        attempts=attempt,
                        can_approve=True,
                    )
                else:
                    await self._set_job_status(
                        job_id,
                        "approved",
                        result_json=draft_json,
                        error="",
                        attempts=attempt,
                    )

                return

            feedback = report["issues"]

            if attempt < max_attempts:
                await self._set_job_status(
                    job_id,
                    "regenerating",
                    error="; ".join(feedback),
                )

        await self._wait_for_human(
            job_id=job_id,
            draft_json=draft_json,
            error="; ".join(feedback),
            attempts=max_attempts,
            can_approve=sources_valid,
        )

from unittest.mock import AsyncMock, patch

import pytest
from temporalio.exceptions import ActivityError, ApplicationError

from app.temporal.workflows import CardWorkflow


@pytest.mark.anyio
async def test_extract_failure_updates_job_status():
    workflow = CardWorkflow()

    with patch(
        "app.temporal.workflows.workflow.execute_activity",
        new_callable=AsyncMock,
    ) as execute:
        execute.side_effect = [
            None,  # Статус extracting
            ActivityError(
                "Extract failed",
                scheduled_event_id=1,
                started_event_id=2,
                identity="test",
                activity_type="extract_activity",
                activity_id="test-extract-001",
                retry_state=None,
            ),
            None,  # Статус failed
        ]

        with pytest.raises(ApplicationError):
            await workflow.run("текст поставщика", job_id="test-job")

    assert execute.call_count == 3
    assert execute.call_args.kwargs["args"] == [
        "test-job",
        "failed",
    ]

@pytest.mark.anyio
async def test_generate_failure_updates_job_status():
    workflow = CardWorkflow()

    error = ActivityError(
        "Generate failed",
        scheduled_event_id=1,
        started_event_id=2,
        identity="test",
        activity_type="generate_activity",
        activity_id="test-generate-001",
        retry_state=None,
    )

    with patch(
        "app.temporal.workflows.workflow.execute_activity",
        new_callable=AsyncMock,
    ) as execute:
        execute.side_effect = [
            None,          # Статус extracting
            '{"product_name": "Товар", "characteristics": {}}',
            None,          # Статус generating
            error,         # Ошибка generate_activity
            None,          # Статус failed
        ]

        with pytest.raises(ApplicationError):
            await workflow.run("текст поставщика", job_id="test-job")

    assert execute.call_count == 5
    assert execute.call_args.kwargs["args"] == [
        "test-job",
        "failed",
    ]

@pytest.mark.anyio
async def test_critique_failure_updates_job_status():
    workflow = CardWorkflow()

    error = ActivityError(
        "Critique failed",
        scheduled_event_id=1,
        started_event_id=2,
        identity="test",
        activity_type="critique_activity",
        activity_id="test-critique-001",
        retry_state=None,
    )

    with patch(
        "app.temporal.workflows.workflow.execute_activity",
        new_callable=AsyncMock,
    ) as execute:
        execute.side_effect = [
            None,           # Статус extracting
            '{"product_name": "Товар", "characteristics": {}}',
            None,           # Статус generating
            '{"title": "Товар"}',
            None,           # Статус critiquing
            error,          # Ошибка critique_activity
            None,           # Статус failed
        ]

        with pytest.raises(ApplicationError):
            await workflow.run("текст поставщика", job_id="test-job")

    assert execute.call_count == 7
    assert execute.call_args.kwargs["args"] == [
        "test-job",
        "failed",
    ]

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import workflows


@pytest.fixture
def client():
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def test_lifespan(app):
        yield

    app.router.lifespan_context = test_lifespan

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.router.lifespan_context = original_lifespan

def test_approve_workflow(client, monkeypatch):
    job_id = "test-job-1"

    monkeypatch.setattr(
        workflows.jobs_repo,
        "get_job_by_id",
        Mock(return_value={"status": "waiting_for_human"}),
    )

    handle = Mock()
    handle.signal = AsyncMock()

    temporal_client = Mock()
    temporal_client.get_workflow_handle.return_value = handle

    monkeypatch.setattr(
        workflows,
        "_client",
        AsyncMock(return_value=temporal_client),
    )

    response = client.post(f"/workflows/{job_id}/approve")

    assert response.status_code == 202
    assert response.json() == {
        "id": job_id,
        "decision": "approve",
        "status": "accepted",
    }

    temporal_client.get_workflow_handle.assert_called_once_with(
        job_id,
    )

    handle.signal.assert_awaited_once_with(
        "submit_human_decision",
        "approve",
    )

def test_reject_workflow(client, monkeypatch):
    job_id = "test-job-2"

    monkeypatch.setattr(
        workflows.jobs_repo,
        "get_job_by_id",
        Mock(return_value={"status": "waiting_for_human"}),
    )

    handle = Mock()
    handle.signal = AsyncMock()

    temporal_client = Mock()
    temporal_client.get_workflow_handle.return_value = handle

    monkeypatch.setattr(
        workflows,
        "_client",
        AsyncMock(return_value=temporal_client),
    )

    response = client.post(f"/workflows/{job_id}/reject")

    assert response.status_code == 202
    assert response.json() == {
        "id": job_id,
        "decision": "reject",
        "status": "accepted",
    }

    temporal_client.get_workflow_handle.assert_called_once_with(
        job_id,
    )

    handle.signal.assert_awaited_once_with(
        "submit_human_decision",
        "reject",
    )

def test_workflow_not_found(client, monkeypatch):
    job_id = "nonexistent-job"

    monkeypatch.setattr(
        workflows.jobs_repo,
        "get_job_by_id",
        Mock(return_value=None),
    )

    temporal_client_mock = AsyncMock()

    monkeypatch.setattr(
        workflows,
        "_client",
        temporal_client_mock,
    )

    response = client.post(f"/workflows/{job_id}/approve")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Job not found",
    }

    temporal_client_mock.assert_not_awaited()

@pytest.mark.parametrize(
    "job_status",
    ["processing", "approved"],
)
def test_workflow_invalid_status(client, monkeypatch, job_status):
    job_id = "test-job-3"

    monkeypatch.setattr(
        workflows.jobs_repo,
        "get_job_by_id",
        Mock(return_value={"status": job_status}),
    )

    temporal_client_mock = AsyncMock()

    monkeypatch.setattr(
        workflows,
        "_client",
        temporal_client_mock,
    )

    response = client.post(f"/workflows/{job_id}/approve")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Job is not waiting for human decision",
    }

    temporal_client_mock.assert_not_awaited()

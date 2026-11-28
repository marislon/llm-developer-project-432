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

def test_workflow_status(client, monkeypatch):
    job_id = "test-status-job"

    get_job_mock = Mock(
        return_value={
            "status": "generating",
            "attempts": 1,
            "error": None,
        }
    )

    monkeypatch.setattr(
        workflows.jobs_repo,
        "get_job_by_id",
        get_job_mock,
    )

    response = client.get(f"/workflows/{job_id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": job_id,
        "status": "generating",
        "attempts": 1,
        "error": None,
    }

    get_job_mock.assert_called_once_with(job_id)


def test_workflow_status_not_found(client, monkeypatch):
    job_id = "nonexistent-status-job"

    get_job_mock = Mock(return_value=None)

    monkeypatch.setattr(
        workflows.jobs_repo,
        "get_job_by_id",
        get_job_mock,
    )

    response = client.get(f"/workflows/{job_id}")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Job not found",
    }

    get_job_mock.assert_called_once_with(job_id)

@pytest.mark.parametrize(
    "job_status",
    ["waiting_for_human", "approved"],
)
def test_workflow_result(client, monkeypatch, job_status):
    job_id = "test-result-job"

    result = {
        "title": "Электрический чайник",
        "confidence": 0.6,
        "missing_fields": ["Гарантия"],
        "sources": [{"fragment_id": "frag-1"}],
    }

    monkeypatch.setattr(
        workflows.jobs_repo,
        "get_job_by_id",
        Mock(return_value={
            "status": job_status,
            "result": result,
        }),
    )

    response = client.get(f"/workflows/{job_id}/result")

    assert response.status_code == 200
    assert response.json() == {
        "id": job_id,
        "status": job_status,
        "result": result,
    }


def test_workflow_result_not_found(client, monkeypatch):
    monkeypatch.setattr(
        workflows.jobs_repo,
        "get_job_by_id",
        Mock(return_value=None),
    )

    response = client.get("/workflows/nonexistent-job/result")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Job not found",
    }


@pytest.mark.parametrize(
    "job_status",
    [
        "pending",
        "retrieving",
        "generating",
        "validating_sources",
        "critiquing",
        "regenerating",
        "rejected",
        "failed",
    ],
)
def test_workflow_result_unavailable(
    client, monkeypatch, job_status
):
    monkeypatch.setattr(
        workflows.jobs_repo,
        "get_job_by_id",
        Mock(return_value={
            "status": job_status,
            "result": {"title": "Электрический чайник"},
        }),
    )

    response = client.get("/workflows/test-job/result")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Job result is not available",
    }


@pytest.mark.parametrize(
    "job_status",
    ["waiting_for_human", "approved"],
)
def test_workflow_result_missing(
    client, monkeypatch, job_status
):
    monkeypatch.setattr(
        workflows.jobs_repo,
        "get_job_by_id",
        Mock(return_value={
            "status": job_status,
            "result": None,
        }),
    )

    response = client.get("/workflows/test-job/result")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Job result is not available",
    }

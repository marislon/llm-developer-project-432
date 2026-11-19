from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.schemas import CritiqueReport
from app.services.context_builder import ContextResult
from app.services.pipeline import run_rag_pipeline


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_rag_pipeline_approved():
    conn = Mock()
    draft = Mock()

    context_text = "Мощность чайника 2200 Вт"

    context = ContextResult(
        text=context_text,
        fragment_ids=["frag-1"],
        size=len(context_text),
    )

    report = CritiqueReport(
        verdict="approve",
        issues=[],
    )

    with (
        patch(
            "app.services.pipeline.retrieve_context",
            return_value=context,
        ) as mock_retrieve,
        patch(
            "app.services.pipeline.generate_from_context",
            new_callable=AsyncMock,
            return_value=draft,
        ) as mock_generate,
        patch(
            "app.services.pipeline.critique_from_context",
            new_callable=AsyncMock,
            return_value=report,
        ) as mock_critique,
    ):
        result = await run_rag_pipeline(
            conn,
            document_ids=["doc-1"],
            product_hint="Чайник",
        )

    assert result == (draft, 1, "approved")

    mock_retrieve.assert_called_once_with(
        conn, ["doc-1"], "Чайник"
    )

    mock_generate.assert_awaited_once_with(
        context=context_text,
        product_hint="Чайник",
        feedback=None,
    )

    mock_critique.assert_awaited_once_with(
        context=context_text,
        draft=draft,
        product_hint="Чайник",
    )

@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_rag_pipeline_regenerate():
    conn = Mock()
    first_draft = Mock()
    second_draft = Mock()

    context_text = "Мощность чайника 2200 Вт"

    context = ContextResult(
        text=context_text,
        fragment_ids=["frag-1"],
        size=len(context_text),
    )

    issues = ["Мощность не соответствует источнику"]

    reports = [
        CritiqueReport(
            verdict="regenerate",
            issues=issues,
        ),
        CritiqueReport(
            verdict="approve",
            issues=[],
        ),
    ]

    with (
        patch(
            "app.services.pipeline.retrieve_context",
            return_value=context,
        ) as mock_retrieve,
        patch(
            "app.services.pipeline.generate_from_context",
            new_callable=AsyncMock,
            side_effect=[first_draft, second_draft],
        ) as mock_generate,
        patch(
            "app.services.pipeline.critique_from_context",
            new_callable=AsyncMock,
            side_effect=reports,
        ) as mock_critique,
    ):
        result = await run_rag_pipeline(
            conn,
            document_ids=["doc-1"],
            product_hint="Чайник",
        )

    assert result == (second_draft, 2, "approved")

    mock_retrieve.assert_called_once()

    assert mock_generate.await_count == 2
    assert mock_critique.await_count == 2

    mock_generate.assert_awaited_with(
        context=context_text,
        product_hint="Чайник",
        feedback=issues,
    )

@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_rag_pipeline_rejected():
    conn = Mock()
    draft = Mock()

    context_text = "Мощность чайника 2200 Вт"

    context = ContextResult(
        text=context_text,
        fragment_ids=["frag-1"],
        size=len(context_text),
    )

    report = CritiqueReport(
        verdict="regenerate",
        issues=["Недостоверные характеристики"],
    )

    with (
        patch(
            "app.services.pipeline.retrieve_context",
            return_value=context,
        ) as mock_retrieve,
        patch(
            "app.services.pipeline.generate_from_context",
            new_callable=AsyncMock,
            return_value=draft,
        ) as mock_generate,
        patch(
            "app.services.pipeline.critique_from_context",
            new_callable=AsyncMock,
            return_value=report,
        ) as mock_critique,
    ):
        result = await run_rag_pipeline(
            conn,
            document_ids=["doc-1"],
            product_hint="Чайник",
        )

    assert result == (draft, 3, "rejected")

    mock_retrieve.assert_called_once()

    assert mock_generate.await_count == 3
    assert mock_critique.await_count == 3

@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_rag_pipeline_empty_context():
    conn = Mock()

    context = ContextResult(
        text="",
        fragment_ids=[],
        size=0,
    )

    with (
        patch(
            "app.services.pipeline.retrieve_context",
            return_value=context,
        ) as mock_retrieve,
        patch(
            "app.services.pipeline.generate_from_context",
            new_callable=AsyncMock,
        ) as mock_generate,
        patch(
            "app.services.pipeline.critique_from_context",
            new_callable=AsyncMock,
        ) as mock_critique,
        pytest.raises(
            ValueError,
            match="Не найден релевантный контекст",
        ),
    ):
        await run_rag_pipeline(
            conn,
            document_ids=["doc-1"],
            product_hint="Чайник",
        )

    mock_retrieve.assert_called_once()
    mock_generate.assert_not_called()
    mock_critique.assert_not_called()

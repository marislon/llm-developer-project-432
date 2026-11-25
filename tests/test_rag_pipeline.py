from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.schemas import CritiqueReport, SourceReference
from app.services.context_builder import ContextResult
from app.services.pipeline import run_rag_pipeline


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_rag_pipeline_approved():
    conn = Mock()
    draft = Mock(
        sources=[SourceReference(fragment_id="frag-1")]
    )

    context_text = "Мощность чайника 2200 Вт"

    context = ContextResult(
        text=context_text,
        fragment_ids=["frag-1"],
        size=len(context_text),
    )

    report = CritiqueReport(
        verdict="approve",
        issues=[],
        sources=[SourceReference(fragment_id="frag-1")],
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
        ) as mock_critique, \
        patch(
            "app.services.validation.get_existing_fragment_ids",
            return_value={"frag-1"},
        ),
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
    first_draft = Mock(
        sources=[SourceReference(fragment_id="frag-1")]
    )
    second_draft = Mock(
        sources=[SourceReference(fragment_id="frag-1")]
    )

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
            sources=[SourceReference(fragment_id="frag-1")],
        ),
        CritiqueReport(
            verdict="approve",
            issues=[],
            sources=[SourceReference(fragment_id="frag-1")],
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
        patch(
            "app.services.validation.get_existing_fragment_ids",
            return_value={"frag-1"},
        ),
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
    draft = Mock(
        sources=[SourceReference(fragment_id="frag-1")]
    )

    context_text = "Мощность чайника 2200 Вт"

    context = ContextResult(
        text=context_text,
        fragment_ids=["frag-1"],
        size=len(context_text),
    )

    report = CritiqueReport(
        verdict="regenerate",
        issues=["Недостоверные характеристики"],
        sources=[SourceReference(fragment_id="frag-1")],
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
        patch(
            "app.services.validation.get_existing_fragment_ids",
            return_value={"frag-1"},
        ),
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
        patch(
            "app.services.validation.get_existing_fragment_ids",
            return_value={"frag-1"},
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

@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_rag_pipeline_fake_generator_source():
    conn = Mock()

    first_draft = Mock(
        sources=[SourceReference(fragment_id="fake-id")]
    )
    second_draft = Mock(
        sources=[SourceReference(fragment_id="frag-1")]
    )

    context_text = "Мощность чайника 2200 Вт"

    context = ContextResult(
        text=context_text,
        fragment_ids=["frag-1"],
        size=len(context_text),
    )

    report = CritiqueReport(
        verdict="approve",
        issues=[],
        sources=[SourceReference(fragment_id="frag-1")],
    )

    with (
        patch(
            "app.services.pipeline.retrieve_context",
            return_value=context,
        ),
        patch(
            "app.services.pipeline.generate_from_context",
            new_callable=AsyncMock,
            side_effect=[first_draft, second_draft],
        ) as mock_generate,
        patch(
            "app.services.pipeline.critique_from_context",
            new_callable=AsyncMock,
            return_value=report,
        ) as mock_critique,
        patch(
            "app.services.validation.get_existing_fragment_ids",
            side_effect=[set(), {"frag-1"}, {"frag-1"}],
        ),
    ):
        result = await run_rag_pipeline(
            conn,
            document_ids=["doc-1"],
            product_hint="Чайник",
        )

    assert result == (second_draft, 2, "approved")
    assert mock_generate.await_count == 2

    mock_critique.assert_awaited_once_with(
        context=context_text,
        draft=second_draft,
        product_hint="Чайник",
    )

    mock_generate.assert_awaited_with(
        context=context_text,
        product_hint="Чайник",
        feedback=[
            "Фрагмент fake-id не существует в БД"
        ],
    )

@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_rag_pipeline_invalid_critic_source():
    conn = Mock()

    draft = Mock(
        sources=[SourceReference(fragment_id="frag-1")]
    )

    context_text = "Мощность чайника 2200 Вт"

    context = ContextResult(
        text=context_text,
        fragment_ids=["frag-1"],
        size=len(context_text),
    )

    reports = [
        CritiqueReport(
            verdict="approve",
            issues=[],
            sources=[
                SourceReference(fragment_id="frag-2")
            ],
        ),
        CritiqueReport(
            verdict="approve",
            issues=[],
            sources=[
                SourceReference(fragment_id="frag-1")
            ],
        ),
    ]

    with (
        patch(
            "app.services.pipeline.retrieve_context",
            return_value=context,
        ),
        patch(
            "app.services.pipeline.generate_from_context",
            new_callable=AsyncMock,
            return_value=draft,
        ) as mock_generate,
        patch(
            "app.services.pipeline.critique_from_context",
            new_callable=AsyncMock,
            side_effect=reports,
        ) as mock_critique,
        patch(
            "app.services.validation.get_existing_fragment_ids",
            side_effect=[
                {"frag-1"},
                {"frag-2"},
                {"frag-1"},
                {"frag-1"},
            ],
        ),
    ):
        result = await run_rag_pipeline(
            conn,
            document_ids=["doc-1"],
            product_hint="Чайник",
        )

    assert result == (draft, 2, "approved")
    assert mock_generate.await_count == 2
    assert mock_critique.await_count == 2

    mock_generate.assert_awaited_with(
        context=context_text,
        product_hint="Чайник",
        feedback=[
            "Фрагмент frag-2 отсутствует в контексте"
        ],
    )
@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_rag_pipeline_persistent_invalid_sources():
    conn = Mock()

    draft = Mock(
        sources=[SourceReference(fragment_id="fake-id")]
    )

    context_text = "Мощность чайника 2200 Вт"

    context = ContextResult(
        text=context_text,
        fragment_ids=["frag-1"],
        size=len(context_text),
    )

    with (
        patch(
            "app.services.pipeline.retrieve_context",
            return_value=context,
        ),
        patch(
            "app.services.pipeline.generate_from_context",
            new_callable=AsyncMock,
            return_value=draft,
        ) as mock_generate,
        patch(
            "app.services.pipeline.critique_from_context",
            new_callable=AsyncMock,
        ) as mock_critique,
        patch(
            "app.services.validation.get_existing_fragment_ids",
            return_value=set(),
        ) as mock_existing,
    ):
        result = await run_rag_pipeline(
            conn,
            document_ids=["doc-1"],
            product_hint="Чайник",
        )

    assert result == (draft, 3, "rejected")
    assert mock_generate.await_count == 3
    assert mock_existing.call_count == 3

    mock_critique.assert_not_called()

    mock_generate.assert_awaited_with(
        context=context_text,
        product_hint="Чайник",
        feedback=[
            "Фрагмент fake-id не существует в БД"
        ],
    )

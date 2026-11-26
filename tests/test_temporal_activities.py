from unittest.mock import AsyncMock

import pytest
from temporalio.exceptions import ApplicationError

from app.repositories import jobs as jobs_repo
from app.schemas import CardDraft, CritiqueReport, SeoBlock, SourceReference
from app.services.context_builder import ContextResult
from app.temporal import activities
from app.temporal.activities import update_job_status_activity


def test_update_job_status_activity(db_pool):
    job_id, _ = jobs_repo.create_job_with_connection(
        {"supplier_text": "Тест обновления через Activity"},
        None,
    )

    try:
        # Проверка обратной совместимости.
        update_job_status_activity(
            job_id,
            "extracting",
        )

        job = jobs_repo.get_job_by_id(job_id)

        assert job is not None
        assert job["status"] == "extracting"
        assert job["attempts"] == 0
        assert job["error"] is None

        # Сохранение номера попытки.
        update_job_status_activity(
            job_id,
            "generating",
            attempts=2,
        )

        job = jobs_repo.get_job_by_id(job_id)

        assert job is not None
        assert job["status"] == "generating"
        assert job["attempts"] == 2

        # Сохранение ошибки.
        update_job_status_activity(
            job_id,
            "regenerating",
            error="Недостоверная ссылка на источник",
        )

        job = jobs_repo.get_job_by_id(job_id)

        assert job is not None
        assert job["status"] == "regenerating"
        assert job["attempts"] == 2
        assert job["error"] == "Недостоверная ссылка на источник"

    finally:
        with db_pool.connection() as conn:
            conn.execute(
                "DELETE FROM jobs WHERE id = %s",
                (job_id,),
            )
def test_retrieve_context_activity(db_pool, monkeypatch):
    expected_context = ContextResult(
        text="Мощность чайника: 2200 Вт",
        fragment_ids=["fragment-1"],
        size=25,
    )

    def fake_retrieve_context(conn, document_ids, product_hint):
        assert document_ids == ["document-1"]
        assert product_hint == "Чайник"
        return expected_context

    monkeypatch.setattr(
        activities.retrieval,
        "retrieve_context",
        fake_retrieve_context,
    )

    result = activities.retrieve_context_activity(
        ["document-1"],
        "Чайник",
    )

    assert result == {
        "text": expected_context.text,
        "fragment_ids": expected_context.fragment_ids,
        "size": expected_context.size,
    }

def test_retrieve_context_activity_empty_context(db_pool, monkeypatch):
    def fake_retrieve_context(conn, document_ids, product_hint):
        return ContextResult(
            text="",
            fragment_ids=[],
            size=0,
        )

    monkeypatch.setattr(
        activities.retrieval,
        "retrieve_context",
        fake_retrieve_context,
    )

    with pytest.raises(ApplicationError) as exc_info:
        activities.retrieve_context_activity(
            ["document-1"],
            "Чайник",
        )

    assert exc_info.value.message == "Не найден релевантный контекст"
    assert exc_info.value.non_retryable is True

@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
@pytest.mark.parametrize(
    "feedback",
    [
        None,
        ["Мощность не соответствует источнику"],
    ],
    ids=["initial", "regeneration"],
)
async def test_generate_from_context_activity(
    monkeypatch,
    feedback,
):
    expected_draft = CardDraft(
        title="Электрический чайник",
        description="Электрический чайник мощностью 2200 Вт.",
        characteristics={"Мощность": "2200 Вт"},
        benefits=["Быстрый нагрев воды"],
        missing_fields=["Объём", "Гарантия"],
        confidence=0.8,
        seo=SeoBlock(
            meta_title="Электрический чайник",
            meta_description="Чайник мощностью 2200 Вт",
        ),
        sources=[
            SourceReference(fragment_id="frag-1"),
        ],
    )

    mock_generate = AsyncMock(
        return_value=expected_draft,
    )

    monkeypatch.setattr(
        activities.steps,
        "generate_from_context",
        mock_generate,
    )

    context = "Мощность чайника 2200 Вт"

    result = await activities.generate_from_context_activity(
        context,
        "Чайник",
        feedback,
    )

    mock_generate.assert_awaited_once_with(
        context=context,
        product_hint="Чайник",
        feedback=feedback,
    )

    assert isinstance(result, str)

    restored_draft = CardDraft.model_validate_json(result)

    assert restored_draft == expected_draft

@pytest.mark.parametrize(
    "sources, expected_errors",
    [
        (
            [{"fragment_id": "frag-1"}],
            [],
        ),
        (
            [{"fragment_id": "fake-id"}],
            ["Фрагмент fake-id не существует в БД"],
        ),
        (
            [],
            ["Отсутствуют ссылки на источники"],
        ),
    ],
    ids=["valid", "invalid", "empty"],
)
def test_validate_sources_activity(
    db_pool,
    monkeypatch,
    sources,
    expected_errors,
):
    context_fragment_ids = ["frag-1"]

    def fake_validate_sources(
        conn,
        source_references,
        fragment_ids,
    ):
        assert source_references == [
            SourceReference.model_validate(source)
            for source in sources
        ]

        assert fragment_ids == context_fragment_ids

        return expected_errors

    monkeypatch.setattr(
        activities.validation,
        "validate_sources",
        fake_validate_sources,
    )

    result = activities.validate_sources_activity(
        sources,
        context_fragment_ids,
    )

    assert result == expected_errors

@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
@pytest.mark.parametrize(
    "verdict, issues",
    [
        ("approve", []),
        ("regenerate", ["Мощность не соответствует источнику"]),
    ],
    ids=["approve", "regenerate"],
)
async def test_critique_from_context_activity(
    monkeypatch,
    verdict,
    issues,
):
    context = "Мощность чайника: 2200 Вт"
    product_hint = "Электрический чайник"

    draft = CardDraft(
        title="Электрический чайник",
        description="Чайник мощностью 2200 Вт.",
        characteristics={"Мощность": "2200 Вт"},
        benefits=["Быстрый нагрев"],
        missing_fields=["Объём", "Гарантия"],
        confidence=0.8,
        sources=[
            SourceReference(fragment_id="frag-1"),
        ],
    )

    expected_report = CritiqueReport(
        verdict=verdict,
        issues=issues,
        sources=[
            SourceReference(fragment_id="frag-1"),
        ],
    )

    mock_critique = AsyncMock(return_value=expected_report)

    monkeypatch.setattr(
        activities.steps,
        "critique_from_context",
        mock_critique,
    )

    result = await activities.critique_from_context_activity(
        context=context,
        draft_json=draft.model_dump_json(),
        product_hint=product_hint,
    )

    mock_critique.assert_awaited_once_with(
        context=context,
        draft=draft,
        product_hint=product_hint,
    )

    assert isinstance(result, str)

    restored_report = CritiqueReport.model_validate_json(result)

    assert restored_report == expected_report

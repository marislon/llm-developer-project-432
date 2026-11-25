import psycopg

from app.repositories.fragments import get_existing_fragment_ids
from app.schemas import SourceReference


def remove_duplicate_missing_fields(characteristics, missing_fields):
    known_fields = {name.strip().casefold() for name in characteristics}

    return [
        field
        for field in missing_fields
        if field.strip().casefold() not in known_fields
    ]

def preserve_valid_fields(
    original: dict,
    corrected: dict,
    invalid_fields: set[str],
) -> dict:
    """Сохранить исходные значения полей, не требующих исправления."""
    result = corrected.copy()

    for field, value in original.items():
        if field not in invalid_fields:
            result[field] = value

    return result

from pydantic import ValidationError


def get_invalid_fields(error: ValidationError) -> set[str]:
    """Получить имена полей верхнего уровня с ошибками валидации."""
    return {
        str(item["loc"][0])
        for item in error.errors()
        if item["loc"]
    }
def validate_sources(
    conn: psycopg.Connection,
    sources: list[SourceReference],
    context_fragment_ids: list[str],
) -> list[str]:
    """Проверить существование источников и их принадлежность контексту."""
    if not sources:
        return ["Отсутствуют ссылки на источники"]

    errors: list[str] = []
    fragment_ids: set[str] = set()

    for index, source in enumerate(sources, start=1):
        if not source.fragment_id:
            errors.append(
                f"Источник {index}: отсутствует fragment_id"
            )
        else:
            fragment_ids.add(source.fragment_id)

    existing_ids = get_existing_fragment_ids(
        conn, sorted(fragment_ids)
    )
    context_ids = set(context_fragment_ids)

    for fragment_id in sorted(fragment_ids):
        if fragment_id not in existing_ids:
            errors.append(
                f"Фрагмент {fragment_id} не существует в БД"
            )
        elif fragment_id not in context_ids:
            errors.append(
                f"Фрагмент {fragment_id} отсутствует в контексте"
            )

    return errors

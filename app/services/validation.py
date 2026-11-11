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

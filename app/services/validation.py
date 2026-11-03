def remove_duplicate_missing_fields(characteristics, missing_fields):
    known_fields = {name.strip().casefold() for name in characteristics}

    return [
        field
        for field in missing_fields
        if field.strip().casefold() not in known_fields
    ]
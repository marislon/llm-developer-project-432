
import re


def normalize_spaces(text: str) -> str:
    return re.sub(r"[^\S\n]+", " ", text)


def normalize_ligatures(text: str) -> str:
    replacements = {
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬀ": "ff",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
    }

    for ligature, replacement in replacements.items():
        text = text.replace(ligature, replacement)

    return text


def normalize_hyphenation(text: str) -> str:
    return re.sub(
        r"(?<=[А-Яа-яЁёA-Za-z])-\s*\n\s*(?=[А-Яа-яЁёA-Za-z])",
        "",
        text,
    )


def find_repeated_lines(pages: list[str]) -> set[str]:
    counts = {}

    for page in pages:
        lines = [
            line.strip()
            for line in page.splitlines()
            if line.strip()
        ]

        candidates = {
            normalize_page_number(line)
            for line in lines[:2] + lines[-2:]
        }

        for line in candidates:
            counts[line] = counts.get(line, 0) + 1

    return {
        line
        for line, count in counts.items()
        if count > 1
    }



def remove_repeated_lines(
    text: str,
    repeated_lines: set[str],
) -> str:
    lines = text.splitlines()

    nonempty_indices = [
        i for i, line in enumerate(lines)
        if line.strip()
    ]

    candidates = set(
        nonempty_indices[:2] + nonempty_indices[-2:]
    )

    result = [
        line
        for i, line in enumerate(lines)
        if not (
            i in candidates
            and normalize_page_number(line.strip()) in repeated_lines

        )
    ]

    return "\n".join(result)


def normalize_text(text: str) -> str:
    text = normalize_ligatures(text)
    text = normalize_hyphenation(text)
    text = normalize_spaces(text)
    return text


def normalize_page_number(line: str) -> str:
    return re.sub(
        r"\bстр\.\s*\d+\b",
        "стр. #",
        line,
    )

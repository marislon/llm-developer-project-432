
from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    document_id: int
    page: int
    section: str
    chunk_index: int




def split_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[str]:
    if chunk_size <= 0 or not 0 <= overlap < chunk_size:
        raise ValueError("Некорректные размеры фрагмента и перекрытия")

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            boundary = find_word_boundary(text, end)
            if boundary > start:
                end = boundary

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        next_start = max(start + 1, end - overlap)
        start = find_word_boundary(text, next_start)

    return chunks


def find_word_boundary(text: str, position: int) -> int:
    if position >= len(text):
        return len(text)

    boundary = max(
        text.rfind(" ", 0, position + 1),
        text.rfind("\n", 0, position + 1),
        text.rfind("\t", 0, position + 1),
    )

    if boundary == -1:
        return position

    return boundary + 1


def create_table_chunk(
    text: str,
    document_id: int,
    page: int,
    section: str,
    chunk_index: int,
) -> Chunk:
    return Chunk(
        text=text,
        document_id=document_id,
        page=page,
        section=section,
        chunk_index=chunk_index,
    )


def create_text_chunks(
    text: str,
    document_id: int,
    page: int,
    section: str,
    chunk_size: int = 500,
    overlap: int = 50,
    start_index: int = 0,
) -> list[Chunk]:
    parts = split_text(text, chunk_size, overlap)

    return [
        Chunk(
            text=part,
            document_id=document_id,
            page=page,
            section=section,
            chunk_index=start_index + i,
        )
        for i, part in enumerate(parts)
    ]

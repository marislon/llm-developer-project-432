import hashlib
from pathlib import Path
from uuid import uuid4

from app.core.db import connection
from app.parsers.docx import parse_docx
from app.parsers.pdf import parse_pdf
from app.parsers.xlsx import parse_xlsx
from app.repositories.documents import update_document_status
from app.repositories.fragments import create_fragment
from app.services.chunking import create_table_chunk, create_text_chunks
from app.services.normalizer import (
    find_repeated_lines,
    normalize_text,
    remove_repeated_lines,
)


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def parse_document(file_path: str):
    extension = Path(file_path).suffix.lower()

    if extension == ".pdf":
        return parse_pdf(file_path)
    if extension == ".docx":
        return parse_docx(file_path)
    if extension == ".xlsx":
        return parse_xlsx(file_path)
    raise ValueError(
        f"Неподдерживаемый формат документа: {extension}"
    )

def prepare_text(text: str) -> str:
    return normalize_text(text)

def prepare_chunks(
    text: str,
    document_id: str,
    page: int,
    section: str,
    start_index: int = 0,
):
    normalized_text = prepare_text(text)

    return create_text_chunks(
        text=normalized_text,
        document_id=document_id,
        page=page,
        section=section,
        start_index=start_index,
    )
def save_chunks(conn, chunks):
    for chunk in chunks:
        create_fragment(
            conn=conn,
            fragment_id=str(uuid4()),
            document_id=chunk.document_id,
            ord=chunk.chunk_index,
            page=chunk.page,
            section=chunk.section,
            text=chunk.text,
        )
def process_document(document_id: str, file_path: str):
    with connection() as conn:
        update_document_status(conn, document_id, "parsing")
    blocks = parse_document(file_path)
    if (
        Path(file_path).suffix.lower() == ".pdf"
        and not any(block.text.strip() for block in blocks)
    ):
        with connection() as conn:
            update_document_status(
                conn,
                document_id,
                "rejected",
                error="PDF не содержит извлекаемого текста (возможно, скан)",
            )
        return 0
    repeated_lines = set()

    if Path(file_path).suffix.lower() == ".pdf":
        repeated_lines = find_repeated_lines(
            [block.text for block in blocks]
        )
    all_chunks = []
    for block in blocks:
        text = remove_repeated_lines(
            block.text, repeated_lines
        )
        if Path(file_path).suffix.lower() == ".xlsx" or (
            getattr(block, "section", "") == "table"
        ):
            chunks = [
                create_table_chunk(
                    text=prepare_text(text),
                    document_id=document_id,
                    page=block.page,
                    section=getattr(block, "section", "table"),
                    chunk_index=len(all_chunks),
                )
            ] if prepare_text(text) else []
        else:
            chunks = prepare_chunks(
                text=text,
                document_id=document_id,
                page=block.page,
                section=getattr(block, "section", "page"),
                start_index=len(all_chunks),
            )
        all_chunks.extend(chunks)
    with connection() as conn:
        save_chunks(conn, all_chunks)
        update_document_status(conn, document_id, "embedding")
    return len(all_chunks)

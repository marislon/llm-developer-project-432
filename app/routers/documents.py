from fastapi import APIRouter, File, HTTPException, UploadFile
from pathlib import Path

import shutil
from uuid import uuid4
from app.core.db import connection
from app.repositories import documents as documents_repo

import hashlib
from psycopg.errors import UniqueViolation

router = APIRouter(prefix="/documents", tags=["documents"])
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx"}
MAX_FILE_SIZE = 20 * 1024 * 1024

def validate_extension(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS

def validate_file_size(size: int) -> bool:
    return 0 < size <= MAX_FILE_SIZE

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.post("", status_code=202)
async def upload_document(file: UploadFile = File(...)):
    if not validate_extension(file.filename or ""):
        raise HTTPException(
            status_code=400,
            detail="Недопустимое расширение файла",
        )

    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)

    if not validate_file_size(size):
        raise HTTPException(
            status_code=400,
            detail="Файл пустой или превышает допустимый размер",
        )
    sha256 = hashlib.sha256()

    for chunk in iter(lambda: file.file.read(8192), b""):
        sha256.update(chunk)

    file_hash = sha256.hexdigest()
    file.file.seek(0)
    with connection() as conn:
        existing_id = documents_repo.get_document_by_hash(
            conn, file_hash
        )

    if existing_id is not None:
        return {
            "document_id": existing_id,
            "status": "existing",
        }
    document_id = str(uuid4())
    file_path = UPLOAD_DIR / f"{document_id}{Path(file.filename).suffix.lower()}"

    with file_path.open("wb") as destination:
        shutil.copyfileobj(file.file, destination)
    try:
        with connection() as conn:
            documents_repo.create_document(
                conn,
                document_id=document_id,
                filename=file.filename,
                ext=Path(file.filename).suffix.lower(),
                size_bytes=size,
                sha256=file_hash,
                storage_path=str(file_path),
            )
            conn.commit()

    except UniqueViolation:
        with connection() as conn:
            existing_id = documents_repo.get_document_by_hash(
                conn, file_hash
            )

        if existing_id is None:
            raise

        file_path.unlink(missing_ok=True)

        return {
            "document_id": existing_id,
            "status": "existing",
        }

    return {
        "document_id": document_id,
        "status": "new",
    }

@router.get("/{document_id}")
def get_document_status(document_id: str):
    with connection() as conn:
        document = documents_repo.get_document(
            conn, document_id
        )

        if document is None:
            raise HTTPException(
                status_code=404,
                detail="Документ не найден",
            )

        chunks_count = documents_repo.count_fragments(
            conn, document_id
        )

    return {
        **document,
        "chunks_count": chunks_count,
    }

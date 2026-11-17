from threading import Lock

from sentence_transformers import SentenceTransformer

from app.core.config import settings

_model: SentenceTransformer | None = None
_model_lock = Lock()


def get_embedding_model() -> SentenceTransformer:
    global _model

    with _model_lock:
        if _model is None:
            _model = SentenceTransformer(
                settings.embedding_model,
                device=settings.embedding_device,
            )

        return _model

def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    model = get_embedding_model()

    embeddings = model.encode_document(
        texts,
        batch_size=settings.embedding_batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    if embeddings.shape[1] != settings.embedding_dimension:
        raise ValueError("Unexpected embedding dimension")

    return embeddings.tolist()

def embed_query(text: str) -> list[float]:
    model = get_embedding_model()

    embedding = model.encode_query(
        text,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    if embedding.shape[0] != settings.embedding_dimension:
        raise ValueError("Unexpected embedding dimension")

    return embedding.tolist()

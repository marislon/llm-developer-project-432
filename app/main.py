from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.core.db import connection, pool
from app.core.logging import setup_logging
from app.routers import cards, jobs, workflows


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    db_pool = pool()
    db_pool.open()
    try:
        db_pool.wait()
        yield
    finally:
        db_pool.close()


app = FastAPI(title="card-pipeline", lifespan=lifespan)
app.include_router(cards.router)
app.include_router(jobs.router)
app.include_router(workflows.router)


@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    try:
        with connection() as conn:
            conn.execute("SELECT 1")

            row = conn.execute(
                "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()

            if row is None:
                raise RuntimeError("Extension vector is not installed")

        return {"status": "ready", "vector": "active"}

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Database is not ready"
        ) from exc

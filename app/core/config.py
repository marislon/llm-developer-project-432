from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen2.5:3b"

    database_url: str = "postgresql://card:card@127.0.0.1:5435/card"
    rabbitmq_url: str = "amqp://card:card@localhost:5672//"

    temporal_host: str = "localhost:7233"
    temporal_task_queue: str = "card-queue"

    llm_timeout_s: float = 120.0
    llm_max_retries: int = 3
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    embedding_model: str = "google/embeddinggemma-300m"
    embedding_dimension: int = Field(default=768, gt=0)
    embedding_device: str = "cpu"
    embedding_batch_size: int = Field(default=32, gt=0)
    search_similarity_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
settings = Settings()

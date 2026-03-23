from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_SECRET_KEY: str
    APP_DEBUG: bool = False
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:3000"

    # Database
    DATABASE_URL: str
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "lexai"
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # AWS
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str = "us-east-1"
    AWS_S3_BUCKET: str
    AWS_S3_REGION: str = "us-east-1"

    # Bedrock – Claude
    BEDROCK_MODEL_ID: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    BEDROCK_MAX_TOKENS: int = 8192
    BEDROCK_TEMPERATURE: float = 0.1

    # Bedrock – Titan Embeddings
    BEDROCK_EMBEDDING_MODEL_ID: str = "amazon.titan-embed-text-v2:0"
    BEDROCK_EMBEDDING_DIMENSIONS: int = 1536

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # RAG
    RAG_TOP_K: int = 8
    RAG_MIN_SIMILARITY: float = 0.72
    RAG_RERANKER_TOP_K: int = 4
    HALLUCINATION_THRESHOLD: float = 0.80
    HALLUCINATION_SENSITIVITY: Literal["low", "medium", "high", "critical"] = "high"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_DAY: int = 2000

    # Async Worker — S3 + SQS + Large File Pipeline
    SQS_QUEUE_URL: str | None = None            # AWS SQS kuyruğu URL'si
    SQS_DLQ_URL: str | None = None              # Dead Letter Queue URL'si
    AWS_KMS_KEY_ID: str | None = None           # SSE-KMS anahtar ID (None → AES256)
    WORKER_BATCH_SIZE: int = 50                 # Her batch'teki sayfa sayısı
    WORKER_BATCH_TIMEOUT_SEC: int = 120         # Tek batch için maksimum süre
    WORKER_VISIBILITY_TIMEOUT_SEC: int = 300    # SQS mesaj gizlilik süresi
    LARGE_FILE_PAGE_THRESHOLD: int = 3000       # Bu üzeri async pipeline'a girer

    # Audit & Anomaly Detection
    SLACK_WEBHOOK_URL: str | None = None        # Boşsa Slack bildirimi atlanır
    ANOMALY_RATE_LIMIT: int = 100               # 1 saatte maksimum sorgu (RULE-1)
    ANOMALY_OFF_HOURS_START: int = 2            # 02:00 UTC (RULE-2)
    ANOMALY_OFF_HOURS_END: int = 6              # 06:00 UTC (RULE-2)
    ANOMALY_DUPLICATE_MAX: int = 5              # 10 saniyede maksimum tekrar (RULE-4)
    ANOMALY_DUPLICATE_WINDOW_SEC: int = 10      # Tekrar penceresi (RULE-4)

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "text"] = "json"

    @field_validator("BEDROCK_TEMPERATURE")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("BEDROCK_TEMPERATURE must be between 0.0 and 1.0")
        return v


settings = Settings()

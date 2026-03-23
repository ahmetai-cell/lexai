"""
LexAI Document Processing Worker

Kullanım:
    python scripts/run_worker.py

Docker:
    docker-compose -f docker-compose.worker.yml up

Ortam değişkenleri (ayrıca .env'den okunur):
    SQS_QUEUE_URL       — AWS SQS kuyruğu URL'si (zorunlu)
    DATABASE_URL        — PostgreSQL bağlantı URL'si (zorunlu)
    AWS_ACCESS_KEY_ID   — AWS kimlik bilgisi
    AWS_SECRET_ACCESS_KEY
    AWS_REGION          — varsayılan: us-east-1
"""
import asyncio
import sys
import os

# Proje kökünü Python path'ine ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.logging import configure_logging
from app.core.config import settings
from app.workers.document_worker import DocumentWorker


async def main() -> None:
    configure_logging()

    # SQS URL zorunlu kontrol
    if not getattr(settings, "SQS_QUEUE_URL", None):
        print("HATA: SQS_QUEUE_URL ortam değişkeni tanımlı değil.", file=sys.stderr)
        sys.exit(1)

    worker = DocumentWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())

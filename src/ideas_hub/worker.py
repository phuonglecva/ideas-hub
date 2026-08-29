import asyncio
from uuid import UUID

from celery import Celery

from ideas_hub.config import get_settings
from ideas_hub.db import SessionLocal
from ideas_hub.pipeline import crawl_source

settings = get_settings()
celery_app = Celery("ideas_hub", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]


@celery_app.task(name="ideas_hub.crawl_source")
def crawl_source_task(source_id: str, limit: int = 20) -> dict:
    async def _run() -> dict:
        async with SessionLocal() as db:
            return await crawl_source(db, UUID(source_id), limit)

    return asyncio.run(_run())

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from celery import Celery
from sqlalchemy import select

from ideas_hub.config import get_settings
from ideas_hub.db import SessionLocal, engine
from ideas_hub.models import CrawlRun, Source, SourceCandidate
from ideas_hub.pipeline import backfill_opportunities, crawl_source
from ideas_hub.source_discovery import discover_from_recent_articles, validate_candidate

settings = get_settings()
celery_app = Celery("ideas_hub", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.beat_schedule = {
    "crawl-enabled-sources": {
        "task": "ideas_hub.crawl_enabled_sources",
        "schedule": settings.crawl_interval_minutes * 60,
        "args": (settings.crawl_limit,),
    },
    "discover-source-candidates": {
        "task": "ideas_hub.discover_source_candidates",
        "schedule": settings.source_discovery_interval_hours * 60 * 60,
        "args": (settings.source_discovery_article_limit,),
    },
}


@celery_app.task(bind=True, name="ideas_hub.crawl_source")
def crawl_source_task(
    self, source_id: str, limit: int = 20, run_id: str | None = None, trigger: str = "manual"
) -> dict:
    async def _run() -> dict:
        started = datetime.now(UTC)
        try:
            async with SessionLocal() as db:
                run = await db.get(CrawlRun, UUID(run_id)) if run_id else None
                if run is None:
                    run = CrawlRun(
                        source_id=UUID(source_id),
                        task_id=self.request.id,
                        trigger=trigger,
                        status="running",
                        limit=limit,
                    )
                    db.add(run)
                run.task_id = self.request.id
                run.status = "running"
                run.started_at = started
                await db.commit()
                try:
                    result = await crawl_source(db, UUID(source_id), limit)
                except Exception as exc:
                    await db.rollback()
                    run = await db.get(CrawlRun, run.id)
                    run.status = "failed"
                    run.error = str(exc)[:1000]
                    run.finished_at = datetime.now(UTC)
                    run.duration_ms = int((run.finished_at - started).total_seconds() * 1000)
                    await db.commit()
                    raise
                run.status = "succeeded"
                run.discovered = result["discovered"]
                run.created = result["created"]
                run.events_updated = result["events_updated"]
                run.opportunities = result["opportunities"]
                run.failures = result["failures"]
                run.finished_at = datetime.now(UTC)
                run.duration_ms = int((run.finished_at - started).total_seconds() * 1000)
                await db.commit()
                return {**result, "run_id": str(run.id)}
        finally:
            # Celery invokes asyncio.run() per task. Drop asyncpg connections
            # before that task's event loop closes so the next task cannot
            # reuse a connection bound to the previous loop.
            await engine.dispose()

    return asyncio.run(_run())


@celery_app.task(name="ideas_hub.crawl_enabled_sources")
def crawl_enabled_sources_task(limit: int | None = None) -> dict:
    async def _source_ids() -> list[str]:
        try:
            async with SessionLocal() as db:
                ids = (
                    await db.scalars(
                        select(Source.id).where(
                            Source.enabled.is_(True), Source.feed_url.is_not(None)
                        )
                    )
                ).all()
                return [str(source_id) for source_id in ids]
        finally:
            await engine.dispose()

    source_ids = asyncio.run(_source_ids())
    crawl_limit = limit or settings.crawl_limit
    for source_id in source_ids:
        crawl_source_task.delay(source_id, crawl_limit, None, "scheduled")
    return {"enqueued": len(source_ids), "limit": crawl_limit}


@celery_app.task(name="ideas_hub.backfill_opportunities")
def backfill_opportunities_task(limit: int = 100) -> dict:
    async def _run() -> dict:
        try:
            async with SessionLocal() as db:
                return await backfill_opportunities(db, limit)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


@celery_app.task(name="ideas_hub.validate_source_candidate")
def validate_source_candidate_task(candidate_id: str) -> dict:
    async def _run() -> dict:
        try:
            async with SessionLocal() as db:
                return await validate_candidate(db, UUID(candidate_id))
        finally:
            await engine.dispose()

    result = asyncio.run(_run())
    if result.get("source_id"):
        crawl_source_task.delay(
            result["source_id"], settings.source_bootstrap_limit, None, "discovery"
        )
    return result


@celery_app.task(name="ideas_hub.discover_source_candidates")
def discover_source_candidates_task(limit: int | None = None) -> dict:
    async def _run() -> tuple[dict, list[str]]:
        try:
            async with SessionLocal() as db:
                result = await discover_from_recent_articles(
                    db, limit or settings.source_discovery_article_limit
                )
                eligible = (
                    await db.scalars(
                        select(SourceCandidate.id).where(
                            SourceCandidate.status.in_(["discovered", "failed"]),
                            SourceCandidate.retry_count < 3,
                        )
                    )
                ).all()
                return result, [str(candidate_id) for candidate_id in eligible]
        finally:
            await engine.dispose()

    result, candidate_ids = asyncio.run(_run())
    for candidate_id in candidate_ids:
        validate_source_candidate_task.delay(candidate_id)
    return {**result, "validation_enqueued": len(candidate_ids)}

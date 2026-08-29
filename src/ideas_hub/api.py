from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ideas_hub.db import get_db
from ideas_hub.models import Article, Event, Opportunity, Signal, Source
from ideas_hub.pipeline import crawl_source
from ideas_hub.schemas import ArticleOut, EventOut, OpportunityOut, SignalOut, SourceCreate, SourceOut
from ideas_hub.worker import crawl_source_task

router = APIRouter(prefix="/v1")


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.post("/sources", response_model=SourceOut)
async def create_source(payload: SourceCreate, db: AsyncSession = Depends(get_db)):
    source = Source(**payload.model_dump())
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(db: AsyncSession = Depends(get_db)):
    return (await db.scalars(select(Source).order_by(Source.name))).all()


@router.get("/articles", response_model=list[ArticleOut])
async def list_articles(limit: int = Query(50, le=200), db: AsyncSession = Depends(get_db)):
    return (await db.scalars(select(Article).order_by(Article.crawled_at.desc()).limit(limit))).all()


@router.get("/events", response_model=list[EventOut])
async def list_events(limit: int = Query(50, le=200), db: AsyncSession = Depends(get_db)):
    return (await db.scalars(select(Event).order_by(Event.last_seen_at.desc()).limit(limit))).all()


@router.get("/signals", response_model=list[SignalOut])
async def list_signals(limit: int = Query(50, le=200), db: AsyncSession = Depends(get_db)):
    return (await db.scalars(select(Signal).order_by(Signal.score.desc()).limit(limit))).all()


@router.get("/opportunities", response_model=list[OpportunityOut])
async def list_opportunities(limit: int = Query(50, le=200), db: AsyncSession = Depends(get_db)):
    return (await db.scalars(select(Opportunity).order_by(Opportunity.score.desc()).limit(limit))).all()


@router.post("/pipeline/sources/{source_id}/crawl")
async def run_source(source_id: UUID, limit: int = Query(20, le=100), db: AsyncSession = Depends(get_db)):
    try:
        return await crawl_source(db, source_id, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/pipeline/sources/{source_id}/enqueue")
async def enqueue_source(source_id: UUID, limit: int = Query(20, le=100)):
    result = crawl_source_task.delay(str(source_id), limit)
    return {"task_id": result.id, "status": "queued"}

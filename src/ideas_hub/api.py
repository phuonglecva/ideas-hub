from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ideas_hub.config import get_settings
from ideas_hub.db import get_db
from ideas_hub.models import (
    Article,
    CrawlRun,
    Event,
    Opportunity,
    Signal,
    Source,
    SourceCandidate,
    SourceCandidateEvidence,
)
from ideas_hub.pipeline import crawl_source
from ideas_hub.schemas import (
    ArticleOut,
    ArticleUpdate,
    CrawlRunOut,
    EventOut,
    EventUpdate,
    OpportunityOut,
    OpportunityUpdate,
    SignalOut,
    SourceCandidateCreate,
    SourceCandidateEvidenceOut,
    SourceCandidateOut,
    SourceCreate,
    SourceOut,
    SourceUpdate,
)
from ideas_hub.source_discovery import (
    promote_candidate,
    registrable_domain,
    validate_public_url,
)
from ideas_hub.worker import (
    backfill_opportunities_task,
    crawl_enabled_sources_task,
    crawl_source_task,
    discover_source_candidates_task,
    validate_source_candidate_task,
)

router = APIRouter(prefix="/v1")
DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.post("/sources", response_model=SourceOut)
async def create_source(payload: SourceCreate, db: DbSession):
    source = Source(**payload.model_dump())
    db.add(source)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Domain already exists") from exc
    await db.refresh(source)
    return source


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(db: DbSession):
    return (await db.scalars(select(Source).order_by(Source.name))).all()


@router.post("/source-candidates", response_model=SourceCandidateOut)
async def create_source_candidate(payload: SourceCandidateCreate, db: DbSession):
    try:
        homepage_url = await validate_public_url(payload.homepage_url)
        feed_url = await validate_public_url(payload.feed_url) if payload.feed_url else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    hostname = urlparse(homepage_url).hostname
    domain = registrable_domain(hostname or "")
    source_domains = (await db.scalars(select(Source.domain))).all()
    if domain in {registrable_domain(item.split("/", 1)[0]) for item in source_domains}:
        raise HTTPException(status_code=409, detail="Source domain is already active")
    existing = await db.scalar(select(SourceCandidate).where(SourceCandidate.domain == domain))
    if existing:
        raise HTTPException(status_code=409, detail="Candidate domain already exists")
    candidate = SourceCandidate(
        name=payload.name.strip()[:200] if payload.name else None,
        domain=domain,
        homepage_url=homepage_url,
        feed_url=feed_url,
        discovery_url=homepage_url,
        discovery_method="manual",
    )
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)
    return candidate


@router.get("/source-candidates", response_model=list[SourceCandidateOut])
async def list_source_candidates(
    db: DbSession,
    status: str | None = None,
    min_score: float | None = Query(None, ge=0, le=100),
    limit: int = Query(100, ge=1, le=200),
):
    query = select(SourceCandidate)
    if status:
        query = query.where(SourceCandidate.status == status)
    if min_score is not None:
        query = query.where(SourceCandidate.score >= min_score)
    candidates = (await db.scalars(query.order_by(SourceCandidate.score.desc()).limit(limit))).all()
    output: list[SourceCandidateOut] = []
    for candidate in candidates:
        evidence_rows = (
            await db.execute(
                select(SourceCandidateEvidence, Article, Source)
                .join(Article, Article.id == SourceCandidateEvidence.article_id)
                .join(Source, Source.id == SourceCandidateEvidence.referring_source_id)
                .where(SourceCandidateEvidence.candidate_id == candidate.id)
                .order_by(SourceCandidateEvidence.created_at.desc())
                .limit(5)
            )
        ).all()
        item = SourceCandidateOut.model_validate(candidate)
        item.evidence = [
            SourceCandidateEvidenceOut(
                article_id=article.id,
                article_title=article.title,
                article_url=article.canonical_url,
                source_name=source.name,
                discovered_url=evidence.discovered_url,
            )
            for evidence, article, source in evidence_rows
        ]
        output.append(item)
    return output


@router.post("/source-discovery/enqueue")
async def enqueue_source_discovery(limit: int = Query(200, ge=1, le=1000)):
    result = discover_source_candidates_task.delay(limit)
    return {"task_id": result.id, "status": "queued"}


@router.post("/source-candidates/{candidate_id}/validate")
async def enqueue_candidate_validation(candidate_id: UUID, db: DbSession):
    candidate = await db.get(SourceCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Source candidate not found")
    if candidate.status == "rejected":
        candidate.status = "discovered"
        candidate.retry_count = 0
        candidate.failure_reason = None
        await db.commit()
    result = validate_source_candidate_task.delay(str(candidate_id))
    return {"task_id": result.id, "status": "queued"}


@router.post("/source-candidates/{candidate_id}/approve", response_model=SourceOut)
async def approve_source_candidate(candidate_id: UUID, db: DbSession):
    candidate = await db.get(SourceCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Source candidate not found")
    if candidate.source_id:
        source = await db.get(Source, candidate.source_id)
        if source:
            return source
    if not candidate.feed_url:
        raise HTTPException(status_code=400, detail="Candidate has no validated feed")
    if candidate.status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Candidate must complete validation before approval",
        )
    source = await promote_candidate(db, candidate)
    candidate.status = "approved"
    await db.commit()
    await db.refresh(source)
    run = CrawlRun(
        source_id=source.id,
        trigger="approval",
        status="queued",
        limit=get_settings().source_bootstrap_limit,
    )
    db.add(run)
    await db.commit()
    result = crawl_source_task.delay(
        str(source.id), get_settings().source_bootstrap_limit, str(run.id), "approval"
    )
    run.task_id = result.id
    await db.commit()
    return source


@router.post("/source-candidates/{candidate_id}/reject", response_model=SourceCandidateOut)
async def reject_source_candidate(candidate_id: UUID, db: DbSession):
    candidate = await db.get(SourceCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Source candidate not found")
    candidate.status = "rejected"
    candidate.failure_reason = "Rejected by operator"
    await db.commit()
    await db.refresh(candidate)
    return candidate


@router.get("/crawl-runs", response_model=list[CrawlRunOut])
async def list_crawl_runs(
    db: DbSession,
    source_id: UUID | None = None,
    status: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    query = select(CrawlRun)
    if source_id:
        query = query.where(CrawlRun.source_id == source_id)
    if status:
        query = query.where(CrawlRun.status == status)
    return (await db.scalars(query.order_by(CrawlRun.queued_at.desc()).limit(limit))).all()


@router.patch("/sources/{source_id}", response_model=SourceOut)
async def update_source(source_id: UUID, payload: SourceUpdate, db: DbSession):
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Domain already exists") from exc
    await db.refresh(source)
    return source


@router.get("/articles", response_model=list[ArticleOut])
async def list_articles(db: DbSession, limit: int = Query(50, le=200)):
    return (
        await db.scalars(select(Article).order_by(Article.crawled_at.desc()).limit(limit))
    ).all()


@router.patch("/articles/{article_id}", response_model=ArticleOut)
async def update_article(article_id: UUID, payload: ArticleUpdate, db: DbSession):
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    values = payload.model_dump(exclude_unset=True)
    if isinstance(values.get("extracted"), dict):
        values["extracted"] = payload.extracted.model_dump(mode="json")
    for field, value in values.items():
        setattr(article, field, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Article URL already exists") from exc
    await db.refresh(article)
    return article


@router.get("/events", response_model=list[EventOut])
async def list_events(db: DbSession, limit: int = Query(50, le=200)):
    return (await db.scalars(select(Event).order_by(Event.last_seen_at.desc()).limit(limit))).all()


@router.patch("/events/{event_id}", response_model=EventOut)
async def update_event(event_id: UUID, payload: EventUpdate, db: DbSession):
    event = await db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    await db.commit()
    await db.refresh(event)
    return event


@router.get("/signals", response_model=list[SignalOut])
async def list_signals(db: DbSession, limit: int = Query(50, le=200)):
    return (await db.scalars(select(Signal).order_by(Signal.score.desc()).limit(limit))).all()


@router.get("/opportunities", response_model=list[OpportunityOut])
async def list_opportunities(db: DbSession, limit: int = Query(50, le=200)):
    return (
        await db.scalars(select(Opportunity).order_by(Opportunity.score.desc()).limit(limit))
    ).all()


@router.post("/opportunities/backfill")
async def enqueue_opportunity_backfill(limit: int = Query(100, ge=1, le=1000)):
    result = backfill_opportunities_task.delay(limit)
    return {"task_id": result.id, "status": "queued", "limit": limit}


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityOut)
async def update_opportunity(opportunity_id: UUID, payload: OpportunityUpdate, db: DbSession):
    opportunity = await db.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(opportunity, field, value)
    await db.commit()
    await db.refresh(opportunity)
    return opportunity


@router.post("/pipeline/sources/{source_id}/crawl")
async def run_source(source_id: UUID, db: DbSession, limit: int = Query(20, le=100)):
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    started = datetime.now(UTC)
    run = CrawlRun(
        source_id=source_id,
        trigger="api_sync",
        status="running",
        limit=limit,
        started_at=started,
    )
    db.add(run)
    await db.commit()
    try:
        result = await crawl_source(db, source_id, limit)
    except ValueError as exc:
        await db.rollback()
        run = await db.get(CrawlRun, run.id)
        run.status = "failed"
        run.error = str(exc)[:1000]
        run.finished_at = datetime.now(UTC)
        run.duration_ms = int((run.finished_at - started).total_seconds() * 1000)
        await db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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


@router.post("/pipeline/sources/{source_id}/enqueue")
async def enqueue_source(source_id: UUID, db: DbSession, limit: int = Query(20, le=100)):
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    run = CrawlRun(source_id=source_id, trigger="manual", status="queued", limit=limit)
    db.add(run)
    await db.commit()
    result = crawl_source_task.delay(str(source_id), limit, str(run.id), "manual")
    run.task_id = result.id
    await db.commit()
    return {"task_id": result.id, "run_id": str(run.id), "status": "queued"}


@router.post("/pipeline/enqueue-enabled")
async def enqueue_enabled_sources(limit: int = Query(20, ge=1, le=100)):
    result = crawl_enabled_sources_task.delay(limit)
    return {"task_id": result.id, "status": "queued"}

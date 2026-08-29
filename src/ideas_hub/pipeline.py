import math
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ideas_hub.config import get_settings
from ideas_hub.crawler import discover_feed_urls, fetch_article
from ideas_hub.embeddings import cosine_similarity, embed_text
from ideas_hub.model_gateway import ModelGateway
from ideas_hub.models import Article, Event, EventArticle, Opportunity, Signal, Source
from ideas_hub.schemas import ArticleInsight, OpportunityScore, OpportunityThesis, SkepticReview
from ideas_hub.storage import ObjectStore


def signal_score(velocity: float, persistence: float, breadth: float, authority: float, novelty: float, economic_relevance: float) -> float:
    return round(100 * (0.20 * velocity + 0.15 * persistence + 0.15 * breadth + 0.15 * authority + 0.10 * novelty + 0.25 * economic_relevance), 2)


async def ingest_url(db: AsyncSession, source: Source, url: str) -> Article | None:
    crawled = await fetch_article(url)
    existing = await db.scalar(select(Article).where((Article.canonical_url == crawled.url) | (Article.content_hash == crawled.content_hash)))
    if existing:
        return None

    store = ObjectStore()
    await store.ensure_bucket()
    raw_key = f"raw/{source.id}/{crawled.content_hash}.html"
    await store.put_text(raw_key, crawled.raw_html)

    vector = await embed_text(f"{crawled.title}\n{crawled.body[:3000]}")
    article = Article(
        source_id=source.id,
        canonical_url=crawled.url,
        title=crawled.title,
        body=crawled.body,
        author=crawled.author,
        published_at=crawled.published_at,
        content_hash=crawled.content_hash,
        raw_object_key=raw_key,
        embedding=vector,
    )
    db.add(article)
    await db.flush()

    gateway = ModelGateway(db)
    try:
        insight = await gateway.structured(
            "article_extract",
            "Extract only information supported by the article. Do not infer startup ideas.",
            {"article_id": str(article.id), "title": article.title, "body": article.body[:12000]},
            ArticleInsight,
        )
        article.extracted = insight.model_dump(mode="json")
    except Exception:
        # In local-first mode ingestion remains useful even if no LLM server is running.
        article.extracted = {"entities": [], "industries": [], "affected_groups": [], "problems": [], "changes": [], "claims": [], "metrics": [], "regulations": []}

    await attach_event(db, article, source)
    return article


async def attach_event(db: AsyncSession, article: Article, source: Source) -> Event:
    settings = get_settings()
    candidates = (await db.scalars(select(Event).order_by(Event.last_seen_at.desc()).limit(200))).all()
    best_event: Event | None = None
    best_similarity = -1.0
    vector = list(article.embedding or [])
    for event in candidates:
        if event.centroid:
            similarity = cosine_similarity(vector, list(event.centroid))
            if similarity > best_similarity:
                best_similarity = similarity
                best_event = event

    if best_event is None or best_similarity < settings.event_similarity_threshold:
        best_event = Event(title=article.title, centroid=vector, article_count=0, source_count=0)
        db.add(best_event)
        await db.flush()
        best_similarity = 1.0

    db.add(EventArticle(event_id=best_event.id, article_id=article.id, similarity=best_similarity))
    best_event.article_count += 1
    best_event.last_seen_at = datetime.now(timezone.utc)

    source_count = await db.scalar(
        select(func.count(func.distinct(Article.source_id)))
        .join(EventArticle, EventArticle.article_id == Article.id)
        .where(EventArticle.event_id == best_event.id)
    )
    best_event.source_count = int(source_count or 0) + (1 if best_event.article_count == 1 else 0)
    return best_event


async def refresh_signal(db: AsyncSession, event: Event) -> Signal:
    event_age_days = max(1.0, (datetime.now(timezone.utc) - event.first_seen_at).total_seconds() / 86400)
    velocity = min(1.0, event.article_count / max(3.0, event_age_days * 2))
    persistence = min(1.0, math.log1p(event_age_days) / math.log(31))
    breadth = min(1.0, event.source_count / 8)

    trust = await db.scalar(
        select(func.avg(Source.trust_score))
        .join(Article, Article.source_id == Source.id)
        .join(EventArticle, EventArticle.article_id == Article.id)
        .where(EventArticle.event_id == event.id)
    )
    authority = float(trust or 0.5)
    novelty = 0.65  # placeholder until historical topic baselines are populated
    economic_relevance = 0.6  # later derived from explicit economic ontology/features
    score = signal_score(velocity, persistence, breadth, authority, novelty, economic_relevance)

    signal = await db.scalar(select(Signal).where(Signal.event_id == event.id))
    if signal is None:
        signal = Signal(event_id=event.id)
        db.add(signal)
    signal.velocity = velocity
    signal.persistence = persistence
    signal.breadth = breadth
    signal.authority = authority
    signal.novelty = novelty
    signal.economic_relevance = economic_relevance
    signal.score = score
    signal.features = {
        "velocity": velocity,
        "persistence": persistence,
        "breadth": breadth,
        "authority": authority,
        "novelty": novelty,
        "economic_relevance": economic_relevance,
        "article_count": event.article_count,
        "source_count": event.source_count,
    }
    await db.flush()
    return signal


async def build_opportunity(db: AsyncSession, signal: Signal) -> Opportunity | None:
    event = await db.get(Event, signal.event_id)
    if not event or signal.score < 35:
        return None

    articles = (
        await db.scalars(
            select(Article)
            .join(EventArticle, EventArticle.article_id == Article.id)
            .where(EventArticle.event_id == event.id)
            .order_by(Article.published_at.desc().nullslast())
            .limit(12)
        )
    ).all()
    evidence = [
        {"id": str(a.id), "title": a.title, "url": a.canonical_url, "insight": a.extracted}
        for a in articles
    ]

    gateway = ModelGateway(db)
    thesis = await gateway.structured(
        "opportunity_generate",
        "Generate a practical Vietnam startup thesis only when evidence supports a real customer problem. Avoid generic 'AI platform' ideas. evidence_ids must reference supplied article ids.",
        {"signal": signal.features, "event": {"id": str(event.id), "title": event.title}, "evidence": evidence},
        OpportunityThesis,
    )
    skeptic = await gateway.structured(
        "opportunity_skeptic",
        "Assume the startup thesis may be wrong. Identify fatal risks, substitutes, counter-evidence, validation tests, and explicit kill criteria.",
        {"thesis": thesis.model_dump(mode="json"), "evidence": evidence},
        SkepticReview,
    )
    judged = await gateway.structured(
        "opportunity_judge",
        "Score conservatively. High scores require evidence for pain, willingness to pay, timing, distribution, competitive gap, and reason to win. Confidence measures evidence quality, not attractiveness.",
        {"thesis": thesis.model_dump(mode="json"), "skeptic": skeptic.model_dump(mode="json"), "signal": signal.features, "evidence": evidence},
        OpportunityScore,
    )
    score = round(judged.weighted_score(), 2)
    opp = Opportunity(
        signal_id=signal.id,
        title=thesis.title,
        customer=thesis.customer,
        problem=thesis.problem,
        solution=thesis.proposed_solution,
        thesis=thesis.model_dump(mode="json"),
        skeptic=skeptic.model_dump(mode="json"),
        score_breakdown=judged.model_dump(mode="json"),
        score=score,
        confidence=judged.confidence,
    )
    db.add(opp)
    await db.flush()
    return opp


async def crawl_source(db: AsyncSession, source_id: UUID, limit: int = 20) -> dict:
    source = await db.get(Source, source_id)
    if not source or not source.enabled:
        raise ValueError("Source not found or disabled")
    if not source.feed_url:
        raise ValueError("MVP source requires feed_url")

    urls = await discover_feed_urls(source.feed_url, limit=limit)
    created = 0
    event_ids: set[UUID] = set()
    for url in urls:
        try:
            article = await ingest_url(db, source, url)
            if article:
                created += 1
                event_id = await db.scalar(select(EventArticle.event_id).where(EventArticle.article_id == article.id))
                if event_id:
                    event_ids.add(event_id)
        except Exception:
            continue

    opportunities = 0
    for event_id in event_ids:
        event = await db.get(Event, event_id)
        if not event:
            continue
        signal = await refresh_signal(db, event)
        if signal.score >= 55:
            try:
                if await build_opportunity(db, signal):
                    opportunities += 1
            except Exception:
                # No cloud/local reasoner should never block deterministic ingestion/analytics.
                pass
    await db.commit()
    return {"discovered": len(urls), "created": created, "events_updated": len(event_ids), "opportunities": opportunities}

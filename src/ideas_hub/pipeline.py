import logging
import math
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ideas_hub.config import get_settings
from ideas_hub.crawler import fetch_article
from ideas_hub.embeddings import cosine_similarity, embed_text
from ideas_hub.model_gateway import ModelGateway
from ideas_hub.models import Article, Event, EventArticle, Opportunity, Signal, Source
from ideas_hub.schemas import ArticleInsight, OpportunityScore, OpportunityThesis, SkepticReview
from ideas_hub.source_adapters import get_source_adapter
from ideas_hub.source_discovery import record_outbound_candidates
from ideas_hub.storage import ObjectStore

logger = logging.getLogger(__name__)


def signal_score(
    velocity: float,
    persistence: float,
    breadth: float,
    authority: float,
    novelty: float,
    economic_relevance: float,
) -> float:
    return round(
        100
        * (
            0.20 * velocity
            + 0.15 * persistence
            + 0.15 * breadth
            + 0.15 * authority
            + 0.10 * novelty
            + 0.25 * economic_relevance
        ),
        2,
    )


def is_signal_eligible(score: float, threshold: float | None = None) -> bool:
    cutoff = threshold if threshold is not None else get_settings().signal_opportunity_threshold
    return score >= cutoff


async def ingest_url(db: AsyncSession, source: Source, url: str) -> Article | None:
    # Avoid downloading, extracting, embedding and invoking the LLM for feed entries
    # whose canonical URL is already present. Content-hash dedupe below remains the
    # second line of defense for redirects, tracking URLs and syndicated copies.
    if await db.scalar(select(Article.id).where(Article.canonical_url == url)):
        return None

    crawled = await fetch_article(url)
    existing = await db.scalar(
        select(Article).where(
            (Article.canonical_url == crawled.url) | (Article.content_hash == crawled.content_hash)
        )
    )
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
    except Exception as exc:  # noqa: BLE001 - optional AI stage must not block ingestion
        logger.warning("article extraction failed for %s: %s", article.id, exc)
        article.extracted = {
            "entities": [],
            "industries": [],
            "affected_groups": [],
            "problems": [],
            "changes": [],
            "claims": [],
            "metrics": [],
            "regulations": [],
        }

    await attach_event(db, article)
    try:
        async with db.begin_nested():
            await record_outbound_candidates(db, article, source, crawled.raw_html)
    except Exception as exc:  # noqa: BLE001 - discovery must never block ingestion
        logger.warning("source candidate extraction failed for %s: %s", article.id, exc)
    return article


async def attach_event(db: AsyncSession, article: Article) -> Event:
    settings = get_settings()
    candidates = (
        await db.scalars(select(Event).order_by(Event.last_seen_at.desc()).limit(200))
    ).all()
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
    best_event.last_seen_at = datetime.now(UTC)
    await db.flush()

    source_count = await db.scalar(
        select(func.count(func.distinct(Article.source_id)))
        .join(EventArticle, EventArticle.article_id == Article.id)
        .where(EventArticle.event_id == best_event.id)
    )
    best_event.source_count = int(source_count or 0)
    return best_event


async def refresh_signal(db: AsyncSession, event: Event) -> Signal:
    event_age_days = max(1.0, (datetime.now(UTC) - event.first_seen_at).total_seconds() / 86400)
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
    novelty = 0.65  # replaced later by historical topic baselines
    economic_relevance = 0.6  # replaced later by ontology-derived features
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
    locked_signal = await db.scalar(select(Signal).where(Signal.id == signal.id).with_for_update())
    if locked_signal is None or not is_signal_eligible(locked_signal.score):
        return None
    event = await db.get(Event, locked_signal.event_id)
    if not event:
        return None
    existing = await db.scalar(select(Opportunity).where(Opportunity.signal_id == locked_signal.id))
    if existing is not None:
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
        {
            "id": str(a.id),
            "title": a.title,
            "url": a.canonical_url,
            "insight": a.extracted,
        }
        for a in articles
    ]

    gateway = ModelGateway(db)
    thesis = await gateway.structured(
        "opportunity_generate",
        "Generate a practical Vietnam startup thesis only when evidence supports a real customer problem. Avoid generic 'AI platform' ideas. evidence_ids must reference supplied article ids.",
        {
            "signal": locked_signal.features,
            "event": {"id": str(event.id), "title": event.title},
            "evidence": evidence,
        },
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
        {
            "thesis": thesis.model_dump(mode="json"),
            "skeptic": skeptic.model_dump(mode="json"),
            "signal": locked_signal.features,
            "evidence": evidence,
        },
        OpportunityScore,
    )
    score = round(judged.weighted_score(), 2)
    opp = Opportunity(
        signal_id=locked_signal.id,
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


async def backfill_opportunities(db: AsyncSession, limit: int = 100) -> dict:
    eligible_ids = (
        await db.scalars(
            select(Signal.id)
            .where(
                Signal.score >= get_settings().signal_opportunity_threshold,
                ~select(Opportunity.id).where(Opportunity.signal_id == Signal.id).exists(),
            )
            .order_by(Signal.score.desc())
            .limit(limit)
        )
    ).all()
    created = 0
    skipped = 0
    failures: list[dict] = []
    for signal_id in eligible_ids:
        try:
            async with db.begin_nested():
                signal = await db.get(Signal, signal_id)
                if signal is None or not is_signal_eligible(signal.score):
                    skipped += 1
                    continue
                if await build_opportunity(db, signal):
                    created += 1
                else:
                    skipped += 1
            await db.commit()
        except Exception as exc:  # noqa: BLE001 - isolate one model run from the batch
            await db.rollback()
            logger.warning("opportunity backfill failed for %s: %s", signal_id, exc)
            failures.append({"signal_id": str(signal_id), "error": str(exc)[:500]})
    result = {
        "eligible": len(eligible_ids),
        "created": created,
        "skipped": skipped,
        "failed": len(failures),
        "failures": failures,
    }
    logger.info("opportunity backfill complete: %s", result)
    return result


async def crawl_source(db: AsyncSession, source_id: UUID, limit: int = 20) -> dict:
    source = await db.get(Source, source_id)
    if not source or not source.enabled:
        raise ValueError("Source not found or disabled")
    if not source.feed_url:
        raise ValueError("Source requires feed_url or sitemap URL")

    adapter = get_source_adapter(source)
    has_articles = bool(
        await db.scalar(select(func.count(Article.id)).where(Article.source_id == source.id))
    )
    # Bootstrap is intentionally bounded. Once a source has history, scan its full
    # current feed/sitemap window and pre-filter known URLs in one DB query. This
    # avoids the previous head-only behavior where >limit posts between schedules
    # could disappear from the ingestion window forever.
    batch = await adapter.discover(source, limit=limit if not has_articles else None)
    urls = batch.urls
    known_urls: set[str] = set()
    if urls:
        known_urls = set(
            (
                await db.scalars(
                    select(Article.canonical_url).where(Article.canonical_url.in_(urls))
                )
            ).all()
        )
    candidate_urls = [url for url in urls if url not in known_urls]

    created = 0
    event_ids: set[UUID] = set()
    failures: list[dict] = []
    for url in candidate_urls:
        try:
            async with db.begin_nested():
                article = await ingest_url(db, source, url)
            if article:
                created += 1
                event_id = await db.scalar(
                    select(EventArticle.event_id).where(EventArticle.article_id == article.id)
                )
                if event_id:
                    event_ids.add(event_id)
        except Exception as exc:  # noqa: BLE001 - isolate one bad external article
            logger.warning("crawl failed for %s: %s", url, exc)
            failures.append({"url": url, "error": str(exc)[:300]})

    opportunities = 0
    for event_id in event_ids:
        event = await db.get(Event, event_id)
        if not event:
            continue
        signal = await refresh_signal(db, event)
        if is_signal_eligible(signal.score):
            try:
                if await build_opportunity(db, signal):
                    opportunities += 1
            except Exception as exc:  # noqa: BLE001 - optional reasoning must not block analytics
                logger.warning("opportunity generation failed for %s: %s", signal.id, exc)

    await db.commit()
    return {
        "discovered": len(urls),
        "candidates": len(candidate_urls),
        "known_skipped": len(known_urls),
        "source_kind": batch.source_kind,
        "created": created,
        "events_updated": len(event_ids),
        "opportunities": opportunities,
        "failures": failures[:10],
    }

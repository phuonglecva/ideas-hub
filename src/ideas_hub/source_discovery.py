import asyncio
import ipaddress
import logging
import socket
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse, urlunparse
from uuid import UUID

import feedparser
import httpx
import trafilatura
from selectolax.parser import HTMLParser
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ideas_hub.config import get_settings
from ideas_hub.crawler import parse_published_at
from ideas_hub.models import Article, Source, SourceCandidate, SourceCandidateEvidence
from ideas_hub.storage import ObjectStore

logger = logging.getLogger(__name__)
MAX_DISCOVERY_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
COMMON_FEED_PATHS = ("/rss.xml", "/rss", "/feed", "/feed.xml", "/atom.xml")
IGNORED_HOSTS = {
    "facebook.com",
    "youtube.com",
    "youtu.be",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "instagram.com",
    "linkedin.com",
    "zalo.me",
    "google.com",
    "googleapis.com",
    "doubleclick.net",
}
IGNORED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".mp3",
    ".mp4",
    ".avi",
    ".zip",
    ".rar",
    ".pdf",
    ".doc",
    ".docx",
}
MARKET_KEYWORDS = {
    "kinh tế",
    "kinh doanh",
    "doanh nghiệp",
    "công nghệ",
    "đầu tư",
    "tài chính",
    "ngân hàng",
    "chứng khoán",
    "thị trường",
    "startup",
    "khởi nghiệp",
    "việc làm",
    "lao động",
    "chính sách",
    "quy định",
    "thuế",
    "xuất khẩu",
    "sản xuất",
    "bán lẻ",
    "bất động sản",
    "đổi mới sáng tạo",
    "chuyển đổi số",
    "trí tuệ nhân tạo",
    "ai ",
}


class UnsafeUrlError(ValueError):
    pass


def registrable_domain(hostname: str) -> str:
    host = hostname.lower().strip(".")
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    if ".".join(labels[-2:]) in {"com.vn", "net.vn", "org.vn", "gov.vn", "edu.vn"}:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("Only absolute HTTP(S) URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("Credentials in URLs are not allowed")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("Invalid URL port") from exc
    if port is not None and port not in {80, 443}:
        raise UnsafeUrlError("Only ports 80 and 443 are allowed")
    host = parsed.hostname.lower().strip(".")
    netloc = host
    if port and not (
        (parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    return urlunparse((parsed.scheme.lower(), netloc, parsed.path or "/", "", parsed.query, ""))


def is_public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


async def validate_public_url(url: str) -> str:
    normalized = normalize_url(url)
    hostname = urlparse(normalized).hostname
    if not hostname or hostname == "localhost" or hostname.endswith(".localhost"):
        raise UnsafeUrlError("Local hostnames are not allowed")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            addresses = await loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise UnsafeUrlError("Hostname could not be resolved") from exc
        resolved = {item[4][0] for item in addresses}
        if not resolved or any(not is_public_ip(address) for address in resolved):
            raise UnsafeUrlError("Hostname resolves to a non-public address")
    else:
        if not is_public_ip(str(literal)):
            raise UnsafeUrlError("Non-public IP addresses are not allowed")
    return normalized


async def safe_fetch(
    url: str,
    *,
    max_bytes: int = MAX_DISCOVERY_BYTES,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[str, bytes, str]:
    current = url
    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=False,
        headers={"User-Agent": "IdeasHub/0.1 source-discovery"},
        transport=transport,
    ) as client:
        for redirect_number in range(MAX_REDIRECTS + 1):
            current = await validate_public_url(current)
            async with client.stream("GET", current) as response:
                if response.is_redirect:
                    if redirect_number == MAX_REDIRECTS:
                        raise UnsafeUrlError("Too many redirects")
                    location = response.headers.get("location")
                    if not location:
                        raise UnsafeUrlError("Redirect has no location")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                declared = int(response.headers.get("content-length") or 0)
                if declared > max_bytes:
                    raise ValueError("Response exceeds discovery size limit")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Response exceeds discovery size limit")
                    chunks.append(chunk)
                return str(response.url), b"".join(chunks), response.headers.get("content-type", "")
    raise UnsafeUrlError("Could not resolve URL")


def extract_external_links(html: str, base_url: str) -> list[str]:
    base_host = urlparse(base_url).hostname or ""
    base_domain = registrable_domain(base_host)
    found: dict[str, str] = {}
    for node in HTMLParser(html).css("a[href]"):
        raw = node.attributes.get("href")
        if not raw:
            continue
        try:
            target = normalize_url(urljoin(base_url, raw))
        except (UnsafeUrlError, ValueError):
            continue
        parsed = urlparse(target)
        domain = registrable_domain(parsed.hostname or "")
        if not domain or domain == base_domain:
            continue
        if any(domain == ignored or domain.endswith(f".{ignored}") for ignored in IGNORED_HOSTS):
            continue
        if PurePosixPath(parsed.path.lower()).suffix in IGNORED_EXTENSIONS:
            continue
        found.setdefault(domain, target)
    return list(found.values())[:30]


def feed_links_from_html(html: bytes, base_url: str) -> list[str]:
    links: list[str] = []
    tree = HTMLParser(html)
    for node in tree.css("link[rel]"):
        rel = (node.attributes.get("rel") or "").lower()
        content_type = (node.attributes.get("type") or "").lower()
        href = node.attributes.get("href")
        if href and "alternate" in rel and ("rss" in content_type or "atom" in content_type):
            links.append(urljoin(base_url, href))
    return list(dict.fromkeys(links))


def is_parsed_feed_valid(parsed) -> bool:
    return bool(parsed.version and parsed.entries)


def _entry_date(entry) -> datetime | None:
    for field in ("published", "updated", "created"):
        value = getattr(entry, field, None)
        if value:
            try:
                return parse_published_at(value)
            except (TypeError, ValueError, OverflowError):
                continue
    return None


def _market_relevance(entries: list) -> float:
    titles = [str(getattr(entry, "title", "")).lower() for entry in entries[:20]]
    if not titles:
        return 0
    relevant = sum(any(keyword in title for keyword in MARKET_KEYWORDS) for title in titles)
    return relevant / len(titles)


def calculate_candidate_score(
    *,
    entry_count: int,
    age_days: float,
    extraction_rate: float,
    relevance: float,
    referring_source_count: int,
    is_https: bool,
) -> dict[str, float]:
    """Return the documented 100-point technical discovery score."""
    return {
        "feed_validity": 20 if entry_count >= 10 else round(2 * entry_count, 2),
        "freshness": 15 if age_days <= 7 else 10 if age_days <= 14 else 0,
        "extractability": round(25 * extraction_rate, 2),
        "market_relevance": round(20 * min(1, relevance / 0.3), 2),
        "referral_diversity": round(15 * min(1, referring_source_count / 2), 2),
        "https": 5 if is_https else 0,
    }


def passes_auto_approve_gates(
    *,
    score: float,
    threshold: float,
    is_https: bool,
    entry_count: int,
    age_days: float,
    publisher_ratio: float,
    extraction_successes: int,
    referring_source_count: int,
) -> bool:
    return (
        score >= threshold
        and is_https
        and entry_count >= 10
        and age_days <= 7
        and publisher_ratio >= 0.8
        and extraction_successes >= 2
        and referring_source_count >= 2
    )


async def _sample_extract(url: str) -> bool:
    _, content, _ = await safe_fetch(url)
    document = trafilatura.bare_extraction(
        content.decode("utf-8", errors="replace"),
        url=url,
        with_metadata=True,
        include_comments=False,
        include_tables=False,
    )
    return bool(document and document.as_dict().get("text"))


async def record_outbound_candidates(
    db: AsyncSession, article: Article, source: Source, raw_html: str
) -> list[UUID]:
    existing_sources = (await db.scalars(select(Source.domain))).all()
    active_domains = {registrable_domain(item.split("/", 1)[0]) for item in existing_sources}
    candidate_ids: list[UUID] = []
    for discovered_url in extract_external_links(raw_html, article.canonical_url):
        parsed = urlparse(discovered_url)
        domain = registrable_domain(parsed.hostname or "")
        if not domain or domain in active_domains:
            continue
        homepage_url = f"{parsed.scheme}://{parsed.hostname}/"
        statement = (
            insert(SourceCandidate)
            .values(
                domain=domain,
                homepage_url=homepage_url,
                discovery_url=discovered_url,
                discovery_method="outbound_link",
            )
            .on_conflict_do_update(
                index_elements=[SourceCandidate.domain],
                set_={"updated_at": func.now()},
            )
            .returning(SourceCandidate.id)
        )
        candidate_id = (await db.execute(statement)).scalar_one()
        await db.execute(
            insert(SourceCandidateEvidence)
            .values(
                candidate_id=candidate_id,
                article_id=article.id,
                referring_source_id=source.id,
                discovered_url=discovered_url,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    SourceCandidateEvidence.candidate_id,
                    SourceCandidateEvidence.article_id,
                ]
            )
        )
        candidate_ids.append(candidate_id)
    return candidate_ids


async def refresh_evidence_counts(db: AsyncSession, candidate: SourceCandidate) -> None:
    row = (
        await db.execute(
            select(
                func.count(SourceCandidateEvidence.id),
                func.count(func.distinct(SourceCandidateEvidence.referring_source_id)),
            ).where(SourceCandidateEvidence.candidate_id == candidate.id)
        )
    ).one()
    candidate.mention_count = int(row[0] or 0)
    candidate.source_count = int(row[1] or 0)


async def discover_candidate_feeds(candidate: SourceCandidate) -> list[str]:
    final_url, homepage, _ = await safe_fetch(candidate.homepage_url)
    origin = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"
    possibilities = feed_links_from_html(homepage, final_url)
    possibilities.extend(urljoin(origin, path) for path in COMMON_FEED_PATHS)
    if candidate.feed_url:
        possibilities.insert(0, candidate.feed_url)
    valid: list[str] = []
    for url in dict.fromkeys(possibilities):
        try:
            final_feed_url, content, _ = await safe_fetch(url)
            parsed = feedparser.parse(content)
            if is_parsed_feed_valid(parsed):
                valid.append(final_feed_url)
        except Exception as exc:  # noqa: BLE001 - candidate probes are isolated
            logger.debug("feed probe failed for %s: %s", url, exc)
    return valid


async def promote_candidate(db: AsyncSession, candidate: SourceCandidate) -> Source:
    if not candidate.feed_url:
        raise ValueError("Candidate has no validated feed")
    existing = await db.scalar(select(Source).where(Source.feed_url == candidate.feed_url))
    if existing:
        candidate.source_id = existing.id
        candidate.status = "approved"
        return existing
    domain_key = candidate.domain
    if await db.scalar(select(Source.id).where(Source.domain == domain_key)):
        domain_key = f"{candidate.domain}/{candidate.id.hex[:8]}"
    source = Source(
        name=candidate.name or candidate.domain,
        domain=domain_key,
        source_type="news",
        feed_url=candidate.feed_url,
        trust_score=0.6,
        enabled=True,
    )
    db.add(source)
    await db.flush()
    candidate.source_id = source.id
    return source


async def validate_candidate(db: AsyncSession, candidate_id: UUID) -> dict:
    candidate = await db.get(SourceCandidate, candidate_id)
    if not candidate:
        raise ValueError("Source candidate not found")
    if candidate.status == "rejected":
        raise ValueError("Rejected candidates require manual approval")
    candidate.status = "validating"
    candidate.failure_reason = None
    await refresh_evidence_counts(db, candidate)
    await db.commit()
    try:
        feeds = await discover_candidate_feeds(candidate)
        if not feeds:
            raise ValueError("No valid RSS or Atom feed found")

        best: dict | None = None
        for feed_url in feeds:
            _, content, _ = await safe_fetch(feed_url)
            parsed = feedparser.parse(content)
            if not is_parsed_feed_valid(parsed):
                continue
            entries = [entry for entry in parsed.entries if getattr(entry, "link", None)]
            if not entries:
                continue
            feed_domain = registrable_domain(urlparse(feed_url).hostname or "")
            same_publisher = [
                entry
                for entry in entries
                if registrable_domain(urlparse(entry.link).hostname or "") == feed_domain
            ]
            publisher_ratio = len(same_publisher) / len(entries)
            dated = [value for value in (_entry_date(entry) for entry in entries) if value]
            latest = max(dated) if dated else None
            age_days = (datetime.now(UTC) - latest).total_seconds() / 86400 if latest else 999
            sample_entries = same_publisher[:3]
            sample_results = await asyncio.gather(
                *(_sample_extract(entry.link) for entry in sample_entries), return_exceptions=True
            )
            extraction_successes = sum(result is True for result in sample_results)
            extraction_rate = extraction_successes / max(1, len(sample_entries))
            relevance = _market_relevance(entries)
            breakdown = calculate_candidate_score(
                entry_count=len(entries),
                age_days=age_days,
                extraction_rate=extraction_rate,
                relevance=relevance,
                referring_source_count=candidate.source_count,
                is_https=urlparse(feed_url).scheme == "https",
            )
            result = {
                "feed_url": feed_url,
                "feed_title": str(getattr(parsed.feed, "title", "")),
                "entries": entries,
                "entry_count": len(entries),
                "latest": latest,
                "age_days": age_days,
                "publisher_ratio": publisher_ratio,
                "extraction_successes": extraction_successes,
                "extraction_rate": extraction_rate,
                "relevance": relevance,
                "breakdown": breakdown,
                "score": round(sum(breakdown.values()), 2),
            }
            if best is None or result["score"] > best["score"]:
                best = result

        if best is None:
            raise ValueError("Feeds contained no usable entries")
        candidate.feed_url = best["feed_url"]
        candidate.name = str(candidate.name or best["feed_title"] or candidate.domain)[:200]
        candidate.score = best["score"]
        candidate.score_breakdown = best["breakdown"]
        candidate.entry_count = best["entry_count"]
        candidate.extraction_rate = best["extraction_rate"]
        candidate.latest_entry_at = best["latest"]
        candidate.sample_headlines = [
            {"title": str(getattr(entry, "title", ""))[:300], "url": entry.link}
            for entry in best["entries"][:3]
        ]
        candidate.last_checked_at = datetime.now(UTC)
        settings = get_settings()
        hard_gates = passes_auto_approve_gates(
            score=candidate.score,
            threshold=settings.source_auto_approve_score,
            is_https=urlparse(candidate.feed_url).scheme == "https",
            entry_count=best["entry_count"],
            age_days=best["age_days"],
            publisher_ratio=best["publisher_ratio"],
            extraction_successes=best["extraction_successes"],
            referring_source_count=candidate.source_count,
        )
        source = None
        if hard_gates:
            candidate.status = "auto_approved"
            source = await promote_candidate(db, candidate)
        elif candidate.score >= 60:
            candidate.status = "pending"
        else:
            candidate.status = "rejected"
            candidate.failure_reason = "Candidate score is below 60"
        await db.commit()
        return {
            "candidate_id": str(candidate.id),
            "status": candidate.status,
            "score": candidate.score,
            "source_id": str(source.id) if source else None,
        }
    except UnsafeUrlError as exc:
        candidate.status = "rejected"
        candidate.failure_reason = str(exc)[:500]
        candidate.last_checked_at = datetime.now(UTC)
        await db.commit()
        return {"candidate_id": str(candidate.id), "status": "rejected", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - transient discovery errors are persisted
        candidate.retry_count += 1
        candidate.status = "failed" if candidate.retry_count < 3 else "rejected"
        candidate.failure_reason = str(exc)[:500]
        candidate.last_checked_at = datetime.now(UTC)
        await db.commit()
        return {"candidate_id": str(candidate.id), "status": candidate.status, "error": str(exc)}


async def discover_from_recent_articles(db: AsyncSession, limit: int | None = None) -> dict:
    article_limit = limit or get_settings().source_discovery_article_limit
    article_ids = (
        await db.scalars(
            select(Article.id)
            .where(Article.raw_object_key.is_not(None))
            .order_by(Article.crawled_at.desc())
            .limit(article_limit)
        )
    ).all()
    store = ObjectStore()
    candidate_ids: set[UUID] = set()
    failures = 0
    for article_id in article_ids:
        try:
            article = await db.get(Article, article_id)
            if article is None:
                continue
            source = await db.get(Source, article.source_id)
            if not source or not article.raw_object_key:
                continue
            raw_html = await store.get_text(article.raw_object_key)
            candidate_ids.update(await record_outbound_candidates(db, article, source, raw_html))
            await db.commit()
        except Exception as exc:  # noqa: BLE001 - one raw object cannot block backfill
            logger.warning("source discovery backfill failed for %s: %s", article_id, exc)
            await db.rollback()
            failures += 1
    return {
        "articles_scanned": len(article_ids),
        "candidates_found": len(candidate_ids),
        "candidate_ids": [str(item) for item in candidate_ids],
        "failures": failures,
    }

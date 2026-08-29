import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import feedparser
import httpx
import trafilatura
from dateutil import parser as date_parser

VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


@dataclass
class CrawledArticle:
    url: str
    title: str
    body: str
    author: str | None
    published_at: datetime | None
    raw_html: str
    content_hash: str


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def article_hash(title: str, body: str) -> str:
    normalized = f"{normalize_text(title).lower()}\n{normalize_text(body).lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = date_parser.parse(value)
    # Vietnamese publishers frequently omit timezone information. Treat a naive
    # timestamp as publication-local time rather than the server's local timezone.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=VIETNAM_TZ)
    return parsed.astimezone(timezone.utc)


async def fetch_article(url: str) -> CrawledArticle:
    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "IdeasHub/0.1 research crawler"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()

    html = response.text
    document = trafilatura.bare_extraction(
        html,
        url=str(response.url),
        with_metadata=True,
        include_comments=False,
        include_tables=False,
    )
    if document is None:
        raise ValueError(f"Could not extract article from {url}")
    result = document.as_dict()
    if not result.get("text"):
        raise ValueError(f"Could not extract article body from {url}")

    title = normalize_text(result.get("title") or urlparse(url).path.rsplit("/", 1)[-1])
    body = normalize_text(result["text"])
    return CrawledArticle(
        url=str(response.url),
        title=title,
        body=body,
        author=result.get("author"),
        published_at=parse_published_at(result.get("date")),
        raw_html=html,
        content_hash=article_hash(title, body),
    )


async def discover_feed_urls(feed_url: str, limit: int = 30) -> list[str]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(feed_url)
        response.raise_for_status()
    feed = feedparser.loads(response.content)
    return [entry.link for entry in feed.entries[:limit] if getattr(entry, "link", None)]

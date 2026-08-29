import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import httpx
import trafilatura
from dateutil import parser as date_parser


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


async def fetch_article(url: str) -> CrawledArticle:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": "IdeasHub/0.1 research crawler"}) as client:
        response = await client.get(url)
        response.raise_for_status()
    html = response.text
    result = trafilatura.bare_extraction(html, url=str(response.url), with_metadata=True, include_comments=False, include_tables=False)
    if not result or not result.get("text"):
        raise ValueError(f"Could not extract article body from {url}")
    title = normalize_text(result.get("title") or urlparse(url).path.rsplit("/", 1)[-1])
    body = normalize_text(result["text"])
    published = result.get("date")
    published_at = date_parser.parse(published).astimezone(timezone.utc) if published else None
    return CrawledArticle(
        url=str(response.url),
        title=title,
        body=body,
        author=result.get("author"),
        published_at=published_at,
        raw_html=html,
        content_hash=article_hash(title, body),
    )


async def discover_feed_urls(feed_url: str, limit: int = 30) -> list[str]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(feed_url)
        response.raise_for_status()
    feed = feedparser.loads(response.content)
    return [entry.link for entry in feed.entries[:limit] if getattr(entry, "link", None)]

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Protocol

import feedparser
import httpx

from ideas_hub.models import Source

MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_FEED_ENTRIES = 500
MAX_SITEMAP_URLS = 1000
MAX_SITEMAP_CHILDREN = 8
USER_AGENT = "IdeasHub/0.2 research crawler"


@dataclass(frozen=True)
class DiscoveryBatch:
    urls: list[str]
    source_kind: str


class SourceAdapter(Protocol):
    async def discover(self, source: Source, limit: int | None = None) -> DiscoveryBatch: ...


async def _fetch_bytes(
    url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    max_bytes: int = MAX_SOURCE_BYTES,
) -> bytes:
    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
        transport=transport,
    ) as client, client.stream("GET", url) as response:
        response.raise_for_status()
        declared = int(response.headers.get("content-length") or 0)
        if declared > max_bytes:
            raise ValueError(f"Source response exceeds {max_bytes} bytes")
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > max_bytes:
                raise ValueError(f"Source response exceeds {max_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks)


class RSSSourceAdapter:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def discover(self, source: Source, limit: int | None = None) -> DiscoveryBatch:
        if not source.feed_url:
            raise ValueError("RSS source requires feed_url")
        content = await _fetch_bytes(source.feed_url, transport=self.transport)
        parsed = feedparser.parse(content)
        if not parsed.entries:
            raise ValueError(f"RSS/Atom feed has no entries: {source.feed_url}")

        urls = [
            str(entry.link)
            for entry in parsed.entries[:MAX_FEED_ENTRIES]
            if getattr(entry, "link", None)
        ]
        urls = list(dict.fromkeys(urls))
        if limit is not None:
            urls = urls[:limit]
        return DiscoveryBatch(urls=urls, source_kind="rss")


class SitemapSourceAdapter:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def _parse_sitemap(self, url: str) -> tuple[str, list[tuple[str, str]]]:
        content = await _fetch_bytes(url, transport=self.transport)
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise ValueError(f"Invalid sitemap XML: {url}") from exc

        kind = root.tag.rsplit("}", 1)[-1].lower()
        rows: list[tuple[str, str]] = []
        for child in root:
            child_kind = child.tag.rsplit("}", 1)[-1].lower()
            if kind == "urlset" and child_kind != "url":
                continue
            if kind == "sitemapindex" and child_kind != "sitemap":
                continue
            loc = ""
            lastmod = ""
            for node in child:
                field = node.tag.rsplit("}", 1)[-1].lower()
                if field == "loc" and node.text:
                    loc = node.text.strip()
                elif field == "lastmod" and node.text:
                    lastmod = node.text.strip()
            if loc:
                rows.append((loc, lastmod))
        if kind not in {"urlset", "sitemapindex"}:
            raise ValueError(f"Unsupported sitemap root: {kind or root.tag}")
        return kind, rows

    async def discover(self, source: Source, limit: int | None = None) -> DiscoveryBatch:
        if not source.feed_url:
            raise ValueError("Sitemap source requires feed_url pointing to sitemap XML")
        kind, rows = await self._parse_sitemap(source.feed_url)
        if kind == "sitemapindex":
            # Prefer recently modified child maps and cap fan-out so one giant index
            # cannot monopolize a worker. A later crawl can use a more specialized
            # adapter when a publisher needs deeper history.
            rows.sort(key=lambda item: item[1], reverse=True)
            page_rows: list[tuple[str, str]] = []
            for child_url, _ in rows[:MAX_SITEMAP_CHILDREN]:
                child_kind, child_rows = await self._parse_sitemap(child_url)
                if child_kind == "urlset":
                    page_rows.extend(child_rows)
            rows = page_rows

        rows.sort(key=lambda item: item[1], reverse=True)
        urls = list(dict.fromkeys(url for url, _ in rows[:MAX_SITEMAP_URLS]))
        if limit is not None:
            urls = urls[:limit]
        return DiscoveryBatch(urls=urls, source_kind="sitemap")


def get_source_adapter(source: Source) -> SourceAdapter:
    # `news` is the legacy value used by existing databases and auto-promoted
    # source candidates. Keep it as an RSS alias while new records can be explicit.
    if source.source_type in {"news", "rss"}:
        return RSSSourceAdapter()
    if source.source_type == "sitemap":
        return SitemapSourceAdapter()
    raise ValueError(f"Unsupported source_type: {source.source_type}")

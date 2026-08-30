from types import SimpleNamespace

import httpx
import pytest

from ideas_hub.source_adapters import RSSSourceAdapter, SitemapSourceAdapter, get_source_adapter


@pytest.mark.asyncio
async def test_rss_adapter_scans_full_feed_when_limit_is_none():
    payload = b"""
    <rss version='2.0'><channel>
      <item><guid>a</guid><link>https://news.vn/a</link></item>
      <item><guid>b</guid><link>https://news.vn/b</link></item>
      <item><guid>c</guid><link>https://news.vn/c</link></item>
    </channel></rss>
    """

    def handler(request):
        return httpx.Response(200, content=payload, request=request)

    source = SimpleNamespace(feed_url="https://news.vn/rss.xml")
    batch = await RSSSourceAdapter(httpx.MockTransport(handler)).discover(source, limit=None)
    assert batch.source_kind == "rss"
    assert batch.urls == ["https://news.vn/a", "https://news.vn/b", "https://news.vn/c"]


@pytest.mark.asyncio
async def test_rss_adapter_respects_bootstrap_limit():
    payload = b"""
    <rss version='2.0'><channel>
      <item><link>https://news.vn/a</link></item>
      <item><link>https://news.vn/b</link></item>
    </channel></rss>
    """

    def handler(request):
        return httpx.Response(200, content=payload, request=request)

    source = SimpleNamespace(feed_url="https://news.vn/rss.xml")
    batch = await RSSSourceAdapter(httpx.MockTransport(handler)).discover(source, limit=1)
    assert batch.urls == ["https://news.vn/a"]


@pytest.mark.asyncio
async def test_sitemap_adapter_orders_recent_urls_and_follows_index():
    root = b"""
    <sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
      <sitemap><loc>https://news.vn/old.xml</loc><lastmod>2026-08-28</lastmod></sitemap>
      <sitemap><loc>https://news.vn/new.xml</loc><lastmod>2026-08-30</lastmod></sitemap>
    </sitemapindex>
    """
    new_map = b"""
    <urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
      <url><loc>https://news.vn/b</loc><lastmod>2026-08-30T09:00:00+07:00</lastmod></url>
      <url><loc>https://news.vn/a</loc><lastmod>2026-08-30T10:00:00+07:00</lastmod></url>
    </urlset>
    """
    old_map = b"""
    <urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
      <url><loc>https://news.vn/old</loc><lastmod>2026-08-28</lastmod></url>
    </urlset>
    """

    def handler(request):
        if str(request.url).endswith("sitemap.xml"):
            return httpx.Response(200, content=root, request=request)
        if str(request.url).endswith("new.xml"):
            return httpx.Response(200, content=new_map, request=request)
        return httpx.Response(200, content=old_map, request=request)

    source = SimpleNamespace(feed_url="https://news.vn/sitemap.xml")
    batch = await SitemapSourceAdapter(httpx.MockTransport(handler)).discover(source, limit=2)
    assert batch.source_kind == "sitemap"
    assert batch.urls == ["https://news.vn/a", "https://news.vn/b"]


def test_adapter_selection_supports_legacy_news_and_explicit_sitemap():
    assert isinstance(get_source_adapter(SimpleNamespace(source_type="news")), RSSSourceAdapter)
    assert isinstance(get_source_adapter(SimpleNamespace(source_type="rss")), RSSSourceAdapter)
    assert isinstance(
        get_source_adapter(SimpleNamespace(source_type="sitemap")), SitemapSourceAdapter
    )
    with pytest.raises(ValueError):
        get_source_adapter(SimpleNamespace(source_type="api"))

import feedparser
import httpx
import pytest

from ideas_hub.bootstrap import DEFAULT_SOURCES
from ideas_hub.source_discovery import (
    UnsafeUrlError,
    calculate_candidate_score,
    extract_external_links,
    feed_links_from_html,
    is_parsed_feed_valid,
    is_public_ip,
    normalize_url,
    passes_auto_approve_gates,
    safe_fetch,
    validate_public_url,
)


def test_default_sources_are_40_unique_market_feeds():
    feeds = [source["feed_url"] for source in DEFAULT_SOURCES]
    domains = [source["domain"] for source in DEFAULT_SOURCES]
    assert len(DEFAULT_SOURCES) == 40
    assert len(feeds) == len(set(feeds))
    assert len(domains) == len(set(domains))
    assert all(feed.startswith("https://") for feed in feeds)


def test_normalize_url_removes_fragment_and_rejects_unsafe_ports():
    assert normalize_url("HTTPS://Example.COM/a?q=1#section") == "https://example.com/a?q=1"
    with pytest.raises(UnsafeUrlError):
        normalize_url("https://example.com:8080/feed")
    with pytest.raises(UnsafeUrlError):
        normalize_url("file:///etc/passwd")


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "192.0.2.1",
        "224.0.0.1",
        "0.0.0.0",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_all_non_public_ip_groups_are_blocked(address):
    assert not is_public_ip(address)


@pytest.mark.asyncio
async def test_literal_private_ip_is_rejected_before_fetch():
    with pytest.raises(UnsafeUrlError):
        await validate_public_url("http://169.254.169.254/latest/meta-data")


@pytest.mark.asyncio
async def test_redirect_target_is_revalidated_for_ssrf():
    async def redirect_to_metadata(request):
        return httpx.Response(
            302,
            headers={"location": "http://169.254.169.254/latest/meta-data"},
            request=request,
        )

    with pytest.raises(UnsafeUrlError):
        await safe_fetch(
            "https://93.184.216.34/",
            transport=httpx.MockTransport(redirect_to_metadata),
        )


def test_extract_external_links_deduplicates_domains_and_ignores_media_social():
    html = """
    <a href="https://publisher.vn/story">first</a>
    <a href="https://publisher.vn/other">same publisher</a>
    <a href="https://facebook.com/page">social</a>
    <a href="https://cdn.vn/report.pdf">file</a>
    <a href="/internal">internal</a>
    """
    assert extract_external_links(html, "https://origin.vn/article") == [
        "https://publisher.vn/story"
    ]


def test_feed_discovery_reads_rss_and_atom_alternates():
    html = b"""
    <link rel="alternate" type="application/rss+xml" href="/rss.xml">
    <link rel="alternate" type="application/atom+xml" href="https://news.vn/atom.xml">
    """
    assert feed_links_from_html(html, "https://news.vn/topic") == [
        "https://news.vn/rss.xml",
        "https://news.vn/atom.xml",
    ]


def test_html_with_article_links_is_not_accepted_as_a_feed():
    parsed = feedparser.parse(b"<html><a href='https://news.vn/a'>story</a></html>")
    assert not is_parsed_feed_valid(parsed)


def test_score_85_and_hard_gates_are_independent():
    breakdown = calculate_candidate_score(
        entry_count=50,
        age_days=1,
        extraction_rate=0.8,
        relevance=0.3,
        referring_source_count=2,
        is_https=True,
    )
    assert sum(breakdown.values()) == 95
    assert passes_auto_approve_gates(
        score=95,
        threshold=85,
        is_https=True,
        entry_count=50,
        age_days=1,
        publisher_ratio=0.9,
        extraction_successes=2,
        referring_source_count=2,
    )
    assert not passes_auto_approve_gates(
        score=95,
        threshold=85,
        is_https=True,
        entry_count=50,
        age_days=1,
        publisher_ratio=0.9,
        extraction_successes=2,
        referring_source_count=1,
    )

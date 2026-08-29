from datetime import UTC

from ideas_hub.crawler import article_hash, parse_published_at


def test_article_hash_normalizes_whitespace_and_case():
    assert article_hash("Hello", "A   B") == article_hash("hello", "A B")


def test_naive_vietnam_publication_time_is_converted_to_utc():
    parsed = parse_published_at("2026-08-29 17:00:00")
    assert parsed is not None
    assert parsed.tzinfo == UTC
    assert parsed.hour == 10

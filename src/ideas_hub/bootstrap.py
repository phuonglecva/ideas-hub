from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ideas_hub.models import Source


DEFAULT_SOURCES = (
    {
        "name": "VnExpress Kinh doanh",
        "domain": "vnexpress.net/kinh-doanh",
        "feed_url": "https://vnexpress.net/rss/kinh-doanh.rss",
        "trust_score": 0.85,
    },
    {
        "name": "VnExpress Khoa học công nghệ",
        "domain": "vnexpress.net/khoa-hoc-cong-nghe",
        "feed_url": "https://vnexpress.net/rss/khoa-hoc-cong-nghe.rss",
        "trust_score": 0.85,
    },
    {
        "name": "Tuổi Trẻ Kinh doanh",
        "domain": "tuoitre.vn/kinh-doanh",
        "feed_url": "https://tuoitre.vn/kinh-doanh.rss",
        "trust_score": 0.8,
    },
    {
        "name": "Tuổi Trẻ Công nghệ",
        "domain": "tuoitre.vn/nhip-song-so",
        "feed_url": "https://tuoitre.vn/nhip-song-so.rss",
        "trust_score": 0.8,
    },
    {
        "name": "Thanh Niên Kinh tế",
        "domain": "thanhnien.vn/kinh-te",
        "feed_url": "https://thanhnien.vn/rss/kinh-te.rss",
        "trust_score": 0.8,
    },
    {
        "name": "Thanh Niên Công nghệ",
        "domain": "thanhnien.vn/cong-nghe",
        "feed_url": "https://thanhnien.vn/rss/cong-nghe.rss",
        "trust_score": 0.8,
    },
    {
        "name": "Thanh Niên Khởi nghiệp",
        "domain": "thanhnien.vn/khoi-nghiep",
        "feed_url": "https://thanhnien.vn/rss/gioi-tre/khoi-nghiep.rss",
        "trust_score": 0.8,
    },
    {
        "name": "Dân Trí Kinh doanh",
        "domain": "dantri.com.vn/kinh-doanh",
        "feed_url": "https://dantri.com.vn/rss/kinh-doanh.rss",
        "trust_score": 0.8,
    },
    {
        "name": "Dân Trí Công nghệ",
        "domain": "dantri.com.vn/cong-nghe",
        "feed_url": "https://dantri.com.vn/rss/cong-nghe.rss",
        "trust_score": 0.8,
    },
    {
        "name": "Dân Trí Lao động - Việc làm",
        "domain": "dantri.com.vn/lao-dong-viec-lam",
        "feed_url": "https://dantri.com.vn/rss/lao-dong-viec-lam.rss",
        "trust_score": 0.8,
    },
    {
        "name": "Nhân Dân Kinh tế",
        "domain": "nhandan.vn/kinh-te",
        "feed_url": "https://nhandan.vn/rss/kinhte-1185.rss",
        "trust_score": 0.9,
    },
    {
        "name": "Nhân Dân Khoa học - Công nghệ",
        "domain": "nhandan.vn/khoa-hoc-cong-nghe",
        "feed_url": "https://nhandan.vn/rss/khoahoc-congnghe-1292.rss",
        "trust_score": 0.9,
    },
    {
        "name": "VietnamPlus Kinh tế",
        "domain": "vietnamplus.vn/kinh-te",
        "feed_url": "https://www.vietnamplus.vn/rss/kinhte-311.rss",
        "trust_score": 0.9,
    },
    {
        "name": "VietnamPlus Doanh nghiệp",
        "domain": "vietnamplus.vn/doanh-nghiep",
        "feed_url": "https://www.vietnamplus.vn/rss/kinhte/doanhnghiep-345.rss",
        "trust_score": 0.9,
    },
    {
        "name": "VietnamPlus Công nghệ",
        "domain": "vietnamplus.vn/cong-nghe",
        "feed_url": "https://www.vietnamplus.vn/rss/congnghe-212.rss",
        "trust_score": 0.9,
    },
    {
        "name": "VietnamNet Kinh doanh",
        "domain": "vietnamnet.vn/kinh-doanh",
        "feed_url": "https://vietnamnet.vn/rss/kinh-doanh.rss",
        "trust_score": 0.8,
    },
    {
        "name": "VietnamNet Công nghệ",
        "domain": "vietnamnet.vn/cong-nghe",
        "feed_url": "https://vietnamnet.vn/rss/cong-nghe.rss",
        "trust_score": 0.8,
    },
)


async def seed_default_sources(db: AsyncSession) -> list[Source]:
    """Create the starter RSS registry once and return only newly created rows."""
    existing_domains = set((await db.scalars(select(Source.domain))).all())
    created = [
        Source(source_type="news", **source)
        for source in DEFAULT_SOURCES
        if source["domain"] not in existing_domains
    ]
    if created:
        db.add_all(created)
        await db.commit()
        for source in created:
            await db.refresh(source)
    return created

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ideas_hub.models import Source


DEFAULT_SOURCES = (
    {"name": "VnExpress Kinh doanh", "domain": "vnexpress.net/kinh-doanh", "feed_url": "https://vnexpress.net/rss/kinh-doanh.rss", "trust_score": 0.85},
    {"name": "VnExpress Khoa học công nghệ", "domain": "vnexpress.net/khoa-hoc-cong-nghe", "feed_url": "https://vnexpress.net/rss/khoa-hoc-cong-nghe.rss", "trust_score": 0.85},
    {"name": "Tuổi Trẻ Kinh doanh", "domain": "tuoitre.vn/kinh-doanh", "feed_url": "https://tuoitre.vn/kinh-doanh.rss", "trust_score": 0.8},
    {"name": "Tuổi Trẻ Công nghệ", "domain": "tuoitre.vn/nhip-song-so", "feed_url": "https://tuoitre.vn/nhip-song-so.rss", "trust_score": 0.8},
    {"name": "Thanh Niên Kinh tế", "domain": "thanhnien.vn/kinh-te", "feed_url": "https://thanhnien.vn/rss/kinh-te.rss", "trust_score": 0.8},
    {"name": "Thanh Niên Công nghệ", "domain": "thanhnien.vn/cong-nghe", "feed_url": "https://thanhnien.vn/rss/cong-nghe.rss", "trust_score": 0.8},
    {"name": "Thanh Niên Khởi nghiệp", "domain": "thanhnien.vn/khoi-nghiep", "feed_url": "https://thanhnien.vn/rss/gioi-tre/khoi-nghiep.rss", "trust_score": 0.8},
    {"name": "Dân Trí Kinh doanh", "domain": "dantri.com.vn/kinh-doanh", "feed_url": "https://dantri.com.vn/rss/kinh-doanh.rss", "trust_score": 0.8},
    {"name": "Dân Trí Công nghệ", "domain": "dantri.com.vn/cong-nghe", "feed_url": "https://dantri.com.vn/rss/cong-nghe.rss", "trust_score": 0.8},
    {"name": "Dân Trí Lao động - Việc làm", "domain": "dantri.com.vn/lao-dong-viec-lam", "feed_url": "https://dantri.com.vn/rss/lao-dong-viec-lam.rss", "trust_score": 0.8},
    {"name": "Nhân Dân Kinh tế", "domain": "nhandan.vn/kinh-te", "feed_url": "https://nhandan.vn/rss/kinhte-1185.rss", "trust_score": 0.9},
    {"name": "Nhân Dân Khoa học - Công nghệ", "domain": "nhandan.vn/khoa-hoc-cong-nghe", "feed_url": "https://nhandan.vn/rss/khoahoc-congnghe-1292.rss", "trust_score": 0.9},
    {"name": "VietnamPlus Kinh tế", "domain": "vietnamplus.vn/kinh-te", "feed_url": "https://www.vietnamplus.vn/rss/kinhte-311.rss", "trust_score": 0.9},
    {"name": "VietnamPlus Doanh nghiệp", "domain": "vietnamplus.vn/doanh-nghiep", "feed_url": "https://www.vietnamplus.vn/rss/kinhte/doanhnghiep-345.rss", "trust_score": 0.9},
    {"name": "VietnamPlus Công nghệ", "domain": "vietnamplus.vn/cong-nghe", "feed_url": "https://www.vietnamplus.vn/rss/congnghe-212.rss", "trust_score": 0.9},
    {"name": "VietnamNet Kinh doanh", "domain": "vietnamnet.vn/kinh-doanh", "feed_url": "https://vietnamnet.vn/rss/kinh-doanh.rss", "trust_score": 0.8},
    {"name": "VietnamNet Công nghệ", "domain": "vietnamnet.vn/cong-nghe", "feed_url": "https://vietnamnet.vn/rss/cong-nghe.rss", "trust_score": 0.8},
    {"name": "CafeF Chứng khoán", "domain": "cafef.vn/chung-khoan", "feed_url": "https://cafef.vn/thi-truong-chung-khoan.rss", "trust_score": 0.78},
    {"name": "CafeF Tài chính - Ngân hàng", "domain": "cafef.vn/tai-chinh-ngan-hang", "feed_url": "https://cafef.vn/tai-chinh-ngan-hang.rss", "trust_score": 0.78},
    {"name": "CafeF Vĩ mô - Đầu tư", "domain": "cafef.vn/vi-mo-dau-tu", "feed_url": "https://cafef.vn/vi-mo-dau-tu.rss", "trust_score": 0.78},
    {"name": "CafeF Kinh tế số", "domain": "cafef.vn/kinh-te-so", "feed_url": "https://cafef.vn/kinh-te-so.rss", "trust_score": 0.78},
    {"name": "Báo Đầu tư Kinh doanh", "domain": "baodautu.vn/kinh-doanh", "feed_url": "https://baodautu.vn/kinh-doanh.rss", "trust_score": 0.86},
    {"name": "Báo Đầu tư Tài chính", "domain": "baodautu.vn/dau-tu-tai-chinh", "feed_url": "https://baodautu.vn/dau-tu-tai-chinh.rss", "trust_score": 0.86},
    {"name": "Báo Đầu tư Kinh tế số", "domain": "baodautu.vn/kinh-te-so", "feed_url": "https://baodautu.vn/kinh-te-so.rss", "trust_score": 0.86},
    {"name": "Báo Đầu tư Khoa học - Công nghệ", "domain": "baodautu.vn/khoa-hoc-va-cong-nghe", "feed_url": "https://baodautu.vn/khoa-hoc-va-cong-nghe.rss", "trust_score": 0.86},
    {"name": "Báo Đầu tư Pháp luật", "domain": "baodautu.vn/dau-tu-va-phap-luat", "feed_url": "https://baodautu.vn/dau-tu-va-phap-luat.rss", "trust_score": 0.86},
    {"name": "VTV Kinh tế", "domain": "vtv.vn/kinh-te", "feed_url": "https://vtv.vn/rss/kinh-te.rss", "trust_score": 0.84},
    {"name": "VTV Doanh nghiệp thời AI", "domain": "vtv.vn/doanh-nghiep-thoi-ai", "feed_url": "https://vtv.vn/rss/vuon-minh-bang-ai/doanh-nghiep-thoi-ai.rss", "trust_score": 0.84},
    {"name": "VTV Thời đại AI", "domain": "vtv.vn/thoi-dai-ai", "feed_url": "https://vtv.vn/rss/vuon-minh-bang-ai/thoi-dai-ai.rss", "trust_score": 0.84},
    {"name": "VTC News Kinh tế", "domain": "vtcnews.vn/kinh-te", "feed_url": "https://vtcnews.vn/rss/kinh-te.rss", "trust_score": 0.8},
    {"name": "VTC News Khoa học - Công nghệ", "domain": "vtcnews.vn/khoa-hoc-cong-nghe", "feed_url": "https://vtcnews.vn/rss/khoa-hoc-cong-nghe.rss", "trust_score": 0.8},
    {"name": "VTC News Doanh nghiệp - Doanh nhân", "domain": "vtcnews.vn/doanh-nghiep-doanh-nhan", "feed_url": "https://vtcnews.vn/rss/doanh-nghiep-doanh-nhan.rss", "trust_score": 0.8},
    {"name": "VnEconomy Tài chính", "domain": "vneconomy.vn/tai-chinh", "feed_url": "https://vneconomy.vn/tai-chinh.rss", "trust_score": 0.84},
    {"name": "VnEconomy Chứng khoán", "domain": "vneconomy.vn/chung-khoan", "feed_url": "https://vneconomy.vn/chung-khoan.rss", "trust_score": 0.84},
    {"name": "VnEconomy Kinh tế số", "domain": "vneconomy.vn/kinh-te-so", "feed_url": "https://vneconomy.vn/kinh-te-so.rss", "trust_score": 0.84},
    {"name": "VnEconomy Đầu tư", "domain": "vneconomy.vn/dau-tu", "feed_url": "https://vneconomy.vn/dau-tu.rss", "trust_score": 0.84},
    {"name": "VnEconomy Công nghệ & Startup", "domain": "vneconomy.vn/cong-nghe-startup", "feed_url": "https://vneconomy.vn/cong-nghe-startup.rss", "trust_score": 0.84},
    {"name": "Người Đưa Tin Kinh tế", "domain": "nguoiduatin.vn/kinh-te", "feed_url": "https://www.nguoiduatin.vn/rss/kinh-te.rss", "trust_score": 0.74},
    {"name": "Người Đưa Tin Chính sách", "domain": "nguoiduatin.vn/chinh-sach", "feed_url": "https://www.nguoiduatin.vn/rss/toan-canh/chinh-sach.rss", "trust_score": 0.74},
    {"name": "Người Đưa Tin Công nghệ", "domain": "nguoiduatin.vn/cong-nghe", "feed_url": "https://www.nguoiduatin.vn/rss/kinh-te/cong-nghe.rss", "trust_score": 0.74},
)


async def seed_default_sources(db: AsyncSession) -> list[Source]:
    """Create the starter RSS registry once and return only newly created rows."""
    existing_domains = set((await db.scalars(select(Source.domain))).all())
    created = [
        Source(source_type="rss", **source)
        for source in DEFAULT_SOURCES
        if source["domain"] not in existing_domains
    ]
    if created:
        db.add_all(created)
        await db.commit()
        for source in created:
            await db.refresh(source)
    return created

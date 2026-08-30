from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ideas_hub.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from ideas_hub import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # create_all does not retrofit constraints when upgrading an existing
        # local database created by an earlier development build.
        candidate_domain_index = await conn.scalar(
            text("SELECT to_regclass('public.uq_source_candidate_domain_idx')")
        )
        if candidate_domain_index is None:
            await conn.execute(
                text(
                    "CREATE UNIQUE INDEX uq_source_candidate_domain_idx "
                    "ON source_candidates (domain)"
                )
            )

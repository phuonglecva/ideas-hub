from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ideas_hub.api import router
from ideas_hub.bootstrap import seed_default_sources
from ideas_hub.config import get_settings
from ideas_hub.db import SessionLocal, init_db
from ideas_hub.storage import ObjectStore
from ideas_hub.worker import crawl_source_task


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await ObjectStore().ensure_bucket()
    settings = get_settings()
    if settings.seed_default_sources:
        async with SessionLocal() as db:
            created_sources = await seed_default_sources(db)
        # Make a fresh install useful immediately. Subsequent crawls are handled
        # by Celery Beat, and reloads do not enqueue existing sources again.
        for source in created_sources:
            crawl_source_task.delay(
                str(source.id), settings.source_bootstrap_limit, None, "bootstrap"
            )
    yield


app = FastAPI(title="Ideas Hub", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3333"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

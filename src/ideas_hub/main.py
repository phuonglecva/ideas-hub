from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ideas_hub.api import router
from ideas_hub.db import init_db
from ideas_hub.storage import ObjectStore


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    try:
        await ObjectStore().ensure_bucket()
    except Exception:
        pass
    yield


app = FastAPI(title="Ideas Hub", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

"""
FastAPI application entrypoint. Route modules only declare endpoints;
all logic lives in services/repositories/schedulers per §41.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import accounts, calendar, captions, dashboard, demo_dashboard, health, inventory, logs, masters, media, publishing, variants
from backend.core.config import settings
from backend.workers import publishing_worker, watcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    watcher.start()  # background poll of content/masters/ (§10) -- Phase 2
    publishing_worker.start()  # background poll of due SCHEDULED posts (§18/§51) -- Phase 5
    yield
    watcher.stop()
    publishing_worker.stop()


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(accounts.router)
app.include_router(masters.router)
app.include_router(variants.router)
app.include_router(captions.router)
app.include_router(inventory.router)
app.include_router(dashboard.router)
app.include_router(calendar.router)
app.include_router(publishing.router)
app.include_router(media.router)
app.include_router(demo_dashboard.router)
app.include_router(logs.router)


@app.get("/")
def root():
    return {"app": settings.APP_NAME, "environment": settings.ENVIRONMENT, "docs": "/docs"}

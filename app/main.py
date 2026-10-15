from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.database import Base, engine, migrate_existing_sqlite_schema
from app.routers import ai, auth, calendar, collaboration, event_sync, invitations, learning, marketplace, portfolio
from app.seed import seed


@asynccontextmanager
async def lifespan(_app: FastAPI):
    migrate_existing_sqlite_schema()
    Base.metadata.create_all(bind=engine)
    seed()
    yield


app = FastAPI(
    title="HackMate API",
    description="A student-focused platform for forming balanced hackathon teams.",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(auth.router, prefix="/api")
app.include_router(marketplace.router, prefix="/api")
app.include_router(collaboration.router, prefix="/api")
app.include_router(learning.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(invitations.router, prefix="/api")
app.include_router(calendar.router, prefix="/api")
app.include_router(event_sync.router, prefix="/api")

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health", tags=["System"])
def health():
    return {"status": "ok"}

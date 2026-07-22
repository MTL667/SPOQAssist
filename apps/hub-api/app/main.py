from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin_ai import router as admin_ai_router
from app.api.admin_ops import router as admin_ops_router
from app.api.analyze import router as analyze_router
from app.api.confirm import router as confirm_router
from app.api.feedback import router as feedback_router
from app.api.health import router as health_router
from app.api.mailbox_profiles import router as mailbox_profiles_router
from app.api.me import router as me_router
from app.core.errors import AppError, RequestIdMiddleware, app_error_handler
from app.core.logging import configure_logging
from app.db.session import init_db

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="SpoqSense Hub API",
    version="0.2.0",
    description="Local Mac Studio hub for SpoqSense (Epics 1–4).",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://localhost:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(AppError, app_error_handler)

app.include_router(health_router)
app.include_router(me_router)
app.include_router(mailbox_profiles_router)
app.include_router(analyze_router)
app.include_router(feedback_router)
app.include_router(confirm_router)
app.include_router(admin_ai_router)
app.include_router(admin_ops_router)


@app.get("/")
async def root() -> dict:
    return {"service": "spoqsense-hub-api", "docs": "/docs"}

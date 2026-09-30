import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1.router import api_router
from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging
from backend.app.database.base import Base
from backend.app.database.seed import seed_database
from backend.app.database.session import SessionLocal, engine
import backend.app.models  # noqa: F401 - registers ORM tables with metadata

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    # create_all is intentionally opt-in for lightweight local development.
    # Production containers run Alembic in their entrypoint before Uvicorn.
    if settings.auto_create_schema:
        logger.warning("AUTO_CREATE_SCHEMA is enabled; this is for local development only")
        Base.metadata.create_all(bind=engine)
    if settings.seed_database:
        with SessionLocal() as db:
            seed_database(db)
    logger.info("Application startup complete")
    yield
    logger.info("Application shutdown complete")


app = FastAPI(title="Intelligent Hotel Platform API", version="0.2.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    """Provide a stable landing response for service and deployment checks."""
    return {
        "service": "Intelligent Hotel Platform API",
        "status": "running",
        "health": f"{settings.api_v1_prefix}/health",
        "docs": "/docs",
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation failed",
            "errors": jsonable_encoder(exc.errors(), custom_encoder={ValueError: str}),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

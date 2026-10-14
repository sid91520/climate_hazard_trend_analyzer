"""FastAPI entry point. Run locally with:  uvicorn app.main:app --reload"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.config import get_settings
from app.db import mongo
from app.errors import AppError
from app.rate_limit import limiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

settings = get_settings()

if settings.environment == "production" and "*" in settings.cors_origin_list:
    # Fail fast at startup rather than silently serving every origin.
    raise RuntimeError("CORS_ORIGINS must not be '*' in production")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await mongo.connect()
    yield
    await mongo.close()


app = FastAPI(
    title="Climate Hazard Trend Analyzer",
    version="1.0.0",
    description="Heatwave frequency, duration and intensity trends from ERA5 reanalysis data.",
    lifespan=lifespan,
)
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET"],  # the API is read-only
    allow_headers=["*"],
)

app.include_router(router)


# ------------------------------------------------------------ error handlers
# Every error leaves the API in the same shape: {"error": {"code": ..., "message": ...}}


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


@app.exception_handler(AppError)
async def handle_app_error(_request: Request, exc: AppError):
    return error_response(exc.status_code, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_request: Request, exc: RequestValidationError):
    messages = []
    for error in exc.errors():
        # loc looks like ("query", "lat"); model-level checks have no field name.
        field = ".".join(str(part) for part in error["loc"] if part != "query")
        text = error["msg"].removeprefix("Value error, ")
        messages.append(f"{field}: {text}" if field else text)
    return error_response(422, "validation_error", "; ".join(messages))


@app.exception_handler(RateLimitExceeded)
async def handle_rate_limit(_request: Request, exc: RateLimitExceeded):
    return error_response(429, "rate_limited", f"Too many requests (limit: {exc.detail}). Please wait a minute.")


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(_request: Request, exc: StarletteHTTPException):
    code = "not_found" if exc.status_code == 404 else "http_error"
    return error_response(exc.status_code, code, str(exc.detail))


@app.exception_handler(Exception)
async def handle_unexpected_error(_request: Request, exc: Exception):
    # Log the details for us; never leak a stack trace to the client.
    logger.exception("Unhandled error", exc_info=exc)
    return error_response(500, "internal_error", "Something went wrong on our side.")

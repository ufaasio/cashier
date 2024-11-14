import json
import logging
from contextlib import asynccontextmanager

import fastapi
import pydantic
from core import exceptions
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from json_advanced import dumps
from usso.exceptions import USSOException

from . import config, db, middlewares


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):  # type: ignore
    """Initialize application services."""
    await db.init_db()
    config.Settings().config_logger()

    logging.info("Startup complete")
    yield
    logging.info("Shutdown complete")


app = fastapi.FastAPI(
    title=config.Settings.project_name.replace("-", " ").title(),
    # description=DESCRIPTION,
    version="0.1.0",
    contact={
        "name": "Mahdi Kiani",
        "url": "https://github.com/mahdikiani/FastAPILaunchpad",
        "email": "mahdikiany@gmail.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://github.com/mahdikiani/FastAPILaunchpad/blob/main/LICENSE",
    },
    openapi_url=f"{config.Settings.base_path}/openapi.json",
    docs_url=f"{config.Settings.base_path}/docs",
    redoc_url=f"{config.Settings.base_path}/redoc",
    lifespan=lifespan,
)


@app.exception_handler(exceptions.BaseHTTPException)
async def base_http_exception_handler(
    request: fastapi.Request, exc: exceptions.BaseHTTPException
):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.message, "error": exc.error},
    )


@app.exception_handler(USSOException)
async def usso_exception_handler(request: fastapi.Request, exc: USSOException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.message, "error": exc.error},
    )


@app.exception_handler(pydantic.ValidationError)
@app.exception_handler(fastapi.exceptions.ResponseValidationError)
async def pydantic_exception_handler(
    request: fastapi.Request, exc: pydantic.ValidationError
):
    return JSONResponse(
        status_code=500,
        content={
            "message": str(exc),
            "error": "Exception",
            "erros": json.loads(dumps(exc.errors())),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: fastapi.Request, exc: Exception):
    import traceback

    traceback_str = "".join(traceback.format_tb(exc.__traceback__))
    # body = request._body

    logging.error(f"Exception: {traceback_str} {exc}")
    logging.error(f"Exception on request: {request.url}")
    # logging.error(f"Exception on request: {await request.body()}")
    return JSONResponse(
        status_code=500,
        content={"message": str(exc), "error": "Exception"},
    )


origins = [
    "http://localhost:8000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(middlewares.OriginalHostMiddleware)

from apps.payment.routes import router as payment_router

app.include_router(payment_router, prefix=f"{config.Settings.base_path}")


@app.get(f"{config.Settings.base_path}/health")
async def health(request: fastapi.Request):
    original_host = request.headers.get("x-original-host", "!not found!")
    forwarded_host = request.headers.get("X-Forwarded-Host", "forwarded_host")
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "forwarded_proto")
    forwarded_for = request.headers.get("X-Forwarded-For", "forwarded_for")

    return {
        "status": "up",
        "host": request.url.hostname,
        "host2": request.base_url.hostname,
        "original_host": original_host,
        "forwarded_host": forwarded_host,
        "forwarded_proto": forwarded_proto,
        "forwarded_for": forwarded_for,
    }


@app.get("/openapi.json", include_in_schema=False)
async def openapi():
    openapi = app.openapi()
    paths = {}
    for path in openapi["paths"]:
        paths[f"{config.Settings.base_path}{path}"] = openapi["paths"][path]
    openapi["paths"] = paths
    return openapi

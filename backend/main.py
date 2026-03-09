import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import graph, query, status, upload
from stores.neo4j_store import init_neo4j
from stores.postgres import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        init_neo4j()
    except Exception as exc:
        logger.warning(f"Neo4j init skipped: {exc}")
    yield


app = FastAPI(
    title="Docify API",
    version="1.0.0",
    description="GraphRAG document intelligence — upload, parse, query",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router, tags=["upload"])
app.include_router(status.router, tags=["status"])
app.include_router(query.router, tags=["query"])
app.include_router(graph.router, tags=["graph"])


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # If detail is already our standard shape, pass it through
    if isinstance(exc.detail, dict) and "status" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    # Otherwise wrap it
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status_code": exc.status_code,
            "status": "error",
            "message": str(exc.detail),
            "error": {},
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status_code": 500,
            "status": "error",
            "message": "Internal server error",
            "error": {"detail": str(exc)},
        },
    )


@app.get("/health")
def health():
    return JSONResponse(
        status_code=200,
        content={"status_code": 200, "status": "success", "message": "OK", "data": {}},
    )

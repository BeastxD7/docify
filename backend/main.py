from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import query, status, upload
from stores.postgres import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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


@app.get("/health")
def health():
    return {"status": "ok"}

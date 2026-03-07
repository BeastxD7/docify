import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from qdrant_client.models import FieldCondition, Filter, MatchAny, QueryRequest as QdrantQueryRequest

from config import settings
from stores.embeddings import get_embedder
from stores.llm import get_llm
from stores.qdrant_store import get_qdrant_client

router = APIRouter()
logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    question: str
    doc_ids: list[str] | None = None  # None = search across all documents
    top_k: int = 8


class Source(BaseModel):
    filename: str
    page_number: int
    doc_id: str
    score: float
    excerpt: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]


@router.post("/query", response_model=QueryResponse)
def query_documents(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # ── 1. Embed question ──────────────────────────────────────────────────────
    embedder = get_embedder()
    question_vec = embedder.get_text_embedding(req.question)

    # ── 2. Vector search in Qdrant ─────────────────────────────────────────────
    client = get_qdrant_client()
    search_filter = None
    if req.doc_ids:
        search_filter = Filter(
            must=[FieldCondition(key="doc_id", match=MatchAny(any=req.doc_ids))]
        )

    results = client.query_points(
        collection_name=settings.qdrant_collection,
        query=question_vec,
        limit=req.top_k,
        query_filter=search_filter,
        with_payload=True,
    ).points

    if not results:
        return QueryResponse(
            answer="No relevant content found in the indexed documents.",
            sources=[],
        )

    # ── 3. Build context for LLM ───────────────────────────────────────────────
    context_blocks = []
    sources = []
    for i, hit in enumerate(results, start=1):
        p = hit.payload
        context_blocks.append(
            f"[{i}] File: {p['filename']}, Page: {p['page_number']}\n{p['text']}"
        )
        sources.append(
            Source(
                filename=p["filename"],
                page_number=p["page_number"],
                doc_id=p["doc_id"],
                score=round(hit.score, 4),
                excerpt=p["text"][:300],
            )
        )

    context = "\n\n---\n\n".join(context_blocks)

    # ── 4. Generate answer via configured LLM ─────────────────────────────────
    prompt = (
        "You are a precise document assistant. Answer the question using ONLY the provided context.\n"
        "If the answer is not in the context, say so clearly — do not invent information.\n"
        "Cite sources using [1], [2], etc. when referencing specific passages.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {req.question}\n\n"
        "Answer:"
    )

    llm = get_llm()
    response = llm.complete(prompt)

    return QueryResponse(answer=response.text, sources=sources)

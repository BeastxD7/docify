import logging

from fastapi import APIRouter
from pydantic import BaseModel
from qdrant_client.models import FieldCondition, Filter, MatchAny

from api.response import api_error, api_success
from config import settings
from stores.cypher_generator import graph_context_for_question
from stores.embeddings import get_embedder
from stores.llm import get_llm
from stores.qdrant_store import get_qdrant_client

router = APIRouter()
logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    question: str
    doc_ids: list[str] | None = None
    top_k: int = 8
    use_graph: bool = True


def _fetch_graph_context(question: str, doc_ids: list[str] | None) -> str:
    """
    For each requested doc, use an LLM to generate a Cypher query tailored to
    the question, execute it, and combine results with top community summaries.
    """
    from stores.neo4j_store import get_neo4j_driver

    context_parts = []
    target_docs = doc_ids or []

    # ── LLM-generated Cypher per doc ───────────────────────────────────────────
    for doc_id in target_docs[:3]:  # cap at 3 docs to keep prompt size sane
        result = graph_context_for_question(question, doc_id)
        if result:
            context_parts.append(result)

    # ── Community summaries (bird's-eye view) ──────────────────────────────────
    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            comm_filter = "WHERE c.doc_id IN $doc_ids" if target_docs else ""
            records = session.run(
                f"""
                MATCH (c:Community)
                {comm_filter}
                RETURN c.summary AS summary
                ORDER BY c.size DESC
                LIMIT 3
                """,
                doc_ids=target_docs,
            ).data()
        driver.close()

        summaries = [r["summary"] for r in records if r.get("summary")]
        if summaries:
            context_parts.append(
                "Document overview (topic clusters):\n"
                + "\n".join(f"- {s}" for s in summaries)
            )
    except Exception as exc:
        logger.warning(f"Community fetch failed: {exc}")

    return "\n\n".join(context_parts)


@router.post("/query")
def query_documents(req: QueryRequest):
    if not req.question.strip():
        api_error(message="Question cannot be empty", status_code=400)

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
        return api_success(
            data={"answer": "No relevant content found in the indexed documents.", "sources": []},
            message="No relevant content found",
        )

    # ── 3. Build context for LLM ───────────────────────────────────────────────
    context_blocks = []
    sources = []
    for i, hit in enumerate(results, start=1):
        p = hit.payload
        context_blocks.append(
            f"[{i}] File: {p['filename']}, Page: {p['page_number']}\n{p['text']}"
        )
        sources.append({
            "filename": p["filename"],
            "page_number": p["page_number"],
            "doc_id": p["doc_id"],
            "score": round(hit.score, 4),
            "excerpt": p["text"][:300],
        })

    vector_context = "\n\n---\n\n".join(context_blocks)

    # ── 4. Graph context (hybrid) ──────────────────────────────────────────────
    graph_context = ""
    if req.use_graph:
        graph_context = _fetch_graph_context(req.question, req.doc_ids)

    # ── 5. Generate answer via configured LLM ─────────────────────────────────
    graph_section = f"\n\nKnowledge Graph Context:\n{graph_context}" if graph_context else ""
    prompt = (
        "You are a precise document assistant. Answer the question using ONLY the provided context.\n"
        "If the answer is not in the context, say so clearly — do not invent information.\n"
        "Cite sources using [1], [2], etc. when referencing specific passages.\n\n"
        f"Document Excerpts:\n{vector_context}"
        f"{graph_section}\n\n"
        f"Question: {req.question}\n\n"
        "Answer:"
    )

    llm = get_llm()
    response = llm.complete(prompt)

    return api_success(
        data={"answer": response.text, "sources": sources},
        message="Query answered successfully",
    )

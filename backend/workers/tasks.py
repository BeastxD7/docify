import logging
import uuid

from qdrant_client.models import PointStruct

from chunkers.hierarchical import chunk_pages
from config import settings
from extractors.community import detect_and_store_communities
from extractors.graph_extractor import DEFAULT_ENTITY_TYPES, DEFAULT_RELATION_TYPES, extract_from_chunks
from parsers.document import parse_document
from stores.embeddings import get_embedder
from stores.postgres import Document, GraphStatus, Job, JobStatus, SessionLocal
from stores.qdrant_store import ensure_collection, get_qdrant_client
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 50


@celery_app.task(bind=True, max_retries=3)
def process_document(self, job_id: str, doc_id: str, file_path: str, filename: str):
    db = SessionLocal()
    try:
        # ── Mark processing ────────────────────────────────────────────────────
        job = db.query(Job).filter(Job.id == job_id).first()
        job.status = JobStatus.processing
        db.commit()

        # ── 1. Parse ───────────────────────────────────────────────────────────
        logger.info(f"[{job_id}] Parsing {filename}")
        pages = parse_document(file_path)
        logger.info(f"[{job_id}] Parsed {len(pages)} pages")

        # ── 2. Chunk ───────────────────────────────────────────────────────────
        chunks = chunk_pages(pages, doc_id=doc_id, filename=filename)
        logger.info(f"[{job_id}] Created {len(chunks)} chunks")

        if not chunks:
            raise ValueError("Document produced zero chunks — may be empty or unparseable")

        # ── 3. Embed + store in Qdrant ─────────────────────────────────────────
        embedder = get_embedder()
        client = get_qdrant_client()
        collection_ready = False

        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[i : i + EMBED_BATCH_SIZE]
            texts = [c["text"] for c in batch]
            embeddings = embedder.get_text_embedding_batch(texts, show_progress=False)

            if not collection_ready:
                ensure_collection(client, vector_size=len(embeddings[0]))
                collection_ready = True

            points = [
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=emb,
                    payload={
                        "text": chunk["text"],
                        "doc_id": chunk["doc_id"],
                        "filename": chunk["filename"],
                        "page_number": chunk["page_number"],
                        "chunk_index": chunk["chunk_index"],
                    },
                )
                for chunk, emb in zip(batch, embeddings)
            ]
            client.upsert(collection_name=settings.qdrant_collection, points=points)
            logger.info(f"[{job_id}] Stored batch {i // EMBED_BATCH_SIZE + 1} / {-(-len(chunks) // EMBED_BATCH_SIZE)}")

        # ── 4. Update records ──────────────────────────────────────────────────
        doc = db.query(Document).filter(Document.id == doc_id).first()
        doc.total_chunks = str(len(chunks))
        job.status = JobStatus.completed
        db.commit()
        logger.info(f"[{job_id}] Done — {len(chunks)} chunks stored")

        # ── 5. Kick off graph extraction ───────────────────────────────────────
        extract_graph.delay(doc_id=doc_id, chunks=chunks)

    except Exception as exc:
        logger.error(f"[{job_id}] Error: {exc}")
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job and self.request.retries >= self.max_retries:
                job.status = JobStatus.failed
                job.error = str(exc)
                db.commit()
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=30)
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=2)
def extract_graph(
    self,
    doc_id: str,
    chunks: list[dict],
    entity_types: list[str] | None = None,
    relation_types: list[str] | None = None,
):
    """Extract entities/relations from chunks, run community detection, store in Neo4j."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.graph_status = GraphStatus.processing
            db.commit()

        etypes = entity_types or DEFAULT_ENTITY_TYPES
        rtypes = relation_types or DEFAULT_RELATION_TYPES

        logger.info(f"[graph:{doc_id}] Extracting entities from {len(chunks)} chunks")
        entities, relations = extract_from_chunks(chunks, doc_id, etypes, rtypes)
        logger.info(f"[graph:{doc_id}] Found {len(entities)} entities, {len(relations)} relations")

        logger.info(f"[graph:{doc_id}] Detecting communities")
        communities = detect_and_store_communities(doc_id)
        logger.info(f"[graph:{doc_id}] Found {len(communities)} communities")

        if doc:
            doc.graph_status = GraphStatus.completed
            db.commit()

    except Exception as exc:
        logger.error(f"[graph:{doc_id}] Error: {exc}")
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc and self.request.retries >= self.max_retries:
                doc.graph_status = GraphStatus.failed
                doc.graph_error = str(exc)
                db.commit()
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()

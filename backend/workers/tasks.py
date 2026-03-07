import logging
import uuid

from qdrant_client.models import PointStruct

from chunkers.hierarchical import chunk_pages
from config import settings
from parsers.document import parse_document
from stores.embeddings import get_embedder
from stores.postgres import Document, Job, JobStatus, SessionLocal
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

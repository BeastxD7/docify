import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from config import settings
from stores.postgres import Document, Job, JobStatus, get_db
from workers.tasks import process_document

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}
MAX_BYTES = settings.max_file_size_mb * 1024 * 1024


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content) // 1024 // 1024}MB). Max: {settings.max_file_size_mb}MB",
        )

    doc_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    # Save to host-mounted upload folder
    dest_dir = Path(settings.upload_dir) / doc_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    file_path = dest_dir / file.filename
    file_path.write_bytes(content)

    # Persist records
    db.add(Document(id=doc_id, filename=file.filename, file_path=str(file_path)))
    db.add(Job(id=job_id, doc_id=doc_id, filename=file.filename, status=JobStatus.pending))
    db.commit()

    # Queue async processing
    process_document.delay(
        job_id=job_id,
        doc_id=doc_id,
        file_path=str(file_path),
        filename=file.filename,
    )

    return {
        "job_id": job_id,
        "doc_id": doc_id,
        "filename": file.filename,
        "status": "queued",
    }

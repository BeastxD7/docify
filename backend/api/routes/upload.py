import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from api.response import api_error, api_success
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
    entity_types: str | None = Form(default=None, description='JSON array e.g. ["PERSON","LOCATION"]'),
    relation_types: str | None = Form(default=None, description='JSON array e.g. ["WORKS_FOR","LOCATED_IN"]'),
):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        api_error(
            message=f"Unsupported file type '{suffix}'",
            status_code=400,
            error={"allowed": sorted(ALLOWED_EXTENSIONS), "received": suffix},
        )

    content = await file.read()
    if len(content) > MAX_BYTES:
        api_error(
            message="File too large",
            status_code=413,
            error={"max_mb": settings.max_file_size_mb, "received_mb": len(content) // 1024 // 1024},
        )

    doc_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    dest_dir = Path(settings.upload_dir) / doc_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    file_path = dest_dir / file.filename
    file_path.write_bytes(content)

    parsed_entity_types = None
    parsed_relation_types = None
    if entity_types:
        try:
            parsed_entity_types = json.loads(entity_types)
        except (json.JSONDecodeError, ValueError):
            api_error("entity_types must be a valid JSON array of strings", status_code=400)
    if relation_types:
        try:
            parsed_relation_types = json.loads(relation_types)
        except (json.JSONDecodeError, ValueError):
            api_error("relation_types must be a valid JSON array of strings", status_code=400)

    db.add(Document(id=doc_id, filename=file.filename, file_path=str(file_path)))
    db.add(Job(id=job_id, doc_id=doc_id, filename=file.filename, status=JobStatus.pending))
    db.commit()

    process_document.delay(
        job_id=job_id,
        doc_id=doc_id,
        file_path=str(file_path),
        filename=file.filename,
        entity_types=parsed_entity_types,
        relation_types=parsed_relation_types,
    )

    return api_success(
        data={"job_id": job_id, "doc_id": doc_id, "filename": file.filename},
        message="File uploaded and queued for processing",
        status_code=202,
    )

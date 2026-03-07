from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from stores.postgres import Document, Job, get_db

router = APIRouter()


@router.get("/status/{job_id}")
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.id,
        "doc_id": job.doc_id,
        "filename": job.filename,
        "status": job.status,
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "total_chunks": d.total_chunks,
            "created_at": d.created_at,
        }
        for d in docs
    ]

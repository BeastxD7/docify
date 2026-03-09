from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.response import api_error, api_success
from stores.postgres import Document, Job, get_db

router = APIRouter()


@router.get("/status/{job_id}")
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        api_error(message="Job not found", status_code=404, error={"job_id": job_id})

    return api_success(
        data={
            "job_id": job.id,
            "doc_id": job.doc_id,
            "filename": job.filename,
            "status": job.status,
            "error": job.error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        },
        message="Job status retrieved",
    )


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return api_success(
        data=[
            {
                "id": d.id,
                "filename": d.filename,
                "total_chunks": d.total_chunks,
                "graph_status": d.graph_status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ],
        message=f"{len(docs)} document(s) found",
    )

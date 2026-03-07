from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}


def parse_document(file_path: str) -> list[dict]:
    """
    Parse a document into a list of page dicts.

    Each dict has:
        text        — page content as markdown/plain text
        page_number — 1-indexed page number
        metadata    — source filename and file type
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _parse_pdf(path)
    elif suffix in (".docx", ".doc"):
        return _parse_docx(path)
    elif suffix == ".txt":
        return _parse_txt(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Supported: {SUPPORTED_EXTENSIONS}")


def _parse_pdf(path: Path) -> list[dict]:
    import pymupdf4llm

    # page_chunks=True returns one dict per page
    raw_pages = pymupdf4llm.to_markdown(str(path), page_chunks=True)
    pages = []
    for page in raw_pages:
        text = page.get("text", "").strip()
        if not text:
            continue
        pages.append({
            "text": text,
            "page_number": page["metadata"]["page"],  # already 1-indexed in pymupdf4llm 0.3+
            "metadata": {"source": path.name, "type": "pdf"},
        })
    return pages


def _parse_docx(path: Path) -> list[dict]:
    from docx import Document

    doc = Document(str(path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return [
        {
            "text": "\n\n".join(paragraphs),
            "page_number": 1,
            "metadata": {"source": path.name, "type": "docx"},
        }
    ]


def _parse_txt(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return [
        {
            "text": text,
            "page_number": 1,
            "metadata": {"source": path.name, "type": "txt"},
        }
    ]

from llama_index.core import Document as LlamaDocument
from llama_index.core.node_parser import SentenceSplitter

from config import settings


def chunk_pages(pages: list[dict], doc_id: str, filename: str) -> list[dict]:
    """
    Split parsed pages into overlapping sentence-window chunks.

    Each chunk dict has:
        text         — chunk content
        chunk_index  — position in document (0-based)
        doc_id       — parent document UUID
        filename     — original filename
        page_number  — source page number
    """
    if not pages:
        return []

    splitter = SentenceSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    chunks: list[dict] = []
    chunk_index = 0

    for page in pages:
        doc = LlamaDocument(
            text=page["text"],
            metadata={
                "doc_id": doc_id,
                "filename": filename,
                "page_number": page["page_number"],
                **page.get("metadata", {}),
            },
        )
        nodes = splitter.get_nodes_from_documents([doc])
        for node in nodes:
            text = node.get_content().strip()
            if not text:
                continue
            chunks.append(
                {
                    "text": text,
                    "chunk_index": chunk_index,
                    "doc_id": doc_id,
                    "filename": filename,
                    "page_number": page["page_number"],
                }
            )
            chunk_index += 1

    return chunks

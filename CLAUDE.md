# Docify — Claude Rules

## Package Managers
- **TypeScript / JavaScript:** Always use `bun` (not npm, yarn, or pnpm)
  - Install: `bun install`, `bun add <pkg>`, `bun run <script>`
  - Run: `bun <file.ts>` directly, no build step needed for scripts
- **Python:** Always use `uv` (not pip, poetry, or pipenv)
  - Install deps: `uv add <pkg>`
  - Run scripts: `uv run <script.py>`
  - Sync: `uv sync`

## Project Stack
- Backend: Python (FastAPI + Celery)
- Frontend: TypeScript (React + Bun)
- Graph DB: Neo4j (Docker)
- Vector DB: Qdrant (Docker)
- Queue: Redis (Docker)
- Metadata DB: PostgreSQL (Docker)
- File Storage: `./uploads/` on host, mounted into container at `/data/uploads`

## General Rules
- Do not use `npm`, `yarn`, `pnpm`, `pip`, `poetry`, or `pipenv` — ever
- Do not suggest MinIO or any object storage; files go to the host `./uploads/` folder
- Prefer editing existing files over creating new ones
- Keep solutions simple — no over-engineering

## Project Architecture (Docify)

GraphRAG document intelligence platform. Users upload PDF/DOCX/TXT, documents are parsed,
chunked, embedded, and stored. Entities and relationships are extracted into a knowledge graph.
Users can query documents via hybrid search (vector + graph) and get cited answers.

### Processing Pipeline (per document)
1. Parse — pymupdf4llm (PDF), python-docx (DOCX), plain text (TXT)
2. Chunk — hierarchical sentence-window chunking, page metadata preserved
3. Embed — nomic-embed-text (local/free) or text-embedding-3-large (OpenAI, paid)
4. Store vectors — Qdrant collection `docify_chunks`
5. Extract entities/relations — LlamaIndex SchemaLLMPathExtractor → Neo4j (Phase 2)
6. Community detection — Leiden algorithm, cluster summaries (Phase 2)

### Query Pipeline
Vector search (Qdrant) + Graph traversal (Neo4j, Phase 2) → RRF fusion → Re-ranker → Claude answer with citations

### Key Design Decisions
- Qdrant from Phase 1 (not pgvector) — scale requirement: 10k PDFs, 10M+ chunks
- pymupdf4llm for Phase 1 parsing (lightweight, good quality); Docling optional for complex layouts
- Celery + Redis for async batch processing
- Single Qdrant collection with doc_id metadata filter (not per-doc collections)
- LLM for extraction: claude-sonnet-4-6 | Q&A: claude-haiku-4-5-20251001

### Phase Status
- Phase 1: Core pipeline — upload, parse, chunk, embed, vector Q&A  ← current
- Phase 2: GraphRAG — entity extraction, Neo4j, community detection
- Phase 3: Visualization — Cytoscape.js graph UI, timeline
- Phase 4: Scale — batch workers, re-ranker, entity deduplication

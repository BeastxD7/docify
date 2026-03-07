# Docify

GraphRAG-powered document intelligence platform. Upload PDFs, DOCX, and TXT files — Docify parses them, builds a knowledge graph of entities and relationships, and lets you ask natural language questions with cited answers.

## What it does

- **Upload** PDF / DOCX / TXT documents (single or batch)
- **Parse & chunk** documents with layout-aware parsing and hierarchical chunking
- **Embed** chunks using local (nomic-embed-text via Ollama) or cloud (OpenAI) embeddings
- **Ask questions** — hybrid vector + graph search returns answers with source citations
- **Visualize** entity relationships as an interactive knowledge graph *(Phase 2 — coming)*

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, Tailwind v4, shadcn/ui |
| Backend | FastAPI, Celery, Python 3.12 |
| Package managers | `bun` (frontend), `uv` (backend) |
| Vector DB | Qdrant |
| Graph DB | Neo4j |
| Queue | Redis |
| Metadata DB | PostgreSQL |
| LLM | llama3.2:3b via Ollama (local) / Claude (Anthropic) |
| Embeddings | nomic-embed-text via Ollama (local) / text-embedding-3-large (OpenAI) |

---

## Local Setup

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Ollama](https://ollama.com/) (for local LLM + embeddings)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- [Bun](https://bun.sh/) (JavaScript runtime + package manager)

### 1. Pull Ollama models

```bash
ollama pull nomic-embed-text   # embeddings
ollama pull llama3.2:3b        # LLM (fits in 16GB RAM)
```

### 2. Start infrastructure

```bash
docker compose -f docker-compose.infra.yml up -d
```

This starts PostgreSQL, Redis, Qdrant, and Neo4j locally with ports exposed.

| Service | URL |
|---|---|
| Qdrant dashboard | http://localhost:6333/dashboard |
| Neo4j browser | http://localhost:7474 |

### 3. Configure backend

```bash
cp .env.local.example backend/.env
# Open backend/.env and fill in ANTHROPIC_API_KEY if using Claude
# For fully local setup (Ollama), no API keys needed
```

### 4. Install backend dependencies

```bash
cd backend
uv sync
```

### 5. Run the backend

Open two terminals:

```bash
# Terminal 1 — API server
cd backend
uvicorn main:app --reload --port 8000

# Terminal 2 — Background worker
cd backend
celery -A workers.celery_app worker --loglevel=info
```

API docs available at http://localhost:8000/docs

### 6. Install and run the frontend

```bash
cd frontend
bun install
bun dev
```

Open http://localhost:3000

---

## Project Structure

```
docify/
├── backend/
│   ├── api/routes/          # FastAPI endpoints (upload, status, query)
│   ├── parsers/             # PDF (pymupdf4llm), DOCX, TXT parsers
│   ├── chunkers/            # Hierarchical sentence-window chunking
│   ├── stores/              # Qdrant, PostgreSQL, embeddings, LLM clients
│   ├── workers/             # Celery tasks (async document processing)
│   ├── config.py            # Settings (reads from .env)
│   ├── main.py              # FastAPI app
│   └── pyproject.toml       # Dependencies (managed by uv)
├── frontend/
│   ├── app/(shell)/         # Chat, Upload, Documents pages
│   ├── components/          # Sidebar, UploadZone, Chat UI
│   └── lib/api.ts           # Typed API client
├── uploads/                 # Raw uploaded files (host folder, gitignored)
├── docker-compose.yml       # Full stack (infra + backend + worker)
├── docker-compose.infra.yml # Infra only (for local dev)
├── plan.md                  # Architecture and phase plan
└── CLAUDE.md                # AI assistant rules for this project
```

---

## API Endpoints

All responses follow a consistent shape:

```json
// Success
{ "status_code": 200, "status": "success", "message": "...", "data": {} }

// Error
{ "status_code": 400, "status": "error", "message": "...", "error": {} }
```

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/upload` | Upload a document, returns `job_id` and `doc_id` |
| `GET` | `/status/{job_id}` | Poll processing status (`pending → processing → completed`) |
| `GET` | `/documents` | List all indexed documents |
| `POST` | `/query` | Ask a question, returns answer + source citations |
| `GET` | `/health` | Health check |

### Example: Upload and query

```bash
# Upload
curl -X POST http://localhost:8000/upload -F "file=@document.pdf"
# → { "data": { "job_id": "...", "doc_id": "..." } }

# Poll until completed
curl http://localhost:8000/status/<job_id>
# → { "data": { "status": "completed" } }

# Ask a question
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the main topics?", "doc_ids": ["<doc_id>"]}'
```

---

## Environment Variables

Copy `.env.local.example` to `backend/.env` and adjust:

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` or `anthropic` |
| `LLM_MODEL` | `llama3.2:3b` | Model name for the LLM |
| `EMBEDDING_PROVIDER` | `ollama` | `ollama` or `openai` |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `ANTHROPIC_API_KEY` | — | Required if `LLM_PROVIDER=anthropic` |
| `OPENAI_API_KEY` | — | Required if `EMBEDDING_PROVIDER=openai` |
| `UPLOAD_DIR` | `../uploads` | Where uploaded files are stored |
| `CHUNK_SIZE` | `512` | Tokens per chunk |
| `CHUNK_OVERLAP` | `64` | Overlap between chunks |

---

## Switching to Cloud LLM / Embeddings

Edit `backend/.env`:

```env
# Use Claude for answers (more accurate)
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=your_key_here

# Use OpenAI for embeddings (more accurate)
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-large
OPENAI_API_KEY=your_key_here
```

---

## Build Phases

- **Phase 1** ✅ — Upload, parse, chunk, embed, vector Q&A, UI
- **Phase 2** 🔄 — GraphRAG: entity/relation extraction, Neo4j, community detection
- **Phase 3** — Visualization: Cytoscape.js graph UI, timeline
- **Phase 4** — Scale: batch processing, re-ranker, entity deduplication

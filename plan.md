# Docify — Document Intelligence Platform

GraphRAG-powered document parsing with entity/relationship extraction, hybrid Q&A, and graph visualization.

---

## What This System Does

- Upload PDF, DOCX, or TXT files (single file or batch of thousands)
- Parse and chunk documents with layout-awareness
- Extract entities and relationships into a knowledge graph (GraphRAG)
- Ask natural language questions — get answers with citations
- Visualize the knowledge graph interactively

---

## Honest Tech Choices

### Embedding Model — Why nomic-embed-text?

| Model | Context Window | Cost | Quality | Notes |
|---|---|---|---|---|
| `nomic-embed-text` | 8192 tokens | Free (local via Ollama) | Good | Best free option for long docs |
| `text-embedding-3-large` | 8192 tokens | ~$0.13/million tokens | Best | Use this if budget allows |
| `BGE-M3` | 8192 tokens | Free (local) | Very good | Multilingual, strong alternative |
| `text-embedding-3-small` | 8192 tokens | ~$0.02/million tokens | Good | Budget cloud option |

**Decision:** Default to `nomic-embed-text` locally (free, 8192 context window matters for long chunks).
Switch to `text-embedding-3-large` in production for maximum accuracy. The code will be model-agnostic.

> The 8192 context window is critical here. Many embedding models cap at 512 tokens, which means long
> paragraphs get truncated and you lose semantic meaning. For 1000-page documents this matters a lot.

---

### File Storage — Why NOT MinIO?

MinIO is object storage (like AWS S3) for raw binary files. PostgreSQL is a relational DB.
They serve different purposes, but for this project we don't need MinIO at all:

- **Dev / Single-server:** Store uploaded files on the local filesystem (Docker volume mount). Simple, zero overhead.
- **Production / Multi-server:** Add MinIO or S3 then — not before.

This removes one container from our stack and keeps things simple.

---

### Vector DB — Qdrant vs pgvector (PostgreSQL extension)

| Option | Pros | Cons |
|---|---|---|
| **Qdrant** (separate container) | Fastest vector search, hybrid search built-in, scales to 10M+ vectors | One more container to manage |
| **pgvector** (extension in Postgres) | No extra container, same DB for everything | Slower at scale (10k+ PDFs), less features |

**Decision:** Use Qdrant via Docker from Phase 1. At the scale described (10,000 PDFs, 1000 pages each =
potentially 10M+ chunks), pgvector starts to slow down. Qdrant handles this natively with HNSW indexing.
It also ships with a built-in dashboard UI at `:6333/dashboard` — useful for inspecting vectors during development.
No reason to start with pgvector and migrate later.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   React Frontend                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │  Upload UI   │  │  Graph Viz   │  │  Chat UI  │  │
│  │  (drag/drop) │  │ (Cytoscape)  │  │  (Q&A)    │  │
│  └──────────────┘  └──────────────┘  └───────────┘  │
└────────────────────────┬────────────────────────────┘
                         │ HTTP / WebSocket
┌────────────────────────▼────────────────────────────┐
│                   FastAPI Backend                    │
│  POST /upload     GET /graph      POST /query        │
│  GET /status      GET /entities   GET /communities   │
└──────┬─────────────────┬───────────────┬────────────┘
       │                 │               │
       ▼                 ▼               ▼
  ┌─────────┐      ┌──────────┐   ┌──────────────┐
  │  Redis  │      │  Neo4j   │   │    Qdrant    │
  │ (queue) │      │ (graph)  │   │  (vectors)   │
  └────┬────┘      └──────────┘   └──────────────┘
       │
  ┌────▼────────────────────┐
  │   Celery Workers        │
  │  (async doc processing) │
  └────────────────────────┘
       │
  ┌────▼────────────────────┐
  │   PostgreSQL            │
  │  (jobs, metadata,       │
  │   document registry)    │
  └────────────────────────┘
       │
  ┌────▼────────────────────┐
  │   Local Filesystem      │
  │  /data/uploads          │
  │  (raw PDF/DOCX/TXT)     │
  └────────────────────────┘
```

---

## Processing Pipeline (per document)

```
File Upload
    │
    ▼
1. PARSE  ──────────────────────────────────────────────
    │  Docling (complex PDFs, tables, images)
    │  python-docx (DOCX)
    │  plain reader (TXT)
    │  Output: structured markdown with page/section metadata
    │
    ▼
2. CHUNK  ──────────────────────────────────────────────
    │  Hierarchical: Document → Chapter → Section → Paragraph
    │  Sentence-window chunking (chunk + surrounding sentences)
    │  Preserves page numbers, section headers in metadata
    │
    ▼
3. EMBED  ──────────────────────────────────────────────
    │  nomic-embed-text (or text-embedding-3-large)
    │  Store in Qdrant with metadata
    │
    ▼
4. EXTRACT ENTITIES & RELATIONS  ───────────────────────
    │  Schema-guided extraction via LLM (Claude claude-sonnet-4-6)
    │
    │  For a GoT-like document, define schema upfront:
    │    Entity types:  CHARACTER, HOUSE, LOCATION, EVENT, FACTION
    │    Relation types: ALLIED_WITH, KILLED, MEMBER_OF, RULES,
    │                    MARRIED_TO, OCCURRED_AT, PARTICIPATED_IN
    │
    │  Generic documents get auto-schema detection first pass,
    │  then user can refine the schema.
    │
    │  Uses LlamaIndex SchemaLLMPathExtractor
    │
    ▼
5. BUILD KNOWLEDGE GRAPH  ──────────────────────────────
    │  Store nodes and edges in Neo4j
    │  Link graph nodes to vector chunks (by chunk_id)
    │
    ▼
6. COMMUNITY DETECTION  ────────────────────────────────
    │  Leiden algorithm over the graph
    │  Groups entities into clusters (Houses, Factions, etc.)
    │  Generates LLM summary for each community
    │  Stored as community nodes in Neo4j
    │
    ▼
7. DONE — document is queryable
```

---

## Query Pipeline

```
User Question: "Who are Jon Snow's allies and what happened to them?"
    │
    ▼
Query Router (classifies intent)
    │
    ├──► VECTOR SEARCH (semantic)
    │     Qdrant: top-K similar chunks
    │
    ├──► GRAPH TRAVERSAL (relational)
    │     Neo4j Cypher: 2-hop walk from "Jon Snow"
    │     MATCH (c:CHARACTER {name: "Jon Snow"})-[r]-(n) RETURN n, r
    │
    └──► KEYWORD SEARCH (exact names, BM25)
          Qdrant sparse vectors
    │
    ▼
Result Fusion (RRF — Reciprocal Rank Fusion)
    │
    ▼
Cross-Encoder Re-ranker (eliminates noise, boosts precision)
    │
    ▼
LLM Synthesis (Claude claude-sonnet-4-6)
    - Answer grounded in retrieved context
    - Citations: [Book 1, Page 247] [Book 3, Chapter 12]
    - Refuses to answer if evidence is absent
```

---

## Visualization

### Graph View (Cytoscape.js)
- Nodes colored by type (CHARACTER=blue, HOUSE=red, LOCATION=green)
- Edge labels show relationship type
- Community clusters highlighted with background color
- Click a node → side panel shows: entity info, related chunks, source pages
- Filter by: node type, community, document, relationship type

### Timeline View
- For temporal relations (OCCURRED_AT with dates/events)
- Horizontal timeline with event nodes

### Document Map
- Which parts of a document contributed which entities
- Click an entity → jump to source page

---

## Precision & Accuracy Strategies

| Problem | Solution |
|---|---|
| PDF tables/columns parsed wrong | Docling (layout-aware, reconstructs tables) |
| Entity extraction misses aliases | Co-reference resolution pass before extraction |
| Wrong relations extracted | Few-shot examples in extraction prompt |
| LLM hallucinates in answers | Strict RAG: answer only from retrieved context |
| Long doc context gets lost | Hierarchical indexing + sentence window retrieval |
| Same entity appears with different names | Entity normalization + deduplication pass |
| Query returns irrelevant passages | Cross-encoder re-ranker eliminates false positives |
| Schema is wrong for domain | Let user define/edit entity types before processing |

**Target accuracy:** ~92-95% entity extraction precision with schema-guided extraction.
Generic (schema-less) extraction gives ~60-70%. Schema is the biggest lever.

---

## Docker Compose Stack

```yaml
services:
  backend:    FastAPI + Celery worker (same image, different command)
  redis:      Queue for Celery jobs
  postgres:   Job tracking, document metadata, user data
  neo4j:      Knowledge graph (graph DB + built-in browser at :7474)
  qdrant:     Vector store (UI at :6333/dashboard)
  ollama:     Local LLM/embedding server (nomic-embed-text, optional)
```

No MinIO needed. Uploads stored on the **host machine** at `./uploads/` (relative to project root),
mounted into the container at `/data/uploads`. Files survive container restarts and are directly
accessible on your machine without going through Docker.

---

## Build Phases

### Phase 1 — Core Pipeline (MVP) ✅ DONE
- [x] FastAPI backend with upload endpoint
- [x] pymupdf4llm PDF parser + python-docx + txt
- [x] Hierarchical sentence-window chunker (page metadata preserved)
- [x] Embedding — nomic-embed-text (Ollama, local) or text-embedding-3-large (OpenAI)
- [x] Qdrant vector storage (Docker, from day 1)
- [x] Basic Q&A — vector search + Claude answer with citations
- [x] Job tracking — PostgreSQL (Job, Document tables)
- [x] docker-compose.infra.yml — infra-only compose for local dev
- [ ] Simple React UI: upload + chat  ← next up before Phase 2

### Phase 2 — GraphRAG ✅ DONE
- [x] Schema defaults API — GET /graph/schema/defaults
- [x] Custom schema at upload — entity_types/relation_types form fields
- [x] Re-trigger extraction — POST /graph/{doc_id}/extract (fetches chunks from Qdrant)
- [x] Entity + relation extraction (LLM schema-guided, extractors/graph_extractor.py)
- [x] Neo4j storage + indexes (stores/neo4j_store.py)
- [x] Community detection (Louvain via networkx, extractors/community.py)
- [x] Community summaries (LLM-generated per cluster)
- [x] Hybrid query: vector search + graph context (entities + community summaries)
- [x] Graph API: /graph/{doc_id}/entities|relations|communities|subgraph

### Phase 3 — Visualization ✅ DONE
- [x] Cytoscape.js graph view (/graph page, force-directed layout)
- [x] Nodes colored by entity type, community borders distinguish clusters
- [x] Filter by entity type (toggle on/off, counts shown)
- [x] Click node → highlight neighborhood + entity detail side panel
- [x] Communities list with LLM summaries in side panel
- [x] Documents page: graph_status badge + "View Graph" button
- [x] Deep-link from documents: /graph?doc=<id>
- [ ] Timeline view for temporal entities (deferred to Phase 4)

### Phase 4 — Scale & Polish
- [ ] Celery workers for batch processing (10,000 PDFs)
- [ ] Qdrant collection sharding for very large corpora
- [ ] Processing progress via WebSocket
- [ ] Cross-encoder re-ranker integration
- [ ] Citation rendering in chat
- [ ] Entity deduplication / normalization
- [ ] Export graph as JSON / CSV

---

## LLM Strategy

| Task | Model | Why |
|---|---|---|
| Entity/relation extraction | Claude claude-sonnet-4-6 | Needs high instruction-following for schema |
| Q&A synthesis | Claude Haiku 4.5 | Fast, cheap for simple retrieval |
| Community summarization | Claude Haiku 4.5 | Bulk operation, cost-sensitive |
| Complex multi-hop reasoning | Claude claude-sonnet-4-6 | Fallback for hard queries |

---

## Project Structure (planned)

```
docify/
├── backend/
│   ├── api/              # FastAPI routes
│   ├── parsers/          # Docling, docx, txt parsers
│   ├── chunkers/         # Hierarchical chunking logic
│   ├── extractors/       # Entity/relation extraction
│   ├── stores/           # Neo4j, Qdrant, Postgres clients
│   ├── workers/          # Celery tasks
│   └── query/            # Query router, fusion, reranker
├── frontend/
│   ├── src/
│   │   ├── components/   # Upload, Chat, GraphView, Timeline
│   │   └── pages/
├── docker-compose.yml
├── plan.md               # this file
└── uploads/              # raw uploaded files (host folder, mounted into container)
```

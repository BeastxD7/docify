# Docify — Concepts, Architecture & Implementation Guide

> A plain-English deep-dive into every component of the system: what it does, why it exists,
> how the code works, and how data flows from a raw PDF to an intelligent, cited answer.

---

## Table of Contents

1. [What is Docify?](#1-what-is-docify)
2. [Why GraphRAG instead of plain RAG?](#2-why-graphrag-instead-of-plain-rag)
3. [System Architecture](#3-system-architecture)
4. [The Full Processing Pipeline](#4-the-full-processing-pipeline)
   - [Step 1 — Upload](#step-1--upload)
   - [Step 2 — Parse](#step-2--parse)
   - [Step 3 — Chunk](#step-3--chunk)
   - [Step 4 — Embed](#step-4--embed)
   - [Step 5 — Store in Vector DB (Qdrant)](#step-5--store-in-vector-db-qdrant)
   - [Step 6 — Entity & Relation Extraction](#step-6--entity--relation-extraction)
   - [Step 7 — Store in Graph DB (Neo4j)](#step-7--store-in-graph-db-neo4j)
   - [Step 8 — Community Detection](#step-8--community-detection)
5. [The Query Pipeline](#5-the-query-pipeline)
6. [Vector Database Deep Dive](#6-vector-database-deep-dive)
7. [Graph Database Deep Dive](#7-graph-database-deep-dive)
8. [LLM Operations — When, Why, How](#8-llm-operations--when-why-how)
9. [Supporting Infrastructure](#9-supporting-infrastructure)
10. [API Reference Summary](#10-api-reference-summary)
11. [Configuration & LLM Providers](#11-configuration--llm-providers)

---

## 1. What is Docify?

Docify is a **document intelligence platform**. You upload PDFs, Word docs, or text files and then:

- Ask questions in plain English → get cited answers from the documents
- Explore a knowledge graph of people, organizations, events, and concepts extracted from the text
- See how entities cluster into communities (groups of related things)

It combines two approaches to finding relevant information:

| Approach | How it works | Good at |
|---|---|---|
| **Vector search** | Converts text to numbers, finds similar passages | Semantic meaning, paraphrasing |
| **Graph traversal** | Follows relationships between entities | Connections, relationships, multi-hop reasoning |

Combining both is called **GraphRAG** (Graph-enhanced Retrieval Augmented Generation).

---

## 2. Why GraphRAG instead of plain RAG?

### Plain RAG (what most AI apps do)

```
Question → embed → search similar chunks → paste into LLM → answer
```

**Problem:** It only finds passages that *sound similar* to your question. It misses *relational* information.

**Example:** You ask *"Who are all the people connected to Project Apollo?"*
- Plain RAG finds chunks that mention "Project Apollo"
- It might miss that "Neil Armstrong" is connected because his chunk just says "lunar mission"

### GraphRAG (what Docify does)

```
Question → embed → search similar chunks
                 + keyword-match entities in Neo4j
                 + fetch community summaries
         → combine all context → LLM → answer
```

The graph stores *who is connected to what*, so a 2-hop traversal from "Project Apollo" finds every person, organization, and event linked to it — even if the word "Apollo" never appears in their passage.

**Analogy:** Plain RAG is like searching Wikipedia by keyword. GraphRAG is like following the hyperlinks between Wikipedia pages.

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        React Frontend                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌───────────┐  │
│  │  Upload  │  │   Chat   │  │    Graph     │  │ Documents │  │
│  │   Page   │  │   Page   │  │     Page     │  │   Page    │  │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘  └─────┬─────┘  │
└───────┼─────────────┼───────────────┼────────────────┼─────────┘
        │             │               │                │
        │         HTTP REST API       │                │
        │             │               │                │
┌───────┴─────────────┴───────────────┴────────────────┴─────────┐
│                     FastAPI Backend (Python)                    │
│                                                                 │
│  POST /upload    POST /query    GET /graph/{id}/entities        │
│  GET /status     GET /documents GET /graph/{id}/communities     │
│  POST /graph/{id}/extract       GET /graph/{id}/subgraph        │
└──────┬──────────────┬──────────────┬──────────────┬────────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
  ┌─────────┐   ┌──────────┐  ┌──────────┐  ┌──────────────┐
  │  Redis  │   │PostgreSQL│  │  Qdrant  │  │    Neo4j     │
  │  Queue  │   │Metadata  │  │ Vectors  │  │    Graph     │
  └────┬────┘   └──────────┘  └──────────┘  └──────────────┘
       │
  ┌────┴────────────────────────┐
  │      Celery Worker          │
  │  (async background tasks)   │
  │                             │
  │  process_document()         │
  │    → parse                  │
  │    → chunk                  │
  │    → embed                  │
  │    → store in Qdrant        │
  │                             │
  │  extract_graph()            │
  │    → LLM entity extraction  │
  │    → store in Neo4j         │
  │    → community detection    │
  └─────────────────────────────┘
       │
  ┌────┴────────────────────────┐
  │  LLM Providers (per task)   │
  │  Extraction → OpenRouter    │
  │  Summaries  → OpenRouter    │
  │  Q&A        → Ollama        │
  │  Embeddings → Ollama        │
  └─────────────────────────────┘
```

### Why these components?

| Component | Role | Why this choice |
|---|---|---|
| **FastAPI** | HTTP API | Async Python, auto-generates docs at `/docs` |
| **Celery + Redis** | Background task queue | Parsing/embedding a 1000-page PDF takes minutes — can't block HTTP |
| **PostgreSQL** | Job tracking, document registry | Reliable relational store for structured metadata |
| **Qdrant** | Vector similarity search | Scales to 10M+ vectors, HNSW index, built-in dashboard |
| **Neo4j** | Knowledge graph | Native graph DB, fast Cypher traversals, visual browser UI |
| **Ollama** | Local LLM/embedding server | Free, no API key, runs on your machine |
| **OpenRouter / Groq / Anthropic** | Cloud LLM options | Better quality, no local RAM needed |

---

## 4. The Full Processing Pipeline

```
PDF / DOCX / TXT
      │
      ▼
  [1] UPLOAD ──────────── save to disk, create DB records, queue Celery job
      │
      ▼
  [2] PARSE ──────────── extract raw text + page numbers
      │
      ▼
  [3] CHUNK ──────────── split into overlapping windows (~512 tokens each)
      │
      ▼
  [4] EMBED ──────────── convert each chunk to a vector (list of ~768 numbers)
      │
      ▼
  [5] STORE VECTORS ───── write chunks + vectors to Qdrant
      │
      ▼
  [6] EXTRACT ENTITIES ── LLM reads each chunk, finds PERSON/LOCATION/EVENT etc.
      │
      ▼
  [7] STORE GRAPH ──────── write Entity nodes + RELATION edges to Neo4j
      │
      ▼
  [8] DETECT COMMUNITIES ─ group related entities into clusters, LLM writes summary
      │
      ▼
  Document is fully indexed and queryable ✓
```

---

### Step 1 — Upload

**File:** `backend/api/routes/upload.py`

```
User picks a file → browser POSTs multipart/form-data to /upload
```

**What happens in code:**

```python
# 1. Validate file extension (.pdf, .docx, .doc, .txt)
suffix = Path(file.filename).suffix.lower()
if suffix not in ALLOWED_EXTENSIONS:
    api_error(...)

# 2. Check file size (default limit: 500 MB)
if len(content) > MAX_BYTES:
    api_error(...)

# 3. Generate two UUIDs — one for the document, one for the job
doc_id = str(uuid.uuid4())   # e.g. "03c8b613-dcaa-4596-a664-3d0c9aa539b7"
job_id = str(uuid.uuid4())   # tracks processing status

# 4. Save the raw file to disk: ./uploads/<doc_id>/<filename>
dest_dir = Path(settings.upload_dir) / doc_id
file_path = dest_dir / file.filename
file_path.write_bytes(content)

# 5. Create DB records
db.add(Document(id=doc_id, filename=..., file_path=...))
db.add(Job(id=job_id, doc_id=doc_id, status=JobStatus.pending))
db.commit()

# 6. Queue the background task — returns immediately, processing happens async
process_document.delay(job_id=job_id, doc_id=doc_id, file_path=..., filename=...)

# 7. Respond to the browser with 202 Accepted
return api_success(data={"job_id": job_id, "doc_id": doc_id}, status_code=202)
```

**Why async?** Parsing + embedding a 200-page PDF takes 30-120 seconds. If this happened inside the HTTP request, the browser would time out. Instead, the job is handed off to Celery and the browser gets an immediate response with a `job_id` it can poll for status.

**Optional schema at upload time:**
```
entity_types=["PERSON","LOCATION","EVENT"]   (JSON array form field)
relation_types=["PARTICIPATED_IN","LOCATED_AT"]
```
These are passed through to the graph extraction step, letting you define what the LLM should look for.

---

### Step 2 — Parse

**File:** `backend/parsers/document.py`

**Goal:** Convert a binary file into a list of `{text, page_number}` dicts.

```
PDF  → pymupdf4llm.to_markdown()  → one dict per page, text as markdown
DOCX → python-docx                → all paragraphs joined, page_number=1
TXT  → plain read()               → entire content, page_number=1
```

**Why pymupdf4llm for PDFs?**

PDFs are not text files — they're a sequence of drawing commands ("draw letter 'A' at position x=100, y=200"). `pymupdf4llm` reconstructs the reading order and converts it to clean Markdown, preserving:
- Headings (detected by font size)
- Tables (converted to Markdown table syntax)
- Page boundaries

**What the output looks like:**
```python
[
  {
    "text": "## Introduction\n\nThis document describes...",
    "page_number": 1,
    "metadata": {"source": "report.pdf", "type": "pdf"}
  },
  {
    "text": "## Chapter 2\n\nThe findings show...",
    "page_number": 2,
    "metadata": {"source": "report.pdf", "type": "pdf"}
  },
  ...
]
```

---

### Step 3 — Chunk

**File:** `backend/chunkers/hierarchical.py`

**Problem:** A page can be 3000 words. LLMs and embedding models have token limits, and embedding a huge blob of text loses detail. We need smaller, focused pieces.

**Solution:** Sentence-window chunking.

```python
splitter = SentenceSplitter(
    chunk_size=512,    # max tokens per chunk
    chunk_overlap=64,  # 64 tokens repeated at the start of next chunk
)
```

**What `chunk_overlap` does:**

```
Chunk 1: "Alice works at Acme Corp. She leads the AI team. The team has 10 members."
Chunk 2: "She leads the AI team. The team has 10 members. They are based in London."
          ↑ these 64 tokens are repeated ↑
```

Without overlap, a sentence that straddles two chunks gets cut in half and loses meaning. With overlap, context bleeds across chunk boundaries.

**Output — each chunk is a dict:**
```python
{
  "text": "She leads the AI team. The team has 10 members.",
  "chunk_index": 42,      # position in the entire document (0-based)
  "doc_id": "03c8b613-...",
  "filename": "report.pdf",
  "page_number": 2
}
```

A 200-page PDF typically produces 400–1200 chunks.

---

### Step 4 — Embed

**File:** `backend/stores/embeddings.py`, called from `backend/workers/tasks.py`

**What is an embedding?**

An embedding is a way to represent meaning as a list of numbers (a "vector"). The key property: *semantically similar text has vectors that are close together* in a high-dimensional space.

```
"The cat sat on the mat"  → [0.23, -0.14, 0.87, ..., 0.41]  (768 numbers)
"A feline rested on a rug" → [0.24, -0.13, 0.85, ..., 0.40]  (very similar!)
"Stock market crashes"    → [-0.67, 0.52, -0.11, ..., 0.33]  (very different)
```

**The embedding model:**

```python
# Ollama (local, free) — nomic-embed-text
OllamaEmbedding(model_name="nomic-embed-text", base_url="http://localhost:11434")

# OpenAI (cloud, paid) — best accuracy
OpenAIEmbedding(model="text-embedding-3-large", api_key=...)
```

**Why nomic-embed-text?** It has an 8192-token context window. Most embedding models cap at 512 tokens, which would truncate our 512-token chunks. With 8192 tokens, even large chunks fit completely.

**Batch processing:**

```python
EMBED_BATCH_SIZE = 50  # embed 50 chunks at a time

for i in range(0, len(chunks), EMBED_BATCH_SIZE):
    batch = chunks[i : i + 50]
    texts = [c["text"] for c in batch]
    embeddings = embedder.get_text_embedding_batch(texts)
    # embeddings is a list of 50 vectors, each ~768 numbers
```

Batching is more efficient than one HTTP call per chunk — especially with remote embedding APIs.

---

### Step 5 — Store in Vector DB (Qdrant)

**File:** `backend/stores/qdrant_store.py`, `backend/workers/tasks.py`

Each chunk + its vector is stored as a **Point** in Qdrant:

```python
PointStruct(
    id=str(uuid.uuid4()),        # unique ID for this vector point
    vector=[0.23, -0.14, ...],   # the 768-number embedding
    payload={                    # metadata stored alongside the vector
        "text": "She leads the AI team...",
        "doc_id": "03c8b613-...",
        "filename": "report.pdf",
        "page_number": 2,
        "chunk_index": 42,
    }
)
```

**Why store payload alongside the vector?**

When you search for similar vectors, Qdrant returns the matching points *with their payload*. That's how we get the original text back — we never have to query PostgreSQL or disk; the full chunk text lives right next to its vector.

**The collection:**

All documents share one Qdrant collection: `docify_chunks`. Documents are distinguished by the `doc_id` in the payload. When querying, we filter by `doc_id` to search only specific documents.

```
Qdrant collection: "docify_chunks"
┌─────────────────────────────────────────────────────┐
│  Point 1: vector=[...], payload={doc_id:"abc", ...} │
│  Point 2: vector=[...], payload={doc_id:"abc", ...} │
│  Point 3: vector=[...], payload={doc_id:"xyz", ...} │
│  ...10,000+ points...                               │
└─────────────────────────────────────────────────────┘
```

**HNSW Index:**

Qdrant uses a data structure called HNSW (Hierarchical Navigable Small World) to make vector search fast. Instead of comparing your query vector against every single stored vector (which would be slow at 10M points), HNSW builds a graph of nearby vectors and navigates it like a map — jumping to the right neighborhood quickly.

Result: searching 10M vectors takes ~5ms.

---

### Step 6 — Entity & Relation Extraction

**File:** `backend/extractors/graph_extractor.py`

This is the GraphRAG-specific step. We read each chunk and ask the LLM: *"What people, places, events, and organizations are mentioned here, and how are they related?"*

**The extraction prompt:**

```
Extract entities and relationships from the text below.

Entity types to find: PERSON, ORGANIZATION, LOCATION, EVENT, CONCEPT, PRODUCT, TECHNOLOGY
Relationship types to find: RELATED_TO, WORKS_FOR, LOCATED_IN, PART_OF, CREATED_BY, CAUSED_BY, PARTICIPATED_IN

Return ONLY valid JSON:
{
  "entities": [
    {"name": "Neil Armstrong", "type": "PERSON", "description": "American astronaut, first human on the Moon"}
  ],
  "relations": [
    {"source": "Neil Armstrong", "type": "PARTICIPATED_IN", "target": "Apollo 11"}
  ]
}

Text: <chunk text goes here>
```

**Why schema-guided extraction?**

Without a schema, the LLM might return random entity types like "ACHIEVEMENT", "CONCEPT", "IDEA", "TOPIC" — inconsistent across chunks. With a fixed schema, all chunks use the same vocabulary, making it possible to merge entities across the document.

**Deduplication:**

```python
all_entities: dict[str, dict] = {}  # key = entity name

for ent in data.get("entities", []):
    if name not in all_entities:   # first occurrence wins
        all_entities[name] = {...}
```

If "Neil Armstrong" appears in 50 chunks, only one Entity node is created. The description from the first occurrence is kept.

**Validation:**

```python
valid_etypes = {t.upper() for t in entity_types}  # {"PERSON", "ORGANIZATION", ...}

for ent in data.get("entities", []):
    etype = ent.get("type", "").strip().upper()
    if etype not in valid_etypes:
        continue  # discard hallucinated types
```

The LLM sometimes invents entity types not in the schema. We silently drop those.

---

### Step 7 — Store in Graph DB (Neo4j)

**File:** `backend/stores/neo4j_store.py`, `backend/extractors/graph_extractor.py`

Neo4j is a **graph database**. Instead of rows and columns, it stores nodes and edges.

```
(Neil Armstrong) --[PARTICIPATED_IN]--> (Apollo 11)
(Apollo 11)      --[LOCATED_AT]-------> (Moon)
(NASA)           --[CREATED_BY]-------> (Apollo 11)
```

**Writing entity nodes:**

```python
session.run(
    """
    MERGE (e:Entity {name: $name, doc_id: $doc_id})
    SET e:PERSON,                   ← also adds a PERSON label for fast filtering
        e.entity_type  = "PERSON",
        e.description  = "American astronaut...",
        e.page_number  = 3
    """,
    name="Neil Armstrong", doc_id="03c8b613-..."
)
```

`MERGE` means "create if not exists, otherwise update" — safe to run multiple times.

**Writing relationship edges:**

```python
session.run(
    """
    MATCH (s:Entity {name: $source, doc_id: $doc_id})
    MATCH (t:Entity {name: $target, doc_id: $doc_id})
    MERGE (s)-[r:PARTICIPATED_IN]->(t)
    SET r.doc_id = $doc_id, r.chunk_index = $chunk_index
    """
)
```

The relationship type (`:PARTICIPATED_IN`) becomes a label on the edge — this allows filtering by relationship type in queries.

**Indexes for fast lookup:**

```python
session.run(
    "CREATE INDEX entity_lookup IF NOT EXISTS FOR (e:Entity) ON (e.name, e.doc_id)"
)
```

Without this index, finding "Neil Armstrong" would scan every node. With it, Neo4j jumps directly to the right node.

---

### Step 8 — Community Detection

**File:** `backend/extractors/community.py`

**What is a community?**

After extraction, we have a graph of hundreds of entities connected by relationships. A "community" is a cluster of entities that are more connected to each other than to the rest of the graph.

**Example:**

In a document about the Apollo program:
- Community 1: Neil Armstrong, Buzz Aldrin, Michael Collins, Apollo 11, Moon Landing
- Community 2: Wernher von Braun, Saturn V rocket, NASA engineering team
- Community 3: Cold War, Soviet space program, Space Race

**How it works — Louvain algorithm:**

```python
import networkx as nx

# 1. Build an in-memory graph from Neo4j data
G = nx.Graph()
for ent in entity_records:
    G.add_node(ent["name"])
for rel in relation_records:
    G.add_edge(rel["source"], rel["target"])

# 2. Run Louvain community detection
partition = nx.community.louvain_communities(G, seed=42)
# partition = [
#   {"Neil Armstrong", "Buzz Aldrin", "Apollo 11"},   ← community 0
#   {"Wernher von Braun", "Saturn V"},                ← community 1
#   ...
# ]
```

Louvain maximizes **modularity** — it finds the partition where edges inside communities are dense and edges between communities are sparse. `seed=42` makes results reproducible.

**LLM community summarization:**

For each community, we ask the LLM to write a human-readable summary:

```
You are summarizing a cluster of related entities from a document.

Entities in this cluster:
- Neil Armstrong (PERSON): American astronaut, first human on the Moon
- Buzz Aldrin (PERSON): American astronaut, second human on the Moon
- Apollo 11 (EVENT): First crewed lunar landing mission, July 1969

Write a concise 2-3 sentence summary describing what connects these entities.
```

The LLM might return:
> "This cluster represents the crew and mission of Apollo 11, the historic 1969 NASA mission that landed the first humans on the Moon. Neil Armstrong and Buzz Aldrin are the two astronauts who walked on the lunar surface, while the mission itself was a landmark achievement in the Space Race."

**Storing communities in Neo4j:**

```python
session.run(
    """
    CREATE (c:Community {
        community_id: 0,
        doc_id: "03c8b613-...",
        members: ["Neil Armstrong", "Buzz Aldrin", "Apollo 11"],
        size: 3,
        summary: "This cluster represents..."
    })
    """
)

# Link each entity to its community
session.run(
    """
    MATCH (e:Entity {name: "Neil Armstrong", doc_id: ...})
    MATCH (c:Community {community_id: 0, doc_id: ...})
    MERGE (e)-[:BELONGS_TO]->(c)
    """
)
```

**Why communities matter for Q&A:**

When you ask a question, community summaries give the LLM a *bird's-eye view* of the document's main themes — even if the exact answer is in a small chunk the vector search didn't rank highly.

---

## 5. The Query Pipeline

```
User types: "Who participated in Apollo 11 and what was their role?"
                              │
                              ▼
              ┌───────────────────────────────┐
              │   1. Embed the question        │
              │   nomic-embed-text             │
              │   → vector [0.21, -0.33, ...]  │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │   2. Vector Search (Qdrant)    │
              │   Find top-8 most similar      │
              │   chunk vectors                │
              │                               │
              │   Returns:                    │
              │   [1] "Armstrong commanded..." │
              │   [2] "Aldrin descended..."   │
              │   [3] "Collins orbited..."    │
              │   ...                         │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │   3. Graph Context (Neo4j)     │
              │   Keywords from question:      │
              │   ["participated", "Apollo",   │
              │    "11", "role"]               │
              │                               │
              │   Entity match:               │
              │   - Apollo 11 (EVENT): ...    │
              │   - Neil Armstrong (PERSON):..│
              │                               │
              │   Top community summaries:    │
              │   - "The Apollo 11 crew..."   │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │   4. Build LLM Prompt          │
              │                               │
              │   System: Answer from context  │
              │   Document Excerpts: [1][2]... │
              │   Knowledge Graph Context:     │
              │     Relevant entities: ...    │
              │     Communities: ...          │
              │   Question: "Who participated"│
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │   5. LLM generates answer      │
              │   (Ollama / OpenRouter / etc.) │
              │                               │
              │   "Neil Armstrong [1] served  │
              │   as commander, Buzz Aldrin   │
              │   [2] was the lunar module    │
              │   pilot, and Michael Collins  │
              │   [3] piloted the command..."  │
              └───────────────────────────────┘
```

**The vector search (step 2) in code:**

```python
# Convert the question text to a vector
question_vec = embedder.get_text_embedding(req.question)

# Search Qdrant for the 8 most similar chunk vectors
results = client.query_points(
    collection_name="docify_chunks",
    query=question_vec,         # the question vector
    limit=8,                    # top-K results
    query_filter=Filter(        # optionally restrict to specific docs
        must=[FieldCondition(key="doc_id", match=MatchAny(any=req.doc_ids))]
    ),
    with_payload=True,          # return chunk text alongside vectors
).points
```

**The graph context (step 3) in code:**

```python
# Extract words longer than 3 characters from the question
words = [w.strip(".,!?") for w in question.split() if len(w) > 3]
# ["participated", "Apollo", "role"]

# Find entities whose names contain any of these words
session.run("""
    MATCH (e:Entity)
    WHERE any(word IN $words WHERE toLower(e.name) CONTAINS toLower(word))
    RETURN e.name, e.entity_type, e.description
    LIMIT 10
""", words=words)

# Also fetch top 3 community summaries for the doc
session.run("""
    MATCH (c:Community {doc_id: $doc_id})
    RETURN c.summary ORDER BY c.size DESC LIMIT 3
""")
```

**Why keyword matching for graph lookup?**

We *could* embed entity names and do vector search on them, but that adds complexity. Simple keyword matching works well because entity names are specific proper nouns — "Apollo 11", "Neil Armstrong" — that appear verbatim in questions.

---

## 6. Vector Database Deep Dive

### What is a vector?

Imagine a city map. Every location has coordinates (latitude, longitude) — 2 numbers. You can find nearby locations by computing distances.

An embedding does the same for *meaning*. It maps text to a point in 768-dimensional space (768 coordinates). Text with similar meaning maps to nearby points.

```
                    768-dimensional space
                    (visualized in 2D)

    "dog"  ●
    "cat"  ●    ← pets cluster together
    "puppy"●

                        ● "stock market"
                        ● "investment"   ← finance cluster
                        ● "portfolio"
```

### How Qdrant stores and retrieves vectors

**Storage:** Each vector is stored with an HNSW index — a multi-layer graph where each node is a vector and edges connect nearby vectors.

```
Layer 2 (coarse):  A ──── E ──── I
                   │             │
Layer 1 (medium):  A ── B ── E ── H ── I
                   │    │    │    │
Layer 0 (fine):    A─B─C─D─E─F─G─H─I─J  ← all vectors
```

When searching, Qdrant starts at the top layer, jumps to the nearest node, then descends through layers — like zooming in on a map. This is why it's fast even with millions of vectors.

**Distance metric:** Docify uses **cosine similarity**. It measures the angle between two vectors (not their distance). Cosine similarity = 1 means identical meaning, 0 means unrelated.

### Filtering

Qdrant supports **payload filtering** — you can say "find the 8 most similar vectors, but only among points where `doc_id == 'abc'"`.

```python
Filter(must=[FieldCondition(key="doc_id", match=MatchAny(any=["abc", "xyz"]))])
```

This is how multi-document search works — the user selects documents in the UI, and only those docs' chunks are searched.

---

## 7. Graph Database Deep Dive

### Neo4j concepts

| SQL world | Neo4j world |
|---|---|
| Table | Node label (`:Entity`, `:Community`) |
| Row | Node |
| Foreign key | Relationship |
| JOIN | Graph traversal |

### The graph schema in Docify

```
(:Entity {name, doc_id, entity_type, description, page_number})
    │
    ├──[:PARTICIPATED_IN]──► (:Entity)
    ├──[:WORKS_FOR]─────────► (:Entity)
    ├──[:LOCATED_IN]────────► (:Entity)
    └──[:BELONGS_TO]────────► (:Community {community_id, summary, members, size})
```

Every entity node gets two labels:
- `:Entity` — common label for all entities (easy to query all at once)
- `:PERSON` / `:LOCATION` / etc. — specific type (fast filtering by type)

### Cypher query language

Cypher is Neo4j's query language. It uses ASCII-art to describe graph patterns:

```cypher
-- "Find all entities 2 hops from Neil Armstrong"
MATCH path = (start:Entity {name: "Neil Armstrong"})-[*1..2]-(neighbor:Entity)
RETURN neighbor.name, neighbor.entity_type
```

The `-[*1..2]-` means "follow 1 or 2 relationships in any direction".

```cypher
-- "Find all communities for document abc"
MATCH (c:Community {doc_id: "abc"})
RETURN c.summary, c.size
ORDER BY c.size DESC
```

### The subgraph endpoint

`GET /graph/{doc_id}/subgraph?entity=Neil+Armstrong&depth=2`

Returns all nodes and edges within 2 hops of "Neil Armstrong" — useful for the Cytoscape.js visualization to zoom in on one entity.

---

## 8. LLM Operations — When, Why, How

There are 3 places where an LLM is called:

```
┌──────────────────────────────────────────────────────────────────┐
│                     LLM Usage Map                                │
├───────────────┬─────────────────────────────┬───────────────────┤
│   Operation   │         When                │   Default Model   │
├───────────────┼─────────────────────────────┼───────────────────┤
│ Entity        │ After chunking/embedding,   │ OpenRouter:       │
│ Extraction    │ once per chunk              │ llama-3.3-70b     │
│               │ (background Celery task)    │ -instruct:free    │
├───────────────┼─────────────────────────────┼───────────────────┤
│ Community     │ After community detection,  │ OpenRouter:       │
│ Summarization │ once per community cluster  │ llama-3.1-8b      │
│               │ (background Celery task)    │ -instruct:free    │
├───────────────┼─────────────────────────────┼───────────────────┤
│ Q&A Synthesis │ On every user query         │ Ollama:           │
│               │ (synchronous, ~2-5s)        │ llama3.2:3b       │
└───────────────┴─────────────────────────────┴───────────────────┘
```

### Why different models per task?

**Extraction** needs a large, instruction-following model. The prompt is complex (schema, JSON format, rules). A small model gets the JSON wrong or hallucinates entity types. `llama-3.3-70b` (70 billion parameters) follows complex instructions reliably.

**Summarization** is simpler — "write 2-3 sentences about this cluster". A small model (`llama-3.1-8b`, 8 billion parameters) does this well and it's much cheaper/faster since you may have 20+ communities per document.

**Q&A** is latency-sensitive — the user is waiting. Local Ollama (`llama3.2:3b`) responds in ~2s with no API cost. If quality matters more than speed, switch to a cloud model.

### The LLM abstraction layer

```python
# stores/llm.py
def get_llm(task: str = "qa"):
    if task == "extraction":
        provider = settings.extraction_llm_provider  # "openrouter"
        model    = settings.extraction_llm_model     # "meta-llama/llama-3.3-70b..."
    elif task == "summary":
        provider = settings.summary_llm_provider
        model    = settings.summary_llm_model
    else:  # "qa"
        provider = settings.llm_provider
        model    = settings.llm_model

    if provider == "ollama":    return Ollama(model=model, ...)
    if provider == "groq":      return Groq(model=model, api_key=...)
    if provider == "openrouter":return OpenAILike(model=model, api_base="https://openrouter.ai/api/v1", ...)
    return Anthropic(model=model, api_key=...)  # default
```

All providers return a LlamaIndex LLM object with the same `.complete(prompt)` interface, so the rest of the code doesn't care which provider is active.

---

## 9. Supporting Infrastructure

### Celery — the task queue

**Problem:** HTTP requests must respond in <30s or browsers time out. Parsing + embedding + extracting a large PDF takes 5-30 minutes.

**Solution:** Celery is a job queue. The FastAPI server puts a task *description* into Redis ("process document X"). A separate Celery worker process picks it up and does the actual work. The HTTP server responds immediately.

```
FastAPI process                    Celery worker process
──────────────                     ─────────────────────
POST /upload                       picks up task from Redis
  → save file                      → parse document
  → create DB record               → chunk
  → push task to Redis   ─────►    → embed
  → return 202                     → store in Qdrant
                                   → trigger extract_graph task
                                       → extract entities
                                       → store in Neo4j
                                       → detect communities
                                       → summarize communities
```

**Why Redis as the broker?** Redis is an in-memory data store that Celery uses as a message queue. Tasks are serialized to JSON and pushed into a Redis list. Workers pop from the list and execute.

**Task retries:**

```python
@celery_app.task(bind=True, max_retries=3)
def process_document(self, ...):
    try:
        ...
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)  # retry after 30s
```

If a task fails (network error, OOM), Celery automatically retries up to 3 times.

### PostgreSQL — metadata store

Stores two tables:

**`jobs`** — tracks processing status per upload:
```
id (UUID) | doc_id | filename | status    | error | created_at | updated_at
───────────────────────────────────────────────────────────────────────────
abc-123   | def-456| file.pdf | completed | NULL  | 2026-01-01 | 2026-01-01
```

**`documents`** — registry of all indexed documents:
```
id (UUID) | filename | file_path | total_chunks | graph_status | graph_error
────────────────────────────────────────────────────────────────────────────
def-456   | file.pdf | /data/... | 342          | completed    | NULL
```

`graph_status` tracks the Phase 2 pipeline separately from the main job — chunking/embedding can succeed while graph extraction is still running.

### Redis — dual role

1. **Celery broker** — task queue (as described above)
2. **Celery backend** — stores task results (so you could query if a specific task succeeded)

### File storage

Raw uploaded files are stored on the host machine at `./uploads/<doc_id>/<filename>` and mounted into Docker at `/data/uploads`. This means:
- Files survive container restarts (they're on the host)
- No object storage (MinIO/S3) needed for local/single-server use
- Files are directly accessible without going through Docker

---

## 10. API Reference Summary

```
Upload & Status
  POST /upload                    Upload a file, start processing
  GET  /status/{job_id}           Check processing status
  GET  /documents                 List all indexed documents

Query
  POST /query                     Ask a question, get cited answer
    body: { question, doc_ids?, top_k?, use_graph? }

Graph Read
  GET  /graph/{doc_id}/entities   List all entities (filter by type)
  GET  /graph/{doc_id}/relations  List all relationships
  GET  /graph/{doc_id}/communities List communities with summaries
  GET  /graph/{doc_id}/subgraph   N-hop subgraph around an entity

Graph Write
  POST /graph/{doc_id}/extract    Re-trigger extraction with custom schema
    body: { entity_types?, relation_types? }

Schema
  GET  /graph/schema/defaults     Get default entity/relation type lists
```

---

## 11. Configuration & LLM Providers

All configuration lives in `backend/.env`. The code reads it via `config.py` using `pydantic-settings` — environment variables are automatically mapped to typed Python fields.

```
┌─────────────────────────────────────────────────────────────────┐
│                     LLM Provider Options                        │
├─────────────────┬───────────────────────────────────────────────┤
│ Provider        │ Set in .env                                   │
├─────────────────┼───────────────────────────────────────────────┤
│ anthropic       │ ANTHROPIC_API_KEY=sk-ant-...                 │
│ groq            │ GROQ_API_KEY=gsk_...                         │
│ openrouter      │ OPENROUTER_API_KEY=sk-or-...                 │
│ ollama          │ OLLAMA_BASE_URL=http://localhost:11434        │
└─────────────────┴───────────────────────────────────────────────┘

Per-task config:
  LLM_PROVIDER / LLM_MODEL                ← Q&A synthesis
  EXTRACTION_LLM_PROVIDER / EXTRACTION_LLM_MODEL ← entity extraction
  SUMMARY_LLM_PROVIDER / SUMMARY_LLM_MODEL       ← community summaries

Embedding:
  EMBEDDING_PROVIDER=ollama               ← ollama | openai
  EMBEDDING_MODEL=nomic-embed-text
```

**Good free model combinations on OpenRouter (`:free` suffix = no cost):**

| Task | Model | Why |
|---|---|---|
| Extraction | `meta-llama/llama-3.3-70b-instruct:free` | Best instruction-following |
| Summaries | `meta-llama/llama-3.1-8b-instruct:free` | Fast, good enough for summaries |
| Q&A | `google/gemma-3-27b-it:free` | Strong reasoning, free |

---

*This document reflects the implementation as of Phase 3 completion (backend + frontend + graph visualization). Phase 4 (scale, re-ranker, WebSocket progress, entity deduplication) is planned next.*

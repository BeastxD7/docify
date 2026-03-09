import logging
import re

from stores.llm import get_llm
from stores.neo4j_store import get_neo4j_driver

logger = logging.getLogger(__name__)

_CYPHER_PROMPT = """\
You are a Neo4j Cypher expert. Write a Cypher query to answer the user's question \
using the knowledge graph schema described below.

Graph schema (doc_id = "{doc_id}"):
  All nodes have label :Entity and property doc_id = "{doc_id}"
  Entity types present: {entity_types}
  Relationship types present: {relation_types}
  Node properties: name, entity_type, description, page_number
  Relationship properties: relation_type, chunk_index

Rules:
- ALWAYS filter nodes with {{doc_id: $doc_id}} — never omit this
- Use MATCH and RETURN only — no CREATE, MERGE, DELETE, SET
- LIMIT results to 15
- Return meaningful column names (source, target, relation, description, etc.)
- If asking about connections between entities, use relationship traversal
- If asking about a specific entity, return its name, type, and description
- If no specific pattern fits, do a broad entity search matching keywords in the question

Question: {question}

Return ONLY the Cypher query, no explanation, no markdown fences:"""

# Only allow read-only Cypher — block any write keywords
_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|REMOVE|SET|DROP|CALL|FOREACH|LOAD)\b",
    re.IGNORECASE,
)


def _is_safe(query: str) -> bool:
    return not _WRITE_KEYWORDS.search(query)


def get_doc_schema(doc_id: str) -> dict:
    """Fetch actual entity types and relation types from Neo4j for a specific doc."""
    driver = get_neo4j_driver()
    try:
        with driver.session() as session:
            entity_types = [
                r["type"]
                for r in session.run(
                    "MATCH (e:Entity {doc_id: $doc_id}) RETURN DISTINCT e.entity_type AS type",
                    doc_id=doc_id,
                ).data()
                if r["type"]
            ]
            relation_types = [
                r["type"]
                for r in session.run(
                    """
                    MATCH (s:Entity {doc_id: $doc_id})-[r]->(t:Entity {doc_id: $doc_id})
                    RETURN DISTINCT r.relation_type AS type
                    """,
                    doc_id=doc_id,
                ).data()
                if r["type"]
            ]
        return {"entity_types": entity_types, "relation_types": relation_types}
    finally:
        driver.close()


def graph_context_for_question(question: str, doc_id: str) -> str:
    """
    Use an LLM to generate a Cypher query tailored to the user's question,
    execute it against Neo4j, and return a formatted string of results
    ready to be inserted into the Q&A prompt.

    Returns "" if the graph has no data or if generation/execution fails.
    """
    schema = get_doc_schema(doc_id)
    if not schema["entity_types"]:
        return ""  # graph not yet populated for this doc

    prompt = _CYPHER_PROMPT.format(
        doc_id=doc_id,
        entity_types=", ".join(schema["entity_types"]),
        relation_types=", ".join(schema["relation_types"]),
        question=question,
    )

    try:
        llm = get_llm(task="extraction")  # capable model for Cypher generation
        raw = llm.complete(prompt).text.strip()

        # Strip any markdown code fences the LLM might add
        cypher = re.sub(r"```(?:cypher)?\s*", "", raw).replace("```", "").strip()

        if not cypher or not _is_safe(cypher):
            logger.warning(f"[cypher] Blocked or empty query: {cypher[:120]}")
            return ""

        logger.info(f"[cypher] Generated: {cypher[:200]}")

        driver = get_neo4j_driver()
        try:
            with driver.session() as session:
                records = session.run(cypher, doc_id=doc_id).data()
        finally:
            driver.close()

        if not records:
            return ""

        # Format results as readable lines for the LLM context
        lines = []
        for rec in records[:15]:
            parts = [f"{k}: {v}" for k, v in rec.items() if v is not None]
            if parts:
                lines.append("  " + " | ".join(parts))

        if not lines:
            return ""

        return "Knowledge graph query results:\n" + "\n".join(lines)

    except Exception as exc:
        logger.warning(f"[cypher] Generation/execution failed: {exc}")
        return ""

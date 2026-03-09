import json
import logging
import re

from stores.llm import get_llm
from stores.neo4j_store import get_neo4j_driver, sanitize_label

logger = logging.getLogger(__name__)

DEFAULT_ENTITY_TYPES = [
    "PERSON", "ORGANIZATION", "LOCATION", "EVENT", "CONCEPT", "PRODUCT", "TECHNOLOGY",
]
DEFAULT_RELATION_TYPES = [
    "RELATED_TO", "WORKS_FOR", "LOCATED_IN", "PART_OF", "CREATED_BY", "CAUSED_BY", "PARTICIPATED_IN",
]

_EXTRACTION_PROMPT = """\
Extract entities and relationships from the text below.

Entity types to find: {entity_types}
Relationship types to find: {relation_types}

Return ONLY valid JSON — no explanation, no markdown fences:
{{
  "entities": [
    {{"name": "exact name", "type": "ENTITY_TYPE", "description": "one sentence"}}
  ],
  "relations": [
    {{"source": "entity name", "type": "RELATION_TYPE", "target": "entity name"}}
  ]
}}

Rules:
- Use ONLY entity/relation types from the lists above
- Entity names must be exact and consistent across all mentions
- Only include relations between entities found in this text
- If nothing relevant is found return {{"entities": [], "relations": []}}

Text:
{text}

JSON:"""


def _parse_json(response: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", response.strip()).replace("```", "").strip()
    start, end = text.find("{"), text.rfind("}") + 1
    if start == -1 or end == 0:
        return {"entities": [], "relations": []}
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return {"entities": [], "relations": []}


def extract_from_chunks(
    chunks: list[dict],
    doc_id: str,
    entity_types: list[str],
    relation_types: list[str],
) -> tuple[list[dict], list[dict]]:
    """
    Run LLM entity/relation extraction over all chunks and store results in Neo4j.
    Returns (entities, relations) for logging/status purposes.
    """
    llm = get_llm()
    driver = get_neo4j_driver()

    # Deduplicated entity map: name → entity dict
    all_entities: dict[str, dict] = {}
    all_relations: list[dict] = []

    for chunk in chunks:
        prompt = _EXTRACTION_PROMPT.format(
            entity_types=", ".join(entity_types),
            relation_types=", ".join(relation_types),
            text=chunk["text"][:2000],
        )
        try:
            data = _parse_json(llm.complete(prompt).text)
        except Exception as exc:
            logger.warning(f"Extraction failed for chunk {chunk.get('chunk_index')}: {exc}")
            continue

        valid_etypes = {t.upper() for t in entity_types}
        valid_rtypes = {r.upper() for r in relation_types}

        for ent in data.get("entities", []):
            name = ent.get("name", "").strip()
            etype = ent.get("type", "").strip().upper()
            if not name or etype not in valid_etypes:
                continue
            if name not in all_entities:
                all_entities[name] = {
                    "name": name,
                    "type": etype,
                    "description": ent.get("description", ""),
                    "doc_id": doc_id,
                    "chunk_index": chunk.get("chunk_index", 0),
                    "page_number": chunk.get("page_number", 1),
                }

        for rel in data.get("relations", []):
            source = rel.get("source", "").strip()
            target = rel.get("target", "").strip()
            rtype = rel.get("type", "").strip().upper()
            if source and target and rtype in valid_rtypes:
                all_relations.append({
                    "source": source,
                    "target": target,
                    "type": rtype,
                    "doc_id": doc_id,
                    "chunk_index": chunk.get("chunk_index", 0),
                })

    # ── Write to Neo4j ─────────────────────────────────────────────────────────
    with driver.session() as session:
        # Wipe existing graph for this doc before re-inserting
        session.run("MATCH (e:Entity {doc_id: $doc_id}) DETACH DELETE e", doc_id=doc_id)

        for ent in all_entities.values():
            type_label = sanitize_label(ent["type"])
            # All entities get :Entity label + their specific type label
            session.run(
                f"""
                MERGE (e:Entity {{name: $name, doc_id: $doc_id}})
                SET e:{type_label},
                    e.entity_type  = $etype,
                    e.description  = $description,
                    e.chunk_index  = $chunk_index,
                    e.page_number  = $page_number
                """,
                name=ent["name"],
                doc_id=doc_id,
                etype=ent["type"],
                description=ent["description"],
                chunk_index=ent["chunk_index"],
                page_number=ent["page_number"],
            )

        for rel in all_relations:
            if rel["source"] not in all_entities or rel["target"] not in all_entities:
                continue
            rtype_label = sanitize_label(rel["type"])
            session.run(
                f"""
                MATCH (s:Entity {{name: $source, doc_id: $doc_id}})
                MATCH (t:Entity {{name: $target, doc_id: $doc_id}})
                MERGE (s)-[r:{rtype_label}]->(t)
                SET r.doc_id       = $doc_id,
                    r.chunk_index  = $chunk_index,
                    r.relation_type = $rtype
                """,
                source=rel["source"],
                target=rel["target"],
                doc_id=doc_id,
                chunk_index=rel["chunk_index"],
                rtype=rel["type"],
            )

    driver.close()
    return list(all_entities.values()), all_relations

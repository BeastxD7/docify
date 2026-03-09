import logging

from fastapi import APIRouter
from pydantic import BaseModel

from api.response import api_error, api_success
from extractors.graph_extractor import DEFAULT_ENTITY_TYPES, DEFAULT_RELATION_TYPES
from stores.neo4j_store import get_neo4j_driver

router = APIRouter()
logger = logging.getLogger(__name__)


class ExtractRequest(BaseModel):
    entity_types: list[str] | None = None
    relation_types: list[str] | None = None


@router.get("/graph/{doc_id}/entities")
def get_entities(doc_id: str, entity_type: str | None = None, limit: int = 200):
    """Return all entities for a document, optionally filtered by type."""
    driver = get_neo4j_driver()
    try:
        with driver.session() as session:
            if entity_type:
                records = session.run(
                    """
                    MATCH (e:Entity {doc_id: $doc_id})
                    WHERE e.entity_type = $entity_type
                    RETURN e.name AS name, e.entity_type AS type,
                           e.description AS description, e.page_number AS page_number
                    LIMIT $limit
                    """,
                    doc_id=doc_id,
                    entity_type=entity_type.upper(),
                    limit=limit,
                ).data()
            else:
                records = session.run(
                    """
                    MATCH (e:Entity {doc_id: $doc_id})
                    RETURN e.name AS name, e.entity_type AS type,
                           e.description AS description, e.page_number AS page_number
                    LIMIT $limit
                    """,
                    doc_id=doc_id,
                    limit=limit,
                ).data()
    finally:
        driver.close()

    return api_success(
        data={"doc_id": doc_id, "entities": records, "count": len(records)},
        message=f"Found {len(records)} entities",
    )


@router.get("/graph/{doc_id}/relations")
def get_relations(doc_id: str, limit: int = 500):
    """Return all relationships for a document."""
    driver = get_neo4j_driver()
    try:
        with driver.session() as session:
            records = session.run(
                """
                MATCH (s:Entity {doc_id: $doc_id})-[r]->(t:Entity {doc_id: $doc_id})
                RETURN s.name AS source, t.name AS target,
                       r.relation_type AS type, r.chunk_index AS chunk_index
                LIMIT $limit
                """,
                doc_id=doc_id,
                limit=limit,
            ).data()
    finally:
        driver.close()

    return api_success(
        data={"doc_id": doc_id, "relations": records, "count": len(records)},
        message=f"Found {len(records)} relations",
    )


@router.get("/graph/{doc_id}/communities")
def get_communities(doc_id: str):
    """Return all detected communities for a document."""
    driver = get_neo4j_driver()
    try:
        with driver.session() as session:
            records = session.run(
                """
                MATCH (c:Community {doc_id: $doc_id})
                RETURN c.community_id AS community_id, c.summary AS summary,
                       c.members AS members, c.size AS size
                ORDER BY c.size DESC
                """,
                doc_id=doc_id,
            ).data()
    finally:
        driver.close()

    return api_success(
        data={"doc_id": doc_id, "communities": records, "count": len(records)},
        message=f"Found {len(records)} communities",
    )


@router.get("/graph/{doc_id}/subgraph")
def get_subgraph(doc_id: str, entity: str, depth: int = 2):
    """Return the subgraph around a specific entity (nodes + edges within N hops)."""
    if depth > 4:
        api_error("depth cannot exceed 4", status_code=400)

    driver = get_neo4j_driver()
    try:
        with driver.session() as session:
            records = session.run(
                f"""
                MATCH path = (start:Entity {{name: $entity, doc_id: $doc_id}})-[*1..{depth}]-(neighbor:Entity {{doc_id: $doc_id}})
                UNWIND relationships(path) AS r
                WITH startNode(r) AS s, endNode(r) AS t, r
                RETURN DISTINCT
                    s.name AS source, s.entity_type AS source_type,
                    t.name AS target, t.entity_type AS target_type,
                    r.relation_type AS relation_type
                LIMIT 200
                """,
                entity=entity,
                doc_id=doc_id,
            ).data()

            # Collect unique nodes
            nodes = {}
            edges = []
            for row in records:
                nodes[row["source"]] = {"name": row["source"], "type": row["source_type"]}
                nodes[row["target"]] = {"name": row["target"], "type": row["target_type"]}
                edges.append({
                    "source": row["source"],
                    "target": row["target"],
                    "type": row["relation_type"],
                })
    finally:
        driver.close()

    return api_success(
        data={
            "doc_id": doc_id,
            "center": entity,
            "nodes": list(nodes.values()),
            "edges": edges,
        },
        message=f"Subgraph around '{entity}': {len(nodes)} nodes, {len(edges)} edges",
    )


@router.get("/graph/schema/defaults")
def get_schema_defaults():
    """Return the default entity and relation type lists."""
    return api_success(
        data={
            "entity_types": DEFAULT_ENTITY_TYPES,
            "relation_types": DEFAULT_RELATION_TYPES,
        },
        message="Default schema",
    )


@router.post("/graph/{doc_id}/extract")
def trigger_extract(doc_id: str, req: ExtractRequest):
    """
    Re-trigger graph extraction for a document that has already been chunked/embedded.
    Fetches chunks from Qdrant and queues an extract_graph task.
    """
    from config import settings
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    from stores.qdrant_store import get_qdrant_client
    from workers.tasks import extract_graph

    client = get_qdrant_client()
    scroll_filter = Filter(
        must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
    )

    all_chunks = []
    offset = None
    while True:
        results, next_offset = client.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=scroll_filter,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in results:
            p = point.payload or {}
            all_chunks.append({
                "text": p.get("text", ""),
                "doc_id": p.get("doc_id", doc_id),
                "filename": p.get("filename", ""),
                "page_number": p.get("page_number", 1),
                "chunk_index": p.get("chunk_index", 0),
            })
        if next_offset is None:
            break
        offset = next_offset

    if not all_chunks:
        return api_error(
            message=f"No chunks found for doc_id '{doc_id}' — upload and process the document first",
            status_code=404,
        )

    extract_graph.delay(
        doc_id=doc_id,
        chunks=all_chunks,
        entity_types=req.entity_types,
        relation_types=req.relation_types,
    )

    return api_success(
        data={
            "doc_id": doc_id,
            "chunks_queued": len(all_chunks),
            "entity_types": req.entity_types or DEFAULT_ENTITY_TYPES,
            "relation_types": req.relation_types or DEFAULT_RELATION_TYPES,
        },
        message=f"Graph extraction queued for {len(all_chunks)} chunks",
        status_code=202,
    )

import logging

from fastapi import APIRouter

from api.response import api_error, api_success
from stores.neo4j_store import get_neo4j_driver

router = APIRouter()
logger = logging.getLogger(__name__)


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

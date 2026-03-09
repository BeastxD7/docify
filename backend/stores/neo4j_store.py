import re

from neo4j import GraphDatabase

from config import settings


def get_neo4j_driver():
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


def sanitize_label(label: str) -> str:
    """Sanitize a string for safe use as a Neo4j node label or relation type."""
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", label.strip())
    if sanitized and sanitized[0].isdigit():
        sanitized = "_" + sanitized
    return sanitized.upper() or "UNKNOWN"


def init_neo4j() -> None:
    """Create indexes for fast entity lookups."""
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.run(
            "CREATE INDEX entity_lookup IF NOT EXISTS FOR (e:Entity) ON (e.name, e.doc_id)"
        )
        session.run(
            "CREATE INDEX community_lookup IF NOT EXISTS FOR (c:Community) ON (c.doc_id)"
        )
    driver.close()

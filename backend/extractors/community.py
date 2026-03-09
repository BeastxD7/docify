import logging

import networkx as nx

from stores.llm import get_llm
from stores.neo4j_store import get_neo4j_driver

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = """\
You are summarizing a cluster of related entities from a document.

Entities in this cluster:
{entities}

Write a concise 2-3 sentence summary describing what connects these entities and their collective significance.
Summary:"""


def _build_graph(entities: list[dict], relations: list[dict]) -> nx.Graph:
    G = nx.Graph()
    for ent in entities:
        G.add_node(ent["name"], **{k: v for k, v in ent.items() if k != "name"})
    for rel in relations:
        if G.has_node(rel["source"]) and G.has_node(rel["target"]):
            G.add_edge(rel["source"], rel["target"], relation_type=rel["type"])
    return G


def detect_and_store_communities(doc_id: str) -> list[dict]:
    """
    Load entities/relations for a doc from Neo4j, run Louvain community detection,
    generate LLM summaries, store Community nodes, and return community list.
    """
    driver = get_neo4j_driver()

    with driver.session() as session:
        # Load entities
        entity_records = session.run(
            "MATCH (e:Entity {doc_id: $doc_id}) RETURN e.name AS name, e.entity_type AS type, e.description AS description",
            doc_id=doc_id,
        ).data()

        # Load relations
        relation_records = session.run(
            """
            MATCH (s:Entity {doc_id: $doc_id})-[r]->(t:Entity {doc_id: $doc_id})
            RETURN s.name AS source, t.name AS target, r.relation_type AS type
            """,
            doc_id=doc_id,
        ).data()

    if not entity_records:
        driver.close()
        return []

    # Build graph and detect communities
    G = _build_graph(entity_records, relation_records)
    partition = nx.community.louvain_communities(G, seed=42)

    llm = get_llm(task="summary")
    communities = []

    with driver.session() as session:
        # Wipe old communities for this doc
        session.run(
            "MATCH (c:Community {doc_id: $doc_id}) DETACH DELETE c",
            doc_id=doc_id,
        )

        for community_id, member_set in enumerate(partition):
            members = list(member_set)
            entity_lines = []
            for name in members:
                node = G.nodes[name]
                desc = node.get("description", "")
                entity_lines.append(f"- {name} ({node.get('type', 'UNKNOWN')}): {desc}")

            prompt = _SUMMARY_PROMPT.format(entities="\n".join(entity_lines))
            try:
                summary = llm.complete(prompt).text.strip()
            except Exception as exc:
                logger.warning(f"Community summary failed for community {community_id}: {exc}")
                summary = f"Cluster of {len(members)} entities: {', '.join(members[:5])}"

            community_data = {
                "community_id": community_id,
                "doc_id": doc_id,
                "members": members,
                "size": len(members),
                "summary": summary,
            }
            communities.append(community_data)

            # Store Community node in Neo4j
            session.run(
                """
                CREATE (c:Community {
                    community_id: $community_id,
                    doc_id: $doc_id,
                    members: $members,
                    size: $size,
                    summary: $summary
                })
                """,
                community_id=community_id,
                doc_id=doc_id,
                members=members,
                size=len(members),
                summary=summary,
            )

            # Link entities to their community
            for member_name in members:
                session.run(
                    """
                    MATCH (e:Entity {name: $name, doc_id: $doc_id})
                    MATCH (c:Community {community_id: $community_id, doc_id: $doc_id})
                    MERGE (e)-[:BELONGS_TO]->(c)
                    """,
                    name=member_name,
                    doc_id=doc_id,
                    community_id=community_id,
                )

    driver.close()
    logger.info(f"[{doc_id}] Detected {len(communities)} communities")
    return communities

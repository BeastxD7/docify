import json
import logging
import re

from stores.llm import get_llm

logger = logging.getLogger(__name__)

_SCHEMA_PROMPT = """\
You are analyzing a document to design a knowledge graph schema for it.

Read the text samples below and suggest entity types and relationship types \
that best capture THIS specific document's domain and content.

Examples of domain-specific schemas:
- Kids story book → CHARACTER, ANIMAL, MAGICAL_OBJECT, PLACE | FRIENDS_WITH, LIVES_IN, OWNS, DEFEATS
- Game of Thrones → CHARACTER, HOUSE, LOCATION, BATTLE, TITLE | MEMBER_OF, RULES, KILLED, ALLIED_WITH, MARRIED_TO
- Legal document → PARTY, CLAUSE, JURISDICTION, OBLIGATION | BOUND_BY, GOVERNS, REFERS_TO, OVERRIDES
- Scientific paper → AUTHOR, INSTITUTION, CONCEPT, EXPERIMENT, FINDING | CONDUCTED_BY, PROVES, CONTRADICTS, CITES
- Business report → COMPANY, PERSON, PRODUCT, MARKET, METRIC | ACQUIRED, COMPETES_WITH, LAUNCHED, REPORTED

Rules:
- Suggest 5-8 entity types (UPPERCASE, specific to this document's domain)
- Suggest 5-8 relationship types (UPPERCASE, verb-based, meaningful for this domain)
- Be specific to the content — avoid generic types like THING or ITEM
- Return ONLY valid JSON, no explanation, no markdown

Text samples from the document:
{samples}

JSON:"""


def detect_schema(chunks: list[dict]) -> dict:
    """
    Sample the first N chunks and ask the LLM to infer the best
    entity/relation schema for this specific document.

    Returns {"entity_types": [...], "relation_types": [...]}.
    Falls back to generic defaults on any failure.
    """
    from extractors.graph_extractor import DEFAULT_ENTITY_TYPES, DEFAULT_RELATION_TYPES

    # Sample: first 15 chunks, truncate each to 400 chars to stay within token budget
    sample_chunks = chunks[:15]
    samples = "\n\n---\n\n".join(c["text"][:400] for c in sample_chunks)

    prompt = _SCHEMA_PROMPT.format(samples=samples)

    try:
        llm = get_llm(task="extraction")
        raw = llm.complete(prompt).text.strip()

        # Strip markdown fences
        text = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON in response")

        data = json.loads(text[start:end])
        entity_types = [t.strip().upper() for t in data.get("entity_types", []) if t.strip()]
        relation_types = [r.strip().upper() for r in data.get("relation_types", []) if r.strip()]

        if not entity_types or not relation_types:
            raise ValueError("Empty schema returned")

        logger.info(f"Auto-detected schema — entities: {entity_types} | relations: {relation_types}")
        return {"entity_types": entity_types, "relation_types": relation_types}

    except Exception as exc:
        logger.warning(f"Schema detection failed, falling back to defaults: {exc}")
        return {"entity_types": DEFAULT_ENTITY_TYPES, "relation_types": DEFAULT_RELATION_TYPES}

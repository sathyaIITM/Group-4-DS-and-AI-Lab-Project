from __future__ import annotations
from typing import Any
from analyst.data.catalogue import Catalogue, CatalogueTable

def describe_table(catalogue: Catalogue, table_name: str) -> dict[str, Any]:
    """Return a template-ready description from the frozen catalogue."""
    table = catalogue.get(table_name)
    return {
        "name": table.name, "status": table.status, "domain": table.domain,
        "topic": table.topic, "publisher": table.publisher, "periods": table.periods,
        "places": table.places, "absent_breakdowns": table.absent_breakdowns,
        "lacking_groups": table.lacking_groups, "lacking_definitions": table.lacking_definitions,
    }

def search_listing(catalogue: Catalogue, query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Lexically rank catalogue table metadata without inventing coverage."""
    tables = catalogue.real_tables()
    docs = [f"{t.name} {t.topic} {t.line} {t.publisher} {' '.join(t.describe_questions)}" for t in tables]
    query_tokens = set(query.lower().split())
    scores = [sum(token in set(doc.lower().split()) for token in query_tokens) for doc in docs]
    ranked = sorted(zip(tables, scores, strict=True), key=lambda pair: pair[1], reverse=True)
    return [{"name": t.name, "topic": t.topic, "domain": t.domain, "score": float(score)}
            for t, score in ranked[:limit] if score > 0]

def explain(catalogue: Catalogue, table_name: str) -> dict[str, Any]:
    """Explain known catalogue limitations for a table."""
    table: CatalogueTable = catalogue.get(table_name)
    return {"name": table.name, "available_periods": table.periods,
            "available_places": table.places, "missing_breakdowns": table.absent_breakdowns,
            "missing_groups": table.lacking_groups, "missing_definitions": table.lacking_definitions}

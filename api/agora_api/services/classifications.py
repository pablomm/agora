"""Statistical classifications (CNAE, CNO, CNED, CPA…): items by level or text, one item in context, correspondences."""

import json
import unicodedata
from functools import lru_cache

from agora_api.services.db import NotFound, catalog


def _fold(text: str) -> str:
    """Lower case without accents, to match "medicos" with "Médicos"."""
    return "".join(char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)).lower()


@lru_cache
def listing() -> list[dict]:
    with catalog() as db:
        rows = db.execute(
            "SELECT c.id, c.title_es AS title, c.version, c.levels, c.license, c.source_url, COUNT(i.code) AS items "
            "FROM classifications c LEFT JOIN classification_items i ON i.classification_id = c.id GROUP BY c.id ORDER BY c.id"
        ).fetchall()
    return [{**row, "levels": json.loads(row["levels"]), "license": json.loads(row["license"] or "null")} for row in rows]


@lru_cache
def _items(classification_id: str) -> list[dict]:
    if classification_id not in {entry["id"] for entry in listing()}:
        raise NotFound(f"Unknown classification {classification_id!r}; available: {[entry['id'] for entry in listing()]}")
    with catalog() as db:
        return db.execute(
            "SELECT code, label, level, level_name, parent FROM classification_items WHERE classification_id = ? ORDER BY position", [classification_id]
        ).fetchall()


def items(classification_id: str, level: int | None = None, parent: str | None = None, query: str | None = None, limit: int = 500) -> dict:
    """A classification's items in its order: of a level, under a parent, or whose code or label match every word of `query`."""
    rows = _items(classification_id)
    if level is not None:
        rows = [row for row in rows if row["level"] == level]
    if parent is not None:
        rows = [row for row in rows if row["parent"] == parent]
    if query:
        words = _fold(query).split()
        rows = [row for row in rows if all(word in _fold(f"{row['code']} {row['label']}") for word in words)]
    meta = next(entry for entry in listing() if entry["id"] == classification_id)
    return {"classification": meta, "total": len(rows), "items": rows[:limit]}


def item(classification_id: str, code: str) -> dict:
    """
    One item with its ancestors (from the top), its children, its correspondences either way, and
    the data dimensions that hold it: as a value (the code itself) or in a group of codes.
    """
    rows = {row["code"]: row for row in _items(classification_id)}
    code = code.replace(".", "")
    if code not in rows:
        raise NotFound(f"{classification_id} has no code {code!r}")
    ancestors, parent = [], rows[code]["parent"]
    while parent:
        ancestors.insert(0, rows[parent])
        parent = rows[parent]["parent"]
    with catalog() as db:
        to = db.execute(
            "SELECT to_classification AS classification, to_code AS code, to_label AS label, note FROM classification_correspondences WHERE from_classification = ? AND from_code = ?",
            [classification_id, code],
        ).fetchall()
        back = db.execute(
            "SELECT from_classification AS classification, from_code AS code, note FROM classification_correspondences WHERE to_classification = ? AND to_code = ?",
            [classification_id, code],
        ).fetchall()
        # Dimensions whose values are this classification's codes, or groups of them (an ancestor counts).
        lineage = [*(ancestor["code"] for ancestor in ancestors), code]
        held = db.execute(
            f"SELECT d.id AS dimension, v.code AS value, v.label FROM dimensions d JOIN dimension_values v ON v.dimension_id = d.id "
            f"WHERE d.classification = ? AND v.code IN ({','.join('?' * len(lineage))})",
            [classification_id, *lineage],
        ).fetchall()
        held += db.execute(
            f"SELECT d.id AS dimension, v.code AS value, v.label FROM dimensions d JOIN dimension_values v ON v.dimension_id = d.id "
            f"JOIN classification_correspondences c ON c.from_classification = d.id AND c.from_code = v.code AND c.to_classification = d.groups_of "
            f"WHERE d.groups_of = ? AND c.to_code IN ({','.join('?' * len(lineage))})",
            [classification_id, *lineage],
        ).fetchall()
    # Labels of the other side when it's a classification here.
    for pair in to + back:
        pair.setdefault("label", None)
        if pair["label"] is None and pair["classification"] in {entry["id"] for entry in listing()}:
            other = {row["code"]: row for row in _items(pair["classification"])}.get(pair["code"])
            pair["label"] = other["label"] if other else None
    return {
        "classification": classification_id,
        **rows[code],
        "ancestors": ancestors,
        "children": [row for row in rows.values() if row["parent"] == code],
        "correspondences": {"to": to, "from": back},
        "dimensions": held,
    }

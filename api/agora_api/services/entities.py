"""Territorial units: lookup, ancestors, children and name search."""

import re
import unicodedata

from agora_api.services.db import NotFound, catalog

COLUMNS = "id, level, code, name, label, parent_id, west, south, east, north"


def get(entity_id: str) -> dict:
    with catalog() as db:
        row = db.execute(f"SELECT {COLUMNS} FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if not row:
        raise NotFound(f"Unknown entity {entity_id!r}")
    return row


def find(entity_id: str) -> dict | None:
    try:
        return get(entity_id)
    except NotFound:
        return None


def names(entity_ids: list[str]) -> dict[str, str]:
    """Labels of the units known to the catalogue (units of other years, like old sections, have none)."""
    out = {}
    with catalog() as db:
        for start in range(0, len(entity_ids), 900):
            chunk = entity_ids[start : start + 900]
            rows = db.execute(f"SELECT id, label FROM entities WHERE id IN ({','.join('?' * len(chunk))})", chunk).fetchall()
            out.update({row["id"]: row["label"] for row in rows})
    return out


def ancestors(entity_id: str) -> list[dict]:
    """From the unit's parent up to Spain."""
    with catalog() as db:
        return db.execute(
            f"""
            WITH RECURSIVE chain(id, depth) AS (
              SELECT parent_id, 1 FROM entities WHERE id = ?
              UNION ALL
              SELECT e.parent_id, chain.depth + 1 FROM entities e JOIN chain ON e.id = chain.id WHERE e.parent_id IS NOT NULL
            )
            SELECT {COLUMNS} FROM entities JOIN chain USING (id) ORDER BY chain.depth
            """,
            (entity_id,),
        ).fetchall()


def children(entity_id: str, limit: int | None = 100) -> tuple[list[dict], int]:
    """The units directly inside one, by name: the first `limit` (None for all) and how many there are."""
    with catalog() as db:
        total = db.execute("SELECT count(*) AS n FROM entities WHERE parent_id = ?", (entity_id,)).fetchone()["n"]
        # SQLite's LIMIT -1 means no limit.
        rows = db.execute(f"SELECT {COLUMNS} FROM entities WHERE parent_id = ? ORDER BY label LIMIT ?", (entity_id, -1 if limit is None else limit)).fetchall()
    return rows, total


def describe(entity_id: str, limit: int | None = 50) -> dict:
    entity = get(entity_id)
    kids, total = children(entity_id, limit)
    return {**entity, "ancestors": ancestors(entity_id), "children": kids, "children_total": total}


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower()


def search(query: str, levels: list[str] | None = None, limit: int | None = 10) -> list[dict]:
    """
    Units by name, accents ignored: exact names first, then names starting with the query, then
    the rest; bigger units before smaller ones when they tie (the province of Madrid before…).
    """
    words = re.findall(r"\w+", query)
    if not words:
        return []
    match = " ".join(f'"{word}"*' for word in words)
    level_filter = f"AND e.level IN ({','.join('?' * len(levels))})" if levels else ""
    with catalog() as db:
        rows = db.execute(
            f"""
            SELECT e.id, e.level, e.code, e.name, e.label, e.parent_id, e.west, e.south, e.east, e.north, l.rank, p.name AS parent_name
            FROM entities_fts f JOIN entities e ON e.rowid = f.rowid JOIN levels l ON l.id = e.level
            LEFT JOIN entities p ON p.id = e.parent_id
            WHERE entities_fts MATCH ? {level_filter}
            """,
            [match, *(levels or [])],
        ).fetchall()
    folded = _fold(query.strip())

    def score(row: dict) -> tuple:
        name = _fold(row["name"])
        return (name != folded, not name.startswith(folded), -row["rank"], len(name))

    rows.sort(key=score)
    for row in rows:
        row.pop("rank")
    return rows[:limit]

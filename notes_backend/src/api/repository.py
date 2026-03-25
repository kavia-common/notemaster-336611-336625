from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import psycopg

from src.api.models import Note

logger = logging.getLogger("notes_backend.repository")


def _iso(dt):
    return dt  # Pydantic will serialize datetime to ISO automatically.


@dataclass(frozen=True)
class NoteRow:
    id: int
    title: str
    content: str
    created_at: Any
    updated_at: Any


def _note_from_row(row: dict[str, Any], tags: list[str]) -> Note:
    return Note(
        id=str(row["id"]),
        title=row["title"],
        content=row["content"],
        tags=tags,
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
    )


def _fetch_note_tags(conn: psycopg.Connection, note_id: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT t.name
        FROM note_tags nt
        JOIN tags t ON t.id = nt.tag_id
        WHERE nt.note_id = %s
        ORDER BY t.name ASC
        """,
        (note_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def _ensure_tags(conn: psycopg.Connection, tag_names: list[str]) -> list[int]:
    """Ensure tags exist and return their ids, in the same order as tag_names (unique, normalized)."""
    normalized = []
    seen = set()
    for t in tag_names:
        name = (t or "").strip()
        if not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        normalized.append(name)

    tag_ids: list[int] = []
    for name in normalized:
        row = conn.execute("SELECT id FROM tags WHERE name=%s", (name,)).fetchone()
        if row:
            tag_ids.append(int(row["id"]))
            continue

        inserted = conn.execute(
            "INSERT INTO tags(name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name RETURNING id",
            (name,),
        ).fetchone()
        tag_ids.append(int(inserted["id"]))
    return tag_ids


def _replace_note_tags(conn: psycopg.Connection, note_id: int, tag_names: list[str]) -> list[str]:
    """Replace tags for a note; creates tags as needed."""
    tag_ids = _ensure_tags(conn, tag_names)

    # Clear existing relationships and insert the new set.
    conn.execute("DELETE FROM note_tags WHERE note_id=%s", (note_id,))
    for tag_id in tag_ids:
        conn.execute(
            "INSERT INTO note_tags(note_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (note_id, tag_id),
        )

    # Return normalized names (sorted for stable UI).
    rows = conn.execute(
        """
        SELECT t.name
        FROM note_tags nt
        JOIN tags t ON t.id = nt.tag_id
        WHERE nt.note_id = %s
        ORDER BY t.name ASC
        """,
        (note_id,),
    ).fetchall()
    return [r["name"] for r in rows]


# PUBLIC_INTERFACE
def list_notes(conn: psycopg.Connection, *, q: str | None, tag: str | None, limit: int = 200) -> list[Note]:
    """List notes with optional search and tag filter.

    Contract:
    - Inputs:
        - q: optional search query (matches title/content/tag name substring, case-insensitive)
        - tag: optional tag name filter (exact match)
        - limit: max results
    - Output: notes sorted by updated_at desc.
    - Errors: surfaces psycopg exceptions.
    - Side effects: none.
    """
    q = (q or "").strip()
    tag = (tag or "").strip() or None

    where = []
    params: list[Any] = []

    if tag:
        where.append("EXISTS (SELECT 1 FROM note_tags nt JOIN tags t ON t.id=nt.tag_id WHERE nt.note_id=n.id AND t.name=%s)")
        params.append(tag)

    if q:
        where.append(
            """(
                n.title ILIKE %s OR
                n.content ILIKE %s OR
                EXISTS (
                    SELECT 1 FROM note_tags nt
                    JOIN tags t ON t.id=nt.tag_id
                    WHERE nt.note_id=n.id AND t.name ILIKE %s
                )
            )"""
        )
        like = f"%{q}%"
        params.extend([like, like, like])

    where_sql = ""
    if where:
        where_sql = "WHERE " + " AND ".join(where)

    rows = conn.execute(
        f"""
        SELECT n.id, n.title, n.content, n.created_at, n.updated_at
        FROM notes n
        {where_sql}
        ORDER BY n.updated_at DESC
        LIMIT %s
        """,
        (*params, limit),
    ).fetchall()

    notes: list[Note] = []
    for r in rows:
        note_id = int(r["id"])
        tags = _fetch_note_tags(conn, note_id)
        notes.append(_note_from_row(r, tags))
    return notes


# PUBLIC_INTERFACE
def create_note(conn: psycopg.Connection) -> Note:
    """Create a new empty note.

    Contract:
    - Output: newly created note with default title/content and no tags.
    """
    row = conn.execute(
        "INSERT INTO notes(title, content) VALUES (%s, %s) RETURNING id, title, content, created_at, updated_at",
        ("Untitled note", ""),
    ).fetchone()
    return _note_from_row(row, [])


# PUBLIC_INTERFACE
def patch_note(
    conn: psycopg.Connection,
    *,
    note_id_str: str,
    title: str | None,
    content: str | None,
    tags: list[str] | None,
) -> Note | None:
    """Autosave-friendly patch update.

    Contract:
    - Inputs:
        - note_id_str: note id as string (frontend contract)
        - title/content: optional fields to update; None => unchanged
        - tags: if provided, replaces the note's tag set
    - Output:
        - Note on success
        - None if note does not exist
    - Side effects:
        - updates notes row and/or note_tags relations
    """
    try:
        note_id = int(note_id_str)
    except ValueError:
        return None

    existing = conn.execute(
        "SELECT id, title, content, created_at, updated_at FROM notes WHERE id=%s",
        (note_id,),
    ).fetchone()
    if not existing:
        return None

    new_title = existing["title"] if title is None else title
    new_content = existing["content"] if content is None else content

    # Always issue UPDATE when title/content changed; trigger updates updated_at.
    if new_title != existing["title"] or new_content != existing["content"]:
        conn.execute(
            "UPDATE notes SET title=%s, content=%s WHERE id=%s",
            (new_title, new_content, note_id),
        )

    if tags is not None:
        replaced = _replace_note_tags(conn, note_id, tags)
    else:
        replaced = _fetch_note_tags(conn, note_id)

    refreshed = conn.execute(
        "SELECT id, title, content, created_at, updated_at FROM notes WHERE id=%s",
        (note_id,),
    ).fetchone()
    return _note_from_row(refreshed, replaced)


# PUBLIC_INTERFACE
def delete_note(conn: psycopg.Connection, *, note_id_str: str) -> bool:
    """Delete a note by id.

    Returns True if deleted, False if not found or invalid id.
    """
    try:
        note_id = int(note_id_str)
    except ValueError:
        return False

    res = conn.execute("DELETE FROM notes WHERE id=%s", (note_id,))
    return res.rowcount > 0


# PUBLIC_INTERFACE
def list_tags(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """List tags with note counts.

    Output items: {name: str, count: int}
    """
    rows = conn.execute(
        """
        SELECT t.name, COUNT(nt.note_id)::INT AS count
        FROM tags t
        LEFT JOIN note_tags nt ON nt.tag_id = t.id
        GROUP BY t.id
        ORDER BY t.name ASC
        """
    ).fetchall()
    return [{"name": r["name"], "count": int(r["count"])} for r in rows]

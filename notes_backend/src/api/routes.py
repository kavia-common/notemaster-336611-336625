from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from src.api.db import get_db_connection
from src.api.models import (
    ErrorResponse,
    NotesListResult,
    PatchNoteRequest,
    TagsListResult,
)
from src.api.repository import create_note, delete_note, list_notes, list_tags, patch_note

logger = logging.getLogger("notes_backend.routes")

router = APIRouter(tags=["Notes"])


def _get_conn():
    # Dependency that yields a connection per request.
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()


@router.get(
    "/notes",
    summary="List notes",
    description="List notes with optional search (q) and tag filter (tag).",
    response_model=NotesListResult,
    responses={500: {"model": ErrorResponse}},
    operation_id="list_notes",
)
def api_list_notes(
    q: Annotated[str | None, Query(default=None, description="Search query. Matches title/content/tags (ILIKE).")] = None,
    tag: Annotated[str | None, Query(default=None, description="Filter by exact tag name.")] = None,
    conn=Depends(_get_conn),
):
    """PUBLIC_INTERFACE

    GET /notes

    Autosave-friendly list endpoint consumed by the Next.js UI.
    """
    try:
        notes = list_notes(conn, q=q, tag=tag)
        return NotesListResult(notes=notes)
    except Exception as e:
        logger.exception("list_notes failed q=%r tag=%r", q, tag)
        raise HTTPException(status_code=500, detail="Failed to list notes") from e


@router.post(
    "/notes",
    summary="Create note",
    description="Create a new note with default title/content.",
    responses={500: {"model": ErrorResponse}},
    operation_id="create_note",
)
def api_create_note(conn=Depends(_get_conn)):
    """PUBLIC_INTERFACE

    POST /notes
    """
    try:
        conn.execute("BEGIN")
        note = create_note(conn)
        conn.commit()
        return note
    except Exception as e:
        conn.rollback()
        logger.exception("create_note failed")
        raise HTTPException(status_code=500, detail="Failed to create note") from e


@router.patch(
    "/notes/{note_id}",
    summary="Update note (autosave)",
    description="Patch note title/content and optionally replace tags (autosave-friendly).",
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    operation_id="patch_note",
)
def api_patch_note(note_id: str, payload: PatchNoteRequest, conn=Depends(_get_conn)):
    """PUBLIC_INTERFACE

    PATCH /notes/{note_id}

    Contract:
    - Omitted fields are unchanged.
    - If tags is provided, it replaces the entire tag set for the note.
    """
    try:
        conn.execute("BEGIN")
        updated = patch_note(
            conn,
            note_id_str=note_id,
            title=payload.title,
            content=payload.content,
            tags=payload.tags,
        )
        if not updated:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Note not found")
        conn.commit()
        return updated
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.exception("patch_note failed note_id=%s", note_id)
        raise HTTPException(status_code=500, detail="Failed to update note") from e


@router.delete(
    "/notes/{note_id}",
    summary="Delete note",
    description="Delete a note by id.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    operation_id="delete_note",
)
def api_delete_note(note_id: str, conn=Depends(_get_conn)):
    """PUBLIC_INTERFACE

    DELETE /notes/{note_id}
    """
    try:
        conn.execute("BEGIN")
        ok = delete_note(conn, note_id_str=note_id)
        if not ok:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Note not found")
        conn.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.exception("delete_note failed note_id=%s", note_id)
        raise HTTPException(status_code=500, detail="Failed to delete note") from e


tags_router = APIRouter(tags=["Tags"])


@tags_router.get(
    "/tags",
    summary="List tags",
    description="List all tags with counts of associated notes.",
    response_model=TagsListResult,
    responses={500: {"model": ErrorResponse}},
    operation_id="list_tags",
)
def api_list_tags(conn=Depends(_get_conn)):
    """PUBLIC_INTERFACE

    GET /tags
    """
    try:
        tags = list_tags(conn)
        return TagsListResult(tags=tags)
    except Exception as e:
        logger.exception("list_tags failed")
        raise HTTPException(status_code=500, detail="Failed to list tags") from e

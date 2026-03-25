from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard API error payload."""

    detail: str = Field(..., description="Human-readable error message.")
    code: str | None = Field(default=None, description="Optional stable error code.")


class Note(BaseModel):
    """A note with tags, formatted for the frontend contract."""

    id: str = Field(..., description="Note id (stringified bigint).")
    title: str = Field(..., description="Note title.")
    content: str = Field(..., description="Markdown content.")
    tags: list[str] = Field(default_factory=list, description="List of tag names.")
    updatedAt: datetime = Field(..., description="Last update timestamp (ISO).")
    createdAt: datetime = Field(..., description="Creation timestamp (ISO).")


class NotesListResult(BaseModel):
    """Response wrapper for note list endpoints."""

    notes: list[Note] = Field(default_factory=list, description="Notes ordered by updatedAt desc.")


class CreateNoteResponse(Note):
    """Create note returns a full Note."""


class PatchNoteRequest(BaseModel):
    """Autosave-friendly PATCH request.

    Fields are optional; omitted fields are left unchanged.
    """

    title: str | None = Field(default=None, description="New title.")
    content: str | None = Field(default=None, description="New markdown content.")
    tags: list[str] | None = Field(
        default=None,
        description="Replace the tag set with these tag names (creates tags as needed).",
    )


class Tag(BaseModel):
    """Tag summary returned by /tags."""

    name: str = Field(..., description="Tag name.")
    count: int = Field(..., description="Number of notes currently associated with this tag.")


class TagsListResult(BaseModel):
    """Response wrapper for tag list endpoint."""

    tags: list[Tag] = Field(default_factory=list, description="Tags sorted by name.")

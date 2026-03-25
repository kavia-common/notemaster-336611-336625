import os
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router as notes_router
from src.api.routes import tags_router


def _cors_origins_from_env() -> List[str]:
    """
    Read allowed CORS origins from env.

    - If NOTES_CORS_ORIGINS is set (comma-separated), use that.
    - Otherwise allow all (*) for template/dev convenience.
    """
    raw = os.getenv("NOTES_CORS_ORIGINS", "").strip()
    if not raw:
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


openapi_tags = [
    {"name": "Notes", "description": "Create, list/search, autosave-update, and delete notes."},
    {"name": "Tags", "description": "List tags and note counts."},
]

app = FastAPI(
    title="NoteMaster API",
    description=(
        "Backend API for the NoteMaster app.\n\n"
        "Frontend expects:\n"
        "- GET /notes?q=&tag=\n"
        "- POST /notes\n"
        "- PATCH /notes/{id} (autosave-friendly)\n"
        "- DELETE /notes/{id}\n"
        "- GET /tags\n"
    ),
    version="0.1.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins_from_env(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health"], summary="Health check", operation_id="health_check")
def health_check():
    """PUBLIC_INTERFACE

    Health check endpoint used by deployment and the frontend for connectivity checks.
    """
    return {"message": "Healthy"}


# Mount feature routers
app.include_router(notes_router)
app.include_router(tags_router)

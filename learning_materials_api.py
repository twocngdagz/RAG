"""Read-only API serving stored learning-material chapters to a frontend.

The store-and-serve milestone's serving half. Distinct from api.py, the old
"Tiny Learning RAG API" that generates a lesson on every request: this serves the
17 already-generated, grounded chapters straight from the database, deriving
nothing at request time.

Endpoints:
  GET /health
  GET /books                              -> [{slug, chapter_count}]
  GET /books/{slug}/chapters              -> light index (no bodies)
  GET /books/{slug}/chapters/{n}          -> the full contract-valid chapter document
  GET /books/{slug}/chapters/{n}/sections/{section}
                                          -> one section of a chapter

The full-chapter response is the stored document served as-is. It was validated
against book_learning_materials_contract.py on write, and re-modelling its
grounded-object tree into Pydantic here would duplicate that schema and invite
drift. Pydantic covers only the light index layer; the body is a passthrough.
"""

import json
import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import book_learning_materials_store as store

# Sections the frontend can request individually, mapped to how they sit in the
# chapter object. All are lists except the two chapter-level scalars.
CHAPTER_SECTIONS = {
    "chapter_summary",
    "estimated_study_time",
    "learning_objectives",
    "key_terms",
    "core_lessons",
    "worked_examples",
    "common_misconceptions",
    "practice_questions",
    "review_checklist",
}


class BookInfo(BaseModel):
    slug: str
    chapter_count: int


class ChapterIndexItem(BaseModel):
    id: str
    book_slug: str
    chapter_number: int
    chapter_title: str
    backend: str | None = None
    model: str | None = None
    contract_status: str


def create_app(engine: Engine | None = None) -> FastAPI:
    engine = engine or store.create_db(os.getenv("LEARNING_MATERIALS_DB_URL", store.DEFAULT_DB_URL))

    app = FastAPI(title="Learning Materials API", version="1.0")
    # A browser frontend on another origin needs CORS. Configurable; permissive by
    # default for local development.
    origins = os.getenv("LEARNING_MATERIALS_CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    def get_session():
        with Session(engine) as session:
            yield session

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/books", response_model=list[BookInfo])
    def get_books(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
        return store.list_books(session)

    @app.get("/books/{slug}/chapters", response_model=list[ChapterIndexItem])
    def get_chapter_index(
        slug: str, session: Session = Depends(get_session)
    ) -> list[dict[str, Any]]:
        rows = store.list_chapters(session, slug)
        if not rows:
            raise HTTPException(status_code=404, detail=f"No chapters for book {slug!r}.")
        return [row.index_item() for row in rows]

    @app.get("/books/{slug}/chapters/{chapter_number}")
    def get_chapter(
        slug: str, chapter_number: int, session: Session = Depends(get_session)
    ) -> dict[str, Any]:
        record = store.get_chapter(session, slug, chapter_number)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=f"Chapter {chapter_number} of book {slug!r} not found.",
            )
        return json.loads(record.document)

    @app.get("/books/{slug}/chapters/{chapter_number}/sections/{section}")
    def get_chapter_section(
        slug: str,
        chapter_number: int,
        section: str,
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        if section not in CHAPTER_SECTIONS:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown section {section!r}. Valid: {sorted(CHAPTER_SECTIONS)}.",
            )
        record = store.get_chapter(session, slug, chapter_number)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=f"Chapter {chapter_number} of book {slug!r} not found.",
            )
        chapter = json.loads(record.document)["learning_materials"]["chapters"][0]
        return {"section": section, "content": chapter.get(section)}

    return app


# Module-level app for `uvicorn learning_materials_api:app`.
app = create_app()

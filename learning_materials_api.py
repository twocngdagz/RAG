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

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

try:  # let the server pick up OLLAMA_API_KEY from .env for essay scoring
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import book_learning_materials_store as store
import essay_feedback

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
    has_enrichment: bool = False


class EssayFeedbackRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    essay: str = Field(min_length=1, max_length=8000)


def create_app(engine: Engine | None = None) -> FastAPI:
    engine = engine or store.create_db(os.getenv("LEARNING_MATERIALS_DB_URL", store.DEFAULT_DB_URL))

    app = FastAPI(title="Learning Materials API", version="1.0")
    # A browser frontend on another origin needs CORS. Configurable; permissive by
    # default for local development.
    origins = os.getenv("LEARNING_MATERIALS_CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins],
        allow_methods=["GET", "POST"],
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
        enriched = set(store.chapters_with_enrichment(session, slug))
        items = []
        for row in rows:
            item = row.index_item()
            item["has_enrichment"] = row.chapter_number in enriched
            items.append(item)
        return items

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

    @app.get("/books/{slug}/chapters/{chapter_number}/enrichment")
    def get_chapter_enrichment(
        slug: str, chapter_number: int, session: Session = Depends(get_session)
    ) -> dict[str, Any]:
        record = store.get_enrichment(session, slug, chapter_number)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=f"No enrichment for chapter {chapter_number} of book {slug!r}.",
            )
        return json.loads(record.document)

    @app.post("/books/{slug}/chapters/{chapter_number}/essay-feedback")
    def post_essay_feedback(
        slug: str, chapter_number: int, body: EssayFeedbackRequest
    ) -> dict[str, Any]:
        """Live scoring: assess a learner's essay against the PTE rubric via the
        hosted model. The app's only non-read endpoint; nothing is stored."""
        try:
            return essay_feedback.score_essay(body.prompt, body.essay)
        except RuntimeError as exc:  # OLLAMA_API_KEY not configured on the server
            raise HTTPException(status_code=503, detail=str(exc))
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Scoring model error: {exc}")
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail=f"Could not parse model output: {exc}")

    return app


# Module-level app for `uvicorn learning_materials_api:app`.
app = create_app()

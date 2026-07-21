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
from pathlib import Path
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
import describe_image_feedback
import essay_feedback
import swt_feedback

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
    prompt_type: str | None = None


class DescribeImageFeedbackRequest(BaseModel):
    item_id: str = Field(min_length=1, max_length=120)
    response: str = Field(min_length=1, max_length=4000)


class SwtFeedbackRequest(BaseModel):
    passage: str = Field(min_length=1, max_length=4000)
    summary: str = Field(min_length=1, max_length=1500)
    passage_id: str | None = None


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

    @app.get("/describe-image-items")
    def get_describe_image_items() -> list[dict[str, Any]]:
        """The Describe Image practice bank (chart SVG + computed ground truth)."""
        path = Path(os.getenv("DESCRIBE_IMAGE_ITEMS_FILE", "output/describe_image_items.json"))
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("items", data) if isinstance(data, dict) else data

    @app.get("/swt-passages")
    def get_swt_passages() -> list[dict[str, Any]]:
        """The validated Summarize Written Text source-passage bank."""
        path = Path(os.getenv("SWT_PASSAGES_FILE", "output/swt_passages.json"))
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("passages", data) if isinstance(data, dict) else data

    @app.get("/essay-prompts")
    def get_essay_prompts() -> list[dict[str, Any]]:
        """The validated Write Essay practice-prompt bank (essay_prompts.py output).
        Book-agnostic; read on each request so a regenerated bank shows up live."""
        path = Path(os.getenv("ESSAY_PROMPTS_FILE", "output/essay_prompts.json"))
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("prompts", data) if isinstance(data, dict) else data

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
        slug: str,
        chapter_number: int,
        body: EssayFeedbackRequest,
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        """Live scoring: assess a learner's essay against the PTE rubric via the
        hosted model, then persist the scored attempt so progress can be tracked."""
        try:
            feedback = essay_feedback.score_essay(body.prompt, body.essay)
        except RuntimeError as exc:  # OLLAMA_API_KEY not configured on the server
            raise HTTPException(status_code=503, detail=str(exc))
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Scoring model error: {exc}")
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail=f"Could not parse model output: {exc}")

        store.save_essay_attempt(
            session,
            book_slug=slug,
            chapter_number=chapter_number,
            prompt_text=body.prompt,
            essay_text=body.essay,
            feedback=feedback,
            prompt_type=body.prompt_type,
            task_type="write_essay",
        )
        session.commit()
        return feedback

    @app.post("/books/{slug}/chapters/{chapter_number}/swt-feedback")
    def post_swt_feedback(
        slug: str,
        chapter_number: int,
        body: SwtFeedbackRequest,
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        """Live scoring for Summarize Written Text, then persist the attempt."""
        try:
            feedback = swt_feedback.score_summary(body.passage, body.summary)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Scoring model error: {exc}")
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail=f"Could not parse model output: {exc}")

        store.save_essay_attempt(
            session,
            book_slug=slug,
            chapter_number=chapter_number,
            prompt_text=body.passage,
            essay_text=body.summary,
            feedback=feedback,
            prompt_type=body.passage_id,
            task_type="summarize_written_text",
        )
        session.commit()
        return feedback

    @app.post("/books/{slug}/chapters/{chapter_number}/describe-image-feedback")
    def post_describe_image_feedback(
        slug: str,
        chapter_number: int,
        body: DescribeImageFeedbackRequest,
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        """Score a Describe Image response against its item's computed facts."""
        try:
            item = describe_image_feedback.get_item(body.item_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        try:
            feedback = describe_image_feedback.score_response(item, body.response)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Scoring model error: {exc}")
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail=f"Could not parse model output: {exc}")

        store.save_essay_attempt(
            session,
            book_slug=slug,
            chapter_number=chapter_number,
            prompt_text=f"{item['title']} ({item['chart_type']} chart)",
            essay_text=body.response,
            feedback=feedback,
            prompt_type=item["id"],
            task_type="describe_image",
        )
        session.commit()
        return feedback

    @app.get("/books/{slug}/essay-attempts/{attempt_id}")
    def get_essay_attempt(
        slug: str, attempt_id: int, session: Session = Depends(get_session)
    ) -> dict[str, Any]:
        """One saved attempt in full — prompt, essay, and the complete feedback."""
        rec = session.get(store.EssayAttempt, attempt_id)
        if rec is None or rec.book_slug != slug:
            raise HTTPException(status_code=404, detail=f"Attempt {attempt_id} not found.")
        return {
            "id": rec.id,
            "chapter_number": rec.chapter_number,
            "created_at": rec.created_at,
            "prompt_type": rec.prompt_type,
            "prompt_text": rec.prompt_text,
            "essay_text": rec.essay_text,
            "feedback": json.loads(rec.feedback),
        }

    @app.get("/books/{slug}/essay-attempts")
    def get_essay_attempts(
        slug: str,
        task_type: str | None = None,
        session: Session = Depends(get_session),
    ) -> list[dict[str, Any]]:
        """Scored writing attempts for a book, newest first — the practice history.
        Optionally filtered to one task (write_essay, summarize_written_text)."""
        out = []
        for rec in store.list_essay_attempts(session, slug, task_type=task_type):
            fb = json.loads(rec.feedback)
            out.append({
                "id": rec.id,
                "chapter_number": rec.chapter_number,
                "task_type": rec.task_type,
                "prompt_type": rec.prompt_type,
                "prompt_excerpt": (rec.prompt_text[:90] + "…") if len(rec.prompt_text) > 90 else rec.prompt_text,
                "raw_total": rec.raw_total,
                "max_raw_total": rec.max_raw_total,
                "word_count": rec.word_count,
                "created_at": rec.created_at,
                "traits": [
                    {"name": t.get("name"), "score": t.get("score"), "max": t.get("max")}
                    for t in fb.get("traits", [])
                ],
            })
        return out

    return app


# Module-level app for `uvicorn learning_materials_api:app`.
app = create_app()

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
import time
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
import math_practice_items
import math_reasoning_feedback
import math_reasoning_items
import reading_mcq_items
import spaced_repetition
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


class ReadingMcqAnswerRequest(BaseModel):
    item_id: str = Field(min_length=1, max_length=120)
    chosen: list[str] = Field(default_factory=list, max_length=8)


def _load_mcq_bank() -> list[dict[str, Any]]:
    path = Path(os.getenv("READING_MCQ_ITEMS_FILE", "output/reading_mcq_items.json"))
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("items", data) if isinstance(data, dict) else data


def _load_math_practice_bank() -> list[dict[str, Any]]:
    path = Path(os.getenv("MATH_PRACTICE_ITEMS_FILE", "output/math_practice_items.json"))
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("items", data) if isinstance(data, dict) else data


def _load_math_reasoning_bank() -> list[dict[str, Any]]:
    path = Path(os.getenv("MATH_REASONING_ITEMS_FILE", "output/math_reasoning_items.json"))
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("items", data) if isinstance(data, dict) else data


class MathPracticeAnswerRequest(BaseModel):
    item_id: str = Field(min_length=1, max_length=120)
    answer: str = Field(default="", max_length=60)


class MathReasoningAnswerRequest(BaseModel):
    item_id: str = Field(min_length=1, max_length=120)
    response: str = Field(default="", max_length=3000)


class SwtFeedbackRequest(BaseModel):
    passage: str = Field(min_length=1, max_length=4000)
    summary: str = Field(min_length=1, max_length=1500)
    passage_id: str | None = None


# Which tasks let a model decide the score. Used to disclose grading on attempts
# saved before `scored_by` existed — the stored feedback blob is opaque JSON, so
# the task type is the only thing left to derive it from.
MODEL_SCORED_TASKS = {"write_essay", "summarize_written_text", "describe_image"}

# ...and which traits inside those rubrics code actually computed, so a back-filled
# attempt is labelled accurately rather than uniformly. Form was measured in code
# long before this field existed; calling it an AI judgement would be a new untruth
# told to fix an old silence.
CODE_SCORED_TRAITS_BY_TASK = {
    "write_essay": essay_feedback.CODE_SCORED_TRAITS,
    "summarize_written_text": swt_feedback.CODE_SCORED_TRAITS,
}


def _with_scoring_disclosure(feedback: dict[str, Any], task_type: str | None) -> dict[str, Any]:
    """Guarantee every feedback payload says who decided the score.

    A learner cannot tell a measured mark from a judged one by looking at it, and
    the payloads used to be silent about the difference. New payloads set this at
    the source; this fills it in for everything already in the database.
    """
    if not isinstance(feedback, dict):
        return feedback
    feedback.setdefault("scored_by", "model" if task_type in MODEL_SCORED_TASKS else "code")
    default = feedback["scored_by"]
    code_traits = CODE_SCORED_TRAITS_BY_TASK.get(task_type or "", frozenset())
    for trait in feedback.get("traits", []) or []:
        if not isinstance(trait, dict):
            continue
        if trait.get("advisory"):
            # the model's opinion, but it scores nothing — `advisory` carries that
            trait.setdefault("scored_by", "model")
        elif trait.get("name") in code_traits:
            trait.setdefault("scored_by", "code")
        else:
            trait.setdefault("scored_by", default)
    return feedback


def _mcq_verdict(result: dict[str, Any], item: dict[str, Any]) -> str:
    """One plain sentence a learner can act on."""
    if result["score"] == result["max_score"]:
        return "Correct."
    if item["mode"] == "single":
        return f"Not quite — the answer was {result['correct_keys'][0]}."
    parts = []
    if result["wrong"]:
        parts.append(f"you chose {', '.join(result['wrong'])} which the passage does not support")
    if result["missed"]:
        parts.append(f"you missed {', '.join(result['missed'])}")
    tail = "; ".join(parts) if parts else "review the explanations below"
    floored = " Choosing wrong options costs marks, so this scored 0." if result["floored"] else ""
    return f"{result['score']} of {result['max_score']} — {tail}.{floored}"


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

    @app.get("/reading-mcq-items")
    def get_reading_mcq_items() -> list[dict[str, Any]]:
        """The Reading Multiple-Choice bank, with the answers stripped out.

        The key and the per-option explanations are deliberately withheld until
        the learner submits — otherwise the answers sit in the page source and
        the practice is worthless."""
        return [
            {k: v for k, v in item.items() if k not in ("correct", "rationale")}
            for item in _load_mcq_bank()
        ]

    def _public_item(item: dict[str, Any]) -> dict[str, Any]:
        withheld = {"answer_num", "answer_den", "answer_tex", "answer_plain",
                    "answer_is_reduced"}
        return {k: v for k, v in item.items() if k not in withheld}

    @app.get("/math-practice-items")
    def get_math_practice_items() -> list[dict[str, Any]]:
        """The maths practice bank, with the computed answer withheld.

        The answer is revealed only on submit — otherwise it sits in the page
        source. Every item's answer is computed by code, so marking is
        deterministic and no model runs."""
        return [_public_item(item) for item in _load_math_practice_bank()]

    @app.get("/books/{slug}/math-practice-next")
    def get_math_practice_next(
        slug: str, after: str | None = None, session: Session = Depends(get_session)
    ) -> dict[str, Any]:
        """The next item the spaced-repetition scheduler chooses, plus progress.

        The Learning Engine (V2) decides this deterministically from the learner's
        per-item state — due items first (weakest), then new, then study-ahead —
        never the model. `after` is the item just answered, so it isn't repeated."""
        bank = _load_math_practice_bank()
        by_id = {i["id"]: i for i in bank}
        states = store.load_math_states(session)
        now = time.time()
        item_id, reason = spaced_repetition.pick_next(states, list(by_id), now, avoid=after)
        summary = spaced_repetition.summary(states, list(by_id), now)
        if item_id is None:
            return {"item": None, "reason": reason, "progress": summary}
        return {"item": _public_item(by_id[item_id]), "reason": reason, "progress": summary}

    def _public_reasoning_item(item: dict[str, Any]) -> dict[str, Any]:
        """Everything that would give the reasoning away is withheld until submit —
        the answer, the working values, the worked example and the rubric."""
        withheld = {"answer_num", "answer_den", "answer_plain", "working_tokens",
                    "working_min", "question_values", "rubric", "model_answer"}
        return {k: v for k, v in item.items() if k not in withheld}

    @app.get("/books/{slug}/math-reasoning-next")
    def get_math_reasoning_next(
        slug: str, after: str | None = None, session: Session = Depends(get_session)
    ) -> dict[str, Any]:
        """The next reasoning item the scheduler chooses, plus progress.

        Reasoning items share the one Learning Engine and the one state table with
        the quick practice — same scheduling rules, a different kind of question."""
        bank = _load_math_reasoning_bank()
        by_id = {i["id"]: i for i in bank}
        states = store.load_math_states(session)
        now = time.time()
        item_id, reason = spaced_repetition.pick_next(states, list(by_id), now, avoid=after)
        summary = spaced_repetition.summary(states, list(by_id), now)
        if item_id is None:
            return {"item": None, "reason": reason, "progress": summary}
        return {"item": _public_reasoning_item(by_id[item_id]), "reason": reason, "progress": summary}

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
        return _with_scoring_disclosure(feedback, "write_essay")

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
        return _with_scoring_disclosure(feedback, "summarize_written_text")

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
        return _with_scoring_disclosure(feedback, "describe_image")

    @app.post("/books/{slug}/chapters/{chapter_number}/math-practice-answer")
    def post_math_practice_answer(
        slug: str,
        chapter_number: int,
        body: MathPracticeAnswerRequest,
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        """Mark a maths practice answer and record it in the history.

        No model is involved: the answer was computed by code and the learner's
        answer is checked exactly (equal value AND simplest form). The V2
        'correct is computable' principle, made a feature."""
        item = next((i for i in _load_math_practice_bank() if i.get("id") == body.item_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Item {body.item_id} not found.")

        result = math_practice_items.check_answer(item, body.answer)
        score = 1 if result["correct"] else 0

        # Update the spaced-repetition schedule for this item (the Learning
        # Engine's state), deterministically, then report the new progress.
        now = time.time()
        states = store.load_math_states(session)
        state = states.get(item["id"]) or spaced_repetition.ItemState(item_id=item["id"])
        spaced_repetition.update(state, correct=result["correct"], now=now)
        store.save_math_state(session, state)
        states[item["id"]] = state
        progress = spaced_repetition.summary(states, [i["id"] for i in _load_math_practice_bank()], now)
        feedback = {
            **result,
            "word_count": 0,
            "gating_applied": False,
            "raw_total": score,
            "max_raw_total": 1,
            "skill": item.get("skill"),
            "skill_title": item.get("skill_title"),
            "capability": item.get("capability"),
            "prompt": item.get("prompt"),
            # capability-scored, matching the V2 evaluation model
            "traits": [{
                "name": item.get("capability") or "application",
                "score": score, "max": 1, "evidence": "", "fix": "",
            }],
            "top_priorities": [],
            "one_line_verdict": result["message"],
            "progress": progress,
            "mastered_now": state.is_mastered,
        }
        store.save_essay_attempt(
            session,
            book_slug=slug,
            chapter_number=chapter_number,
            prompt_text=f"{item.get('skill_title', 'Maths')}: {item['prompt_inline']}",
            essay_text=(body.answer or "(no answer)"),
            feedback=feedback,
            prompt_type=item["id"],
            task_type="math_practice",
        )
        session.commit()
        return _with_scoring_disclosure(feedback, "math_practice")

    @app.post("/books/{slug}/chapters/{chapter_number}/math-reasoning-answer")
    def post_math_reasoning_answer(
        slug: str,
        chapter_number: int,
        body: MathReasoningAnswerRequest,
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        """Mark an open reasoning response: code decides, the model only advises.

        The split is the point of this endpoint. Code owns the mark (right answer,
        working shown) and the schedule. The model's read on the *explanation* is
        attached alongside, flagged advisory, and is allowed to fail — if the coach
        is down the learner is still marked, because advisory means non-essential.
        """
        item = next((i for i in _load_math_reasoning_bank() if i.get("id") == body.item_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Item {body.item_id} not found.")

        det = math_reasoning_items.check_working(item, body.response)
        score = int(det["answer_shown"]) + int(det["working_shown"])

        # The schedule moves on the deterministic verdict only. An advisory opinion
        # must never decide when a child sees a question again.
        now = time.time()
        states = store.load_math_states(session)
        state = states.get(item["id"]) or spaced_repetition.ItemState(item_id=item["id"])
        spaced_repetition.update(state, correct=det["correct"], now=now)
        store.save_math_state(session, state)
        states[item["id"]] = state
        progress = spaced_repetition.summary(
            states, [i["id"] for i in _load_math_reasoning_bank()], now
        )

        advisory: dict[str, Any] | None = None
        advisory_error: str | None = None
        try:
            advisory = math_reasoning_feedback.score_reasoning(item, body.response, det)
        except RuntimeError:
            advisory_error = "The explanation coach is not set up yet, so only the maths was checked."
        except httpx.HTTPError:
            advisory_error = "The explanation coach could not be reached, so only the maths was checked."
        except (ValueError, json.JSONDecodeError):
            advisory_error = "The explanation coach replied in a form I could not read, so only the maths was checked."

        traits: list[dict[str, Any]] = [
            # advisory is stated, not implied by absence, so the UI can never
            # render a model's opinion as if it were a mark
            {"name": "right_answer", "score": int(det["answer_shown"]), "max": 1,
             "evidence": "", "fix": "", "advisory": False},
            {"name": "working_shown", "score": int(det["working_shown"]), "max": 1,
             "evidence": "", "fix": "", "advisory": False},
        ]
        if advisory:
            traits.extend(advisory["traits"])

        feedback = {
            **det,
            "word_count": len((body.response or "").split()),
            "gating_applied": False,
            # the mark is the deterministic part, and only the deterministic part
            "raw_total": score,
            "max_raw_total": 2,
            "marking": "computed; explanation feedback is advisory",
            "kind": "reasoning",
            "skill": item.get("skill"),
            "skill_title": item.get("skill_title"),
            "capability": item.get("capability"),
            "question": item.get("question"),
            # revealed only now that they have answered
            "rubric": item.get("rubric", []),
            "model_answer": item.get("model_answer"),
            "traits": traits,
            "advisory": advisory,
            "advisory_error": advisory_error,
            "top_priorities": [advisory["next_step"]] if advisory else [],
            "one_line_verdict": det["message"],
            "progress": progress,
            "mastered_now": state.is_mastered,
        }
        store.save_essay_attempt(
            session,
            book_slug=slug,
            chapter_number=chapter_number,
            prompt_text=f"{item.get('skill_title', 'Reasoning')}: {item['question']}",
            essay_text=(body.response or "(no response)"),
            feedback=feedback,
            prompt_type=item["id"],
            task_type="math_reasoning",
        )
        session.commit()
        return _with_scoring_disclosure(feedback, "math_reasoning")

    @app.post("/books/{slug}/chapters/{chapter_number}/reading-mcq-answer")
    def post_reading_mcq_answer(
        slug: str,
        chapter_number: int,
        body: ReadingMcqAnswerRequest,
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        """Mark a Reading Multiple-Choice answer and record it in the history.

        No model is involved: the marking is the official rule applied in code,
        so the same answer always earns the same mark."""
        item = next((i for i in _load_mcq_bank() if i.get("id") == body.item_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Item {body.item_id} not found.")

        result = reading_mcq_items.score_answer(item, body.chosen)
        # Shaped like the other feedback payloads so one history list, one detail
        # view and one progress chart can cover every task type.
        feedback = {
            **result,
            "word_count": 0,
            "gating_applied": False,
            "raw_total": result["score"],
            "max_raw_total": result["max_score"],
            "mode": item["mode"],
            "question": item["question"],
            "options": item["options"],
            "skill": item.get("skill"),
            "traits": [{
                "name": item.get("skill") or "reading",
                "score": result["score"],
                "max": result["max_score"],
                "evidence": "", "fix": "",
            }],
            "top_priorities": [],
            "one_line_verdict": _mcq_verdict(result, item),
        }
        store.save_essay_attempt(
            session,
            book_slug=slug,
            chapter_number=chapter_number,
            prompt_text=f"{item['title']} — {item['question']}",
            essay_text=", ".join(result["chosen_keys"]) or "(no answer)",
            feedback=feedback,
            prompt_type=item["id"],
            task_type="reading_multiple_choice",
        )
        session.commit()
        return _with_scoring_disclosure(feedback, "reading_multiple_choice")

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
            # older attempts predate `scored_by`; fill it in from the task type so
            # the detail view discloses AI grading for history too, not just new work
            "feedback": _with_scoring_disclosure(json.loads(rec.feedback), rec.task_type),
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
            fb = _with_scoring_disclosure(json.loads(rec.feedback), rec.task_type)
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
                "scored_by": fb.get("scored_by"),
                "traits": [
                    {"name": t.get("name"), "score": t.get("score"), "max": t.get("max"),
                     "scored_by": t.get("scored_by"), "advisory": bool(t.get("advisory"))}
                    for t in fb.get("traits", [])
                ],
            })
        return out

    return app


# Module-level app for `uvicorn learning_materials_api:app`.
app = create_app()
